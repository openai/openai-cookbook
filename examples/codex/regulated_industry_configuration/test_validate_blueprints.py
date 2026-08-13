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
    """Keep every supported platform on the same least-privilege baseline."""

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

    def test_broad_filesystem_reads_are_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][PROFILE_NAME]["filesystem"][":root"] = "read"
        self.assertTrue(
            any(
                "broad filesystem" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_inheriting_the_workspace_profile_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["permissions"][PROFILE_NAME]["extends"] = ":workspace"
        self.assertTrue(
            any(
                "inherit a broader profile" in finding
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

    def test_interactive_command_exception_is_rejected(self) -> None:
        requirements = copy.deepcopy(self.requirements)
        requirements["rules"]["prefix_rules"][0]["decision"] = "prompt"
        self.assertTrue(
            any(
                "forbidden execution rules" in finding
                for finding in validate_requirements(requirements, "windows")
            )
        )

    def test_approval_policy_mismatch_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        config["approval_policy"] = "on-request"
        self.assertTrue(
            any(
                "approval policy" in finding
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
