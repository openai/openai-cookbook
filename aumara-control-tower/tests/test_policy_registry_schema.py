from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import unittest


CONTROL_TOWER = pathlib.Path(__file__).resolve().parents[1]
POLICY_ROOT = CONTROL_TOWER / "policies"
SCRIPTS = CONTROL_TOWER / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_policy_registry import (  # noqa: E402
    RegistryValidationError,
    validate_registry,
)


class PolicyRegistrySchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name) / "policies"
        shutil.copytree(POLICY_ROOT, self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _read(self, filename: str) -> dict:
        return json.loads((self.root / filename).read_text(encoding="utf-8"))

    def _write(self, filename: str, value: dict) -> None:
        (self.root / filename).write_text(
            json.dumps(value, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_registry_is_valid_and_separate(self) -> None:
        result = validate_registry(self.root)
        self.assertEqual(result["policy_version"], "2026.07.27.1")
        self.assertEqual(result["registry_count"], 3)

        index = self._read("registry.yaml")
        self.assertEqual(
            index["registries"],
            {
                "shared": "shared.yaml",
                "elcid": "elcid.yaml",
                "aumara": "aumara.yaml",
            },
        )

    def test_schema_rejects_missing_required_field(self) -> None:
        document = self._read("elcid.yaml")
        del document["policies"][0]["rule"]
        self._write("elcid.yaml", document)
        with self.assertRaisesRegex(RegistryValidationError, "missing rule"):
            validate_registry(self.root)

    def test_version_drift_is_rejected(self) -> None:
        document = self._read("aumara.yaml")
        document["policy_version"] = "2026.07.27.2"
        self._write("aumara.yaml", document)
        with self.assertRaisesRegex(RegistryValidationError, "version drift"):
            validate_registry(self.root)

    def test_cross_property_policy_is_rejected(self) -> None:
        document = self._read("aumara.yaml")
        document["policies"][0]["property"] = "elcid"
        self._write("aumara.yaml", document)
        with self.assertRaisesRegex(RegistryValidationError, "property mismatch"):
            validate_registry(self.root)

    def test_cross_property_template_is_rejected(self) -> None:
        document = self._read("elcid.yaml")
        document["policies"][0]["response_template_ids"] = [
            "aumara.unapproved-template"
        ]
        self._write("elcid.yaml", document)
        with self.assertRaisesRegex(RegistryValidationError, "crosses product"):
            validate_registry(self.root)

    def test_pending_policy_cannot_enable_automation(self) -> None:
        document = self._read("elcid.yaml")
        document["policies"][0]["allowed_beds24_action"] = [
            "record_guest_request"
        ]
        self._write("elcid.yaml", document)
        with self.assertRaisesRegex(RegistryValidationError, "enables automation"):
            validate_registry(self.root)

    def test_private_operational_key_is_rejected(self) -> None:
        document = self._read("aumara.yaml")
        document["policies"][0]["property_id"] = "runtime-value"
        self._write("aumara.yaml", document)
        with self.assertRaisesRegex(RegistryValidationError, "private-data key"):
            validate_registry(self.root)

    def test_private_operational_value_is_rejected(self) -> None:
        document = self._read("elcid.yaml")
        document["policies"][0]["rule"] = "Resolve value " + ("123" * 3) + "."
        self._write("elcid.yaml", document)
        with self.assertRaisesRegex(RegistryValidationError, "operational value"):
            validate_registry(self.root)

    def test_multilingual_templates_are_allowed_for_verified_policy(self) -> None:
        document = self._read("elcid.yaml")
        policy = next(
            item
            for item in document["policies"]
            if item["policy_id"] == "elcid.non-smoking-room-reply-fragment"
        )
        self.assertTrue(policy["allowed_auto_reply"])
        self.assertIn("en", policy["response_templates"])
        validate_registry(self.root)


if __name__ == "__main__":
    unittest.main()
