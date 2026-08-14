"""Validate regulated-industry Codex configuration blueprints.

The default checks use only the current Python standard library. Pass ``--schema``
to validate client configuration files and managed permission profiles against a
downloaded Codex JSON schema; that optional mode requires ``jsonschema``.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import UUID

import tomllib


PROFILE_NAME = "regulated_workspace"
READ_ONLY_PROFILE_NAME = "regulated_read_only"
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
REQUIRED_GLOBAL_SECRET_PATHS = frozenset(
    {
        "~/.ssh/id_rsa",
        "~/.ssh/id_ed25519",
        "~/.aws/credentials",
        "~/.kube/config",
        "~/.docker/config.json",
        "~/.npmrc",
        "~/.netrc",
        "/**/*.pem",
        "/**/*.key",
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
        "plugin_sharing",
        "remote_control",
        "remote_plugin",
        "skill_mcp_dependency_install",
    }
)
REQUIRED_FORBIDDEN_COMMANDS = (
    ("ngrok",),
    ("cloudflared", "tunnel"),
    ("ssh", "-R"),
    ("sudo",),
    ("git", "reset", "--hard"),
    ("kubectl", "port-forward"),
)
SUPPORTED_REQUIREMENT_KEYS = frozenset(
    {
        "allow_appshots",
        "allow_login_shell",
        "allow_managed_hooks_only",
        "allow_remote_control",
        "allowed_approval_policies",
        "allowed_approvals_reviewers",
        "allowed_chatgpt_workspaces",
        "allowed_login_methods",
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
        "model_catalog_json",
        "models",
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


def is_absolute_local_path(value: Any) -> bool:
    """Accept absolute device paths and reject remote URLs or network shares."""

    if not isinstance(value, str) or not value or "://" in value:
        return False
    if value.startswith(("//", "\\\\")):
        return False
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def rule_matches_command(rule: dict[str, Any], command: tuple[str, ...]) -> bool:
    """Match the cookbook's exact-token and any-of command prefixes."""

    pattern = rule.get("pattern", [])
    if not isinstance(pattern, list) or len(pattern) > len(command):
        return False
    for matcher, argument in zip(pattern, command, strict=False):
        if not isinstance(matcher, dict):
            return False
        if "token" in matcher and matcher["token"] != argument:
            return False
        if "any_of" in matcher and argument not in matcher["any_of"]:
            return False
        if ("token" in matcher) == ("any_of" in matcher):
            return False
    return bool(pattern)


def validate_requirements(
    requirements: dict[str, Any],
    platform: str,
    allow_windows_fallback: bool = False,
) -> list[str]:
    """Return security or compatibility findings for one requirements file."""

    findings: list[str] = []
    unsupported = sorted(set(requirements) - SUPPORTED_REQUIREMENT_KEYS)
    if unsupported:
        findings.append(f"unsupported managed requirement keys: {unsupported}")

    model_catalog = requirements.get("model_catalog_json")
    if model_catalog is not None and not is_absolute_local_path(model_catalog):
        findings.append("managed model catalogs must use an absolute local path")

    if requirements.get("allowed_login_methods") != ["chatgpt"]:
        findings.append("managed login methods must allow only enterprise ChatGPT")
    workspace_ids = requirements.get("allowed_chatgpt_workspaces")
    if workspace_ids is not None:
        if not isinstance(workspace_ids, list) or not workspace_ids:
            findings.append(
                "managed workspace restrictions need verified workspace IDs"
            )
        else:
            for workspace_id in workspace_ids:
                try:
                    UUID(workspace_id)
                except (AttributeError, TypeError, ValueError):
                    findings.append("managed workspace restrictions need valid UUIDs")
                    break

    policies = requirements.get("allowed_approval_policies", [])
    if not policies or not set(policies).issubset(ALLOWED_APPROVAL_POLICIES):
        findings.append("approval policies must require supervised human review")
    if requirements.get("allowed_approvals_reviewers") != ["user"]:
        findings.append("the only allowed approvals reviewer must be 'user'")
    sandbox_modes = requirements.get("allowed_sandbox_modes")
    if sandbox_modes is not None and (
        not sandbox_modes or not set(sandbox_modes).issubset(ALLOWED_SANDBOX_MODES)
    ):
        findings.append("sandbox modes must exclude unrestricted full access")
    search_modes = requirements.get("allowed_web_search_modes", [])
    if not search_modes or not set(search_modes).issubset(ALLOWED_WEB_SEARCH_MODES):
        findings.append("web search must be restricted to disabled or cached modes")
    if requirements.get("default_permissions") != PROFILE_NAME:
        findings.append("the managed default must select the regulated profile")
    if requirements.get("allowed_permission_profiles") != {
        ":read-only": True,
        READ_ONLY_PROFILE_NAME: True,
        PROFILE_NAME: True,
    }:
        findings.append("only approved read-only and regulated profiles may be used")
    if requirements.get("allow_login_shell") is not False:
        findings.append("enterprise requirements must disable login shells")
    if requirements.get("allow_managed_hooks_only") is not True:
        findings.append("only enterprise-managed hooks may be enabled")
    if requirements.get("allow_appshots") is not False:
        findings.append("Appshots must be disabled")
    if requirements.get("allow_remote_control") is not False:
        findings.append(
            "device remote control must be disabled by managed requirements"
        )
    if requirements.get("mcp_servers") != {}:
        findings.append("an explicit empty MCP allowlist must deny MCP servers")
    if requirements.get("plugins") != {}:
        findings.append(
            "an explicit empty plugin allowlist must deny plugin MCP servers"
        )

    permissions = requirements.get("permissions", {})
    readonly_profile = permissions.get(READ_ONLY_PROFILE_NAME, {})
    if readonly_profile.get("extends") != ":read-only":
        findings.append("the inspection profile must extend the read-only profile")
    if readonly_profile.get("network", {}).get("enabled") is not False:
        findings.append("the inspection profile must disable command networking")

    global_deny_read = permissions.get("filesystem", {}).get("deny_read", [])
    if not isinstance(
        global_deny_read, list
    ) or not REQUIRED_GLOBAL_SECRET_PATHS.issubset(global_deny_read):
        findings.append(
            "global deny-read requirements must protect sensitive credentials"
        )

    profile = permissions.get(PROFILE_NAME, {})
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
    for command in REQUIRED_FORBIDDEN_COMMANDS:
        if not any(
            rule.get("decision") == "forbidden" and rule_matches_command(rule, command)
            for rule in rules
        ):
            findings.append(f"high-risk command must be forbidden: {' '.join(command)}")

    windows = requirements.get("windows")
    if platform == "windows":
        implementations = (
            windows.get("allowed_sandbox_implementations", []) if windows else []
        )
        valid_implementations = {"elevated", "unelevated"}
        if (
            not implementations
            or not set(implementations).issubset(valid_implementations)
            or (not allow_windows_fallback and implementations != ["elevated"])
        ):
            findings.append("Windows requirements must enforce the elevated sandbox")
        if not windows or windows.get("sandbox_private_desktop") is not True:
            findings.append("Windows requirements must enforce a private desktop")
        if windows and set(windows) - {
            "allowed_sandbox_implementations",
            "sandbox_private_desktop",
        }:
            findings.append("Windows requirements contain unsupported managed settings")
    elif windows:
        findings.append("non-Windows requirements must not contain Windows-only policy")

    return findings


def validate_config(
    config: dict[str, Any],
    requirements: dict[str, Any],
    platform: str,
    allow_windows_fallback: bool = False,
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
    if "sandbox_mode" in config or "sandbox_workspace_write" in config:
        findings.append(
            "permission profiles must not be combined with legacy sandbox settings"
        )
    if config.get("web_search") not in requirements.get("allowed_web_search_modes", []):
        findings.append("client web search must match the allowed enterprise modes")
    if config.get("allow_login_shell") is not False:
        findings.append("login shell execution must be disabled")
    if config.get("forced_login_method") != "chatgpt":
        findings.append("the client must use the enterprise ChatGPT login flow")
    workspace_ids = requirements.get("allowed_chatgpt_workspaces")
    configured_workspace = config.get("forced_chatgpt_workspace_id")
    if (
        workspace_ids
        and configured_workspace
        and configured_workspace not in workspace_ids
    ):
        findings.append(
            "the client workspace must match the managed workspace allowlist"
        )
    if config.get("cli_auth_credentials_store") != "keyring":
        findings.append("CLI credentials must use the operating-system keyring")
    if config.get("mcp_oauth_credentials_store") != "keyring":
        findings.append("MCP OAuth credentials must use the operating-system keyring")

    required_model_catalog = requirements.get("model_catalog_json")
    configured_model_catalog = config.get("model_catalog_json")
    if configured_model_catalog is not None and not is_absolute_local_path(
        configured_model_catalog
    ):
        findings.append("client model catalogs must use an absolute local path")
    if (
        required_model_catalog is not None
        and configured_model_catalog is not None
        and configured_model_catalog != required_model_catalog
    ):
        findings.append("client model catalog must match the managed requirement")

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
    environment = config.get("shell_environment_policy", {})
    if environment.get("inherit") != "core":
        findings.append("shell subprocesses must inherit only core environment values")
    if environment.get("ignore_default_excludes") is not False:
        findings.append(
            "automatic secret environment-variable exclusions must stay active"
        )
    if "filters" in environment and any(
        key in environment for key in ("exclude", "include_only")
    ):
        findings.append("shell filters must not mix keyed filters with legacy arrays")

    windows = config.get("windows")
    if platform == "windows":
        selected_sandbox = windows.get("sandbox") if windows else None
        allowed_sandboxes = requirements.get("windows", {}).get(
            "allowed_sandbox_implementations", []
        )
        if selected_sandbox not in allowed_sandboxes or (
            not allow_windows_fallback and selected_sandbox != "elevated"
        ):
            findings.append("Windows clients must select the elevated sandbox")
        if not windows or windows.get("sandbox_private_desktop") is not True:
            findings.append("Windows sandbox processes must use a private desktop")
    elif windows:
        findings.append("non-Windows client defaults must not include Windows settings")

    return findings


def validate_model_catalog(
    catalog: dict[str, Any], config: dict[str, Any]
) -> list[str]:
    """Validate approved model choices and supported reasoning defaults."""

    models = catalog.get("models")
    if not isinstance(models, list) or not models:
        return ["the approved model catalog must contain at least one model"]

    findings: list[str] = []
    models_by_slug: dict[str, dict[str, Any]] = {}
    for model in models:
        if not isinstance(model, dict) or not isinstance(model.get("slug"), str):
            findings.append("every approved model needs a valid model slug")
            continue

        slug = model["slug"]
        if not slug:
            findings.append("every approved model needs a valid model slug")
            continue
        if slug in models_by_slug:
            findings.append(f"the approved model catalog repeats model {slug!r}")
            continue
        models_by_slug[slug] = model

        reasoning_levels = model.get("supported_reasoning_levels")
        if not isinstance(reasoning_levels, list) or not reasoning_levels:
            findings.append(f"approved model {slug!r} needs supported reasoning levels")
            continue
        efforts = {
            level.get("effort")
            for level in reasoning_levels
            if isinstance(level, dict) and isinstance(level.get("effort"), str)
        }
        if len(efforts) != len(reasoning_levels):
            findings.append(f"approved model {slug!r} has invalid reasoning levels")
            continue
        if model.get("default_reasoning_level") not in efforts:
            findings.append(
                f"approved model {slug!r} needs an approved default reasoning level"
            )

    selected_model = config.get("model")
    if selected_model is None:
        return findings
    if selected_model not in models_by_slug:
        findings.append(
            "the configured default model must appear in the approved catalog"
        )
        return findings

    supported_levels = models_by_slug[selected_model].get(
        "supported_reasoning_levels", []
    )
    if not isinstance(supported_levels, list):
        return findings
    supported_efforts = {
        level.get("effort") for level in supported_levels if isinstance(level, dict)
    }
    if config.get("model_reasoning_effort") not in supported_efforts:
        findings.append(
            "the configured reasoning effort must be approved for the default model"
        )
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
    profile_schema = {
        "$ref": "#/definitions/PermissionProfileToml",
        "definitions": schema["definitions"],
    }
    for profile_name in (READ_ONLY_PROFILE_NAME, PROFILE_NAME):
        jsonschema.validate(requirements["permissions"][profile_name], profile_schema)


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
    parser.add_argument(
        "--allow-windows-fallback",
        action="store_true",
        help="Validate an explicitly reviewed unelevated Windows exception.",
    )
    parser.add_argument(
        "--model-catalog",
        type=Path,
        help="Optional approved model catalog to validate against client defaults.",
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
        findings = validate_requirements(
            requirements, platform, options.allow_windows_fallback
        )
        findings.extend(
            validate_config(
                config, requirements, platform, options.allow_windows_fallback
            )
        )

        if options.model_catalog:
            try:
                with options.model_catalog.open(encoding="utf-8") as source:
                    catalog = json.load(source)
                if not isinstance(catalog, dict):
                    raise ValueError("the model catalog root must be a JSON object")
                findings.extend(validate_model_catalog(catalog, config))
            except (OSError, ValueError) as error:
                findings.append(f"model catalog validation failed: {error}")

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

    print(f"Validated {len(BLUEPRINTS)} blueprint pair for the latest Codex release.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
