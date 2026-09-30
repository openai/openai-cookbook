"""Offline checks for the retrieval failure report."""

import unittest

from report_failures import build_report


class ReportFailuresTests(unittest.TestCase):
    def setUp(self):
        self.queries = [
            {
                "id": "q-1",
                "text": "Şifremi nasıl yenilerim?",
                "relevant_ids": ["doc-a", "doc-b"],
                "split": "development",
            }
        ]
        self.documents = ["doc-a", "doc-b", "doc-c"]

    def result(self, ranking, split="development"):
        return {
            "split": split,
            "methods": {"unicode": {"rankings": {"q-1": ranking}}},
        }

    def test_partial_recall_lists_only_missing_relevant_ids(self):
        report = build_report(self.result([["doc-a", 0.9], ["doc-c", 0.5]]), self.queries, self.documents)
        self.assertIn("Split: `development`", report)
        self.assertIn("Query: Şifremi nasıl yenilerim?", report)
        self.assertIn("Relevant: doc-a, doc-b", report)
        self.assertIn("Retrieved: doc-a, doc-c", report)
        self.assertIn("Missing: doc-b", report)

    def test_fully_correct_ranking_has_no_failure_entry(self):
        report = build_report(self.result([["doc-a", 0.9], ["doc-b", 0.8]]), self.queries, self.documents)
        self.assertIn("No relevant documents were missed.", report)

    def test_empty_ranking_reports_all_relevant_ids(self):
        report = build_report(self.result([]), self.queries, self.documents)
        self.assertIn("Retrieved: (none)", report)
        self.assertIn("Missing: doc-a, doc-b", report)

    def test_rejects_held_out_split_and_bad_schema(self):
        with self.assertRaisesRegex(ValueError, "development split"):
            build_report(self.result([], split="held-out"), self.queries, self.documents)
        with self.assertRaisesRegex(ValueError, "methods object"):
            build_report({"split": "development", "methods": []}, self.queries, self.documents)

    def test_rejects_missing_query_and_document_ids(self):
        with self.assertRaisesRegex(ValueError, "query IDs"):
            build_report(self.result([]), [], self.documents)
        with self.assertRaisesRegex(ValueError, "unknown document ID"):
            build_report(self.result([["unknown", 0.9]]), self.queries, self.documents)
        with self.assertRaisesRegex(ValueError, "invalid relevant document IDs"):
            query = [{**self.queries[0], "relevant_ids": ["unknown"]}]
            build_report(self.result([]), query, self.documents)


if __name__ == "__main__":
    unittest.main()
