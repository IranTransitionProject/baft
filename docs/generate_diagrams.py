#!/usr/bin/env python3
"""Generate architecture and workflow SVG diagrams for Baft documentation.

Run:  python docs/generate_diagrams.py
Output: docs/images/*.svg
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).parent / "images"
OUT.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# SVG helpers (same minimal builder as heddle)
# ---------------------------------------------------------------------------

class SVG:
    def __init__(self, w: int, h: int, *, bg: str = "#fafafb"):
        self.w, self.h = w, h
        self.defs: list[str] = []
        self.body: list[str] = []
        self._id = 0
        self.body.append(f'<rect width="{w}" height="{h}" rx="12" fill="{bg}"/>')

    def rect(self, x, y, w, h, *, fill="#555", rx=8, stroke=None, sw=1, opacity=1):
        s = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"'
        if stroke:
            s += f' stroke="{stroke}" stroke-width="{sw}"'
        if opacity < 1:
            s += f' opacity="{opacity}"'
        s += "/>"
        self.body.append(s)

    def text(self, x, y, txt, *, size=14, weight=600, fill="#fff", anchor="middle", baseline="central", family="Inter, system-ui, sans-serif"):
        esc = txt.replace("&", "&amp;").replace("<", "&lt;")
        self.body.append(
            f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
            f'dominant-baseline="{baseline}">{esc}</text>'
        )

    def mtext(self, x, y, lines: list[str], *, size=10, weight=400, fill="#666", anchor="start", lh=1.4):
        self.body.append(f'<text x="{x}" y="{y}" font-family="Inter, system-ui, sans-serif" font-size="{size}" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">')
        for i, line in enumerate(lines):
            dy = 0 if i == 0 else size * lh
            esc = line.replace("&", "&amp;").replace("<", "&lt;")
            self.body.append(f'  <tspan x="{x}" dy="{dy}">{esc}</tspan>')
        self.body.append("</text>")

    def line(self, x1, y1, x2, y2, *, color="#999", sw=2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.body.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"{d}/>')

    def arrow(self, x1, y1, x2, y2, *, color="#888", sw=2):
        mid = f"arrow_{self._next_id()}"
        self.defs.append(f'<marker id="{mid}" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 3 L 0 6 z" fill="{color}"/></marker>')
        self.body.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}" marker-end="url(#{mid})"/>')

    def circle(self, cx, cy, r, *, fill="#555"):
        self.body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>')

    def _next_id(self):
        self._id += 1
        return self._id

    def box_label(self, x, y, w, h, label, *, fill="#555", text_color="#fff", fs=14, rx=8):
        self.rect(x, y, w, h, fill=fill, rx=rx)
        self.text(x + w / 2, y + h / 2, label, size=fs, fill=text_color)

    def layer_bg(self, x, y, w, h, fill, label):
        self.rect(x, y, w, h, fill=fill, rx=10)
        self.text(x + 14, y + 14, label, size=11, weight=500, fill="#888", anchor="start", baseline="hanging")

    def step_badge(self, x, y, num, color):
        self.circle(x + 16, y + 16, 16, fill=color)
        self.text(x + 16, y + 16, str(num), size=14, weight=700, fill="#fff")

    def note_box(self, x, y, w, h, text_str, *, bg="#f4f0ff", border="#d4c8ee", text_color="#6b50a0"):
        self.rect(x, y, w, h, fill=bg, rx=4, stroke=border, sw=1)
        self.text(x + w / 2, y + h / 2, text_str, size=9, weight=400, fill=text_color)

    def render(self) -> str:
        defs = "\n".join(self.defs)
        body = "\n".join(self.body)
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}">\n'
            f'<defs>{defs}</defs>\n'
            f'{body}\n'
            f'</svg>'
        )

    def save(self, path: Path):
        path.write_text(self.render(), encoding="utf-8")
        print(f"  wrote {path}  ({self.w}x{self.h})")


# ===========================================================================
# Color palette — baft uses warmer tones to distinguish from heddle's blue theme
# ===========================================================================

# Worker role colors
SP = "#d97520"  # source processor — orange
IA = "#b5332e"  # intelligence analyst — red
DE = "#6b7280"  # database engineer — gray
XV = "#4278d9"  # cross-validator — blue
IN = "#2e9e57"  # input node — green
TN = "#8b5cf6"  # terminology neutralizer — violet
LA = "#0891b2"  # logic auditor — cyan
PA = "#0891b2"  # perspective auditor — cyan
RT = "#dc2626"  # red teamer — bold red
AS = "#7c3aed"  # audit synthesizer — purple
SA = "#059669"  # session advisor — emerald
WT = "#d97706"  # watch tower — amber
NI = "#ca8a04"  # narrative intelligence — yellow

BLIND = "#0891b2"   # all blind workers share a cyan tone
SIGHTED = "#d97520"  # sighted workers — warm
SCHED = "#d97706"    # scheduled — amber
TITLE = "#1e1e26"
SUB = "#888"
W = "#fff"
BG = "#fafafb"


# ===========================================================================
# Diagram 1: Three-Repo Architecture
# ===========================================================================

def three_repo_architecture():
    s = SVG(1200, 550)

    s.text(40, 38, "Baft — System Architecture", size=26, weight=700, fill=TITLE, anchor="start")
    s.text(40, 62, "Three-repo design: baseline (data)  +  heddle (runtime)  +  baft (application)", size=12, weight=400, fill=SUB, anchor="start")

    # --- Three repos ---
    # Framework
    s.rect(40, 100, 320, 300, fill="#fef3c7", rx=12, stroke="#f59e0b", sw=2)
    s.text(200, 125, "baseline/", size=18, weight=700, fill="#92400e")
    s.text(200, 148, "ITP Analytical Database", size=11, weight=400, fill="#b45309")
    s.mtext(60, 175, [
        "YAML source of truth",
        "",
        "Entities, observations, scenarios",
        "Intelligence briefs",
        "Analytical schemas",
        "Constitution / epistemic rules",
        "",
        "Git-versioned, human-readable",
        "No code — data only",
    ], size=11, fill="#92400e", lh=1.5)

    # Loom
    s.rect(430, 100, 320, 300, fill="#dbeafe", rx=12, stroke="#3b82f6", sw=2)
    s.text(590, 125, "heddle/", size=18, weight=700, fill="#1e40af")
    s.text(590, 148, "Orchestration Framework", size=11, weight=400, fill="#2563eb")
    s.mtext(450, 175, [
        "Actor-based runtime",
        "",
        "Worker execution engine",
        "Pipeline orchestrator",
        "NATS message bus",
        "MCP gateway (FastMCP 3.x)",
        "Workshop web UI",
        "OpenTelemetry tracing",
        "CLI + TUI dashboard",
    ], size=11, fill="#1e40af", lh=1.5)

    # Baft
    s.rect(820, 100, 340, 300, fill="#fce7f3", rx=12, stroke="#ec4899", sw=2)
    s.text(990, 125, "baft/", size=18, weight=700, fill="#9d174d")
    s.text(990, 148, "ITP Application Layer", size=11, weight=400, fill="#be185d")
    s.mtext(840, 175, [
        "13 worker YAML configs",
        "",
        "3 pipeline orchestrators",
        "5 scheduled actors",
        "Knowledge silo mappings",
        "Pydantic I/O contracts",
        "Session CLI + automation",
        "Helm chart (24 deployments)",
        "Pipeline config data files",
    ], size=11, fill="#9d174d", lh=1.5)

    # Arrows: baft → heddle (depends on)
    s.arrow(820, 250, 750, 250, color="#ec4899", sw=2)
    s.text(785, 240, "depends on", size=9, weight=500, fill="#be185d")

    # Arrows: baft → baseline (reads data from)
    s.arrow(820, 290, 360, 290, color="#f59e0b", sw=2)
    s.text(590, 280, "reads data from", size=9, weight=500, fill="#b45309")

    # Bottom: deployment targets
    s.rect(40, 430, 1120, 80, fill="#f1f5f9", rx=10)
    s.text(600, 452, "DEPLOYMENT", size=12, weight=700, fill="#64748b")
    targets = ["Docker Compose", "Kubernetes (Helm)", "Local + NATS", "Workshop UI", "MCP Server"]
    for i, t in enumerate(targets):
        s.box_label(60 + i * 218, 460, 198, 35, t, fill="#64748b", fs=11)

    s.save(OUT / "three-repo-architecture.svg")


# ===========================================================================
# Diagram 2: Worker Map — 13 workers with roles and tiers
# ===========================================================================

def worker_map():
    s = SVG(1200, 750)

    s.text(40, 38, "Baft — Worker Map", size=26, weight=700, fill=TITLE, anchor="start")
    s.text(40, 62, "13 ITP workers organized by pipeline tier and analytical role", size=12, weight=400, fill=SUB, anchor="start")

    # --- Tier 2: Standard Pipeline ---
    s.layer_bg(30, 95, 1140, 145, "#fff7ed", "TIER 2 — STANDARD PIPELINE  (SP -> IA -> XV -> DE)")

    workers_t2 = [
        ("SP", "Source\nProcessor", SP, "local"),
        ("IA", "Intelligence\nAnalyst", IA, "frontier"),
        ("XV", "Cross\nValidator", XV, "local"),
        ("DE", "Database\nEngineer", DE, "local"),
    ]
    for i, (code, name, color, tier) in enumerate(workers_t2):
        bx = 60 + i * 275
        s.rect(bx, 125, 235, 85, fill=color, rx=10)
        s.text(bx + 40, 155, code, size=22, weight=700, fill=W, anchor="start")
        s.text(bx + 40, 180, name.split("\n")[0], size=11, weight=500, fill="#ffffffcc", anchor="start")
        if "\n" in name:
            s.text(bx + 40, 194, name.split("\n")[1], size=11, weight=500, fill="#ffffffcc", anchor="start")
        # Tier badge
        tier_colors = {"local": "#34d399", "standard": "#60a5fa", "frontier": "#f87171"}
        s.rect(bx + 165, 130, 60, 20, fill=tier_colors[tier], rx=10)
        s.text(bx + 195, 140, tier, size=9, weight=600, fill=W)
        # Arrow
        if i < len(workers_t2) - 1:
            s.arrow(bx + 235, 167, bx + 275, 167, color="#d97520", sw=2)

    # --- Tier 3: Audit Pipeline ---
    s.layer_bg(30, 270, 1140, 160, "#f5f3ff", "TIER 3 — AUDIT PIPELINE  (TN -> [LA + PA + RT parallel] -> AS)")

    # TN
    s.rect(60, 305, 160, 85, fill=TN, rx=10)
    s.text(100, 335, "TN", size=22, weight=700, fill=W, anchor="start")
    s.text(100, 358, "Terminology", size=11, weight=500, fill="#ffffffcc", anchor="start")
    s.text(100, 372, "Neutralizer", size=11, weight=500, fill="#ffffffcc", anchor="start")
    s.rect(170, 310, 40, 20, fill="#34d399", rx=10)
    s.text(190, 320, "local", size=9, weight=600, fill=W)

    s.arrow(220, 347, 280, 347, color="#8b5cf6", sw=2)

    # Parallel group — LA, PA, RT
    s.rect(280, 295, 510, 105, fill="#ede9fe", rx=8, stroke="#c4b5fd", sw=1)
    s.text(535, 305, "PARALLEL", size=9, weight=700, fill="#7c3aed")

    blind_workers = [
        ("LA", "Logic\nAuditor", BLIND, "standard", 300),
        ("PA", "Perspective\nAuditor", BLIND, "standard", 470),
        ("RT", "Red\nTeamer", RT, "frontier", 640),
    ]
    for code, name, color, tier, bx in blind_workers:
        s.rect(bx, 318, 145, 70, fill=color, rx=8)
        s.text(bx + 35, 342, code, size=18, weight=700, fill=W, anchor="start")
        s.text(bx + 35, 362, name.split("\n")[0], size=10, weight=500, fill="#ffffffcc", anchor="start")
        if "\n" in name:
            s.text(bx + 35, 374, name.split("\n")[1], size=10, weight=500, fill="#ffffffcc", anchor="start")
        tier_colors = {"standard": "#60a5fa", "frontier": "#f87171"}
        s.rect(bx + 90, 322, 48, 18, fill=tier_colors[tier], rx=9)
        s.text(bx + 114, 331, tier, size=8, weight=600, fill=W)

    s.note_box(300, 392, 160, 20, "BLIND — no framework data", bg="#fef2f2", border="#fca5a5", text_color="#dc2626")

    s.arrow(790, 347, 840, 347, color="#8b5cf6", sw=2)

    # AS
    s.rect(840, 305, 160, 85, fill=AS, rx=10)
    s.text(880, 335, "AS", size=22, weight=700, fill=W, anchor="start")
    s.text(880, 358, "Audit", size=11, weight=500, fill="#ffffffcc", anchor="start")
    s.text(880, 372, "Synthesizer", size=11, weight=500, fill="#ffffffcc", anchor="start")
    s.rect(950, 310, 40, 20, fill="#60a5fa", rx=10)
    s.text(970, 320, "std", size=9, weight=600, fill=W)

    # --- Tier 1: Quick (Direct Dispatch) ---
    s.layer_bg(30, 460, 540, 115, "#f0fdf4", "TIER 1 — QUICK  (Direct single-worker dispatch)")

    quick_workers = [
        ("IN", "Input\nNode", IN, "local"),
    ]
    s.rect(60, 495, 160, 60, fill=IN, rx=8)
    s.text(100, 518, "IN", size=18, weight=700, fill=W, anchor="start")
    s.text(100, 537, "Input Node", size=10, weight=500, fill="#ffffffcc", anchor="start")
    s.rect(170, 498, 40, 18, fill="#34d399", rx=9)
    s.text(190, 507, "local", size=8, weight=600, fill=W)

    s.text(260, 518, "Also via Tier 1:", size=10, weight=500, fill="#666", anchor="start")
    s.text(260, 536, "DE (validate_only), XV (quick check)", size=10, weight=400, fill="#999", anchor="start")

    # --- Scheduled / Background Workers ---
    s.layer_bg(600, 460, 570, 115, "#fffbeb", "SCHEDULED / BACKGROUND WORKERS")

    sched_workers = [
        ("SA", "Session\nAdvisor", SA, "local", "every 15min"),
        ("WT", "Watch\nTower", WT, "standard", "daily"),
        ("NI", "Narrative\nIntel", NI, "standard", "daily"),
    ]
    for i, (code, name, color, tier, freq) in enumerate(sched_workers):
        bx = 620 + i * 175
        s.rect(bx, 495, 155, 60, fill=color, rx=8)
        s.text(bx + 30, 518, code, size=18, weight=700, fill=W, anchor="start")
        s.text(bx + 30, 537, name.split("\n")[0], size=10, weight=500, fill="#ffffffcc", anchor="start")
        # Frequency badge
        s.rect(bx + 95, 498, 52, 18, fill="#00000030", rx=9)
        s.text(bx + 121, 507, freq, size=8, weight=500, fill=W)

    # --- Legend ---
    s.text(40, 620, "Model Tiers:", size=11, weight=600, fill="#555", anchor="start")
    for i, (label, color) in enumerate([("local (Ollama)", "#34d399"), ("standard (Sonnet)", "#60a5fa"), ("frontier (Opus)", "#f87171")]):
        lx = 140 + i * 180
        s.circle(lx, 618, 6, fill=color)
        s.text(lx + 12, 620, label, size=10, weight=400, fill="#666", anchor="start")

    s.text(40, 650, "Worker Types:", size=11, weight=600, fill="#555", anchor="start")
    s.text(140, 650, "LLM Workers (SP, IA, XV, IN, TN, LA, PA, RT, AS, SA, WT, NI)  |  Processor Worker: DE (SyncProcessingBackend, DuckDB)", size=10, weight=400, fill="#666", anchor="start")

    s.text(40, 680, "Contracts:", size=11, weight=600, fill="#555", anchor="start")
    s.text(140, 680, "baft.contracts — Pydantic I/O models for all 13 workers (core.py, audit.py, monitor.py)", size=10, weight=400, fill="#666", anchor="start")

    s.save(OUT / "worker-map.svg")


# ===========================================================================
# Diagram 3: Silo Isolation — Knowledge access control
# ===========================================================================

def silo_isolation():
    s = SVG(1200, 800)

    s.text(40, 38, "Baft — Knowledge Silo Isolation", size=26, weight=700, fill=TITLE, anchor="start")
    s.text(40, 62, "Epistemic quarantine: who sees what — the foundation of audit independence", size=12, weight=400, fill=SUB, anchor="start")

    # --- ISOLATED silos (left) ---
    s.layer_bg(30, 95, 360, 260, "#fef2f2", "ISOLATED SILOS  (strict access control)")

    isolated = [
        ("framework_full", "Full ITB + ISA", "#dc2626", ["IA"]),
        ("database_current", "Entity state", "#dc2626", ["IA", "DE"]),
        ("cognitive_profile", "Analyst profile", "#dc2626", ["SA"]),
    ]
    for i, (name, desc, color, workers) in enumerate(isolated):
        sy = 130 + i * 72
        s.rect(50, sy, 210, 55, fill="#fff", rx=6, stroke=color, sw=2)
        s.text(60, sy + 20, name, size=11, weight=700, fill=color, anchor="start")
        s.text(60, sy + 38, desc, size=9, weight=400, fill="#999", anchor="start")
        # Access arrows
        for j, w in enumerate(workers):
            wx = 290 + j * 50
            s.arrow(260, sy + 27, wx, sy + 27, color=color, sw=1.5)
            s.rect(wx, sy + 14, 36, 26, fill=color, rx=4)
            s.text(wx + 18, sy + 27, w, size=10, weight=700, fill=W)

    # RED LINE
    s.rect(30, 365, 1140, 30, fill="#fef2f2", rx=0)
    s.text(600, 380, "RED LINE: framework_full and database_current MUST NEVER reach blind workers (LA, PA, RT, AS) or SA", size=10, weight=700, fill="#dc2626")

    # --- SHARED silos (right, grid) ---
    s.layer_bg(420, 95, 750, 260, "#f0fdf4", "SHARED SILOS")

    shared = [
        ("framework_schemas", "DE, XV"),
        ("entity_id_registry", "XV, SP, DE"),
        ("source_hierarchy", "SP, WT, NI"),
        ("epistemic_rules", "SP, IA"),
        ("entity_name_registry", "SP"),
        ("terminology_registry", "TN only"),
        ("tier_rules", "SA"),
        ("watch_list", "WT"),
        ("constitution", "All workers"),
        ("evaluation_rubric", "LA, PA"),
    ]
    cols = 3
    for i, (name, workers) in enumerate(shared):
        col = i % cols
        row = i // cols
        sx = 440 + col * 240
        sy = 125 + row * 55
        s.rect(sx, sy, 220, 42, fill="#fff", rx=5, stroke="#86efac", sw=1)
        s.text(sx + 10, sy + 16, name, size=10, weight=600, fill="#166534", anchor="start")
        s.text(sx + 10, sy + 32, workers, size=9, weight=400, fill="#999", anchor="start")

    # --- Blind vs Sighted worker groups ---
    y = 420
    s.layer_bg(30, y, 560, 170, "#eff6ff", "SIGHTED WORKERS  (access analytical framework)")
    sighted = [
        ("SP", SP), ("IA", IA), ("XV", XV), ("DE", DE), ("IN", IN),
    ]
    for i, (code, color) in enumerate(sighted):
        s.box_label(55 + i * 105, y + 35, 85, 45, code, fill=color, fs=16)
    s.mtext(55, y + 95, [
        "Can see: framework_full (IA), database_current (IA, DE),",
        "framework_schemas, entity registries, epistemic rules, constitution",
    ], size=9, fill="#1e40af")
    s.note_box(55, y + 135, 280, 22, "SP has no session_id — processes raw source only", bg="#dbeafe", border="#93c5fd", text_color="#1e40af")

    s.layer_bg(620, y, 550, 170, "#faf5ff", "BLIND WORKERS  (no framework data)")
    blind = [
        ("TN", TN), ("LA", LA), ("PA", PA), ("RT", RT), ("AS", AS),
    ]
    for i, (code, color) in enumerate(blind):
        s.box_label(645 + i * 105, y + 35, 85, 45, code, fill=color, fs=16)
    s.mtext(645, y + 95, [
        "Can see: constitution only (+ evaluation_rubric for LA, PA)",
        "TN: terminology_registry only (neutralization firewall)",
    ], size=9, fill="#6b21a8")
    s.note_box(645, y + 135, 280, 22, "TN output is the ONLY input to blind auditors", bg="#f5f3ff", border="#c4b5fd", text_color="#6b21a8")

    # --- Background monitors ---
    s.layer_bg(30, y + 195, 1140, 90, "#fffbeb", "BACKGROUND / SCHEDULED WORKERS")
    monitors = [("SA", SA, "cognitive_profile, tier_rules, constitution"), ("WT", WT, "source_hierarchy, watch_list"), ("NI", NI, "source_hierarchy")]
    for i, (code, color, silos) in enumerate(monitors):
        bx = 55 + i * 380
        s.box_label(bx, y + 225, 60, 40, code, fill=color, fs=16)
        s.text(bx + 75, y + 238, silos, size=9, weight=400, fill="#92400e", anchor="start")
    s.note_box(55, y + 270, 400, 20, "SA is isolated from analytical framework — monitors behavior, not content", bg="#fffbeb", border="#fde68a", text_color="#92400e")

    s.save(OUT / "silo-isolation.svg")


# ===========================================================================
# Diagram 4: Pipeline Data Flow (Tier 2 + Tier 3)
# ===========================================================================

def pipeline_data_flow():
    s = SVG(1200, 900)

    s.text(40, 38, "Baft — Pipeline Data Flow", size=26, weight=700, fill=TITLE, anchor="start")
    s.text(40, 62, "Tier 2 (standard) and Tier 3 (audit) pipeline stages with data schemas", size=12, weight=400, fill=SUB, anchor="start")

    # =========== TIER 2 ===========
    s.layer_bg(30, 95, 1140, 310, "#fff7ed", "TIER 2 — STANDARD PIPELINE")

    # SP
    y = 130
    s.box_label(50, y, 200, 60, "SP — Source Processor", fill=SP, fs=12)
    s.mtext(50, y + 72, ["Input: source_material, source_url, source_type", "Output: claims[], source_tier, epistemic_tags"], size=9, fill="#92400e")

    s.arrow(250, y + 30, 310, y + 30, color=SP, sw=2)
    s.text(280, y + 20, "claims", size=8, weight=500, fill=SP)

    # IA
    s.box_label(320, y, 230, 60, "IA — Intelligence Analyst", fill=IA, fs=12)
    s.mtext(320, y + 72, ["Input: claims, session_id, analyst_guidance", "Output: integration_spec, new_entities,", "         updated_variables, scenarios"], size=9, fill="#991b1b")

    s.arrow(550, y + 30, 610, y + 30, color=IA, sw=2)
    s.text(580, y + 20, "spec", size=8, weight=500, fill=IA)

    # XV
    s.box_label(620, y, 200, 60, "XV — Cross Validator", fill=XV, fs=12)
    s.mtext(620, y + 72, ["Input: integration_spec, entity_ids", "Output: validation_result, issues[]"], size=9, fill="#1e40af")

    s.arrow(820, y + 30, 880, y + 30, color=XV, sw=2)
    s.text(850, y + 20, "valid", size=8, weight=500, fill=XV)

    # DE
    s.box_label(890, y, 230, 60, "DE — Database Engineer", fill=DE, fs=12)
    s.mtext(890, y + 72, ["Input: integration_spec, action, session_id", "Output: changes_applied[], db_state_summary"], size=9, fill="#374151")

    # Session flow annotation
    s.rect(50, y + 120, 1070, 30, fill="#fef3c7", rx=4)
    s.text(585, y + 135, "session_id flows: IA -> XV -> DE  |  SP has no session (raw source processing)  |  DE tracks session_operation_count", size=9, weight=500, fill="#92400e")

    # Retry annotations
    s.mtext(50, y + 165, [
        "Retry policy:  SP max_retries=2 (local, cheap)  |  IA max_retries=1 (frontier, expensive)  |  XV max_retries=2  |  DE max_retries=2",
    ], size=9, fill="#999")

    # =========== TIER 3 ===========
    s.layer_bg(30, 430, 1140, 330, "#f5f3ff", "TIER 3 — AUDIT PIPELINE")

    y = 465
    # TN
    s.box_label(50, y, 200, 60, "TN — Neutralizer", fill=TN, fs=12)
    s.mtext(50, y + 72, ["Input: analytical_text, audit_id", "Output: neutralized_text, term_map"], size=9, fill="#5b21b6")

    s.arrow(250, y + 30, 310, y + 30, color=TN, sw=2)
    s.text(275, y + 20, "neutral", size=8, weight=500, fill=TN)

    # Parallel group
    s.rect(310, y - 10, 550, 165, fill="#ede9fe", rx=10, stroke="#c4b5fd", sw=1)
    s.text(585, y - 2, "PARALLEL GROUP  (asyncio.wait FIRST_COMPLETED)", size=9, weight=700, fill="#7c3aed")

    # LA
    s.box_label(330, y + 15, 155, 55, "LA — Logic Auditor", fill=LA, fs=11)
    s.mtext(330, y + 80, ["reasoning_quality,", "logical_errors[]"], size=8, fill="#155e75")

    # PA
    s.box_label(505, y + 15, 170, 55, "PA — Perspective Auditor", fill=PA, fs=11)
    s.mtext(505, y + 80, ["perspective_gaps[],", "bias_indicators[]"], size=8, fill="#155e75")

    # RT
    s.box_label(695, y + 15, 145, 55, "RT — Red Teamer", fill=RT, fs=11)
    s.mtext(695, y + 80, ["challenges[],", "vulnerability_score"], size=8, fill="#991b1b")

    # Blind badge
    s.note_box(330, y + 110, 230, 24, "ALL BLIND — receive neutralized_text only", bg="#fef2f2", border="#fca5a5", text_color="#dc2626")

    s.arrow(860, y + 42, 900, y + 42, color=AS, sw=2)

    # AS
    s.box_label(910, y, 210, 60, "AS — Audit Synthesizer", fill=AS, fs=12)
    s.mtext(910, y + 72, ["Input: all 3 audit reports + decision_log", "Output: synthesis, consensus_score,", "         recommendations[]"], size=9, fill="#5b21b6")

    # Audit flow annotation
    s.rect(50, y + 160, 1070, 30, fill="#ede9fe", rx=4)
    s.text(585, y + 175, "audit_id (not session_id) — auditors have NO knowledge of which session or analyst produced the work", size=9, weight=500, fill="#5b21b6")

    # Publication gate
    s.rect(50, y + 200, 1070, 45, fill="#fff", rx=6, stroke="#c4b5fd", sw=1)
    s.text(585, y + 215, "PUBLICATION GATE", size=10, weight=700, fill="#7c3aed")
    s.text(585, y + 232, "RT escalation (vulnerability_score >= threshold) blocks publication and requires human review", size=9, weight=400, fill="#666")

    s.save(OUT / "pipeline-data-flow.svg")


# ===========================================================================
# Diagram 5: Session & Analyst Workflow
# ===========================================================================

def analyst_workflow():
    s = SVG(1100, 600)

    s.text(40, 38, "Baft — Analyst Session Workflow", size=26, weight=700, fill=TITLE, anchor="start")
    s.text(40, 62, "Session lifecycle from start to publication via MCP tools and CLI", size=12, weight=400, fill=SUB, anchor="start")

    steps = [
        (100, "#059669", "SESSION START", "baft session start  (pull framework, import DuckDB, register)"),
        (200, SP, "INGEST SOURCE", "SP processes raw Telegram/document → claims with epistemic tags"),
        (300, IA, "ANALYZE", "IA integrates claims into analytical framework (session_id scoped)"),
        (400, XV, "VALIDATE", "XV cross-references entity IDs + integration spec"),
        (500, DE, "PERSIST", "DE writes to DuckDB (serialized, session_operation_count tracked)"),
        (600, AS, "AUDIT", "Tier 3: TN neutralizes → [LA+PA+RT blind review] → AS synthesizes"),
        (700, "#059669", "SESSION END", "baft session end  (commit framework, push, unregister)"),
    ]

    for i, (y, color, title, desc) in enumerate(steps):
        s.step_badge(40, y, i + 1, color)
        s.text(80, y + 10, title, size=14, weight=700, fill=color, anchor="start", baseline="hanging")
        s.text(80, y + 30, desc, size=11, weight=400, fill=SUB, anchor="start", baseline="hanging")

        if i < len(steps) - 1:
            next_y = steps[i + 1][0]
            s.arrow(56, y + 50, 56, next_y - 5, color="#ccc", sw=2)

    # Side panel: concurrent sessions
    s.rect(680, 100, 380, 200, fill="#f0fdf4", rx=10, stroke="#86efac", sw=1)
    s.text(870, 120, "Concurrent Sessions", size=14, weight=700, fill="#166534")
    s.mtext(700, 145, [
        "Multiple analysts can work simultaneously:",
        "",
        "- Pipelines: max_concurrent_goals=4",
        "- SA: expand_from dispatches per active session",
        "- DE: serialize_writes (single writer)",
        "- Session markers: ~/.heddle/sessions/*.json",
        "",
        "Each session_id is isolated — no cross-talk",
    ], size=10, fill="#166534", lh=1.5)

    # Side panel: SA monitoring
    s.rect(680, 330, 380, 130, fill="#fffbeb", rx=10, stroke="#fde68a", sw=1)
    s.text(870, 350, "SA — Continuous Monitoring", size=14, weight=700, fill="#92400e")
    s.mtext(700, 375, [
        "Runs every 15 minutes per active session",
        "",
        "Checks: cognitive load, confirmation bias,",
        "epistemic discipline, analysis quality",
        "",
        "Uses cognitive_profile — NOT framework data",
    ], size=10, fill="#92400e", lh=1.5)

    # Side panel: tools
    s.rect(680, 490, 380, 75, fill="#f1f5f9", rx=10, stroke="#cbd5e1", sw=1)
    s.text(870, 510, "Access Methods", size=14, weight=700, fill="#475569")
    s.mtext(700, 530, [
        "MCP tools (Claude Desktop/Code) | Workshop UI | CLI",
        "heddle ui (TUI dashboard) | Direct NATS submission",
    ], size=10, fill="#475569", lh=1.5)

    s.save(OUT / "analyst-workflow.svg")


# ===========================================================================
# Diagram 6: Deployment Architecture
# ===========================================================================

def deployment_architecture():
    s = SVG(1100, 550)

    s.text(40, 38, "Baft — Deployment Architecture", size=26, weight=700, fill=TITLE, anchor="start")
    s.text(40, 62, "Kubernetes deployment via Helm chart  ·  24 deployments  ·  NATS + DuckDB + Workshop", size=12, weight=400, fill=SUB, anchor="start")

    # Infrastructure layer
    s.layer_bg(30, 95, 1040, 90, "#e0e8ff", "INFRASTRUCTURE")
    infra = [("NATS Server", "#3b82f6"), ("DuckDB (volume)", "#6b7280"), ("Ollama (local)", "#34d399"), ("Jaeger (OTel)", "#8b5cf6")]
    for i, (name, color) in enumerate(infra):
        s.box_label(55 + i * 250, 125, 225, 40, name, fill=color, fs=12)

    # Services layer
    s.layer_bg(30, 210, 1040, 90, "#ddf4de", "SERVICES")
    services = [("Router", "#555c70"), ("Workshop UI", "#d97520"), ("MCP Gateway", "#3b82f6"), ("Scheduler", "#d97706")]
    for i, (name, color) in enumerate(services):
        s.box_label(55 + i * 250, 240, 225, 40, name, fill=color, fs=12)

    # Workers layer
    s.layer_bg(30, 325, 1040, 140, "#fff7ed", "WORKERS  (13 deployments, each scalable via replicas)")

    # Row 1: Tier 2
    t2_workers = ["SP", "IA", "XV", "DE", "IN"]
    for i, w in enumerate(t2_workers):
        s.box_label(55 + i * 200, 355, 80, 35, w, fill=SP if w == "SP" else IA if w == "IA" else XV if w == "XV" else DE if w == "DE" else IN, fs=14)
    s.text(55 + 5 * 200, 372, "Tier 1-2", size=10, weight=500, fill="#999", anchor="start")

    # Row 2: Tier 3 + scheduled
    t3_workers = ["TN", "LA", "PA", "RT", "AS", "SA", "WT", "NI"]
    for i, w in enumerate(t3_workers):
        colors = {"TN": TN, "LA": LA, "PA": PA, "RT": RT, "AS": AS, "SA": SA, "WT": WT, "NI": NI}
        s.box_label(55 + i * 122, 405, 105, 35, w, fill=colors[w], fs=14)

    s.text(55, 452, "Tier 3 (audit) + Scheduled", size=10, weight=500, fill="#999", anchor="start")

    # Scaling note
    s.rect(30, 485, 1040, 40, fill="#f1f5f9", rx=6)
    s.text(550, 505, "Horizontal scaling: kubectl scale deployment/heddle-worker-sp --replicas=N  |  NATS queue groups auto-balance  |  HPA supported", size=10, weight=400, fill="#475569")

    s.save(OUT / "deployment-architecture.svg")


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    print("Generating Baft documentation diagrams...")
    three_repo_architecture()
    worker_map()
    silo_isolation()
    pipeline_data_flow()
    analyst_workflow()
    deployment_architecture()
    print(f"\nDone! {len(list(OUT.glob('*.svg')))} SVGs in {OUT}/")
