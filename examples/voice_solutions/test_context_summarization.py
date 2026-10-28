"""Check archived Realtime summaries without credentials, network or audio devices.

Run from the Cookbook root:
    python3 examples/voice_solutions/test_context_summarization.py
"""
import ast
import asyncio
import base64
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from io import StringIO
import json
from pathlib import Path
from types import SimpleNamespace
from typing import List, Literal

notebook = Path(__file__).resolve().parents[1] / "Context_summarization_with_realtime_api.ipynb"
cells = json.loads(notebook.read_text())["cells"]

def definitions(namespace, names):
    """Load only named sample definitions, without executing dependency/setup cells."""
    found = set()
    for cell in cells:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        module = ast.parse(source, filename=str(notebook))
        for node in module.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in names:
                    exec(compile(ast.Module(body=[node], type_ignores=[]), str(notebook), "exec"),
                         namespace)
                    found.add(node.name)
    assert found == set(names), f"Missing sample definitions: {set(names) - found}"


async def scenario(outcome):
    namespace = dict(globals())
    namespace.update(SAMPLE_RATE_HZ=24000, SUMMARY_TRIGGER=20, KEEP_LAST_TURNS=1,
                     BYTES_PER_SAMPLE=2, openai=SimpleNamespace(api_key="synthetic"))
    definitions(namespace, {
        "Turn", "ConversationState", "summarise_and_prune", "maybe_summarise", "realtime_session"
    })
    sent, summaries, states = [], [], []
    original = namespace["ConversationState"]

    def new_state():
        state = original()
        states.append(state)
        return state

    async def summary(text):
        summaries.append(text)
        if outcome == "during-summary":
            states[0].history.append(namespace["Turn"]("user", "user2"))
            await asyncio.sleep(0.01)
        return "summary including: " + text

    async def mic(queue):
        await asyncio.Future()

    async def upload(queue, ws):
        while await queue.get() is not None:
            pass

    class Socket:
        index = 0
        transcript_present = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send(self, payload):
            event = json.loads(payload)
            if event["type"] == "conversation.item.delete" and not self.transcript_present:
                raise AssertionError("Deleted a user turn before authoritative transcription")
            sent.append(event)

        async def recv(self):
            return json.dumps({"type": "session.created", "session": {"id": "s1"}})

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(0.04)
            events = [
                {"type": "conversation.item.added", "item": {
                    "id": "user1", "role": "user", "content": [
                        {"type": "input_audio", "transcript": None}]}},
                {"type": "response.done", "response": {
                    "status": "completed", "usage": {"total_tokens": 50},
                    "output": [{"role": "assistant", "id": "a1",
                                "content": [{"transcript": "assistant answer"}]}]}},
            ]
            if self.index == 2:
                assert not summaries, f"Summary omitted unready user text: {summaries!r}"
                assert not [e for e in sent if e["type"] == "conversation.item.delete"]
                assert any(t.item_id == "user1" for t in states[0].history), "Lost pending user turn"
                if outcome in ("completed", "during-summary"):
                    self.transcript_present = True
                    events.append({"type": "conversation.item.input_audio_transcription.completed",
                                   "item_id": "user1", "content_index": 0,
                                   "transcript": "user's necessary question"})
                elif outcome == "failed":
                    events.append({"type": "conversation.item.input_audio_transcription.failed",
                                   "item_id": "user1", "content_index": 0,
                                   "error": {"message": "synthetic transcription failed"}})
            if self.index >= len(events):
                raise StopAsyncIteration
            event = events[self.index]
            self.index += 1
            return json.dumps(event)

    socket = Socket()
    namespace.update(ConversationState=new_state, run_summary_llm=summary,
                     print_history=lambda state: None, mic_to_queue=mic,
                     queue_to_websocket=upload,
                     websockets=SimpleNamespace(connect=lambda *args, **kwargs: socket))
    error = None
    with redirect_stdout(StringIO()):
        try:
            await namespace["realtime_session"](enable_playback=False)
            await asyncio.sleep(0.04)
        except RuntimeError as exc:
            error = exc
    if outcome in ("completed", "during-summary"):
        assert error is None, error
        assert summaries == ["user: user's necessary question"], summaries
        assert any(e["type"] == "conversation.item.delete" and e["item_id"] == "user1"
                   for e in sent), sent
        if outcome == "during-summary":
            assert any(t.item_id == "user2" and t.text is None for t in states[0].history), (
                "New user turn received during summary was lost"
            )
            assert not any(e["type"] == "conversation.item.delete" and e["item_id"] == "user2"
                           for e in sent)
    elif outcome == "failed":
        assert error is not None, "Failed transcription must not silently continue into pruning"
        assert "user1" in str(error), error
        assert any(t.item_id == "user1" and t.text is None for t in states[0].history)
    else:
        assert error is None, error
        assert any(t.item_id == "user1" and t.text is None for t in states[0].history)
        assert not summaries

async def before_task_start():
    namespace = dict(globals())
    namespace.update(SUMMARY_TRIGGER=20, KEEP_LAST_TURNS=1)
    definitions(namespace, {"Turn", "ConversationState", "summarise_and_prune", "maybe_summarise"})
    sent, summaries = [], []
    async def summarize(text):
        summaries.append(text)
        return "summary"
    async def send(payload):
        sent.append(json.loads(payload))
    namespace.update(run_summary_llm=summarize, print_history=lambda state: None)
    turn = namespace["Turn"]
    state = namespace["ConversationState"](
        history=[turn("user", "user1", "required question"), turn("assistant", "a1", "answer")],
        latest_tokens=50)
    # Model buffered websocket events arriving before the scheduled task begins.
    namespace["maybe_summarise"](SimpleNamespace(send=send), state)
    state.history.extend([turn("user", "user2"), turn("assistant", "a2", "answer2")])
    await asyncio.sleep(0.04)
    assert summaries == ["user: required question"], summaries
    assert [t.item_id for t in state.history] == ["sum_001", "a1", "user2", "a2"], state.history
    assert [e["item_id"] for e in sent if e["type"] == "conversation.item.delete"] == ["user1"]
    print("PASS before-task-start")

async def response_end(status):
    namespace = dict(globals())
    namespace.update(SAMPLE_RATE_HZ=24000, BYTES_PER_SAMPLE=2,
                     openai=SimpleNamespace(api_key="synthetic"))
    definitions(namespace, {"Turn", "ConversationState", "realtime_session"})
    states, played = [], []
    original = namespace["ConversationState"]

    def new_state():
        state = original()
        states.append(state)
        return state

    async def mic(queue):
        await asyncio.Future()

    async def upload(queue, ws):
        while await queue.get() is not None:
            pass

    def audio(response_id, pcm):
        return {"type": "response.output_audio.delta", "response_id": response_id,
                "delta": base64.b64encode(pcm).decode()}

    events = [
        audio("interrupted", b"old!"),
        # The next response may already be buffered when the first one ends.
        audio("next", b"next"),
        {"type": "response.done", "response": {"id": "interrupted", "status": status}},
        audio("next", b"part"),
        {"type": "response.done", "response": {
            "id": "next", "status": "completed", "usage": {"total_tokens": 4},
            "output": [{"id": "a2", "role": "assistant",
                        "content": [{"transcript": "next answer"}]}]}},
    ]

    class Socket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send(self, payload):
            pass

        async def recv(self):
            return json.dumps({"type": "session.created"})

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not events:
                raise StopAsyncIteration
            return json.dumps(events.pop(0))

    namespace.update(ConversationState=new_state, print_history=lambda state: None,
                     maybe_summarise=lambda ws, state: None, mic_to_queue=mic,
                     queue_to_websocket=upload, websockets=SimpleNamespace(
                         connect=lambda *args, **kwargs: Socket()),
                     simpleaudio=SimpleNamespace(
                         play_buffer=lambda pcm, *format: played.append(pcm)))
    error = None
    with redirect_stdout(StringIO()):
        try:
            await namespace["realtime_session"]()
        except RuntimeError as exc:
            error = exc
    if status == "cancelled":
        assert error is None, error
        assert played == [b"nextpart"], played
        assert [(turn.item_id, turn.text) for turn in states[0].history] == [
            ("a2", "next answer")]
        assert states[0].latest_tokens == 4
    else:
        assert error is not None, f"{status} must still raise"
        assert not played, played
        assert not states[0].history, states[0].history
    print("PASS response-end", status)


async def main():
    failures = []
    for outcome in ("completed", "failed", "missing", "during-summary"):
        try:
            await scenario(outcome)
        except Exception as error:
            failures.append(f"{outcome}: {type(error).__name__}: {error}")
        else:
            print("PASS", outcome)
    try:
        await before_task_start()
    except Exception as error:
        failures.append(f"before-task-start: {type(error).__name__}: {error}")
    for status in ("cancelled", "failed", "incomplete"):
        try:
            await response_end(status)
        except Exception as error:
            failures.append(f"response-{status}: {type(error).__name__}: {error}")
    if failures:
        raise AssertionError("; ".join(failures))

if __name__ == "__main__":
    asyncio.run(main())
