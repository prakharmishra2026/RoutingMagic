#!/usr/bin/env python3
"""
Benchmark Aggregator — Free Sources Only

Fetches model evaluation data from free sources and merges into a single
benchmark_scores.json consumed by build_task_rankings.py.

Sources:
  1. OpenRouter models API          — pricing, capabilities, context, category
  2. Aider polyglot leaderboard YAML — coding pass rates
  3. HuggingFace trending API        — popularity/recency signal

Outputs: registry/benchmark_raw.json
"""
import json, os, sys, urllib.request, ssl, yaml
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

REPO = Path(__file__).resolve().parents[1]
REGISTRY_DIR = REPO / "registry"
BENCHMARK_FILE = REGISTRY_DIR / "benchmark_raw.json"
ALIASES_FILE = REGISTRY_DIR / "model_aliases.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models?include_pricing=true"
OPENROUTER_CAT_URL = "https://openrouter.ai/api/v1/models?include_pricing=true&limit=500"
HF_TRENDING_URL = "https://huggingface.co/api/models?sort=trendingScore&limit=50"
AIDER_URL = "https://raw.githubusercontent.com/Aider-AI/aider/main/aider/website/_data/polyglot_leaderboard.yml"

TIMEOUT = 30


def fetch_url(url: str, headers: dict = None) -> dict:
    """Fetch a JSON endpoint. Returns {} on failure."""
    try:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "RoutingMagic/1.0"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[fetch_benchmarks] {url}: {e}")
        return {}


def fetch_openrouter() -> dict:
    """Fetch OpenRouter models with pricing."""
    data = fetch_url(OPENROUTER_URL)
    models = data.get("data", [])
    print(f"[fetch_benchmarks] OpenRouter: {len(models)} models")
    return {"total": data.get("total_count", len(models)), "models": models}


def fetch_aider() -> list:
    """Fetch Aider polyglot leaderboard."""
    try:
        req = urllib.request.Request(AIDER_URL, headers={"User-Agent": "RoutingMagic/1.0"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, context=ctx, timeout=TIMEOUT) as resp:
            raw = resp.read().decode()
        data = yaml.safe_load(raw)
        print(f"[fetch_benchmarks] Aider polyglot: {len(data)} entries")
        return data
    except Exception as e:
        print(f"[fetch_benchmarks] Aider: {e}")
        return []


def fetch_hf_trending() -> list:
    """Fetch HuggingFace trending models."""
    data = fetch_url(HF_TRENDING_URL)
    models = data if isinstance(data, list) else data.get("models", [])
    print(f"[fetch_benchmarks] HF trending: {len(models)} models")
    return [{"id": m.get("id", ""), "trendingScore": m.get("trendingScore", 0), "likes": m.get("likes", 0)} for m in models]


def build_aliases_map() -> Dict[str, str]:
    """Build prefix -> openrouter_id map from alias table."""
    if not ALIASES_FILE.exists():
        return {}
    try:
        with open(ALIASES_FILE) as f:
            aliases = json.load(f)
        mapping = {}
        for a in aliases.get("aliases", []):
            aid = a.get("aider_name", "")
            or_id = a.get("openrouter_id", "")
            if aid and or_id:
                mapping[aid.lower()] = or_id
        return mapping
    except Exception as e:
        print(f"[fetch_benchmarks] aliases: {e}")
        return {}


def match_aider_to_openrouter(aider_entries: list, or_models: list, alias_map: Dict[str, str]) -> Dict[str, dict]:
    """Map Aider entries to OpenRouter IDs, returning {openrouter_id: {pass_rate, ...}}."""
    # Build reverse lookup: openrouter id/name -> model object
    or_lookup = {}
    for m in or_models:
        oid = m.get("id", "")
        name = m.get("name", "").lower()
        or_lookup[oid] = m
        or_lookup[name] = m
        # also check hugging_face_id
        hf = m.get("hugging_face_id", "")
        if hf:
            or_lookup[hf.lower()] = m

    results = {}
    for entry in aider_entries:
        cmd = entry.get("command", "")
        model_name = entry.get("model", "").lower()

        # Extract model name from command: --model <name>
        aid_name = None
        if "--model" in cmd:
            parts = cmd.split("--model")
            if len(parts) > 1:
                aid_name = parts[1].strip().split()[0]
        aid_name = aid_name or model_name
        if not aid_name:
            continue

        aid_lower = aid_name.lower()

        # Try alias map first
        or_id = alias_map.get(aid_lower)
        if or_id and or_id in or_lookup:
            results[or_id] = _merge_scores(results.get(or_id, {}), entry)
            continue

        # Fuzzy prefix match
        for oid, mobj in or_lookup.items():
            if aid_lower in oid.lower() or oid.lower() in aid_lower:
                if oid not in results:  # first match wins
                    results[or_id if or_id in or_lookup else oid] = _merge_scores(
                        results.get(oid, {}), entry
                    )
                break

    return results


def _merge_scores(existing: dict, entry: dict) -> dict:
    """Merge Aider entry scores into existing dict."""
    pass1 = entry.get("pass_rate_1", 0) or 0
    pass2 = entry.get("pass_rate_2", 0) or 0
    total = entry.get("total_tests", 1) or 1
    existing["aider_pass_rate_1"] = round(pass1, 2)
    existing["aider_pass_rate_2"] = round(pass2, 2)
    existing["aider_total_tests"] = total
    existing["aider_entries"] = existing.get("aider_entries", 0) + 1
    return existing


def main():
    print("[fetch_benchmarks] Starting...")

    # Fetch sources
    or_data = fetch_openrouter()
    or_models = or_data["models"]
    aider_entries = fetch_aider()
    hf_trending = fetch_hf_trending()
    alias_map = build_aliases_map()

    # Build HF lookup
    hf_lookup = {m["id"].lower(): m for m in hf_trending}

    # Enrich OpenRouter models with benchmark data
    scored_models = []
    for m in or_models:
        oid = m.get("id", "")
        if not oid:
            continue
        entry = {
            "id": oid,
            "name": m.get("name", ""),
            "pricing": m.get("pricing", {}),
            "context_length": m.get("context_length", 0),
            "supported_parameters": m.get("supported_parameters", []),
            "reasoning": m.get("reasoning", False),
            "tool_call": m.get("tool_call", False),
            "structured_output": m.get("structured_output", False),
            "temperature": m.get("temperature", False),
            "release_date": m.get("release_date", ""),
            "created": m.get("created", 0),
            "modalities": m.get("modalities", {}),
            "hugging_face_id": m.get("hugging_face_id", ""),
            "categories": m.get("categories"),
            "trending_score": hf_lookup.get(oid.lower(), {}).get("trendingScore", 0),
            "trending_likes": hf_lookup.get(oid.lower(), {}).get("likes", 0),
        }
        scored_models.append(entry)

    # Overlay Aider scores
    aider_scores = match_aider_to_openrouter(aider_entries, or_models, alias_map)
    for sm in scored_models:
        aid = aider_scores.get(sm["id"], {})
        sm["aider_pass_rate_1"] = aid.get("aider_pass_rate_1", 0)
        sm["aider_pass_rate_2"] = aid.get("aider_pass_rate_2", 0)
        sm["aider_total_tests"] = aid.get("aider_total_tests", 0)
        sm["aider_entries"] = aid.get("aider_entries", 0)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sources": {
            "openrouter": {"total": or_data["total"], "fetched": len(or_models)},
            "aider_polyglot": {"entries": len(aider_entries)},
            "hf_trending": {"entries": len(hf_trending)},
        },
        "models": scored_models,
    }

    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    with open(BENCHMARK_FILE, "w") as f:
        json.dump(output, f, indent=2)

    # Also save a compact openrouter catalog for downstream
    catalog_file = REGISTRY_DIR / "openrouter_catalog.json"
    with open(catalog_file, "w") as f:
        json.dump(scored_models, f, indent=2)

    print(f"[fetch_benchmarks] Done. {len(scored_models)} models scored. Output: {BENCHMARK_FILE}")


if __name__ == "__main__":
    main()
