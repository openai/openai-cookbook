from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = REPOSITORY_ROOT / "scripts" / "aws-observability-preflight.sh"


def test_preflight_rejects_conflicting_region_variables() -> None:
    environment = {
        "PATH": os.environ["PATH"],
        "AWS_REGION": "us-west-2",
        "AWS_DEFAULT_REGION": "us-east-1",
    }

    result = subprocess.run(
        ["bash", str(PREFLIGHT)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "AWS_REGION and AWS_DEFAULT_REGION must match" in result.stderr
    assert "Read-only AWS observability preflight" not in result.stdout


def run_preflight(
    tmp_path: Path, *, environment: dict[str, str], profile_region: str = ""
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_aws = fake_bin / "aws"
    fake_aws.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$*" >> "$PREFLIGHT_TEST_COMMANDS"\n'
        'if [[ "$*" == "configure get region" ]]; then\n'
        '  printf "%s\\n" "$PREFLIGHT_TEST_PROFILE_REGION"\n'
        "fi\n",
        encoding="utf-8",
    )
    fake_aws.chmod(0o755)
    commands = tmp_path / "aws-commands.txt"
    process_environment = {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "AWS_PROFILE": "agentcore-test",
        "COOKBOOK_TRACE_VERIFICATION_LOG_GROUP": "test-spans",
        "PREFLIGHT_TEST_COMMANDS": str(commands),
        "PREFLIGHT_TEST_PROFILE_REGION": profile_region,
        **environment,
    }
    result = subprocess.run(
        ["bash", str(PREFLIGHT)],
        cwd=REPOSITORY_ROOT,
        env=process_environment,
        capture_output=True,
        text=True,
        check=False,
    )
    return result, commands.read_text().splitlines() if commands.exists() else []


@pytest.mark.parametrize(
    ("environment", "profile_region", "expected"),
    [
        ({"AWS_REGION": "us-west-2"}, "", "us-west-2"),
        ({"AWS_DEFAULT_REGION": "us-east-2"}, "", "us-east-2"),
        ({"AWS_REGION": "us-west-2"}, "eu-west-1", "us-west-2"),
        ({}, "eu-west-1", "eu-west-1"),
        (
            {"COOKBOOK_EXECUTION_MODE": "local", "AGENTCORE_RUNTIME_REGION": "us-east-1"},
            "eu-west-1",
            "eu-west-1",
        ),
        (
            {
                "COOKBOOK_EXECUTION_MODE": "deployed",
                "AGENTCORE_RUNTIME_REGION": "us-east-1",
                "AWS_REGION": "us-west-2",
                "AWS_DEFAULT_REGION": "eu-west-1",
            },
            "ap-south-1",
            "us-east-1",
        ),
        ({"COOKBOOK_EXECUTION_MODE": "deployed"}, "eu-west-1", "eu-west-1"),
        (
            {
                "FLIGHT_DATA_SOURCE": "agentcore-runtime",
                "AGENTCORE_RUNTIME_REGION": "us-east-1",
            },
            "eu-west-1",
            "us-east-1",
        ),
    ],
)
def test_preflight_uses_selected_region_and_log_group(
    tmp_path: Path, environment: dict[str, str], profile_region: str, expected: str
) -> None:
    result, commands = run_preflight(
        tmp_path, environment=environment, profile_region=profile_region
    )
    assert result.returncode == 0
    assert f"Region: {expected}" in result.stdout
    assert "Trace log group: test-spans" in result.stdout
    assert "Read-only diagnostics completed" in result.stdout
    diagnostic_commands = [command for command in commands if command != "configure get region"]
    assert len(diagnostic_commands) == 6
    assert all(f"--region {expected} " in command for command in diagnostic_commands)
    assert sum("test-spans" in command for command in diagnostic_commands) == 2
    # Empty read results remain diagnostic evidence, not an ingestion-readiness gate.
    assert "This does not verify that a trace was ingested" in result.stdout


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({}, "AWS Region is missing"),
        ({"COOKBOOK_EXECUTION_MODE": "remote"}, "must be local or deployed"),
        ({"FLIGHT_DATA_SOURCE": "stub"}, "must be local-agent or agentcore-runtime"),
        (
            {"COOKBOOK_EXECUTION_MODE": "local", "FLIGHT_DATA_SOURCE": "agentcore-runtime"},
            "conflicts with legacy FLIGHT_DATA_SOURCE",
        ),
    ],
)
def test_preflight_rejects_missing_or_conflicting_configuration(
    tmp_path: Path, environment: dict[str, str], message: str
) -> None:
    result, commands = run_preflight(tmp_path, environment=environment)
    assert result.returncode == 1
    assert message in result.stderr
    assert "Read-only AWS observability preflight" not in result.stdout
    assert all(command == "configure get region" for command in commands)
