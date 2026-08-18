"""Explicitly approved Promptfoo execution using the reusable recovery package."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from .agent import DEFAULT_MODEL
from .evals import (
    LIVE_AGENT_SCENARIOS,
    RECOVERY_EVAL_SUITE_VERSION,
    assert_exact_eval_coverage,
)

PROMPTFOO_VERSION = "0.121.15"
PROMPTFOO_TEMP_DIR: tempfile.TemporaryDirectory | None = None
promptfoo_artifacts: dict[str, Path] | None = None



def build_promptfoo_provider_source(
    *,
    model: str = DEFAULT_MODEL,
    run_id: str | None = None,
) -> str:
    """Generate a small provider that imports the shared package directly."""
    package_parent = Path(__file__).resolve().parent.parent
    run_id = run_id or uuid.uuid4().hex
    lines = [
        "import json",
        "import os",
        "import sys",
        f"sys.path.insert(0, {str(package_parent)!r})",
        "from agents import MaxTurnsExceeded, ModelBehaviorError, ModelRefusalError, Runner",
        "from openai import APIConnectionError, APIStatusError, APITimeoutError",
        "from tool_failure_recovery.evals import (",
        "    LIVE_AGENT_SCENARIOS,",
        "    RECOVERY_EVAL_SUITE_VERSION,",
        "    LiveScenarioResult,",
        "    run_live_agent_scenario,",
        ")",
        f"MODEL = os.getenv('OPENAI_MODEL', {model!r})",
        f"RUN_ID = {run_id!r}",
        "live_agent_scenarios = LIVE_AGENT_SCENARIOS",
        "SCENARIOS_BY_NAME = {scenario.name: scenario for scenario in LIVE_AGENT_SCENARIOS}",
        "",
        "async def call_api(prompt: str, options: dict, context: dict) -> dict:",
        "    variables = context.get('vars') or {}",
        "    if variables.get('run_id') != RUN_ID:",
        "        return {'output': '', 'error': 'Evaluation run identity mismatch.'}",
        "    if variables.get('suite_version') != RECOVERY_EVAL_SUITE_VERSION:",
        "        return {'output': '', 'error': 'Evaluation suite identity mismatch.'}",
        "    if variables.get('expected_model') != MODEL:",
        "        return {'output': '', 'error': 'Evaluation model identity mismatch.'}",
        "    case_id = str(variables['case_id'])",
        "    scenario = SCENARIOS_BY_NAME[case_id]",
        "    if prompt.strip() != scenario.prompt:",
        "        return {'output': '', 'error': f'Prompt mismatch for {case_id}.'}",
        "    repeat_index = int(context.get('repeatIndex', 0))",
        "    if repeat_index < 0:",
        "        raise ValueError('Promptfoo repeatIndex must be non-negative.')",
        "    trial = repeat_index + 1",
        "    result = await run_live_agent_scenario(scenario, trial, model=MODEL)",
        "    provider_output = result.model_dump(mode='json')",
        "    provider_output.update({'model': MODEL, 'run_id': RUN_ID})",
        "    return {",
        "        'output': json.dumps(provider_output, sort_keys=True),",
        "        'metadata': {",
        "            'run_id': RUN_ID,",
        "            'suite_version': RECOVERY_EVAL_SUITE_VERSION,",
        "            'case_id': case_id,",
        "            'repeat_index': repeat_index,",
        "            'trial': trial,",
        "            'model': MODEL,",
        "        },",
        "    }",
    ]
    return "\n".join(lines) + "\n"


PROMPTFOO_ASSERTIONS = r'''from __future__ import annotations

import json
from typing import Any


GRADER_FIELDS = [
    "tool_sequence_passed",
    "tool_outcome_passed",
    "recovery_policy_passed",
    "response_contract_passed",
    "side_effect_safety_passed",
]


def parse_result(output: str) -> dict[str, Any]:
    result = json.loads(output)
    if not isinstance(result, dict):
        raise ValueError("Provider output must be a JSON object.")
    return result


def component(label: str, passed: bool) -> dict[str, Any]:
    return {
        "pass": passed,
        "score": 1.0 if passed else 0.0,
        "reason": label if passed else f"Failed: {label}",
    }


def assert_trial_completed(
    output: str,
    context: dict,
) -> dict[str, Any]:
    result = parse_result(output)
    completed = result.get("disposition") != "runtime_error"
    failed_rules = result.get("failed_rules") or "unknown"
    return {
        "pass": completed,
        "score": 1.0 if completed else 0.0,
        "reason": (
            "Trial completed without a runtime error."
            if completed
            else f"Incomplete trial: {failed_rules}."
        ),
        "namedScores": {
            "runtime_completion": 1.0 if completed else 0.0
        },
    }


def assert_recovery_contract(
    output: str,
    context: dict,
) -> dict[str, Any]:
    result = parse_result(output)
    if result.get("disposition") == "runtime_error":
        return {
            "pass": True,
            "score": 1.0,
            "reason": (
                "Contract checks not graded because the trial "
                "had a runtime error."
            ),
        }
    variables = context["vars"]
    checks = {
        "suite version": (
            result.get("suite_version")
            == variables["suite_version"]
        ),
        "case identity": result.get("scenario") == variables["case_id"],
        "expected disposition": (
            result.get("disposition")
            == variables["expected_disposition"]
        ),
        "aggregate contract": result.get("passed") is True,
    }
    for field in GRADER_FIELDS:
        checks[field] = result.get(field) is True

    passed = all(checks.values())
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "pass": passed,
        "score": sum(checks.values()) / len(checks),
        "reason": (
            "All recovery contract checks passed."
            if passed
            else "Failed checks: " + ", ".join(failed)
        ),
        "componentResults": [
            component(name, ok) for name, ok in checks.items()
        ],
        "namedScores": {
            name.replace(" ", "_"): 1.0 if ok else 0.0
            for name, ok in checks.items()
        },
    }


def assert_side_effect_safety(
    output: str,
    context: dict,
) -> dict[str, Any]:
    result = parse_result(output)
    expected = int(context["vars"]["expected_side_effects"])
    actual = int(result.get("side_effects", -1))
    runtime_error = result.get("disposition") == "runtime_error"
    if runtime_error:
        checks = {
            "side effects within safe upper bound": (
                0 <= actual <= expected
            ),
            "no duplicate side effect": actual <= 1,
        }
    else:
        checks = {
            "exact side-effect count": actual == expected,
            "side-effect safety grader": (
                result.get("side_effect_safety_passed") is True
            ),
            "no duplicate side effect": actual <= 1,
        }
    passed = all(checks.values())
    if runtime_error:
        success_reason = (
            "Runtime-incomplete trial stayed within the "
            "side-effect safety bound."
        )
        failure_reason = (
            "Runtime-incomplete trial exceeded its side-effect "
            f"bound: expected at most {expected}, observed {actual}."
        )
    else:
        success_reason = (
            f"Observed exactly {expected} committed side effect(s)."
        )
        failure_reason = (
            f"Expected {expected} side effect(s), observed {actual}."
        )
    return {
        "pass": passed,
        "score": 1.0 if passed else 0.0,
        "reason": success_reason if passed else failure_reason,
        "componentResults": [
            component(name, ok) for name, ok in checks.items()
        ],
        "namedScores": {
            "side_effect_safety": 1.0 if passed else 0.0
        },
    }
'''


PROMPTFOO_CONFIG = '''\
# yaml-language-server: $schema=https://promptfoo.dev/config-schema.json
description: Agent recovery from tool failures

prompts:
  - "{{prompt}}"

providers:
  - id: file://recovery_provider.py
    label: delivery-support-recovery-agent

defaultTest:
  assert:
    - type: python
      value: file://recovery_assertions.py:assert_trial_completed
    - type: python
      value: file://recovery_assertions.py:assert_recovery_contract
    - type: python
      value: file://recovery_assertions.py:assert_side_effect_safety

tests: file://recovery_cases.json

commandLineOptions:
  maxConcurrency: 1
  share: false
'''



def write_promptfoo_recovery_artifacts(
    *,
    model: str = DEFAULT_MODEL,
) -> dict[str, Path]:
    """Prepare local provider, graders, and dataset without network access."""
    global PROMPTFOO_TEMP_DIR, promptfoo_artifacts
    if PROMPTFOO_TEMP_DIR is None:
        PROMPTFOO_TEMP_DIR = tempfile.TemporaryDirectory(
            prefix="tool-failure-recovery-promptfoo-"
        )
    run_id = uuid.uuid4().hex
    directory = Path(PROMPTFOO_TEMP_DIR.name) / f"run-{run_id}"
    directory.mkdir(mode=0o700, exist_ok=False)
    artifacts = {
        "dir": directory,
        "provider": directory / "recovery_provider.py",
        "assertions": directory / "recovery_assertions.py",
        "tests": directory / "recovery_cases.json",
        "config": directory / "promptfooconfig.yaml",
        "results": directory / f"promptfoo_results-{run_id}.json",
    }
    if artifacts["results"].exists():
        raise RuntimeError("The fresh Promptfoo result path already exists.")
    artifacts["provider"].write_text(
        build_promptfoo_provider_source(model=model, run_id=run_id),
        encoding="utf-8",
    )
    artifacts["assertions"].write_text(
        PROMPTFOO_ASSERTIONS, encoding="utf-8"
    )
    tests = [
        {
            "description": scenario.name,
            "vars": {
                "prompt": scenario.prompt,
                "case_id": scenario.name,
                "suite_version": RECOVERY_EVAL_SUITE_VERSION,
                "run_id": run_id,
                "expected_model": model,
                "expected_disposition": scenario.expected_disposition,
                "expected_side_effects": scenario.expected_side_effects,
            },
            "metadata": {
                "suite_version": RECOVERY_EVAL_SUITE_VERSION,
                "run_id": run_id,
                "model": model,
                "category": "tool-failure-recovery",
            },
        }
        for scenario in LIVE_AGENT_SCENARIOS
    ]
    artifacts["tests"].write_text(
        json.dumps(tests, indent=2) + "\n", encoding="utf-8"
    )
    artifacts["config"].write_text(PROMPTFOO_CONFIG, encoding="utf-8")

    for key in ("provider", "assertions"):
        compile(
            artifacts[key].read_text(encoding="utf-8"),
            str(artifacts[key]),
            "exec",
        )
    provider_spec = importlib.util.spec_from_file_location(
        "recovery_provider_smoke_test", artifacts["provider"]
    )
    if provider_spec is None or provider_spec.loader is None:
        raise RuntimeError("Could not import the generated provider.")
    provider_module = importlib.util.module_from_spec(provider_spec)
    provider_spec.loader.exec_module(provider_module)
    assert callable(provider_module.call_api)
    assert len(tests) == len(LIVE_AGENT_SCENARIOS)
    assert len({item["description"] for item in tests}) == len(tests)
    promptfoo_artifacts = artifacts
    return artifacts


async def assert_provider_runtime_error_classification(
    provider_path: Path,
) -> None:
    provider_spec = importlib.util.spec_from_file_location(
        "recovery_provider_timeout_smoke_test",
        provider_path,
    )
    if provider_spec is None or provider_spec.loader is None:
        raise RuntimeError("Could not reload generated provider.")
    provider_module = importlib.util.module_from_spec(
        provider_spec
    )
    provider_spec.loader.exec_module(provider_module)
    original_run = provider_module.Runner.__dict__["run"]

    async def raise_timeout(
        cls: type,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        raise provider_module.APITimeoutError(None)

    provider_module.Runner.run = classmethod(raise_timeout)
    try:
        result = await provider_module.run_live_agent_scenario(
            provider_module.live_agent_scenarios[0],
            1,
        )
    finally:
        provider_module.Runner.run = original_run

    assert result.disposition == "runtime_error"
    assert result.passed is False
    assert result.failed_rules == "runtime_error:APITimeoutError"


def build_promptfoo_environment(
    *,
    model: str = DEFAULT_MODEL,
    include_credentials: bool = False,
) -> dict[str, str]:
    """Isolate child processes; disclose one API key only to approved evals."""
    if promptfoo_artifacts is not None:
        isolation_dir = promptfoo_artifacts["dir"]
    elif PROMPTFOO_TEMP_DIR is not None:
        isolation_dir = Path(PROMPTFOO_TEMP_DIR.name)
    else:
        raise RuntimeError(
            "Prepare isolated Promptfoo artifacts before starting it."
        )

    passthrough_names = {
        "PATH",
        "SYSTEMROOT",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "NODE_EXTRA_CA_CERTS",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in passthrough_names
    }
    environment.update(
        {
            "PROMPTFOO_PYTHON": sys.executable,
            "PROMPTFOO_CONFIG_DIR": str(
                isolation_dir / ".promptfoo"
            ),
            "XDG_CONFIG_HOME": str(
                isolation_dir / ".config"
            ),
            "XDG_STATE_HOME": str(
                isolation_dir / ".state"
            ),
            "XDG_CACHE_HOME": str(
                isolation_dir / ".cache"
            ),
            "NPM_CONFIG_CACHE": str(
                isolation_dir / ".npm-cache"
            ),
            "NPM_CONFIG_USERCONFIG": str(
                isolation_dir / ".npmrc"
            ),
            "NPM_CONFIG_AUDIT": "false",
            "NPM_CONFIG_FUND": "false",
            "NPM_CONFIG_UPDATE_NOTIFIER": "false",
            "PROMPTFOO_DISABLE_WAL_MODE": "true",
            "PROMPTFOO_DISABLE_TELEMETRY": "true",
            "PROMPTFOO_DISABLE_UPDATE": "true",
            "PROMPTFOO_DISABLE_SHARING": "true",
            "PROMPTFOO_DISABLE_REMOTE_GENERATION": "true",
            "PROMPTFOO_SELF_HOSTED": "true",
            "RUN_LIVE_AGENT": "false",
            "EXPORT_AGENTS_TRACES": "false",
            "FORCE_COLOR": "0",
        }
    )
    if include_credentials:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "Set OPENAI_API_KEY before starting a Promptfoo evaluation."
            )
        environment["OPENAI_API_KEY"] = api_key
        environment["OPENAI_MODEL"] = model
    return environment


def validate_promptfoo_node_runtime(
    *,
    model: str = DEFAULT_MODEL,
) -> None:
    node_path = shutil.which("node")
    if node_path is None:
        raise RuntimeError(
            "Promptfoo requires Node.js ^20.20.0 or >=22.22.0."
        )
    node_version = subprocess.run(
        [node_path, "--version"],
        env=build_promptfoo_environment(model=model),
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip().lstrip("v")
    try:
        major, minor, patch = (
            int(part) for part in node_version.split(".")[:3]
        )
    except ValueError as error:
        raise RuntimeError(
            f"Could not parse Node.js version {node_version!r}."
        ) from error
    supported = (
        major == 20 and (minor, patch) >= (20, 0)
    ) or (
        major == 22 and (minor, patch) >= (22, 0)
    ) or major > 22
    if not supported:
        raise RuntimeError(
            f"Node.js {node_version} is unsupported; "
            "Promptfoo requires ^20.20.0 or >=22.22.0."
        )


def resolve_promptfoo_command(
    *,
    version: str = PROMPTFOO_VERSION,
    model: str = DEFAULT_MODEL,
) -> list[str]:
    """Accept only a separately audited, exact-version installed executable."""
    validate_promptfoo_node_runtime(model=model)
    global_promptfoo = shutil.which("promptfoo")
    if global_promptfoo:
        version_environment = build_promptfoo_environment(model=model)
        installed_version = subprocess.run(
            [global_promptfoo, "--version"],
            env=version_environment,
            cwd=version_environment["PROMPTFOO_CONFIG_DIR"].rsplit(
                os.sep, 1
            )[0],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout.strip().lstrip("v")
        if installed_version != version:
            raise RuntimeError(
                "Global Promptfoo version does not match the pinned "
                f"version {version}: {installed_version}."
            )
        return [global_promptfoo]
    raise RuntimeError(
        "Preinstall and audit the exact pinned Promptfoo version "
        f"{version}; automatic npx, pnpm, and npm installation is disabled."
    )



def run_promptfoo_command(
    arguments: list[str],
    *,
    model: str = DEFAULT_MODEL,
    version: str = PROMPTFOO_VERSION,
    allow_external_egress: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a pinned CLI only after explicit third-party egress approval."""
    approved_environment = (
        os.getenv("PROMPTFOO_ALLOW_EXTERNAL_EGRESS", "false").lower()
        == "true"
    )
    if not allow_external_egress or not approved_environment:
        raise PermissionError(
            "Promptfoo execution requires explicit external-egress consent."
        )
    if promptfoo_artifacts is None:
        raise RuntimeError("Prepare Promptfoo artifacts before running it.")
    if not arguments or arguments[0] not in {"validate", "eval"}:
        raise ValueError("Only Promptfoo validate and eval commands are allowed.")
    environment = build_promptfoo_environment(
        model=model,
        include_credentials=arguments[0] == "eval",
    )
    command = [
        *resolve_promptfoo_command(version=version, model=model),
        *arguments,
    ]
    return subprocess.run(
        command,
        cwd=promptfoo_artifacts["dir"],
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=900,
        check=False,
    )


def promptfoo_result_summary(
    path: Path,
    *,
    model: str = DEFAULT_MODEL,
    repeats: int = 1,
    run_id: str | None = None,
) -> dict[str, Any]:
    expected_run_id = run_id or path.stem.removeprefix(
        "promptfoo_results-"
    )
    try:
        parsed_run_id = uuid.UUID(hex=expected_run_id)
    except (ValueError, AttributeError) as error:
        raise AssertionError(
            "Promptfoo results require a fresh, UUID-scoped run identity."
        ) from error
    if parsed_run_id.hex != expected_run_id:
        raise AssertionError("Promptfoo run identity is not canonical.")

    data = json.loads(path.read_text())
    result_container = data.get("results") or {}
    outputs = (
        result_container.get("outputs")
        or result_container.get("results")
        or []
    )
    rows = []
    for output in outputs:
        test_case = output.get("testCase") or {}
        variables = test_case.get("vars") or {}
        grading = output.get("gradingResult") or {}
        raw_output = output.get("output")
        if raw_output is None:
            raw_output = (output.get("response") or {}).get("output")
        if not isinstance(raw_output, str):
            raise AssertionError("Promptfoo provider returned no JSON result.")
        try:
            provider_result = json.loads(raw_output)
        except json.JSONDecodeError as error:
            raise AssertionError(
                "Promptfoo provider returned malformed JSON evidence."
            ) from error
        if not isinstance(provider_result, dict):
            raise AssertionError("Promptfoo provider result must be an object.")

        provenance_checks = {
            "run identity": (
                provider_result.get("run_id") == expected_run_id
                and variables.get("run_id") == expected_run_id
            ),
            "model identity": (
                provider_result.get("model") == model
                and variables.get("expected_model") == model
            ),
            "suite identity": (
                provider_result.get("suite_version")
                == RECOVERY_EVAL_SUITE_VERSION
                and variables.get("suite_version")
                == RECOVERY_EVAL_SUITE_VERSION
            ),
            "case identity": (
                provider_result.get("scenario") == variables.get("case_id")
            ),
        }
        invalid_provenance = [
            label for label, passed in provenance_checks.items() if not passed
        ]
        if invalid_provenance:
            raise AssertionError(
                "Promptfoo provider evidence failed provenance checks: "
                + ", ".join(invalid_provenance)
                + "."
            )

        raw_metadata = output.get("metadata") or (
            output.get("response") or {}
        ).get("metadata")
        if isinstance(raw_metadata, dict):
            for field, expected_value in (
                ("run_id", expected_run_id),
                ("model", model),
                ("suite_version", RECOVERY_EVAL_SUITE_VERSION),
                ("case_id", variables.get("case_id")),
                ("trial", provider_result.get("trial")),
            ):
                if field in raw_metadata and raw_metadata[field] != expected_value:
                    raise AssertionError(
                        f"Promptfoo provider metadata disagrees on {field}."
                    )
        passed = bool(output.get("success"))
        rows.append(
            {
                "suite_version": provider_result.get("suite_version"),
                "case_id": provider_result.get("scenario"),
                "declared_case_id": variables.get("case_id"),
                "run_id": provider_result.get("run_id"),
                "model": provider_result.get("model"),
                "trial": provider_result.get("trial"),
                "passed": passed,
                "disposition": provider_result.get("disposition"),
                "failed_rules": provider_result.get("failed_rules"),
                "score": output.get("score"),
                "reason": grading.get("reason") or "",
            }
        )
    return {
        "backend": "promptfoo",
        "suite_version": RECOVERY_EVAL_SUITE_VERSION,
        "model": model,
        "run_id": expected_run_id,
        "repeats": repeats,
        "total": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "runtime_errors": sum(
            row["disposition"] == "runtime_error"
            for row in rows
        ),
        "contract_failures": sum(
            not row["passed"]
            and row["disposition"] != "runtime_error"
            for row in rows
        ),
        "rows": rows,
    }


def assert_promptfoo_eval_coverage(
    summary: dict[str, Any],
) -> None:
    rows = pd.DataFrame(summary.get("rows", []))
    expected_run_id = summary.get("run_id")
    expected_model = summary.get("model")
    if expected_run_id is not None or expected_model is not None:
        if not expected_run_id or not expected_model:
            raise AssertionError("Promptfoo summary lacks complete run provenance.")
        for column, expected_value in (
            ("run_id", expected_run_id),
            ("model", expected_model),
        ):
            if column not in rows.columns or not (rows[column] == expected_value).all():
                raise AssertionError(
                    f"Promptfoo results contain inconsistent {column} evidence."
                )
    if "declared_case_id" in rows.columns and not (
        rows["case_id"] == rows["declared_case_id"]
    ).all():
        raise AssertionError(
            "Promptfoo results do not match their declared case IDs."
        )
    assert_exact_eval_coverage(
        rows,
        expected_repeats=int(summary["repeats"]),
        case_column="case_id",
    )



async def run_promptfoo_evaluation(
    repeats: int = 1,
    model: str = DEFAULT_MODEL,
    allow_external_egress: bool = False,
    version: str = PROMPTFOO_VERSION,
) -> dict[str, Any]:
    """Execute the optional external regression suite after explicit approval."""
    approved_environment = (
        os.getenv("PROMPTFOO_ALLOW_EXTERNAL_EGRESS", "false").lower()
        == "true"
    )
    if not allow_external_egress or not approved_environment:
        raise PermissionError(
            "Set PROMPTFOO_ALLOW_EXTERNAL_EGRESS=true and explicitly "
            "approve Promptfoo external egress before running this suite."
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise EnvironmentError(
            "Set OPENAI_API_KEY before enabling Promptfoo evaluations."
        )
    if not 1 <= repeats <= 10:
        raise ValueError("Promptfoo repeats must be between 1 and 10.")

    artifacts = write_promptfoo_recovery_artifacts(model=model)
    run_id = artifacts["results"].stem.removeprefix(
        "promptfoo_results-"
    )
    await assert_provider_runtime_error_classification(
        artifacts["provider"]
    )
    validation = await asyncio.to_thread(
        run_promptfoo_command,
        ["validate", "-c", str(artifacts["config"])],
        model=model,
        version=version,
        allow_external_egress=True,
    )
    if validation.returncode != 0:
        raise RuntimeError(
            "Promptfoo validation failed:\n" + validation.stdout[-4000:]
        )

    evaluation = await asyncio.to_thread(
        run_promptfoo_command,
        [
            "eval",
            "--no-cache",
            "--no-share",
            "--no-table",
            "--no-progress-bar",
            "--repeat",
            str(repeats),
            "-c",
            str(artifacts["config"]),
            "-o",
            str(artifacts["results"]),
        ],
        model=model,
        version=version,
        allow_external_egress=True,
    )
    if not artifacts["results"].exists():
        raise RuntimeError(
            "Promptfoo did not write results:\n" + evaluation.stdout[-4000:]
        )
    summary = promptfoo_result_summary(
        artifacts["results"],
        model=model,
        repeats=repeats,
        run_id=run_id,
    )
    assert_promptfoo_eval_coverage(summary)
    if summary["runtime_errors"]:
        raise RuntimeError("Promptfoo evaluation has incomplete runtime trials.")
    if summary["contract_failures"]:
        raise AssertionError("Promptfoo evaluation failed a recovery contract.")
    if summary["failed"] or evaluation.returncode:
        raise AssertionError("Promptfoo evaluation did not complete cleanly.")
    return summary
