"""Process, service, and report utilities for the executable cookbook.

The notebook keeps requests, responses, and the agent configuration visible;
this module owns subprocess limits, environment filtering, and cleanup.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

PROCESS_SUPPORT_ENV_NAMES = frozenset(
    {
        "ALL_PROXY",
        "COMSPEC",
        "COOKBOOK_DEMO_TRAVEL_DATE",
        "CURL_CA_BUNDLE",
        "FORCE_COLOR",
        "HOME",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LOGNAME",
        "NODE_EXTRA_CA_CERTS",
        "NO_COLOR",
        "NO_PROXY",
        "PATH",
        "PATHEXT",
        "REQUESTS_CA_BUNDLE",
        "SHELL",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "TMPDIR",
        "USER",
        "USERPROFILE",
        "UV_CACHE_DIR",
        "UV_NO_CACHE",
        "UV_OFFLINE",
        "UV_PROJECT_ENVIRONMENT",
        "UV_PYTHON",
        "UV_PYTHON_DOWNLOADS",
        "UV_SYSTEM_PYTHON",
        "VIRTUAL_ENV",
        "WINDIR",
        "XDG_CACHE_HOME",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)
AWS_LIVE_ENV_NAMES = frozenset(
    {
        "AWS_ACCESS_KEY_ID",
        "AWS_CA_BUNDLE",
        "AWS_CONFIG_FILE",
        "AWS_CONTAINER_AUTHORIZATION_TOKEN",
        "AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
        "AWS_DEFAULT_REGION",
        "AWS_EC2_METADATA_DISABLED",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_ROLE_ARN",
        "AWS_ROLE_SESSION_NAME",
        "AWS_SDK_LOAD_CONFIG",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SECURITY_TOKEN",
        "AWS_SESSION_TOKEN",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
    }
)
OPENAI_LIVE_ENV_NAMES = frozenset(
    {
        "OPENAI_AGENTS_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_PROJECT_ID",
        "OPENAI_TRACE_API_KEY",
        "OPENAI_TRACE_WORKFLOW_NAME",
    }
)
DEFAULT_COMMAND_TIMEOUT_SECONDS = 600
COMMAND_TERMINATION_GRACE_SECONDS = 5
COMMAND_OUTPUT_POLL_SECONDS = 0.05
MAX_COMMAND_OUTPUT_BYTES = 1_048_576
MAX_DIAGNOSTIC_CHARACTERS = 4_000


def selected_environment(
    extra_names: frozenset[str] = frozenset(),
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    allowed_names = PROCESS_SUPPORT_ENV_NAMES | extra_names
    environment = {name: os.environ[name] for name in allowed_names if name in os.environ}
    if overrides:
        environment.update(overrides)
    return environment


def bounded_diagnostic(
    value: str,
    env: dict[str, str],
    limit: int = MAX_DIAGNOSTIC_CHARACTERS,
) -> str:
    diagnostic = value
    sensitive_markers = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
    for name, secret in env.items():
        if (
            any(marker in name.upper() for marker in sensitive_markers)
            and secret
            and len(secret) >= 4
        ):
            diagnostic = diagnostic.replace(secret, "[REDACTED]")
    diagnostic = re.sub(
        r"\b((?:[a-z][a-z0-9+.-]*:)?//)[^/\s@]+@",
        r"\1[REDACTED]@",
        diagnostic,
        flags=re.IGNORECASE,
    )
    diagnostic = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[REDACTED_AWS_ACCESS_KEY]", diagnostic)
    diagnostic = re.sub(r"(Bearer\s+)[^\s]+", r"\1[REDACTED]", diagnostic, flags=re.IGNORECASE)
    diagnostic = re.sub(
        r"((?:api[_-]?key|access[_-]?key|session[_-]?token|secret|password|credential)\s*[=:]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        diagnostic,
        flags=re.IGNORECASE,
    )
    diagnostic = diagnostic.strip()
    if len(diagnostic) <= limit:
        return diagnostic
    return "[... diagnostic truncated ...]\n" + diagnostic[-limit:]


def terminate_process(
    process: subprocess.Popen[str] | subprocess.Popen[bytes],
    grace_seconds: int = COMMAND_TERMINATION_GRACE_SECONDS,
) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=grace_seconds)


def stream_size(stream: BinaryIO) -> int:
    return os.fstat(stream.fileno()).st_size


def read_stream_tail(stream: BinaryIO, limit: int) -> str:
    stream.flush()
    size = stream_size(stream)
    stream.seek(max(0, size - limit))
    return stream.read(limit).decode("utf-8", errors="replace")


def run(
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout_seconds: int = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    command_env = dict(env) if env is not None else selected_environment()
    command_display = bounded_diagnostic(" ".join(command), command_env, limit=500)
    print("$", command_display)
    failure_reason: str | None = None
    with (
        tempfile.TemporaryFile(mode="w+b") as stdout_log,
        tempfile.TemporaryFile(mode="w+b") as stderr_log,
    ):
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=command_env,
                stdout=stdout_log,
                stderr=stderr_log,
            )
        except OSError as exc:
            diagnostic = bounded_diagnostic(str(exc), command_env)
            raise RuntimeError(
                f"Could not start command: {command_display}\n{diagnostic}"
            ) from None

        deadline = time.monotonic() + timeout_seconds
        try:
            while process.poll() is None:
                output_bytes = stream_size(stdout_log) + stream_size(stderr_log)
                if output_bytes > MAX_COMMAND_OUTPUT_BYTES:
                    failure_reason = (
                        f"Command output exceeded {MAX_COMMAND_OUTPUT_BYTES} bytes: "
                        f"{command_display}"
                    )
                    terminate_process(process)
                    break
                if time.monotonic() >= deadline:
                    failure_reason = (
                        f"Command timed out after {timeout_seconds} seconds: {command_display}"
                    )
                    terminate_process(process)
                    break
                time.sleep(COMMAND_OUTPUT_POLL_SECONDS)
        except BaseException:
            terminate_process(process)
            raise

        output_bytes = stream_size(stdout_log) + stream_size(stderr_log)
        if output_bytes > MAX_COMMAND_OUTPUT_BYTES and failure_reason is None:
            failure_reason = (
                f"Command output exceeded {MAX_COMMAND_OUTPUT_BYTES} bytes: {command_display}"
            )
        stream_limit = (
            MAX_COMMAND_OUTPUT_BYTES // 2 if failure_reason else MAX_COMMAND_OUTPUT_BYTES
        )
        stdout = read_stream_tail(stdout_log, stream_limit)
        stderr = read_stream_tail(stderr_log, stream_limit)

    captured = "\n".join(part for part in (stdout, stderr) if part)
    diagnostic = bounded_diagnostic(captured, command_env)
    if failure_reason:
        raise RuntimeError(failure_reason + (f"\n{diagnostic}" if diagnostic else ""))

    completed = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    if completed.returncode:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {command_display}"
            + (f"\n{diagnostic}" if diagnostic else "")
        )
    return completed


@contextmanager
def local_runtime_service(uv: str, runtime_dir: Path) -> Iterator[dict]:
    """Start the credential-free HTTP service and stop it even if a cell fails."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as port_check:
        port_check.settimeout(0.5)
        if port_check.connect_ex(("127.0.0.1", 8080)) == 0:
            raise RuntimeError(
                "Port 8080 is already in use; stop that process before running this cell."
            )

    service_env = selected_environment(overrides={"COOKBOOK_FORCE_LOCAL_TOOLS": "1"})
    with tempfile.TemporaryFile(mode="w+b") as service_log:
        service = subprocess.Popen(
            [uv, "run", "python", "runtime.py"],
            cwd=runtime_dir,
            env=service_env,
            stdout=service_log,
            stderr=subprocess.STDOUT,
        )

        def check_output() -> None:
            if stream_size(service_log) > MAX_COMMAND_OUTPUT_BYTES:
                raise RuntimeError(
                    f"AgentCore service output exceeded {MAX_COMMAND_OUTPUT_BYTES} bytes."
                )

        try:
            deadline = time.monotonic() + 30
            while True:
                check_output()
                if service.poll() is not None:
                    raise RuntimeError("AgentCore service exited before becoming healthy.")
                try:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:8080/ping", timeout=2
                    ) as response:
                        health = json.loads(response.read())
                    if service.poll() is None:
                        break
                except (urllib.error.URLError, TimeoutError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "AgentCore service did not become healthy before the 30-second deadline."
                    )
                time.sleep(0.25)

            yield health
            check_output()
        except Exception as exc:
            terminate_process(service, grace_seconds=10)
            logs = read_stream_tail(service_log, 8_000)
            diagnostic = bounded_diagnostic(str(exc) + "\n" + logs, service_env)
            raise RuntimeError(diagnostic) from None
        finally:
            terminate_process(service, grace_seconds=10)


def evaluation_environment() -> dict[str, str]:
    """Pass only the credentials and settings used by the live evaluation runner."""
    return selected_environment(
        AWS_LIVE_ENV_NAMES
        | OPENAI_LIVE_ENV_NAMES
        | frozenset(
            {
                "COOKBOOK_TRACING_MODE",
                "LOCAL_AGENT_LOG_GROUP",
                "LOCAL_AGENT_SERVICE_NAME",
                "PROMPTFOO_AGENT_EVALUATION_CASE_IDS",
                "PROMPTFOO_AGENT_EVALUATION_TIMEOUT_MS",
            }
        ),
        overrides={"RUN_PROMPTFOO_AGENT_EVALUATION": "1"},
    )


def live_runtime_environment(demo_travel_date: str) -> dict[str, str]:
    """An existing Runtime needs AWS invoke access, not local model or trace keys."""
    return selected_environment(
        AWS_LIVE_ENV_NAMES
        | frozenset(
            {
                "AGENTCORE_RUNTIME_AGENT_ARN",
                "AGENTCORE_RUNTIME_QUALIFIER",
                "AGENTCORE_RUNTIME_REGION",
                "AGENTCORE_RUNTIME_USER_ID",
            }
        ),
        overrides={
            "COOKBOOK_DEMO_TRAVEL_DATE": demo_travel_date,
            "COOKBOOK_EXECUTION_MODE": "deployed",
        },
    )


def run_agent_evaluation(node: str, runtime_dir: Path) -> dict:
    """Run the guarded evaluation and summarize its one fresh report."""
    if os.getenv("RUN_PROMPTFOO_AGENT_EVALUATION", "0") != "1":
        raise RuntimeError(
            "Set RUN_PROMPTFOO_AGENT_EVALUATION=1 before running agent evaluations."
        )
    results_directory = runtime_dir / "evals" / "results"
    reports_before = set(results_directory.glob("promptfoo-agent-*.json"))
    # Bypass the npm --env-file wrapper so it cannot add unrelated credentials.
    run(
        [node, "evals/run-agent-evaluation.cjs"],
        runtime_dir,
        evaluation_environment(),
        timeout_seconds=2_000,
    )
    new_reports = set(results_directory.glob("promptfoo-agent-*.json")) - reports_before
    if len(new_reports) != 1:
        raise RuntimeError(f"Expected one new Promptfoo report, found {len(new_reports)}.")

    report_path = new_reports.pop()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    result_block = report["results"]
    stats = result_block["stats"]
    case_summaries = []
    for result in result_block["results"]:
        trace_metadata = result.get("response", {}).get("metadata", {})
        case_summaries.append(
            {
                "case_id": result.get("vars", {}).get("case_id"),
                "success": result.get("success"),
                "score": result.get("score"),
                "runtime_session_id": trace_metadata.get("runtime_session_id"),
                "invocation_id": trace_metadata.get("invocation_id"),
            }
        )
    if stats["failures"] or stats["errors"]:
        raise RuntimeError(f"Promptfoo evaluation did not pass: {stats}")

    trace_workflow_base = (
        os.getenv("OPENAI_TRACE_WORKFLOW_NAME", "").strip() or "ChatGPT flight agent"
    )
    return {
        "report": str(report_path.relative_to(runtime_dir.parent)),
        "successes": stats["successes"],
        "failures": stats["failures"],
        "errors": stats["errors"],
        "cases": case_summaries,
        "openai_trace_workflow": f"{trace_workflow_base} (local)",
        "openai_traces": "https://platform.openai.com/traces",
    }
