#!/usr/bin/env python3
"""
telegram_corpus_interleave.py
------------------------------
Merge multiple Telegram JSON exports into a single chronologically
interleaved timeline for manual narrative intelligence scanning.

Output: one line per message, sorted by timestamp, prefixed with
channel name, faction tag, and source tier.

Usage:
  python telegram_corpus_interleave.py \\
      --exports /path/to/exports/*.json \\
      --registry pipeline/config/itp_telegram_channels.yaml \\
      --hours 24 \\
      --output /tmp/merged_timeline.txt
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Telegram exports into interleaved timeline")
    parser.add_argument("--exports", nargs="+", required=True, help="Telegram JSON export files")
    parser.add_argument("--registry", default="pipeline/config/itp_telegram_channels.yaml")
    parser.add_argument("--hours", type=int, default=24, help="Hours of history to include")
    parser.add_argument("--output", help="Output file (default: stdout)")
    parser.add_argument("--watch-list", help="Highlight messages matching watch keywords")
    args = parser.parse_args()

    try:
        from loom.contrib.rag.ingestion.telegram_ingestor import TelegramIngestor
    except ImportError:
        print("ERROR: loom not installed.")
        sys.exit(1)

    registry = {}
    if Path(args.registry).exists():
        registry = load_yaml(Path(args.registry))

    keywords: set[str] = set()
    if args.watch_list and Path(args.watch_list).exists():
        wl = load_yaml(Path(args.watch_list))
        for item in wl.get("items", []):
            for term in item.get("search_terms", []) + item.get("search_terms_fa", []):
                keywords.add(term.lower())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    all_messages = []
    for export_file in args.exports:
        path = Path(export_file)
        if not path.exists():
            print(f"[WARN] Not found: {path}", file=sys.stderr)
            continue

        ingestor = TelegramIngestor(source_path=path, min_text_len=10)
        ingestor.load()

        # Find channel meta
        faction = "unknown"
        tier = 4
        for category in registry.get("categories", []):
            for ch in category.get("channels", []):
                if ch.get("name_en", "").lower() in (ingestor.channel_name or "").lower():
                    faction = category.get("faction", "unknown")
                    tier = category.get("source_tier", 4)
                    break

        for post in ingestor.ingest():
            ts = post.timestamp
            if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                continue

            match = bool(keywords) and any(kw in post.text_clean.lower() for kw in keywords)
            all_messages.append({
                "timestamp": ts,
                "channel": ingestor.channel_name or path.stem,
                "faction": faction,
                "tier": tier,
                "text": post.text_clean,
                "is_forward": post.is_forward,
                "forwarded_from": post.forwarded_from,
                "watch_match": match,
            })

    all_messages.sort(key=lambda x: x["timestamp"])

    lines = []
    for msg in all_messages:
        ts_str = msg["timestamp"].strftime("%Y-%m-%d %H:%M")
        fwd = f" [FWD:{msg['forwarded_from']}]" if msg["is_forward"] and msg["forwarded_from"] else ""
        match_marker = " *** WATCH MATCH ***" if msg["watch_match"] else ""
        header = f"[{ts_str}] [{msg['channel']} | {msg['faction']} | T{msg['tier']}]{fwd}{match_marker}"
        text = msg["text"].replace("\n", " ").strip()
        lines.append(f"{header}\n{text}\n")

    output = "\n".join(lines)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Timeline written: {args.output} ({len(all_messages)} messages)")
    else:
        print(output)


if __name__ == "__main__":
    main()
