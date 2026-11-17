"""Local regression tests; no network access and no paid requests."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from evaluate import summarize
from report import write_report
from review import (CHOICES, build_request, create_client, load_cases, next_step,
                    parse_answers, request_preview, review_case, ROOT)


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_cases()
        cls.case = cls.data["cases"][0]
        cls.product = cls.data["products"][cls.case["product_id"]]
        cls.payload = build_request(cls.case, cls.product)

    def answer(self, **changes):
        value = {"type": "choice", "name": "listing_color",
                 "choice": "match", "confidence": 0.9}
        value.update(changes)
        return value

    def test_invalid_confidences_do_not_raise(self):
        for value in [True, None, "0.9", -0.1, 1.1, float("nan"),
                      float("inf"), 10**400]:
            with self.subTest(value=type(value).__name__):
                parsed = parse_answers({"answers": [self.answer(confidence=value)]},
                                       self.payload["questions"])
                self.assertEqual(parsed[0]["choice"], "unusable_answer")

    def test_missing_duplicate_refused_and_malformed(self):
        for answers in [None, [], [self.answer(), self.answer()],
                        [{"type": "refusal", "name": "listing_color"}], ["bad"]]:
            parsed = parse_answers({"answers": answers}, self.payload["questions"])
            self.assertTrue(all(a["choice"] == "unusable_answer" for a in parsed))
            self.assertEqual(next_step(parsed), "request_evidence")

    def test_answers_are_matched_by_name(self):
        answers = [self.answer(name=q["name"]) for q in self.payload["questions"]]
        self.assertEqual([a["name"] for a in parse_answers(
            {"answers": answers[::-1]}, self.payload["questions"])],
            [q["name"] for q in self.payload["questions"]])

    def test_allowed_choices_come_from_request(self):
        questions = copy.deepcopy(self.payload["questions"])
        questions[0]["choices"] = [{"value": "custom_choice", "description": "Custom"}]
        parsed = parse_answers({"answers": [self.answer(choice="custom_choice")]}, questions)
        self.assertEqual(parsed[0]["choice"], "custom_choice")

    def test_labels_and_titles_are_not_sent(self):
        altered = dict(self.case, title="DO NOT SEND GOLD LABEL", expected="mismatch")
        payload = build_request(altered, self.product)
        self.assertNotIn("DO NOT SEND GOLD LABEL", json.dumps(payload))
        self.assertNotIn("expected", json.dumps(payload))
        self.assertEqual(payload["input"][0]["role"], "user")
        self.assertEqual(payload["input"][0]["content"][1]["type"], "input_json")
        self.assertEqual(len(payload["questions"]), 4)
        self.assertNotIn("base64,", json.dumps(request_preview(payload)))

    def test_policy_never_publishes_and_preserves_uncertainty(self):
        self.assertEqual(next_step([]), "request_evidence")
        for value, expected in [("match", "ready_for_editor_review"),
                                ("mismatch", "review_mismatch"),
                                ("insufficient_evidence", "request_evidence")]:
            self.assertEqual(next_step([{"choice": value}]), expected)

    def test_every_fixture_and_label_is_complete(self):
        labels = json.loads((ROOT / "labels.json").read_text())
        self.assertEqual(set(labels), {case["id"] for case in self.data["cases"]})
        for case in self.data["cases"]:
            payload = build_request(case, self.data["products"][case["product_id"]])
            self.assertEqual(set(labels[case["id"]]), {q["name"] for q in payload["questions"]})
            self.assertTrue(set(labels[case["id"]].values()) <= {c["value"] for c in CHOICES})
        manifest = json.loads((ROOT / "images" / "provenance.json").read_text())
        for filename, expected in manifest["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / "images" / filename).read_bytes()).hexdigest(),
                             expected)

    def test_sdk_request_and_response_with_local_transport(self):
        import httpx2
        from openai import OpenAI

        seen = []
        def handler(request):
            seen.append(request)
            body = json.loads(request.content)
            self.assertEqual(request.url.path, "/v1/decisions")
            self.assertEqual(body, self.payload)
            return httpx2.Response(200, json={
                "model": "gpt-6-luna", "answers": [
                    self.answer(name=q["name"]) for q in body["questions"]],
                "usage": {"input_tokens": 100, "total_tokens": 100},
            })

        transport = httpx2.Client(transport=httpx2.MockTransport(handler),
                                 follow_redirects=False, trust_env=False)
        with OpenAI(api_key="offline-test-key", http_client=transport,
                    max_retries=0) as client:
            row = review_case(client, self.case, self.product)
        self.assertEqual(len(seen), 1)
        self.assertEqual(row["next_step"], "ready_for_editor_review")
        self.assertNotIn("offline-test-key", json.dumps(row))
        with tempfile.TemporaryDirectory() as directory:
            row["title"] = '<script>alert("test")</script>'
            path = Path(directory) / "report.html"
            write_report([row], path)
            self.assertNotIn("<script>", path.read_text())
            self.assertIn("ACTUAL", path.read_text().upper())

    def test_redirects_are_rejected_without_forwarding(self):
        import httpx2
        from openai import APIStatusError, OpenAI

        seen = []
        def handler(request):
            seen.append(str(request.url))
            return httpx2.Response(302, headers={"Location": "https://other.example/"})

        transport = httpx2.Client(transport=httpx2.MockTransport(handler),
                                 follow_redirects=False, trust_env=False)
        with OpenAI(api_key="offline-test-key", http_client=transport,
                    max_retries=0) as client:
            with self.assertRaises(APIStatusError):
                review_case(client, self.case, self.product)
        self.assertEqual(len(seen), 1)
        with create_client("offline-test-key") as client:
            self.assertFalse(client._client.follow_redirects)
            self.assertEqual(client.max_retries, 0)

    def test_evaluation_counts_unsafe_matches_and_false_flags(self):
        labels = {"case": {"a": "mismatch", "b": "match", "c": "insufficient_evidence"}}
        row = {"case_id": "case", "group": "test", "next_step": "ready_for_editor_review",
               "answers": [{"name": "a", "choice": "match"},
                           {"name": "b", "choice": "mismatch"},
                           {"name": "c", "choice": "match"}]}
        metrics = summarize([row], labels)["test"]
        self.assertEqual(metrics["missed_mismatch_flags"], 1)
        self.assertEqual(metrics["false_mismatch_flags"], 1)
        self.assertEqual(metrics["unclear_marked_match"], 1)
        self.assertEqual(metrics["mismatch_cases_marked_ready"], 1)
        with self.assertRaises(ValueError):
            summarize([row, row], labels)


if __name__ == "__main__":
    unittest.main()
