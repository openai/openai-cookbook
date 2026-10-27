"""Offline checks for Promptfoo preparation and result accounting."""

import copy
import json
import unittest

from routing_eval import build_config, config_matches, notebook_definitions, result_rows


class PromptfooRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope = notebook_definitions()

    def setUp(self):
        self.config = build_config(self.scope["offline_cases"],
                                   self.scope["QUESTION"], self.scope["MODEL"])
        self.export = {"results": {"results": [{
            "testCase": test,
            "response": {"output": json.dumps(self.scope["fixture_response"](
                test["vars"]["case_id"]))},
        } for test in self.config["tests"]]}}

    def test_config_uses_native_decisions_and_does_not_render_labels(self):
        self.assertEqual(self.config["prompts"], ["{{message}}"])
        self.assertEqual(self.config["providers"][0]["id"], "openai:decisions:gpt-6-luna")
        self.assertEqual(self.config["providers"][0]["config"]["maxRetries"], 0)
        self.assertFalse(self.config["sharing"])

    def test_fixture_grades_match_notebook(self):
        rows = result_rows(self.export, self.config, self.scope)
        held_out = [r for r in rows if r["split"] == "test"]
        result = self.scope["evaluate"](held_out, 0.8)
        self.assertEqual((result["accepted"], result["reviewed"], result["misroutes"]), (9, 3, 1))

    def test_incomplete_duplicate_and_changed_labels_are_rejected(self):
        variants = []
        missing = copy.deepcopy(self.export)
        missing["results"]["results"].pop()
        variants.append(missing)
        duplicate = copy.deepcopy(self.export)
        duplicate["results"]["results"].append(duplicate["results"]["results"][0])
        variants.append(duplicate)
        changed = copy.deepcopy(self.export)
        changed["results"]["results"][0]["testCase"]["vars"]["expected"] = "foreign"
        variants.append(changed)
        for export in variants:
            with self.subTest(export=export):
                with self.assertRaises(ValueError):
                    result_rows(export, self.config, self.scope)

    def test_provider_error_is_not_scored_as_a_refusal(self):
        self.export["results"]["results"][0]["error"] = "HTTP 429"
        with self.assertRaisesRegex(ValueError, "Provider/runtime error"):
            result_rows(self.export, self.config, self.scope)

    def test_failed_assertion_with_valid_refusal_is_reviewed(self):
        result = self.export["results"]["results"][0]
        result.update({"success": False, "error": "Custom function returned false",
                       "failureReason": 1, "gradingResult": {"pass": False}})
        result["response"]["output"] = json.dumps({
            "answers": [{"type": "refusal", "name": "route"}]})
        rows = result_rows(self.export, self.config, self.scope)
        self.assertIsNone(rows[0]["predicted"])
        self.assertEqual(self.scope["evaluate"]([rows[0]], 0)["reviewed"], 1)

    def test_runtime_failure_with_partial_output_is_rejected(self):
        result = self.export["results"]["results"][0]
        result.update({"failureReason": 2, "error": "HTTP 429"})
        with self.assertRaisesRegex(ValueError, "Provider/runtime error"):
            result_rows(self.export, self.config, self.scope)

    def test_export_defaults_allowed_but_changed_question_rejected(self):
        exported = copy.deepcopy(self.config)
        exported["basePath"] = "/local/exporter/default"
        self.assertTrue(config_matches(exported, self.config))
        exported["providers"][0]["config"]["questions"][0]["name"] = "changed"
        self.assertFalse(config_matches(exported, self.config))


if __name__ == "__main__":
    unittest.main()
