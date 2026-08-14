"""Regression tests for the regulated-industry Codex configuration blueprint."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validate_blueprints import BLUEPRINTS
from validate_blueprints import PROFILE_NAME
from validate_blueprints import READ_ONLY_PROFILE_NAME
from validate_blueprints import load_toml
from validate_blueprints import validate_config
from validate_blueprints import validate_model_catalog
from validate_blueprints import validate_requirements


BLUEPRINT_DIRECTORY = Path(__file__).resolve().parent


class RegulatedBlueprintTests(unittest.TestCase):
    """Keep every platform on the same supervised enterprise-governance baseline."""

    def setUp(self) -> None:
        self.requirements = load_toml(BLUEPRINT_DIRECTORY / "requirements.toml")
        self.config = load_toml(BLUEPRINT_DIRECTORY / "config.toml")

    def windows_requirements(self) -> dict:
        """Add the documented optional Windows requirement to the shared policy."""

        requirements = copy.deepcopy(self.requirements)
        requirements["windows"] = {
            "allowed_sandbox_implementations": ["elevated"],
            "sandbox_private_desktop": True,
        }
        return requirements

    def windows_config(self) -> dict:
        """Add the documented optional Windows client settings to shared defaults."""

        config = copy.deepcopy(self.config)
        config["windows"] = {"sandbox": "elevated", "sandbox_private_desktop": True}
        return config

    def approved_model_catalog(self) -> dict:
        """Create a small catalog with one approved model and reasoning level."""

        return {
            "models": [
                {
                    "slug": "gpt-5.6-luna",
                    "default_reasoning_level": "medium",
                    "supported_reasoning_levels": [
                        {"effort": "low", "description": "Faster responses"},
                        {"effort": "medium", "description": "Balanced responses"},
                    ],
                }
            ]
        }

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

    def test_optional_windows_settings_are_valid(self) -> None:
        requirements = self.windows_requirements()
        config = self.windows_config()
        self.assertEqual(validate_requirements(requirements, "windows"), [])
        self.assertEqual(validate_config(config, requirements, "windows"), [])

    def test_validator_accepts_separate_deployed_windows_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            deployed = Path(directory)
            requirements_path = deployed / "requirements.toml"
            config_path = deployed / "config.toml"
            requirements_path.write_text(
                (BLUEPRINT_DIRECTORY / "requirements.toml").read_text()
                + '\n[windows]\nallowed_sandbox_implementations = ["elevated"]\n'
                + "sandbox_private_desktop = true\n"
            )
            config_path.write_text(
                (BLUEPRINT_DIRECTORY / "config.toml").read_text()
                + '\n[windows]\nsandbox = "elevated"\nsandbox_private_desktop = true\n'
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(BLUEPRINT_DIRECTORY / "validate_blueprints.py"),
                    "--platform",
                    "windows",
                    "--requirements",
                    str(requirements_path),
                    "--config",
                    str(config_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS windows: requirements.toml, config.toml", result.stdout)

    def test_managed_model_catalog_is_valid_on_latest_release(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["model_catalog_json"] = "/etc/codex/approved-models.json"
        self.assertEqual(validate_requirements(requirements, "general"), [])

    def test_windows_managed_model_catalog_accepts_device_path(self) -> None:
        requirements = self.windows_requirements()
        requirements["model_catalog_json"] = (
            r"C:\ProgramData\OpenAI\Codex\approved-models.json"
        )
        self.assertEqual(validate_requirements(requirements, "windows"), [])

    def test_remote_managed_model_catalog_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["model_catalog_json"] = "https://example.com/approved-models.json"
        self.assertTrue(
            any(
                "absolute local path" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_network_share_model_catalog_is_rejected(self) -> None:
        requirements = self.windows_requirements()
        requirements["model_catalog_json"] = r"\\server\share\approved-models.json"
        self.assertTrue(
            any(
                "absolute local path" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_client_model_catalog_must_match_managed_catalog(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["model_catalog_json"] = "/etc/codex/approved-models.json"
        config = copy.deepcopy(self.config)
        config["model_catalog_json"] = "/etc/codex/other-models.json"
        self.assertTrue(
            any(
                "match the managed requirement" in finding
                for finding in validate_config(config, requirements, "general")
            )
        )

    def test_remote_client_model_catalog_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["model_catalog_json"] = "https://example.com/approved-models.json"
        self.assertTrue(
            any(
                "absolute local path" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_approved_model_catalog_matches_client_defaults(self) -> None:
        config = copy.deepcopy(self.config)
        config["model"] = "gpt-5.6-luna"
        self.assertEqual(
            validate_model_catalog(self.approved_model_catalog(), config), []
        )

    def test_empty_approved_model_catalog_is_rejected(self) -> None:
        self.assertTrue(
            any(
                "at least one model" in finding
                for finding in validate_model_catalog({"models": []}, self.config)
            )
        )

    def test_unapproved_default_model_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["model"] = "unapproved-model"
        self.assertTrue(
            any(
                "default model must appear" in finding
                for finding in validate_model_catalog(
                    self.approved_model_catalog(), config
                )
            )
        )

    def test_unapproved_reasoning_effort_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["model"] = "gpt-5.6-luna"
        config["model_reasoning_effort"] = "xhigh"
        self.assertTrue(
            any(
                "reasoning effort must be approved" in finding
                for finding in validate_model_catalog(
                    self.approved_model_catalog(), config
                )
            )
        )

    def test_unapproved_catalog_reasoning_default_is_rejected(self) -> None:
        catalog = self.approved_model_catalog()
        catalog["models"][0]["default_reasoning_level"] = "xhigh"
        self.assertTrue(
            any(
                "approved default reasoning level" in finding
                for finding in validate_model_catalog(catalog, self.config)
            )
        )

    def test_validator_accepts_managed_model_catalog_deployment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            deployed = Path(directory)
            requirements_path = deployed / "requirements.toml"
            config_path = deployed / "config.toml"
            catalog_path = deployed / "approved-models.json"
            catalog_path.write_text(json.dumps(self.approved_model_catalog()))
            requirements_path.write_text(
                f'model_catalog_json = "{catalog_path}"\n'
                + (BLUEPRINT_DIRECTORY / "requirements.toml").read_text()
            )
            config_path.write_text(
                'model = "gpt-5.6-luna"\n'
                + f'model_catalog_json = "{catalog_path}"\n'
                + (BLUEPRINT_DIRECTORY / "config.toml").read_text()
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(BLUEPRINT_DIRECTORY / "validate_blueprints.py"),
                    "--requirements",
                    str(requirements_path),
                    "--config",
                    str(config_path),
                    "--model-catalog",
                    str(catalog_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("for the latest Codex release", result.stdout)

    def test_root_filesystem_writes_are_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][PROFILE_NAME]["filesystem"][":root"] = "write"
        self.assertTrue(
            any(
                "root filesystem writes" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_unapproved_base_permission_profile_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][PROFILE_NAME]["extends"] = ":danger-full-access"
        self.assertTrue(
            any(
                "standard workspace profile" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_unsupervised_approval_policy_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_approval_policies"].append("never")
        self.assertTrue(
            any(
                "supervised human review" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_automatic_approval_reviewer_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_approvals_reviewers"].append("auto_review")
        self.assertTrue(
            any(
                "approvals reviewer" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_full_access_sandbox_mode_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_sandbox_modes"] = ["danger-full-access"]
        self.assertTrue(
            any(
                "unrestricted full access" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_live_web_search_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_web_search_modes"].append("live")
        self.assertTrue(
            any(
                "disabled or cached" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_command_network_access_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][PROFILE_NAME]["network"]["enabled"] = True
        self.assertTrue(
            any(
                "command-network access" in finding
                for finding in validate_requirements(requirements, "general")
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
                for finding in validate_requirements(requirements, "general")
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
                for finding in validate_requirements(requirements, "general")
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
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_unrestricted_mcp_servers_are_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        del requirements["mcp_servers"]
        self.assertTrue(
            any(
                "MCP allowlist" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_windows_sandbox_fallback_is_rejected(self) -> None:
        requirements = self.windows_requirements()
        requirements["windows"]["allowed_sandbox_implementations"].append("unelevated")
        self.assertTrue(
            any(
                "elevated sandbox" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_missing_windows_private_desktop_requirement_is_rejected(self) -> None:
        requirements = self.windows_requirements()
        requirements["windows"]["sandbox_private_desktop"] = False
        self.assertTrue(
            any(
                "enforce a private desktop" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_automatic_execution_rule_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["rules"]["prefix_rules"][0]["decision"] = "allow"
        self.assertTrue(
            any(
                "prompt or forbid" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_missing_production_change_prohibition_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        for rule in requirements["rules"]["prefix_rules"]:
            rule["decision"] = "prompt"
        self.assertTrue(
            any(
                "human review and forbidden actions" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_missing_tunnel_prohibition_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["rules"]["prefix_rules"] = [
            rule
            for rule in requirements["rules"]["prefix_rules"]
            if not any(
                "ngrok" in matcher.get("any_of", []) for matcher in rule["pattern"]
            )
        ]
        self.assertTrue(
            any(
                "high-risk command must be forbidden: ngrok" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_missing_privilege_escalation_prohibition_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["rules"]["prefix_rules"] = [
            rule
            for rule in requirements["rules"]["prefix_rules"]
            if not any(
                "sudo" in matcher.get("any_of", []) for matcher in rule["pattern"]
            )
        ]
        self.assertTrue(
            any(
                "high-risk command must be forbidden: sudo" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_approval_policy_mismatch_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["approval_policy"] = "never"
        self.assertTrue(
            any(
                "approval policy" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_personal_authentication_mode_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["forced_login_method"] = "api"
        self.assertTrue(
            any(
                "enterprise ChatGPT login" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_file_backed_credentials_are_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["cli_auth_credentials_store"] = "file"
        self.assertTrue(
            any(
                "operating-system keyring" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_client_live_search_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["web_search"] = "live"
        self.assertTrue(
            any(
                "allowed enterprise modes" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_enabled_optional_analytics_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["analytics"]["enabled"] = True
        self.assertTrue(
            any(
                "optional product analytics" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_raw_prompt_telemetry_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["otel"]["log_user_prompt"] = True
        self.assertTrue(
            any(
                "raw user prompts" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_legacy_workspace_sandbox_settings_are_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["sandbox_workspace_write"] = {"network_access": False}
        self.assertTrue(
            any(
                "legacy sandbox settings" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_unelevated_windows_client_is_rejected(self) -> None:
        config = self.windows_config()
        config["windows"]["sandbox"] = "unelevated"
        requirements = self.windows_requirements()
        self.assertTrue(
            any(
                "elevated sandbox" in finding
                for finding in validate_config(config, requirements, "windows")
            )
        )

    def test_windows_private_desktop_disable_is_rejected(self) -> None:
        config = self.windows_config()
        config["windows"]["sandbox_private_desktop"] = False
        requirements = self.windows_requirements()
        self.assertTrue(
            any(
                "private desktop" in finding
                for finding in validate_config(config, requirements, "windows")
            )
        )

    def test_feedback_disable_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["feedback"]["enabled"] = False
        self.assertTrue(
            any(
                "feedback must stay available" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_mixed_shell_filter_formats_are_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["shell_environment_policy"]["filters"] = {"*PASSWORD*": "exclude"}
        self.assertTrue(
            any(
                "must not mix keyed filters" in finding
                for finding in validate_config(config, self.requirements, "general")
            )
        )

    def test_non_enterprise_managed_login_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_login_methods"] = ["api"]
        self.assertTrue(
            any(
                "only enterprise ChatGPT" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_unverified_workspace_identifier_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_chatgpt_workspaces"] = ["not-a-workspace-id"]
        self.assertTrue(
            any(
                "valid UUIDs" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_approved_workspace_identifier_is_accepted(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_chatgpt_workspaces"] = [
            "2b14bd54-a607-4c40-a0bd-90c3269a7d55"
        ]
        self.assertEqual(validate_requirements(requirements, "general"), [])

    def test_client_workspace_must_match_managed_allowlist(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allowed_chatgpt_workspaces"] = [
            "2b14bd54-a607-4c40-a0bd-90c3269a7d55"
        ]
        config = copy.deepcopy(self.config)
        config["forced_chatgpt_workspace_id"] = "1c276944-966e-451c-8563-09eb1890b937"
        self.assertTrue(
            any(
                "managed workspace allowlist" in finding
                for finding in validate_config(config, requirements, "general")
            )
        )

    def test_enabled_managed_login_shell_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allow_login_shell"] = True
        self.assertTrue(
            any(
                "disable login shells" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_enabled_remote_control_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["allow_remote_control"] = True
        self.assertTrue(
            any(
                "remote control" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_unrestricted_plugin_servers_are_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        del requirements["plugins"]
        self.assertTrue(
            any(
                "plugin allowlist" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_missing_global_credential_denial_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"]["filesystem"]["deny_read"].remove(
            "~/.aws/credentials"
        )
        self.assertTrue(
            any(
                "global deny-read" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_non_read_only_inspection_profile_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][READ_ONLY_PROFILE_NAME]["extends"] = ":workspace"
        self.assertTrue(
            any(
                "inspection profile must extend" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_network_enabled_inspection_profile_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][READ_ONLY_PROFILE_NAME]["network"]["enabled"] = True
        self.assertTrue(
            any(
                "inspection profile must disable" in finding
                for finding in validate_requirements(requirements, "general")
            )
        )

    def test_reviewed_windows_fallback_requires_explicit_opt_in(self) -> None:
        requirements = self.windows_requirements()
        requirements["windows"]["allowed_sandbox_implementations"] = ["unelevated"]
        config = self.windows_config()
        config["windows"]["sandbox"] = "unelevated"
        self.assertTrue(validate_requirements(requirements, "windows"))
        self.assertTrue(validate_config(config, requirements, "windows"))
        self.assertEqual(validate_requirements(requirements, "windows", True), [])
        self.assertEqual(validate_config(config, requirements, "windows", True), [])

    def test_unknown_windows_requirement_is_rejected(self) -> None:
        requirements = self.windows_requirements()
        requirements["windows"]["unknown_setting"] = True
        self.assertTrue(
            any(
                "unsupported managed settings" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )


if __name__ == "__main__":
    unittest.main()
