"""Offline regressions for the independently verified public product contract."""
from __future__ import annotations

import json
import runpy
import unittest

from stress_helpers import ROOT, PrivateRecipeCase
from fleet_security.surface import UNSUPPORTED_BULK_FLAGS


def notebook_path():
    published = ROOT / "governed_repository_security_reviews.ipynb"
    return published if published.is_file() else ROOT / "cookbook" / published.name


class PublicSecurityContractAdversarialStress(unittest.TestCase):
    def test_documented_bulk_cost_threshold_is_not_classified_unsupported(self) -> None:
        self.assertNotIn("--max-cost", UNSUPPORTED_BULK_FLAGS)

    def test_undocumented_bulk_options_remain_refused(self) -> None:
        self.assertEqual(
            UNSUPPORTED_BULK_FLAGS,
            frozenset({"--auth", "--max-time-hours", "--diff", "--head"}),
        )

    def test_both_publication_sources_describe_per_attempt_soft_threshold(self) -> None:
        for relative in (
            "PUBLICATION_SOURCES.md",
            "cookbook/security-review-pipeline/PUBLICATION_SOURCES.md",
        ):
            with self.subTest(path=relative):
                document = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("`bulk-scan --max-cost USD` is documented", document)
                self.assertIn("separately to each repository attempt", document)
                self.assertIn("in-flight requests can overshoot", document)
                self.assertIn("not a hard aggregate campaign cap", document)
                self.assertNotIn("`--max-time-hours` and `--max-cost` belong", document)
                self.assertIn("`scan --patch --create-pr`", document)
                self.assertIn("**draft\nGitHub pull request**", document)
                self.assertIn("separately approved repository, branch", document)
                self.assertIn("Neither establishes bulk pull-request creation", document)

    def test_adopter_readme_requires_independent_customer_owned_budget(self) -> None:
        document = (
            ROOT / "cookbook" / "security-review-pipeline" / "README.md"
        ).read_text(encoding="utf-8")
        self.assertIn("supports `--max-cost USD`", document)
        self.assertIn("per-repository-attempt estimated threshold", document)
        self.assertIn("may overshoot", document)
        self.assertIn("not** a hard aggregate campaign cap", document)
        self.assertIn("independently bound admissions", document)

    def test_notebook_generator_preserves_supported_option_and_no_spend_boundary(self) -> None:
        source = (
            ROOT / "scripts" / "build_security_review_cookbook.py"
        ).read_text(encoding="utf-8")
        self.assertIn("`bulk-scan --max-cost USD` is a documented", source)
        self.assertIn("per-repository-attempt estimated threshold", source)
        self.assertIn("independent customer-owned admission budget", source)
        self.assertIn("no real scan or expenditure is approved", source)
        self.assertNotIn("`--max-cost` is not a documented bulk-campaign flag", source)

    def test_generated_notebook_no_longer_repeats_disproved_claim(self) -> None:
        notebook = json.loads(
            notebook_path()
            .read_text(encoding="utf-8")
        )
        markdown = "\n".join(
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "markdown"
        )
        self.assertIn("bulk-scan --max-cost USD", markdown)
        self.assertIn("not a hard aggregate campaign cap", markdown)
        self.assertNotIn("not a documented bulk-campaign flag", markdown)

    def test_generated_notebook_matches_its_reviewable_source_generator(self) -> None:
        namespace = runpy.run_path(
            str(ROOT / "scripts" / "build_security_review_cookbook.py")
        )
        notebook = json.loads(
            notebook_path()
            .read_text(encoding="utf-8")
        )
        self.assertEqual(notebook["cells"], namespace["build_cells"]())


class InertCampaignCostControlStress(PrivateRecipeCase):
    def test_supported_optional_threshold_does_not_authorise_live_execution(self) -> None:
        result = self.cycle()
        self.assertFalse(result["live_product_execution"])
        self.assertEqual(result["paid_api_calls"], 0)
        self.assertEqual(result["external_writes"], 0)
        for plan in result["native_campaign_plans"]:
            self.assertFalse(plan["command_executed"])
            self.assertFalse(plan["customer_model_approval_verified"])
            self.assertNotIn("--max-cost", plan["command"])


if __name__ == "__main__":
    unittest.main()
