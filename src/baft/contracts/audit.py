"""I/O contracts for Tier 3 audit pipeline workers: TN, LA, PA, RT, AS."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# TN — Terminology Neutralizer
# ---------------------------------------------------------------------------


class ContentType(StrEnum):
    """Content type variants for TN neutralization input."""

    ANALYTICAL_OUTPUT_YAML = "analytical_output_yaml"
    OBSERVATION_TEXT = "observation_text"
    BRIEF_SECTION = "brief_section"


class NeutralizationRequestInner(BaseModel):
    """Inner payload for TN neutralization request."""

    analytical_text: str
    content_type: str | None = None


class NeutralizationRequest(BaseModel):
    """TN input: ``neutralization_request`` wrapper."""

    neutralization_request: NeutralizationRequestInner


class Replacement(BaseModel):
    """A single term replacement applied during neutralization."""

    original: str
    replacement: str
    count: int


class NeutralizationResultInner(BaseModel):
    """Inner payload of TN neutralization result."""

    neutralized_text: str
    replacements_applied: list[Replacement]
    reverse_map: dict[str, str]
    replacement_count: int


class NeutralizationResult(BaseModel):
    """TN output: ``neutralization_result`` wrapper."""

    neutralization_result: NeutralizationResultInner


# ---------------------------------------------------------------------------
# LA / PA / RT — Shared audit input
# ---------------------------------------------------------------------------


class AuditRequestInner(BaseModel):
    """Inner payload for shared LA/PA/RT audit request."""

    neutralized_text: str
    audit_id: str
    content_type: str | None = None


class AuditRequest(BaseModel):
    """Shared input for LA, PA, RT: ``audit_request`` wrapper."""

    audit_request: AuditRequestInner


# ---------------------------------------------------------------------------
# LA — Logic Auditor
# ---------------------------------------------------------------------------


class AuditDimension(BaseModel):
    """Scored audit dimension with justification."""

    dimension: str
    score: int = Field(..., ge=1, le=10)
    justification: str
    issues: list[str] | None = None


class LAauditInner(BaseModel):
    """Inner payload of LA logic audit result."""

    audit_id: str
    auditor: str = "la_logic_auditor"
    dimensions: list[AuditDimension]
    overall_score: float
    top_issues: list[str] | None = None
    recommended_revision: str | None = None


class LAaudit(BaseModel):
    """LA output: ``la_audit`` wrapper."""

    la_audit: LAauditInner


# ---------------------------------------------------------------------------
# PA — Perspective Auditor
# ---------------------------------------------------------------------------


class PAauditInner(BaseModel):
    """Inner payload of PA perspective audit result."""

    audit_id: str
    auditor: str = "pa_perspective_auditor"
    dimensions: list[AuditDimension]
    overall_score: float
    top_issues: list[str] | None = None
    recommended_revision: str | None = None


class PAaudit(BaseModel):
    """PA output: ``pa_audit`` wrapper."""

    pa_audit: PAauditInner


# ---------------------------------------------------------------------------
# RT — Red Teamer
# ---------------------------------------------------------------------------


class Challenge(BaseModel):
    """A single red-team challenge against a claim."""

    challenge_id: str
    claim_challenged: str
    counter_argument: str
    strength: int = Field(..., ge=1, le=10)
    evidence_basis: str | None = None
    requires_revision: bool | None = None


class RTauditInner(BaseModel):
    """Inner payload of RT red-team audit result."""

    audit_id: str
    auditor: str = "rt_red_teamer"
    escalation_required: bool
    challenges: list[Challenge]
    max_challenge_strength: int
    summary_assessment: str | None = None


class RTaudit(BaseModel):
    """RT output: ``rt_audit`` wrapper."""

    rt_audit: RTauditInner


# ---------------------------------------------------------------------------
# AS — Audit Synthesizer
# ---------------------------------------------------------------------------


class SynthesisRequestInner(BaseModel):
    """Inner payload for AS synthesis request."""

    audit_id: str
    la_audit: dict[str, Any]
    pa_audit: dict[str, Any]
    rt_audit: dict[str, Any]
    reverse_map: dict[str, str] | None = None
    original_ia_output_summary: str | None = None


class SynthesisRequest(BaseModel):
    """AS input: ``synthesis_request`` wrapper."""

    synthesis_request: SynthesisRequestInner


class OverallQuality(BaseModel):
    """Composite quality scores from LA, PA, and RT auditors."""

    la_score: float | None = None
    pa_score: float | None = None
    rt_max_challenge: int | None = None
    composite: float | None = None


class AuditReportInner(BaseModel):
    """Inner payload of AS audit synthesis report."""

    audit_id: str
    escalation_required: bool
    escalation_trigger: str | None = None
    consensus_findings: list[str]
    conflicts: list[str]
    blind_spot_alerts: list[str] | None = None
    recommended_decisions: list[str]
    integration_patch: dict[str, Any] | None = None
    overall_quality: OverallQuality | None = None


class AuditReport(BaseModel):
    """AS output: ``audit_report`` wrapper."""

    audit_report: AuditReportInner
