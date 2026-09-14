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
from types import ModuleType, SimpleNamespace

import httpx
import pytest
from runloop_api_client import NotFoundError


def load_module(filename: str, name: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def handler() -> ModuleType:
    return load_module("handler.py", "runloop_webhook_handler")


@pytest.fixture(scope="module")
def deploy() -> ModuleType:
    return load_module("deploy.py", "runloop_webhook_deploy")


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


@pytest.mark.parametrize("saved_fingerprint", ["current", "previous"])
def test_missing_saved_controller_is_recreated(
    deploy: ModuleType, saved_fingerprint: str
) -> None:
    class MissingController:
        async def get_info(self) -> None:
            response = httpx.Response(
                404,
                request=httpx.Request(
                    "GET", "https://api.runloop.ai/v1/devboxes/missing"
                ),
            )
            raise NotFoundError("Devbox not found", response=response, body=None)

    class Devboxes:
        def from_id(self, _: str) -> MissingController:
            return MissingController()

    runloop = SimpleNamespace(devbox=Devboxes())
    state = {"devbox_id": "missing", "fingerprint": saved_fingerprint}
    assert asyncio.run(deploy.reuse_saved_controller(runloop, state, "current")) is None


def test_secret_lookup_checks_the_full_account_page(deploy: ModuleType) -> None:
    class Secrets:
        async def list(self, *, limit: int) -> SimpleNamespace:
            assert limit == 5000
            return SimpleNamespace(secrets=[SimpleNamespace(name="existing")])

    runloop = SimpleNamespace(api=SimpleNamespace(secrets=Secrets()))
    assert asyncio.run(deploy.list_secret_names(runloop)) == {"existing"}


def test_gateway_lookup_filters_and_paginates(deploy: ModuleType) -> None:
    updates: list[dict[str, object]] = []

    class Gateway:
        id = "gateway_exact"

        async def update(self, **kwargs: object) -> None:
            updates.append(kwargs)

    class Gateways:
        async def list(self, **kwargs: object) -> object:
            assert kwargs == {
                "name": "target",
                "limit": 5000,
                "include_total_count": False,
            }

            async def pages() -> object:
                yield SimpleNamespace(id="gateway_partial", name="target-old")
                yield SimpleNamespace(id="gateway_exact", name="target")

            return pages()

    gateway = Gateway()
    runloop = SimpleNamespace(
        api=SimpleNamespace(gateway_configs=Gateways()),
        gateway_config=SimpleNamespace(from_id=lambda _: gateway),
    )
    assert asyncio.run(deploy.ensure_gateway(runloop, "target", "description")) == (
        "gateway_exact"
    )
    assert updates == [
        {
            "endpoint": "https://api.openai.com",
            "auth_mechanism": {"type": "bearer"},
        }
    ]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
