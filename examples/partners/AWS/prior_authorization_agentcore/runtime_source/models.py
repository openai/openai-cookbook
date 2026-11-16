"""Typed contracts for the prior authorization review example."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(StrictModel):
    id: str = Field(min_length=1)
    kind: Literal["clinical_note", "diagnostic_result", "coverage", "order"]
    label: str = Field(min_length=1)
    content: str = Field(min_length=1)


class PolicyCriterion(StrictModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    requirement: str = Field(min_length=1)


class PolicyReference(StrictModel):
    policyId: str = Field(min_length=1)
    version: str = Field(min_length=1)


class PolicyDefinition(StrictModel):
    policyId: str = Field(min_length=1)
    title: str = Field(min_length=1)
    version: str = Field(min_length=1)
    effectiveDate: str = Field(min_length=1)
    criteria: list[PolicyCriterion] = Field(min_length=1)


class RequestedService(StrictModel):
    code: str = Field(min_length=1)
    description: str = Field(min_length=1)
    requestedAt: str = Field(min_length=1)


class PriorAuthorizationCase(StrictModel):
    caseId: str = Field(min_length=1)
    memberId: str = Field(min_length=1)
    payer: str = Field(min_length=1)
    coverage: str = Field(min_length=1)
    diagnosis: str = Field(min_length=1)
    requestedService: RequestedService
    policy: PolicyReference
    evidence: list[EvidenceItem] = Field(min_length=1)


class Safeguards(StrictModel):
    dataClassification: Literal["synthetic", "customer-governed"]
    autonomousDispositionAllowed: Literal[False]
    humanDispositionRequired: Literal[True]
    storeModelResponses: Literal[False]


class ReviewRequest(StrictModel):
    schemaVersion: Literal["1.0"]
    operation: Literal["policy_to_review"]
    case: PriorAuthorizationCase
    safeguards: Safeguards


class PolicyChunk(StrictModel):
    documentId: str = Field(min_length=1)
    sourceDocumentId: str = Field(min_length=1)
    sourceUri: str = Field(min_length=1)
    score: float | None
    content: str = Field(min_length=1)
    metadata: dict[str, Any]


class PolicySelectionAttempt(StrictModel):
    provider: Literal["bedrock-knowledge-base"]
    knowledgeBaseId: str = Field(min_length=1)
    query: str = Field(min_length=1)
    filters: list[dict[str, Any]] = Field(min_length=1)
    selectionRule: str = Field(min_length=1)
    candidatePolicyKeys: list[str]
    retrievedResultCount: int = Field(ge=0)


class PolicySelection(StrictModel):
    provider: Literal["bedrock-knowledge-base"]
    knowledgeBaseId: str = Field(min_length=1)
    query: str = Field(min_length=1)
    filters: list[dict[str, Any]] = Field(min_length=1)
    selectionRule: str = Field(min_length=1)
    policyId: str = Field(min_length=1)
    version: str = Field(min_length=1)
    sourceUris: list[str] = Field(min_length=1)
    candidatePolicyKeys: list[str] = Field(min_length=1)
    topScore: float
    retrievedChunkCount: int = Field(ge=1)
    chunks: list[PolicyChunk] = Field(min_length=1)


class EvidenceInventoryItem(StrictModel):
    sourceId: str = Field(min_length=1)
    label: str = Field(min_length=1)
    salientFacts: list[str]


class IntakeNormalization(StrictModel):
    caseId: str = Field(min_length=1)
    requestedService: str = Field(min_length=1)
    evidenceInventory: list[EvidenceInventoryItem]
    unresolvedGaps: list[str]


class EvidenceCitation(StrictModel):
    sourceId: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)


class PolicyCitation(StrictModel):
    sourceDocumentId: str = Field(min_length=1)
    sourceUri: str = Field(min_length=1)
    excerpt: str = Field(min_length=1)


class CriterionAssessment(StrictModel):
    criterionId: str = Field(min_length=1)
    status: Literal["met", "not_met", "unknown", "conflicting"]
    rationale: str = Field(min_length=1)
    evidence: list[EvidenceCitation]
    policyEvidence: list[PolicyCitation] = Field(min_length=1)


class PolicyMapping(StrictModel):
    caseId: str = Field(min_length=1)
    policyId: str = Field(min_length=1)
    policyVersion: str = Field(min_length=1)
    criteria: list[CriterionAssessment] = Field(min_length=1)
    missingInformation: list[str]


class FinalAssessment(StrictModel):
    caseId: str = Field(min_length=1)
    policyId: str = Field(min_length=1)
    policyVersion: str = Field(min_length=1)
    overallStatus: Literal["complete", "incomplete", "conflicting"]
    recommendedQueue: Literal[
        "request_more_information",
        "human_clinical_review",
        "ready_for_human_approval_review",
    ]
    summary: str = Field(min_length=1)
    criteria: list[CriterionAssessment] = Field(min_length=1)
    missingInformation: list[str]
    expertReviewRequired: Literal[True]


class UsageSummary(StrictModel):
    inputTokens: int = Field(ge=0)
    outputTokens: int = Field(ge=0)
    totalTokens: int = Field(ge=0)


class AgentTraceItem(StrictModel):
    stage: Literal["intake", "policy_mapping", "review_synthesis"]
    model: str = Field(min_length=1)
    status: Literal["completed"]


class PolicyMappingRequiredResponse(StrictModel):
    schemaVersion: Literal["1.0"]
    runtime: Literal["amazon-bedrock-agentcore"]
    workflow: Literal["policy-to-review-kb-v1"]
    outcome: Literal["policy_mapping_required"]
    caseId: str = Field(min_length=1)
    stage: Literal["select_policy"]
    reasonCode: Literal["NO_POLICY_MATCH"]
    message: str = Field(min_length=1)
    policySelectionAttempt: PolicySelectionAttempt
    humanActionRequired: str = Field(min_length=1)
    coverageDisposition: Literal["NOT_PERFORMED"]
    requestedModels: list[str] = Field(max_length=0)
    usage: UsageSummary
    agentTrace: list[AgentTraceItem] = Field(max_length=0)


class RuntimeResponse(StrictModel):
    schemaVersion: Literal["1.0"]
    runtime: Literal["amazon-bedrock-agentcore"]
    workflow: Literal["policy-to-review-kb-v1"]
    outcome: Literal["review_ready"]
    reviewId: str = Field(min_length=1)
    policySelection: PolicySelection
    assessment: FinalAssessment
    coverageDisposition: Literal["NOT_PERFORMED"]
    requestedModels: list[str] = Field(min_length=3, max_length=3)
    usage: UsageSummary
    agentTrace: list[AgentTraceItem] = Field(min_length=3, max_length=3)
