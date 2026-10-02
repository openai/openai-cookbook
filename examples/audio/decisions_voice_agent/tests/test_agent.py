import asyncio

import pytest
from cookbook_evaluation_backend import ApplicationBackend, DelegationHandoff

from agent import Choice, ExampleBackend, ScriptedRouter, SupportAgent


def handoff(text="Where is my order?", *, follow_up=False):
    return DelegationHandoff(
        task="Resolve the current user request from the conversation.",
        transcript_srt=f"1\n00:00:00,000 --> 00:00:01,000\nUSER: {text}",
        follow_up=follow_up,
    )


class RecordingTools:
    def __init__(self):
        self.calls = []

    async def call(self, name, arguments):
        self.calls.append((name, arguments))
        return {"order_status": "Shipped", "return_policy": "30 days"}[name]


class Events(list):
    async def emit(self, event):
        self.append(event)


class FixedRouter:
    def __init__(self, choice):
        self.choice = choice

    async def choose(self, request):
        return self.choice


async def test_public_backend_contract_uses_transcript_not_task():
    tools, events = RecordingTools(), Events()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools))
    assert isinstance(backend, ApplicationBackend)
    request = handoff()
    assert "order" not in request.task
    assert await backend.run(request, events.emit) == "Shipped"
    assert tools.calls == [("order_status", {"order_id": "DEMO-1001"})]
    assert [event["type"] for event in events] == [
        "routing.completed", "tool.called", "tool.completed"
    ]
    await backend.close()


async def test_policy_route_has_fixed_empty_arguments():
    tools = RecordingTools()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools))
    assert await backend.run(handoff("What is the return policy?"), Events().emit) == "30 days"
    assert tools.calls == [("return_policy", {})]
    await backend.close()


@pytest.mark.parametrize("text", ["Can you help with that?", "Status and policy, please.", ""])
async def test_ambiguous_or_unknown_input_clarifies_without_calling_tools(text):
    tools = RecordingTools()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools))
    assert "restate" in await backend.run(handoff(text), Events().emit)
    assert not tools.calls
    await backend.close()


async def test_followup_is_not_mistaken_for_complete_conversation():
    tools = RecordingTools()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools))
    await backend.run(handoff(), Events().emit)
    assert "restate" in await backend.run(
        handoff("What is the return policy?", follow_up=True), Events().emit
    )
    assert len(tools.calls) == 1
    await backend.close()


async def test_missing_transcript_does_not_route_on_generic_task():
    tools = RecordingTools()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools))
    assert "restate" in await backend.run(
        DelegationHandoff(task="Where is my order?", transcript_srt=""), Events().emit
    )
    assert not tools.calls
    await backend.close()


async def test_unsupported_mutation_does_not_call_tools():
    tools = RecordingTools()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools))
    assert "cannot change" in await backend.run(handoff("Cancel my order."), Events().emit)
    assert not tools.calls
    await backend.close()


@pytest.mark.parametrize("choice", ["delete_order", {"name": "order_status", "order_id": "OTHER"}])
async def test_invalid_backend_choice_cannot_supply_a_tool_or_arguments(choice):
    tools, events = RecordingTools(), Events()
    backend = ExampleBackend(SupportAgent(FixedRouter(choice), tools))
    assert "Routing failed" in await backend.run(handoff(), events.emit)
    assert not tools.calls
    assert events[0]["type"] == "routing.failed"
    await backend.close()


async def test_valid_but_wrong_route_is_a_semantic_failure():
    # A finite schema cannot establish semantic correctness. This injected wrong
    # selection is legal and executes, but fails the case's expected route/answer.
    tools, events = RecordingTools(), Events()
    backend = ExampleBackend(SupportAgent(FixedRouter(Choice.RETURN_POLICY), tools))
    answer = await backend.run(handoff("Where is my order?"), events.emit)
    expected_choice, expected_answer = Choice.ORDER_STATUS, "Shipped"
    assert events[0]["choice"] != expected_choice
    assert answer != expected_answer
    assert tools.calls == [("return_policy", {})]
    await backend.close()


async def test_unavailable_tool_is_not_reported_as_success():
    class Unavailable:
        async def call(self, name, arguments):
            raise ConnectionError("synthetic outage")

    events = Events()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), Unavailable()))
    assert "no verified answer" in await backend.run(handoff(), events.emit)
    assert events[-1]["type"] == "tool.failed"
    assert not any(event["type"] == "tool.completed" for event in events)
    await backend.close()


class BlockingTools:
    def __init__(self, *, swallow_cancellation=False):
        self.started = asyncio.Event()
        self.stopped = asyncio.Event()
        self.swallow_cancellation = swallow_cancellation

    async def call(self, name, arguments):
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            if self.swallow_cancellation:
                return "Stale shipped answer"
            raise
        finally:
            self.stopped.set()


@pytest.mark.parametrize("swallow", [False, True])
async def test_interrupt_cancels_and_suppresses_stale_results(swallow):
    tools, events = BlockingTools(swallow_cancellation=swallow), Events()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools))
    run = asyncio.create_task(backend.run(handoff(), events.emit))
    await asyncio.wait_for(tools.started.wait(), timeout=1)
    await backend.interrupt()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert tools.stopped.is_set()
    assert not any(event["type"] == "tool.completed" for event in events)
    await backend.close()


async def test_caller_cancellation_propagates_and_closes_work():
    tools, events = BlockingTools(swallow_cancellation=True), Events()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools))
    run = asyncio.create_task(backend.run(handoff(), events.emit))
    await asyncio.wait_for(tools.started.wait(), timeout=1)
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert tools.stopped.is_set()
    assert not any(event["type"] == "tool.completed" for event in events)
    await backend.close()


async def test_timeout_closes_work_and_returns_explicit_failure():
    tools, events = BlockingTools(), Events()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools), timeout=0.02)
    answer = await asyncio.wait_for(backend.run(handoff(), events.emit), timeout=1)
    assert "timed out" in answer
    assert tools.stopped.is_set()
    assert events[-1] == {"type": "routing.failed", "error": "timeout"}
    await backend.close()


async def test_overlapping_requests_are_not_queued_or_executed():
    tools = BlockingTools()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), tools))
    run = asyncio.create_task(backend.run(handoff(), Events().emit))
    await asyncio.wait_for(tools.started.wait(), timeout=1)
    assert "still running" in await backend.run(handoff(), Events().emit)
    await backend.close()
    with pytest.raises(asyncio.CancelledError):
        await run
    await backend.close()
    with pytest.raises(RuntimeError, match="closed"):
        await backend.run(handoff(), Events().emit)


@pytest.mark.parametrize("timeout_case", [True, False])
async def test_close_during_failure_event_suppresses_returned_answer(timeout_case):
    entered, release = asyncio.Event(), asyncio.Event()

    async def emit(event):
        if event["type"] == "routing.failed":
            entered.set()
            await release.wait()

    router = ScriptedRouter() if timeout_case else FixedRouter("invalid")
    backend = ExampleBackend(SupportAgent(router, BlockingTools()), timeout=0.01)
    run = asyncio.create_task(backend.run(handoff(), emit))
    await asyncio.wait_for(entered.wait(), timeout=1)
    await backend.close()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await run


async def test_empty_tool_output_is_explicit_failure():
    class EmptyTools:
        async def call(self, name, arguments):
            return ""

    events = Events()
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), EmptyTools()))
    assert "no verified answer" in await backend.run(handoff(), events.emit)
    assert events[-1]["type"] == "tool.failed"
    await backend.close()


async def test_uncooperative_dependency_has_bounded_shutdown_failure():
    started, release = asyncio.Event(), asyncio.Event()

    class UncooperativeTools:
        async def call(self, name, arguments):
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
            return "Stale answer"

    events = Events()
    backend = ExampleBackend(
        SupportAgent(ScriptedRouter(), UncooperativeTools()), timeout=0.01, shutdown_timeout=0.01
    )
    run = asyncio.create_task(backend.run(handoff(), events.emit))
    await asyncio.wait_for(started.wait(), timeout=1)
    try:
        with pytest.raises(RuntimeError, match="shutdown deadline"):
            await asyncio.wait_for(run, timeout=1)
        assert "still running" in await backend.run(handoff(), events.emit)
        assert not any(event["type"] == "tool.completed" for event in events)
    finally:
        release.set()
        await backend.close()
