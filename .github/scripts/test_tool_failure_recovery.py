"""Validate the published recovery notebook without network or model calls."""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import pkgutil
import socket
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import nbformat
import pandas as pd

import tool_failure_recovery
from tool_failure_recovery import evals
from tool_failure_recovery.agent import (
    SupportResponse,
    build_escalation_request,
    build_support_agent,
    create_delivery_escalation_operation,
    get_order_status_operation,
    search_orders_operation,
    serialize_outcome,
)


MODEL = "gpt-5.6"


class SyntheticRunResult:
    """Represent an SDK run using genuine tool evidence and no model calls."""

    def __init__(self, items: list[Any], response: SupportResponse) -> None:
        self.new_items = items
        self.response = response

    def final_output_as(self, response_type: type, **kwargs: Any) -> Any:
        return self.response


async def run_synthetic_agent(
    scenario: Any, agent: Any, context: Any
) -> SyntheticRunResult:
    items = []
    outcomes = []
    for index, tool_name in enumerate(scenario.expected_tools):
        if tool_name == "get_order_status":
            outcome = await get_order_status_operation(context, "ORDER-1001")
        elif tool_name == "search_orders":
            outcome = await search_orders_operation(
                context, **scenario.expected_search_filters
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
            (
                evals.ToolCallItem(
                    agent=agent,
                    raw_item={"call_id": call_id, "name": tool_name},
                ),
                evals.ToolCallOutputItem(
                    agent=agent,
                    raw_item={"call_id": call_id},
                    output=serialize_outcome(outcome),
                ),
            )
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
        message="An unverified refund was issued.",
    )
    return SyntheticRunResult(items, response)


class RecoveryNotebookTests(unittest.IsolatedAsyncioTestCase):
    async def test_modules_import_without_credentials(self) -> None:
        self.assertNotIn("OPENAI_API_KEY", os.environ)
        for module in pkgutil.iter_modules(tool_failure_recovery.__path__):
            importlib.import_module(f"tool_failure_recovery.{module.name}")

    async def test_customer_notebook_runs_offline(self) -> None:
        self.assertNotIn("OPENAI_API_KEY", os.environ)
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
        no_network = AssertionError("The offline notebook opened a network connection.")
        with patch.dict(
            os.environ,
            {"RUN_LIVE_AGENT": "false", "EXPORT_AGENTS_TRACES": "false"},
        ), patch.object(socket.socket, "connect", side_effect=no_network):
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

        offline_results = namespace["offline_results"]
        security_results = namespace["security_results"]
        self.assertGreaterEqual(len(offline_results), 12)
        self.assertTrue(offline_results["passed"].all())
        self.assertIn(
            "false_empty_order_search_recovers",
            set(offline_results["scenario"]),
        )
        self.assertEqual(len(security_results), 7)
        self.assertTrue(security_results["check"].is_unique)
        self.assertTrue(security_results["passed"].all())
        self.assertFalse(namespace["RUN_LIVE_AGENT"])

    async def test_native_agent_trajectories_and_release_gate(self) -> None:
        agent = build_support_agent(model=MODEL)
        active_scenario: Any = None

        async def run_without_network(
            cls: type, current_agent: Any, prompt: str, **kwargs: Any
        ) -> SyntheticRunResult:
            return await run_synthetic_agent(
                active_scenario, current_agent, kwargs["context"]
            )

        results = []
        with patch.object(evals.Runner, "run", classmethod(run_without_network)):
            for trial in (1, 2):
                for scenario in evals.LIVE_AGENT_SCENARIOS:
                    active_scenario = scenario
                    result = await evals.run_live_agent_scenario(
                        scenario, trial, model=MODEL, agent=agent
                    )
                    self.assertTrue(result.passed, result.failed_rules)
                    self.assertNotIn("refund", result.customer_message.lower())
                    results.append(result.model_dump(mode="json"))

        self.assertEqual(len(results), 2 * len(evals.LIVE_AGENT_SCENARIOS))
        frame = pd.DataFrame(results)
        evals.assert_live_eval_release_gate(frame, expected_repeats=2)
        with self.assertRaises((AssertionError, ValueError)):
            evals.assert_live_eval_release_gate(
                frame.iloc[0:0], expected_repeats=0
            )

        forged = frame[frame["trial"] == 1].copy()
        forged.loc[:, "passed"] = True
        forged.loc[:, "expected_side_effects"] = 99
        forged.loc[:, "side_effects"] = 99
        forged.loc[:, "side_effect_safety_passed"] = True
        with self.assertRaises((AssertionError, ValueError)):
            evals.assert_live_eval_release_gate(forged, expected_repeats=1)

        forged_message = frame.copy()
        forged_message.loc[:, "customer_message"] = "A refund was issued."
        forged_message.loc[:, "expected_customer_message"] = "A refund was issued."
        with self.assertRaises((AssertionError, ValueError)):
            evals.assert_live_eval_release_gate(
                forged_message, expected_repeats=2
            )


if __name__ == "__main__":
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ["RUN_LIVE_AGENT"] = "false"
    os.environ["EXPORT_AGENTS_TRACES"] = "false"
    unittest.main(verbosity=2)
