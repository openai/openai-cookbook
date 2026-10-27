"""Offline regression tests. Run with unittest discovery from the repository root."""

import contextlib
import csv
import hashlib
import io
import json
import os
import runpy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import urllib.error


def cell_source(cell):
    source = cell["source"]
    return source if isinstance(source, str) else "".join(source)


class RoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).with_name("customer_request_routing.ipynb")
        cls.cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
        cls.scope = {"__name__": "__main__"}
        with patch.dict(os.environ, {"RUN_DECISIONS_API": "0"}):
            with patch("urllib.request.urlopen", side_effect=AssertionError("Offline mode used the network")):
                with contextlib.redirect_stdout(io.StringIO()):
                    for cell in cls.cells:
                        if cell["cell_type"] == "code":
                            exec(cell_source(cell), cls.scope)

    def test_preview_makes_one_request_and_displays_response(self):
        response = {"answers": [{"type": "choice", "name": "route",
                                  "choice": "card_delivery", "confidence": 0.92}]}
        output = io.StringIO()
        runner = Path(__file__).with_name("run_customer_request_routing.py")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-placeholder"}):
            with patch.object(sys, "argv", [str(runner), "--preview"]):
                with patch("urllib.request.urlopen") as send:
                    send.return_value.__enter__.return_value = io.StringIO(json.dumps(response))
                    with contextlib.redirect_stdout(output):
                        runpy.run_path(str(runner), run_name="__main__")
        send.assert_called_once()
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/decisions")
        self.assertEqual(json.loads(request.data)["model"], "gpt-6-luna")
        self.assertIn("LIVE API RESPONSE", output.getvalue())
        self.assertIn('"confidence": 0.92', output.getvalue())

    def test_fixture_accounting_and_no_test_leakage_in_selection(self):
        self.assertEqual(self.scope["SELECTED_THRESHOLD"], 0.8)
        result = self.scope["evaluate"](self.scope["test_rows"], 0.8)
        self.assertEqual((result["accepted"], result["reviewed"], result["misroutes"]), (9, 3, 1))
        selected = min(self.scope["calibration_results"], key=lambda row: (
            row["average_loss"], -row["coverage"], row["threshold"]))
        self.assertEqual(selected["threshold"], 0.8)

    def test_refusals_and_malformed_answers_go_to_review(self):
        parse = self.scope["parse_prediction"]
        for response in [None, {}, {"answers": []}, {"answers": [None]},
                         {"answers": [{"type": "refusal", "name": "route"}]}]:
            with self.subTest(response=response):
                self.assertEqual(parse(response), (None, None))
        for confidence in [True, None, "0.9", -1, 2, float("nan"), float("inf")]:
            answer = {"type": "choice", "name": "route", "choice": "card_delivery", "confidence": confidence}
            self.assertEqual(parse({"answers": [answer]}), (None, None))

    def test_review_only_and_empty_evaluation(self):
        result = self.scope["evaluate"]([
            {"predicted": None, "confidence": None, "expected": "card_delivery"}], 0.8)
        self.assertEqual(result["coverage"], 0)
        self.assertIsNone(result["accepted_accuracy"])
        self.assertEqual(result["average_loss"], self.scope["REVIEW_COST"])
        with self.assertRaises(ValueError):
            self.scope["evaluate"]([], 0.8)

    def test_live_request_contract_and_no_label_transmission(self):
        body = {"answers": [{"type": "choice", "name": "route",
                              "choice": "card_delivery", "confidence": 0.9}]}
        with patch.dict(self.scope, {"API_KEY": "unit-test-sentinel"}):
            with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(body).encode())) as network:
                response, elapsed = self.scope["request_prediction"]("synthetic message")
        request = network.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(set(payload), {"model", "input", "questions"})
        self.assertEqual(payload["input"], "synthetic message")
        self.assertEqual(payload["model"], "gpt-6-luna")
        self.assertEqual(request.full_url, "https://api.openai.com/v1/decisions")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer unit-test-sentinel")
        self.assertEqual(self.scope["parse_prediction"](response), ("card_delivery", 0.9))
        self.assertGreaterEqual(elapsed, 0)

    def test_service_errors_are_not_retried(self):
        for error in [urllib.error.HTTPError("https://api.openai.com/v1/decisions", 429, "limited", {}, None),
                      urllib.error.URLError("offline")]:
            with patch("urllib.request.urlopen", side_effect=error) as network:
                with self.assertRaisesRegex(RuntimeError, "no automatic retry"):
                    self.scope["request_prediction"]("synthetic message")
                self.assertEqual(network.call_count, 1)

    def test_live_mode_needs_a_key_before_network(self):
        config = next(cell_source(cell) for cell in self.cells
                      if cell["cell_type"] == "code" and "MODE_FLAG =" in cell_source(cell))
        with patch.dict(os.environ, {"RUN_DECISIONS_API": "1"}, clear=True):
            with patch("urllib.request.urlopen") as network:
                with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                    exec(config, {})
                network.assert_not_called()

    def dataset_bytes(self, split):
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["text", "category"])
        for category in self.scope["SOURCE_TO_ROUTE"]:
            for index in range(30):
                writer.writerow([f"{split} {category} example {index}", category])
            writer.writerow([f"shared {category}", category])
        return output.getvalue().encode()

    def test_dataset_sampling_is_deterministic_and_disjoint(self):
        content = {name: self.dataset_bytes(name) for name in ("train.csv", "test.csv")}
        hashes = {name: hashlib.sha256(value).hexdigest() for name, value in content.items()}

        def download(url, timeout):
            return io.BytesIO(content[url.rsplit("/", 1)[-1]])

        with patch.dict(self.scope, {"DATASET_HASHES": hashes}):
            with patch("urllib.request.urlopen", side_effect=download):
                first = self.scope["load_public_cases"](10, 20)
                second = self.scope["load_public_cases"](10, 20)
                small = self.scope["load_public_cases"](2, 3)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 120)
        self.assertEqual(len(small), 20)
        self.assertTrue({case[0] for case in small}.issubset({case[0] for case in first}))
        train_texts = {case[3] for case in first if case[1] == "calibration"}
        test_texts = {case[3] for case in first if case[1] == "test"}
        self.assertTrue(train_texts.isdisjoint(test_texts))
        self.assertFalse(any(text.startswith("shared ") for text in train_texts))
        for route in self.scope["ROUTES"]:
            self.assertEqual(sum(case[1] == "calibration" and case[2] == route for case in first), 10)
            self.assertEqual(sum(case[1] == "test" and case[2] == route for case in first), 20)

    def test_invalid_sample_counts_fail_before_network(self):
        for counts in [(0, 3), (2, -1), (True, 3), (1.5, 3)]:
            with self.subTest(counts=counts), patch("urllib.request.urlopen") as network:
                with self.assertRaisesRegex(ValueError, "positive integers"):
                    self.scope["load_public_cases"](*counts)
                network.assert_not_called()

    def test_live_cli_obeys_default_and_configured_request_budgets(self):
        runner = Path(__file__).with_name("run_customer_request_routing.py")
        content = {name: self.dataset_bytes(name) for name in ("train.csv", "test.csv")}
        notebook = json.loads(runner.with_name("customer_request_routing.ipynb").read_text())
        data_source = cell_source(notebook["cells"][4])
        for name, value in content.items():
            data_source = data_source.replace(self.scope["DATASET_HASHES"][name],
                                              hashlib.sha256(value).hexdigest())
        notebook["cells"][4]["source"] = data_source
        variants = [([], 20), (["--calibration-per-route", "1", "--test-per-route", "2"], 12),
                    (["--calibration-per-route", "10", "--test-per-route", "20"], 120)]
        for options, expected_calls in variants:
            calls = []

            def network(request, timeout):
                if isinstance(request, str):
                    return io.BytesIO(content[request.rsplit("/", 1)[-1]])
                payload = json.loads(request.data)
                calls.append(payload)
                route = next(route for label, route in self.scope["SOURCE_TO_ROUTE"].items()
                             if label in payload["input"])
                return io.BytesIO(json.dumps({"answers": [{"type": "choice", "name": "route",
                    "choice": route, "confidence": 0.9}], "usage": {"input_tokens": 1}}).encode())

            with self.subTest(options=options):
                with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-placeholder"}):
                    with patch.object(sys, "argv", [str(runner), "--live", *options]):
                        with patch.object(Path, "read_text", return_value=json.dumps(notebook)):
                            with patch("urllib.request.urlopen", side_effect=network):
                                with contextlib.redirect_stdout(io.StringIO()):
                                    runpy.run_path(str(runner), run_name="__main__")
                self.assertEqual(len(calls), expected_calls)
                self.assertTrue(all(set(call) == {"model", "input", "questions"} for call in calls))

    def test_dataset_checksum_mismatch_stops_before_classification(self):
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"unexpected")) as network:
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                self.scope["load_public_cases"]()
            self.assertEqual(network.call_count, 1)


if __name__ == "__main__":
    unittest.main()
