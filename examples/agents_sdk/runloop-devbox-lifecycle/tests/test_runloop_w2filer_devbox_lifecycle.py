from __future__ import annotations

import inspect
import io
import json
import sys
import threading
import time
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest


def _install_agents_sdk_stubs() -> None:
    """Install minimal SDK stubs for unit tests that do not exercise live SDK behavior."""
    if "agents" in sys.modules and "openai.types.shared.reasoning" in sys.modules:
        return

    class _KeywordInit:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            for key, value in kwargs.items():
                setattr(self, key, value)

    class _MaxTurnsExceeded(Exception):
        pass

    class _Runner:
        @staticmethod
        def run_streamed(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("Runner.run_streamed is not used by these offline tests")

    openai_module = types.ModuleType("openai")
    openai_types_module = types.ModuleType("openai.types")
    openai_types_shared_module = types.ModuleType("openai.types.shared")
    reasoning_module = types.ModuleType("openai.types.shared.reasoning")
    reasoning_module.Reasoning = _KeywordInit

    agents_module = types.ModuleType("agents")
    agents_module.MaxTurnsExceeded = _MaxTurnsExceeded
    agents_module.ModelSettings = _KeywordInit
    agents_module.Runner = _Runner

    agents_run_module = types.ModuleType("agents.run")
    agents_run_module.RunConfig = _KeywordInit

    agents_sandbox_module = types.ModuleType("agents.sandbox")
    agents_sandbox_module.Manifest = _KeywordInit
    agents_sandbox_module.SandboxAgent = _KeywordInit
    agents_sandbox_module.SandboxRunConfig = _KeywordInit

    capabilities_module = types.ModuleType("agents.sandbox.capabilities")
    capabilities_module.Shell = _KeywordInit

    entries_module = types.ModuleType("agents.sandbox.entries")
    entries_module.Dir = _KeywordInit
    entries_module.File = _KeywordInit
    entries_module.LocalFile = _KeywordInit

    session_module = types.ModuleType("agents.sandbox.session")
    session_module.SandboxSession = _KeywordInit

    extensions_module = types.ModuleType("agents.extensions")
    extensions_sandbox_module = types.ModuleType("agents.extensions.sandbox")
    extensions_sandbox_module.RunloopSandboxClient = _KeywordInit
    extensions_sandbox_module.RunloopSandboxClientOptions = _KeywordInit
    extensions_sandbox_module.RunloopSandboxSessionState = type(
        "RunloopSandboxSessionState",
        (_KeywordInit,),
        {},
    )
    extensions_sandbox_module.RunloopTimeouts = _KeywordInit
    extensions_sandbox_module.RunloopUserParameters = _KeywordInit

    sys.modules.setdefault("openai", openai_module)
    sys.modules.setdefault("openai.types", openai_types_module)
    sys.modules.setdefault("openai.types.shared", openai_types_shared_module)
    sys.modules.setdefault("openai.types.shared.reasoning", reasoning_module)
    sys.modules.setdefault("agents", agents_module)
    sys.modules.setdefault("agents.run", agents_run_module)
    sys.modules.setdefault("agents.sandbox", agents_sandbox_module)
    sys.modules.setdefault("agents.sandbox.capabilities", capabilities_module)
    sys.modules.setdefault("agents.sandbox.entries", entries_module)
    sys.modules.setdefault("agents.sandbox.session", session_module)
    sys.modules.setdefault("agents.extensions", extensions_module)
    sys.modules.setdefault("agents.extensions.sandbox", extensions_sandbox_module)


def _load_module(name: str, path: Path) -> Any:
    spec = spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    assert isinstance(module, ModuleType)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return cast(Any, module)


REPO_ROOT = Path(__file__).resolve().parents[4]
EXAMPLE_DIR = Path(__file__).resolve().parents[1]
_install_agents_sdk_stubs()
RUNLOOP_LIFECYCLE_EXAMPLE = _load_module(
    "runloop_devbox_lifecycle_example",
    EXAMPLE_DIR / "runloop_w2filer_devbox_lifecycle.py",
)
_load_module("parse_w2", EXAMPLE_DIR / "data" / "parse_w2.py")
BUILD_FORM_1040 = _load_module("build_form1040", EXAMPLE_DIR / "data" / "build_form1040.py")
REFRESH_TAX_RETURN = _load_module(
    "refresh_tax_return",
    EXAMPLE_DIR / "data" / "refresh_tax_return.py",
)


class _FakeDirEntry:
    def __init__(self, path: Path, *, is_dir: bool) -> None:
        self.path = str(path)
        self._is_dir = is_dir

    def is_dir(self) -> bool:
        return self._is_dir


class _FakeExecResult:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", exit_code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code

    def ok(self) -> bool:
        return self.exit_code == 0


class _FakeSession:
    def __init__(
        self,
        files: dict[Path, bytes] | None = None,
        *,
        mtimes_ns: dict[Path, int] | None = None,
    ) -> None:
        self._output_root = Path("/root/project/output")
        if files is None:
            self._files = {
                self._output_root / "tax_return_summary.json": b'{"status": "ok"}\n',
                self._output_root / "filing_checklist.md": b"# Checklist\n",
                self._output_root / "f1040_form_data.json": b'{"form": "1040"}\n',
            }
        else:
            self._files = files
        self._mtimes_ns = dict(mtimes_ns or {})
        self._next_mtime_ns = max(self._mtimes_ns.values(), default=0) + 1
        for path in self._files:
            self._mtimes_ns.setdefault(path, self._allocate_mtime_ns())

    def normalize_path(self, path: str) -> Path:
        assert path == "output"
        return self._output_root

    def _allocate_mtime_ns(self) -> int:
        mtime_ns = self._next_mtime_ns
        self._next_mtime_ns += 1
        return mtime_ns

    def set_file(self, path: Path, payload: bytes, *, mtime_ns: int | None = None) -> None:
        self._files[path] = payload
        self._mtimes_ns[path] = mtime_ns if mtime_ns is not None else self._allocate_mtime_ns()

    async def ls(self, path: Path) -> list[_FakeDirEntry]:
        assert path == self._output_root
        return [_FakeDirEntry(file_path, is_dir=False) for file_path in sorted(self._files)]

    async def read(self, path: Path) -> io.BytesIO:
        return io.BytesIO(self._files[path])

    async def exec(
        self,
        *command: str,
        shell: bool = True,
        user: object | None = None,
        timeout: float | None = None,
    ) -> _FakeExecResult:
        assert user is None
        assert timeout is None
        assert shell is False
        assert command[:2] == ("python3", "-c")
        path = Path(command[3])
        if path not in self._files:
            return _FakeExecResult(exit_code=2)
        return _FakeExecResult(stdout=f"{self._mtimes_ns[path]}\n".encode())


def _valid_tax_summary_bytes() -> bytes:
    return json.dumps(
        {
            "success": True,
            "documentsProcessed": [],
            "form1040": {},
            "summary": {},
        }
    ).encode("utf-8")


def _sample_w2_fields() -> dict[str, object]:
    return {
        "taxpayer_name": "Jane Doe",
        "first_name": "Jane",
        "last_name": "Doe",
        "ssn": "123-45-6789",
        "address": "123 Main St",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94105",
        "employer_name": "Acme Corp",
        "employer_ein": "12-3456789",
        "employer_address": "456 Market St",
        "employer_city": "San Francisco",
        "employer_state": "CA",
        "employer_zip_code": "94105",
        "wages": 50000.0,
        "tax_withheld": 5000.0,
        "social_security_wages": 50000.0,
        "social_security_tax_withheld": 3100.0,
        "medicare_wages": 50000.0,
        "medicare_tax_withheld": 725.0,
    }


def _sample_agent_adjustments() -> dict[str, object]:
    return {
        "other_income": {
            "taxable_interest": 125.0,
            "qualified_dividends": 25.0,
        },
        "additional_payments": {
            "estimated_tax_payments": 100.0,
            "refundable_credits": 50.0,
        },
        "documents": [
            {
                "filename": "supplemental-1099-int.pdf",
                "type": "1099-int",
                "mappedAmounts": {
                    "other_income": {"taxable_interest": 125.0, "qualified_dividends": 25.0},
                    "additional_payments": {
                        "estimated_tax_payments": 100.0,
                        "refundable_credits": 50.0,
                    },
                },
                "notes": ["Mapped non-W-2 income into the filing inputs."],
            }
        ],
    }


def test_resolve_w2_path_prefers_cli_override(tmp_path: Path) -> None:
    custom_w2 = tmp_path / "custom-w2.pdf"
    custom_w2.write_bytes(b"%PDF-1.4\n")

    resolved = RUNLOOP_LIFECYCLE_EXAMPLE._resolve_w2_path(
        cli_w2_path=str(custom_w2),
        stdin_isatty=True,
    )

    assert resolved == custom_w2.resolve()


def test_resolve_w2_path_uses_default_when_prompt_is_blank() -> None:
    resolved = RUNLOOP_LIFECYCLE_EXAMPLE._resolve_w2_path(
        cli_w2_path=None,
        stdin_isatty=True,
        input_func=lambda _prompt: "",
    )

    assert resolved == RUNLOOP_LIFECYCLE_EXAMPLE.DEFAULT_W2_PATH.resolve()


def test_resolve_w2_path_uses_default_for_non_tty(capsys: pytest.CaptureFixture[str]) -> None:
    resolved = RUNLOOP_LIFECYCLE_EXAMPLE._resolve_w2_path(
        cli_w2_path=None,
        stdin_isatty=False,
    )

    assert resolved == RUNLOOP_LIFECYCLE_EXAMPLE.DEFAULT_W2_PATH.resolve()
    assert "Non-interactive run detected." in capsys.readouterr().out


def test_resolve_additional_w2_paths_validates_cli_inputs(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"%PDF-1.4\n")
    second.write_bytes(b"%PDF-1.4\n")

    resolved = RUNLOOP_LIFECYCLE_EXAMPLE._resolve_additional_w2_paths([str(first), str(second)])

    assert resolved == [first.resolve(), second.resolve()]


def test_next_follow_up_w2_path_prefers_pending_cli_paths(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"%PDF-1.4\n")
    second.write_bytes(b"%PDF-1.4\n")
    pending = [first.resolve(), second.resolve()]

    selected = RUNLOOP_LIFECYCLE_EXAMPLE._next_follow_up_w2_path(
        pending_paths=pending,
        stdin_isatty=True,
        input_func=lambda _prompt: "no",
    )

    assert selected == first.resolve()
    assert pending == [second.resolve()]


def test_next_follow_up_w2_path_returns_none_when_user_declines() -> None:
    selected = RUNLOOP_LIFECYCLE_EXAMPLE._next_follow_up_w2_path(
        pending_paths=[],
        stdin_isatty=True,
        input_func=lambda _prompt: "n",
    )

    assert selected is None


def test_next_follow_up_w2_path_returns_none_for_non_tty_without_pending_paths() -> None:
    selected = RUNLOOP_LIFECYCLE_EXAMPLE._next_follow_up_w2_path(
        pending_paths=[],
        stdin_isatty=False,
    )

    assert selected is None


def test_task_config_includes_source_document_filenames() -> None:
    payload = RUNLOOP_LIFECYCLE_EXAMPLE.json.loads(
        RUNLOOP_LIFECYCLE_EXAMPLE._task_config(
            filing_status="single",
            qualifying_children=0,
            source_document_filenames=["employee-w2.pdf", "spouse-w2.pdf"],
        ).decode("utf-8")
    )

    assert payload["source_document_filenames"] == ["employee-w2.pdf", "spouse-w2.pdf"]


@pytest.mark.asyncio
async def test_final_review_window_downloads_output_after_ack(tmp_path: Path) -> None:
    responses = iter(["yes", "y"])
    copied_files = await RUNLOOP_LIFECYCLE_EXAMPLE._run_final_review_window(
        _FakeSession(),
        devbox_name="devbox-123",
        download_dir=tmp_path / "downloads",
        stdin_isatty=True,
        review_timeout_s=1.0,
        input_func=lambda _prompt: next(responses),
    )

    assert [path.name for path in copied_files] == [
        "f1040_form_data.json",
        "filing_checklist.md",
        "tax_return_summary.json",
    ]
    assert (tmp_path / "downloads" / "filing_checklist.md").read_text(
        encoding="utf-8"
    ) == "# Checklist\n"
    assert (tmp_path / "downloads" / "tax_return_summary.json").read_text(
        encoding="utf-8"
    ) == '{"status": "ok"}\n'


@pytest.mark.asyncio
async def test_final_review_window_times_out_before_ack(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _slow_input(_prompt: str) -> str:
        time.sleep(0.05)
        return "yes"

    copied_files = await RUNLOOP_LIFECYCLE_EXAMPLE._run_final_review_window(
        _FakeSession(),
        devbox_name="devbox-123",
        download_dir=tmp_path / "downloads",
        stdin_isatty=True,
        review_timeout_s=0.01,
        input_func=_slow_input,
    )

    assert copied_files == []
    assert not (tmp_path / "downloads").exists()
    assert "review window expired before acknowledgment" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_prompt_with_deadline_does_not_wait_for_blocked_input() -> None:
    blocker = threading.Event()

    def _blocking_input(_prompt: str) -> str:
        blocker.wait(60)
        return "late response"

    started = time.monotonic()
    result = await RUNLOOP_LIFECYCLE_EXAMPLE._prompt_with_deadline(
        "Acknowledge the prepared filing? [y/N]: ",
        deadline=time.monotonic() + 0.01,
        input_func=_blocking_input,
    )
    elapsed = time.monotonic() - started

    assert result is None
    assert elapsed < 0.5


def test_tax_agent_instructions_describe_shell_exec_recovery() -> None:
    instructions = RUNLOOP_LIFECYCLE_EXAMPLE.TAX_AGENT_INSTRUCTIONS

    assert "Shell capability is backed by command execution inside this devbox" in instructions
    assert "`python3 taxpayer_data/refresh_tax_return.py ...` fails" in instructions
    assert "repair `taxpayer_data/agent_tax_adjustments.json` if needed" in instructions


def test_summary_turn_budget_constant_and_callsite() -> None:
    assert RUNLOOP_LIFECYCLE_EXAMPLE.SUMMARY_AGENT_MAX_TURNS == 10
    assert "max_turns=SUMMARY_AGENT_MAX_TURNS" in inspect.getsource(RUNLOOP_LIFECYCLE_EXAMPLE.main)


@pytest.mark.asyncio
async def test_validate_tax_summary_output_rejects_missing_file() -> None:
    with pytest.raises(RuntimeError, match=r"tax_return_summary\.json was not created"):
        await RUNLOOP_LIFECYCLE_EXAMPLE._validate_tax_summary_output(_FakeSession(files={}))


@pytest.mark.asyncio
async def test_validate_tax_summary_output_rejects_malformed_json() -> None:
    session = _FakeSession(
        files={
            RUNLOOP_LIFECYCLE_EXAMPLE.TAX_SUMMARY_PATH: b"{not json}\n",
        }
    )

    with pytest.raises(RuntimeError, match=r"tax_return_summary\.json is not valid JSON"):
        await RUNLOOP_LIFECYCLE_EXAMPLE._validate_tax_summary_output(session)


@pytest.mark.asyncio
async def test_validate_tax_summary_output_rejects_stale_existing_summary() -> None:
    session = _FakeSession(
        files={
            RUNLOOP_LIFECYCLE_EXAMPLE.TAX_SUMMARY_PATH: _valid_tax_summary_bytes(),
        },
        mtimes_ns={
            RUNLOOP_LIFECYCLE_EXAMPLE.TAX_SUMMARY_PATH: 100,
        },
    )

    with pytest.raises(RuntimeError, match="was not refreshed for the current prep round"):
        await RUNLOOP_LIFECYCLE_EXAMPLE._validate_tax_summary_output(
            session,
            previous_summary_mtime_ns=100,
        )


@pytest.mark.asyncio
async def test_run_tax_prep_round_retries_after_missing_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = _FakeSession(files={})
    prompts: list[str] = []

    async def _fake_run_agent(
        _agent: object,
        prompt: str,
        _session: object,
        *,
        workflow_name: str,
        max_turns: int = 30,
    ) -> str:
        prompts.append(prompt)
        if len(prompts) == 2:
            session.set_file(
                RUNLOOP_LIFECYCLE_EXAMPLE.TAX_SUMMARY_PATH,
                _valid_tax_summary_bytes(),
            )
            return "Recovered filing refresh complete"
        return "First attempt looked done"

    monkeypatch.setattr(RUNLOOP_LIFECYCLE_EXAMPLE, "_run_agent", _fake_run_agent)

    result = await RUNLOOP_LIFECYCLE_EXAMPLE._run_tax_prep_round(
        object(),
        "Refresh the filing.",
        session,
        round_label="Tax preparation round 2",
        workflow_name="workflow",
    )

    assert result == "Recovered filing refresh complete"
    assert len(prompts) == 2
    assert (
        "use shell/exec commands inside this devbox to diagnose the problem" in prompts[1].lower()
    )
    assert "Retrying with explicit shell/exec recovery guidance." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_tax_prep_round_retries_after_stale_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = _FakeSession(
        files={
            RUNLOOP_LIFECYCLE_EXAMPLE.TAX_SUMMARY_PATH: _valid_tax_summary_bytes(),
        },
        mtimes_ns={
            RUNLOOP_LIFECYCLE_EXAMPLE.TAX_SUMMARY_PATH: 100,
        },
    )
    prompts: list[str] = []

    async def _fake_run_agent(
        _agent: object,
        prompt: str,
        _session: object,
        *,
        workflow_name: str,
        max_turns: int = 30,
    ) -> str:
        prompts.append(prompt)
        if len(prompts) == 2:
            session.set_file(
                RUNLOOP_LIFECYCLE_EXAMPLE.TAX_SUMMARY_PATH,
                _valid_tax_summary_bytes(),
                mtime_ns=200,
            )
            return "Recovered filing refresh complete"
        return "First attempt left the previous summary in place"

    monkeypatch.setattr(RUNLOOP_LIFECYCLE_EXAMPLE, "_run_agent", _fake_run_agent)

    result = await RUNLOOP_LIFECYCLE_EXAMPLE._run_tax_prep_round(
        object(),
        "Refresh the filing.",
        session,
        round_label="Tax preparation round 2",
        workflow_name="workflow",
    )

    assert result == "Recovered filing refresh complete"
    assert len(prompts) == 2
    assert "was not refreshed for the current prep round" in prompts[1]
    assert "Retrying with explicit shell/exec recovery guidance." in capsys.readouterr().out


@pytest.mark.asyncio
async def test_run_tax_prep_round_retries_after_agent_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _FakeSession(files={})
    calls = 0

    async def _fake_run_agent(
        _agent: object,
        prompt: str,
        _session: object,
        *,
        workflow_name: str,
        max_turns: int = 30,
    ) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RUNLOOP_LIFECYCLE_EXAMPLE.MaxTurnsExceeded("Max turns exceeded")
        session.set_file(
            RUNLOOP_LIFECYCLE_EXAMPLE.TAX_SUMMARY_PATH,
            _valid_tax_summary_bytes(),
        )
        return "Recovered after retry"

    monkeypatch.setattr(RUNLOOP_LIFECYCLE_EXAMPLE, "_run_agent", _fake_run_agent)

    result = await RUNLOOP_LIFECYCLE_EXAMPLE._run_tax_prep_round(
        object(),
        "Refresh the filing.",
        session,
        round_label="Initial tax preparation",
        workflow_name="workflow",
    )

    assert result == "Recovered after retry"
    assert calls == 2


@pytest.mark.asyncio
async def test_run_tax_prep_round_raises_after_two_failed_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_run_agent(
        _agent: object,
        prompt: str,
        _session: object,
        *,
        workflow_name: str,
        max_turns: int = 30,
    ) -> str:
        return ""

    monkeypatch.setattr(RUNLOOP_LIFECYCLE_EXAMPLE, "_run_agent", _fake_run_agent)

    with pytest.raises(
        RuntimeError,
        match=r"Tax preparation round 3 failed after 2 attempts: agent returned no final response",
    ):
        await RUNLOOP_LIFECYCLE_EXAMPLE._run_tax_prep_round(
            object(),
            "Refresh the filing.",
            _FakeSession(files={}),
            round_label="Tax preparation round 3",
            workflow_name="workflow",
        )


def test_build_summary_uses_source_document_filename() -> None:
    summary = BUILD_FORM_1040.build_summary(
        _sample_w2_fields(),
        {
            "filing_status": "single",
            "qualifying_children": 0,
            "source_document_filename": "uploaded-w2.pdf",
        },
    )

    assert summary["documentsProcessed"][0]["filename"] == "uploaded-w2.pdf"


def test_build_summary_defaults_document_filename_when_absent() -> None:
    summary = BUILD_FORM_1040.build_summary(
        _sample_w2_fields(),
        {
            "filing_status": "single",
            "qualifying_children": 0,
        },
    )

    assert summary["documentsProcessed"][0]["filename"] == "sample_w2.pdf"


def test_build_summary_aggregates_multiple_w2s() -> None:
    second_w2 = _sample_w2_fields() | {
        "employer_name": "Other Corp",
        "employer_ein": "98-7654321",
        "wages": 25000.0,
        "tax_withheld": 2500.0,
        "social_security_wages": 25000.0,
        "social_security_tax_withheld": 1550.0,
        "medicare_wages": 25000.0,
        "medicare_tax_withheld": 362.5,
        "source_document_filename": "second-w2.pdf",
    }

    summary = BUILD_FORM_1040.build_summary(
        [
            _sample_w2_fields() | {"source_document_filename": "first-w2.pdf"},
            second_w2,
        ],
        {
            "filing_status": "single",
            "qualifying_children": 0,
        },
    )

    assert [item["filename"] for item in summary["documentsProcessed"]] == [
        "first-w2.pdf",
        "second-w2.pdf",
    ]
    assert summary["form1040"]["income"]["wages"] == pytest.approx(75_000.0)
    assert summary["form1040"]["payments"]["federalTaxWithheld"] == pytest.approx(7_500.0)
    assert summary["summary"]["wages"] == pytest.approx(75_000.0)
    assert summary["summary"]["totalWithholdings"] == pytest.approx(7_500.0)


def test_build_summary_rejects_mismatched_taxpayer() -> None:
    mismatched_w2 = _sample_w2_fields() | {
        "first_name": "Janet",
        "taxpayer_name": "Janet Doe",
        "ssn": "999-99-9999",
        "source_document_filename": "other-w2.pdf",
    }

    with pytest.raises(ValueError, match="same taxpayer"):
        BUILD_FORM_1040.build_summary(
            [
                _sample_w2_fields() | {"source_document_filename": "first-w2.pdf"},
                mismatched_w2,
            ],
            {
                "filing_status": "single",
                "qualifying_children": 0,
            },
        )


@pytest.mark.parametrize("qualifying_children", [-1, 1.9, "1.9", True])
def test_build_summary_rejects_invalid_qualifying_children(qualifying_children: object) -> None:
    with pytest.raises(ValueError, match="qualifying_children must be a non-negative integer"):
        BUILD_FORM_1040.build_summary(
            _sample_w2_fields() | {"source_document_filename": "w2.pdf"},
            {
                "filing_status": "single",
                "qualifying_children": qualifying_children,
            },
        )


def test_build_summary_accepts_integer_like_string_qualifying_children() -> None:
    summary = BUILD_FORM_1040.build_summary(
        _sample_w2_fields() | {"source_document_filename": "w2.pdf"},
        {
            "filing_status": "single",
            "qualifying_children": "2",
        },
    )

    assert summary["form1040"]["tax"]["nonrefundableCredits"] == pytest.approx(4_000.0)
    assert len(summary["form1040"]["dependents"]) == 2


def test_build_summary_synthesizes_dependents_for_claimed_child_credit() -> None:
    summary = BUILD_FORM_1040.build_summary(
        _sample_w2_fields() | {"source_document_filename": "w2.pdf"},
        {
            "filing_status": "single",
            "qualifying_children": 2,
        },
    )

    assert summary["form1040"]["dependents"] == [
        {
            "name": "Qualifying child 1",
            "ssn": "",
            "relationship": "Child",
            "qualifiesForChildTaxCredit": True,
            "qualifiesForOtherDependentCredit": False,
        },
        {
            "name": "Qualifying child 2",
            "ssn": "",
            "relationship": "Child",
            "qualifiesForChildTaxCredit": True,
            "qualifiesForOtherDependentCredit": False,
        },
    ]


def test_build_summary_rejects_mismatched_explicit_dependents() -> None:
    with pytest.raises(
        ValueError,
        match="dependents qualifying for child tax credit must match qualifying_children",
    ):
        BUILD_FORM_1040.build_summary(
            _sample_w2_fields() | {"source_document_filename": "w2.pdf"},
            {
                "filing_status": "single",
                "qualifying_children": 2,
                "dependents": [
                    {
                        "name": "Child One",
                        "ssn": "",
                        "relationship": "Child",
                        "qualifiesForChildTaxCredit": True,
                        "qualifiesForOtherDependentCredit": False,
                    }
                ],
            },
        )


def test_build_summary_merges_agent_adjustments_into_tax_totals() -> None:
    summary = BUILD_FORM_1040.build_summary(
        _sample_w2_fields() | {"source_document_filename": "w2.pdf"},
        {
            "filing_status": "single",
            "qualifying_children": 0,
            "other_income": {"taxable_interest": 10.0},
            "additional_payments": {"estimated_tax_payments": 5.0},
        },
        agent_tax_adjustments=_sample_agent_adjustments(),
        detected_supplemental_documents=[
            {
                "filename": "supplemental-1099-int.pdf",
                "type": "1099-int",
                "mappedAmounts": {"other_income": {}, "additional_payments": {}},
                "notes": ["Detected a non-W-2 document."],
            }
        ],
    )

    assert summary["form1040"]["income"]["taxableInterest"] == pytest.approx(135.0)
    assert summary["form1040"]["income"]["qualifiedDividends"] == pytest.approx(25.0)
    assert summary["form1040"]["payments"]["estimatedTaxPayments"] == pytest.approx(105.0)
    assert summary["form1040"]["payments"]["refundableCredits"] == pytest.approx(50.0)
    assert summary["summary"]["agi"] == pytest.approx(50_160.0)
    assert summary["summary"]["totalWithholdings"] == pytest.approx(5_155.0)
    assert summary["documentsProcessed"][1]["filename"] == "supplemental-1099-int.pdf"
    assert summary["documentsProcessed"][1]["type"] == "1099-int"
    assert summary["documentsProcessed"][1]["mappedAmounts"]["otherIncome"] == {
        "qualified_dividends": 25.0,
        "taxable_interest": 125.0,
    }


def test_write_summary_artifacts_creates_audit_json(tmp_path: Path) -> None:
    summary = BUILD_FORM_1040.build_summary(
        _sample_w2_fields() | {"source_document_filename": "w2.pdf"},
        {"filing_status": "single", "qualifying_children": 0},
    )
    output_path = tmp_path / "output" / "tax_return_summary.json"

    BUILD_FORM_1040.write_summary_artifacts(
        summary,
        output_path=output_path,
    )

    form_data_path = output_path.parent / BUILD_FORM_1040.FORM_DATA_OUTPUT_FILENAME
    assert form_data_path.exists()

    payload = json.loads(form_data_path.read_text(encoding="utf-8"))
    assert payload["form"] == "1040"
    assert payload["taxYear"] == 2024
    assert payload["filingStatus"] == "single"
    assert payload["taxpayer"]["firstName"] == "Jane"
    assert payload["taxpayer"]["lastName"] == "Doe"
    assert payload["lineItems"]["1a"] == pytest.approx(50_000.0)
    assert payload["lineItems"]["24"] == pytest.approx(4_016.0)
    assert payload["lineItems"]["33"] == pytest.approx(5_000.0)
    assert payload["lineItems"]["34"] == pytest.approx(984.0)


def test_refresh_tax_return_main_merges_detected_supplemental_docs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()
    (documents_dir / "w2.pdf").write_bytes(b"%PDF-1.4\n")
    config_path = tmp_path / "task_config.json"
    config_path.write_text(
        json.dumps({"filing_status": "single", "qualifying_children": 0}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "agent_tax_adjustments.json").write_text(
        json.dumps(_sample_agent_adjustments()) + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "output" / "tax_return_summary.json"

    monkeypatch.setattr(
        REFRESH_TAX_RETURN,
        "_parse_staged_documents",
        lambda _documents_dir: (
            [_sample_w2_fields() | {"source_document_filename": "w2.pdf"}],
            [
                {
                    "filename": "supplemental-1099-int.pdf",
                    "type": "1099-int",
                    "mappedAmounts": {"other_income": {}, "additional_payments": {}},
                    "notes": ["Detected supplemental document."],
                }
            ],
        ),
    )

    result = REFRESH_TAX_RETURN.main(
        [
            "refresh_tax_return.py",
            str(documents_dir),
            str(config_path),
            str(output_path),
        ]
    )

    assert result == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["documentsProcessed"][1]["type"] == "1099-int"
    assert payload["summary"]["agi"] == pytest.approx(50_150.0)
    assert payload["summary"]["totalWithholdings"] == pytest.approx(5_150.0)
    assert (output_path.parent / BUILD_FORM_1040.FORM_DATA_OUTPUT_FILENAME).exists()


def test_detect_document_type_recognizes_w2_wage_and_tax_statement() -> None:
    assert (
        REFRESH_TAX_RETURN._detect_document_type(
            "W-2 Wage and Tax Statement",
            Path("uploaded.pdf"),
        )
        == "w2"
    )


def test_detect_document_type_uses_w2_filename_fallback() -> None:
    assert (
        REFRESH_TAX_RETURN._detect_document_type(
            "scanned document with unclear extracted text",
            Path("sample_w2.pdf"),
        )
        == "w2"
    )


def test_detect_document_type_keeps_1099_detection() -> None:
    assert (
        REFRESH_TAX_RETURN._detect_document_type(
            "Form 1099-INT Interest Income",
            Path("uploaded.pdf"),
        )
        == "1099-int"
    )


def test_detect_document_type_defaults_to_other_tax_document() -> None:
    assert (
        REFRESH_TAX_RETURN._detect_document_type(
            "general supplemental tax paperwork",
            Path("uploaded.pdf"),
        )
        == "other_tax_document"
    )


def test_parse_staged_documents_accepts_w2_like_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()
    (documents_dir / "sample_w2.pdf").write_bytes(b"%PDF-1.4\n")

    def _write_w2_text(_pdf_path: Path, text_path: Path) -> str:
        text = "W-2 Wage and Tax Statement"
        text_path.write_text(text, encoding="utf-8")
        return text

    monkeypatch.setattr(REFRESH_TAX_RETURN, "_extract_pdf_text", _write_w2_text)
    monkeypatch.setattr(
        REFRESH_TAX_RETURN,
        "parse",
        lambda _text_path: _sample_w2_fields(),
    )

    parsed_w2s, supplemental_documents = REFRESH_TAX_RETURN._parse_staged_documents(documents_dir)

    assert len(parsed_w2s) == 1
    assert parsed_w2s[0]["source_document_filename"] == "sample_w2.pdf"
    assert supplemental_documents == []


def test_parse_staged_documents_surfaces_w2_parse_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()
    (documents_dir / "sample_w2.pdf").write_bytes(b"%PDF-1.4\n")

    def _write_w2_text(_pdf_path: Path, text_path: Path) -> str:
        text = "W-2 Wage and Tax Statement"
        text_path.write_text(text, encoding="utf-8")
        return text

    monkeypatch.setattr(REFRESH_TAX_RETURN, "_extract_pdf_text", _write_w2_text)

    def _raise_parse_error(_text_path: str) -> dict[str, object]:
        raise ValueError("could not parse wages")

    monkeypatch.setattr(REFRESH_TAX_RETURN, "parse", _raise_parse_error)

    with pytest.raises(
        ValueError, match=r"failed to parse W-2 PDF sample_w2\.pdf: could not parse wages"
    ):
        REFRESH_TAX_RETURN._parse_staged_documents(documents_dir)


def test_single_tax_brackets_match_2024_schedule_x_thresholds() -> None:
    tax, steps = BUILD_FORM_1040._tax_computation(300000.0, "single")

    assert tax == pytest.approx(75_374.75)
    assert steps[3]["bracket"] == "100,525.00-191,950.00"
    assert steps[4]["bracket"] == "191,950.00-243,725.00"
    assert steps[5]["bracket"] == "243,725.00-609,350.00"


def test_head_of_household_tax_brackets_match_2024_thresholds() -> None:
    tax, steps = BUILD_FORM_1040._tax_computation(300000.0, "head_of_household")

    assert tax == pytest.approx(73_682.0)
    assert steps[3]["bracket"] == "100,500.00-191,950.00"
    assert steps[4]["bracket"] == "191,950.00-243,700.00"
    assert steps[5]["bracket"] == "243,700.00-609,350.00"


def test_married_filing_separately_brackets_match_2024_thresholds() -> None:
    tax, steps = BUILD_FORM_1040._tax_computation(400000.0, "married_filing_separately")

    assert tax == pytest.approx(111_062.75)
    assert steps[5]["bracket"] == "243,725.00-365,600.00"
    assert steps[6]["bracket"] == "365,600.00-and up"
