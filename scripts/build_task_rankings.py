#!/usr/bin/env python3
"""
Task Rankings Builder

Merges the benchmark catalog with live model health data from
registry/model_registry.json to produce per-task ranked model lists.

Tasks: coding, reasoning, agentic, long_context, fast_chat, vision, finance

Each task has:
  primary   = verified free models (best quality first)
  secondary = paid models ranked by benchmark-per-dollar

Outputs: registry/task_rankings.json
"""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

REPO = Path(__file__).resolve().parents[1]
REGISTRY_DIR = REPO / "registry"
BENCHMARK_FILE = REGISTRY_DIR / "benchmark_raw.json"
REGISTRY_FILE = REGISTRY_DIR / "model_registry.json"
CATALOG_FILE = REGISTRY_DIR / "openrouter_catalog.json"
OUTPUT_FILE = REGISTRY_DIR / "task_rankings.json"
VERIFIED_FILE = REGISTRY_DIR / "verified_free_models.json"

# ─── Task Definitions ───────────────────────────────────────────
TASKS = {
    "coding": {
        "label": "Coding",
        "filters": {
            "keywords": ["coder", "code", "programming", "codestral", "deepseek", "glm", "qwen3-coder", "mistral", "gpt-4.1", "gpt-5"],
            "require_tools": True,
            "require_reasoning": False,
        },
        "context_floor": 128000,
    },
    "reasoning": {
        "label": "Reasoning / Hard Bugs",
        "filters": {
            "keywords": ["reasoning", "think", "nemotron-ultra", "nemotron-super", "nemotron-3.5-lightning"],
            "require_tools": False,
            "require_reasoning": True,
        },
        "context_floor": 128000,
    },
    "agentic": {
        "label": "Agentic / Tool Use",
        "filters": {
            "keywords": ["agent", "nim", "kimi", "minimax-m"],
            "require_tools": True,
            "require_reasoning": False,
        },
        "context_floor": 65536,
    },
    "long_context": {
        "label": "Long Context",
        "filters": {
            "min_context": 500000,
            "require_tools": False,
            "require_reasoning": False,
        },
    },
    "fast_chat": {
        "label": "Fast / Cheap Chat",
        "filters": {
            "max_cost_prompt": 0.00001,
            "require_tools": False,
            "require_reasoning": False,
        },
        "context_floor": 65536,
    },
    "vision": {
        "label": "Vision / Multimodal",
        "filters": {
            "keywords": ["vl", "vision", "omni", "gemma", "qwen3.5", "pixtral", "jina"],
            "require_tools": False,
            "require_reasoning": False,
        },
    },
    "finance": {
        "label": "Finance / Numbers",
        "filters": {
            "keywords": ["minimax", "deepseek", "gpt", "claude", "grok"],
            "require_reasoning": True,
            "require_tools": False,
        },
        "context_floor": 128000,
    },
}


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def compute_benchmark_per_dollar(model: dict) -> float:
    """Higher = better quality-per-dollar. Uses Aider scores + intelligence proxies."""
    pricing = model.get("pricing", {})
    try:
        prompt_cost = float(pricing.get("prompt", "0"))
        completion_cost = float(pricing.get("completion", "0"))
    except (ValueError, TypeError):
        return 0.0
    total_cost = prompt_cost + completion_cost
    if total_cost <= 0:
        return 9999.0  # free models get top score

    # Quality proxy: aider_pass_rate_2 + context + reasoning + tool_call
    quality = 0.0
    quality += (model.get("aider_pass_rate_2", 0) / 100) * 40  # max 40
    quality += min(model.get("context_length", 0) / 1_000_000, 1.0) * 20  # max 20
    if model.get("reasoning"): quality += 15
    if model.get("tool_call"): quality += 10
    if model.get("structured_output"): quality += 5
    if model.get("aider_entries", 0) > 0: quality += 5  # benchmark-verified
    if model.get("trending_score", 0) > 0: quality += min(model["trending_score"] / 1000, 10)

    return quality / total_cost * 1000  # normalize


def categorize_model(model: dict) -> List[str]:
    """Determine which tasks a model belongs to."""
    model_id = model.get("id", "").lower()
    name = model.get("name", "").lower()
    text = f"{model_id} {name}"
    params = model.get("supported_parameters", [])
    modalities = model.get("modalities", {}).get("input", [])
    context = model.get("context_length", 0)

    tasks = []
    for task_id, task_def in TASKS.items():
        f = task_def["filters"]
        matched = True

        # Keywords
        if f.get("keywords"):
            if not any(kw in text for kw in f["keywords"]):
                matched = False

        # Min context
        if f.get("min_context") and context < f["min_context"]:
            matched = False

        # Max cost
        if f.get("max_cost_prompt"):
            try:
                cost = float(model.get("pricing", {}).get("prompt", "1"))
                if cost > f["max_cost_prompt"]:
                    matched = False
            except (ValueError, TypeError):
                pass

        # Require tools (check supported_parameters)
        if f.get("require_tools") and not has_tool_capability(model):
            matched = False

        # Require reasoning (check supported_parameters)
        if f.get("require_reasoning") and not has_param(model, "reasoning"):
            matched = False

        # Require modalities
        if f.get("modalities_input"):
            if not any(m in modalities for m in f["modalities_input"]):
                matched = False

        if matched:
            tasks.append(task_id)

    return tasks


def is_free_model(model: dict) -> bool:
    pricing = model.get("pricing", {})
    try:
        return float(pricing.get("prompt", "1")) == 0 and float(pricing.get("completion", "1")) == 0
    except (ValueError, TypeError):
        return False


def has_param(model: dict, param: str) -> bool:
    """Check if a parameter is in supported_parameters."""
    return param in model.get("supported_parameters", [])


def has_tool_capability(model: dict) -> bool:
    """Check if model supports tools via supported_parameters."""
    return has_param(model, "tools") or has_param(model, "tool_choice")


def load_verified_free_models() -> set:
    """Load verified-free model IDs from the health check."""
    data = load_json(VERIFIED_FILE)
    if not data:
        return set()
    ids = set()
    for role, models in data.get("pool", {}).items():
        for m in models:
            ids.add(m.get("id", ""))
    return ids


def build_task_rankings():
    print("[build_task_rankings] Loading data...")

    benchmark = load_json(BENCHMARK_FILE)
    registry = load_json(REGISTRY_FILE)
    catalog = load_json(CATALOG_FILE)

    if not benchmark:
        print("[build_task_rankings] No benchmark data. Using catalog only.")
        benchmark = {"models": catalog or []}
    if not catalog and benchmark:
        catalog = benchmark.get("models", [])

    verified_free = load_verified_free_models()

    # Build lookup: openrouter_id -> model
    model_lookup = {}
    for m in catalog:
        oid = m.get("id", "")
        if oid:
            model_lookup[oid] = m
    for m in benchmark.get("models", []):
        oid = m.get("id", "")
        if oid and oid not in model_lookup:
            model_lookup[oid] = m

    # For openrouter models not in catalog, try registry
    if registry:
        for source in ["openrouter_models", "nim_models"]:
            for m in registry.get(source, []):
                oid = m.get("id", "")
                if oid and oid not in model_lookup:
                    model_lookup[oid] = {"id": oid, "name": m.get("name", oid)}

    # Categorize and rank
    task_rankings = {}
    for task_id, task_def in TASKS.items():
        scored = []
        for model in model_lookup.values():
            tasks = categorize_model(model)
            if task_id not in tasks:
                continue
            score = compute_benchmark_per_dollar(model)
            free = is_free_model(model)
            verified = model.get("id", "") in verified_free

            scored.append({
                "id": model.get("id", ""),
                "name": model.get("name", model.get("id", "")),
                "score": round(score, 2),
                "free": free,
                "verified_free": verified,
                "context_length": model.get("context_length", 0),
                "pricing": model.get("pricing", {}),
                "reasoning": has_param(model, "reasoning"),
                "tool_call": model.get("tool_call", False),
                "aider_pass_rate_2": model.get("aider_pass_rate_2", 0),
                "release_date": model.get("release_date", ""),
            })

        # Sort: verified-free first, then free (by score desc), then paid (by score desc)
        scored.sort(key=lambda x: (
            0 if x["verified_free"] else (1 if x["free"] else 2),
            -x["score"] if not x["free"] else x["score"] * 10,  # free higher is better
        ))

        primary = [m for m in scored if m["free"]][:10]
        secondary = [m for m in scored if not m["free"]][:10]

        task_rankings[task_id] = {
            "label": task_def["label"],
            "primary_free": primary,
            "secondary_paid": secondary,
            "total_evaluated": len(scored),
        }

    # Build summary
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tasks": task_rankings,
        "metadata": {
            "models_in_catalog": len(model_lookup),
            "verified_free_count": len(verified_free),
            "benchmark_source": "openrouter + aider_polyglot + hf_trending",
        },
    }

    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"[build_task_rankings] Done. {len(model_lookup)} models evaluated.")
    for task_id, data in task_rankings.items():
        print(f"  {task_id}: {len(data['primary_free'])} primary free, {len(data['secondary_paid'])} paid")


if __name__ == "__main__":
    build_task_rankings()
