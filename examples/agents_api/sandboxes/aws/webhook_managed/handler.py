"""Handle OpenAI webhooks that start, resume, or stop a MicroVM."""

import base64
import json
import os

import boto3
from common import launch_microvm
from openai import InvalidWebhookSignatureError, NotFoundError, OpenAI

VM_METADATA_KEY = "aws_microvm_id"


def response(status, message):
    return {"statusCode": status, "body": json.dumps({"message": message})}


def reconcile(client, microvms, session_id):
    try:
        session = client.beta.agents.sessions.retrieve(session_id)
    except NotFoundError:
        return "session deleted"
    if session.agent.id != os.environ["OPENAI_AGENT_ID"]:
        return "different agent"
    if session.environment.type != "self_hosted":
        return "different environment"
    metadata = session.metadata or {}
    if session.status == "failed":
        if metadata.get(VM_METADATA_KEY):
            microvms.terminate_microvm(microvmIdentifier=metadata[VM_METADATA_KEY])
        return "failed session cleanup"
    if not any(a.type == "environment_connection" for a in session.required_actions):
        return "connection no longer required"

    if vm_id := metadata.get(VM_METADATA_KEY):
        vm = microvms.get_microvm(microvmIdentifier=vm_id)
        if vm["state"] == "SUSPENDED":
            microvms.resume_microvm(microvmIdentifier=vm_id)
            print(json.dumps({"action": "resumed", "session_id": session_id, "microvm_id": vm_id}))
            return "resumed"
        if vm["state"] in {"PENDING", "RUNNING"}:
            return "existing VM connecting"
        raise RuntimeError("Recorded VM cannot resume; create a new session")

    vm = launch_microvm(
        microvms,
        session.environment,
        {
            "image_arn": os.environ["MICROVM_IMAGE_ARN"],
            "image_version": os.environ["MICROVM_IMAGE_VERSION"],
        },
        {
            "role_arn": os.environ["MICROVM_EXECUTION_ROLE_ARN"],
            "executor_secret_arn": os.environ["EXECUTOR_SECRET_ARN"],
        },
        suspend_resume=metadata.get("aws_suspend_resume") == "true",
    )
    vm_id = vm["microvmId"]
    # The client reads this ID to download output and terminate the VM.
    try:
        client.beta.agents.sessions.update(
            session_id, metadata={**metadata, VM_METADATA_KEY: vm_id}
        )
    except Exception:
        microvms.terminate_microvm(microvmIdentifier=vm_id)
        raise
    print(json.dumps({"action": "started", "session_id": session_id, "microvm_id": vm_id}))
    return "started"


def lambda_handler(event, _context):
    if event.get("requestContext", {}).get("http", {}).get("method") != "POST":
        return response(405, "POST required")
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    secrets = boto3.client("secretsmanager").get_secret_value(
        SecretId=os.environ["CONTROLLER_SECRET_ARN"]
    )
    settings = json.loads(secrets["SecretString"])
    if not settings.get("OPENAI_WEBHOOK_SECRET"):
        return response(503, "webhook signing secret not configured")
    with OpenAI(
        api_key=settings["OPENAI_API_KEY"],
        webhook_secret=settings["OPENAI_WEBHOOK_SECRET"],
        timeout=20,
        max_retries=0,
    ) as client:
        try:
            client.webhooks.verify_signature(payload=raw, headers=event.get("headers", {}))
        except (InvalidWebhookSignatureError, ValueError):
            return response(400, "invalid signature")
        try:
            delivery = json.loads(raw)
            relevant = delivery["type"] == "agent.session.failed" or (
                delivery["type"] == "agent.session.action_required"
                and delivery["data"]["required_action"]["type"] == "environment_connection"
            )
            if not relevant:
                return response(200, "ignored")
            message = reconcile(client, boto3.client("lambda-microvms"), delivery["data"]["id"])
            print(json.dumps({"event_id": delivery.get("id"), "outcome": message}))
            return response(200, message)
        except Exception as error:
            # Log the error type only; response bodies can contain credentials.
            print(json.dumps({"error_type": type(error).__name__}))
            return response(500, "provisioning failed")
