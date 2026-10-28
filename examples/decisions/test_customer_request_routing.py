"""Offline application checks for the ten-message routing demo."""

import contextlib
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
                     parse_prediction, request_prediction, load_demo_messages)


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
            with patch.object(sys, "argv", ["demo", "--message", "My card is late."]):
                with patch("urllib.request.urlopen", return_value=io.BytesIO(json.dumps(ANSWER).encode())) as send:
                    with contextlib.redirect_stdout(output):
                        runpy.run_path(str(EXAMPLE / "run_customer_request_routing.py"), run_name="__main__")
        send.assert_called_once()
        self.assertIn("LIVE API RESPONSE", output.getvalue())
        self.assertIn('"route": "card_delivery"', output.getvalue())
        self.assertNotIn("test-only-placeholder", output.getvalue())

    def test_bundled_messages_cover_four_queues(self):
        cases = load_demo_messages()
        self.assertEqual(len(cases), 10)
        self.assertEqual(len({case["id"] for case in cases}), 10)
        self.assertEqual({case["source_label"] for case in cases}, set(SOURCE_TO_ROUTE))
        self.assertTrue(all(case["message"].strip() for case in cases))

    def test_default_cli_makes_ten_model_requests(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-placeholder"}):
            with patch.object(sys, "argv", ["demo"]):
                with patch("urllib.request.urlopen", side_effect=lambda *a, **k: io.BytesIO(json.dumps(ANSWER).encode())) as send:
                    with contextlib.redirect_stdout(io.StringIO()):
                        runpy.run_path(str(EXAMPLE / "run_customer_request_routing.py"), run_name="__main__")
        self.assertEqual(send.call_count, 10)
        for call, case in zip(send.call_args_list, load_demo_messages()):
            body = json.loads(call.args[0].data)
            self.assertEqual(set(body), {"model", "input", "questions"})
            self.assertEqual(body["input"], case["message"])

    def test_cli_missing_key_stops_before_network(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with patch.object(sys, "argv", ["demo"]):
                with patch("urllib.request.urlopen") as send:
                    with contextlib.redirect_stderr(io.StringIO()):
                        with self.assertRaises(SystemExit) as stopped:
                            runpy.run_path(str(EXAMPLE / "run_customer_request_routing.py"), run_name="__main__")
        self.assertEqual(stopped.exception.code, 2)
        send.assert_not_called()

    def test_notebook_empty_key_stops_before_model_requests(self):
        notebook = json.loads((EXAMPLE / "customer_request_routing.ipynb").read_text())
        cases = [{"id": str(i), "message": f"public sample {i}", "source_label": "card_arrival"}
                 for i in range(10)]
        scope = {}
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with patch.object(Path, "cwd", return_value=EXAMPLE):
                with patch("routing.load_demo_messages", return_value=cases):
                    with patch("getpass.getpass", return_value=""):
                        with patch("urllib.request.urlopen") as send:
                            with contextlib.redirect_stdout(io.StringIO()):
                                with self.assertRaisesRegex(RuntimeError, "No key supplied"):
                                    for cell in notebook["cells"]:
                                        if cell["cell_type"] == "code":
                                            exec(compile("".join(cell["source"]), "routing-notebook", "exec"), scope)
        send.assert_not_called()
        self.assertEqual(scope["outputs"], [])
        self.assertIsNone(scope["api_key"])
        self.assertEqual(len(ROUTES), 4)

    def test_notebook_hidden_key_is_not_printed_and_cleared_after_requests(self):
        notebook = json.loads((EXAMPLE / "customer_request_routing.ipynb").read_text())
        cases = [{"id": str(i), "message": f"public sample {i}", "source_label": "card_arrival"}
                 for i in range(10)]
        for fail in [False, True]:
            scope = {}
            output = io.StringIO()
            network_result = (urllib.error.URLError("offline") if fail else
                              lambda *a, **k: io.BytesIO(json.dumps(ANSWER).encode()))
            with self.subTest(fail=fail):
                with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
                    with patch.object(Path, "cwd", return_value=EXAMPLE):
                        with patch("getpass.getpass", return_value="hidden-test-placeholder") as prompt:
                            with patch("routing.load_demo_messages", return_value=cases):
                                with patch("urllib.request.urlopen", side_effect=network_result) as send:
                                    with contextlib.redirect_stdout(output):
                                        try:
                                            for cell in notebook["cells"]:
                                                if cell["cell_type"] == "code":
                                                    source = "".join(cell["source"])
                                                    exec(compile(source, "routing-notebook", "exec"), scope)
                                        except RuntimeError:
                                            if not fail:
                                                raise
            prompt.assert_called_once()
            self.assertEqual(send.call_count, 1 if fail else 10)
            self.assertIsNone(scope["api_key"])
            self.assertNotIn("hidden-test-placeholder", output.getvalue())
            if not fail:
                self.assertEqual(send.call_args.args[0].get_header("Authorization"),
                                 "Bearer hidden-test-placeholder")


if __name__ == "__main__":
    unittest.main()
