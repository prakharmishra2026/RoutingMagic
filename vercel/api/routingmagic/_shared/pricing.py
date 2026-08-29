"""Pricing and free model detection for Vercel deployment."""
import re
from typing import Optional, Dict, Set

# USD per 1M tokens
PRICING = {
    "claude-fable-5":    {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_write": 12.50},
    "claude-mythos-5":   {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_write": 12.50},
    "claude-opus-4-8":   {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25},
    "gpt-5":             {"input": 2.50, "output": 10.00, "cache_read": 0.25, "cache_write": 2.50},
    "gpt-4-turbo":       {"input": 10.00, "output": 30.00, "cache_read": 0.50, "cache_write": 10.00},
    "o3-mini":           {"input": 1.10, "output": 4.40, "cache_read": 0.11, "cache_write": 1.10},
    "gemini-2.5-flash":  {"input": 0.15, "output": 0.60, "cache_read": 0.0375, "cache_write": 0.15},
    "gemini-2.5-pro":    {"input": 1.25, "output": 10.00, "cache_read": 0.125, "cache_write": 1.25},
    "deepseek-v3":       {"input": 0.27, "output": 1.10, "cache_read": 0.07, "cache_write": 0.27},
    "deepseek-r1":       {"input": 0.55, "output": 2.19, "cache_read": 0.14, "cache_write": 0.55},
}

ZERO_PRICING = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

FREE_PROVIDER_TOKENS = {"nvidia", "nim", "opencode"}
FREE_MODEL_TOKENS = {"gpt-oss", "big-pickle", "laguna", "nemotron-3-ultra-free", "nemotron-3.5-lightning-free"}

PRICING_KEYS = {k.lower(): v for k, v in PRICING.items()}

FAMILY_PRICING = [
    ({"fable", "mythos"}, "claude-fable-5"),
    ({"opus"}, "claude-opus-4-8"),
    ({"sonnet"}, "claude-sonnet-4-6"),
    ({"haiku"}, "claude-haiku-4-5"),
    ({"claude"}, "claude-sonnet-4-6"),
    ({"deepseek", "r1"}, "deepseek-r1"),
    ({"deepseek"}, "deepseek-v3"),
    ({"gemini", "pro"}, "gemini-2.5-pro"),
    ({"gemini", "flash"}, "gemini-2.5-flash"),
    ({"gemini"}, "gemini-2.5-flash"),
    ({"gpt", "5"}, "gpt-5"),
    ({"gpt", "4"}, "gpt-4-turbo"),
    ({"o3"}, "o3-mini"),
    ({"o1"}, "o3-mini"),
]

# Cache for dynamic free models from registry
_freemodel_cache = {"nim": set(), "openrouter": set(), "mtime": 0}

def _model_tokens(model: str) -> Set[str]:
    return set(re.split(r"[/\-._:]+", model.lower()))

def _load_free_models_from_registry() -> tuple[Set[str], Set[str]]:
    """Load free model sets from registry JSON. Returns (nim_free, openrouter_free)."""
    global _freemodel_cache
    from pathlib import Path
    registry_path = Path("/tmp/registry/model_registry.json")
    if not registry_path.exists():
        return set(), set()
    
    mtime = registry_path.stat().st_mtime
    if _freemodel_cache["mtime"] == mtime and _freemodel_cache["nim"]:
        return _freemodel_cache["nim"], _freemodel_cache["openrouter"]
    
    try:
        import json
        with open(registry_path) as f:
            data = json.load(f)
        nim_free = set(m.lower() for m in data.get("nim_free_models", []))
        or_free = set(m.lower() for m in data.get("openrouter_free_models", []))
        _freemodel_cache = {"nim": nim_free, "openrouter": or_free, "mtime": mtime}
        return nim_free, or_free
    except Exception:
        return set(), set()

def is_free(model: str, source: str = None) -> bool:
    """Unified free/paid determination used by server + serialized to client."""
    if not model:
        return True
    m = model.lower()
    if source == "routingmagic":
        return True
    if ":free" in m:
        return True
    tokens = _model_tokens(m)
    if "free" in tokens:
        return True
    if "/" in m:
        provider = m.split("/", 1)[0]
        if provider in FREE_PROVIDER_TOKENS:
            return True
        if provider in {"nvidia", "nim", "openrouter"}:
            # Check registry for dynamic free models
            nim_free, or_free = _load_free_models_from_registry()
            if m in nim_free or m in or_free:
                return True
    if tokens & FREE_MODEL_TOKENS:
        return True
    return False

def get_pricing(model: str, source: str = None) -> Optional[Dict]:
    if not model:
        return None
    if is_free(model, source):
        return ZERO_PRICING
    low = model.lower()
    if low in PRICING_KEYS:
        return PRICING_KEYS[low]
    base = low.split("/")[-1]
    if base in PRICING_KEYS:
        return PRICING_KEYS[base]
    tokens = _model_tokens(low)
    for family_tokens, pricing_key in FAMILY_PRICING:
        if family_tokens.issubset(tokens):
            return PRICING_KEYS[pricing_key]
    return None

def calc_cost(model: str, inp: int, out: int, cache_read: int, cache_write: int, source: str = None) -> float:
    p = get_pricing(model, source)
    if not p:
        return 0.0
    return (
        inp * p["input"] / 1_000_000 +
        out * p["output"] / 1_000_000 +
        cache_read * p["cache_read"] / 1_000_000 +
        cache_write * p["cache_write"] / 1_000_000
    )
