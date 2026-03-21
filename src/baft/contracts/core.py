"""I/O contracts for Tier 1-2 core pipeline workers: SP, IA, DE, XV, IN."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# SP — Source Processor
# ---------------------------------------------------------------------------


class EpistemicTag(StrEnum):
    """Epistemic classification tags for claims."""

    FACT = "[Fact]"
    INFERENCE = "[Inference]"
    UNCERTAIN = "[Uncertain]"
    SPECULATION = "[Speculation]"


class SourceItem(BaseModel):
    """A single raw source item in the source bundle."""

    global_id: str | None = None
    url: Any = None
    language: str | None = None
    source_tier: int = Field(..., ge=1, le=5)
    faction_tag: str | None = None
    retrieval_date: str | None = None
    raw_text: str
    normalized_text: Any = None
    is_forward: bool | None = None
    forwarded_from: Any = None


class SourceBundle(BaseModel):
    """SP input: ``source_bundle`` wrapper."""

    source_bundle: SourceBundleInner


class SourceBundleInner(BaseModel):
    """Inner payload of SP source bundle input."""

    generated_at: str | None = None
    items: list[SourceItem]


# Pydantic needs forward-ref update for SourceBundle → SourceBundleInner.
SourceBundle.model_rebuild()


class Claim(BaseModel):
    """A single extracted claim with epistemic classification."""

    claim_id: str
    source_global_id: str | None = None
    source_tier: int
    faction_tag: str | None = None
    language: str | None = None
    claim_text: str
    raw_excerpt: str | None = None
    epistemic_tag: EpistemicTag
    entity_ids: list[str] | None = None
    entity_candidates: list[str] | None = None
    is_forward: bool | None = None
    forwarded_from: Any = None
    provenance_flag: bool | None = None


class ExtractedClaimsInner(BaseModel):
    """Inner payload of SP extracted claims output."""

    processed_at: str | None = None
    source_count: int
    claim_count: int
    claims: list[Claim]
    languages_detected: list[str] | None = None
    low_confidence_count: int | None = None


class ExtractedClaims(BaseModel):
    """SP output: ``extracted_claims`` wrapper."""

    extracted_claims: ExtractedClaimsInner


# ---------------------------------------------------------------------------
# IA — Intelligence Analyst
# ---------------------------------------------------------------------------


class AssessmentVerdict(StrEnum):
    """Verdict categories for IA claim assessment."""

    CORROBORATES = "corroborates"
    CONTRADICTS = "contradicts"
    UPDATES_VARIABLE = "updates_variable"
    FILLS_GAP = "fills_gap"
    TRIGGERS_TRAP = "triggers_trap"
    NEW_INTELLIGENCE = "new_intelligence"
    NOISE = "noise"


class AnalyticalInput(BaseModel):
    """IA input: ``analytical_input`` wrapper."""

    analytical_input: AnalyticalInputInner


class AnalyticalInputInner(BaseModel):
    """Inner payload of IA analytical input."""

    extracted_claims: Any
    session_id: str | None = None
    analyst_note: str | None = None
    priority_gaps: list[str] | None = None


AnalyticalInput.model_rebuild()


class ClaimAssessment(BaseModel):
    """Assessment verdict for a single claim."""

    claim_id: str
    assessment: AssessmentVerdict
    entity_ids: list[str] | None = None
    analytical_note: str | None = None


class IntegrationSpec(BaseModel):
    """Database integration specification produced by IA."""

    session_id: str | None = None
    operations: list[dict[str, Any]] = Field(default_factory=list)


class AnalyticalOutputInner(BaseModel):
    """Inner payload of IA analytical output."""

    claims_assessed: list[ClaimAssessment]
    new_observations: list[dict[str, Any]] | None = None
    variable_updates: list[dict[str, Any]] | None = None
    scenario_updates: list[dict[str, Any]] | None = None
    gap_fills: list[dict[str, Any]] | None = None
    integration_spec: IntegrationSpec
    publication_flag: bool | None = None


class AnalyticalOutput(BaseModel):
    """IA output: ``analytical_output`` wrapper."""

    analytical_output: AnalyticalOutputInner


# ---------------------------------------------------------------------------
# DE — Database Engineer
# ---------------------------------------------------------------------------


class DBAction(StrEnum):
    """Supported database operation action types."""

    CREATE = "create"
    UPDATE = "update"
    APPEND = "append"
    VALIDATE_ONLY = "validate_only"


class DBOperation(BaseModel):
    """A single database operation in an integration request."""

    action: DBAction
    target_file: str
    entity_id: str | None = None
    fields: dict[str, Any] | None = None


class IntegrationRequest(BaseModel):
    """DE input: ``integration_request`` wrapper."""

    integration_request: IntegrationRequestInner


class IntegrationRequestInner(BaseModel):
    """Inner payload of DE integration request."""

    operation_id: str | None = None
    operations: list[DBOperation]


IntegrationRequest.model_rebuild()


class BuildStatus(StrEnum):
    """Overall build status after DE operations."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"


class OperationResultItem(BaseModel):
    """Result detail for a single DE database operation."""

    operation_index: int | None = None
    action: str | None = None
    target_file: str | None = None
    status: str | None = None
    message: str | None = None


class IntegrationResultInner(BaseModel):
    """Inner payload of DE integration result."""

    operations_attempted: int
    operations_succeeded: int
    operations_failed: int
    results: list[OperationResultItem]
    build_status: BuildStatus
    session_operation_count: int | None = None
    ga_notification: str | None = None


class IntegrationResult(BaseModel):
    """DE output: ``integration_result`` wrapper."""

    integration_result: IntegrationResultInner


# ---------------------------------------------------------------------------
# XV — Cross Validator
# ---------------------------------------------------------------------------


class XVstatus(StrEnum):
    """Overall validation status from XV cross-validator."""

    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"


class EntityCheckStatus(StrEnum):
    """Per-entity lookup status from XV."""

    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    WARNING = "WARNING"


class EntityCheckDetail(BaseModel):
    """Detail of a single entity check by XV."""

    entity_id: str
    status: EntityCheckStatus
    note: str | None = None


class ValidationRequestInner(BaseModel):
    """Inner payload of XV validation request."""

    integration_spec: dict[str, Any]
    entity_refs: list[str]


class ValidationRequest(BaseModel):
    """XV input: ``validation_request`` wrapper."""

    validation_request: ValidationRequestInner


class ValidationResultInner(BaseModel):
    """Inner payload of XV validation result."""

    overall_status: XVstatus
    checked_count: int
    failed_count: int
    details: list[EntityCheckDetail]


class ValidationResult(BaseModel):
    """XV output: ``validation_result`` wrapper."""

    validation_result: ValidationResultInner


# ---------------------------------------------------------------------------
# IN — Input Node
# ---------------------------------------------------------------------------


class PriorityLevel(StrEnum):
    """Priority tiers for inbox items captured by IN."""

    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class NoteInput(BaseModel):
    """IN input: raw analyst note."""

    note: str
    priority_override: PriorityLevel | None = None


class InboxItem(BaseModel):
    """IN output: ``inbox_item`` wrapper."""

    inbox_item: InboxItemInner


class InboxItemInner(BaseModel):
    """Inner payload of IN inbox item output."""

    item_id: str
    captured_at: str
    raw_note: str
    priority: PriorityLevel
    route_to: str
    entity_ids: list[str] | None = None
    source_refs: list[str] | None = None
    epistemic_hint: str | None = None
    processed: bool


InboxItem.model_rebuild()
