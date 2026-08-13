"""Validate regulated-industry Codex configuration blueprints.

The default checks use only the Python 3.11 standard library. Pass ``--schema``
to validate client configuration files and managed permission profiles against a
downloaded Codex JSON schema; that optional mode requires ``jsonschema``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib


MINIMUM_CODEX_VERSION = "0.138.0"
PROFILE_NAME = "regulated_workspace"
ALLOWED_APPROVAL_POLICIES = frozenset({"on-request", "untrusted"})
ALLOWED_SANDBOX_MODES = frozenset({"read-only", "workspace-write"})
ALLOWED_WEB_SEARCH_MODES = frozenset({"disabled", "cached"})
REQUIRED_SECRET_PATTERNS = frozenset(
    {
        ".env",
        ".env.local",
        "**/.env",
        "**/.env.*",
        "**/*.env",
        "**/*.key",
        "**/*.pem",
        "**/*.p12",
        "**/*.pfx",
    }
)
REQUIRED_DISABLED_FEATURES = frozenset(
    {
        "browser_use",
        "browser_use_external",
        "computer_use",
        "enable_mcp_apps",
        "guardian_approval",
        "in_app_browser",
        "memories",
        "memory_tool",
        "remote_control",
        "skill_mcp_dependency_install",
    }
)
SUPPORTED_REQUIREMENT_KEYS = frozenset(
    {
        "allow_appshots",
        "allow_managed_hooks_only",
        "allowed_approval_policies",
        "allowed_approvals_reviewers",
        "allowed_permission_profiles",
        "allowed_sandbox_modes",
        "allowed_web_search_modes",
        "apps",
        "computer_use",
        "default_permissions",
        "enforce_residency",
        "experimental_network",
        "features",
        "guardian_policy_config",
        "hooks",
        "mcp_servers",
        "permissions",
        "plugins",
        "remote_sandbox_config",
        "rules",
        "windows",
    }
)


@dataclass(frozen=True)
class Blueprint:
    """Pair one complete managed-requirements file with its client defaults."""

    platform: str
    requirements: str
    config: str


BLUEPRINTS = (Blueprint("general", "requirements.toml", "config.toml"),)


def load_toml(path: Path) -> dict[str, Any]:
    """Read a UTF-8 TOML document without expanding local paths or secrets."""

    with path.open("rb") as source:
        return tomllib.load(source)


def validate_requirements(requirements: dict[str, Any], platform: str) -> list[str]:
    """Return security or compatibility findings for one requirements file."""

    findings: list[str] = []
    unsupported = sorted(set(requirements) - SUPPORTED_REQUIREMENT_KEYS)
    if unsupported:
        findings.append(f"unsupported managed requirement keys: {unsupported}")

    policies = requirements.get("allowed_approval_policies", [])
    if not policies or not set(policies).issubset(ALLOWED_APPROVAL_POLICIES):
        findings.append("approval policies must require supervised human review")
    if requirements.get("allowed_approvals_reviewers") != ["user"]:
        findings.append("the only allowed approvals reviewer must be 'user'")
    sandbox_modes = requirements.get("allowed_sandbox_modes", [])
    if not sandbox_modes or not set(sandbox_modes).issubset(ALLOWED_SANDBOX_MODES):
        findings.append("sandbox modes must exclude unrestricted full access")
    search_modes = requirements.get("allowed_web_search_modes", [])
    if not search_modes or not set(search_modes).issubset(ALLOWED_WEB_SEARCH_MODES):
        findings.append("web search must be restricted to disabled or cached modes")
    if requirements.get("default_permissions") != PROFILE_NAME:
        findings.append("the managed default must select the regulated profile")
    if requirements.get("allowed_permission_profiles") != {
        ":read-only": True,
        PROFILE_NAME: True,
    }:
        findings.append("only read-only and regulated permission profiles may be used")
    if requirements.get("allow_managed_hooks_only") is not True:
        findings.append("only enterprise-managed hooks may be enabled")
    if requirements.get("allow_appshots") is not False:
        findings.append("Appshots must be disabled")
    if requirements.get("mcp_servers") != {}:
        findings.append("an explicit empty MCP allowlist must deny MCP servers")

    profile = requirements.get("permissions", {}).get(PROFILE_NAME, {})
    filesystem = profile.get("filesystem", {})
    workspace = filesystem.get(":workspace_roots", {})

    if profile.get("extends") != ":workspace":
        findings.append(
            "the general baseline must extend the standard workspace profile"
        )
    if filesystem.get(":root") == "write":
        findings.append("the regulated profile must not grant root filesystem writes")
    if not all(
        workspace.get(pattern) == "deny" for pattern in REQUIRED_SECRET_PATTERNS
    ):
        findings.append("all secret-bearing workspace patterns must be denied")
    if (
        not isinstance(filesystem.get("glob_scan_max_depth"), int)
        or filesystem["glob_scan_max_depth"] < 1
    ):
        findings.append("recursive deny patterns require a positive glob scan depth")
    if profile.get("network", {}).get("enabled") is not False:
        findings.append("sandboxed command-network access must be disabled")

    features = requirements.get("features", {})
    if any(features.get(name) is not False for name in REQUIRED_DISABLED_FEATURES):
        findings.append("all high-risk optional features must be explicitly disabled")

    rules = requirements.get("rules", {}).get("prefix_rules", [])
    if not rules:
        findings.append("managed execution rules must not be empty")
    decisions = {rule.get("decision") for rule in rules}
    if "prompt" not in decisions or "forbidden" not in decisions:
        findings.append(
            "execution rules must include human review and forbidden actions"
        )
    for rule in rules:
        if rule.get("decision") not in {"prompt", "forbidden"}:
            findings.append("execution rules must either prompt or forbid the action")
        if not rule.get("justification"):
            findings.append("every managed execution rule needs a justification")
        for token in rule.get("pattern", []):
            if ("token" in token) == ("any_of" in token):
                findings.append("rule tokens must define exactly one token matcher")

    windows = requirements.get("windows")
    if platform == "windows":
        if not windows or windows.get("allowed_sandbox_implementations") != [
            "elevated"
        ]:
            findings.append("Windows requirements must enforce the elevated sandbox")
        if windows and set(windows) != {"allowed_sandbox_implementations"}:
            findings.append("Windows requirements contain unsupported 0.138.0 keys")
    elif windows:
        findings.append("non-Windows requirements must not contain Windows-only policy")

    return findings


def validate_config(
    config: dict[str, Any], requirements: dict[str, Any], platform: str
) -> list[str]:
    """Return mismatches between client defaults and enforced requirements."""

    findings: list[str] = []
    if config.get("approval_policy") not in requirements.get(
        "allowed_approval_policies", []
    ):
        findings.append("client approval policy must match enterprise requirements")
    if config.get("approvals_reviewer") != "user":
        findings.append("client approvals reviewer must remain 'user'")
    if config.get("default_permissions") != requirements.get("default_permissions"):
        findings.append("client and enterprise permission profiles must match")
    if config.get("web_search") not in requirements.get("allowed_web_search_modes", []):
        findings.append("client web search must match the allowed enterprise modes")
    if config.get("allow_login_shell") is not False:
        findings.append("login shell execution must be disabled")
    if config.get("forced_login_method") != "chatgpt":
        findings.append("the client must use the enterprise ChatGPT login flow")
    if config.get("cli_auth_credentials_store") != "keyring":
        findings.append("CLI credentials must use the operating-system keyring")
    if config.get("mcp_oauth_credentials_store") != "keyring":
        findings.append("MCP OAuth credentials must use the operating-system keyring")

    apps = config.get("apps", {}).get("_default", {})
    if any(
        apps.get(setting) is not False
        for setting in ("enabled", "destructive_enabled", "open_world_enabled")
    ):
        findings.append("apps and destructive or open-world app tools must be disabled")
    if config.get("analytics", {}).get("enabled") is not False:
        findings.append("optional product analytics must be disabled")
    if config.get("feedback", {}).get("enabled") is not True:
        findings.append(
            "feedback must stay available for current-session investigation"
        )
    if config.get("history", {}).get("persistence") != "none":
        findings.append("local history persistence must be disabled")
    if config.get("otel", {}).get("log_user_prompt") is not False:
        findings.append("OpenTelemetry must not export raw user prompts")
    if not config.get("otel", {}).get("environment"):
        findings.append("OpenTelemetry events need an environment classification")
    if config.get("sandbox_workspace_write", {}).get("network_access") is not False:
        findings.append("workspace sandbox defaults must disable command networking")

    environment = config.get("shell_environment_policy", {})
    if environment.get("inherit") != "core":
        findings.append("shell subprocesses must inherit only core environment values")
    if environment.get("ignore_default_excludes") is not False:
        findings.append(
            "automatic secret environment-variable exclusions must stay active"
        )
    if "filters" in environment:
        findings.append("shell_environment_policy.filters is unsupported in 0.138.0")

    windows = config.get("windows")
    if platform == "windows":
        if not windows or windows.get("sandbox") != "elevated":
            findings.append("Windows clients must select the elevated sandbox")
        if not windows or windows.get("sandbox_private_desktop") is not True:
            findings.append("Windows sandbox processes must use a private desktop")
    elif windows:
        findings.append("non-Windows client defaults must not include Windows settings")

    return findings


def validate_schema(
    config: dict[str, Any], requirements: dict[str, Any], schema_path: Path
) -> None:
    """Validate client defaults and managed profiles against a release schema."""

    try:
        import jsonschema
    except ImportError as error:
        raise RuntimeError(
            "Install jsonschema before using --schema: python -m pip install jsonschema"
        ) from error

    with schema_path.open(encoding="utf-8") as source:
        schema = json.load(source)
    jsonschema.validate(config, schema)
    jsonschema.validate(
        requirements["permissions"][PROFILE_NAME],
        {
            "$ref": "#/definitions/PermissionProfileToml",
            "definitions": schema["definitions"],
        },
    )


def main() -> int:
    """Validate all complete blueprint pairs without contacting external services."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--schema",
        type=Path,
        help="Optional Codex config.schema.json for the deployed client version.",
    )
    parser.add_argument(
        "--platform",
        choices=("general", "macos", "windows"),
        default="general",
        help="Validate optional platform-specific settings added to the shared files.",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        help="Optional path to a deployed enterprise requirements.toml file.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional path to a deployed client config.toml file.",
    )
    options = parser.parse_args()
    directory = Path(__file__).resolve().parent
    failures = 0

    for blueprint in BLUEPRINTS:
        requirements_path = options.requirements or directory / blueprint.requirements
        config_path = options.config or directory / blueprint.config
        requirements = load_toml(requirements_path)
        config = load_toml(config_path)
        platform = options.platform
        findings = validate_requirements(requirements, platform)
        findings.extend(validate_config(config, requirements, platform))

        if options.schema:
            try:
                validate_schema(config, requirements, options.schema)
            except Exception as error:
                findings.append(f"release schema validation failed: {error}")

        if findings:
            failures += 1
            print(f"FAIL {platform}")
            for finding in findings:
                print(f"  - {finding}")
            continue

        print(f"PASS {platform}: {requirements_path.name}, {config_path.name}")

    if failures:
        print(f"Validation failed for {failures} blueprint pair(s).")
        return 1

    print(
        f"Validated {len(BLUEPRINTS)} regulated-industry blueprint pair "
        f"for Codex {MINIMUM_CODEX_VERSION} or later."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
