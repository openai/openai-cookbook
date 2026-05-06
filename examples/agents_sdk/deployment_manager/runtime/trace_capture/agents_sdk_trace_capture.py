from __future__ import annotations

import json
import os
import queue
import threading
import urllib.request
from datetime import datetime, timezone
from typing import Any


_INSTALLED = False
_LOCK = threading.Lock()


def install() -> None:
    endpoint = os.environ.get("AGENTS_SDK_MANAGER_TRACE_ENDPOINT")
    if not endpoint:
        return

    global _INSTALLED
    with _LOCK:
        if _INSTALLED:
            return
        try:
            from agents.tracing import add_trace_processor
        except Exception:
            return
        add_trace_processor(
            ManagerTraceProcessor(
                endpoint=endpoint,
                deployment_id=os.environ.get("AGENTS_SDK_DEPLOYMENT_ID"),
                project_id=os.environ.get("AGENTS_SDK_PROJECT_ID"),
            )
        )
        _INSTALLED = True


class ManagerTraceProcessor:
    def __init__(
        self, *, endpoint: str, deployment_id: str | None, project_id: str | None
    ) -> None:
        self.endpoint = endpoint
        self.deployment_id = deployment_id
        self.project_id = project_id
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=1000)
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._worker = threading.Thread(
            target=self._drain, name="agents-manager-trace", daemon=True
        )
        self._worker.start()

    def on_trace_start(self, trace: Any) -> None:
        self._enqueue("trace_start", trace)

    def on_trace_end(self, trace: Any) -> None:
        self._enqueue("trace_end", trace)

    def on_span_start(self, span: Any) -> None:
        self._enqueue("span_start", span)

    def on_span_end(self, span: Any) -> None:
        self._enqueue("span_end", span)

    def shutdown(self) -> None:
        self.force_flush()

    def force_flush(self) -> None:
        self._queue.join()

    def _enqueue(self, event_type: str, item: Any) -> None:
        payload = _export(item)
        if not payload:
            return
        record = {
            "event": event_type,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "deployment_id": self.deployment_id,
            "project_id": self.project_id,
            "payload": payload,
        }
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            return

    def _drain(self) -> None:
        while True:
            record = self._queue.get()
            try:
                if record is None:
                    return
                self._post(record)
            finally:
                self._queue.task_done()

    def _post(self, record: dict[str, Any]) -> None:
        body = json.dumps(record, default=str).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=1):
                pass
        except Exception:
            return


def _export(item: Any) -> dict[str, Any] | None:
    export = getattr(item, "export", None)
    if callable(export):
        try:
            payload = export()
        except Exception:
            return None
        if isinstance(payload, dict):
            return payload
    return None
