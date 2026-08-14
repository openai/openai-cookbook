"""AgentCore Runtime entrypoint for prior authorization review."""

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from policy_to_review.models import (
    PolicyMappingRequiredResponse,
    UsageSummary,
)
from policy_to_review.retrieval import PolicyMappingRequiredError
from policy_to_review.workflow import run_policy_to_review

app = BedrockAgentCoreApp()


def policy_mapping_required_response(
    error: PolicyMappingRequiredError,
) -> PolicyMappingRequiredResponse:
    return PolicyMappingRequiredResponse(
        schemaVersion="1.0",
        runtime="amazon-bedrock-agentcore",
        workflow="policy-to-review-kb-v1",
        outcome="policy_mapping_required",
        caseId=error.case_id,
        stage="select_policy",
        reasonCode="NO_POLICY_MATCH",
        message=str(error),
        policySelectionAttempt=error.attempt,
        humanActionRequired=(
            "A qualified policy specialist must locate or "
            "authoritatively map the applicable policy."
        ),
        coverageDisposition="NOT_PERFORMED",
        requestedModels=[],
        usage=UsageSummary(
            inputTokens=0,
            outputTokens=0,
            totalTokens=0,
        ),
        agentTrace=[],
    )


@app.entrypoint
async def agent_invocation(
    payload: dict[str, object],
    context: object,
) -> dict[str, object]:
    try:
        response = await run_policy_to_review(payload)
    except PolicyMappingRequiredError as error:
        response = policy_mapping_required_response(error)
    return response.model_dump(mode="json")


if __name__ == "__main__":
    app.run(
        host=os.getenv("AGENTCORE_BIND_HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8080")),
    )
