from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAGRAMS = (
    "controlled-agentic-commerce-overview.png",
    "controlled-agentic-commerce-local-and-testnet.png",
    "controlled-agentic-commerce-x402-sequence.png",
)


def _notebook_path() -> Path:
    candidates = (
        ROOT / "controlled_agentic_commerce.ipynb",
        ROOT / "cookbook/controlled_agentic_commerce.ipynb",
    )
    return next(path for path in candidates if path.is_file())


def test_documented_uv_commands_do_not_require_a_lockfile() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    notebook = _notebook_path().read_text(encoding="utf-8")

    assert "uv run" in readme
    assert "--frozen" not in readme
    assert "--frozen" not in notebook


def test_notebook_is_committed_without_outputs() -> None:
    notebook = json.loads(_notebook_path().read_text(encoding="utf-8"))
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]

    assert code_cells
    assert all(cell.get("execution_count") is None for cell in code_cells)
    assert all(cell.get("outputs", []) == [] for cell in code_cells)


def test_notebook_has_publishable_boundaries_and_diagrams() -> None:
    notebook = json.loads(_notebook_path().read_text(encoding="utf-8"))
    source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])

    assert "Agentic commerce" in source
    assert "AgentCore Payments" in source
    assert "optional connection to AgentCore Payments" not in source
    assert "### Using the Responses API directly" in source
    assert "responses_client.responses.create" in source
    assert '"function_call_output"' in source
    assert "**Authors:** Deepak Jain and Sid Rampally" not in source
    assert "AgentCore Runtime is not used by this notebook" in source
    assert "RUN_AGENTCORE_E2E" in source
    assert "run_managed_e2e" in source
    assert "settlement_verified=false" in source
    assert "Sanitized validation snapshot" not in source
    for diagram in DIAGRAMS:
        relative_path = Path("../../../../images/partners/AWS") / diagram
        assert str(relative_path) in source
        image = (ROOT / relative_path).resolve()
        assert image.is_file()
        assert image.stat().st_size > 10_000
        assert image.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_live_opt_ins_are_disabled_by_default() -> None:
    settings = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", maxsplit=1)
            settings[name] = value

    assert settings["ALLOW_AGENTCORE_TESTNET"] == "0"
    assert settings["ALLOW_AGENTCORE_READ_ONLY"] == "0"
    assert settings["RUN_AGENTCORE_E2E"] == "0"
    assert settings["ALLOW_PAID_INFERENCE"] == "0"
    assert settings["APPROVE_AGENTCORE_TESTNET_PURCHASE"] == "0"
    assert settings["ALLOW_AGENTCORE_SESSION_ADMIN"] == "0"
    assert settings["PAYMENT_MANAGER_ARN"] == ""
    assert settings["PAYMENT_INSTRUMENT_ID"] == ""
    assert settings["PAYMENT_SESSION_ID"] == ""
    assert settings["PAYMENT_USER_ID"] == ""
    assert settings["X402_APPROVED_PAY_TO"] == ""
    assert settings["BEDROCK_AWS_PROFILE"] == ""
    assert settings["AGENTCORE_SESSION_AWS_PROFILE"] == ""
    assert settings["AGENTCORE_RUNTIME_AWS_PROFILE"] == ""


def test_publishable_text_has_no_high_confidence_credentials() -> None:
    allowed_suffixes = {
        ".example",
        ".ipynb",
        ".json",
        ".md",
        ".py",
        ".toml",
        ".yaml",
        ".yml",
    }
    excluded_parts = {".git", ".venv", "__pycache__"}
    patterns = (
        re.compile("-" * 5 + r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY" + "-" * 5),
        re.compile(r"\bA" + r"KIA[0-9A-Z]{16}\b"),
        re.compile(r"\bA" + r"SIA[0-9A-Z]{16}\b"),
        re.compile(
            r"aws_secret_" + r"access_key\s*=\s*[A-Za-z0-9/+=]{32,}",
            re.IGNORECASE,
        ),
    )
    findings = []
    for path in ROOT.rglob("*"):
        if (
            not path.is_file()
            or path.suffix not in allowed_suffixes
            or excluded_parts.intersection(path.parts)
        ):
            continue
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in patterns):
            findings.append(str(path.relative_to(ROOT)))

    assert findings == []
