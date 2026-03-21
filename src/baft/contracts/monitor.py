"""I/O contracts for background/scheduled workers: SA, WT, NI."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# SA — Session Advisor
# ---------------------------------------------------------------------------


class SessionMonitorRequest(BaseModel):
    """SA input: ``session_monitor_request`` wrapper."""

    session_monitor_request: SessionMonitorRequestInner


class SessionMonitorRequestInner(BaseModel):
    """Inner payload of SA session monitor request."""

    session_id: str
    transcript: str
    session_start: str | None = None
    session_objective: str | None = None
    current_tier: str | None = None
    operation_count: int | None = None


SessionMonitorRequest.model_rebuild()


class FlagSeverity(StrEnum):
    """Severity levels for SA cognitive flags."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SAflag(BaseModel):
    """A single SA advisory flag with severity and recommended action."""

    flag_type: str
    severity: FlagSeverity
    evidence: str
    recommended_action: str


class SAadvisoryInner(BaseModel):
    """Inner payload of SA advisory output."""

    no_flags: bool
    flags: list[SAflag] | None = None


class SAadvisory(BaseModel):
    """SA output: ``sa_advisory`` wrapper."""

    sa_advisory: SAadvisoryInner


# ---------------------------------------------------------------------------
# WT — Watch Tower
# ---------------------------------------------------------------------------


class WatchMode(StrEnum):
    """Operating mode for WT watch request."""

    SCAN = "scan"
    AGENDA_ASSEMBLY = "agenda_assembly"


class WatchRequestInner(BaseModel):
    """Inner payload of WT watch request."""

    watch_list_path: str
    mode: WatchMode = WatchMode.SCAN
    hours_lookback: int = 24


class WatchRequest(BaseModel):
    """WT input: ``watch_request`` wrapper."""

    watch_request: WatchRequestInner


class WatchFinding(BaseModel):
    """A single watch list item finding from WT scan."""

    item_id: str | None = None
    status: str | None = None
    summary: str | None = None
    channels_checked: list[str] | None = None


class AgendaItem(BaseModel):
    """A single prioritized agenda item for session preparation."""

    priority: str | None = None
    description: str | None = None
    source: str | None = None


class WatchResultsInner(BaseModel):
    """Inner payload of WT scan mode watch results."""

    scan_completed_at: str | None = None
    items_checked: int | None = None
    findings: list[WatchFinding]
    agenda_items: list[AgendaItem] | None = None


class SessionAgendaInner(BaseModel):
    """Inner payload of WT agenda mode session agenda."""

    generated_at: str | None = None
    priority_items: list[AgendaItem]
    secondary_items: list[AgendaItem] | None = None
    silence_alerts: list[dict[str, Any]] | None = None


class WatchResults(BaseModel):
    """WT output: scan mode ``watch_results`` wrapper."""

    watch_results: WatchResultsInner


class SessionAgenda(BaseModel):
    """WT output: agenda mode ``session_agenda`` wrapper."""

    session_agenda: SessionAgendaInner


# ---------------------------------------------------------------------------
# NI — Narrative Intelligence
# ---------------------------------------------------------------------------


class AnalysisMode(StrEnum):
    """Narrative analysis mode variants for NI."""

    COORDINATION = "coordination"
    SILENCE = "silence"
    DIVERGENCE = "divergence"
    VELOCITY = "velocity"
    TONE = "tone"
    AMPLIFICATION = "amplification"


class NIrequestInner(BaseModel):
    """Inner payload of NI narrative intelligence request."""

    corpus_path: str
    time_range: str
    analysis_modes: list[AnalysisMode] | None = None


class NIrequest(BaseModel):
    """NI input: ``ni_request`` wrapper."""

    ni_request: NIrequestInner


class Significance(StrEnum):
    """Significance level for NI findings."""

    LOW = "low"
    MEDIUM_LOW = "medium-low"
    MEDIUM = "medium"
    MEDIUM_HIGH = "medium-high"
    HIGH = "high"


class NIFinding(BaseModel):
    """A single narrative intelligence finding from NI."""

    finding_id: str
    finding_type: str
    channels_involved: list[str]
    description: str
    significance: Significance
    time_range: str | None = None
    recommended_routing: str | None = None


class NIoutputInner(BaseModel):
    """Inner payload of NI narrative intelligence output."""

    analyzed_at: str
    findings: list[NIFinding]
    messages_analyzed: int | None = None
    channels_covered: int | None = None
    no_significant_findings: bool | None = None


class NIoutput(BaseModel):
    """NI output: ``ni_output`` wrapper."""

    ni_output: NIoutputInner
