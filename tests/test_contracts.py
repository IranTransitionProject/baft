"""Tests for baft.contracts — Pydantic I/O models for all 13 workers.

Validates that:
  - All contract models instantiate with valid data
  - Required fields are enforced
  - Enums accept only valid values
  - JSON Schema generation produces expected structure
  - Round-trip: model → JSON Schema → validate sample dict
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from baft.contracts.audit import (
    AuditReport,
    AuditRequest,
    LAaudit,
    NeutralizationRequest,
    NeutralizationResult,
    PAaudit,
    RTaudit,
    SynthesisRequest,
)
from baft.contracts.core import (
    AnalyticalInput,
    AnalyticalOutput,
    AssessmentVerdict,
    BuildStatus,
    DBAction,
    EpistemicTag,
    ExtractedClaims,
    InboxItem,
    IntegrationRequest,
    IntegrationResult,
    NoteInput,
    PriorityLevel,
    SourceBundle,
    ValidationRequest,
    ValidationResult,
    XVstatus,
)
from baft.contracts.monitor import (
    NIoutput,
    NIrequest,
    SAadvisory,
    SessionMonitorRequest,
    WatchRequest,
    WatchResults,
)

# ---------------------------------------------------------------------------
# SP — Source Processor
# ---------------------------------------------------------------------------


class TestSourceBundle:
    def test_valid(self):
        sb = SourceBundle(source_bundle={"items": [{"source_tier": 3, "raw_text": "test content"}]})
        assert len(sb.source_bundle.items) == 1
        assert sb.source_bundle.items[0].source_tier == 3

    def test_missing_items_fails(self):
        with pytest.raises(ValidationError):
            SourceBundle(source_bundle={"generated_at": "2026-01-01"})

    def test_source_tier_range(self):
        with pytest.raises(ValidationError):
            SourceBundle(source_bundle={"items": [{"source_tier": 6, "raw_text": "test"}]})


class TestExtractedClaims:
    def test_valid(self):
        ec = ExtractedClaims(
            extracted_claims={
                "source_count": 1,
                "claim_count": 1,
                "claims": [
                    {
                        "claim_id": "C-001",
                        "source_tier": 3,
                        "claim_text": "Test claim",
                        "epistemic_tag": "[Fact]",
                    }
                ],
            }
        )
        assert ec.extracted_claims.claims[0].epistemic_tag == EpistemicTag.FACT

    def test_invalid_epistemic_tag_fails(self):
        with pytest.raises(ValidationError):
            ExtractedClaims(
                extracted_claims={
                    "source_count": 1,
                    "claim_count": 1,
                    "claims": [
                        {
                            "claim_id": "C-001",
                            "source_tier": 3,
                            "claim_text": "Test",
                            "epistemic_tag": "[Invalid]",
                        }
                    ],
                }
            )


# ---------------------------------------------------------------------------
# IA — Intelligence Analyst
# ---------------------------------------------------------------------------


class TestAnalyticalIO:
    def test_input_valid(self):
        ai = AnalyticalInput(analytical_input={"extracted_claims": {"claims": []}})
        assert ai.analytical_input.extracted_claims is not None

    def test_output_valid(self):
        ao = AnalyticalOutput(
            analytical_output={
                "claims_assessed": [{"claim_id": "C-001", "assessment": "corroborates"}],
                "integration_spec": {"operations": []},
            }
        )
        assert ao.analytical_output.claims_assessed[0].assessment == AssessmentVerdict.CORROBORATES

    def test_invalid_assessment_fails(self):
        with pytest.raises(ValidationError):
            AnalyticalOutput(
                analytical_output={
                    "claims_assessed": [{"claim_id": "C-001", "assessment": "bogus"}],
                    "integration_spec": {"operations": []},
                }
            )


# ---------------------------------------------------------------------------
# DE — Database Engineer
# ---------------------------------------------------------------------------


class TestIntegrationIO:
    def test_request_valid(self):
        ir = IntegrationRequest(
            integration_request={
                "operations": [{"action": "create", "target_file": "variables.yaml"}]
            }
        )
        assert ir.integration_request.operations[0].action == DBAction.CREATE

    def test_result_valid(self):
        result = IntegrationResult(
            integration_result={
                "operations_attempted": 1,
                "operations_succeeded": 1,
                "operations_failed": 0,
                "results": [],
                "build_status": "PASS",
            }
        )
        assert result.integration_result.build_status == BuildStatus.PASS


# ---------------------------------------------------------------------------
# XV — Cross Validator
# ---------------------------------------------------------------------------


class TestValidationIO:
    def test_request_valid(self):
        vr = ValidationRequest(
            validation_request={
                "integration_spec": {"operations": []},
                "entity_refs": ["V-16", "Obs-042"],
            }
        )
        assert len(vr.validation_request.entity_refs) == 2

    def test_result_valid(self):
        vr = ValidationResult(
            validation_result={
                "overall_status": "PASS",
                "checked_count": 2,
                "failed_count": 0,
                "details": [{"entity_id": "V-16", "status": "FOUND"}],
            }
        )
        assert vr.validation_result.overall_status == XVstatus.PASS


# ---------------------------------------------------------------------------
# IN — Input Node
# ---------------------------------------------------------------------------


class TestNoteIO:
    def test_input_valid(self):
        ni = NoteInput(note="Quick finding about IRGC movement")
        assert ni.note.startswith("Quick")

    def test_output_valid(self):
        ii = InboxItem(
            inbox_item={
                "item_id": "IN-001",
                "captured_at": "2026-03-15T14:00:00Z",
                "raw_note": "test",
                "priority": "normal",
                "route_to": "SP_queue",
                "processed": False,
            }
        )
        assert ii.inbox_item.priority == PriorityLevel.NORMAL


# ---------------------------------------------------------------------------
# TN — Terminology Neutralizer
# ---------------------------------------------------------------------------


class TestNeutralizationIO:
    def test_request_valid(self):
        nr = NeutralizationRequest(
            neutralization_request={"analytical_text": "The A9 Hollowness thesis..."}
        )
        assert "A9" in nr.neutralization_request.analytical_text

    def test_result_valid(self):
        result = NeutralizationResult(
            neutralization_result={
                "neutralized_text": "The structural-fragility thesis...",
                "replacements_applied": [
                    {"original": "A9 Hollowness", "replacement": "structural-fragility", "count": 1}
                ],
                "reverse_map": {"structural-fragility": "A9 Hollowness"},
                "replacement_count": 1,
            }
        )
        assert result.neutralization_result.replacement_count == 1


# ---------------------------------------------------------------------------
# LA, PA, RT — Audit Nodes
# ---------------------------------------------------------------------------


class TestAuditRequest:
    def test_valid(self):
        ar = AuditRequest(audit_request={"neutralized_text": "neutral text", "audit_id": "AUD-001"})
        assert ar.audit_request.audit_id == "AUD-001"

    def test_missing_audit_id_fails(self):
        with pytest.raises(ValidationError):
            AuditRequest(audit_request={"neutralized_text": "text"})


class TestLAaudit:
    def test_valid(self):
        la = LAaudit(
            la_audit={
                "audit_id": "AUD-001",
                "auditor": "la_logic_auditor",
                "dimensions": [
                    {
                        "dimension": "factual_accuracy",
                        "score": 8,
                        "justification": "Strong evidence",
                    }
                ],
                "overall_score": 8.0,
            }
        )
        assert la.la_audit.dimensions[0].score == 8


class TestRTaudit:
    def test_valid(self):
        rt = RTaudit(
            rt_audit={
                "audit_id": "AUD-001",
                "auditor": "rt_red_teamer",
                "escalation_required": True,
                "challenges": [
                    {
                        "challenge_id": "CH-001",
                        "claim_challenged": "claim X",
                        "counter_argument": "but what about Y",
                        "strength": 9,
                    }
                ],
                "max_challenge_strength": 9,
            }
        )
        assert rt.rt_audit.escalation_required is True
        assert rt.rt_audit.challenges[0].strength == 9

    def test_strength_out_of_range_fails(self):
        with pytest.raises(ValidationError):
            RTaudit(
                rt_audit={
                    "audit_id": "AUD-001",
                    "auditor": "rt_red_teamer",
                    "escalation_required": False,
                    "challenges": [
                        {
                            "challenge_id": "CH-001",
                            "claim_challenged": "X",
                            "counter_argument": "Y",
                            "strength": 11,
                        }
                    ],
                    "max_challenge_strength": 11,
                }
            )


# ---------------------------------------------------------------------------
# AS — Audit Synthesizer
# ---------------------------------------------------------------------------


class TestAuditSynthesisIO:
    def test_request_valid(self):
        sr = SynthesisRequest(
            synthesis_request={
                "audit_id": "AUD-001",
                "la_audit": {},
                "pa_audit": {},
                "rt_audit": {},
            }
        )
        assert sr.synthesis_request.audit_id == "AUD-001"

    def test_report_valid(self):
        ar = AuditReport(
            audit_report={
                "audit_id": "AUD-001",
                "escalation_required": False,
                "consensus_findings": ["finding 1"],
                "conflicts": [],
                "recommended_decisions": ["proceed"],
            }
        )
        assert ar.audit_report.escalation_required is False


# ---------------------------------------------------------------------------
# SA — Session Advisor
# ---------------------------------------------------------------------------


class TestSessionAdvisorIO:
    def test_request_valid(self):
        smr = SessionMonitorRequest(
            session_monitor_request={
                "session_id": "S25",
                "transcript": "Analyst working on V-16...",
            }
        )
        assert smr.session_monitor_request.session_id == "S25"

    def test_advisory_no_flags(self):
        sa = SAadvisory(sa_advisory={"no_flags": True})
        assert sa.sa_advisory.no_flags is True

    def test_advisory_with_flags(self):
        sa = SAadvisory(
            sa_advisory={
                "no_flags": False,
                "flags": [
                    {
                        "flag_type": "tunnel_vision",
                        "severity": "medium",
                        "evidence": "40 min on single variable",
                        "recommended_action": "broaden scope",
                    }
                ],
            }
        )
        assert len(sa.sa_advisory.flags) == 1


# ---------------------------------------------------------------------------
# WT — Watch Tower
# ---------------------------------------------------------------------------


class TestWatchTowerIO:
    def test_request_valid(self):
        wr = WatchRequest(watch_request={"watch_list_path": "/path/to/watch_list.yaml"})
        assert wr.watch_request.hours_lookback == 24  # default

    def test_results_valid(self):
        wr = WatchResults(watch_results={"findings": [{"item_id": "W-01", "status": "active"}]})
        assert len(wr.watch_results.findings) == 1


# ---------------------------------------------------------------------------
# NI — Narrative Intelligence
# ---------------------------------------------------------------------------


class TestNarrativeIntelligenceIO:
    def test_request_valid(self):
        nr = NIrequest(
            ni_request={
                "corpus_path": "/data/telegram",
                "time_range": "2026-03-01/2026-03-15",
            }
        )
        assert nr.ni_request.time_range.startswith("2026")

    def test_output_valid(self):
        no = NIoutput(
            ni_output={
                "analyzed_at": "2026-03-15T14:00:00Z",
                "findings": [
                    {
                        "finding_id": "NI-001",
                        "finding_type": "coordination",
                        "channels_involved": ["ch1", "ch2"],
                        "description": "Coordinated messaging",
                        "significance": "high",
                    }
                ],
            }
        )
        assert no.ni_output.findings[0].significance.value == "high"


# ---------------------------------------------------------------------------
# JSON Schema generation — all models produce valid schemas
# ---------------------------------------------------------------------------


ALL_MODELS = [
    SourceBundle,
    ExtractedClaims,
    AnalyticalInput,
    AnalyticalOutput,
    IntegrationRequest,
    IntegrationResult,
    ValidationRequest,
    ValidationResult,
    NoteInput,
    InboxItem,
    NeutralizationRequest,
    NeutralizationResult,
    AuditRequest,
    LAaudit,
    PAaudit,
    RTaudit,
    SynthesisRequest,
    AuditReport,
    SessionMonitorRequest,
    SAadvisory,
    WatchRequest,
    WatchResults,
    NIrequest,
    NIoutput,
]


class TestSchemaGeneration:
    @pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.__name__)
    def test_generates_valid_json_schema(self, model):
        schema = model.model_json_schema()
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert "properties" in schema or "$defs" in schema
