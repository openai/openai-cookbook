"""Offline regressions for the return evidence tutorial. No model calls."""

import copy
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import return_evidence as demo
import return_reporting as reporting
import run_product_return_evidence as runner
from return_reporting import display_request, write_report


def response(issue="damaged_item", usable=0.99, damaged=0.99):
    return {"answers": [
        {"type": "choice", "name": "reported_issue", "choice": issue, "confidence": 0.99},
        {"type": "predicate", "name": "photo_usable", "probability": usable},
        {"type": "predicate", "name": "visible_damage", "probability": damaged},
    ]}


class ReturnEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.cases = demo.load_cases()
        self.case = self.cases[0]

    def test_answer_order_is_irrelevant(self):
        body = response()
        body["answers"].reverse()
        self.assertEqual(demo.parse_answers(body)["reported_issue"], "damaged_item")

    def test_refusals_duplicates_and_missing_answers_fall_back(self):
        bodies = [None, [], {}, {"answers": []}, {"answers": [None] * 3}]
        for field in ["type", "name"]:
            body = response()
            body["answers"][0][field] = "refusal" if field == "type" else "photo_usable"
            bodies.append(body)
        for body in bodies:
            with self.subTest(body=body):
                self.assertIsNone(demo.parse_answers(body))
                self.assertEqual(demo.recommend_next_step(self.case, None)["next_step"], "specialist_review")

    def test_invalid_numeric_values_do_not_crash(self):
        for value in [True, "0.9", None, -0.1, 1.1, float("nan"), float("inf"), 10**400]:
            for index, field in [(0, "confidence"), (1, "probability"), (2, "probability")]:
                with self.subTest(value=repr(value), field=field):
                    body = response()
                    body["answers"][index][field] = value
                    self.assertIsNone(demo.parse_answers(body))

    def test_choice_customization_stays_in_sync(self):
        questions = copy.deepcopy(demo.QUESTIONS)
        questions[0]["choices"][0]["value"] = "billing"
        with patch.object(demo, "QUESTIONS", questions):
            self.assertEqual(demo.parse_answers(response(issue="billing"))["reported_issue"], "billing")
            self.assertEqual(demo.build_request(self.case)["questions"], questions)

    def test_unknown_choice_and_question_name_are_rejected(self):
        self.assertIsNone(demo.parse_answers(response(issue="approve_refund")))
        body = response()
        body["answers"][0]["name"] = "approve_refund"
        self.assertIsNone(demo.parse_answers(body))

    def test_clear_evidence_prepares_a_case_for_human_approval(self):
        record = demo.recommend_next_step(self.case, demo.parse_answers(response()))
        self.assertEqual(record["next_step"], "prepare_for_review")
        self.assertTrue(record["approval_required"])
        self.assertEqual(record["owner"], "returns_agent")

    def test_unclear_or_hidden_product_requests_information(self):
        record = demo.recommend_next_step(self.case, demo.parse_answers(response(usable=0.1)))
        self.assertEqual(record["next_step"], "request_information")

    def test_conflicting_or_uncertain_damage_reaches_a_specialist(self):
        for probability in [0.0, 0.2, 0.5, 0.79]:
            record = demo.recommend_next_step(self.case, demo.parse_answers(response(damaged=probability)))
            self.assertEqual(record["next_step"], "specialist_review")

    def test_policy_exceptions_and_missing_order_information(self):
        for days, expected in [(30, "prepare_for_review"), (31, "specialist_review"),
                               (-1, "request_information"), (True, "request_information"),
                               (None, "request_information")]:
            case = copy.deepcopy(self.case)
            case["order"]["days_since_delivery"] = days
            record = demo.recommend_next_step(case, demo.parse_answers(response()))
            self.assertEqual(record["next_step"], expected)
        record = demo.recommend_next_step(self.cases[5], demo.parse_answers(response()))
        self.assertEqual(record["next_step"], "request_information")

    def test_reported_issue_confidence_and_other_workflows(self):
        for issue in ["packaging_damage", "wrong_item", "other"]:
            answers = demo.parse_answers(response(issue=issue))
            record = demo.recommend_next_step(self.case, answers)
            self.assertEqual(record["next_step"], "specialist_review")
        body = response()
        body["answers"][0]["confidence"] = 0.5
        record = demo.recommend_next_step(self.case, demo.parse_answers(body))
        self.assertEqual(record["reason"], "uncertain_reported_issue")

    def test_all_fixtures_build_and_expected_labels_stay_local(self):
        self.assertEqual(len(self.cases), 10)
        self.assertEqual(len({case["id"] for case in self.cases}), 10)
        for case in self.cases:
            payload = demo.build_request(case)
            self.assertEqual(payload["model"], demo.MODEL)
            self.assertEqual(len(payload["questions"]), 3)
            self.assertNotIn("expected", json.dumps(payload))
        conversation = demo.build_request(self.cases[-1])["input"]
        self.assertEqual([m["role"] for m in conversation], ["user", "assistant", "user"])
        self.assertIn("input_json", [p["type"] for p in conversation[-1]["content"]])

    def test_payload_preview_does_not_mutate_the_sent_image(self):
        payload = demo.build_request(self.case)
        original = payload["input"][0]["content"][1]["image_url"]
        self.assertNotIn(original, json.dumps(display_request(payload)))
        self.assertEqual(payload["input"][0]["content"][1]["image_url"], original)

    def test_redirects_are_rejected_for_every_redirect_status(self):
        request = urllib.request.Request(demo.API_URL, data=b"{}", headers={"Authorization": "Bearer dummy"})
        handler = demo._RejectRedirects()
        for status in [301, 302, 303, 307, 308]:
            self.assertIsNone(handler.redirect_request(request, None, status, "", {}, "https://example.org/"))
        self.assertTrue(any(isinstance(h, demo._RejectRedirects) for h in demo._OPENER.handlers))

    def test_network_failure_is_not_retried_and_headers_are_not_reported(self):
        with patch.object(demo._OPENER, "open", side_effect=urllib.error.URLError("dummy-secret")) as call:
            with self.assertRaisesRegex(RuntimeError, "stopped without retry") as error:
                demo.request_decision(demo.build_request(self.case), "dummy-secret")
            self.assertNotIn("dummy-secret", str(error.exception))
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.kwargs["timeout"], 30)

    def test_html_report_contains_images_and_escapes_untrusted_content(self):
        case = copy.deepcopy(self.case)
        case["title"] = "<script>alert(1)</script>"
        handoff = demo.recommend_next_step(case, None)
        request_preview = display_request(demo.build_request(case))
        rows = [{"case": case, "request": request_preview,
                 "response": response(), "handoff": handoff,
                 "grade": demo.grade_result(case["id"], handoff, {case["id"]: "specialist_review"}),
                 "latency_ms": 10}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            write_report(rows, path, Path(demo.__file__).parent)
            text = path.read_text()
            self.assertIn("data:image/png;base64,", text)
            self.assertNotIn("<script>alert", text)
            self.assertIn("&lt;script&gt;", text)
            saved = json.loads(path.with_suffix(".json").read_text())
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["request"], request_preview)
            self.assertIn("API request</h3>", text)
            self.assertIn("POST " + demo.API_URL, text)
            self.assertIn("Actual Decisions API response", text)
            self.assertNotIn("Authorization", json.dumps(saved[0]["request"]))
            self.assertNotIn("data:image/png;base64,", json.dumps(saved[0]["request"]))

    def test_help_never_prompts_for_a_key(self):
        script = Path(demo.__file__).with_name("run_product_return_evidence.py")
        flags = ["-P"] if sys.version_info >= (3, 11) else []
        result = subprocess.run([sys.executable, *flags, str(script), "--help"],
                                input="", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("API key (hidden)", result.stdout)

    def test_notebook_runs_ten_calls_and_clears_its_key_with_test_doubles(self):
        notebook = Path(demo.__file__).with_name("product_return_evidence.ipynb")
        cells = json.loads(notebook.read_text())["cells"]
        display_module = types.ModuleType("IPython.display")
        display_module.Image = lambda **kwargs: None
        display_module.Markdown = lambda text: text
        display_module.display = lambda *args: None
        modules = {"IPython": types.ModuleType("IPython"), "IPython.display": display_module}
        namespace = {"__name__": "__main__"}
        previous = Path.cwd()
        try:
            os.chdir(Path(demo.__file__).parent)
            with patch.dict(sys.modules, modules), \
                    patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-only"}), \
                    patch.object(demo, "request_decision", return_value=(response(), 10)) as call, \
                    patch.object(reporting, "write_report"), contextlib.redirect_stdout(io.StringIO()):
                for cell in cells:
                    if cell["cell_type"] == "code":
                        exec(compile("".join(cell["source"]), str(notebook), "exec"), namespace)
            self.assertEqual(call.call_count, 10)
            self.assertEqual(len(namespace["rows"]), 10)
            for row, request_call in zip(namespace["rows"], call.call_args_list):
                self.assertEqual(row["request"], display_request(request_call.args[0]))
                self.assertNotIn("unit-test-only", json.dumps(row))
            self.assertIsNone(namespace["api_key"])
        finally:
            os.chdir(previous)

    def test_notebook_summary_tolerates_malformed_responses_and_usage(self):
        notebook = Path(demo.__file__).with_name("product_return_evidence.ipynb")
        cells = json.loads(notebook.read_text())["cells"]
        summary = next("".join(cell["source"]) for cell in cells
                       if cell["cell_type"] == "code"
                       and "Completed API requests:" in "".join(cell["source"]))
        bodies = [None, [], "invalid", 7, {"usage": None},
                  {"usage": {"total_tokens": "10"}},
                  {"usage": {"total_tokens": True}},
                  {"usage": {"total_tokens": -1}},
                  {"usage": {"total_tokens": 1.5}},
                  {"usage": {"total_tokens": 12}}]
        rows = []
        for case, body in zip(self.cases, bodies):
            handoff = demo.recommend_next_step(case, demo.parse_answers(body))
            rows.append({"case": case, "response": body, "latency_ms": 10,
                         "grade": demo.grade_result(case["id"], handoff,
                                                   {case["id"]: "specialist_review"})})
        namespace = {"rows": rows, "cases": self.cases,
                     "parse_answers": demo.parse_answers,
                     "total_tokens": reporting.total_tokens,
                     "Markdown": lambda text: text, "display": lambda *args: None}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            exec(compile(summary, str(notebook), "exec"), namespace)
        self.assertIn("Completed API requests: 10/10", output.getvalue())
        self.assertIn("Total tokens: 12", output.getvalue())
        self.assertIn("Unusable API answers: 10", output.getvalue())

    def test_report_output_cannot_overwrite_bundled_data(self):
        directory = Path(demo.__file__).parent
        source = directory / "return_cases.json"
        before = source.read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite bundled JSON"):
            write_report([], directory / "return_cases.html", directory)
        self.assertEqual(source.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "end in .html"):
            write_report([], source, directory)
        self.assertEqual(source.read_bytes(), before)

    def test_report_image_traversal_and_symlink_escape_are_rejected(self):
        case = copy.deepcopy(self.case)
        case["conversation"][0]["image"] = "../../../private.png"
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            destination = directory / "report.html"
            with self.assertRaisesRegex(ValueError, "bundled PNG"):
                write_report([{"case": case}], destination, Path(demo.__file__).parent)
            self.assertFalse(destination.exists())
            (directory / "images").mkdir()
            (directory / "private.png").write_bytes(b"private fixture")
            (directory / "images" / "linked.png").symlink_to(directory / "private.png")
            case["conversation"][0]["image"] = "linked.png"
            with self.assertRaisesRegex(ValueError, "inside the images folder"):
                demo.build_request(case, directory)
            with self.assertRaisesRegex(ValueError, "inside the images folder"):
                write_report([{"case": case}], destination, directory)
            self.assertFalse(destination.exists())

    def test_matching_specialist_fallback_still_reports_an_unusable_answer(self):
        refusal = {"answers": [{"type": "refusal", "name": "reported_issue"}]}
        handoff = demo.recommend_next_step(self.case, demo.parse_answers(refusal))
        rows = [{"case": self.case, "response": refusal, "handoff": handoff,
                 "grade": demo.grade_result(self.case["id"], handoff,
                                           {self.case["id"]: "specialist_review"}),
                 "latency_ms": 10}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            write_report(rows, path, Path(demo.__file__).parent)
            text = path.read_text()
            self.assertIn("1/1 expected outcomes matched", text)
            self.assertIn("Unusable API answers sent for specialist review: 1", text)
            self.assertIn("Request preview was not recorded", text)

    def test_reports_preserve_unusable_response_shapes(self):
        for body in [None, [], "invalid", 7, {"usage": None}]:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                handoff = demo.recommend_next_step(self.case, demo.parse_answers(body))
                rows = [{"case": self.case, "response": body, "handoff": handoff,
                         "grade": demo.grade_result(self.case["id"], handoff,
                                                   {self.case["id"]: "specialist_review"}),
                         "latency_ms": 10}]
                path = Path(tmp) / "report.html"
                write_report(rows, path, Path(demo.__file__).parent)
                self.assertEqual(json.loads(path.with_suffix(".json").read_text()), rows)
                text = path.read_text()
                self.assertIn("Unusable API answers sent for specialist review: 1", text)
                self.assertIn("Total tokens: 0", text)

    def test_reports_tolerate_missing_or_malformed_usage(self):
        usages = [None, [], "invalid", 7, {}, {"total_tokens": None},
                  {"total_tokens": "10"}, {"total_tokens": True},
                  {"total_tokens": -1}, {"total_tokens": 1.5},
                  {"total_tokens": 12}]
        for usage in usages:
            with self.subTest(usage=usage), tempfile.TemporaryDirectory() as tmp:
                body = response()
                body["usage"] = usage
                handoff = demo.recommend_next_step(self.case, demo.parse_answers(body))
                rows = [{"case": self.case, "response": body, "handoff": handoff,
                         "grade": demo.grade_result(self.case["id"], handoff,
                                                   {self.case["id"]: "prepare_for_review"}),
                         "latency_ms": 10}]
                path = Path(tmp) / "report.html"
                write_report(rows, path, Path(demo.__file__).parent)
                self.assertEqual(json.loads(path.with_suffix(".json").read_text()), rows)
                text = path.read_text()
                expected_tokens = 12 if usage == {"total_tokens": 12} else 0
                self.assertIn(f"Total tokens: {expected_tokens}", text)
                self.assertIn("Unusable API answers sent for specialist review: 0", text)

    def test_invalid_output_stops_cli_before_credentials_or_api_calls(self):
        source = Path(demo.__file__).with_name("return_cases.json")
        with patch.object(sys, "argv", ["runner", "--output", str(source)]), \
                patch.object(runner.getpass, "getpass") as prompt, \
                patch.object(runner, "request_decision") as call:
            with self.assertRaisesRegex(ValueError, "end in .html"):
                runner.main()
            prompt.assert_not_called()
            call.assert_not_called()

    def test_cli_runs_ten_cases_with_actual_request_previews(self):
        predictions = [response(), response(damaged=0),
                       response(issue="packaging_damage", damaged=0),
                       response(usable=0, damaged=0), response(usable=0, damaged=0),
                       response(), response(), response(issue="wrong_item", damaged=0),
                       response(usable=0, damaged=0), response()]
        with tempfile.TemporaryDirectory() as tmp:
            args = ["runner", "--output", str(Path(tmp) / "report.html")]
            with patch.object(sys, "argv", args), \
                    patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-only"}), \
                    patch.object(runner, "request_decision",
                                 side_effect=[(body, 10) for body in predictions]) as call, \
                    patch.object(runner, "write_report") as report, \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(), 0)
            self.assertEqual(call.call_count, 10)
            self.assertEqual(report.call_count, 11)
            rows = report.call_args.args[0]
            self.assertEqual(len(rows), 10)
            self.assertTrue(all(row["grade"]["passed"] for row in rows))
            for row, request_call in zip(rows, call.call_args_list):
                self.assertEqual(row["request"], display_request(request_call.args[0]))
            self.assertNotIn("unit-test-only", output.getvalue())

    def test_cli_keeps_partial_progress_and_stops_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = ["runner", "--output", str(Path(tmp) / "report.html")]
            with patch.object(sys, "argv", args), \
                    patch.dict(os.environ, {"OPENAI_API_KEY": "unit-test-only"}), \
                    patch.object(runner, "request_decision",
                                 side_effect=[(response(), 10), RuntimeError("failed")]) as call, \
                    patch.object(runner, "write_report") as report, \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "failed"):
                    runner.main()
            self.assertEqual(call.call_count, 2)
            self.assertEqual(report.call_count, 2)
            self.assertEqual(len(report.call_args.args[0]), 1)

    def test_reference_labels_are_validated_before_running_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "return_expectations.json"
            for labels in [{}, {"return-01": "approve_refund"}, [],
                           {case["id"]: [] for case in self.cases}]:
                path.write_text(json.dumps(labels))
                with self.assertRaisesRegex(ValueError, "Reference outcomes"):
                    demo.load_expectations(self.cases, Path(tmp))

    def test_image_paths_cannot_traverse_to_other_local_files(self):
        case = copy.deepcopy(self.case)
        case["conversation"][0]["image"] = "../../../private.png"
        with self.assertRaisesRegex(ValueError, "bundled PNG"):
            demo.build_request(case)


if __name__ == "__main__":
    unittest.main()
