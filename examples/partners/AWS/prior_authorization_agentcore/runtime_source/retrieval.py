"""Deterministic policy retrieval from Amazon Bedrock Knowledge Bases."""

import os
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.config import Config

from .models import (
    PolicyChunk,
    PolicyDefinition,
    PolicySelection,
    PolicySelectionAttempt,
    PriorAuthorizationCase,
)

DEFAULT_REGION = "us-east-2"
DEFAULT_MINIMUM_SCORE = 0.65
DEFAULT_RESULT_COUNT = 6
CMS_AUTHORITY = "Centers for Medicare & Medicaid Services"


class PolicyMappingRequiredError(Exception):
    def __init__(
        self,
        *,
        case_id: str,
        attempt: PolicySelectionAttempt,
    ) -> None:
        super().__init__(
            "No active policy matched the payer, plan, service code, "
            "and request date."
        )
        self.case_id = case_id
        self.attempt = attempt


def _epoch_seconds(value: str) -> int:
    parsed = datetime.fromisoformat(f"{value}T23:59:59+00:00")
    return int(parsed.astimezone(UTC).timestamp())


def _query(
    case: PriorAuthorizationCase,
    policy: PolicyDefinition,
) -> str:
    criteria = " | ".join(
        f"{item.label}: {item.requirement}"
        for item in policy.criteria
    )
    return " | ".join(
        [
            case.requestedService.code,
            case.requestedService.description,
            case.diagnosis,
            criteria,
        ]
    )


def _filters(case: PriorAuthorizationCase) -> list[dict[str, Any]]:
    return [
        {"equals": {"key": "payer", "value": case.payer}},
        {"equals": {"key": "plan", "value": case.coverage}},
        {
            "equals": {
                "key": "service_code",
                "value": case.requestedService.code,
            }
        },
        {"equals": {"key": "policy_status", "value": "active"}},
        {
            "lessThanOrEquals": {
                "key": "effective_date_epoch",
                "value": _epoch_seconds(
                    case.requestedService.requestedAt
                ),
            }
        },
    ]


def _source_uri(result: dict[str, Any]) -> str:
    location = result.get("location", {})
    return (
        location.get("s3Location", {}).get("uri")
        or location.get("webLocation", {}).get("url")
        or "bedrock-kb://unknown-source"
    )


def retrieve_policy(
    case: PriorAuthorizationCase,
    policy: PolicyDefinition,
) -> PolicySelection:
    if (
        case.policy.policyId != policy.policyId
        or case.policy.version != policy.version
    ):
        raise ValueError(
            "Trusted policy does not match the request reference."
        )
    knowledge_base_id = os.getenv("BEDROCK_KNOWLEDGE_BASE_ID")
    if not knowledge_base_id:
        raise RuntimeError(
            "BEDROCK_KNOWLEDGE_BASE_ID is required; no local fallback exists."
        )

    query = _query(case, policy)
    filters = _filters(case)
    result_count = int(
        os.getenv("BEDROCK_KB_RESULT_COUNT", str(DEFAULT_RESULT_COUNT))
    )
    if not 1 <= result_count <= 20:
        raise ValueError("BEDROCK_KB_RESULT_COUNT must be between 1 and 20.")
    region = (
        os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or DEFAULT_REGION
    )
    client = boto3.client(
        "bedrock-agent-runtime",
        region_name=region,
        config=Config(
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )
    response = client.retrieve(
        knowledgeBaseId=knowledge_base_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": result_count,
                "filter": {"andAll": filters},
            }
        },
    )

    chunks = []
    candidate_keys = set()
    for index, result in enumerate(response.get("retrievalResults", [])):
        metadata = result.get("metadata", {})
        policy_id = metadata.get("policy_id")
        policy_version = metadata.get("policy_version")
        if isinstance(policy_id, str) and isinstance(policy_version, str):
            candidate_keys.add(f"{policy_id}:{policy_version}")

        if (
            policy_id != policy.policyId
            or policy_version != policy.version
        ):
            continue
        if metadata.get("source_authority") != CMS_AUTHORITY:
            raise ValueError("Retrieved policy authority is not CMS.")

        source_url = metadata.get("source_url") or _source_uri(result)
        if not source_url.startswith("https://www.cms.gov/"):
            raise ValueError("Retrieved policy did not preserve an official CMS URL.")
        source_document_id = metadata.get("source_document_id")
        if not isinstance(source_document_id, str) or not source_document_id:
            raise ValueError("Retrieved policy is missing its CMS document ID.")

        content = result.get("content", {}).get("text", "")
        if not content:
            continue
        chunks.append(
            PolicyChunk(
                documentId=(
                    result.get("documentId")
                    or f"{policy_id}:{policy_version}:chunk-{index + 1}"
                ),
                sourceDocumentId=source_document_id,
                sourceUri=source_url,
                score=result.get("score"),
                content=content,
                metadata={
                    key: value
                    for key, value in metadata.items()
                    if isinstance(value, (str, int, float, bool))
                },
            )
        )

    expected_key = f"{policy.policyId}:{policy.version}"
    if expected_key not in candidate_keys or not chunks:
        raise PolicyMappingRequiredError(
            case_id=case.caseId,
            attempt=PolicySelectionAttempt(
                provider="bedrock-knowledge-base",
                knowledgeBaseId=knowledge_base_id,
                query=query,
                filters=filters,
                selectionRule=(
                    "Exact payer, plan, service-code, active-status, "
                    "and effective-date filters returned no eligible "
                    "mapped public CMS policy."
                ),
                candidatePolicyKeys=sorted(candidate_keys),
                retrievedResultCount=len(
                    response.get("retrievalResults", [])
                ),
            ),
        )
    if candidate_keys != {expected_key}:
        raise ValueError(
            "More than one policy identity remained after deterministic filters."
        )

    scores = [chunk.score for chunk in chunks if chunk.score is not None]
    if not scores:
        raise ValueError("Bedrock retrieval returned no similarity scores.")
    top_score = max(scores)
    minimum_score = float(
        os.getenv("BEDROCK_KB_MIN_SCORE", str(DEFAULT_MINIMUM_SCORE))
    )
    if top_score < minimum_score:
        raise ValueError(
            f"Top retrieval score {top_score:.3f} is below "
            f"the configured threshold {minimum_score:.3f}."
        )

    return PolicySelection(
        provider="bedrock-knowledge-base",
        knowledgeBaseId=knowledge_base_id,
        query=query,
        filters=filters,
        selectionRule=(
            "Exact metadata establishes eligibility; the application then "
            "requires the expected mapped policy ID and version, official CMS "
            "authority and URL, and the configured minimum retrieval score."
        ),
        policyId=policy.policyId,
        version=policy.version,
        sourceUris=sorted({chunk.sourceUri for chunk in chunks}),
        candidatePolicyKeys=sorted(candidate_keys),
        topScore=top_score,
        retrievedChunkCount=len(chunks),
        chunks=chunks,
    )
