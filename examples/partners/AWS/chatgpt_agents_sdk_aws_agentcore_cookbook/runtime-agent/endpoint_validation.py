from __future__ import annotations

import re
from urllib.parse import urlsplit

_AWS_REGION = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
_APPROVED_PATH = "/v1"


def resolve_aws_region(aws_region: str | None, aws_default_region: str | None) -> str:
    primary = (aws_region or "").strip()
    fallback = (aws_default_region or "").strip()
    if primary and fallback and primary != fallback:
        raise RuntimeError("AWS_REGION and AWS_DEFAULT_REGION must match")
    region = primary or fallback
    if not region:
        raise RuntimeError("AWS_REGION or AWS_DEFAULT_REGION is required")
    if not _AWS_REGION.fullmatch(region):
        raise RuntimeError("The configured AWS region is invalid")
    return region


def validate_bedrock_base_url(endpoint: str, region: str) -> str:
    """Return the approved Bedrock URL, rejecting authority-confusion inputs."""
    canonical = f"https://bedrock-mantle.{region}.api.aws{_APPROVED_PATH}"
    if not endpoint or endpoint != endpoint.strip() or "\\" in endpoint:
        raise RuntimeError("OPENAI_BASE_URL is not an approved AWS Bedrock endpoint")
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError("OPENAI_BASE_URL is not an approved AWS Bedrock endpoint") from exc
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or parsed.query
        or port is not None
        or parsed.hostname != f"bedrock-mantle.{region}.api.aws"
        or parsed.path != _APPROVED_PATH
        or endpoint != canonical
    ):
        raise RuntimeError("OPENAI_BASE_URL is not an approved AWS Bedrock endpoint")
    return canonical
