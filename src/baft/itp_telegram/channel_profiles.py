"""ITP-curated Telegram channel profiles.

Loads the analyst-maintained registry at
``$ITP_ROOT/baft/pipeline/config/itp_telegram_channels.yaml`` and
produces ``heddle.contrib.rag.schemas.post.ChannelEditorProfile``
instances keyed by lowercase handle (without ``@``).

The registry is the single source of truth for channel selection; this
module is the *projection* into Heddle's runtime types.

Inclusion rule:
  Channels with ``monitoring_priority in {"critical", "high"}`` and
  ``status != "unverified"`` and a non-placeholder handle.

Augmentation (``STARTER_EXTRAS``):
  Four channels carried in from the original Telegram MCP setup brief
  that aren't in the registry — ``khamenei_ir``, ``Factnameh``,
  ``Iranwire``, ``tabnak``. ``tabnak`` is in the registry at
  ``monitoring_priority: medium`` (filtered out by the rule above);
  the starter list pulls it back in for trust-weighted analysis of
  the pragmatist-Rezaei orbit.

Channel IDs are not known until Telethon resolves them at runtime
(``baft itp-telegram resolve-ids``). Until then ``channel_id`` is 0
and the profile lookup uses the lowercase handle as the key.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from heddle.contrib.rag.schemas.post import (
    ChannelBias,
    ChannelEditorProfile,
    Language,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registry-faction → Heddle ChannelBias (and trust weight)
# ---------------------------------------------------------------------------

# Mapping rationale:
# - "regime_official", "irgc_*"             → STATE_MEDIA  (direct regime mouthpieces)
# - "eschatological_paydari_masaf"          → STATE_ALIGNED (faction propaganda, not state)
# - "reformist_pragmatist", "religious_establishment", "principlist_hardline"
#                                            → STATE_ALIGNED (within-regime counter-currents)
# - "diaspora_opposition"                    → OPPOSITION
# - "mainstream_centrist", "non_aligned"     → NEUTRAL
# - "civil_society"                          → INDEPENDENT
_FACTION_TO_BIAS: dict[str, ChannelBias] = {
    "regime_official": ChannelBias.STATE_MEDIA,
    "irgc_hardline": ChannelBias.STATE_MEDIA,
    "irgc_military": ChannelBias.STATE_MEDIA,
    "eschatological_paydari_masaf": ChannelBias.STATE_ALIGNED,
    "reformist_pragmatist": ChannelBias.STATE_ALIGNED,
    "religious_establishment": ChannelBias.STATE_ALIGNED,
    "principlist_hardline": ChannelBias.STATE_ALIGNED,
    "diaspora_opposition": ChannelBias.OPPOSITION,
    "mainstream_centrist": ChannelBias.NEUTRAL,
    "non_aligned": ChannelBias.NEUTRAL,
    "civil_society": ChannelBias.INDEPENDENT,
}

# Trust weights per faction. Tuned to match the §2 starter list values
# (state media 0.3, opposition 0.7, fact-check 0.9, independent 0.85)
# and extended to factions the starter list didn't enumerate.
_FACTION_TO_TRUST: dict[str, float] = {
    "regime_official": 0.30,
    "irgc_hardline": 0.30,
    "irgc_military": 0.25,
    "eschatological_paydari_masaf": 0.20,
    "reformist_pragmatist": 0.65,
    "religious_establishment": 0.50,
    "principlist_hardline": 0.40,
    "diaspora_opposition": 0.70,
    "mainstream_centrist": 0.50,
    "non_aligned": 0.45,
    "civil_society": 0.80,
}

_LANG_MAP: dict[str, Language] = {
    "fa": Language.PERSIAN,
    "ar": Language.ARABIC,
    "en": Language.ENGLISH,
}

# Channels added on top of the registry-derived set.
# Hardcoded here because they're either not in the registry yet
# (khamenei_ir, Factnameh, Iranwire) or were demoted by the priority
# filter but kept in the analytical baseline (tabnak).
STARTER_EXTRAS: dict[str, ChannelEditorProfile] = {
    "khamenei_ir": ChannelEditorProfile(
        channel_id=0,
        channel_name="Office of the Supreme Leader",
        channel_handle="khamenei_ir",
        bias=ChannelBias.STATE_MEDIA,
        language=Language.PERSIAN,
        trust_weight=0.30,
        description=(
            "Khamenei's office channel (handle unverified — see "
            "registry verification_queue)."
        ),
    ),
    "factnameh": ChannelEditorProfile(
        channel_id=1098179827,  # known from heddle DEFAULT_PROFILES
        channel_name="FactNameh",
        channel_handle="Factnameh",
        bias=ChannelBias.FACT_CHECK,
        language=Language.PERSIAN,
        trust_weight=0.90,
        description="Independent Persian fact-checking outlet.",
    ),
    "iranwire": ChannelEditorProfile(
        channel_id=1008727276,  # known from heddle DEFAULT_PROFILES
        channel_name="Iranwire",
        channel_handle="IranWire",
        bias=ChannelBias.INDEPENDENT,
        language=Language.PERSIAN,
        trust_weight=0.85,
        description="Diaspora investigative journalism, human rights focus.",
    ),
    "tabnak": ChannelEditorProfile(
        channel_id=0,
        channel_name="Tabnak",
        channel_handle="tabnak",
        bias=ChannelBias.NEUTRAL,
        language=Language.PERSIAN,
        trust_weight=0.50,
        description="Mainstream centrist (Mohsen Rezaei orbit).",
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_registry(registry_path: Path) -> dict:
    """Load and return the raw YAML registry (no transformation)."""
    if not registry_path.exists():
        raise FileNotFoundError(
            f"Channel registry not found at {registry_path}. "
            "Set ITP_ROOT or pass --registry."
        )
    with registry_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_itp_profiles(
    registry_path: Path,
    *,
    priorities: tuple[str, ...] = ("critical", "high"),
) -> dict[str, ChannelEditorProfile]:
    """Return the union of registry-derived + starter profiles.

    Args:
        registry_path: Path to ``itp_telegram_channels.yaml``.
        priorities: Inclusion filter on registry ``monitoring_priority``
            (default: critical and high).

    Returns:
        Dict keyed by lowercase handle (no leading ``@``) →
        ``ChannelEditorProfile``.
    """
    raw = load_registry(registry_path)
    profiles: dict[str, ChannelEditorProfile] = {}
    skipped_unverified = 0
    skipped_priority = 0

    for category in raw.get("categories", []):
        priority = category.get("monitoring_priority")
        if priority not in priorities:
            skipped_priority += len(category.get("channels", []))
            continue
        faction = category.get("faction", "non_aligned")
        bias = _FACTION_TO_BIAS.get(faction, ChannelBias.UNKNOWN)
        trust = _FACTION_TO_TRUST.get(faction, 0.50)

        for ch in category.get("channels", []):
            handle_raw = (ch.get("handle") or "").lstrip("@").strip()
            if not handle_raw or handle_raw.startswith("TBD_"):
                skipped_unverified += 1
                continue
            if ch.get("status") == "unverified":
                skipped_unverified += 1
                continue

            key = handle_raw.lower()
            language = _LANG_MAP.get(ch.get("language", ""), Language.UNKNOWN)
            profiles[key] = ChannelEditorProfile(
                channel_id=0,
                channel_name=ch.get("name_en") or handle_raw,
                channel_handle=handle_raw,
                bias=bias,
                language=language,
                trust_weight=trust,
                description=(ch.get("notes") or "").strip(),
            )

    # Layer in the starter extras (override registry on handle collision —
    # only relevant for ``tabnak`` which the priority filter excludes).
    for key, profile in STARTER_EXTRAS.items():
        profiles[key] = profile

    logger.info(
        "Loaded %d ITP channel profiles (skipped %d unverified, %d below priority)",
        len(profiles),
        skipped_unverified,
        skipped_priority,
    )
    return profiles


def channel_handles(profiles: dict[str, ChannelEditorProfile]) -> list[str]:
    """Return ``@handle`` strings ready to pass to TelegramLiveIngestor."""
    return [f"@{p.channel_handle}" for p in profiles.values() if p.channel_handle]


def by_channel_id(
    profiles: dict[str, ChannelEditorProfile],
) -> dict[int, ChannelEditorProfile]:
    """Reverse-lookup table by numeric channel_id (only for resolved profiles)."""
    return {p.channel_id: p for p in profiles.values() if p.channel_id}


def merge_resolved_ids(
    profiles: dict[str, ChannelEditorProfile],
    resolved_ids_path: Path,
) -> dict[str, ChannelEditorProfile]:
    """Backfill numeric ``channel_id`` from a ``baft itp-telegram resolve-ids`` JSON.

    Mutates and returns ``profiles``. Resolved IDs always win over the
    placeholder ``channel_id=0`` set at registry-load time AND over the
    hardcoded values in ``STARTER_EXTRAS`` — the resolved value reflects
    what Telethon actually receives messages for, which is what the MCP
    server must look up to enrich results with bias and trust_weight.

    Missing or unreadable file is non-fatal: profiles come back unchanged
    and a single info-line is logged so the operator knows enrichment
    will be incomplete.
    """
    if not resolved_ids_path.exists():
        logger.info(
            "No resolved-IDs file at %s; channel enrichment will be incomplete. "
            "Run `baft itp-telegram resolve-ids` after `auth`.",
            resolved_ids_path,
        )
        return profiles

    try:
        payload = json.loads(resolved_ids_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read resolved-IDs file %s: %s", resolved_ids_path, exc)
        return profiles

    backfilled = 0
    for handle, info in payload.get("channels", {}).items():
        key = handle.lower()
        if key not in profiles:
            continue
        cid = int(info.get("channel_id", 0))
        if not cid:
            continue
        # Pydantic v2 model_copy with update — preserves all other fields.
        profiles[key] = profiles[key].model_copy(update={"channel_id": cid})
        backfilled += 1

    logger.info(
        "Backfilled %d channel IDs from %s",
        backfilled,
        resolved_ids_path,
    )
    return profiles
