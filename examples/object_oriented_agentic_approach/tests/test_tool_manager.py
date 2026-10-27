"""Offline checks, run from the repository root:

python3 -B -m unittest discover \
    -s examples/object_oriented_agentic_approach/tests
"""

import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


# Import the example's source without importing provider clients or factories.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

from object_oriented_agents.core_classes.base_agent import BaseAgent
from object_oriented_agents.core_classes.tool_interface import ToolInterface
from object_oriented_agents.core_classes.tool_manager import ToolManager
from object_oriented_agents.services.language_model_interface import (
    LanguageModelInterface,
)


MODEL_NAME = "offline-model"
FINAL_ANSWER = "Both results are ready.\nUse them in the requested order."
DEVELOPER_PROMPT = "Use the registered tools."
USER_TASK = "Collect the requested results."


def make_tool_call(call_id, name, value):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(
            name=name, arguments=json.dumps({"value": value})
        ),
    )


class FakeTool(ToolInterface):
    """Record actual tool executions and return a distinguishable string."""

    def __init__(self, name, executions):
        self.name = name
        self.executions = executions

    def get_definition(self):
        return {
            "function": {
                "name": self.name,
                "description": "Return a value for an offline test.",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            }
        }

    def run(self, arguments):
        self.executions.append((self.name, arguments))
        return f"{self.name}: {arguments['value']}\nfinished"


class FakeLanguageModel(LanguageModelInterface):
    """Reject incomplete tool results before producing a final answer."""

    def __init__(self, tool_calls, executions):
        self.assistant_message = SimpleNamespace(
            role="assistant", content=None, tool_calls=tool_calls
        )
        self.executions = executions
        self.requests = []

    def generate_completion(self, **params):
        request = dict(params)
        request["messages"] = list(params["messages"])
        self.requests.append(request)
        if len(self.requests) == 1:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=self.assistant_message)]
            )

        expected_executions = []
        expected_messages = [
            {"role": "developer", "content": DEVELOPER_PROMPT},
            {"role": "user", "content": USER_TASK},
            self.assistant_message,
        ]
        for call in self.assistant_message.tool_calls:
            arguments = json.loads(call.function.arguments)
            expected_executions.append((call.function.name, arguments))
            expected_messages.append({
                "role": "tool",
                "content": (
                    f"{call.function.name}: {arguments['value']}\nfinished"
                ),
                "tool_call_id": call.id,
            })

        if self.executions != expected_executions:
            raise AssertionError(
                f"Incomplete or unordered executions: {self.executions!r}; "
                f"expected {expected_executions!r} before final completion"
            )
        if request["messages"] != expected_messages:
            raise AssertionError(
                f"Incomplete or unordered results: {request['messages']!r}; "
                f"expected {expected_messages!r}"
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content=FINAL_ANSWER, tool_calls=None
            ))]
        )


class FakeAgent(BaseAgent):
    """Exercise the public BaseAgent task path with registered fake tools."""

    def __init__(self, model, tools, reasoning_effort=None):
        logger = logging.getLogger("offline-tool-manager")
        logger.addHandler(logging.NullHandler())
        super().__init__(
            developer_prompt=DEVELOPER_PROMPT,
            model_name=MODEL_NAME,
            logger=logger,
            language_model_interface=model,
            reasoning_effort=reasoning_effort,
        )
        self.tools_to_register = tools
        self.setup_tools()

    def setup_tools(self):
        self.tool_manager = ToolManager(
            logger=self.logger,
            language_model_interface=self.language_model_interface,
        )
        for tool in self.tools_to_register:
            self.tool_manager.register_tool(tool)


class ToolManagerTests(unittest.TestCase):
    def make_agent(self, calls, names=("probe",), reasoning_effort=None):
        executions = []
        model = FakeLanguageModel(calls, executions)
        tools = [FakeTool(name, executions) for name in names]
        agent = FakeAgent(model, tools, reasoning_effort)
        return agent, model, executions

    def assert_final_answer(self, agent, model, executions, expected):
        self.assertEqual(agent.task(USER_TASK), FINAL_ANSWER)
        self.assertEqual(executions, expected)
        self.assertEqual(len(model.requests), 2)
        follow_up = model.requests[1]
        self.assertEqual(follow_up["model"], MODEL_NAME)
        self.assertNotIn("tools", follow_up)
        self.assertEqual(
            sum(message is model.assistant_message
                for message in follow_up["messages"]),
            1,
        )
        self.assertEqual(agent.messages.get_messages()[-1], {
            "role": "assistant", "content": FINAL_ANSWER
        })

    def test_repeated_calls_execute_and_answer_every_id(self):
        calls = [make_tool_call("call_0", "probe", "A"),
                 make_tool_call("call_1", "probe", "B")]
        agent, model, executions = self.make_agent(calls)
        self.assert_final_answer(agent, model, executions, [
            ("probe", {"value": "A"}), ("probe", {"value": "B"})
        ])

    def test_distinct_tools_execute_in_call_order(self):
        calls = [make_tool_call("call_second", "second", "B"),
                 make_tool_call("call_first", "first", "A")]
        agent, model, executions = self.make_agent(
            calls, names=("first", "second")
        )
        self.assert_final_answer(agent, model, executions, [
            ("second", {"value": "B"}), ("first", {"value": "A"})
        ])
        self.assertEqual(
            model.requests[0]["tools"],
            agent.tool_manager.get_tool_definitions(),
        )

    def test_single_call_final_answer_compatibility(self):
        agent, model, executions = self.make_agent([
            make_tool_call("call_single", "probe", "A")
        ])
        self.assert_final_answer(agent, model, executions, [
            ("probe", {"value": "A"})
        ])

    def test_reasoning_effort_forwarding_and_omission(self):
        for default, override, expected in [
            (None, None, None), ("high", None, "high"),
            ("high", "medium", "medium"),
        ]:
            with self.subTest(default=default, override=override):
                agent, model, _ = self.make_agent([
                    make_tool_call("call_0", "probe", "A"),
                    make_tool_call("call_1", "probe", "B"),
                ], reasoning_effort=default)
                self.assertEqual(agent.task(
                    USER_TASK, reasoning_effort=override
                ), FINAL_ANSWER)
                self.assertEqual(len(model.requests), 2)
                for request in model.requests:
                    self.assertEqual(request["model"], MODEL_NAME)
                    if expected is None:
                        self.assertNotIn("reasoning_effort", request)
                    else:
                        self.assertEqual(request["reasoning_effort"], expected)

    def test_single_call_raw_return_compatibility(self):
        self.assert_raw_first_call([
            make_tool_call("call_single", "probe", "A")
        ])

    def test_multiple_call_raw_return_keeps_first_call_only(self):
        self.assert_raw_first_call([
            make_tool_call("call_0", "probe", "A"),
            make_tool_call("call_1", "probe", "B"),
        ])

    def assert_raw_first_call(self, calls):
        agent, model, executions = self.make_agent(calls)
        result = agent.task(USER_TASK, return_tool_response_as_is=True)
        self.assertEqual(result, "probe: A\nfinished")
        self.assertIsInstance(result, str)
        self.assertEqual(executions, [("probe", {"value": "A"})])
        self.assertEqual(len(model.requests), 1)
        self.assertEqual(agent.messages.get_messages(), [
            {"role": "developer", "content": DEVELOPER_PROMPT},
            {"role": "user", "content": USER_TASK},
            {"role": "assistant", "content": result},
        ])


if __name__ == "__main__":
    unittest.main()
