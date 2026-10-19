# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.43.34"]
# ///
"""Deploy the webhook handler to Lambda and API Gateway."""

import argparse
import json
import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent
SHARED = ROOT.parent / "application_managed"


def deploy(args):
    aws = boto3.Session(profile_name=args.profile, region_name=args.region)
    sts = aws.client("sts")
    secrets = aws.client("secretsmanager")
    logs = aws.client("logs")
    iam = aws.client("iam")
    lambda_client = aws.client("lambda")
    gateway = aws.client("apigatewayv2")
    image = json.loads(args.image_state.read_text())
    execution = json.loads(args.execution_state.read_text())
    account = sts.get_caller_identity()["Account"]
    if (image["account"], image["region"]) != (account, args.region):
        raise ValueError("Image state belongs to a different account or region")
    secret = secrets.describe_secret(SecretId=args.controller_secret_arn)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(args.state.read_text()) if args.state.exists() else {}
    if state and (state["account"], state["region"], state["function_name"]) != (
        account,
        args.region,
        args.name,
    ):
        raise ValueError("Deployment state belongs to a different target")
    state.update(
        account=account,
        region=args.region,
        profile=args.profile,
        function_name=args.name,
        agent_id=args.agent_id,
        controller_secret_arn=secret["ARN"],
    )

    def save():
        args.state.write_text(json.dumps(state, indent=2) + "\n")

    save()
    group = f"/aws/lambda/{args.name}"
    if "log_group" not in state:
        logs.create_log_group(logGroupName=group)
        state["log_group"] = group
        save()
    logs.put_retention_policy(logGroupName=group, retentionInDays=7)
    if "role_arn" not in state:
        trust = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        role = iam.create_role(
            RoleName=args.name,
            AssumeRolePolicyDocument=json.dumps(trust),
        )
        state["role_arn"] = role["Role"]["Arn"]
        save()
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": secret["ARN"],
            },
            {
                "Effect": "Allow",
                "Action": "iam:PassRole",
                "Resource": execution["role_arn"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "lambda:RunMicrovm",
                    "lambda:GetMicrovm",
                    "lambda:ResumeMicrovm",
                    "lambda:TerminateMicrovm",
                ],
                "Resource": image["image_arn"],
            },
            {
                "Effect": "Allow",
                "Action": "lambda:PassNetworkConnector",
                "Resource": [
                    f"arn:aws:lambda:{args.region}:aws:network-connector:aws-network-connector:ALL_INGRESS",
                    f"arn:aws:lambda:{args.region}:aws:network-connector:aws-network-connector:INTERNET_EGRESS",
                ],
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": f"arn:aws:logs:{args.region}:{account}:log-group:{group}:*",
            },
        ],
    }
    iam.put_role_policy(
        RoleName=args.name,
        PolicyName="webhook-controller",
        PolicyDocument=json.dumps(policy),
    )
    package = args.state.parent / "package"
    if package.exists():
        shutil.rmtree(package)
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(package),
            "--python-version",
            "3.13",
            "--python-platform",
            "x86_64-manylinux2014",
            "--only-binary",
            ":all:",
            "-r",
            str(ROOT / "requirements.txt"),
        ],
        check=True,
    )
    archive = args.state.parent / "function.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        output.write(ROOT / "handler.py", "handler.py")
        output.write(ROOT.parent / "common.py", "common.py")
        for file in package.rglob("*"):
            if file.is_file() and "__pycache__" not in file.parts:
                output.write(file, file.relative_to(package))
    env = {
        "Variables": {
            "OPENAI_AGENT_ID": args.agent_id,
            "CONTROLLER_SECRET_ARN": secret["ARN"],
            "MICROVM_IMAGE_ARN": image["image_arn"],
            "MICROVM_IMAGE_VERSION": image["image_version"],
            "MICROVM_EXECUTION_ROLE_ARN": execution["role_arn"],
            "EXECUTOR_SECRET_ARN": execution["executor_secret_arn"],
        }
    }
    if state.get("function_arn"):
        function = lambda_client.update_function_code(
            FunctionName=args.name, ZipFile=archive.read_bytes()
        )
        lambda_client.get_waiter("function_updated_v2").wait(FunctionName=args.name)
        lambda_client.update_function_configuration(FunctionName=args.name, Environment=env)
        lambda_client.get_waiter("function_updated_v2").wait(FunctionName=args.name)
    else:
        time.sleep(10)  # Allow the new IAM role and policy to propagate.
        function = lambda_client.create_function(
            FunctionName=args.name,
            Runtime="python3.13",
            Handler="handler.lambda_handler",
            Role=state["role_arn"],
            Timeout=60,
            MemorySize=256,
            Code={"ZipFile": archive.read_bytes()},
            Environment=env,
        )
        lambda_client.get_waiter("function_active_v2").wait(FunctionName=args.name)
    state["function_arn"] = function["FunctionArn"]
    save()
    if "api_id" not in state:
        api = gateway.create_api(
            Name=args.name,
            ProtocolType="HTTP",
        )
        state["api_id"] = api["ApiId"]
        state["url"] = f"{api['ApiEndpoint']}/webhook"
        save()
    if "integration_id" not in state:
        integration = gateway.create_integration(
            ApiId=state["api_id"],
            IntegrationType="AWS_PROXY",
            IntegrationUri=state["function_arn"],
            PayloadFormatVersion="2.0",
            TimeoutInMillis=30000,
        )
        state["integration_id"] = integration["IntegrationId"]
        save()
    if "route_id" not in state:
        route = gateway.create_route(
            ApiId=state["api_id"],
            RouteKey="POST /webhook",
            Target=f"integrations/{state['integration_id']}",
        )
        state["route_id"] = route["RouteId"]
        save()
    if "invoke_permission" not in state:
        lambda_client.add_permission(
            FunctionName=args.name,
            StatementId="webhook-api-gateway",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{args.region}:{account}:{state['api_id']}/*/POST/webhook",
            SourceAccount=account,
        )
        state["invoke_permission"] = True
        save()
    if "stage" not in state:
        gateway.create_stage(
            ApiId=state["api_id"],
            StageName="$default",
            AutoDeploy=True,
            DefaultRouteSettings={"ThrottlingBurstLimit": 5, "ThrottlingRateLimit": 2},
        )
        state["stage"] = "$default"
        save()
    print(f"Webhook URL: {state['url']}")
    print(f"Deployment metadata: {args.state}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--name", default="codex-agents-api-webhook")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--controller-secret-arn", required=True)
    parser.add_argument("--image-state", type=Path, default=SHARED / ".local/image.json")
    parser.add_argument(
        "--execution-state", type=Path, default=SHARED / ".local/execution-role.json"
    )
    parser.add_argument("--state", type=Path, default=ROOT / ".local/deployment.json")
    deploy(parser.parse_args())
