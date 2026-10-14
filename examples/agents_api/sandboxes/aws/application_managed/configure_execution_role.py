# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.43.34"]
# ///
"""Create an execution role that reads one existing Secrets Manager secret."""

import argparse
import json
import os
from pathlib import Path

import boto3


def configure(args):
    aws = boto3.Session(profile_name=args.profile, region_name=args.region)
    secrets = aws.client("secretsmanager")
    iam = aws.client("iam")
    # Read the secret ARN without retrieving its value.
    secret = secrets.describe_secret(SecretId=args.executor_secret_arn)
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
        RoleName=args.name,
        AssumeRolePolicyDocument=json.dumps(trust),
        Description="Read the Codex executor secret at MicroVM runtime",
    )
    state = {
        "role_arn": role["Role"]["Arn"],
        "role_name": args.name,
        "executor_secret_arn": secret["ARN"],
        "region": args.region,
    }
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(state, indent=2) + "\n")
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": secret["ARN"],
            }
        ],
    }
    iam.put_role_policy(
        RoleName=args.name,
        PolicyName="read-executor-secret",
        PolicyDocument=json.dumps(policy),
    )
    print(f"Execution role: {state['role_arn']}")
    print(f"Resource metadata saved to {args.state}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "us-west-2"))
    parser.add_argument("--executor-secret-arn", required=True)
    parser.add_argument("--name", default="codex-agents-api-executor")
    parser.add_argument(
        "--state",
        type=Path,
        default=Path(__file__).with_name(".local") / "execution-role.json",
    )
    configure(parser.parse_args())
