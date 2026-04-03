#!/usr/bin/env python3
"""Convert a Telegram JSON export into SP source_bundle format.

Parses Telegram JSON via heddle's TelegramIngestor, enriches with channel
metadata, applies keyword pre-filter against the WT watch list, and emits
a ``source_bundle.yaml`` in SP input schema format.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict | list:
    """Load a YAML file, returning an empty dict on empty content."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_watch_keywords(watch_list: dict) -> set[str]:
    """Extract all search terms from WT watch list items."""
    keywords: set[str] = set()
    for item in watch_list.get("items", []):
        for term in item.get("search_terms", []):
            keywords.add(term.lower())
        for term in item.get("search_terms_fa", []):
            keywords.add(term.lower())
        # Entity names also count
        if "entity_id" in item:
            keywords.add(item["entity_id"].lower())
        if "entity_name" in item:
            keywords.add(item["entity_name"].lower())
    return keywords


def message_matches_keywords(text: str, keywords: set[str]) -> bool:
    """Return True if message text contains any watch keyword."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def build_source_entry(post, channel_meta: dict, watch_match: bool) -> dict:
    """Convert a NormalizedPost to SP source_bundle item format."""
    return {
        "global_id": post.global_id,
        "url": None,  # Telegram has no URL — identified by global_id
        "language": post.language.value if hasattr(post.language, "value") else str(post.language),
        "source_tier": channel_meta.get("source_tier", 4),
        "faction_tag": channel_meta.get("faction", "unknown"),
        "retrieval_date": datetime.now(UTC).date().isoformat(),
        "timestamp": post.timestamp.isoformat()
        if hasattr(post.timestamp, "isoformat")
        else str(post.timestamp),
        "channel_id": post.source_channel_id,
        "channel_name": post.source_channel_name,
        "raw_text": post.text_raw,
        "normalized_text": post.text_clean,
        "is_rtl": post.text_rtl,
        "has_media": post.has_media,
        "is_forward": post.is_forward,
        "forwarded_from": post.forwarded_from,
        "reaction_total": post.reaction_total,
        "links": post.links,
        "hashtags": post.hashtags,
        "watch_list_match": watch_match,
        "content_hash": hashlib.sha256(post.text_clean.encode()).hexdigest()[:16],
    }


def find_channel_meta(channel_id: int, channel_name: str, registry: dict) -> dict:
    """Look up channel metadata from the channel registry."""
    for category in registry.get("categories", []):
        for ch in category.get("channels", []):
            # Match by channel_id if available in registry, else by name
            if ch.get("channel_id") == channel_id:
                return {
                    "source_tier": category.get("source_tier", 4),
                    "faction": category.get("faction", "unknown"),
                    "monitoring_priority": category.get("monitoring_priority", "medium"),
                    "handle": ch.get("handle", ""),
                }
            if ch.get("name_en", "").lower() in channel_name.lower():
                return {
                    "source_tier": category.get("source_tier", 4),
                    "faction": category.get("faction", "unknown"),
                    "monitoring_priority": category.get("monitoring_priority", "medium"),
                    "handle": ch.get("handle", ""),
                }
    # Not found — return defaults
    return {"source_tier": 4, "faction": "unknown", "monitoring_priority": "low", "handle": ""}


def main() -> None:
    """Convert a Telegram export to SP source_bundle YAML."""
    parser = argparse.ArgumentParser(description="Convert Telegram export to SP source_bundle")
    parser.add_argument("--export", required=True, help="Telegram JSON export file")
    parser.add_argument(
        "--registry",
        default="pipeline/config/itp_telegram_channels.yaml",
        help="Channel registry YAML",
    )
    parser.add_argument(
        "--watch-list",
        default="pipeline/config/itp_watch_list.yaml",
        help="WT watch list YAML for keyword pre-filter",
    )
    parser.add_argument(
        "--output", help="Output path (default: pipeline/exports/source_bundle_DATE.yaml)"
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Include all messages regardless of watch list match",
    )
    parser.add_argument(
        "--min-tier",
        type=int,
        default=1,
        help="Minimum source_tier to include (1=all, 3=independent+, 5=noise only)",
    )
    args = parser.parse_args()

    export_path = Path(args.export)
    if not export_path.exists():
        print(f"ERROR: Export file not found: {export_path}")
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        date_str = datetime.now(UTC).date().isoformat()
        output_path = Path(f"pipeline/exports/source_bundle_{date_str}.yaml")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load registry and watch list
    registry = {}
    if Path(args.registry).exists():
        registry = load_yaml(Path(args.registry))
    else:
        print(f"[WARN] Registry not found: {args.registry} — using defaults")

    keywords: set[str] = set()
    if not args.no_filter:
        if Path(args.watch_list).exists():
            watch_list = load_yaml(Path(args.watch_list))
            keywords = build_watch_keywords(watch_list)
            print(f"Watch list loaded: {len(keywords)} keywords")
        else:
            print(f"[WARN] Watch list not found: {args.watch_list} — disabling filter")
            args.no_filter = True

    # Import TelegramIngestor from Loom
    try:
        from heddle.contrib.rag.ingestion.telegram_ingestor import TelegramIngestor
    except ImportError:
        print("ERROR: heddle package not installed. Run: pip install -e /path/to/heddle-ai[rag]")
        sys.exit(1)

    print(f"Loading {export_path}...")
    ingestor = TelegramIngestor(
        source_path=export_path,
        skip_empty=True,
        skip_media_only=False,
        min_text_len=30,
    )
    ingestor.load()
    print(f"Channel: {ingestor.channel_name} (id={ingestor.channel_id})")

    # Get channel metadata
    channel_meta = find_channel_meta(
        ingestor.channel_id or 0,
        ingestor.channel_name or "",
        registry,
    )
    print(f"Channel meta: tier={channel_meta['source_tier']}, faction={channel_meta['faction']}")

    # Filter by min_tier
    if channel_meta["source_tier"] > args.min_tier:
        tier = channel_meta["source_tier"]
        print(f"Channel source_tier={tier} > min_tier={args.min_tier} -- skipping")
        sys.exit(0)

    # Process messages
    source_items = []
    stats = {"total": 0, "watch_match": 0, "no_match": 0, "included": 0}

    for post in ingestor.ingest():
        stats["total"] += 1
        watch_match = args.no_filter or message_matches_keywords(post.text_clean, keywords)

        if watch_match:
            stats["watch_match"] += 1
        else:
            stats["no_match"] += 1

        if args.no_filter or watch_match:
            entry = build_source_entry(post, channel_meta, watch_match)
            source_items.append(entry)
            stats["included"] += 1

    # Sort chronologically
    source_items.sort(key=lambda x: x["timestamp"])

    # Build SP source_bundle output
    source_bundle = {
        "type": "source_bundle",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_file": str(export_path),
        "channel_id": ingestor.channel_id,
        "channel_name": ingestor.channel_name,
        "source_tier": channel_meta["source_tier"],
        "faction_tag": channel_meta["faction"],
        "stats": stats,
        "items": source_items,
    }

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(source_bundle, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print("\nConversion complete:")
    print(f"  Total messages processed: {stats['total']}")
    print(f"  Watch list matches:        {stats['watch_match']}")
    print(f"  No match (excluded):       {stats['no_match']}")
    print(f"  Items in bundle:           {stats['included']}")
    print(f"  Output: {output_path}")


if __name__ == "__main__":
    main()
