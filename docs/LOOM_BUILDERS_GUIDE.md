# Loom Builder's Guide

**Version:** 0.1 DRAFT
**Date:** 2026-03-15
**Audience:** Anyone extending Loom for a new analytical project, or building a similar multi-agent pipeline from scratch.
**Source project:** ITP (Iran Transition Project) / Baft repository

---

## 1. What Loom Is

Loom is a multi-agent orchestration framework for structured analytical work. It connects specialized LLM workers via a message bus (NATS), routes tasks by complexity tier, enforces knowledge silos for audit independence, and exposes the entire pipeline as MCP tools so a human analyst can interact through a conversational interface (Claude Chat, Claude Code, or any MCP client).

The metaphor: a weaving loom where each thread (worker) has a specific function, isolation boundaries prevent cross-contamination, and the fabric (analytical output) is traceable from raw source to published conclusion.

### Core design principles

**Schema-driven workers.** Every worker is defined by a YAML config with explicit `input_schema`, `output_schema`, `system_prompt`, and `knowledge_sources`. The worker code is generic — it reads the config and calls the model. The analytical intelligence lives in the configs, not the code.

**Silo-enforced independence.** Some workers (LA, PA, RT — the audit pipeline) must be blind to the project's analytical framework. Their `knowledge_sources` are intentionally empty or limited to generic rubrics. TN (Terminology Neutralizer) sits at the firewall, stripping project-specific vocabulary before handoff to blind auditors. This is not a nicety — if auditors can pattern-match to published project content, their independence is fake.

**Tier-based routing.** Workers declare a `default_model_tier` (local/standard/frontier). The router enforces this: mechanical extraction tasks (SP, DE, XV) run on small local models (cheap, fast), analytical work (IA) requires frontier models (expensive, slow), and audit work (LA, PA) runs on standard-tier models from a different provider than IA to ensure training-data independence.

**JSON internal, YAML human-facing.** Worker configs are YAML (human-edited). Worker output is JSON (machine-reliable). Conversion between the two is trivial (`json.loads` / `yaml.dump`) and happens at the build or inspection step, not in the pipeline.

---

## 2. Lessons Learned (the hard way)

### 2.1 The Concrete Example Rule

**Finding:** The single most impactful change to worker reliability was adding a concrete output example to every system_prompt.

DE (Database Engineer) was the only worker with a concrete YAML/JSON example in its prompt. It scored 6/6 on every model tested. SP (Source Processor) described its output structure in 60 lines of prose instructions but never showed the actual structure. It scored 2/7 on every model — including models that aced DE.

**Root cause:** The `output_schema` in the worker config is consumed by the test harness for scoring. It is never injected into the model's context. The model's only guidance is the system_prompt. For models ≤10B parameters, prose descriptions of nested structures are insufficient. They need to see the shape.

**Rule:** Every system_prompt must end with an `## Output format` section containing:

1. "Output ONLY valid JSON matching this exact structure. No preamble, no explanation, no code fences, no markdown."
2. A one-line JSON example showing every required field with realistic placeholder values.
3. The example must use the exact key names from `output_schema`.

**Corollary:** The audition script should also inject the top-level key and required nested keys from `output_schema` into the user message as belt-and-suspenders.

### 2.2 JSON over YAML for model output

**Finding:** YAML is treacherous as a model output format. Problems encountered:

- Indentation sensitivity: a single misaligned space makes the output unparseable.
- Type coercion surprises: bare `yes`/`no` become `true`/`false`; bare numbers lose string type; timestamps without quotes get interpreted as datetime objects.
- Small models frequently mix YAML and prose, or embed YAML inside code fences inconsistently.

**Decision:** JSON is the internal wire format. YAML is the human-inspection view, generated on demand via trivial conversion. Worker configs themselves remain YAML (human-edited, not model-generated).

### 2.3 Prompt length vs. model capability is inversely correlated for schema compliance

SP has the longest system_prompt (~60 lines of extraction instructions) and the worst schema compliance. DE has a shorter, more focused prompt and perfect compliance. This isn't just about the example — it's about cognitive budget. Small models allocate attention to the entire prompt. By the time they reach the output section, the schema details have been displaced from the attention window.

**Rule:** For local-tier workers (≤10B models), keep the system_prompt under 40 lines. Move detailed instructions into the knowledge silo injection rather than the system_prompt. The output format section should be the last thing the model reads.

### 2.4 Audition before you build

**Finding:** Building the full pipeline before testing whether candidate models can even produce compliant output for each role is backwards. The audition script (`audition_models.py`) should be the first thing you build after the worker configs.

**Pattern:**

1. Write worker configs (system_prompt + schemas)
2. Write test payloads for each role
3. Run audition against local models
4. Fix prompts until your known-good model passes all roles
5. Then wire the pipeline

### 2.5 The "no_preamble" problem

Many models prepend conversational text before their structured output ("Here is the result:", "Based on the input..."). This is the most common failure mode after wrong-key failures.

**Mitigation strategies (cumulative):**

- Include "No preamble, no explanation" in the output format instruction.
- Set temperature to 0.1 (not 0.0 — some APIs reject 0.0).
- In the audition harness, strip common preamble patterns before parsing.
- Accept both bare JSON and fenced JSON in the parser (the model might wrap its output in ```json``` fences even when told not to).

### 2.6 Reasoning models are wrong for mechanical workers

deepseek-r1:8b scored 0/6 on DE and 0/7 on SP. It's a reasoning model — it "thinks out loud" before producing output, which means its structured output is buried inside a reasoning trace. These models are designed for complex reasoning tasks, not mechanical extraction or schema-filling.

**Rule:** Never assign a reasoning model (deepseek-r1, phi4-reasoning, etc.) to a local-tier mechanical worker. Reasoning models may be appropriate for IA or RT (analytical/adversarial roles) if the cost is acceptable.

### 2.7 Provider diversity for audit independence

LA, PA, and RT are blind audit workers. If they run on the same model that produced the IA output, they share training-data biases with IA. The architecture doc specifies that RT should use a different LLM provider (e.g., Gemini or GPT-4o) for Tier 4 adversarial runs.

In practice, this means your backend config needs at least two provider slots: one for the analytical pipeline (Anthropic), one for the audit pipeline (OpenAI/Google/other).

---

## 3. Comparison: Loom vs. Pathmode

Pathmode (pathmode.io) is a Finnish SaaS product building an "Intent Layer" for product teams. It's the closest publicly visible system to what Loom does, despite targeting a completely different domain (product development vs. intelligence analysis). The comparison is instructive.

### What they share

| Concept | Pathmode term | Loom term |
|---------|--------------|-----------|
| Structured specs as core artifact | IntentSpec (Markdown + YAML frontmatter) | Worker configs (YAML + JSON schemas) |
| Evidence → structured output pipeline | Collect → Cluster → Synthesize → Ship | SP → IA → TN → LA/PA/RT → AS → DE |
| Traceability from source to output | Friction ID → Intent ID → shipped feature | Source tier → claim_id → entity_id → published brief |
| Machine-readable schema | IntentSpec JSON Schema | output_schema in worker configs |
| Guardrails / constraints | Constitution Rules (non-negotiable constraints injected into every agent prompt) | Standing analytical rules (in IA system_prompt), silo isolation rules, epistemic tags |
| Human review gate | Intent Specs are "compiled, not written" — AI drafts, human reviews | IA produces, TN neutralizes, LA/PA/RT audit blindly, AS synthesizes, human decides |

### Where they diverge

| Dimension | Pathmode | Loom |
|-----------|----------|------|
| **Domain** | Product discovery / software development | Geopolitical intelligence analysis |
| **Input sources** | Support tickets, Intercom, Dovetail, analytics | Telegram channels, regime media, OSINT, multilingual primary sources |
| **Who uses it** | Product managers, developers | Solo analyst + LLM pipeline |
| **Multi-agent?** | Single-agent (one LLM synthesizes) | 13+ specialized agents with silo isolation |
| **Audit independence** | None (same model drafts and reviews) | Enforced via TN terminology neutralization + provider diversity + blind knowledge silos |
| **Output** | IntentSpec pushed to Cursor/Linear/Jira | Analytical observations, variables, briefs pushed to YAML database + Substack |
| **Epistemic discipline** | Confidence score (single number) | Four-level epistemic tags ([Fact]/[Inference]/[Uncertain]/[Speculation]) with source-tier grounding |
| **MCP integration** | MCP server for agent tool use | MCP server for human-analyst tool access to entire pipeline |

### What Loom can learn from Pathmode

**"Constitution Rules" pattern.** Pathmode injects a set of non-negotiable constraints into every agent prompt automatically. Loom does this ad hoc — IA has standing rules, but they're manually maintained in the system_prompt. A dedicated `constitution.yaml` file that auto-injects into every worker prompt would be cleaner and ensure consistency. ITP's version would include: sophisticated actor default, factional neutrality, epistemic discipline, Wikipedia exclusion, anti-Islamophobic framing discipline.

**Vision-first filtering.** Pathmode aligns every evidence signal against a product vision before it enters the pipeline. This filters noise early. Loom's equivalent would be a "project thesis anchors" filter in SP or a pre-IA gate that checks whether new claims are relevant to the project's core analytical questions. Currently this happens implicitly in IA's system_prompt. Making it an explicit pipeline stage would improve signal-to-noise for high-volume ingestion.

**Evidence typing.** Pathmode categorizes evidence into five types: friction, quotes, observations, metrics, requests. Loom's SP extracts claims but doesn't sub-type them. Adding a `claim_type` field (factual assertion, stated position, quantitative metric, event report, attributed quote) would improve downstream routing and IA triage.

### What Pathmode could learn from Loom

**Audit independence is not optional.** Pathmode's synthesis is single-model: the same AI that ingests evidence also produces the spec. There's no independent review. Loom's blind audit pipeline (TN → LA/PA/RT → AS) is architecturally expensive but catches systematic biases that single-model pipelines cannot detect.

**Epistemic discipline beyond confidence scores.** A single confidence number (Pathmode's "92% confidence") collapses too many dimensions. Loom's four-level epistemic tags + source tier grounding + explicit reasoning chains provide much more actionable quality metadata.

**Terminology neutralization for honest review.** Without stripping project-specific vocabulary, an LLM reviewer will pattern-match to the project's framing and produce a favorable review that looks independent but isn't. This is a subtle and important insight that applies to any multi-agent system where one agent reviews another's work.

---

## 4. Gotchas and Anti-Patterns

### 4.1 Don't let the audition harness flatter you

The audition script tests schema compliance — not analytical quality. A model that produces perfectly structured garbage will score 6/6. Schema compliance is necessary but not sufficient. You also need analytical quality tests, which require human evaluation of the content.

### 4.2 output_schema is metadata, not instruction

The `output_schema` block in a worker config is consumed by the test harness and potentially by the Loom runner for validation. It is NOT automatically shown to the model. If you change the output_schema, you must also update the concrete example in the system_prompt. These two things can drift out of sync — and when they do, the model produces output that matches the example (what it sees) but fails schema validation (what the harness checks).

**Mitigation:** The audition script is the canary. Run it after every schema change.

### 4.3 YAML's boolean trap

In YAML, bare `yes`, `no`, `true`, `false`, `on`, `off` are all booleans. If a worker config has an `enum` field that includes the string "true", YAML will parse it as boolean `True` before the worker ever sees it. This caused a real bug in early SP development where `is_forward: false` in the JSON example was being parsed by the config loader as Python `False` (boolean) instead of JSON `false`.

**Rule:** Always quote enum values in YAML configs if they could be interpreted as booleans. Better yet: use JSON for model output where this ambiguity doesn't exist.

### 4.4 The "frozen context" problem

LLM workers are stateless. Each invocation gets the system_prompt + knowledge silo content + user message. If the knowledge silo content is stale (e.g., the entity registry was updated but the silo file wasn't rebuilt), the worker operates on outdated information.

**Mitigation:** Knowledge silo rebuild should be a mandatory pre-step before any pipeline run. The Loom runner should refuse to start if silos are older than the database modification timestamp.

### 4.5 Silo leakage through examples

If your system_prompt example contains real project data (real entity names, real analytical conclusions), and that worker is supposed to be blind (LA, PA, RT), the example itself is a silo leak. Use generic, non-project-specific examples in blind worker prompts.

---

## 5. Extending Loom for a New Project

### 5.1 Minimum viable configuration

To adapt Loom for a different analytical domain, you need:

1. **Worker configs** (`configs/workers/*.yaml`): One per analytical role. Start with the five mechanical workers (SP, DE, XV, TN, IN) — these are domain-generic and mostly need prompt customization.

2. **Knowledge silos** (`configs/knowledge/*.yaml`): Define what each worker can see. The silo index maps silo names to file paths. Blind workers get minimal or empty silos.

3. **Entity ID registry**: A lookup table of all entities in your domain. Workers reference this for cross-validation.

4. **Terminology registry**: A mapping of project-specific terms to neutral equivalents. Required for audit independence.

5. **Test payloads**: Realistic input data for each worker role, used by the audition script.

### 5.2 The adaptation sequence

1. Define your analytical roles (who does what — claim extraction, analysis, audit, database ops).
2. Write worker configs with system_prompts, schemas, and concrete JSON output examples.
3. Build test payloads.
4. Run auditions to find which local models work for which roles.
5. Wire knowledge silos.
6. Configure the orchestrator pipeline (which worker feeds which).
7. Wire MCP gateway for human-in-the-loop interaction.

### 5.3 What's domain-generic vs. domain-specific

**Domain-generic (reusable as-is or with minor edits):**

- DE (Database Engineer) — just change entity ID formats and file paths
- XV (Cross-Validator) — just change the entity registry
- IN (Input Node) — routing rules need customization but structure is generic
- SA (Session Advisor) — cognitive monitoring is domain-agnostic
- AS (Audit Synthesizer) — synthesis logic is generic

**Domain-specific (requires full rewrite):**

- SP (Source Processor) — extraction rules depend entirely on source types
- IA (Intelligence Analyst) — the core analytical engine, fully domain-specific
- TN (Terminology Neutralizer) — registry is 100% project-specific
- WT (Watch Tower) — monitoring targets are project-specific
- NI (Narrative Intelligence) — corpus analysis patterns are domain-specific

**Domain-generic but rubric-specific:**

- LA (Logic Auditor) — generic rubric works across domains, but you may want to add domain-specific evaluation dimensions
- PA (Perspective Auditor) — same pattern
- RT (Red Teamer) — adversarial approach is generic; challenge targets may need domain tuning

---

## 6. Open Questions for Future Versions

1. **Constitution file pattern:** Should there be a `constitution.yaml` that auto-injects non-negotiable rules into every worker prompt? (Inspired by Pathmode's Constitution Rules.)

2. **Claim typing in SP:** Should SP sub-type extracted claims (factual assertion / stated position / quantitative metric / event report / attributed quote) for better downstream routing?

3. **Silo freshness enforcement:** Should the Loom runner refuse to start if knowledge silos are older than the source database?

4. **IntentSpec-like artifact standard:** Should Loom adopt a standardized output artifact format (like Pathmode's IntentSpec) that is readable by external tools? The current output is JSON blobs — a defined schema with a `.intent.json` extension and standard fields would improve interoperability.

5. **Multi-run convergence:** For high-stakes analytical tasks, should IA run multiple times with different temperatures and the results be aggregated? This is expensive but could improve confidence assessment.

---

## Appendix A: Model Audition Results (as of 2026-03-15)

Pre-fix results (before concrete output examples were added):

| Model | DE score | SP score | Notes |
|-------|----------|----------|-------|
| granite4:latest | 6/6 | 2/7 | DE had example; SP didn't |
| granite3.2:8b | 6/6 | error | Same pattern |
| llama3.2:3b | 5/6 | 2/7 | Slow (85s) |
| command-r7b | 5/6 | 0/7 | SP unparseable |
| deepseek-r1:8b | 0/6 | 0/7 | Reasoning model — wrong fit |

Post-fix results: pending (Code running auditions with corrected prompts).

## Appendix B: File Reference

| File | Purpose |
|------|---------|
| `configs/workers/*.yaml` | Worker definitions (system_prompt + schemas) |
| `configs/knowledge/itp_silos.yaml` | Silo index mapping |
| `scripts/audition_models.py` | Model audition test harness |
| `docs/architecture/ITP_MULTI_AGENT_ARCHITECTURE_v0_5.md` | Full architecture doc |
| `itp-workspace/SESSION_STARTER_*.md` | Session handoff documents |
