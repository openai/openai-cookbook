# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastapi>=0.115,<1",
#     "openai>=3.13.0",
#     "pytest>=8,<9",
#     "runloop-api-client>=1.31.0",
#     "uvicorn>=0.30,<1",
# ]
# ///

from __future__ import annotations

import asyncio
import importlib.util
import sqlite3
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(scope="module")
def handler() -> ModuleType:
    path = Path(__file__).with_name("handler.py")
    spec = importlib.util.spec_from_file_location("runloop_webhook_handler", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def queue(handler: ModuleType) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect(":memory:")
    handler.initialize_queue(db)
    try:
        yield db
    finally:
        db.close()


def test_delivery_during_successful_reconcile_remains_queued(
    handler: ModuleType,
    queue: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def check() -> None:
        handler.enqueue(queue, "session_1")
        started = asyncio.Event()
        finish = asyncio.Event()

        async def reconcile(_: str) -> None:
            started.set()
            await finish.wait()

        monkeypatch.setattr(handler, "reconcile", reconcile)
        task = asyncio.create_task(handler.process_next_job(queue))
        await started.wait()
        assert queue.execute(
            "SELECT attempts, generation FROM jobs WHERE session_id = 'session_1'"
        ).fetchone() == (0, 0)
        handler.enqueue(queue, "session_1")
        finish.set()
        assert await task
        assert queue.execute(
            "SELECT attempts, generation FROM jobs WHERE session_id = 'session_1'"
        ).fetchone() == (0, 1)

    asyncio.run(check())


def test_delivery_during_failed_reconcile_keeps_fresh_retry_state(
    handler: ModuleType,
    queue: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def check() -> None:
        handler.enqueue(queue, "session_1")

        async def reconcile(session_id: str) -> None:
            handler.enqueue(queue, session_id)
            raise RuntimeError("provisioning failed")

        monkeypatch.setattr(handler, "reconcile", reconcile)
        assert await handler.process_next_job(queue)
        assert queue.execute(
            "SELECT attempts, retry_at, generation FROM jobs "
            "WHERE session_id = 'session_1'"
        ).fetchone() == (0, 0.0, 1)

    asyncio.run(check())


def test_failed_reconcile_advances_retry_and_stops_at_limit(
    handler: ModuleType,
    queue: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def check() -> None:
        handler.enqueue(queue, "session_1")

        async def reconcile(_: str) -> None:
            raise RuntimeError("provisioning failed")

        monkeypatch.setattr(handler, "reconcile", reconcile)
        started_at = time.time()
        assert await handler.process_next_job(queue)
        attempts, retry_at = queue.execute(
            "SELECT attempts, retry_at FROM jobs WHERE session_id = 'session_1'"
        ).fetchone()
        assert attempts == 1
        assert retry_at >= started_at + 9

        queue.execute(
            "UPDATE jobs SET attempts = 4, retry_at = 0 WHERE session_id = 'session_1'"
        )
        queue.commit()
        assert await handler.process_next_job(queue)
        assert (
            queue.execute(
                "SELECT 1 FROM jobs WHERE session_id = 'session_1'"
            ).fetchone()
            is None
        )

    asyncio.run(check())


def test_remote_path_requires_the_gateway_upstream(handler: ModuleType) -> None:
    assert (
        handler.remote_path("https://api.openai.com/v1/agents/api?token=x")
        == "/v1/agents/api?token=x"
    )
    with pytest.raises(ValueError, match="does not use"):
        handler.remote_path("https://example.com/v1/agents/api")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
