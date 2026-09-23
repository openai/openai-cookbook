from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file
from pydantic import ValidationError

from .dockerfile_writer import dockerfile_text, ensure_dockerfile
from .models import CreateDeploymentRequest, Deployment, ImportProjectRequest
from .project_inspector import inspect_project
from .runner import (
    read_deployment_log,
    refresh_status,
    start_local_docker,
    start_local_process,
    stop_local_docker,
    stop_local_process,
)
from .store import Store
from .timeline import (
    docker_containers,
    docker_logs,
    list_sessions,
    timeline_for_session,
)
from .trace_store import TraceStore

ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = ROOT / "state"
DIST_DIR = ROOT / "dist"
INDEX_PATH = DIST_DIR / "index.html"
STORE = Store(STATE_ROOT / "store.json")
TRACE_STORE = TraceStore(STATE_ROOT / "traces.sqlite3")
DOC_FILES = {
    "agent-interactions.png": "agent-interactions.png",
    "agent-sequence.png": "agent-sequence.png",
    "prompt.md": "prompt.md",
}

app = Flask(__name__)


def _json_error(message: str, status: int) -> tuple[Response, int]:
    return jsonify({"detail": message}), status


def _request_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _serve_setup_page() -> bytes:
    html = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Agents SDK Deployment Manager</title>
    <style>
      body {
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background: #f3f4f6;
        color: #111827;
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .card {
        width: min(520px, calc(100vw - 32px));
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        background: #fff;
        padding: 24px;
      }
      pre {
        padding: 14px;
        border-left: 2px solid #d1d5db;
        overflow: auto;
      }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Frontend not built yet</h1>
      <p>The Python API is up, but the React frontend has not been built into <code>dist/</code> yet.</p>
      <pre>npm install
npm run build</pre>
    </div>
  </body>
</html>
"""
    return html.encode("utf-8")


def _serve_frontend(frontend_path: str = "") -> Response:
    if frontend_path.startswith("api/"):
        return Response("Not found", status=404, content_type="text/plain")

    dist_target = DIST_DIR / frontend_path
    if dist_target.exists() and dist_target.is_file():
        return send_file(dist_target)

    if INDEX_PATH.exists():
        return send_file(INDEX_PATH)

    return Response(_serve_setup_page(), content_type="text/html; charset=utf-8")


def _project_docs_dir(project_id: str) -> Path | None:
    project = STORE.get_project(project_id)
    if project is None:
        return None
    return Path(project.path) / "docs"


@app.get("/api/health")
def health() -> Response:
    return jsonify({"ok": "true"})


@app.get("/api/projects")
def projects() -> Response:
    return jsonify(
        {"projects": [project.model_dump() for project in STORE.list_projects()]}
    )


@app.post("/api/projects/import")
def import_project() -> Response | tuple[Response, int]:
    try:
        import_request = ImportProjectRequest.model_validate(_request_payload())
        project = inspect_project(import_request.path)
    except (ValidationError, ValueError) as exc:
        return _json_error(str(exc), 400)
    STORE.upsert_project(project)
    return jsonify({"project": project.model_dump()})


@app.get("/api/projects/<project_id>")
def project_detail(project_id: str) -> Response | tuple[Response, int]:
    project = STORE.get_project(project_id)
    if project is None:
        return _json_error("project not found", 404)
    return jsonify({"project": project.model_dump()})


@app.get("/api/projects/<project_id>/docs")
def project_docs(project_id: str) -> Response | tuple[Response, int]:
    docs_dir = _project_docs_dir(project_id)
    if docs_dir is None:
        return _json_error("project not found", 404)

    prompt_path = docs_dir / "prompt.md"
    docs = {
        "agent_interactions_url": f"/api/projects/{project_id}/docs/agent-interactions.png"
        if (docs_dir / "agent-interactions.png").is_file()
        else None,
        "agent_sequence_url": f"/api/projects/{project_id}/docs/agent-sequence.png"
        if (docs_dir / "agent-sequence.png").is_file()
        else None,
        "prompt": prompt_path.read_text(encoding="utf-8")
        if prompt_path.is_file()
        else "",
        "prompt_path": "docs/prompt.md" if prompt_path.is_file() else None,
    }
    return jsonify(docs)


@app.get("/api/projects/<project_id>/docs/<name>")
def project_doc_file(project_id: str, name: str) -> Response | tuple[Response, int]:
    safe_name = DOC_FILES.get(name)
    if safe_name is None:
        return _json_error("doc not found", 404)
    docs_dir = _project_docs_dir(project_id)
    if docs_dir is None:
        return _json_error("project not found", 404)
    doc_path = docs_dir / safe_name
    if not doc_path.is_file():
        return _json_error("doc not found", 404)
    return send_file(doc_path)


@app.get("/api/deployments")
def deployments() -> Response:
    deployments = []
    for deployment in STORE.list_deployments():
        deployment = refresh_status(deployment)
        if STORE.update_deployment(deployment) is None:
            continue
        deployments.append(deployment.model_dump())
    return jsonify({"deployments": deployments})


@app.post("/api/deployments")
def create_deployment() -> Response | tuple[Response, int]:
    try:
        deployment_request = CreateDeploymentRequest.model_validate(_request_payload())
    except ValidationError as exc:
        return _json_error(str(exc), 400)

    project = STORE.get_project(deployment_request.project_id)
    if project is None:
        return _json_error("project not found", 404)
    deployment_id = f"dep-{uuid.uuid4().hex[:8]}"
    port = deployment_request.port or project.port
    deployment = Deployment(
        id=deployment_id,
        project_id=project.id,
        name=deployment_request.name or project.name,
        target=deployment_request.target,
        port=port,
        sandbox_backend=deployment_request.sandbox_backend,
        requires_docker_socket=project.uses_sandbox_agent
        and deployment_request.sandbox_backend == "docker",
        app_url=f"http://127.0.0.1:{port}",
    )
    if deployment.target == "local-docker":
        deployment.dockerfile_path = str(ensure_dockerfile(project))
    STORE.upsert_deployment(deployment)
    return jsonify({"deployment": deployment.model_dump()})


@app.get("/api/deployments/<deployment_id>")
def deployment_detail(deployment_id: str) -> Response | tuple[Response, int]:
    deployment = STORE.get_deployment(deployment_id)
    if deployment is None:
        return _json_error("deployment not found", 404)
    deployment = refresh_status(deployment)
    if STORE.update_deployment(deployment) is None:
        return _json_error("deployment not found", 404)
    project = STORE.get_project(deployment.project_id)
    return jsonify(
        {
            "deployment": deployment.model_dump(),
            "project": project.model_dump() if project else None,
        }
    )


@app.post("/api/deployments/<deployment_id>/start")
def start_deployment(deployment_id: str) -> Response | tuple[Response, int]:
    deployment = STORE.get_deployment(deployment_id)
    if deployment is None:
        return _json_error("deployment not found", 404)
    project = STORE.get_project(deployment.project_id)
    if project is None:
        return _json_error("project not found", 404)
    try:
        if deployment.target == "local-docker":
            deployment = start_local_docker(STATE_ROOT, project, deployment)
        else:
            deployment = start_local_process(STATE_ROOT, project, deployment)
    except RuntimeError as exc:
        deployment.status = "failed"
        deployment.error = str(exc)
    STORE.upsert_deployment(deployment)
    return jsonify({"deployment": deployment.model_dump()})


@app.post("/api/deployments/<deployment_id>/stop")
def stop_deployment(deployment_id: str) -> Response | tuple[Response, int]:
    deployment = STORE.get_deployment(deployment_id)
    if deployment is None:
        return _json_error("deployment not found", 404)
    if deployment.target == "local-docker":
        deployment = stop_local_docker(deployment)
    else:
        deployment = stop_local_process(deployment)
    STORE.upsert_deployment(deployment)
    return jsonify({"deployment": deployment.model_dump()})


@app.delete("/api/deployments/<deployment_id>")
def remove_deployment(deployment_id: str) -> Response | tuple[Response, int]:
    deployment = STORE.get_deployment(deployment_id)
    if deployment is None:
        return _json_error("deployment not found", 404)
    if deployment.target == "local-docker":
        deployment = stop_local_docker(deployment)
    else:
        deployment = stop_local_process(deployment)
    deleted_traces = TRACE_STORE.delete_deployment(deployment_id)
    STORE.delete_deployment(deployment_id)
    shutil.rmtree(STATE_ROOT / "deployments" / deployment_id, ignore_errors=True)
    return jsonify(
        {
            "ok": True,
            "deployment": deployment.model_dump(),
            "deleted_traces": deleted_traces,
        }
    )


@app.get("/api/deployments/<deployment_id>/logs")
def deployment_logs(deployment_id: str) -> Response | tuple[Response, int]:
    deployment = STORE.get_deployment(deployment_id)
    if deployment is None:
        return _json_error("deployment not found", 404)
    return Response(
        read_deployment_log(deployment), content_type="text/plain; charset=utf-8"
    )


@app.get("/api/deployments/<deployment_id>/dockerfile")
def deployment_dockerfile(deployment_id: str) -> Response | tuple[Response, int]:
    deployment = STORE.get_deployment(deployment_id)
    if deployment is None:
        return _json_error("deployment not found", 404)
    project = STORE.get_project(deployment.project_id)
    if project is None:
        return _json_error("project not found", 404)
    return Response(dockerfile_text(project), content_type="text/plain; charset=utf-8")


@app.get("/api/deployments/<deployment_id>/containers")
def deployment_containers(deployment_id: str) -> Response | tuple[Response, int]:
    if STORE.get_deployment(deployment_id) is None:
        return _json_error("deployment not found", 404)
    return jsonify(
        {
            "containers": [
                container.model_dump()
                for container in docker_containers(deployment_id=deployment_id)
            ]
        }
    )


@app.get("/api/deployments/<deployment_id>/sessions")
def deployment_sessions(deployment_id: str) -> Response | tuple[Response, int]:
    deployment = STORE.get_deployment(deployment_id)
    if deployment is None:
        return _json_error("deployment not found", 404)
    project = STORE.get_project(deployment.project_id)
    if project is None:
        return _json_error("project not found", 404)
    return jsonify(
        {
            "sessions": [
                session.model_dump()
                for session in list_sessions(project, deployment, TRACE_STORE)
            ]
        }
    )


@app.get("/api/sessions")
def sessions() -> Response:
    sessions = []
    for deployment in STORE.list_deployments():
        deployment = refresh_status(deployment)
        if STORE.update_deployment(deployment) is None:
            continue
        project = STORE.get_project(deployment.project_id)
        if project is None:
            continue
        sessions.extend(
            session.model_dump()
            for session in list_sessions(project, deployment, TRACE_STORE)
        )
    return jsonify(
        {
            "sessions": sorted(
                sessions,
                key=lambda session: str(session.get("updated_at") or ""),
                reverse=True,
            )
        }
    )


@app.get("/api/sessions/<deployment_id>/<expense_id>/timeline")
def session_timeline(
    deployment_id: str, expense_id: str
) -> Response | tuple[Response, int]:
    deployment = STORE.get_deployment(deployment_id)
    if deployment is None:
        return _json_error("deployment not found", 404)
    project = STORE.get_project(deployment.project_id)
    if project is None:
        return _json_error("project not found", 404)
    return jsonify(
        {
            "events": [
                event.model_dump()
                for event in timeline_for_session(
                    project, deployment, expense_id, TRACE_STORE
                )
            ]
        }
    )


@app.post("/api/traces/ingest")
def ingest_traces() -> Response | tuple[Response, int]:
    payload = request.get_json(silent=True)
    if isinstance(payload, list):
        records = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict) and isinstance(payload.get("events"), list):
        records = [item for item in payload["events"] if isinstance(item, dict)]
    elif isinstance(payload, dict):
        records = [payload]
    else:
        return _json_error("expected a trace event object or list", 400)
    return jsonify({"ok": True, "ingested": TRACE_STORE.ingest_many(records)})


@app.get("/api/traces")
def traces() -> Response:
    deployment_id = request.args.get("deployment_id")
    if deployment_id:
        if STORE.get_deployment(deployment_id) is None:
            return jsonify({"traces": []})
        return jsonify({"traces": TRACE_STORE.trace_summaries(deployment_id)})
    active_deployment_ids = {deployment.id for deployment in STORE.list_deployments()}
    return jsonify(
        {
            "traces": [
                trace
                for trace in TRACE_STORE.trace_summaries()
                if trace.get("deployment_id") in active_deployment_ids
            ]
        }
    )


@app.get("/api/traces/<trace_id>/spans")
def trace_spans(trace_id: str) -> Response:
    return jsonify({"object": "list", "data": TRACE_STORE.spans_for_trace(trace_id)})


@app.get("/api/containers/<container_id>/logs")
def container_logs(container_id: str) -> Response:
    return Response(docker_logs(container_id), content_type="text/plain; charset=utf-8")


@app.get("/")
def frontend_index() -> Response:
    return _serve_frontend()


@app.get("/<path:frontend_path>")
def frontend_fallback(frontend_path: str) -> Response:
    return _serve_frontend(frontend_path)


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8732"))
    print(f"Agents SDK Deployment Manager running at http://{host}:{port}")
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
