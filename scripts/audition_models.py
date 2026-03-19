#!/usr/bin/env python3
"""
audition_models.py — Test LLM candidates against ITP worker output schemas.

Sends each worker's system prompt + test payload to candidate models via
OpenAI-compatible APIs, then scores responses on schema compliance, field
accuracy, format correctness, and latency.

Usage:
  python scripts/audition_models.py                          # Ollama, all roles
  python scripts/audition_models.py --role sp --model llama3.1:8b
  python scripts/audition_models.py --provider chatllm       # ChatLLM/Abacus
  python scripts/audition_models.py --all-providers           # All configured
  python scripts/audition_models.py -v                        # Show full responses
  python scripts/audition_models.py --json                    # Machine-readable

Env vars:
  OLLAMA_URL          Ollama base (default http://localhost:11434)
  CHATLLM_BASE_URL    ChatLLM/Abacus endpoint
  CHATLLM_API_KEY     ChatLLM/Abacus API key
  OPENROUTER_API_KEY  OpenRouter API key
  ANTHROPIC_API_KEY   Anthropic API key (for direct Anthropic calls)

Requirements: pip install httpx pyyaml
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

BAFT_DIR = Path(__file__).parent.parent
WORKERS_DIR = BAFT_DIR / "configs" / "workers"

PROVIDERS: dict[str, dict[str, str]] = {
    "ollama": {
        "base_url": os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/v1",
        "api_key": "ollama",
    },
    "chatllm": {
        "base_url": os.environ.get("CHATLLM_BASE_URL", "https://api.abacus.ai/v1"),
        "api_key": os.environ.get("CHATLLM_API_KEY", ""),
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": os.environ.get("OPENROUTER_API_KEY", ""),
    },
}

MODEL_CANDIDATES: dict[str, list[str]] = {
    "ollama": [
        "llama3.2:3b",
        "command-r7b:latest",
        "granite3.2:8b",
        "granite4:latest",
        "gemma3:27b",
        "devstral:latest",
        "qwen3-coder:30b",
    ],
    "chatllm": [
        "claude-sonnet-4-20250514",
        "gpt-4o-mini",
        "gemini-2.0-flash",
        "llama-3.1-70b",
        "mistral-small-latest",
        "deepseek-chat",
        "command-r-plus",
    ],
    "openrouter": [
        "anthropic/claude-sonnet-4-20250514",
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.1-70b-instruct",
    ],
}

TEST_PAYLOADS: dict[str, dict[str, Any]] = {
    "sp": {
        "source_bundle": {
            "items": [
                {
                    "global_id": "test:1",
                    "url": "https://example.com/report",
                    "language": "en",
                    "source_tier": 3,
                    "retrieval_date": "2026-03-15",
                    "raw_text": (
                        "Iranian state media reported that IRGC commanders met with "
                        "Ali Larijani at SNSC headquarters to discuss succession "
                        "arrangements following Khamenei's death in the February strikes. "
                        "The meeting took place at a secure location in Tehran on March 10, "
                        "2026. Separately, Tasnim News Agency published a statement "
                        "attributed to Mojtaba Khamenei calling for 'national unity in the "
                        "face of aggression.' This was the first public statement from "
                        "Mojtaba since the February 28 strikes. The statement was text-only "
                        "with no video or audio evidence."
                    ),
                    "is_forward": False,
                }
            ],
        },
    },
    "de": {
        "integration_request": {
            "session_id": "audition_test",
            "operations": [
                {
                    "operation_id": "test_op_1",
                    "action": "validate_only",
                    "target_file": "data/variables.yaml",
                    "entity_id": "TV-16",
                    "fields": {"current_value": "near-halted", "epistemic_tag": "[Fact]"},
                }
            ],
        },
    },
    "xv": {
        "validation_request": {
            "entity_refs": ["TV-16", "TV-17", "Obs 031", "G22-01", "ITB-A9", "FAKE-999", "B07"],
        },
    },
    "tn": {
        "neutralization_request": {
            "analytical_text": (
                "The A9 Hollowness thesis predicts that the IRGC parallel economy "
                "will fracture under sustained bombardment. The Puppet Problem (Obs 008) "
                "applies to Mojtaba's succession: the Assembly of Experts has been coerced "
                "by Paydari faction operatives aligned with Mirbagheri. The Deal Cannot "
                "Hold thesis (B05) remains validated."
            ),
            "content_type": "observation_text",
        },
    },
    "in": {
        "note": (
            "URGENT: Factnameh posted satellite imagery showing new runway repair at "
            "Shiraz air base. Contradicts earlier Sentinel-2 data. Possibly IRGC rapid "
            "repair capability. Affects G23-03. Source: @factnameh Telegram, 14:22 UTC."
        ),
        "priority_override": "urgent",
    },
}

ROLE_TO_CONFIG = {
    "sp": "sp_source_processor.yaml",
    "de": "de_database_engineer.yaml",
    "xv": "xv_cross_validator.yaml",
    "tn": "tn_terminology_neutralizer.yaml",
    "in": "in_input_node.yaml",
}

_FENCE_RE = re.compile(r"```(?:json|ya?ml)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


@dataclass
class ScoreResult:
    """Result of auditing a single model against a worker schema."""

    model: str
    provider: str
    role: str
    schema_pass: bool
    required_fields_found: int
    required_fields_total: int
    output_format: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    error: str | None = None
    raw_response: str = ""


def _detect_format(raw: str) -> str:
    """Detect the output format (json, yaml, fenced_json, etc.) of a response."""
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            json.loads(stripped)
            return "json"
        except json.JSONDecodeError:
            pass
    fence_match = _FENCE_RE.search(stripped)
    if fence_match:
        inner = fence_match.group(1).strip()
        try:
            json.loads(inner)
            return "fenced_json"
        except json.JSONDecodeError:
            pass
        try:
            if isinstance(yaml.safe_load(inner), dict):
                return "fenced_yaml"
        except yaml.YAMLError:
            pass
    try:
        if isinstance(yaml.safe_load(stripped), dict):
            return "yaml"
    except yaml.YAMLError:
        pass
    return "prose"


def _parse_response(raw: str) -> dict | None:
    """Parse a model response as JSON or YAML, returning None on failure."""
    stripped = raw.strip()
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass
    fence_match = _FENCE_RE.search(stripped)
    if fence_match:
        inner = fence_match.group(1).strip()
        try:
            return json.loads(inner)
        except (json.JSONDecodeError, ValueError):
            pass
        try:
            p = yaml.safe_load(inner)
            if isinstance(p, dict):
                return p
        except yaml.YAMLError:
            pass
    try:
        p = yaml.safe_load(stripped)
        if isinstance(p, dict):
            return p
    except yaml.YAMLError:
        pass
    return None


def _check_required_fields(parsed: dict, output_schema: dict) -> tuple[int, int]:
    found = total = 0
    required_top = output_schema.get("required", [])
    properties = output_schema.get("properties", {})
    for req_key in required_top:
        total += 1
        if req_key in parsed:
            found += 1
            nested = properties.get(req_key, {})
            nested_req = nested.get("required", [])
            if nested_req and isinstance(parsed[req_key], dict):
                for nk in nested_req:
                    total += 1
                    if nk in parsed[req_key]:
                        found += 1
    return found, total


def call_model(
    provider_name: str, model: str, system_prompt: str, user_message: str, timeout: float = 120
) -> tuple[str, int, int, float]:
    """Send a chat completion request and return (content, tokens_in, tokens_out, latency_ms)."""
    provider = PROVIDERS[provider_name]
    base_url = provider["base_url"]
    api_key = provider["api_key"]
    if not api_key:
        raise ValueError(f"No API key for '{provider_name}'")
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 4000,
        "temperature": 0.1,
    }
    t0 = time.monotonic()
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(f"{base_url}/chat/completions", json=body, headers=headers)
        resp.raise_for_status()
    latency_ms = int((time.monotonic() - t0) * 1000)
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return content, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), latency_ms


def load_worker_config(role: str) -> dict:
    """Load a worker YAML config by role abbreviation."""
    with open(WORKERS_DIR / ROLE_TO_CONFIG[role]) as f:
        return yaml.safe_load(f)


def audition_one(
    provider_name: str, model: str, role: str, verbose: bool = False, timeout: float = 120
) -> ScoreResult:
    """Run a single model audition against the specified worker role."""
    config = load_worker_config(role)
    system_prompt = config["system_prompt"]
    output_schema = config.get("output_schema", {})
    payload = TEST_PAYLOADS[role]
    # Belt-and-suspenders: inject output schema key hints into user message
    schema_hint = ""
    if output_schema and output_schema.get("properties"):
        top_key = next(iter(output_schema["properties"].keys()))
        nested_props = output_schema["properties"].get(top_key, {})
        nested_req = nested_props.get("required", [])
        schema_hint = (
            f"\n\nYour output MUST be valid JSON with '{top_key}' as the "
            f"top-level key. Required nested keys under `{top_key}`: "
            f"{', '.join(nested_req) if nested_req else 'see system prompt'}."
        )

    user_msg = (
        "Process the following input and return structured output as specified."
        f"{schema_hint}\n\n"
        f"INPUT:\n```yaml\n{yaml.dump(payload, default_flow_style=False)}\n```"
    )
    try:
        content, tok_in, tok_out, latency = call_model(
            provider_name, model, system_prompt, user_msg, timeout
        )
    except Exception as e:
        return ScoreResult(
            model=model,
            provider=provider_name,
            role=role,
            schema_pass=False,
            required_fields_found=0,
            required_fields_total=0,
            output_format="error",
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            error=f"{type(e).__name__}: {str(e)[:100]}",
        )
    fmt = _detect_format(content)
    parsed = _parse_response(content)
    if parsed is None:
        return ScoreResult(
            model=model,
            provider=provider_name,
            role=role,
            schema_pass=False,
            required_fields_found=0,
            required_fields_total=0,
            output_format=fmt,
            latency_ms=latency,
            tokens_in=tok_in,
            tokens_out=tok_out,
            error="Could not parse structured output",
            raw_response=content if verbose else content[:200],
        )
    found, total = _check_required_fields(parsed, output_schema)
    return ScoreResult(
        model=model,
        provider=provider_name,
        role=role,
        schema_pass=(found == total and total > 0),
        required_fields_found=found,
        required_fields_total=total,
        output_format=fmt,
        latency_ms=latency,
        tokens_in=tok_in,
        tokens_out=tok_out,
        raw_response=content if verbose else "",
    )


def print_results(results: list[ScoreResult], as_json: bool = False) -> None:
    """Print audition results as a table or JSON."""
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "model": r.model,
                        "provider": r.provider,
                        "role": r.role,
                        "schema_pass": r.schema_pass,
                        "fields": f"{r.required_fields_found}/{r.required_fields_total}",
                        "format": r.output_format,
                        "latency_ms": r.latency_ms,
                        "tokens_out": r.tokens_out,
                        "error": r.error,
                    }
                    for r in results
                ],
                indent=2,
            )
        )
        return
    roles_seen: dict[str, list[ScoreResult]] = {}
    for r in results:
        roles_seen.setdefault(r.role, []).append(r)
    for role, rr in roles_seen.items():
        print(f"\n{'=' * 72}")
        print(f"  Role: {role.upper()} ({ROLE_TO_CONFIG[role]})")
        print(f"{'=' * 72}")
        print(
            f"  {'Model':<35} {'Pass':>4}  {'Fields':>8}  {'Format':<13} {'Latency':>8}  {'Tok':>5}"
        )
        print(f"  {'-' * 35} {'-' * 4}  {'-' * 8}  {'-' * 13} {'-' * 8}  {'-' * 5}")
        for r in sorted(rr, key=lambda x: (not x.schema_pass, x.latency_ms)):
            mark = "\u2705" if r.schema_pass else "\u274c"
            fields = f"{r.required_fields_found}/{r.required_fields_total}"
            err = f"  \u26a0 {r.error[:40]}" if r.error else ""
            print(
                f"  {r.model:<35} {mark:>4}  {fields:>8}  "
                f"{r.output_format:<13} {r.latency_ms:>7}ms  {r.tokens_out:>5}{err}"
            )
    total = len(results)
    passed = sum(1 for r in results if r.schema_pass)
    print(f"\n{'=' * 72}")
    print(f"  TOTAL: {passed}/{total} passed schema validation")
    print(f"{'=' * 72}")


def main() -> None:
    """CLI entry point for the model audition runner."""
    parser = argparse.ArgumentParser(description="Audition LLMs against ITP worker schemas")
    parser.add_argument("--role", choices=list(ROLE_TO_CONFIG.keys()))
    parser.add_argument("--model", help="Test specific model")
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), default="ollama")
    parser.add_argument("--all-providers", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    roles = [args.role] if args.role else list(ROLE_TO_CONFIG.keys())
    if args.all_providers:
        providers = [p for p in PROVIDERS if PROVIDERS[p]["api_key"]]
    else:
        providers = [args.provider]
    results: list[ScoreResult] = []
    for prov in providers:
        models = [args.model] if args.model else MODEL_CANDIDATES.get(prov, [])
        if not models:
            print(f"No models for '{prov}', skipping.", file=sys.stderr)
            continue
        for model in models:
            for role in roles:
                if not args.json:
                    print(f"  Testing [{prov}] {model} \u2192 {role}...", end="", flush=True)
                r = audition_one(prov, model, role, verbose=args.verbose, timeout=args.timeout)
                results.append(r)
                if not args.json:
                    s = "\u2705" if r.schema_pass else "\u274c"
                    print(f" {s} ({r.latency_ms}ms)")
                if args.verbose and r.raw_response:
                    print("    --- Response (first 400 chars) ---")
                    print(f"    {r.raw_response[:400]}")
                    print("    ----------------------------------")
    print_results(results, as_json=args.json)


if __name__ == "__main__":
    main()
