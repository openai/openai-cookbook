"""Mitigation for https://github.com/langchain-ai/langchain/issues/36380.

`RunnableWithMessageHistory` calls ``load(run.inputs)`` and ``load(run.outputs)``
with ``allowed_objects="all"``, which can revive constructor-shaped dicts (e.g.
serialized ``SystemMessage``) from untrusted model output into real objects
persisted in chat history.

This module patches ``RunnableWithMessageHistory`` to use an explicit
``load(..., allowed_objects=...)`` allowlist of conversational message types only
(mirroring the intended upstream fix in ``langchain_core``).

Call ``apply_langchain_issue_36380_fix()`` once at process startup after
``langchain_core`` is importable. When upstream releases a fixed ``langchain-core``,
remove this patch and depend on the new version instead.

Made-with: Cursor
"""

from __future__ import annotations

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.load.load import load
from langchain_core.load.serializable import Serializable
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    ChatMessage,
    ChatMessageChunk,
    FunctionMessage,
    FunctionMessageChunk,
    HumanMessage,
    HumanMessageChunk,
    RemoveMessage,
    ToolMessage,
    ToolMessageChunk,
)
from langchain_core.runnables.config import RunnableConfig
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.tracers.schemas import Run

_MESSAGE_HISTORY_LOAD_ALLOWED: tuple[type[Serializable], ...] = (
    HumanMessage,
    HumanMessageChunk,
    AIMessage,
    AIMessageChunk,
    ToolMessage,
    ToolMessageChunk,
    FunctionMessage,
    FunctionMessageChunk,
    ChatMessage,
    ChatMessageChunk,
    RemoveMessage,
)

_applied = False


def apply_langchain_issue_36380_fix() -> None:
    """Patch ``RunnableWithMessageHistory`` history persistence (idempotent)."""
    global _applied
    if _applied:
        return
    RunnableWithMessageHistory._exit_history = _exit_history  # type: ignore[method-assign]
    RunnableWithMessageHistory._aexit_history = _aexit_history  # type: ignore[method-assign]
    _applied = True


def _exit_history(
    self: RunnableWithMessageHistory, run: Run, config: RunnableConfig
) -> None:
    hist: BaseChatMessageHistory = config["configurable"]["message_history"]

    inputs = load(run.inputs, allowed_objects=_MESSAGE_HISTORY_LOAD_ALLOWED)
    input_messages = self._get_input_messages(inputs)
    if not self.history_messages_key:
        historic_messages = config["configurable"]["message_history"].messages
        input_messages = input_messages[len(historic_messages) :]

    output_val = load(run.outputs, allowed_objects=_MESSAGE_HISTORY_LOAD_ALLOWED)
    output_messages = self._get_output_messages(output_val)
    hist.add_messages(input_messages + output_messages)


async def _aexit_history(
    self: RunnableWithMessageHistory, run: Run, config: RunnableConfig
) -> None:
    hist: BaseChatMessageHistory = config["configurable"]["message_history"]

    inputs = load(run.inputs, allowed_objects=_MESSAGE_HISTORY_LOAD_ALLOWED)
    input_messages = self._get_input_messages(inputs)
    if not self.history_messages_key:
        historic_messages = await hist.aget_messages()
        input_messages = input_messages[len(historic_messages) :]

    output_val = load(run.outputs, allowed_objects=_MESSAGE_HISTORY_LOAD_ALLOWED)
    output_messages = self._get_output_messages(output_val)
    await hist.aadd_messages(input_messages + output_messages)
