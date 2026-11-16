"""Handle AWS lifecycle hooks and transfer workspace files."""

import json
import os
import shutil
import signal
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path

import boto3
from flask import Flask, abort, request, send_file

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32768
WORKSPACE = Path("/workspace")
executor = None
connection = None


@app.post("/aws/lambda-microvms/runtime/v1/ready")
def ready():
    # Fetch credentials in the run hook, after AWS takes the image snapshot.
    return {"ready": True}


@app.post("/aws/lambda-microvms/runtime/v1/validate")
def validate():
    subprocess.run(["codex", "--version"], check=True, timeout=10, stdout=subprocess.DEVNULL)
    with tempfile.TemporaryFile(dir="/workspace") as probe:
        probe.write(b"ready")
    return {"validated": True}


@app.post("/aws/lambda-microvms/runtime/v1/run")
@app.post("/aws/lambda-microvms/runtime/v1/resume")
def start():
    global executor, connection
    if executor is not None and executor.poll() is None:
        return {"executor_running": True}
    try:
        if request.path.endswith("/run"):
            connection = json.loads(request.get_json()["runHookPayload"])
        secret_arn = connection["executor_secret_arn"]
        secrets = boto3.client("secretsmanager", region_name=secret_arn.split(":")[3])
        key = secrets.get_secret_value(SecretId=secret_arn)["SecretString"]
        if key.startswith("{"):
            key = json.loads(key)["OPENAI_EXECUTOR_API_KEY"]
        executor = subprocess.Popen(
            [
                "codex",
                "exec-server",
                "--remote",
                connection["remote_url"],
                "--environment-id",
                connection["environment_id"],
            ],
            cwd="/workspace",
            env={**os.environ, "CODEX_API_KEY": key},
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"executor_running": True}
    except Exception as error:
        # Log the error type only; response bodies can contain credentials.
        app.logger.error("Executor startup failed: %s", type(error).__name__)
        return {"error": "executor startup failed"}, 500


@app.post("/aws/lambda-microvms/runtime/v1/suspend")
@app.post("/aws/lambda-microvms/runtime/v1/terminate")
def stop():
    global executor
    if executor is not None and executor.poll() is None:
        with suppress(ProcessLookupError):
            os.killpg(executor.pid, signal.SIGTERM)
        try:
            executor.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(executor.pid, signal.SIGKILL)
            executor.wait(timeout=5)
    executor = None
    os.sync()
    return {"executor_running": False}


def workspace_file(filename):
    path = (WORKSPACE / filename).resolve()
    if not path.is_relative_to(WORKSPACE) or path.is_dir():
        abort(404)
    return path


@app.get("/download/<path:filename>")
def download(filename):
    path = workspace_file(filename)
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True)


@app.put("/upload/<path:filename>")
def upload(filename):
    request.max_content_length = 64 * 1024 * 1024
    path = workspace_file(filename)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError):
        abort(409)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            shutil.copyfileobj(request.stream, output)
            output.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return "", 204


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=False)
