"""Offline application checks for the one-request routing demo."""

import contextlib
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch
import urllib.error

from routing import (API_URL, MODEL, ROUTES, SOURCE_TO_ROUTE, build_request,
                     parse_prediction, request_prediction, sample_public_messages)


EXAMPLE = Path(__file__).resolve().parent
ANSWER = {"answers": [{"type": "choice", "name": "route",
                       "choice": "card_delivery", "confidence": 0.92}]}


class RoutingTests(unittest.TestCase):
    def test_request_contract_and_no_key_in_body(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-placeholder"}):
            with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(ANSWER).encode())) as send:
                response, latency = request_prediction("My new card is late.")
        send.assert_called_once()
        request = send.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(set(body), {"model", "input", "questions"})
        self.assertEqual((request.full_url, request.method, body["model"]), (API_URL, "POST", MODEL))
        self.assertEqual(body["input"], "My new card is late.")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-only-placeholder")
        self.assertNotIn("test-only-placeholder", request.data.decode())
        self.assertEqual(parse_prediction(response), ("card_delivery", 0.92))
        self.assertGreaterEqual(latency, 0)

    def test_missing_key_and_empty_message_stop_before_network(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with patch("urllib.request.urlopen") as send:
                with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                    request_prediction("My card is late.")
                send.assert_not_called()
        for message in [None, "", "  "]:
            with self.assertRaises(ValueError):
                build_request(message)

    def test_refusals_and_invalid_answers_go_to_review(self):
        for answer in [None, {}, {"answers": []}, {"answers": [None]},
                       {"answers": [{"type": "refusal", "name": "route"}]}]:
            self.assertEqual(parse_prediction(answer), (None, None))
        for confidence in [True, None, "0.9", -1, 2, float("nan"), float("inf")]:
            answer = {"answers": [{"type": "choice", "name": "route",
                                    "choice": "card_delivery", "confidence": confidence}]}
            self.assertEqual(parse_prediction(answer), (None, None))
        for field, value in [("name", "wrong_question"), ("choice", "unknown")]:
            answer = json.loads(json.dumps(ANSWER))
            answer["answers"][0][field] = value
            self.assertEqual(parse_prediction(answer), (None, None))

    def test_http_network_and_invalid_json_errors_are_not_retried(self):
        errors = [urllib.error.HTTPError(API_URL, 429, "limited", {}, None),
                  urllib.error.URLError("offline")]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-placeholder"}):
            for error in errors:
                with patch("urllib.request.urlopen", side_effect=error) as send:
                    with self.assertRaisesRegex(RuntimeError, "no automatic retry"):
                        request_prediction("My card is late.")
                    send.assert_called_once()
            with patch("urllib.request.urlopen", return_value=io.BytesIO(b"invalid JSON")) as send:
                with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                    request_prediction("My card is late.")
                send.assert_called_once()

    def test_cli_custom_message_makes_one_request_and_displays_response(self):
        output = io.StringIO()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-placeholder"}):
            with patch.object(sys, "argv", ["demo", "--live", "--message", "My card is late."]):
                with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(ANSWER).encode())) as send:
                    with contextlib.redirect_stdout(output):
                        runpy.run_path(str(EXAMPLE / "run_customer_request_routing.py"), run_name="__main__")
        send.assert_called_once()
        self.assertIn("LIVE API RESPONSE", output.getvalue())
        self.assertIn('"route": "card_delivery"', output.getvalue())
        self.assertNotIn("test-only-placeholder", output.getvalue())

    def test_public_sampler_is_balanced_deterministic_and_checksum_verified(self):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["text", "category"])
        for label in SOURCE_TO_ROUTE:
            for index in range(3):
                writer.writerow([f"synthetic {label} {index}", label])
        writer.writerow(["conflicting", "card_arrival"])
        writer.writerow(["conflicting", "cancel_transfer"])
        content = stream.getvalue().encode()
        with patch("routing.DATASET_SHA256", hashlib.sha256(content).hexdigest()):
            def download(*args, **kwargs):
                return io.BytesIO(content)
            with patch("urllib.request.urlopen", side_effect=download):
                first = sample_public_messages(2)
                second = sample_public_messages(2)
                self.assertEqual(first, second)
                self.assertEqual(len(first), 8)
                self.assertEqual(len({case["id"] for case in first}), 8)
                self.assertFalse(any(case["message"] == "conflicting" for case in first))
                for label in SOURCE_TO_ROUTE:
                    self.assertEqual(sum(case["source_label"] == label for case in first), 2)
                with self.assertRaisesRegex(ValueError, "Only 3"):
                    sample_public_messages(4)
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b"unexpected")):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                sample_public_messages()

    def test_cli_batch_sizes_control_model_call_count(self):
        for options, count in [([], 4), (["--samples-per-route", "2"], 8)]:
            cases = [{"id": str(i), "message": f"public message {i}", "source_label": "local label"}
                     for i in range(count)]
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-placeholder"}):
                with patch.object(sys, "argv", ["demo", "--live", *options]):
                    with patch("routing.sample_public_messages", return_value=cases) as sample:
                        with patch("urllib.request.urlopen", side_effect=lambda *a, **k: io.BytesIO(json.dumps(ANSWER).encode())) as send:
                            with contextlib.redirect_stdout(io.StringIO()):
                                runpy.run_path(str(EXAMPLE / "run_customer_request_routing.py"), run_name="__main__")
            sample.assert_called_once_with(count // 4)
            self.assertEqual(send.call_count, count)
            for call in send.call_args_list:
                self.assertEqual(set(json.loads(call.args[0].data)), {"model", "input", "questions"})

    def test_cli_default_is_no_network_request_preview(self):
        with patch.object(sys, "argv", ["demo"]):
            with patch("urllib.request.urlopen") as send:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    runpy.run_path(str(EXAMPLE / "run_customer_request_routing.py"), run_name="__main__")
        send.assert_not_called()
        self.assertIn("REQUEST PREVIEW ONLY", output.getvalue())

    def test_notebook_runs_top_to_bottom_offline(self):
        notebook = json.loads((EXAMPLE / "customer_request_routing.ipynb").read_text())
        with patch.dict(os.environ, {"RUN_DECISIONS_API": "0"}):
            with patch.object(Path, "cwd", return_value=EXAMPLE):
                with patch("urllib.request.urlopen") as send:
                    with contextlib.redirect_stdout(io.StringIO()):
                        scope = {}
                        for cell in notebook["cells"]:
                            if cell["cell_type"] == "code":
                                exec(compile("".join(cell["source"]), "routing-notebook", "exec"), scope)
        send.assert_not_called()
        self.assertEqual(scope["outputs"], [])
        self.assertEqual(len(ROUTES), 4)


if __name__ == "__main__":
    unittest.main()
