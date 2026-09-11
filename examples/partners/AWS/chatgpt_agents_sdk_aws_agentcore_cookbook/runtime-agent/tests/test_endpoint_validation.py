from __future__ import annotations

import pytest

from endpoint_validation import resolve_aws_region, validate_bedrock_base_url


def test_resolve_aws_region_prefers_one_consistent_value() -> None:
    assert resolve_aws_region("us-west-2", None) == "us-west-2"
    assert resolve_aws_region(None, "us-west-2") == "us-west-2"
    assert resolve_aws_region("us-west-2", "us-west-2") == "us-west-2"


@pytest.mark.parametrize(
    ("primary", "fallback", "message"),
    [
        (None, None, "is required"),
        ("us-west-2", "us-east-1", "must match"),
        ("us.west.2", None, "invalid"),
    ],
)
def test_resolve_aws_region_rejects_missing_conflicting_or_invalid_values(
    primary: str | None, fallback: str | None, message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        resolve_aws_region(primary, fallback)


def test_validate_bedrock_base_url_accepts_the_documented_endpoint() -> None:
    endpoint = "https://bedrock-mantle.us-west-2.api.aws/v1"
    assert validate_bedrock_base_url(endpoint, "us-west-2") == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://bedrock-mantle.us-west-2.api.aws/v1",
        "https://bedrock-mantle.us-west-2.api.aws.evil.example/v1",
        "https://evil.example/bedrock-mantle.us-west-2.api.aws/v1",
        "https://bedrock-mantle.us-west-2.api.aws@evil.example/v1",
        "https://user:password@bedrock-mantle.us-west-2.api.aws/v1",
        "https://bedrock-mantle.us-west-2.api.aws\\@evil.example/v1",
        "https://bedrock-mantle.us-west-2.api.aws:443/v1",
        "https://bedrock-mantle.us-west-2.api.aws/openai/v1",
        "https://bedrock-mantle.us-west-2.api.aws/v1?bedrock=true",
        "https://bedrock-mantle.us-west-2.api.aws/v1#fragment",
        "https://bedrock-mantle.us-east-1.api.aws/v1",
        "not a url",
        "",
    ],
)
def test_validate_bedrock_base_url_rejects_unapproved_endpoints(endpoint: str) -> None:
    with pytest.raises(RuntimeError, match="not an approved AWS Bedrock endpoint") as exc_info:
        validate_bedrock_base_url(endpoint, "us-west-2")

    assert "password" not in str(exc_info.value)
    if endpoint:
        assert endpoint not in str(exc_info.value)
