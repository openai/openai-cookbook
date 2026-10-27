from __future__ import annotations

import csv
import io
import unittest
from dataclasses import replace

from support import repository
from fleet_security import ThreatCatalogue, generate_inventory
from fleet_security.surface import (
    CSV_COLUMNS, UNSUPPORTED_BULK_FLAGS, CampaignResumeLedger,
    NativeBulkCampaign, group_native_campaigns,
)


class NativeBulkSurfaceTests(unittest.TestCase):
    def test_two_thousand_records_group_into_ten_campaign_wide_archetypes(self) -> None:
        campaigns = group_native_campaigns(generate_inventory(2_000), ThreatCatalogue())
        self.assertEqual(len(campaigns), 10)
        self.assertEqual(sum(len(campaign.rows) for campaign in campaigns), 2_000)
        self.assertTrue(all(len(campaign.knowledge_base_paths) == 2 for campaign in campaigns))

    def test_csv_header_and_full_revision_match_documented_native_contract(self) -> None:
        campaign = group_native_campaigns((repository(),), ThreatCatalogue())[0]
        parsed = csv.DictReader(io.StringIO(campaign.csv_text()))
        self.assertEqual(tuple(parsed.fieldnames or ()), CSV_COLUMNS)
        row = next(parsed)
        self.assertEqual(len(row["revision"]), 40)
        self.assertEqual(row["scope"], "")
        self.assertEqual(row["mode"], "standard")

    def test_native_campaign_id_has_no_slash_and_collisions_are_rejected(self) -> None:
        campaign = group_native_campaigns((repository(),), ThreatCatalogue())[0]
        self.assertEqual(campaign.rows[0]["id"], "synthetic-repo-0001")
        first = repository(repo_id="synthetic/a-b")
        second = repository(2, repo_id="synthetic-a/b")
        with self.assertRaisesRegex(ValueError, "colliding"):
            group_native_campaigns((first, second), ThreatCatalogue())

    def test_group_scope_is_empty_for_full_authorised_repository(self) -> None:
        campaigns = group_native_campaigns(generate_inventory(20), ThreatCatalogue())
        self.assertTrue(all(row["scope"] == "" for item in campaigns for row in item.rows))

    def test_per_repository_delta_uses_csv_prompt_not_unsupported_per_row_knowledge_flags(self) -> None:
        campaign = group_native_campaigns((repository(data_class="confidential"),), ThreatCatalogue())[0]
        self.assertIn("data=confidential", campaign.rows[0]["prompt"])
        self.assertIn("effective_context_sha256=", campaign.rows[0]["prompt"])
        self.assertEqual(len(campaign.knowledge_base_paths), 2)

    def test_high_risk_repositories_are_marked_deep(self) -> None:
        campaign = group_native_campaigns((repository(criticality="critical"),), ThreatCatalogue())[0]
        self.assertEqual(campaign.rows[0]["mode"], "deep")

    def test_command_vector_is_inert_and_has_only_documented_bulk_options(self) -> None:
        campaign = group_native_campaigns((repository(),), ThreatCatalogue(), workers=3, max_attempts=2)[0]
        command = campaign.command(csv_path="repositories.csv", output_dir="/private/output")
        self.assertEqual(command[:4], ("npx", "@openai/codex-security@0.1.20", "bulk-scan", "repositories.csv"))
        self.assertIn("--workers", command)
        self.assertIn("--max-attempts", command)
        self.assertFalse(set(command) & UNSUPPORTED_BULK_FLAGS)
        self.assertEqual(command.count("--knowledge-base"), 2)

    def test_resume_reuses_exact_campaign_but_rejects_changed_revision_or_prompt(self) -> None:
        record = repository()
        campaign = group_native_campaigns((record,), ThreatCatalogue())[0]
        ledger = CampaignResumeLedger()
        self.assertEqual(ledger.admit("/private/campaign", campaign), "created")
        self.assertEqual(ledger.admit("/private/campaign", campaign), "resumed")
        replacement = group_native_campaigns((replace(record, commit_sha="b" * 40),), ThreatCatalogue())[0]
        with self.assertRaisesRegex(ValueError, "new output campaign"):
            ledger.admit("/private/campaign", replacement)
        self.assertEqual(ledger.admit("/private/new-campaign", replacement), "created")

    def test_campaign_rejects_unsafe_id_scope_or_partial_revision(self) -> None:
        original = group_native_campaigns((repository(),), ThreatCatalogue())[0]
        for changes in ({"id": "unsafe/name"}, {"scope": "../hidden"}, {"revision": "abcdef"}):
            row = dict(original.rows[0])
            row.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                NativeBulkCampaign(original.archetype, (row,), original.knowledge_base_paths)


if __name__ == "__main__":
    unittest.main()
