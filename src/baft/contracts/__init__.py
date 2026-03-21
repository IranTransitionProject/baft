"""Pydantic I/O contracts for Baft workers.

Each submodule defines typed input/output models for a group of workers.
These models are the source of truth for worker I/O schemas - worker YAML
configs reference them via ``input_schema_ref`` / ``output_schema_ref``,
and Loom resolves them to JSON Schema at load time.

Submodules:
    core    - SP, IA, DE, XV, IN (Tier 1-2 pipeline workers)
    audit   - TN, LA, PA, RT, AS (Tier 3 audit pipeline workers)
    monitor - SA, WT, NI (background/scheduled workers)
"""

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
    ExtractedClaims,
    InboxItem,
    IntegrationRequest,
    IntegrationResult,
    NoteInput,
    SourceBundle,
    ValidationRequest,
    ValidationResult,
)
from baft.contracts.monitor import (
    NIoutput,
    NIrequest,
    SAadvisory,
    SessionMonitorRequest,
    WatchRequest,
    WatchResults,
)

__all__ = [
    "AnalyticalInput",
    "AnalyticalOutput",
    "AuditReport",
    "AuditRequest",
    "ExtractedClaims",
    "InboxItem",
    "IntegrationRequest",
    "IntegrationResult",
    "LAaudit",
    "NIoutput",
    "NIrequest",
    "NeutralizationRequest",
    "NeutralizationResult",
    "NoteInput",
    "PAaudit",
    "RTaudit",
    "SAadvisory",
    "SessionMonitorRequest",
    "SourceBundle",
    "SynthesisRequest",
    "ValidationRequest",
    "ValidationResult",
    "WatchRequest",
    "WatchResults",
]
