# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.43.34"]
# ///
"""Build a Codex MicroVM image in AWS."""

import argparse
import json
import os
import time
import uuid
import zipfile
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent


def build(args):
    aws = boto3.Session(profile_name=args.profile, region_name=args.region)
    sts = aws.client("sts")
    s3 = aws.client("s3")
    logs = aws.client("logs")
    iam = aws.client("iam")
    microvms = aws.client("lambda-microvms")
    account = sts.get_caller_identity()["Account"]
    args.state.parent.mkdir(parents=True, exist_ok=True)
    if args.state.exists():
        state = json.loads(args.state.read_text())
        if state.get("deleted"):
            raise RuntimeError("This image was deleted; use a new --name and --state")
        if (state["account"], state["region"], state["name"]) != (
            account,
            args.region,
            args.name,
        ):
            raise RuntimeError("State belongs to another account, region, or image name")
    else:
        state = {
            "account": account,
            "region": args.region,
            "name": args.name,
            "build_name": f"{args.name}-{uuid.uuid4().hex[:8]}",
        }

    def save():
        args.state.write_text(json.dumps(state, indent=2) + "\n")

    save()
    tags = [{"Key": "Purpose", "Value": "codex-agents-api-example"}]
    bucket = f"{state['build_name']}-{account}"
    if "bucket" not in state:
        config = (
            {}
            if args.region == "us-east-1"
            else {"CreateBucketConfiguration": {"LocationConstraint": args.region}}
        )
        s3.create_bucket(Bucket=bucket, **config)
        state["bucket"] = bucket
        save()
    block = s3.get_public_access_block(Bucket=bucket)
    if not all(block["PublicAccessBlockConfiguration"].values()):
        raise RuntimeError("The build bucket must block all public access")
    s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": tags})

    group = state.get("log_group", f"/aws/lambda-microvms/{args.name}")
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
                    "Action": ["sts:AssumeRole", "sts:TagSession"],
                }
            ],
        }
        role = iam.create_role(
            RoleName=state["build_name"],
            AssumeRolePolicyDocument=json.dumps(trust),
            Tags=tags,
            Description="Build the reusable Codex Agents API MicroVM image",
        )
        state["role_name"] = state["build_name"]
        state["role_arn"] = role["Role"]["Arn"]
        save()
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject"],
                "Resource": f"arn:aws:s3:::{bucket}/image.zip",
            },
            {
                "Effect": "Allow",
                "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": f"arn:aws:logs:{args.region}:{account}:log-group:{group}:*",
            },
        ],
    }
    iam.put_role_policy(
        RoleName=state["role_name"],
        PolicyName="codex-image-build",
        PolicyDocument=json.dumps(policy),
    )
    state["role_policy"] = "codex-image-build"
    save()

    if "image_arn" not in state or args.rebuild:
        archive = args.state.parent / "image.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
            for filename in ("Dockerfile", "sandbox_server.py"):
                output.write(ROOT / filename, filename)
        s3.upload_file(str(archive), bucket, "image.zip")
        state["object_key"] = "image.zip"
        save()
        time.sleep(10)  # Allow the new IAM role and policy to propagate.
        updating = "image_arn" in state
        identity = (
            {"imageIdentifier": state["image_arn"]}
            if updating
            else {"name": args.name, "tags": {"Purpose": "codex-agents-api-example"}}
        )
        create_image = microvms.update_microvm_image if updating else microvms.create_microvm_image
        image = create_image(
            **identity,
            baseImageArn=f"arn:aws:lambda:{args.region}:aws:microvm-image:al2023-1",
            buildRoleArn=state["role_arn"],
            codeArtifact={"uri": f"s3://{bucket}/image.zip"},
            resources=[{"minimumMemoryInMiB": 8192}],
            egressNetworkConnectors=[
                f"arn:aws:lambda:{args.region}:aws:network-connector:aws-network-connector:INTERNET_EGRESS"
            ],
            hooks={
                "port": 8080,
                "microvmHooks": {
                    "run": "ENABLED",
                    "runTimeoutInSeconds": 60,
                    "suspend": "ENABLED",
                    "suspendTimeoutInSeconds": 30,
                    "resume": "ENABLED",
                    "resumeTimeoutInSeconds": 60,
                    "terminate": "ENABLED",
                    "terminateTimeoutInSeconds": 30,
                },
                "microvmImageHooks": {
                    "ready": "ENABLED",
                    "readyTimeoutInSeconds": 60,
                    "validate": "ENABLED",
                    "validateTimeoutInSeconds": 30,
                },
            },
        )
        state["image_arn"] = image["imageArn"]
        state["pending_image_version"] = image["imageVersion"]
        save()
    print(f"Image: {state['image_arn']}", flush=True)
    print(f"Build resources saved to {args.state}", flush=True)
    for _ in range(120):
        image = microvms.get_microvm_image(
            imageIdentifier=state["image_arn"],
        )
        active = image.get("latestActiveImageVersion")
        pending = state.get("pending_image_version")
        if active and (not pending or active == pending):
            state["image_version"] = active
            state.pop("pending_image_version", None)
            save()
            print(f"Ready: {state['image_arn']} version {state['image_version']}")
            return
        if (pending and image.get("latestFailedImageVersion") == pending) or image["state"] in {
            "CREATION_FAILED",
            "UPDATE_FAILED",
        }:
            raise RuntimeError(f"Image build failed; inspect CloudWatch group {group}")
        time.sleep(10)
    raise TimeoutError(f"Build still pending; rerun with the same --state {args.state}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--name", default="codex-executor")
    parser.add_argument(
        "--rebuild", action="store_true", help="Build a new version from current source"
    )
    parser.add_argument("--state", type=Path, default=ROOT / ".local" / "image.json")
    build(parser.parse_args())
