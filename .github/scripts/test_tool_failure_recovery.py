"""Exercise recovery boundaries locally without model calls or third-party CLIs."""

from __future__ import annotations

import ast
import asyncio
import importlib
import importlib.util
import inspect
import json
import os
import pkgutil
import socket
import subprocess
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import nbformat
import pandas as pd

import tool_failure_recovery
from tool_failure_recovery import evals, promptfoo
from tool_failure_recovery.agent import (
    SupportResponse,
    build_escalation_request,
    build_support_agent,
    create_delivery_escalation_operation,
    get_order_status_operation,
    search_orders_operation,
    serialize_outcome,
)
from tool_failure_recovery.offline import run_offline_recovery_suite
from tool_failure_recovery.security_tests import run_security_checks


DUMMY_API_KEY = "offline-test-placeholder-not-an-api-key"
MODEL = "gpt-5.6"


class SyntheticRunResult:
    """Return real SDK tool-call items without contacting a model."""

    def __init__(self, items: list[Any], response: SupportResponse) -> None:
        self.new_items = items
        self.response = response

    def final_output_as(self, response_type: type, **kwargs: Any) -> Any:
        return self.response


async def synthetic_agent_run(
    scenario: Any,
    agent: Any,
    context: Any,
) -> SyntheticRunResult:
    items = []
    outcomes = []
    for index, name in enumerate(scenario.expected_tools):
        if name == "get_order_status":
            outcome = await get_order_status_operation(context, "ORDER-1001")
        elif name == "search_orders":
            outcome = await search_orders_operation(
                context,
                **scenario.expected_search_filters,
            )
        else:
            request = build_escalation_request(
                context,
                "ORDER-1001",
                "The delayed shipment needs carrier investigation.",
            )
            outcome = await create_delivery_escalation_operation(context, request)
        call_id = f"offline-{scenario.name}-{index}"
        items.extend(
            [
                evals.ToolCallItem(
                    agent=agent,
                    raw_item={"call_id": call_id, "name": name},
                ),
                evals.ToolCallOutputItem(
                    agent=agent,
                    raw_item={"call_id": call_id},
                    output=serialize_outcome(outcome),
                ),
            ]
        )
        outcomes.append(outcome)

    escalation_id = (
        outcomes[-1].data["escalation_id"]
        if scenario.expected_disposition == "escalation_created"
        else None
    )
    response = SupportResponse(
        disposition=scenario.expected_disposition,
        order_id=scenario.expected_order_id,
        order_status=scenario.expected_order_status,
        escalation_id=escalation_id,
        confirmed_side_effect=scenario.expected_confirmed_side_effect,
        error_code=scenario.expected_error_code,
        message="An unverified refund was issued and the shipment arrived.",
    )
    return SyntheticRunResult(items, response)


def import_generated_module(name: str, path: Path) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise AssertionError(f"Could not import generated module: {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def recovery_result(
    scenario: Any,
    variables: dict[str, Any],
    *,
    trial: int = 1,
) -> dict[str, Any]:
    """Build deterministic provider evidence without invoking the provider."""
    return {
        "suite_version": evals.RECOVERY_EVAL_SUITE_VERSION,
        "scenario": scenario.name,
        "trial": trial,
        "model": variables["expected_model"],
        "run_id": variables["run_id"],
        "disposition": scenario.expected_disposition,
        "expected_disposition": scenario.expected_disposition,
        "expected_side_effects": scenario.expected_side_effects,
        "side_effects": scenario.expected_side_effects,
        "tool_sequence_passed": True,
        "tool_outcome_passed": True,
        "recovery_policy_passed": True,
        "response_contract_passed": True,
        "side_effect_safety_passed": True,
        "passed": True,
        "failed_rules": "",
    }


def generated_case_variables(artifacts: dict[str, Path]) -> dict[str, dict[str, Any]]:
    cases = json.loads(artifacts["tests"].read_text(encoding="utf-8"))
    return {case["description"]: case["vars"] for case in cases}


def exported_promptfoo_results(
    artifacts: dict[str, Path],
    *,
    repeats: int = 1,
) -> dict[str, Any]:
    variables_by_name = generated_case_variables(artifacts)
    outputs = []
    for trial in range(1, repeats + 1):
        for scenario in evals.LIVE_AGENT_SCENARIOS:
            variables = dict(variables_by_name[scenario.name])
            result = recovery_result(scenario, variables, trial=trial)
            metadata = {
                "run_id": result["run_id"],
                "model": result["model"],
                "suite_version": result["suite_version"],
                "case_id": result["scenario"],
                "trial": trial,
            }
            outputs.append(
                {
                    "testCase": {"vars": variables},
                    "response": {
                        "output": json.dumps(result),
                        "metadata": metadata,
                    },
                    "success": True,
                    "gradingResult": {"reason": "offline fixture"},
                    "score": 1.0,
                }
            )
    return {"results": {"outputs": outputs}}


class OfflineRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_package_modules_import_without_credentials(self) -> None:
        self.assertNotIn("OPENAI_API_KEY", os.environ)
        for module in pkgutil.iter_modules(tool_failure_recovery.__path__):
            importlib.import_module(f"tool_failure_recovery.{module.name}")

    async def test_complete_offline_recovery_and_security_suites(self) -> None:
        self.assertNotIn("OPENAI_API_KEY", os.environ)
        network_error = AssertionError("Offline recovery attempted a network call.")
        with patch.object(socket.socket, "connect", side_effect=network_error):
            offline_results = await run_offline_recovery_suite()
            security_results = await run_security_checks()
            notebook_path = (
                Path(__file__).resolve().parents[2]
                / "examples"
                / "agents_sdk"
                / "testing_agent_recovery_from_tool_failures.ipynb"
            )
            notebook = nbformat.read(notebook_path, as_version=4)
            namespace: dict[str, Any] = {
                "__name__": "__main__",
                "display": lambda value: value,
            }
            offline_environment = {
                "RUN_LIVE_AGENT": "false",
                "RUN_PROMPTFOO_EVAL": "false",
                "PROMPTFOO_ALLOW_EXTERNAL_EGRESS": "false",
                "EXPORT_AGENTS_TRACES": "false",
            }
            with patch.dict(os.environ, offline_environment):
                for cell in notebook.cells:
                    if cell.cell_type != "code" or cell.id == "install-dependencies":
                        continue
                    executable = compile(
                        cell.source,
                        f"{notebook_path}:{cell.id}",
                        "exec",
                        flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
                    )
                    result = eval(executable, namespace)
                    if inspect.isawaitable(result):
                        await result
        self.assertGreaterEqual(len(offline_results), 64)
        self.assertTrue(offline_results["passed"].all())
        self.assertTrue(security_results["check"].is_unique)
        self.assertTrue(security_results["passed"].all())
        self.assertTrue(namespace["offline_results"]["passed"].all())
        self.assertTrue(namespace["security_results"]["passed"].all())
        self.assertFalse(namespace["RUN_LIVE_AGENT"])
        self.assertFalse(namespace["RUN_PROMPTFOO_EVAL"])

    async def test_real_sdk_trajectories_and_fail_closed_release_gate(self) -> None:
        agent = build_support_agent(model=MODEL)
        active_scenario: Any = None

        async def run_without_network(
            cls: type,
            current_agent: Any,
            prompt: str,
            **kwargs: Any,
        ) -> SyntheticRunResult:
            self.assertIsNotNone(active_scenario)
            return await synthetic_agent_run(
                active_scenario,
                current_agent,
                kwargs["context"],
            )

        results = []
        with patch.object(evals.Runner, "run", classmethod(run_without_network)):
            for trial in (1, 2):
                for scenario in evals.LIVE_AGENT_SCENARIOS:
                    active_scenario = scenario
                    result = await evals.run_live_agent_scenario(
                        scenario,
                        trial,
                        model=MODEL,
                        agent=agent,
                    )
                    self.assertTrue(result.passed, result.failed_rules)
                    self.assertNotIn("refund", result.customer_message.lower())
                    results.append(result.model_dump(mode="json"))

        self.assertEqual(len(results), len(evals.LIVE_AGENT_SCENARIOS) * 2)
        result_frame = pd.DataFrame(results)
        evals.assert_live_eval_release_gate(result_frame, expected_repeats=2)

        with self.assertRaises((AssertionError, ValueError)):
            evals.assert_live_eval_release_gate(
                result_frame.iloc[0:0],
                expected_repeats=0,
            )

        forged_results = result_frame[result_frame["trial"] == 1].copy()
        forged_results.loc[:, "passed"] = True
        forged_results.loc[:, "side_effects"] = 99
        forged_results.loc[:, "side_effect_safety_passed"] = False
        with self.assertRaises((AssertionError, ValueError)):
            evals.assert_live_eval_release_gate(
                forged_results,
                expected_repeats=1,
            )


class PromptfooSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.environment_patch = patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": DUMMY_API_KEY,
                "OPENAI_BASE_URL": "https://private.example.invalid",
                "OPENAI_ORG_ID": "private-org-id",
                "OPENAI_ORGANIZATION": "private-org",
                "OPENAI_PROJECT": "private-project",
                "OPENAI_PROJECT_ID": "private-project-id",
                "GITHUB_TOKEN": "private-github-token",
                "AWS_SECRET_ACCESS_KEY": "private-cloud-secret",
                "PROMPTFOO_ALLOW_EXTERNAL_EGRESS": "true",
            },
        )
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)
        self.artifacts = promptfoo.write_promptfoo_recovery_artifacts(model=MODEL)

    def fake_which(self, name: str) -> str | None:
        return {
            "node": "/offline/mock/node",
            "promptfoo": "/offline/mock/promptfoo",
            "npx": "/offline/mock/npx",
            "pnpm": "/offline/mock/pnpm",
        }.get(name)

    def test_credential_boundaries_and_pinned_global_executable(self) -> None:
        captured: list[tuple[list[str], dict[str, Any]]] = []
        which_queries: list[str] = []

        def which(name: str) -> str | None:
            which_queries.append(name)
            return self.fake_which(name)

        def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured.append((command, kwargs))
            if command == ["/offline/mock/node", "--version"]:
                output = "v22.22.0\n"
            elif command == ["/offline/mock/promptfoo", "--version"]:
                output = promptfoo.PROMPTFOO_VERSION + "\n"
            else:
                output = "ok\n"
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

        with patch.object(promptfoo.shutil, "which", side_effect=which), patch.object(
            promptfoo.subprocess,
            "run",
            side_effect=fake_run,
        ):
            promptfoo.run_promptfoo_command(
                ["validate", "-c", str(self.artifacts["config"])],
                model=MODEL,
                allow_external_egress=True,
            )
            promptfoo.run_promptfoo_command(
                ["eval", "-c", str(self.artifacts["config"])],
                model=MODEL,
                allow_external_egress=True,
            )

        self.assertNotIn("npx", which_queries)
        self.assertNotIn("pnpm", which_queries)
        evaluation_children = []
        for command, kwargs in captured:
            environment = kwargs["env"]
            self.assertNotIn("GITHUB_TOKEN", environment)
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
            self.assertNotIn("OPENAI_ORGANIZATION", environment)
            self.assertNotIn("OPENAI_PROJECT", environment)
            self.assertEqual(environment["PROMPTFOO_DISABLE_TELEMETRY"], "true")
            self.assertEqual(environment["PROMPTFOO_DISABLE_UPDATE"], "true")
            if len(command) > 1 and command[1] == "eval":
                evaluation_children.append(command)
                self.assertEqual(environment["OPENAI_API_KEY"], DUMMY_API_KEY)
                self.assertEqual(environment["OPENAI_MODEL"], MODEL)
                self.assertEqual(
                    environment["OPENAI_BASE_URL"],
                    "https://private.example.invalid",
                )
                self.assertEqual(environment["OPENAI_ORG_ID"], "private-org-id")
                self.assertEqual(
                    environment["OPENAI_PROJECT_ID"],
                    "private-project-id",
                )
            else:
                self.assertFalse(any(name.startswith("OPENAI_") for name in environment))
        self.assertEqual(len(evaluation_children), 1)

    def test_missing_global_binary_never_falls_back_to_package_installers(self) -> None:
        subprocess_commands: list[list[str]] = []

        def no_global_binary(name: str) -> str | None:
            if name == "promptfoo":
                return None
            return self.fake_which(name)

        def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            subprocess_commands.append(command)
            self.assertEqual(command, ["/offline/mock/node", "--version"])
            self.assertNotIn("OPENAI_API_KEY", kwargs["env"])
            return subprocess.CompletedProcess(command, 0, stdout="v22.22.0\n")

        with patch.object(
            promptfoo.shutil,
            "which",
            side_effect=no_global_binary,
        ), patch.object(promptfoo.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, "automatic npx"):
                promptfoo.resolve_promptfoo_command(model=MODEL)
        self.assertEqual(subprocess_commands, [["/offline/mock/node", "--version"]])

    async def test_unapproved_egress_never_starts_a_subprocess(self) -> None:
        with patch.dict(os.environ, {"PROMPTFOO_ALLOW_EXTERNAL_EGRESS": "false"}):
            with patch.object(
                promptfoo.subprocess,
                "run",
                side_effect=AssertionError("Unapproved Promptfoo subprocess started."),
            ):
                with self.assertRaises(PermissionError):
                    promptfoo.run_promptfoo_command(
                        ["eval"],
                        allow_external_egress=True,
                    )
                with self.assertRaises(PermissionError):
                    await promptfoo.run_promptfoo_evaluation(
                        allow_external_egress=True,
                    )

    def test_generated_artifacts_use_fresh_run_scoped_results(self) -> None:
        old_results = self.artifacts["results"]
        old_results.write_text("stale previous success", encoding="utf-8")
        new_artifacts = promptfoo.write_promptfoo_recovery_artifacts(model=MODEL)
        self.assertNotEqual(new_artifacts["results"], old_results)
        self.assertTrue(old_results.exists())
        self.assertFalse(new_artifacts["results"].exists())
        cases = generated_case_variables(new_artifacts)
        run_id = new_artifacts["results"].stem.removeprefix("promptfoo_results-")
        self.assertTrue(all(variables["run_id"] == run_id for variables in cases.values()))
        self.assertTrue(
            all(variables["expected_model"] == MODEL for variables in cases.values())
        )

    async def test_provider_rejects_wrong_run_suite_and_model_before_execution(self) -> None:
        provider = import_generated_module("secure_provider_fixture", self.artifacts["provider"])
        scenario = evals.LIVE_AGENT_SCENARIOS[0]
        variables = generated_case_variables(self.artifacts)[scenario.name]
        for field, bad_value in (
            ("run_id", "stale-run"),
            ("suite_version", "0.0.0"),
            ("expected_model", "wrong-model"),
        ):
            invalid_variables = {**variables, field: bad_value}
            with patch.object(
                provider,
                "run_live_agent_scenario",
                side_effect=AssertionError("An invalid provider run reached the model."),
            ):
                result = await provider.call_api(
                    scenario.prompt,
                    {},
                    {"vars": invalid_variables},
                )
            self.assertIn("identity mismatch", result["error"])

    async def test_provider_binds_model_run_and_repeat_to_actual_output(self) -> None:
        provider = import_generated_module("repeat_provider_fixture", self.artifacts["provider"])
        scenario = evals.LIVE_AGENT_SCENARIOS[0]
        variables = generated_case_variables(self.artifacts)[scenario.name]
        expected = evals.LiveScenarioResult(
            suite_version=evals.RECOVERY_EVAL_SUITE_VERSION,
            scenario=scenario.name,
            trial=3,
            expected_disposition=scenario.expected_disposition,
            expected_side_effects=scenario.expected_side_effects,
            observed_tools=[],
            tool_events=[],
            tool_statuses=[],
            tool_attempts=[],
            disposition=scenario.expected_disposition,
            side_effects=scenario.expected_side_effects,
            tool_sequence_passed=True,
            tool_outcome_passed=True,
            recovery_policy_passed=True,
            response_contract_passed=True,
            side_effect_safety_passed=True,
            latency_seconds=0.0,
            trace_export="disabled",
            passed=True,
            failed_rules="",
        )
        with patch.object(
            provider,
            "run_live_agent_scenario",
            new=AsyncMock(return_value=expected),
        ) as mocked_runner:
            result = await provider.call_api(
                scenario.prompt,
                {},
                {"vars": variables, "repeatIndex": 2},
            )
        self.assertNotIn("error", result, result)
        mocked_runner.assert_awaited_once_with(scenario, 3, model=MODEL)
        output = json.loads(result["output"])
        self.assertEqual(output["run_id"], variables["run_id"])
        self.assertEqual(output["model"], MODEL)
        self.assertEqual(output["trial"], 3)
        self.assertEqual(result["metadata"]["run_id"], variables["run_id"])
        self.assertEqual(result["metadata"]["model"], MODEL)
        self.assertEqual(result["metadata"]["trial"], 3)

    def test_generated_contract_graders_cover_every_scenario(self) -> None:
        graders = import_generated_module("secure_grader_fixture", self.artifacts["assertions"])
        variables_by_name = generated_case_variables(self.artifacts)
        check_count = 0
        for scenario in evals.LIVE_AGENT_SCENARIOS:
            variables = variables_by_name[scenario.name]
            payload = json.dumps(recovery_result(scenario, variables))
            for grader in (
                graders.assert_trial_completed,
                graders.assert_recovery_contract,
                graders.assert_side_effect_safety,
            ):
                self.assertTrue(grader(payload, {"vars": variables})["pass"])
                check_count += 1
        self.assertEqual(check_count, len(evals.LIVE_AGENT_SCENARIOS) * 3)

    def test_result_parser_binds_run_model_case_suite_and_provider_metadata(self) -> None:
        payload = exported_promptfoo_results(self.artifacts, repeats=2)
        self.artifacts["results"].write_text(json.dumps(payload), encoding="utf-8")
        summary = promptfoo.promptfoo_result_summary(
            self.artifacts["results"],
            model=MODEL,
            repeats=2,
        )
        promptfoo.assert_promptfoo_eval_coverage(summary)
        self.assertEqual(summary["total"], len(evals.LIVE_AGENT_SCENARIOS) * 2)
        self.assertEqual(summary["model"], MODEL)
        self.assertEqual(
            summary["run_id"],
            self.artifacts["results"].stem.removeprefix("promptfoo_results-"),
        )
        for field, replacement in (
            ("run_id", "stale-run"),
            ("model", "incorrect-model"),
        ):
            corrupted_summary = {
                **summary,
                "rows": [dict(row) for row in summary["rows"]],
            }
            corrupted_summary["rows"][0][field] = replacement
            with self.assertRaisesRegex(AssertionError, field):
                promptfoo.assert_promptfoo_eval_coverage(corrupted_summary)

        invalid_coverage = [
            summary["rows"][:-1],
            summary["rows"][:-1] + [dict(summary["rows"][0])],
        ]
        for field, replacement in (
            ("suite_version", "0.0.0"),
            ("trial", 99),
            ("declared_case_id", "incorrect-case"),
        ):
            corrupted_rows = [dict(row) for row in summary["rows"]]
            corrupted_rows[0][field] = replacement
            invalid_coverage.append(corrupted_rows)
        for rows in invalid_coverage:
            with self.assertRaises((AssertionError, ValueError)):
                promptfoo.assert_promptfoo_eval_coverage(
                    {**summary, "rows": rows}
                )

        mutations = (
            ("run_id", "stale-run"),
            ("model", "incorrect-model"),
            ("suite_version", "0.0.0"),
            ("scenario", "incorrect-case"),
        )
        for field, replacement in mutations:
            corrupted = exported_promptfoo_results(self.artifacts)
            raw_result = json.loads(corrupted["results"]["outputs"][0]["response"]["output"])
            raw_result[field] = replacement
            corrupted["results"]["outputs"][0]["response"]["output"] = json.dumps(raw_result)
            self.artifacts["results"].write_text(json.dumps(corrupted), encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "provenance"):
                promptfoo.promptfoo_result_summary(self.artifacts["results"], model=MODEL)

        corrupted = exported_promptfoo_results(self.artifacts)
        corrupted["results"]["outputs"][0]["response"]["metadata"]["model"] = "wrong-model"
        self.artifacts["results"].write_text(json.dumps(corrupted), encoding="utf-8")
        with self.assertRaisesRegex(AssertionError, "metadata"):
            promptfoo.promptfoo_result_summary(self.artifacts["results"], model=MODEL)

    async def test_full_pipeline_rejects_previous_run_results(self) -> None:
        previous_results = self.artifacts["results"]
        previous_results.write_text(
            json.dumps(exported_promptfoo_results(self.artifacts)),
            encoding="utf-8",
        )

        def zero_exit_without_new_results(
            arguments: list[str],
            **kwargs: Any,
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(arguments, 0, stdout="offline mock")

        with patch.object(
            promptfoo,
            "assert_provider_runtime_error_classification",
            new=AsyncMock(),
        ), patch.object(
            promptfoo,
            "run_promptfoo_command",
            side_effect=zero_exit_without_new_results,
        ):
            with self.assertRaisesRegex(RuntimeError, "did not write results"):
                await promptfoo.run_promptfoo_evaluation(
                    model=MODEL,
                    allow_external_egress=True,
                )
        self.assertTrue(previous_results.exists())

    async def test_full_pipeline_accepts_fresh_exact_provenance(self) -> None:
        def write_fresh_results(
            arguments: list[str],
            **kwargs: Any,
        ) -> subprocess.CompletedProcess[str]:
            if arguments[0] == "eval":
                self.assertIn("--no-cache", arguments)
                self.assertIn("--no-write", arguments)
                self.assertIn("-o", arguments)
                artifacts = promptfoo.promptfoo_artifacts
                if artifacts is None:
                    raise AssertionError("Promptfoo artifacts were not prepared.")
                self.assertEqual(
                    arguments[arguments.index("-o") + 1],
                    str(artifacts["results"]),
                )
                artifacts["results"].write_text(
                    json.dumps(exported_promptfoo_results(artifacts)),
                    encoding="utf-8",
                )
            return subprocess.CompletedProcess(arguments, 0, stdout="offline mock")

        with patch.object(
            promptfoo,
            "assert_provider_runtime_error_classification",
            new=AsyncMock(),
        ), patch.object(
            promptfoo,
            "run_promptfoo_command",
            side_effect=write_fresh_results,
        ):
            summary = await promptfoo.run_promptfoo_evaluation(
                model=MODEL,
                allow_external_egress=True,
            )
        self.assertEqual(summary["passed"], len(evals.LIVE_AGENT_SCENARIOS))
        self.assertEqual(summary["model"], MODEL)


if __name__ == "__main__":
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ["RUN_LIVE_AGENT"] = "false"
    os.environ["RUN_PROMPTFOO_EVAL"] = "false"
    os.environ["PROMPTFOO_ALLOW_EXTERNAL_EGRESS"] = "false"
    os.environ["EXPORT_AGENTS_TRACES"] = "false"
    unittest.main(verbosity=2)
