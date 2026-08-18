"""
ITP S29 Batch Sweep Runner
==========================

Executes the queries defined in `s29_sweep_plan.md` against the running
ITP Telegram MCP server at http://127.0.0.1:8765/mcp/ and writes a single
structured markdown report to baseline/staging/session_29/.

Usage::

    cd /Volumes/Data/Developer/IranTransitionProject
    uv run python baft/scripts/s29_sweep_runner.py

Designed to be:
- Idempotent (each run produces a timestamped output file, never overwrites)
- Fault-tolerant (per-query try/except — one bad query doesn't kill the batch)
- Observable (prints 1-line progress per query)
- Self-contained (no external state beyond the MCP server)

Requires:
- ITP Telegram daemon running (PID file at ~/.heddle/itp_telegram.pid)
- LM Studio with gemma-4-26b-a4b loaded (for corroboration_check queries)
- fastmcp installed (already in baft venv)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from fastmcp import Client
except ImportError:
    print("ERROR: fastmcp not installed. Run from baft venv: uv run python ...")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MCP_URL = "http://127.0.0.1:8765/mcp/"
OUTPUT_DIR = Path(
    "/Volumes/Data/Developer/IranTransitionProject/baseline/staging/session_29"
)
PER_QUERY_TIMEOUT_SEC = 60  # corroboration_check can be slow

# ---------------------------------------------------------------------------
# Query definitions — mirror the structure in s29_sweep_plan.md
# ---------------------------------------------------------------------------

GROUP_A_SANITY: list[dict[str, Any]] = [
    {"id": "A1", "tool": "stats", "args": {}, "label": "Vector store statistics"},
    {"id": "A2", "tool": "list_channels", "args": {},
     "label": "All channels with bias + trust_weight"},
    {"id": "A3", "tool": "capture_status", "args": {}, "label": "Live capture counters"},
]

GROUP_B_NARRATIVE: list[dict[str, Any]] = [
    {"id": "B1", "label": "Hormuz blockade narrative",
     "queries": ["تنگه هرمز محاصره", "Hormuz blockade strait closure"]},
    {"id": "B2", "label": "Islamabad talks framing",
     "queries": ["مذاکرات اسلام‌آباد ویتکاف", "Islamabad talks Vance Witkoff"]},
    {"id": "B3", "label": "Vahidi / IRGC decision authority",
     "queries": ["وحیدی سپاه تصمیم نظامی", "Vahidi IRGC decision military political"]},
    {"id": "B4", "label": "Mojtaba Khamenei leadership",
     "queries": ["مجتبی خامنه‌ای رهبری", "Mojtaba Khamenei Supreme Leader successor"]},
    {"id": "B5", "label": "Pezeshkian government authority",
     "queries": ["پزشکیان دولت اختیار", "Pezeshkian government cabinet authority"]},
    {"id": "B6", "label": "Ceasefire extension framing",
     "queries": ["آتش بس تمدید نامحدود", "ceasefire indefinite extension"]},
    {"id": "B7", "label": "Nuclear enrichment red line",
     "queries": ["غنی‌سازی هسته‌ای پذیرش", "nuclear enrichment acceptance red line"]},
    {"id": "B8", "label": "Naval kinetic / ship seizures",
     "queries": ["کشتی‌های آمریکایی نفت‌کش توقیف", "American ships oil tanker seizure"]},
    {"id": "B9", "label": "Pay-system stress",
     "queries": ["حقوق نظامیان پلیس", "military police salaries unpaid"]},
    {"id": "B10", "label": "Eschatological / jihad framing",
     "queries": ["جهاد شهادت پایداری", "jihad martyrdom resistance"]},
]

GROUP_C_CORROBORATION: list[dict[str, Any]] = [
    {"id": "C1",
     "claim": "ایران در برابر فشار غرب تسلیم نخواهد شد",
     "label": "Unified-revolutionary-message probe"},
    {"id": "C2",
     "claim": "The IRGC is making decisions on military and political matters",
     "label": "Vahidi-era authority probe"},
    {"id": "C3",
     "claim": "America cannot be trusted in negotiations",
     "label": "Anti-America framing — universal or factional?"},
]

GROUP_D_RECENT: list[dict[str, Any]] = [
    {"id": "D1", "hours_back": 6, "label": "Last 6h dominant topics"},
    {"id": "D2", "hours_back": 24, "label": "Last 24h broader trends"},
]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def fmt_section_header(group: str, qid: str, label: str, tool: str, args: dict) -> str:
    """Render a query header in markdown."""
    args_str = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
    return (
        f"\n### {qid}: {label}\n\n"
        f"- **Tool:** `{tool}`\n"
        f"- **Args:** `{args_str}`\n"
    )


def fmt_search_results(payload: dict, top_n: int = 5) -> str:
    """Render a search_posts or recent_posts result as markdown."""
    if not isinstance(payload, dict):
        return f"\n```\n{payload!r}\n```\n"

    count = payload.get("count", 0)
    results = payload.get("results", [])

    if count == 0:
        return "\n_No results._\n"

    # Per-result formatting
    chunks = [f"\n**Returned:** {count} result(s) (showing top {min(top_n, count)})\n"]

    # Channel/bias coverage summary
    bias_counts: dict[str, int] = {}
    for r in results:
        bias = r.get("channel_bias") or "unknown"
        bias_counts[bias] = bias_counts.get(bias, 0) + 1
    if bias_counts:
        bias_summary = ", ".join(
            f"{b}={n}" for b, n in sorted(bias_counts.items(), key=lambda x: -x[1])
        )
        chunks.append(f"\n**Bias distribution:** {bias_summary}\n")

    # Top results
    chunks.append("\n| # | Score | Channel | Bias | Trust | Text (truncated) |\n")
    chunks.append("|---|---|---|---|---|---|\n")
    for i, r in enumerate(results[:top_n], 1):
        score = r.get("score", "?")
        chan = r.get("channel_name") or r.get("channel_handle") or str(r.get("channel_id", ""))
        bias = r.get("channel_bias") or "?"
        trust = r.get("channel_trust", "?")
        text = (r.get("text") or "").replace("\n", " ").replace("|", "\\|")
        if len(text) > 200:
            text = text[:200] + "..."
        chunks.append(f"| {i} | {score} | {chan} | {bias} | {trust} | {text} |\n")

    return "".join(chunks)


def fmt_corroboration_results(payload: dict) -> str:
    """Render a corroboration_check result as markdown."""
    if not isinstance(payload, dict):
        return f"\n```\n{payload!r}\n```\n"

    if "error" in payload:
        return f"\n_Error: {payload['error']}_\n"

    matches = payload.get("matches", [])
    analyzed = payload.get("analyzed_posts", "?")

    if not matches:
        return f"\n_Analyzed {analyzed} posts; no cross-channel clusters detected._\n"

    chunks = [f"\n**Analyzed posts:** {analyzed}\n",
              f"\n**Matches:** {len(matches)}\n\n"]
    for i, m in enumerate(matches[:5], 1):
        claim = m.get("claim") or m.get("topic") or "?"
        channels = m.get("channels") or m.get("supporting_channels") or []
        confidence = m.get("confidence") or m.get("trust_score") or "?"
        chunks.append(f"\n**Cluster {i}** (confidence={confidence}):\n")
        chunks.append(f"- Claim/topic: {claim}\n")
        chunks.append(f"- Channels: {', '.join(str(c) for c in channels)}\n")
    return "".join(chunks)


def fmt_generic_payload(payload: Any, max_chars: int = 4000) -> str:
    """Render any other payload — stats, list_channels, capture_status — as JSON."""
    try:
        s = json.dumps(payload, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        s = repr(payload)
    if len(s) > max_chars:
        s = s[:max_chars] + "\n... (truncated)"
    return f"\n```json\n{s}\n```\n"


def fmt_error(exc: Exception, latency_ms: int) -> str:
    return (
        f"\n**ERROR after {latency_ms}ms:** `{type(exc).__name__}`\n\n"
        f"```\n{exc}\n```\n"
    )


# ---------------------------------------------------------------------------
# Tool call wrapper
# ---------------------------------------------------------------------------


async def call_tool(
    client: Client,
    tool: str,
    args: dict,
    progress_label: str,
) -> tuple[Any | None, Exception | None, int]:
    """Invoke an MCP tool with timing + error capture. Returns (payload, error, ms)."""
    print(f"  → {progress_label}", end=" ... ", flush=True)
    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(
            client.call_tool(tool, args),
            timeout=PER_QUERY_TIMEOUT_SEC,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        # FastMCP Client returns a CallToolResult; the actual payload is in .data
        # or .structured_content depending on version. Try both.
        payload = None
        if hasattr(result, "structured_content") and result.structured_content:
            payload = result.structured_content
        elif hasattr(result, "data"):
            payload = result.data
        elif hasattr(result, "content") and result.content:
            # content is a list of content blocks; try to extract text + parse JSON
            for block in result.content:
                if hasattr(block, "text"):
                    try:
                        payload = json.loads(block.text)
                        break
                    except (json.JSONDecodeError, TypeError):
                        payload = block.text
                        break
        if payload is None:
            payload = {"_raw_result": str(result)}
        print(f"OK ({latency_ms}ms)")
        return payload, None, latency_ms
    except asyncio.TimeoutError:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        print(f"TIMEOUT ({latency_ms}ms)")
        return None, TimeoutError(f"Exceeded {PER_QUERY_TIMEOUT_SEC}s"), latency_ms
    except Exception as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        print(f"ERROR ({latency_ms}ms): {type(exc).__name__}")
        return None, exc, latency_ms


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


async def run_sweep() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_path = OUTPUT_DIR / f"sweep_results_{timestamp}.md"

    sections: list[str] = []
    summary_rows: list[dict[str, Any]] = []
    overall_t0 = time.perf_counter()

    sections.append(
        f"# ITP S29 — Batch Sweep #1 Results\n\n"
        f"**Generated:** {datetime.now(timezone.utc).isoformat(timespec='seconds')} UTC\n"
        f"**MCP endpoint:** {MCP_URL}\n"
        f"**Plan reference:** s29_sweep_plan.md\n\n"
        "_Detailed results below; see summary table at the end._\n"
    )

    print(f"\n→ Connecting to {MCP_URL}")
    print(f"→ Output: {out_path}\n")

    async with Client(MCP_URL) as client:
        # ---- Group A: Sanity checks ----
        sections.append("\n## Group A — Sanity checks\n")
        for q in GROUP_A_SANITY:
            sections.append(fmt_section_header("A", q["id"], q["label"], q["tool"], q["args"]))
            payload, err, ms = await call_tool(
                client, q["tool"], q["args"], f"{q['id']} {q['label']}"
            )
            if err:
                sections.append(fmt_error(err, ms))
                summary_rows.append({"id": q["id"], "ms": ms, "ok": False, "note": str(err)})
            else:
                sections.append(f"\n_Latency: {ms}ms_\n")
                sections.append(fmt_generic_payload(payload))
                summary_rows.append({"id": q["id"], "ms": ms, "ok": True, "note": ""})

        # ---- Group B: Narrative search ----
        sections.append("\n## Group B — Current narrative state (search_posts)\n")
        for q in GROUP_B_NARRATIVE:
            for j, query in enumerate(q["queries"]):
                qid = f"{q['id']}.{j+1}"
                args = {"query": query, "limit": 10, "min_score": 0.3}
                sections.append(
                    fmt_section_header(
                        "B", qid, f"{q['label']} ({'fa' if j == 0 else 'en'})",
                        "search_posts", args,
                    )
                )
                payload, err, ms = await call_tool(
                    client, "search_posts", args, f"{qid} {query[:40]}"
                )
                if err:
                    sections.append(fmt_error(err, ms))
                    summary_rows.append({"id": qid, "ms": ms, "ok": False, "note": str(err)})
                else:
                    sections.append(f"\n_Latency: {ms}ms_\n")
                    sections.append(fmt_search_results(payload))
                    count = (payload or {}).get("count", 0) if isinstance(payload, dict) else 0
                    summary_rows.append({
                        "id": qid, "ms": ms, "ok": True,
                        "note": f"{count} hit(s)",
                    })
                    sections.append(
                        f"\n<details><summary>Raw JSON</summary>\n\n"
                        f"```json\n{json.dumps(payload, indent=2, ensure_ascii=False)[:8000]}\n```\n\n"
                        f"</details>\n"
                    )

        # ---- Group C: Corroboration ----
        sections.append("\n## Group C — Narrative-cluster detection (corroboration_check)\n")
        for q in GROUP_C_CORROBORATION:
            args = {"claim": q["claim"], "hours_back": 24, "min_score": 0.4}
            sections.append(
                fmt_section_header("C", q["id"], q["label"], "corroboration_check", args)
            )
            payload, err, ms = await call_tool(
                client, "corroboration_check", args, f"{q['id']} {q['label']}"
            )
            if err:
                sections.append(fmt_error(err, ms))
                summary_rows.append({"id": q["id"], "ms": ms, "ok": False, "note": str(err)})
            else:
                sections.append(f"\n_Latency: {ms}ms_\n")
                sections.append(fmt_corroboration_results(payload))
                n_matches = len((payload or {}).get("matches", [])) if isinstance(payload, dict) else 0
                summary_rows.append({
                    "id": q["id"], "ms": ms, "ok": True,
                    "note": f"{n_matches} cluster(s)",
                })
                sections.append(
                    f"\n<details><summary>Raw JSON</summary>\n\n"
                    f"```json\n{json.dumps(payload, indent=2, ensure_ascii=False)[:8000]}\n```\n\n"
                    f"</details>\n"
                )

        # ---- Group D: Recent windows ----
        sections.append("\n## Group D — Time-window snapshots (recent_posts)\n")
        for q in GROUP_D_RECENT:
            args = {"hours_back": q["hours_back"], "limit": 30}
            sections.append(
                fmt_section_header("D", q["id"], q["label"], "recent_posts", args)
            )
            payload, err, ms = await call_tool(
                client, "recent_posts", args, f"{q['id']} {q['label']}"
            )
            if err:
                sections.append(fmt_error(err, ms))
                summary_rows.append({"id": q["id"], "ms": ms, "ok": False, "note": str(err)})
            else:
                sections.append(f"\n_Latency: {ms}ms_\n")
                sections.append(fmt_search_results(payload, top_n=10))
                count = (payload or {}).get("count", 0) if isinstance(payload, dict) else 0
                summary_rows.append({
                    "id": q["id"], "ms": ms, "ok": True,
                    "note": f"{count} post(s)",
                })

    overall_ms = int((time.perf_counter() - overall_t0) * 1000)

    # ---- Summary table at the end ----
    summary_lines = [
        "\n---\n\n## Summary\n\n",
        f"**Total runtime:** {overall_ms / 1000:.1f}s\n\n",
        "| Query | Latency | Status | Notes |\n",
        "|---|---|---|---|\n",
    ]
    for row in summary_rows:
        status = "✓" if row["ok"] else "✗"
        summary_lines.append(
            f"| {row['id']} | {row['ms']}ms | {status} | {row['note']} |\n"
        )

    out_path.write_text("".join(sections + summary_lines), encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    print("ITP S29 Batch Sweep Runner")
    print("=" * 50)
    try:
        out_path = asyncio.run(run_sweep())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as exc:
        print(f"\nFATAL: {type(exc).__name__}: {exc}")
        return 1

    print(f"\n✓ Sweep complete. Results: {out_path}")
    print(f"  Size: {out_path.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
