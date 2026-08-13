"""Regression tests for the regulated-industry Codex configuration blueprint."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path

from validate_blueprints import BLUEPRINTS
from validate_blueprints import PROFILE_NAME
from validate_blueprints import load_toml
from validate_blueprints import validate_config
from validate_blueprints import validate_requirements


BLUEPRINT_DIRECTORY = Path(__file__).resolve().parent


class RegulatedBlueprintTests(unittest.TestCase):
    """Keep every platform on the same supervised enterprise-governance baseline."""

    def setUp(self) -> None:
        self.requirements = load_toml(BLUEPRINT_DIRECTORY / "requirements.windows.toml")
        self.config = load_toml(BLUEPRINT_DIRECTORY / "config.windows.toml")

    def test_all_reference_blueprints_are_valid(self) -> None:
        for blueprint in BLUEPRINTS:
            with self.subTest(platform=blueprint.platform):
                requirements = load_toml(BLUEPRINT_DIRECTORY / blueprint.requirements)
                config = load_toml(BLUEPRINT_DIRECTORY / blueprint.config)
                self.assertEqual(
                    validate_requirements(requirements, blueprint.platform), []
                )
                self.assertEqual(
                    validate_config(config, requirements, blueprint.platform), []
                )

    def test_root_filesystem_writes_are_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][PROFILE_NAME]["filesystem"][":root"] = "write"
        self.assertTrue(
            any(
                "root filesystem writes" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_unapproved_base_permission_profile_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][PROFILE_NAME]["extends"] = ":danger-full-access"
        self.assertTrue(
            any(
                "standard workspace profile" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_unsupervised_approval_policy_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_approval_policies"].append("never")
        self.assertTrue(
            any(
                "supervised human review" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_automatic_approval_reviewer_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_approvals_reviewers"].append("auto_review")
        self.assertTrue(
            any(
                "approvals reviewer" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_full_access_sandbox_mode_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_sandbox_modes"].append("danger-full-access")
        self.assertTrue(
            any(
                "unrestricted full access" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_live_web_search_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_web_search_modes"].append("live")
        self.assertTrue(
            any(
                "disabled or cached" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_command_network_access_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][PROFILE_NAME]["network"]["enabled"] = True
        self.assertTrue(
            any(
                "command-network access" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_missing_secret_deny_pattern_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        del requirements["permissions"][PROFILE_NAME]["filesystem"][":workspace_roots"][
            "**/*.pem"
        ]
        self.assertTrue(
            any(
                "secret-bearing" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_missing_known_future_secret_path_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        del requirements["permissions"][PROFILE_NAME]["filesystem"][":workspace_roots"][
            ".env.local"
        ]
        self.assertTrue(
            any(
                "secret-bearing" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_unbounded_recursive_secret_scan_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        del requirements["permissions"][PROFILE_NAME]["filesystem"][
            "glob_scan_max_depth"
        ]
        self.assertTrue(
            any(
                "positive glob scan depth" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_unrestricted_mcp_servers_are_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        del requirements["mcp_servers"]
        self.assertTrue(
            any(
                "MCP allowlist" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_windows_sandbox_fallback_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["windows"]["allowed_sandbox_implementations"].append("unelevated")
        self.assertTrue(
            any(
                "elevated sandbox" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_unsupported_windows_requirement_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["windows"]["sandbox_private_desktop"] = True
        self.assertTrue(
            any(
                "unsupported 0.138.0" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_automatic_execution_rule_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["rules"]["prefix_rules"][0]["decision"] = "allow"
        self.assertTrue(
            any(
                "prompt or forbid" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_missing_production_change_prohibition_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        for rule in requirements["rules"]["prefix_rules"]:
            rule["decision"] = "prompt"
        self.assertTrue(
            any(
                "human review and forbidden actions" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_approval_policy_mismatch_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["approval_policy"] = "never"
        self.assertTrue(
            any(
                "approval policy" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_personal_authentication_mode_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["forced_login_method"] = "api"
        self.assertTrue(
            any(
                "enterprise ChatGPT login" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_file_backed_credentials_are_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["cli_auth_credentials_store"] = "file"
        self.assertTrue(
            any(
                "operating-system keyring" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_client_live_search_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["web_search"] = "live"
        self.assertTrue(
            any(
                "allowed enterprise modes" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_enabled_optional_analytics_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["analytics"]["enabled"] = True
        self.assertTrue(
            any(
                "optional product analytics" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_raw_prompt_telemetry_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["otel"]["log_user_prompt"] = True
        self.assertTrue(
            any(
                "raw user prompts" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_default_workspace_network_access_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["sandbox_workspace_write"]["network_access"] = True
        self.assertTrue(
            any(
                "disable command networking" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_unelevated_windows_client_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["windows"]["sandbox"] = "unelevated"
        self.assertTrue(
            any(
                "elevated sandbox" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_windows_private_desktop_disable_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["windows"]["sandbox_private_desktop"] = False
        self.assertTrue(
            any(
                "private desktop" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_feedback_disable_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["feedback"]["enabled"] = False
        self.assertTrue(
            any(
                "feedback must stay available" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )

    def test_unsupported_shell_filter_format_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["shell_environment_policy"]["filters"] = {"*PASSWORD*": "exclude"}
        self.assertTrue(
            any(
                "unsupported in 0.138.0" in finding
                for finding in validate_config(config, self.requirements, "windows")
            )
        )


if __name__ == "__main__":
    unittest.main()
