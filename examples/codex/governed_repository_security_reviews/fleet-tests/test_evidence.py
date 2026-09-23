from __future__ import annotations

import json
import stat
import unittest
from copy import deepcopy
from pathlib import Path

from support import approve_scope, pipeline, repository
from fleet_security import AuditLog, EvidenceError, EvidenceSealer, FindingRegistry
from fleet_security.evidence import SecureArtifactStore
from fleet_security.schema_validation import official_schema_directory, validate_schema


SCHEMAS = official_schema_directory()


class EvidenceIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = repository(fixture="vulnerable_service")
        self.flow = pipeline()
        approve_scope(self.flow, self.record)
        self.flow.run((self.record,))
        evidence = self.flow.states[self.record.repo_id].evidence
        self.assertIsNotNone(evidence)
        self.bundle = deepcopy(evidence)

    def test_all_three_artifacts_validate_against_installed_official_product_schemas(self) -> None:
        for name in ("findings", "coverage", "scan-manifest"):
            with self.subTest(name=name):
                schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
                validate_schema(self.bundle[f"{name}.json"], schema)

    def test_valid_host_signed_artifacts_pass_integrity_and_provenance_verification(self) -> None:
        self.flow.sealer.verify(self.bundle)
        manifest = self.bundle["scan-manifest.json"]
        self.assertEqual(manifest["scan"]["target"]["revision"], self.record.commit_sha)
        self.assertTrue(manifest["hostIntegrityMac"])

    def test_all_official_contract_artifacts_unmistakably_identify_synthetic_provenance(self) -> None:
        for name in ("findings.json", "coverage.json", "scan-manifest.json"):
            with self.subTest(name=name):
                self.assertIs(self.bundle[name]["synthetic"], True)
        manifest = self.bundle["scan-manifest.json"]
        finding = self.bundle["findings.json"]["findings"][0]
        self.assertEqual(manifest["scan"]["producer"]["name"], "synthetic-local-adapter")
        self.assertEqual(finding["provenance"]["source"], "synthetic-local-adapter")
        self.assertFalse(finding["provenance"]["productExecution"])

    def test_tampered_finding_severity_is_rejected(self) -> None:
        self.bundle["findings.json"]["findings"][0]["severity"]["level"] = "low"
        with self.assertRaisesRegex(EvidenceError, "hash mismatch"):
            self.flow.sealer.verify(self.bundle)

    def test_tampered_report_or_coverage_is_rejected(self) -> None:
        for field, mutation in (
            ("report.md", lambda current: current + "tampered"),
            ("coverage.json", lambda current: {**current, "completeness": "unknown"}),
        ):
            current = deepcopy(self.bundle)
            current[field] = mutation(current[field])
            with self.subTest(field=field), self.assertRaisesRegex(EvidenceError, "hash mismatch"):
                self.flow.sealer.verify(current)

    def test_resealed_untrusted_manifest_without_host_key_is_rejected(self) -> None:
        self.bundle["scan-manifest.json"]["scan"]["target"]["revision"] = "f" * 40
        self.bundle["scan-manifest.json"]["hostIntegrityMac"] = "0" * 64
        with self.assertRaisesRegex(EvidenceError, "signature"):
            self.flow.sealer.verify(self.bundle)

    def test_different_process_host_key_cannot_verify_existing_manifest(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "signature"):
            EvidenceSealer().verify(self.bundle)

    def test_official_schema_rejects_forged_finding_id_and_invalid_confidence(self) -> None:
        schema = json.loads((SCHEMAS / "findings.schema.json").read_text(encoding="utf-8"))
        for path, value in (("findingId", "invented"), ("confidence", {"level": "certain", "rationale": "x"})):
            document = deepcopy(self.bundle["findings.json"])
            document["findings"][0][path] = value
            with self.subTest(path=path), self.assertRaises(EvidenceError):
                validate_schema(document, schema)

    def test_official_coverage_rejects_complete_scan_with_deferred_surface(self) -> None:
        schema = json.loads((SCHEMAS / "coverage.schema.json").read_text(encoding="utf-8"))
        coverage = deepcopy(self.bundle["coverage.json"])
        coverage["deferred"] = [{"id": "omitted", "reason": "not reviewed"}]
        with self.assertRaises(EvidenceError):
            validate_schema(coverage, schema)

    def test_duplicate_finding_registry_suppresses_repeated_stable_identity(self) -> None:
        finding = self.bundle["findings.json"]["findings"][0]
        registry = FindingRegistry()
        first, first_duplicates = registry.admit((finding, finding))
        second, second_duplicates = registry.admit((finding,))
        self.assertEqual((len(first), first_duplicates, len(second), second_duplicates, registry.count), (1, 1, 0, 1, 1))

    def test_audit_hash_chain_detects_tampering_reordering_and_deletion(self) -> None:
        audit = AuditLog()
        audit.append("authorised", self.record.repo_id, actor="trusted-owner")
        audit.append("completed", self.record.repo_id, finding_count=1)
        self.assertTrue(audit.verify())
        events = list(audit.events)
        events[0]["metadata"]["actor"] = "forged-owner"
        self.assertFalse(audit.verify(tuple(events)))
        self.assertFalse(audit.verify(tuple(reversed(audit.events))))
        self.assertFalse(audit.verify(audit.events[1:]))

    def test_audit_refuses_credential_prompt_and_repository_source_fields(self) -> None:
        for forbidden in ("api_key", "secret", "access_token", "source", "prompt"):
            with self.subTest(forbidden=forbidden), self.assertRaises(EvidenceError):
                AuditLog().append("attempt", self.record.repo_id, **{forbidden: "synthetic"})

    def test_secure_artifact_store_uses_owner_only_permissions_and_verified_cleanup(self) -> None:
        with SecureArtifactStore() as store:
            root = store.path
            self.assertIsNotNone(root)
            receipt = store.write("receipt.json", {"repository": self.record.repo_id})
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
            with self.assertRaises(EvidenceError):
                store.write("../escape.json", {})
        self.assertFalse(root.exists())


if __name__ == "__main__":
    unittest.main()
