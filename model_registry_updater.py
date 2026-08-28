#!/usr/bin/env python3
"""
Model Registry Auto-Updater — Dual Source (NVIDIA NIM + OpenRouter)

Daily fetches model registries from both sources, merges with priority:
  Tier 1: NVIDIA NIM Direct (free, ~40 RPM, same models that cost $ on OpenRouter)
  Tier 2: OpenRouter Free Models (fallback when NIM rate-limited)
  Tier 3: opencode Built-in Free Models (last resort)

Updates:
- Free model list with reasoning support
- NVIDIA NIM model mappings
- Fallback chains (pre-computed priority order)
- Model capability metadata
- Health checks (marks degraded models for 24h)
"""
import os
import json
import argparse
import urllib.request
import ssl
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, asdict, field
from dotenv import load_dotenv

# Load API keys from user's config
_ROUTING_MAGIC_ENV = os.path.expanduser("~/.routingmagic/.env")
load_dotenv(_ROUTING_MAGIC_ENV)
load_dotenv(os.path.expanduser("~/global.env"))

# ─── Paths ──────────────────────────────────────────────────────────────
# Default: repo registry (versioned, shared via GitHub Action)
# Override with --output-dir for local ~/.routingmagic/registry
REPO_REGISTRY_DIR = Path(__file__).parent / "registry"
HOME_REGISTRY_DIR = Path.home() / ".routingmagic" / "registry"

REGISTRY_DIR = REPO_REGISTRY_DIR  # Default, overridden by CLI
MODEL_REGISTRY_FILE = REGISTRY_DIR / "model_registry.json"
MODEL_CHANGELOG_FILE = REGISTRY_DIR / "model_changelog.md"
LAST_UPDATE_FILE = REGISTRY_DIR / "last_update.txt"
HEALTH_CACHE_FILE = REGISTRY_DIR / "health_cache.json"

# ─── API Endpoints ──────────────────────────────────────────────────────
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_PRICING_URL = "https://openrouter.ai/api/v1/models?include_pricing=true"
NVIDIA_NIM_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"

# ─── Constants ──────────────────────────────────────────────────────────
MIN_CONTEXT_LENGTH = 8000
REQUIRED_PARAMS = ["temperature", "max_tokens"]

# opencode built-in free models (static, always available)
OPENCODE_BUILTIN_MODELS = [
    {"id": "opencode/nemotron-3-ultra-free", "name": "Nemotron 3 Ultra (opencode)", "context_length": 1000000, "category": "reasoning_flagship", "source": "opencode", "has_reasoning": True, "score": 45.0},
    {"id": "opencode/nemotron-3.5-lightning-free", "name": "Nemotron 3.5 Lightning (opencode)", "context_length": 1000000, "category": "long_context", "source": "opencode", "has_reasoning": True, "score": 40.0},
]

# Tier 1: NVIDIA NIM Direct models (known free models on NIM)
# These are the SAME models that cost money on OpenRouter
# Model IDs match the actual NVIDIA NIM API response (no "nvidia/" prefix for partner models)

# Known metadata for NIM models (since API doesn't return context_length/params)
NIM_MODEL_METADATA = {
    "deepseek-ai/deepseek-v4-flash-0731":      {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens", "reasoning"], "category": "coding"},
    "z-ai/glm-5.2":                            {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens", "reasoning"], "category": "agentic"},
    "nvidia/nemotron-3-ultra-550b-a55b":       {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens", "reasoning"], "category": "reasoning_flagship"},
    "qwen/qwen3-coder-480b-a35b-instruct":     {"context_length": 256000, "supported_parameters": ["temperature", "max_tokens", "tools"], "category": "coding"},
    "minimaxai/minimax-m2.7":                  {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens"], "category": "long_context"},
    "google/gemma-4-31b-it":                   {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens"], "category": "general"},
    "nvidia/nemotron-3.5-lightning-30b-a3b":   {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens", "reasoning"], "category": "long_context"},
    "mistralai/mistral-large-2-instruct":      {"context_length": 128000, "supported_parameters": ["temperature", "max_tokens", "tools"], "category": "general"},
    "minimaxai/minimax-m3":                    {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens", "tools"], "category": "long_context"},
    "nvidia/nemotron-3-super-120b-a12b":       {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens", "reasoning", "tools"], "category": "reasoning"},
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": {"context_length": 256000, "supported_parameters": ["temperature", "max_tokens", "reasoning"], "category": "reasoning"},
    "nvidia/nemotron-ocr-v1":                  {"context_length": 128000, "supported_parameters": ["temperature", "max_tokens"], "category": "vision"},
    "nvidia/nemotron-voicechat":               {"context_length": 128000, "supported_parameters": ["temperature", "max_tokens"], "category": "vision"},
    "nvidia/cosmos-reason2-8b":                {"context_length": 128000, "supported_parameters": ["temperature", "max_tokens", "reasoning"], "category": "reasoning"},
    "stepfun-ai/step-3.7-flash":               {"context_length": 128000, "supported_parameters": ["temperature", "max_tokens"], "category": "general"},
    "moonshotai/kimi-k2.6":                    {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens", "tools"], "category": "agentic"},
    "nvidia/llama-3.1-nemotron-ultra-253b-v1": {"context_length": 1000000, "supported_parameters": ["temperature", "max_tokens", "reasoning"], "category": "reasoning_flagship"},
    "poolside/laguna-xs-2.1":                  {"context_length": 262144, "supported_parameters": ["temperature", "max_tokens", "tools"], "category": "coding"},
    "openai/gpt-oss-120b":                     {"context_length": 131072, "supported_parameters": ["temperature", "max_tokens", "reasoning", "tools"], "category": "reasoning"},
    "nvidia/nemotron-3.5-content-safety":      {"context_length": 128000, "supported_parameters": ["temperature", "max_tokens", "reasoning"], "category": "general"},
}

NIM_KNOWN_FREE_MODELS = list(NIM_MODEL_METADATA.keys())

# ─── Data Classes ───────────────────────────────────────────────────────
@dataclass
class ModelInfo:
    id: str
    name: str
    context_length: int
    providers: List[str] = field(default_factory=list)
    provider_count: int = 0
    has_reasoning: bool = False
    supported_parameters: List[str] = field(default_factory=list)
    created: int = 0
    score: float = 0.0
    category: str = "general"
    source: str = "openrouter"  # "nim" | "openrouter" | "opencode"
    degraded_until: Optional[str] = None  # ISO timestamp when health check failed

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "ModelInfo":
        return cls(**data)


@dataclass
class Registry:
    nim_models: List[ModelInfo] = field(default_factory=list)
    openrouter_models: List[ModelInfo] = field(default_factory=list)
    opencode_models: List[ModelInfo] = field(default_factory=list)
    merged_fallback_chain: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "nim_models": [m.to_dict() for m in self.nim_models],
            "openrouter_models": [m.to_dict() for m in self.openrouter_models],
            "opencode_models": [m.to_dict() for m in self.opencode_models],
            "merged_fallback_chain": self.merged_fallback_chain,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Registry":
        return cls(
            nim_models=[ModelInfo.from_dict(m) for m in data.get("nim_models", [])],
            openrouter_models=[ModelInfo.from_dict(m) for m in data.get("openrouter_models", [])],
            opencode_models=[ModelInfo.from_dict(m) for m in data.get("opencode_models", [])],
            merged_fallback_chain=data.get("merged_fallback_chain", []),
            metadata=data.get("metadata", {}),
        )


# ─── Scoring & Categorization ───────────────────────────────────────────
def get_model_score(model: Dict, source: str) -> float:
    """Score model for routing priority. Higher = better."""
    score = 0.0
    
    # Context length (normalized to 1M)
    ctx = model.get("context_length", 0)
    score += min(ctx / 1_000_000, 1.0) * 10
    
    # Source priority: NIM direct > OpenRouter free > opencode
    source_bonus = {"nim": 30, "openrouter": 20, "opencode": 10}
    score += source_bonus.get(source, 0)
    
    # Reasoning support
    params = model.get("supported_parameters", [])
    if "reasoning" in params or "include_reasoning" in params or "reasoning_effort" in params:
        score += 15
    
    # Provider diversity (more providers = more reliable) — OpenRouter only
    if source == "openrouter":
        providers = len(model.get("providers", []))
        score += min(providers, 5) * 2
    
    # Recent model bonus (created timestamp)
    created = model.get("created", 0)
    if created > 1704067200:  # After 2024-01-01
        score += 5
    
    return score


def categorize_model(model: Dict) -> str:
    """Categorize model for routing."""
    model_id = model.get("id", "").lower()
    name = model.get("name", "").lower()
    
    # Reasoning specialists
    if "nemotron" in model_id and "ultra" in model_id:
        return "reasoning_flagship"
    if "gpt-oss" in model_id or "o1" in model_id or "o3" in model_id:
        return "reasoning"
    if "nemotron" in model_id and "super" in model_id:
        return "reasoning"
    if "phi-4" in model_id and "reasoning" in model_id:
        return "reasoning"
    if "reasoning" in model_id or "thinking" in model_id:
        return "reasoning"
    if "inkling" in model_id:
        return "reasoning"
    
    # Coding specialists
    if "coder" in model_id or "code" in model_id:
        return "coding"
    if "north-mini-code" in model_id:
        return "coding"
    if "poolside" in model_id and "laguna" in model_id:
        return "coding"
    
    # Large context (500K+)
    if model.get("context_length", 0) >= 500000:
        return "long_context"
    
    # Vision/multimodal
    if "vl" in model_id or "vision" in model_id or "omni" in model_id:
        return "vision"
    if "nemotron-ocr" in model_id:
        return "vision"
    
    # Agentic/tool use
    params = model.get("supported_parameters", [])
    if "tools" in params or "tool_choice" in params:
        return "agentic"
    
    return "general"


def has_reasoning(model: Dict) -> bool:
    params = model.get("supported_parameters", [])
    return any(p in params for p in ["reasoning", "include_reasoning", "reasoning_effort"])


def is_free_openrouter_model(model: Dict) -> bool:
    """Check if OpenRouter model is free (prompt and completion pricing = 0)."""
    pricing = model.get("pricing", {})
    try:
        prompt = float(pricing.get("prompt", "0"))
        completion = float(pricing.get("completion", "0"))
        return prompt == 0 and completion == 0
    except (ValueError, TypeError):
        return False


# ─── Fetching ───────────────────────────────────────────────────────────
def fetch_openrouter_models() -> List[Dict]:
    """Fetch live model data from OpenRouter."""
    try:
        req = urllib.request.Request(
            OPENROUTER_PRICING_URL,
            headers={"User-Agent": "RoutingMagic/1.0"}
        )
        context = ssl.create_default_context()
        with urllib.request.urlopen(req, context=context, timeout=30) as response:
            data = json.loads(response.read().decode())
            return data.get("data", [])
    except Exception as e:
        print(f"[ModelRegistry] Failed to fetch OpenRouter models: {e}")
        return []


def fetch_nvidia_nim_models(api_key: Optional[str] = None) -> List[Dict]:
    """Fetch live model data from NVIDIA NIM."""
    api_key = api_key or os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY")
    if not api_key:
        print("[ModelRegistry] No NVAPI_KEY found, skipping NVIDIA NIM fetch")
        return []
    
    try:
        req = urllib.request.Request(
            NVIDIA_NIM_MODELS_URL,
            headers={
                "User-Agent": "RoutingMagic/1.0",
                "Authorization": f"Bearer {api_key}",
            }
        )
        context = ssl.create_default_context()
        with urllib.request.urlopen(req, context=context, timeout=30) as response:
            data = json.loads(response.read().decode())
            return data.get("data", [])
    except Exception as e:
        print(f"[ModelRegistry] Failed to fetch NVIDIA NIM models: {e}")
        return []


def process_openrouter_models(raw_models: List[Dict]) -> List[ModelInfo]:
    """Process OpenRouter models, keep only free ones."""
    processed = []
    for model in raw_models:
        if not is_free_openrouter_model(model):
            continue
        
        model_id = model.get("id", "")
        if not model_id:
            continue
        
        info = ModelInfo(
            id=model_id,
            name=model.get("name", ""),
            context_length=model.get("context_length", 0),
            providers=model.get("providers", []),
            provider_count=len(model.get("providers", [])),
            has_reasoning=has_reasoning(model),
            supported_parameters=model.get("supported_parameters", []),
            created=model.get("created", 0),
            score=get_model_score(model, "openrouter"),
            category=categorize_model(model),
            source="openrouter",
        )
        processed.append(info)
    
    processed.sort(key=lambda x: x.score, reverse=True)
    return processed


def process_nvidia_nim_models(raw_models: List[Dict]) -> List[ModelInfo]:
    """Process NVIDIA NIM models, keep only known free ones."""
    processed = []
    known_free_set = set(NIM_KNOWN_FREE_MODELS)
    
    for model in raw_models:
        model_id = model.get("id", "")
        if not model_id:
            continue
        
        # Only include known free models
        if model_id not in known_free_set:
            continue
        
        # Enrich with known metadata since NIM API doesn't return context_length/params
        meta = NIM_MODEL_METADATA.get(model_id, {})
        context_length = meta.get("context_length", model.get("context_length", 0))
        supported_params = meta.get("supported_parameters", model.get("supported_parameters", []))
        category = meta.get("category", categorize_model(model))
        
        info = ModelInfo(
            id=model_id,
            name=model.get("name", model_id),
            context_length=context_length,
            providers=[],  # NIM doesn't return providers
            provider_count=1,
            has_reasoning="reasoning" in supported_params or "include_reasoning" in supported_params,
            supported_parameters=supported_params,
            created=model.get("created", 0),
            score=get_model_score({"context_length": context_length, "supported_parameters": supported_params}, "nim"),
            category=category,
            source="nim",
        )
        processed.append(info)
    
    processed.sort(key=lambda x: x.score, reverse=True)
    return processed


def get_opencode_models() -> List[ModelInfo]:
    """Get static opencode built-in models."""
    return [ModelInfo(**m) for m in OPENCODE_BUILTIN_MODELS]


# ─── Registry Operations ────────────────────────────────────────────────
def load_existing_registry(registry_dir: Path) -> Registry:
    """Load existing registry if exists."""
    registry_file = registry_dir / "model_registry.json"
    if registry_file.exists():
        try:
            with open(registry_file) as f:
                data = json.load(f)
                return Registry.from_dict(data)
        except Exception as e:
            print(f"[ModelRegistry] Failed to load registry: {e}")
    return Registry()


def save_registry_atomic(registry: Registry, registry_dir: Path):
    """Save registry to file atomically (write to temp, then rename)."""
    registry_dir.mkdir(parents=True, exist_ok=True)
    registry_file = registry_dir / "model_registry.json"
    temp_file = registry_dir / "model_registry.json.tmp"
    
    # Update metadata
    now = datetime.now(timezone.utc)
    registry.metadata.update({
        "updated_at": now.isoformat().replace("+00:00", "Z"),
        "nim_count": len(registry.nim_models),
        "openrouter_free_count": len(registry.openrouter_models),
        "opencode_count": len(registry.opencode_models),
        "total_models": len(registry.nim_models) + len(registry.openrouter_models) + len(registry.opencode_models),
    })
    
    with open(temp_file, "w") as f:
        json.dump(registry.to_dict(), f, indent=2)
    
    # Atomic rename
    temp_file.replace(registry_file)
    
    # Update last update timestamp
    with open(registry_dir / "last_update.txt", "w") as f:
        f.write(now.isoformat().replace("+00:00", "Z"))


def log_changes(old: Registry, new: Registry):
    """Log model changes to changelog."""
    changes = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    def model_key(m: ModelInfo) -> str:
        return f"{m.source}:{m.id}"
    
    old_models = {model_key(m): m for m in old.nim_models + old.openrouter_models + old.opencode_models}
    new_models = {model_key(m): m for m in new.nim_models + new.openrouter_models + new.opencode_models}
    
    # New models
    for key in set(new_models.keys()) - set(old_models.keys()):
        m = new_models[key]
        changes.append(f"  ➕ **Added**: {m.id} ({m.source}, {m.category}, score: {m.score:.1f})")
    
    # Removed models
    for key in set(old_models.keys()) - set(new_models.keys()):
        m = old_models[key]
        changes.append(f"  ➖ **Removed**: {m.id} ({m.source}, {m.category})")
    
    # Score changes
    for key in set(old_models.keys()) & set(new_models.keys()):
        old_score = old_models[key].score
        new_score = new_models[key].score
        if abs(old_score - new_score) > 5:
            direction = "⬆️" if new_score > old_score else "⬇️"
            changes.append(f"  {direction} **Score change**: {key} ({old_score:.1f} → {new_score:.1f})")
    
    if changes:
        with open(MODEL_CHANGELOG_FILE, "a") as f:
            f.write(f"\n## {timestamp}\n")
            f.write("\n".join(changes) + "\n")
        print(f"[ModelRegistry] Logged {len(changes)} changes")


def build_merged_fallback_chain(registry: Registry) -> List[str]:
    """Build pre-computed fallback chain: NIM → OpenRouter → opencode → paid."""
    chain = []
    seen = set()
    
    # Tier 1: NVIDIA NIM Direct (highest priority)
    for m in registry.nim_models:
        if m.id not in seen:
            chain.append(m.id)
            seen.add(m.id)
    
    # Tier 2: OpenRouter Free
    for m in registry.openrouter_models:
        if m.id not in seen:
            chain.append(m.id)
            seen.add(m.id)
    
    # Tier 3: opencode built-in
    for m in registry.opencode_models:
        if m.id not in seen:
            chain.append(m.id)
            seen.add(m.id)
    
    # Tier 4: Paid fallbacks (last resort)
    paid_fallbacks = [
        "gemini-2.5-pro",
        "openai/gpt-5",
        "openai/gpt-4-turbo",
        "openai/o3-mini",
    ]
    for m in paid_fallbacks:
        if m not in seen:
            chain.append(m)
            seen.add(m)
    
    return chain


# ─── Health Checks ──────────────────────────────────────────────────────
async def health_check_model(session: aiohttp.ClientSession, model: ModelInfo, api_key: str, base_url: str) -> bool:
    """Test a single model with a tiny prompt. Returns True if healthy."""
    test_prompt = "Reply with exactly: OK"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model.id,
        "messages": [{"role": "user", "content": test_prompt}],
        "max_tokens": 10,
        "temperature": 0,
    }
    
    try:
        async with session.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                return content == "OK"
            elif resp.status in (404, 429, 500, 502, 503, 504):
                return False
            return False
    except asyncio.TimeoutError:
        return False
    except Exception:
        return False


async def run_health_checks(registry: Registry, max_concurrent: int = 10) -> Dict[str, str]:
    """Run health checks on all free models. Returns dict of degraded model IDs with timestamp."""
    degraded = {}
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat().replace("+00:00", "Z")
    
    # Load existing health cache
    health_cache = {}
    if HEALTH_CACHE_FILE.exists():
        try:
            with open(HEALTH_CACHE_FILE) as f:
                health_cache = json.load(f)
        except Exception:
            pass
    
    # Models to check: all NIM + top 30 OpenRouter + opencode
    models_to_check = (
        registry.nim_models +
        registry.openrouter_models[:30] +
        registry.opencode_models
    )
    
    # Filter out already degraded (within 24h)
    models_to_check = [
        m for m in models_to_check
        if not m.degraded_until or datetime.fromisoformat(m.degraded_until.replace("Z", "+00:00")) < now
    ]
    
    if not models_to_check:
        return {}
    
    print(f"[ModelRegistry] Running health checks on {len(models_to_check)} models...")
    
    # NIM models use NVIDIA API
    nim_key = os.getenv("NVAPI_KEY") or os.getenv("NVIDIA_API_KEY")
    or_key = os.getenv("OPENROUTER_API_KEY")
    
    if not nim_key and not or_key:
        print("[ModelRegistry] No API keys for health checks, skipping")
        return {}
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def check_with_semaphore(model: ModelInfo) -> tuple[str, bool]:
        async with semaphore:
            if model.source == "nim" and nim_key:
                healthy = await health_check_model(session, model, nim_key, "https://integrate.api.nvidia.com/v1")
            elif model.source == "openrouter" and or_key:
                healthy = await health_check_model(session, model, or_key, "https://openrouter.ai/api/v1")
            elif model.source == "opencode":
                # opencode models use OpenRouter endpoint
                healthy = await health_check_model(session, model, or_key or "dummy", "https://openrouter.ai/api/v1")
            else:
                healthy = True  # Can't check, assume healthy
            return model.id, healthy
    
    async with aiohttp.ClientSession() as session:
        tasks = [check_with_semaphore(m) for m in models_to_check]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            continue
        model_id, healthy = result
        if not healthy:
            degraded[model_id] = now_iso
            print(f"[ModelRegistry] ⚠ Model degraded: {model_id}")
        elif model_id in health_cache:
            # Model recovered
            print(f"[ModelRegistry] ✓ Model recovered: {model_id}")
    
    # Save health cache
    with open(HEALTH_CACHE_FILE, "w") as f:
        json.dump(degraded, f, indent=2)
    
    return degraded


def apply_health_degradation(registry: Registry, degraded: Dict[str, str]):
    """Mark degraded models in registry."""
    for model_list in [registry.nim_models, registry.openrouter_models, registry.opencode_models]:
        for m in model_list:
            if m.id in degraded:
                m.degraded_until = degraded[m.id]
    
    # Rebuild fallback chain excluding degraded models
    registry.merged_fallback_chain = build_merged_fallback_chain(registry)


# ─── Main Update Flow ───────────────────────────────────────────────────
def update_registry(registry_dir: Path = REGISTRY_DIR, do_health_checks: bool = False) -> Dict:
    """Main update function - fetch, process, and save."""
    global REGISTRY_DIR, MODEL_REGISTRY_FILE, MODEL_CHANGELOG_FILE, LAST_UPDATE_FILE, HEALTH_CACHE_FILE
    
    # Check for SKIP_HEALTH_CHECKS env var (set by GitHub Actions when NVIDIA key missing)
    skip_health_env = os.getenv("SKIP_HEALTH_CHECKS", "false").lower() == "true"
    if skip_health_env:
        do_health_checks = False
        print("[ModelRegistry] SKIP_HEALTH_CHECKS=true, skipping health checks")
    
    # Update global paths if registry_dir changed
    REGISTRY_DIR = registry_dir
    MODEL_REGISTRY_FILE = REGISTRY_DIR / "model_registry.json"
    MODEL_CHANGELOG_FILE = REGISTRY_DIR / "model_changelog.md"
    LAST_UPDATE_FILE = REGISTRY_DIR / "last_update.txt"
    HEALTH_CACHE_FILE = REGISTRY_DIR / "health_cache.json"
    
    print(f"[ModelRegistry] Using registry directory: {REGISTRY_DIR}")
    
    old_registry = load_existing_registry(registry_dir)
    
    # Fetch from both sources
    print("[ModelRegistry] Fetching OpenRouter models...")
    or_raw = fetch_openrouter_models()
    or_models = process_openrouter_models(or_raw)
    print(f"[ModelRegistry] Found {len(or_models)} free OpenRouter models")
    
    print("[ModelRegistry] Fetching NVIDIA NIM models...")
    nim_raw = fetch_nvidia_nim_models()
    nim_models = process_nvidia_nim_models(nim_raw)
    print(f"[ModelRegistry] Found {len(nim_models)} free NVIDIA NIM models")
    
    opencode_models = get_opencode_models()
    
    # Ensure registry directory exists before logging
    registry_dir.mkdir(parents=True, exist_ok=True)
    
    # Build new registry
    new_registry = Registry(
        nim_models=nim_models,
        openrouter_models=or_models,
        opencode_models=opencode_models,
    )
    new_registry.merged_fallback_chain = build_merged_fallback_chain(new_registry)
    
    # Log changes
    log_changes(old_registry, new_registry)
    
    # Run health checks if requested
    if do_health_checks:
        degraded = asyncio.run(run_health_checks(new_registry))
        if degraded:
            apply_health_degradation(new_registry, degraded)
            print(f"[ModelRegistry] Marked {len(degraded)} models as degraded for 24h")
    
    # Save
    save_registry_atomic(new_registry, registry_dir)
    
    return {
        "success": True,
        "nim_models": len(nim_models),
        "openrouter_free_models": len(or_models),
        "opencode_models": len(opencode_models),
        "total_models": len(nim_models) + len(or_models) + len(opencode_models),
        "fallback_chain_length": len(new_registry.merged_fallback_chain),
        "updated_at": new_registry.metadata["updated_at"],
    }


def is_update_needed(max_age_hours: int = 24) -> bool:
    """Check if registry update is needed (default: daily)."""
    if not LAST_UPDATE_FILE.exists():
        return True
    
    try:
        with open(LAST_UPDATE_FILE) as f:
            last = f.read().strip()
        last_update = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - last_update > timedelta(hours=max_age_hours)
    except Exception:
        return True


def auto_update_if_needed(max_age_hours: int = 24) -> bool:
    """Auto-update registry if needed (called on startup). Default: daily."""
    if is_update_needed(max_age_hours):
        print("[ModelRegistry] Daily update needed, fetching latest models...")
        result = update_registry(run_health_checks=True)
        return result.get("success", False)
    return True


# ─── Public API ─────────────────────────────────────────────────────────
def get_fallback_chain(task_type: str = "general", registry_dir: Path = REGISTRY_DIR) -> List[str]:
    """Get dynamic fallback chain based on current registry."""
    registry = load_existing_registry(registry_dir)
    
    if not registry.merged_fallback_chain:
        # Hardcoded ultimate fallback
        return [
            "nvidia/deepseek-ai/deepseek-v4-flash",
            "nvidia/z-ai/glm-5.2",
            "nvidia/nvidia/nemotron-3-ultra-550b-a55b",
            "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
            "openrouter/poolside/laguna-s-2.1:free",
            "opencode/nemotron-3-ultra-free",
            "gemini-2.5-pro",
        ]
    
    # Filter out degraded models
    now = datetime.now(timezone.utc)
    chain = [
        m for m in registry.merged_fallback_chain
        if not any(
            md.id == m and md.degraded_until and 
            datetime.fromisoformat(md.degraded_until.replace("Z", "+00:00")) > now
            for md in registry.nim_models + registry.openrouter_models + registry.opencode_models
        )
    ]
    
    return chain if chain else get_fallback_chain(task_type, registry_dir)  # Recurse with fallback


def get_reasoning_models(registry_dir: Path = REGISTRY_DIR) -> List[ModelInfo]:
    """Get all free reasoning models from all sources."""
    registry = load_existing_registry(registry_dir)
    all_models = registry.nim_models + registry.openrouter_models + registry.opencode_models
    return [
        m for m in all_models
        if m.has_reasoning or m.category in ("reasoning", "reasoning_flagship")
    ]


def get_coding_models(registry_dir: Path = REGISTRY_DIR) -> List[ModelInfo]:
    """Get all free coding models from all sources."""
    registry = load_existing_registry(registry_dir)
    all_models = registry.nim_models + registry.openrouter_models + registry.opencode_models
    return [m for m in all_models if m.category == "coding"]


def get_long_context_models(min_context: int = 200000, registry_dir: Path = REGISTRY_DIR) -> List[ModelInfo]:
    """Get models with large context windows from all sources."""
    registry = load_existing_registry(registry_dir)
    all_models = registry.nim_models + registry.openrouter_models + registry.opencode_models
    return [m for m in all_models if m.context_length >= min_context]


def get_nvidia_models(registry_dir: Path = REGISTRY_DIR) -> List[ModelInfo]:
    """Get NVIDIA NIM models."""
    registry = load_existing_registry(registry_dir)
    return registry.nim_models


def load_registry(registry_dir: Path = REGISTRY_DIR) -> Registry:
    """Load full registry."""
    return load_existing_registry(registry_dir)


# ─── CLI ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="RoutingMagic Model Registry Updater")
    parser.add_argument("--daily", action="store_true", help="Run daily update (with health checks)")
    parser.add_argument("--output-dir", type=Path, help="Output directory (default: ./registry)")
    parser.add_argument("--no-health-check", action="store_true", help="Skip health checks")
    parser.add_argument("--force", action="store_true", help="Force update even if not needed")
    args = parser.parse_args()
    
    output_dir = args.output_dir or REGISTRY_DIR
    
    if args.daily or args.force:
        run_health = not args.no_health_check and args.daily
        result = update_registry(output_dir, do_health_checks=run_health)
        print(json.dumps(result, indent=2))
    else:
        # Just check if update needed
        if is_update_needed():
            print("Update needed")
        else:
            print("Up to date")


if __name__ == "__main__":
    main()


# Export key functions
__all__ = [
    "update_registry",
    "get_fallback_chain",
    "get_reasoning_models",
    "get_coding_models",
    "get_long_context_models",
    "get_nvidia_models",
    "auto_update_if_needed",
    "load_registry",
    "load_existing_registry",
    "ModelInfo",
    "Registry",
]