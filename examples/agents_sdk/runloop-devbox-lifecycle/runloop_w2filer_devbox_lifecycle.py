"""
Runloop devbox lifecycle example: staged tax-document Form 1040 prep with suspend/resume.

This script demonstrates the full Runloop devbox lifecycle using the OpenAI Agents SDK,
with staged tax PDFs processed inside the sandbox and a filing-status-driven Form 1040
JSON package refreshed in place as new documents arrive. The example uses mounted helper
scripts to keep the W-2 extraction and tax math deterministic inside the devbox while
leaving the surrounding agent narration and review steps intentionally flexible:
`parse_w2.py` for W-2 parsing, `build_form1040.py` for the 2024 Form 1040 JSON, and
`refresh_tax_return.py` for rebuilding the work-in-progress filing from every staged tax PDF.

    1. Create a Runloop devbox and mount helper scripts plus task config via the
       sandbox file API.
    2. Upload an initial W-2 PDF into a persistent workspace directory and run a
       SandboxAgent that installs poppler-utils and creates an initial filing package.
    3. Suspend the devbox (pause_on_exit=True) between additional W-2 uploads so the
       filesystem survives across turns.
    4. Enable a Runloop tunnel with wake_on_http=True, send an HTTP request to resume
       the suspended devbox, upload the next W-2, and refresh the work-in-progress filing.
    5. Repeat the suspend/resume/upload/update loop until there are no more W-2s.
    6. Hand the same devbox to a verifier agent that confirms the final filing package
       survived the staged lifecycle and appends a filing-ready checklist.
    7. Take a disk snapshot of the final workspace for observability and audit.

Required environment variables:
    - OPENAI_API_KEY
    - RUNLOOP_API_KEY

Runloop AI TaxMan Demo Repository: https://github.com/runloopai/codex-tax-man

Example usage:
    python examples/agents_sdk/runloop-devbox-lifecycle/runloop_w2filer_devbox_lifecycle.py
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import Any

from openai.types.shared.reasoning import Reasoning

from agents import MaxTurnsExceeded, ModelSettings, Runner
from agents.run import RunConfig
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
from agents.sandbox.capabilities import Shell
from agents.sandbox.entries import Dir, File, LocalFile
from agents.sandbox.session import SandboxSession

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    from agents.extensions.sandbox import (
        RunloopSandboxClient,
        RunloopSandboxClientOptions,
        RunloopSandboxSessionState,
        RunloopTimeouts,
        RunloopUserParameters,
    )
except ImportError as exc:
    raise SystemExit(
        "Runloop sandbox examples require the Runloop Agents SDK extra.\n"
        "Install this cookbook's dependencies with: "
        "pip install -r examples/agents_sdk/runloop-devbox-lifecycle/requirements.txt"
    ) from exc

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "gpt-5.4"
WORKSPACE_ROOT = Path("/root/project")
W2_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_W2_PATH = W2_DATA_DIR / "sample_w2.pdf"
DOCUMENT_STAGING_DIR = WORKSPACE_ROOT / "taxpayer_data" / "documents"
W2_STAGING_DIR = WORKSPACE_ROOT / "taxpayer_data" / "w2s"
AGENT_TAX_ADJUSTMENTS_PATH = WORKSPACE_ROOT / "taxpayer_data" / "agent_tax_adjustments.json"
TAX_SUMMARY_PATH = WORKSPACE_ROOT / "output" / "tax_return_summary.json"
CHECKLIST_PATH = WORKSPACE_ROOT / "output" / "filing_checklist.md"
FORM_DATA_OUTPUT_PATH = WORKSPACE_ROOT / "output" / "f1040_form_data.json"
DEVBOX_NAME_PREFIX = "agents-sdk-tax-pdf-lifecycle"
TUNNEL_WAKE_PORT = 8080
DEFAULT_DOWNLOADS_DIRNAME = "runloop-devbox-lifecycle-downloads"
FINAL_REVIEW_TIMEOUT_S = 120.0
RECORDING_PAUSE_BEFORE_CLEAR_S = 5.0
RECORDING_PAUSE_AFTER_CLEAR_S = 2.0
AGENT_REASONING_SETTINGS = ModelSettings(reasoning=Reasoning(effort="medium", summary="detailed"))
# A turn is one model invocation, including any tool calls made within that invocation.
TAX_PREP_AGENT_MAX_TURNS = 30
VERIFY_AGENT_MAX_TURNS = 10
SUMMARY_AGENT_MAX_TURNS = 10

# ---------------------------------------------------------------------------
# Tax agent instructions
# ---------------------------------------------------------------------------

TAX_AGENT_INSTRUCTIONS = dedent("""\
    You are a federal tax preparation agent for tax year 2024. You have access to a
    shell. Use only the files mounted in this workspace:

      - `taxpayer_data/documents/*.pdf`
      - `taxpayer_data/w2s/*.pdf`
      - `taxpayer_data/build_form1040.py`
      - `taxpayer_data/parse_w2.py`
      - `taxpayer_data/refresh_tax_return.py`
      - `taxpayer_data/task_config.json`
      - `taxpayer_data/agent_tax_adjustments.json`
    The helper scripts are authoritative. Do not reimplement their logic in ad hoc
    shell snippets. If any refresh step fails, stop immediately and report the
    command failure.

    This demo stages one or more tax PDFs over time. W-2 inputs stay on the
    deterministic path. Non-W-2 tax forms may be inspected non-deterministically,
    but any structured values you map must be written into
    `taxpayer_data/agent_tax_adjustments.json` before the refresh command runs.

    `taxpayer_data/agent_tax_adjustments.json` must stay cumulative across all staged
    non-W-2 documents and use this shape:
      {
        "other_income": {
          "taxable_interest": 0.0,
          "qualified_dividends": 0.0,
          "ira_distributions": 0.0,
          "pensions_annuities": 0.0,
          "social_security_benefits": 0.0,
          "capital_gain_loss": 0.0,
          "schedule_d": 0.0,
          "additional_income_schedule_1": 0.0
        },
        "additional_payments": {
          "estimated_tax_payments": 0.0,
          "earned_income_credit": 0.0,
          "additional_child_tax_credit": 0.0,
          "american_opportunity_credit": 0.0,
          "refundable_credits": 0.0
        },
        "documents": [
          {
            "filename": "sample_1099.pdf",
            "type": "1099-int",
            "mappedAmounts": {
              "other_income": {"taxable_interest": 125.0},
              "additional_payments": {}
            },
            "notes": ["Mapped 1099 interest into taxable_interest."]
          }
        ]
      }

    ## Required workflow

    If every staged document is a W-2, use exactly 2 shell commands total:
    1. ensure `pdftotext` is available and install `poppler-utils` only if it is missing
    2. run:
       `python3 taxpayer_data/refresh_tax_return.py taxpayer_data/documents taxpayer_data/task_config.json output/tax_return_summary.json`

    If any staged document is not a W-2, you may use more commands. In that case:
    1. ensure `pdftotext` is available
    2. inspect every non-W-2 tax document as needed
    3. rewrite `taxpayer_data/agent_tax_adjustments.json` with cumulative totals and
       per-document provenance
    4. run the same refresh command

    Unsupported tax forms should not halt the workflow. If you cannot map a document
    cleanly, preserve a note for it in `agent_tax_adjustments.json` and continue.

    ## Recovery workflow

    The Shell capability is backed by command execution inside this devbox. If
    `python3 taxpayer_data/refresh_tax_return.py ...` fails, you may use shell/exec
    commands inside the devbox to diagnose and recover before rerunning the refresh.
    Allowed recovery actions:
    1. inspect staged files under `taxpayer_data/documents/`
    2. verify `pdftotext` availability and install `poppler-utils` if missing
    3. inspect extracted text or JSON inputs with `python3` or shell commands
    4. repair `taxpayer_data/agent_tax_adjustments.json` if needed
    5. rerun `refresh_tax_return.py`

    Keep the deterministic helper scripts authoritative. Do not reimplement tax
    logic in ad hoc shell snippets.

    ## Final response format

    Respond with a concise natural-language status update. State how many staged tax
    documents were processed, confirm that the filing was refreshed, and report AGI plus
    refund or amount owed.
""")

VERIFY_AGENT_INSTRUCTIONS = dedent("""\
    You are a tax filing review agent. A prior agent prepared a Form 1040-style JSON
    package at `output/tax_return_summary.json` plus an audit export at
    `output/f1040_form_data.json` inside a Runloop devbox that was updated across
    multiple W-2 intake turns, suspended, and resumed. Your job is to verify the
    final data survived and prepare the filing checklist.

    ## Important: minimize shell commands

    Complete this entire task in a single python3 script.

    The script should:
      - Read and parse `output/tax_return_summary.json`
      - Read and parse `output/f1040_form_data.json`
      - Validate the top-level keys: `success`, `documentsProcessed`, `form1040`, `summary`
      - Validate the audit export top-level keys:
        `form`, `taxYear`, `taxpayer`, `filingStatus`, `lineItems`, `summary`
      - Validate the nested Form 1040 sections:
        `taxpayer`, `filingStatus`, `dependents`, `income`, `deductions`, `taxableIncome`,
        `tax`, `payments`, `refundOrOwed`
      - Extract the SSN last 4 digits from `form1040.taxpayer.ssn`
      - Determine whether the filing result is a refund or a balance due
      - Write output/filing_checklist.md with:
        * Taxpayer name and last four of SSN
        * Filing status
        * AGI and taxable income
        * Federal tax and refund or amount owed
        * Processed document list
        * Checkboxes: [ ] Supporting tax forms attached, [ ] Review Form 1040 data, [ ] Signature, [ ] Date, [ ] E-file ready
      - Print a one-line confirmation

    Do NOT run multiple commands. Do NOT cat files to stdout.

    ## Response format

    After the script runs, respond with a concise natural-language summary. Confirm
    which sections survived suspend/resume, whether the JSON is intact, and the key
    dollar values you found.
""")

SUMMARY_AGENT_INSTRUCTIONS = dedent("""\
    You are a demo summary agent. You are running inside a Runloop devbox that has
    been through a full lifecycle: creation, staged tax-document intake, AI-driven filing
    refreshes, suspension, wake-on-HTTP resumes, persistence verification, and an
    audit snapshot.

    ## Important: minimize shell commands

    Use a single python3 command to inspect the final filing artifacts.

    ## Task

    In one python3 script, do all of the following:
      - Read and parse `output/tax_return_summary.json`
      - Confirm that `output/filing_checklist.md` and `output/f1040_form_data.json` exist
      - Extract:
        * processed document count
        * AGI
        * taxable income
        * federal tax
        * refund or amount owed
      - Print a one-line machine-readable summary containing those values

    Then produce a concluding summary of the demo. Your summary should:
      - Confirm that staged tax document uploads updated the same filing over multiple turns
      - Confirm that 2 agents did work on this devbox (tax prep + filing review)
      - List the artifacts produced (`tax_return_summary.json`, `filing_checklist.md`,
        `f1040_form_data.json`)
      - Include the actual AGI, taxable income, federal tax, and refund or amount owed
      - Note that filing-status-driven tax calculations, suspend/resume persistence,
        and snapshot capture were all tested end to end
      - Briefly state that this pattern applies to any stateful workload:
        tax prep, databases, dev servers, long-running pipelines -- suspend when idle,
        wake on demand, pick up where you left off

    ## Response format

    Respond with a natural, conversational wrap-up. Keep it concise -- 4-6 sentences.
    This is the final output the viewer sees.
""")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env(name: str) -> None:
    if not os.environ.get(name):
        raise SystemExit(f"{name} must be set before running this example.")


def _header(title: str) -> None:
    print(f"\n{'=' * 64}")
    print(f"  {title}")
    print(f"{'=' * 64}\n")


def _clear_screen() -> None:
    print("\033[2J\033[H", end="", flush=True)


async def _pause_and_clear_before_next_turn() -> None:
    await asyncio.sleep(RECORDING_PAUSE_BEFORE_CLEAR_S)
    _clear_screen()
    await asyncio.sleep(RECORDING_PAUSE_AFTER_CLEAR_S)


def _devbox_name() -> str:
    return f"{DEVBOX_NAME_PREFIX}-{uuid.uuid4().hex[:8]}"


def _default_download_dir(devbox_name: str) -> Path:
    return Path.cwd() / DEFAULT_DOWNLOADS_DIRNAME / devbox_name


def _validate_w2_path(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.suffix.lower() != ".pdf":
        raise SystemExit(f"W-2 path must point to a PDF file: {expanded}")
    if not expanded.is_file():
        raise SystemExit(f"W-2 file not found: {expanded}")
    return expanded.resolve()


def _resolve_w2_path(
    *,
    cli_w2_path: str | None,
    stdin_isatty: bool,
    input_func: Callable[[str], str] = input,
    default_w2_path: Path = DEFAULT_W2_PATH,
) -> Path:
    if cli_w2_path:
        return _validate_w2_path(Path(cli_w2_path))

    if not stdin_isatty:
        print("Non-interactive run detected. Using the bundled sample W-2 PDF.")
        return _validate_w2_path(default_w2_path)

    prompt = f"Enter a local path to the initial document PDF [{default_w2_path}]: "
    try:
        response = input_func(prompt).strip()
    except EOFError:
        response = ""

    if not response:
        return _validate_w2_path(default_w2_path)
    return _validate_w2_path(Path(response))


def _resolve_additional_w2_paths(cli_w2_paths: list[str] | None) -> list[Path]:
    return [_validate_w2_path(Path(path)) for path in (cli_w2_paths or [])]


def _prompt_for_additional_w2(
    *,
    stdin_isatty: bool,
    input_func: Callable[[str], str] = input,
) -> Path | None:
    if not stdin_isatty:
        return None

    try:
        wants_more = input_func("Add another supporting document PDF? [y/N]: ").strip()
    except EOFError:
        return None

    if not _is_affirmative(wants_more):
        return None

    while True:
        try:
            response = input_func("Enter a local path to the additional document PDF: ").strip()
        except EOFError:
            return None

        if not response:
            print("No path entered. Skipping the additional document upload.")
            return None

        try:
            return _validate_w2_path(Path(response))
        except SystemExit as exc:
            print(exc)


def _next_follow_up_w2_path(
    *,
    pending_paths: list[Path],
    stdin_isatty: bool,
    input_func: Callable[[str], str] = input,
) -> Path | None:
    if pending_paths:
        return pending_paths.pop(0)
    return _prompt_for_additional_w2(stdin_isatty=stdin_isatty, input_func=input_func)


def _task_config(
    *,
    filing_status: str,
    qualifying_children: int,
    source_document_filenames: list[str] | None = None,
    source_document_filename: str | None = None,
) -> bytes:
    payload = {
        "filing_status": filing_status,
        "qualifying_children": qualifying_children,
        "other_income": {
            "taxable_interest": 0.0,
            "qualified_dividends": 0.0,
            "ira_distributions": 0.0,
            "pensions_annuities": 0.0,
            "social_security_benefits": 0.0,
            "capital_gain_loss": 0.0,
            "schedule_d": 0.0,
            "additional_income_schedule_1": 0.0,
        },
        "additional_payments": {
            "estimated_tax_payments": 0.0,
            "earned_income_credit": 0.0,
            "additional_child_tax_credit": 0.0,
            "american_opportunity_credit": 0.0,
            "refundable_credits": 0.0,
        },
        "dependents": [],
    }
    if source_document_filenames:
        payload["source_document_filenames"] = source_document_filenames
    if source_document_filename is not None:
        payload["source_document_filename"] = source_document_filename
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _build_manifest(*, filing_status: str, qualifying_children: int) -> Manifest:
    return Manifest(
        root=str(WORKSPACE_ROOT),
        entries={
            "taxpayer_data": Dir(
                children={
                    "parse_w2.py": LocalFile(src=W2_DATA_DIR / "parse_w2.py"),
                    "build_form1040.py": LocalFile(src=W2_DATA_DIR / "build_form1040.py"),
                    "refresh_tax_return.py": LocalFile(src=W2_DATA_DIR / "refresh_tax_return.py"),
                    "task_config.json": File(
                        content=_task_config(
                            filing_status=filing_status,
                            qualifying_children=qualifying_children,
                        )
                    ),
                    "agent_tax_adjustments.json": File(
                        content=(
                            json.dumps(
                                {
                                    "other_income": {},
                                    "additional_payments": {},
                                    "documents": [],
                                },
                                indent=2,
                                sort_keys=True,
                            )
                            + "\n"
                        ).encode("utf-8")
                    ),
                    "documents": Dir(
                        description="All staged tax PDFs uploaded across multiple turns."
                    ),
                    "w2s": Dir(
                        description="Internal W-2 subset rebuilt by refresh_tax_return.py for deterministic math."
                    ),
                },
                description="Taxpayer tax inputs, deterministic tax helpers, and task config.",
            ),
            "output": Dir(description="Generated filing artifacts."),
        },
    )


async def _run_agent(
    agent: SandboxAgent,
    prompt: str,
    session: SandboxSession,
    *,
    workflow_name: str,
    max_turns: int = TAX_PREP_AGENT_MAX_TURNS,
) -> str:
    stream = Runner.run_streamed(
        agent,
        prompt,
        max_turns=max_turns,
        run_config=RunConfig(
            sandbox=SandboxRunConfig(session=session),
            tracing_disabled=True,
            workflow_name=workflow_name,
        ),
    )
    active_section: str | None = None
    saw_streamed_output = False

    def _end_active_section() -> None:
        nonlocal active_section
        if active_section is not None:
            print()
            active_section = None

    async for event in stream.stream_events():
        if event.type == "raw_response_event":
            raw_event = event.data
            if raw_event.type == "response.reasoning_summary_text.delta":
                if active_section != "thinking":
                    _end_active_section()
                    print("Thinking: ", end="", flush=True)
                    active_section = "thinking"
                print(raw_event.delta, end="", flush=True)
            elif raw_event.type == "response.output_text.delta":
                if active_section != "response":
                    _end_active_section()
                    print("Response: ", end="", flush=True)
                    active_section = "response"
                print(raw_event.delta, end="", flush=True)
                saw_streamed_output = True
        elif event.type == "run_item_stream_event" and event.name == "tool_called":
            raw_item = event.item.raw_item
            item_type = (
                raw_item.get("type")
                if isinstance(raw_item, dict)
                else getattr(raw_item, "type", None)
            )
            if item_type not in {"local_shell_call", "shell_call"}:
                continue

            action = (
                raw_item.get("action")
                if isinstance(raw_item, dict)
                else getattr(raw_item, "action", None)
            )
            command = (
                action.get("command")
                if isinstance(action, dict)
                else getattr(action, "command", None)
            )
            if isinstance(command, list):
                command_text = " ".join(command)
            elif command is None:
                command_text = "<unknown shell command>"
            else:
                command_text = str(command)

            _end_active_section()
            print(f"Shell: {command_text}")

    _end_active_section()
    final_output = str(stream.final_output).strip()
    if final_output and not saw_streamed_output:
        print(final_output)
    return final_output


async def _read_remote_mtime_ns(session: SandboxSession, path: Path) -> int | None:
    result = await session.exec(
        "python3",
        "-c",
        (
            "import os\n"
            "import sys\n"
            "try:\n"
            "    print(os.stat(sys.argv[1]).st_mtime_ns)\n"
            "except FileNotFoundError:\n"
            "    sys.exit(2)\n"
        ),
        str(path),
        shell=False,
    )
    if result.exit_code == 2:
        return None
    if not result.ok():
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"could not stat {path}: {stderr or f'exit code {result.exit_code}'}")

    raw_mtime = result.stdout.decode("utf-8", errors="replace").strip()
    try:
        return int(raw_mtime)
    except ValueError as exc:
        raise RuntimeError(f"could not parse mtime for {path}: {raw_mtime!r}") from exc


async def _validate_tax_summary_output(
    session: SandboxSession,
    *,
    summary_mtime_ns: int | None = None,
    previous_summary_mtime_ns: int | None = None,
) -> dict[str, object]:
    try:
        handle = await session.read(TAX_SUMMARY_PATH)
    except Exception as exc:
        raise RuntimeError(f"{TAX_SUMMARY_PATH} was not created: {exc}") from exc

    try:
        raw_payload = handle.read()
    finally:
        handle.close()

    if isinstance(raw_payload, bytes):
        raw_text = raw_payload.decode("utf-8", errors="replace")
    else:
        raw_text = str(raw_payload)

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{TAX_SUMMARY_PATH} is not valid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"{TAX_SUMMARY_PATH} must contain a top-level JSON object")

    required_keys = {"success", "documentsProcessed", "form1040", "summary"}
    missing_keys = sorted(required_keys - payload.keys())
    if missing_keys:
        raise RuntimeError(f"{TAX_SUMMARY_PATH} is missing keys: {', '.join(missing_keys)}")

    effective_summary_mtime_ns = summary_mtime_ns
    if effective_summary_mtime_ns is None:
        effective_summary_mtime_ns = await _read_remote_mtime_ns(session, TAX_SUMMARY_PATH)

    if (
        previous_summary_mtime_ns is not None
        and effective_summary_mtime_ns is not None
        and effective_summary_mtime_ns <= previous_summary_mtime_ns
    ):
        raise RuntimeError(
            f"{TAX_SUMMARY_PATH} was not refreshed for the current prep round; "
            "it still has the same modification time as the previous summary"
        )

    return payload


def _tax_prep_recovery_prompt(base_prompt: str, failure_reason: str) -> str:
    return dedent(
        f"""\
        {base_prompt}

        The previous attempt did not produce a valid filing package: {failure_reason}
        Use shell/exec commands inside this devbox to diagnose the problem, repair any
        staging or adjustment issue, rerun
        `python3 taxpayer_data/refresh_tax_return.py taxpayer_data/documents taxpayer_data/task_config.json output/tax_return_summary.json`,
        and do not finish until `output/tax_return_summary.json` exists and parses as
        valid JSON with the top-level keys `success`, `documentsProcessed`, `form1040`,
        and `summary`.
        """
    )


async def _run_tax_prep_round(
    agent: SandboxAgent,
    prompt: str,
    session: SandboxSession,
    *,
    round_label: str,
    workflow_name: str,
    max_turns: int = TAX_PREP_AGENT_MAX_TURNS,
) -> str:
    last_failure_reason = "agent did not complete successfully"
    last_exception: Exception | None = None
    previous_summary_mtime_ns = await _read_remote_mtime_ns(session, TAX_SUMMARY_PATH)

    for attempt in range(2):
        attempt_prompt = (
            prompt if attempt == 0 else _tax_prep_recovery_prompt(prompt, last_failure_reason)
        )
        attempt_workflow_name = workflow_name if attempt == 0 else f"{workflow_name} recovery"

        try:
            final_output = await _run_agent(
                agent,
                attempt_prompt,
                session,
                workflow_name=attempt_workflow_name,
                max_turns=max_turns,
            )
            if not final_output:
                raise RuntimeError("agent returned no final response")
            await _validate_tax_summary_output(
                session,
                previous_summary_mtime_ns=previous_summary_mtime_ns,
            )
            return final_output
        except MaxTurnsExceeded as exc:
            last_exception = exc
            last_failure_reason = f"agent exceeded max turns ({max_turns})"
        except Exception as exc:
            last_exception = exc
            last_failure_reason = str(exc)

        if attempt == 0:
            print(
                "Tax prep did not produce a valid filing package "
                f"({last_failure_reason}). Retrying with explicit shell/exec recovery guidance.\n"
            )

    raise RuntimeError(
        f"{round_label} failed after 2 attempts: {last_failure_reason}"
    ) from last_exception


def _allocate_uploaded_w2_name(local_path: Path, uploaded_names: set[str]) -> str:
    candidate = local_path.name
    stem = local_path.stem
    suffix = local_path.suffix
    counter = 2

    while candidate in uploaded_names:
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1

    uploaded_names.add(candidate)
    return candidate


async def _upload_w2(
    session: SandboxSession,
    *,
    local_path: Path,
    uploaded_names: set[str],
) -> str:
    remote_name = _allocate_uploaded_w2_name(local_path, uploaded_names)
    remote_path = DOCUMENT_STAGING_DIR / remote_name

    with local_path.open("rb") as handle:
        await session.write(remote_path, io.BytesIO(handle.read()))

    return remote_name


async def _enable_wake_on_http(session: SandboxSession) -> str | None:
    """Enable a Runloop tunnel with wake_on_http on the underlying devbox.

    Returns the tunnel_key for URL construction, or None if not available.
    """
    inner = getattr(session, "_inner", None)
    devbox = getattr(inner, "_devbox", None)
    if devbox is None:
        print("  warning: could not access underlying devbox for tunnel config")
        return None
    try:
        tunnel = await devbox.net.enable_tunnel(
            auth_mode="open",
            http_keep_alive=True,
            wake_on_http=True,
        )
        tunnel_key = getattr(tunnel, "tunnel_key", None)
        if tunnel_key:
            print("  tunnel enabled with wake_on_http=True")
            print(f"  tunnel URL pattern: https://{{port}}-{tunnel_key}.tunnel.runloop.ai")
            return str(tunnel_key)
        print("  tunnel enabled but no tunnel_key returned")
        return None
    except Exception as exc:
        print(f"  warning: could not enable tunnel: {exc}")
        return None


async def _wait_for_devbox_status(
    devbox: Any,
    *,
    target_status: str,
    max_attempts: int = 60,
    poll_interval_s: float = 2.0,
) -> bool:
    """Poll the Runloop backend status until the target state is reached."""
    last_status: str | None = None
    for attempt in range(max_attempts):
        try:
            info = await devbox.get_info(timeout=10)
            status = getattr(info, "status", None)
        except Exception as exc:
            if attempt == 0 or (attempt + 1) % 5 == 0:
                print(f"  status check failed (attempt {attempt + 1}/{max_attempts}): {exc}")
        else:
            if isinstance(status, str) and status != last_status:
                print(f"  backend status -> {status} (attempt {attempt + 1}/{max_attempts})")
                last_status = status
            if status == target_status:
                print(f"  devbox reached `{target_status}`")
                return True
        await asyncio.sleep(poll_interval_s)

    print(f"  warning: devbox did not reach `{target_status}` within timeout")
    return False


async def _suspend_for_additional_document_wait(
    session: SandboxSession,
    client: RunloopSandboxClient,
) -> tuple[dict[str, object], str | None]:
    """Suspend the current devbox before asking for the next additional document."""
    tunnel_key = await _enable_wake_on_http(session)
    if not isinstance(session.state, RunloopSandboxSessionState):
        raise TypeError("Runloop example expected a RunloopSandboxSessionState")

    devbox_id = str(session.state.devbox_id)
    poll_devbox = client._sdk.devbox.from_id(devbox_id)

    if tunnel_key:
        print(
            "Wake-on-HTTP is enabled. Once the devbox is suspended, the next selected "
            "tax file can wake this same box through the tunnel URL.\n"
        )
    else:
        print("Wake-on-HTTP is unavailable for this turn. Resume will fall back to the SDK.\n")

    print("Serializing session state so we can reconnect after resume...")
    serialized = client.serialize_session_state(session.state)
    print(f"  session state captured ({len(serialized)} keys)")

    print("\nClosing the session. Because pause_on_exit=True, Runloop snapshots")
    print("the VM disk and suspends instead of destroying it.\n")
    await session.aclose()
    print("Waiting for Runloop to finish suspending the devbox...")
    await _wait_for_devbox_status(poll_devbox, target_status="suspended")
    return serialized, tunnel_key


async def _wake_via_http(tunnel_key: str, port: int = TUNNEL_WAKE_PORT) -> bool:
    """Send an HTTP request to the tunnel URL to trigger wake-on-http resume."""
    url = f"https://{port}-{tunnel_key}.tunnel.runloop.ai/"
    print(f"  sending wake request to {url}")
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "runloop-lifecycle-example/1.0")
        with urllib.request.urlopen(req, timeout=120) as resp:
            print(f"  wake response: {resp.status}")
            return True
    except urllib.error.HTTPError as exc:
        print(f"  wake response: HTTP {exc.code} (devbox resuming)")
        return True
    except urllib.error.URLError as exc:
        print(f"  wake request failed: {exc.reason}")
        return False
    except Exception as exc:
        print(f"  wake request failed: {exc}")
        return False


async def _resume_after_additional_document_wait(
    client: RunloopSandboxClient,
    *,
    serialized: dict[str, object],
    tunnel_key: str | None,
    next_w2_path: Path | None,
    round_number: int | None = None,
) -> SandboxSession:
    """Resume a suspended devbox after the additional-document wait."""
    devbox_id_for_resume = str(serialized["devbox_id"])
    poll_devbox = client._sdk.devbox.from_id(devbox_id_for_resume)

    if next_w2_path is None:
        _header("Resume for Final Verification")
        print("No additional documents were selected while the devbox was suspended.")
        print("Resuming the same devbox now so the final verification turn can continue.\n")
    else:
        _header(f"Wake, Resume, and Upload Document #{round_number}")
        if tunnel_key:
            print(f"Selected tax file is ready: {next_w2_path.name}")
            print("The devbox is suspended. Sending an HTTP request to the tunnel")
            print("URL now so Runloop resumes the same box before the upload begins.\n")
            woke = await _wake_via_http(tunnel_key)
            if woke:
                print("\nRunloop received the HTTP request and is waking the devbox.")
                print("A 503 response is expected -- it means the tunnel recognized")
                print("the request and initiated the resume process.")
            else:
                print("\nNo response from tunnel; will fall back to SDK resume.")

            print("\nWaiting for the HTTP-triggered resume to move through")
            print("the backend states until the devbox is running again...")
            await _wait_for_devbox_status(poll_devbox, target_status="running")
        else:
            print("No tunnel available; resuming the same devbox via the SDK now.\n")

    print("\nReconnecting to the resumed devbox via the Agents SDK...")
    restored_state = client.deserialize_session_state(serialized)
    active_session = await client.resume(restored_state)
    await active_session.start()
    print("  Devbox status: running")
    return active_session


async def _snapshot_devbox(session: SandboxSession, *, name: str) -> str | None:
    """Take a disk snapshot of the devbox for audit/observability.

    Returns the snapshot ID, or None if snapshotting is unavailable.
    """
    inner = getattr(session, "_inner", None)
    devbox = getattr(inner, "_devbox", None)
    if devbox is None:
        print("  warning: could not access underlying devbox for snapshot")
        return None
    try:
        snapshot = await devbox.snapshot_disk(
            name=name,
            metadata={"purpose": "audit", "example": "runloop-devbox-lifecycle"},
            commit_message="Post-processing snapshot for observability and audit.",
        )
        snapshot_id = getattr(snapshot, "id", None) or getattr(snapshot, "_id", None)
        if snapshot_id:
            print(f"  snapshot created: {snapshot_id}")
            return str(snapshot_id)
        print("  snapshot created (no ID returned)")
        return None
    except Exception as exc:
        print(f"  warning: snapshot failed: {exc}")
        return None


async def _copy_output_dir(
    *,
    session: SandboxSession,
    destination_root: Path,
) -> list[Path]:
    destination_root.mkdir(parents=True, exist_ok=True)
    remote_output_root = session.normalize_path("output")

    pending_dirs = [remote_output_root]
    copied_files: list[Path] = []
    while pending_dirs:
        current_dir = pending_dirs.pop()
        for entry in await session.ls(current_dir):
            entry_path = Path(entry.path)
            if entry.is_dir():
                pending_dirs.append(entry_path)
                continue

            relative_path = entry_path.relative_to(remote_output_root)
            local_path = destination_root / relative_path
            local_path.parent.mkdir(parents=True, exist_ok=True)

            handle = await session.read(entry_path)
            try:
                payload = handle.read()
            finally:
                handle.close()

            if isinstance(payload, str):
                local_path.write_text(payload, encoding="utf-8")
            else:
                local_path.write_bytes(bytes(payload))
            copied_files.append(local_path)

    return sorted(copied_files)


async def _prompt_with_deadline(
    prompt: str,
    *,
    deadline: float,
    input_func: Callable[[str], str] = input,
    monotonic: Callable[[], float] = time.monotonic,
) -> str | None:
    remaining = deadline - monotonic()
    if remaining <= 0:
        return None

    result_queue: queue.SimpleQueue[object] = queue.SimpleQueue()

    def _read_input() -> None:
        try:
            result_queue.put(input_func(prompt))
        except BaseException as exc:
            result_queue.put(exc)

    threading.Thread(target=_read_input, daemon=True).start()

    while True:
        try:
            response = result_queue.get_nowait()
        except queue.Empty:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(0.05, remaining))
            continue

        if isinstance(response, EOFError | KeyboardInterrupt):
            return ""
        if isinstance(response, BaseException):
            raise response
        return str(response).strip()


def _is_affirmative(response: str) -> bool:
    return response.strip().lower() in {"y", "yes"}


async def _run_final_review_window(
    session: SandboxSession,
    *,
    devbox_name: str,
    download_dir: Path | None,
    stdin_isatty: bool,
    review_timeout_s: float = FINAL_REVIEW_TIMEOUT_S,
    input_func: Callable[[str], str] = input,
    monotonic: Callable[[], float] = time.monotonic,
) -> list[Path]:
    _header("Review & Shutdown")
    if not stdin_isatty:
        print("Non-interactive run detected. Skipping the final review turn and local download.")
        print("Cleanup will delete the devbox immediately.\n")
        return []

    destination_root = download_dir or _default_download_dir(devbox_name)
    deadline = monotonic() + review_timeout_s
    print(
        f"You have {int(review_timeout_s)} seconds to acknowledge the prepared filing "
        "before the devbox shuts down."
    )
    print("Reply with `y` or `yes` to acknowledge or download. Any other response skips.\n")

    acknowledged = await _prompt_with_deadline(
        "Acknowledge the prepared filing? [y/N]: ",
        deadline=deadline,
        input_func=input_func,
        monotonic=monotonic,
    )
    if acknowledged is None:
        print("  review window expired before acknowledgment; proceeding to shutdown")
        return []
    if not _is_affirmative(acknowledged):
        print("  acknowledgment not received; proceeding to shutdown")
        return []

    remaining_s = max(0, int(deadline - monotonic()))
    print(f"  filing acknowledged with about {remaining_s} seconds remaining")

    download_choice = await _prompt_with_deadline(
        f"Download sandbox output/ to {destination_root}? [y/N]: ",
        deadline=deadline,
        input_func=input_func,
        monotonic=monotonic,
    )
    if download_choice is None:
        print("  review window expired before the download choice; proceeding to shutdown")
        return []
    if not _is_affirmative(download_choice):
        print("  local download skipped")
        return []

    print(f"  copying sandbox output/ to {destination_root}")
    copied_files = await _copy_output_dir(session=session, destination_root=destination_root)
    print(f"  copied {len(copied_files)} file(s)")
    for copied_file in copied_files:
        print(f"    {copied_file}")
    print("  download complete; shutting down the devbox now")
    return copied_files


async def _cleanup(
    session: SandboxSession | None,
    client: RunloopSandboxClient,
    *,
    delete: bool = True,
) -> None:
    if session is None:
        return
    if delete and isinstance(session.state, RunloopSandboxSessionState):
        session.state.pause_on_exit = False
    try:
        await session.aclose()
    except Exception as exc:
        print(f"  cleanup warning: {exc}", file=sys.stderr)


async def _cleanup_suspended_state(
    client: RunloopSandboxClient,
    serialized_state: dict[str, object] | None,
    *,
    delete: bool = True,
) -> None:
    if serialized_state is None:
        return

    resumed_for_cleanup: SandboxSession | None = None
    try:
        restored_state = client.deserialize_session_state(serialized_state)
        if delete and isinstance(restored_state, RunloopSandboxSessionState):
            restored_state.pause_on_exit = False
        resumed_for_cleanup = await client.resume(restored_state)
    except Exception as exc:
        print(f"  cleanup warning: could not reconnect to suspended devbox: {exc}", file=sys.stderr)
        return

    await _cleanup(resumed_for_cleanup, client, delete=delete)


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


async def main(
    *,
    model: str,
    blueprint_name: str | None,
    filing_status: str,
    qualifying_children: int,
    w2_path: str | None,
    additional_w2_paths: list[str] | None,
    download_dir: Path | None,
) -> None:
    _require_env("OPENAI_API_KEY")
    _require_env("RUNLOOP_API_KEY")

    initial_w2_path = _resolve_w2_path(
        cli_w2_path=w2_path,
        stdin_isatty=sys.stdin.isatty(),
    )
    pending_follow_up_w2s = _resolve_additional_w2_paths(additional_w2_paths)
    manifest = _build_manifest(
        filing_status=filing_status,
        qualifying_children=qualifying_children,
    )
    devbox_id = _devbox_name()

    tax_agent = SandboxAgent(
        name="Tax Prep Agent",
        model=model,
        instructions=TAX_AGENT_INSTRUCTIONS,
        model_settings=AGENT_REASONING_SETTINGS,
        capabilities=[Shell()],
        default_manifest=manifest,
    )

    verify_agent = SandboxAgent(
        name="Filing Review Agent",
        model=model,
        instructions=VERIFY_AGENT_INSTRUCTIONS,
        model_settings=AGENT_REASONING_SETTINGS,
        capabilities=[Shell()],
        default_manifest=manifest,
    )

    summary_agent = SandboxAgent(
        name="Demo Summary Agent",
        model=model,
        instructions=SUMMARY_AGENT_INSTRUCTIONS,
        model_settings=AGENT_REASONING_SETTINGS,
        capabilities=[Shell()],
        default_manifest=manifest,
    )

    client = RunloopSandboxClient()
    options = RunloopSandboxClientOptions(
        blueprint_name=blueprint_name,
        pause_on_exit=True,
        name=devbox_id,
        user_parameters=RunloopUserParameters(username="root", uid=0),
        timeouts=RunloopTimeouts(create_s=600, resume_s=600),
    )

    active_session: SandboxSession | None = None
    serialized: dict[str, object] | None = None
    uploaded_names: set[str] = set()
    staged_remote_names: list[str] = []

    try:
        # ── Create devbox ─────────────────────────────────────────────
        _header("Create Devbox")
        print("Launching a full Ubuntu 24.04 VM on Runloop.")
        print("The devbox is configured with pause_on_exit=True so it")
        print("suspends instead of shutting down when the session closes.\n")
        active_session = await client.create(manifest=manifest, options=options)
        await active_session.start()
        print(f"  devbox name   : {devbox_id}")
        if blueprint_name:
            print(f"  blueprint     : {blueprint_name}")
        else:
            print("  blueprint     : provider default")
        print(f"  workspace root: {WORKSPACE_ROOT}")
        print("  user          : root (uid=0)")
        print(f"  staged document dir: {DOCUMENT_STAGING_DIR}")
        print(f"  isolated W-2 dir   : {W2_STAGING_DIR}")
        print(f"  filing status : {filing_status}")
        print(f"  qualifying children: {qualifying_children}")
        print("\nThe helper scripts, task config, and persistent staged")
        print("tax-document directories are ready in the devbox.")
        await _pause_and_clear_before_next_turn()

        # ── Initial document intake and tax preparation ───────────────
        _header("Initial Document Intake & Tax Preparation")
        assert active_session is not None
        initial_remote_name = await _upload_w2(
            active_session,
            local_path=initial_w2_path,
            uploaded_names=uploaded_names,
        )
        staged_remote_names.append(initial_remote_name)
        print(f"Uploaded the initial tax document to {DOCUMENT_STAGING_DIR / initial_remote_name}")
        print("Handing the devbox to a SandboxAgent with Shell capability.\n")
        tax_output = await _run_tax_prep_round(
            tax_agent,
            (
                "Create the initial work-in-progress filing from every tax document "
                "currently staged in taxpayer_data/documents/."
            ),
            active_session,
            round_label="Initial tax preparation",
            workflow_name="Runloop lifecycle - tax preparation",
        )
        if not tax_output:
            print("No response was produced.")
        await _pause_and_clear_before_next_turn()

        # ── Additional document intake loop ───────────────────────────
        while True:
            round_number = len(staged_remote_names) + 1
            _header("Additional Document Intake")
            print(f"Preparing to wait for document #{round_number}.")
            print("We suspend the devbox while waiting so the disk state is preserved")
            print("without keeping the environment actively running before we ask")
            print("whether another tax file should be added.\n")

            assert active_session is not None
            serialized, tunnel_key = await _suspend_for_additional_document_wait(
                active_session, client
            )
            active_session = None
            print("\nThe devbox is now suspended while we wait for the next document choice.\n")

            next_w2_path = _next_follow_up_w2_path(
                pending_paths=pending_follow_up_w2s,
                stdin_isatty=sys.stdin.isatty(),
            )
            if next_w2_path is None:
                print("No additional documents were provided.")
                active_session = await _resume_after_additional_document_wait(
                    client,
                    serialized=serialized,
                    tunnel_key=tunnel_key,
                    next_w2_path=None,
                )
                serialized = None
                print(f"  Devbox name  : {devbox_id}")
                print("\nProceeding to final verification.\n")
                await _pause_and_clear_before_next_turn()
                break

            print(f"Selected additional tax file #{round_number}: {next_w2_path}")
            active_session = await _resume_after_additional_document_wait(
                client,
                serialized=serialized,
                tunnel_key=tunnel_key,
                next_w2_path=next_w2_path,
                round_number=round_number,
            )
            serialized = None
            print(f"  Devbox name  : {devbox_id}")

            remote_name = await _upload_w2(
                active_session,
                local_path=next_w2_path,
                uploaded_names=uploaded_names,
            )
            staged_remote_names.append(remote_name)
            print(f"Uploaded document #{round_number} to {DOCUMENT_STAGING_DIR / remote_name}")
            print("Refreshing the work-in-progress filing using every staged tax document.\n")
            tax_output = await _run_tax_prep_round(
                tax_agent,
                (
                    "A new tax document was uploaded. Refresh the existing filing using every "
                    "PDF currently staged in taxpayer_data/documents/."
                ),
                active_session,
                round_label=f"Tax preparation round {round_number}",
                workflow_name=f"Runloop lifecycle - tax preparation round {round_number}",
            )
            if not tax_output:
                print("No response was produced.")
            await _pause_and_clear_before_next_turn()

        # ── Verify persistence and filing review ──────────────────────
        _header("Verify Persistence & Filing Review")
        print("Handing the final staged filing to the filing review agent.\n")
        assert active_session is not None
        verify_output = await _run_agent(
            verify_agent,
            (
                "Verify the final Form 1040 JSON package and audit export survived the "
                "staged suspend/resume workflow and produce the filing checklist."
            ),
            active_session,
            workflow_name="Runloop lifecycle - filing review",
            max_turns=VERIFY_AGENT_MAX_TURNS,
        )
        if not verify_output:
            print("No response was produced.")
        await _pause_and_clear_before_next_turn()

        # ── Snapshot for audit ────────────────────────────────────────
        _header("Audit Snapshot")
        print("Taking a disk snapshot of the final workspace for observability")
        print("and audit purposes. This captures the complete state: the staged")
        print("tax PDFs, the updated tax summary JSON, the audit export, the filing checklist, and")
        print("all installed tools.\n")
        snapshot_name = f"audit-{devbox_id}"
        assert active_session is not None
        snapshot_id = await _snapshot_devbox(active_session, name=snapshot_name)
        if snapshot_id:
            print(f"  snapshot name : {snapshot_name}")
            print("\nThis snapshot can be used to reproduce the exact workspace state")
            print("for compliance review, debugging, or to spin up a new devbox from")
            print("this checkpoint.")
        await _pause_and_clear_before_next_turn()

        # ── Agent-generated summary ───────────────────────────────────
        _header("Summary")
        print("Handing the devbox to the summary agent for a final overview.\n")
        print(
            f"This final summary step allows up to {SUMMARY_AGENT_MAX_TURNS} model turns. "
            "A turn is one model invocation, including tool-use cycles, not a shell-command count.\n"
        )
        assert active_session is not None
        summary_output = await _run_agent(
            summary_agent,
            "Summarize what happened on this devbox during the demo.",
            active_session,
            workflow_name="Runloop lifecycle - summary",
            max_turns=SUMMARY_AGENT_MAX_TURNS,
        )
        if not summary_output:
            print("No response was produced.")
        await _pause_and_clear_before_next_turn()

        assert active_session is not None
        await _run_final_review_window(
            active_session,
            devbox_name=devbox_id,
            download_dir=download_dir,
            stdin_isatty=sys.stdin.isatty(),
        )

    finally:
        try:
            await _cleanup(active_session, client, delete=True)
            await _cleanup_suspended_state(client, serialized, delete=True)
            await client.close()
        finally:
            _clear_screen()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Runloop devbox lifecycle: staged tax-document prep with suspend and wake-on-HTTP resume.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name to use.")
    parser.add_argument(
        "--blueprint-name",
        help="Optional Runloop blueprint name override. Defaults to the provider's standard VM blueprint.",
    )
    parser.add_argument(
        "--filing-status",
        default="single",
        choices=[
            "single",
            "married_filing_jointly",
            "married_filing_separately",
            "head_of_household",
        ],
        help="2024 filing status used for the Form 1040 data-generation workflow.",
    )
    parser.add_argument(
        "--qualifying-children",
        type=int,
        default=0,
        help="Number of qualifying children under 17 for Child Tax Credit calculations.",
    )
    parser.add_argument(
        "--w2-path",
        help=(
            "Optional local path to the initial document PDF. When omitted in a TTY, "
            "the script prompts for one."
        ),
    )
    parser.add_argument(
        "--additional-w2-path",
        action="append",
        default=None,
        help=(
            "Optional follow-up document PDF. Repeat this flag to stage multiple "
            "additional documents in non-interactive runs."
        ),
    )
    parser.add_argument(
        "--download-dir",
        help=(
            "Optional local directory to copy sandbox output/ into after acknowledgment. "
            "Defaults to ./runloop-devbox-lifecycle-downloads/<devbox-name>."
        ),
    )
    args = parser.parse_args()

    asyncio.run(
        main(
            model=args.model,
            blueprint_name=args.blueprint_name,
            filing_status=args.filing_status,
            qualifying_children=args.qualifying_children,
            w2_path=args.w2_path,
            additional_w2_paths=args.additional_w2_path,
            download_dir=Path(args.download_dir).resolve() if args.download_dir else None,
        )
    )
