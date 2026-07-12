#!/usr/bin/env python3
"""
Model Registry Auto-Updater

Weekly fetches OpenRouter model registry, updates:
- Free model list with reasoning support
- NVIDIA NIM model mappings
- Fallback chains
- Model capability metadata
"""
import os
import json
import urllib.request
import ssl
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from typing import Any

REGISTRY_DIR = Path.home() / ".routingmagic" / "registry"
REGISTRY_DIR.mkdir(parents=True, exist_ok=True)

MODEL_REGISTRY_FILE = REGISTRY_DIR / "model_registry.json"
MODEL_CHANGELOG_FILE = REGISTRY_DIR / "model_changelog.md"
LAST_UPDATE_FILE = REGISTRY_DIR / "last_update.txt"

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_PRICING_URL = "https://openrouter.ai/api/v1/models?include_pricing=true"

# Minimum criteria for free models
MIN_CONTEXT_LENGTH = 8000
REQUIRED_PARAMS = ["temperature", "max_tokens"]


def fetch_openrouter_models() -> List[Dict]:
    """Fetch live model data from OpenRouter."""
    try:
        req = urllib.request.Request(
            OPENROUTER_PRICING_URL,
            headers={"User-Agent": "RoutingMagic/1.0"}
        )
        # Use default SSL context
        context = ssl.create_default_context()
        with urllib.request.urlopen(req, context=context, timeout=30) as response:
            data = json.loads(response.read().decode())
            return data.get("data", [])
    except Exception as e:
        print(f"[ModelRegistry] Failed to fetch OpenRouter models: {e}")
        return []


def is_free_model(model: Dict) -> bool:
    """Check if model is free (prompt and completion pricing = 0)."""
    pricing = model.get("pricing", {})
    try:
        prompt = float(pricing.get("prompt", "0"))
        completion = float(pricing.get("completion", "0"))
        return prompt == 0 and completion == 0
    except (ValueError, TypeError):
        return False


def has_reasoning(model: Dict) -> bool:
    """Check if model supports reasoning tokens."""
    params = model.get("supported_parameters", [])
    return "reasoning" in params


def get_model_score(model: Dict) -> float:
    """Score model for routing priority."""
    score = 0.0
    
    # Context length (normalized to 1M)
    ctx = model.get("context_length", 0)
    score += min(ctx / 1_000_000, 1.0) * 10
    
    # Free model bonus
    if is_free_model(model):
        score += 20
    
    # Reasoning support
    if has_reasoning(model):
        score += 15
    
    # Provider diversity (more providers = more reliable)
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
    
    # Coding specialists
    if "coder" in model_id or "code" in model_id:
        return "coding"
    
    # Large context
    if model.get("context_length", 0) >= 500000:
        return "long_context"
    
    # Vision/multimodal
    if "vl" in model_id or "vision" in model_id or "omni" in model_id:
        return "vision"
    
    # Agentic/tool use
    if has_reasoning({"supported_parameters": model.get("supported_parameters", [])}):
        return "agentic"
    
    return "general"


def fetch_and_process_models() -> Dict:
    """Fetch and process models from OpenRouter."""
    print("[ModelRegistry] Fetching models from OpenRouter...")
    raw_models = fetch_openrouter_models()
    
    if not raw_models:
        return {"error": "Failed to fetch models"}
    
    processed = {
        "free_models": [],
        "reasoning_models": [],
        "coding_models": [],
        "long_context_models": [],
        "vision_models": [],
        "agentic_models": [],
        "general_models": [],
        "all_free_models": [],
        "metadata": {
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "total_models": len(raw_models),
            "free_count": 0
        }
    }
    
    for model in raw_models:
        if not is_free_model(model):
            continue
        
        processed["metadata"]["free_count"] += 1
        model_id = model.get("id", "")
        
        # Basic info
        model_info = {
            "id": model_id,
            "name": model.get("name", ""),
            "context_length": model.get("context_length", 0),
            "providers": model.get("providers", []),
            "provider_count": len(model.get("providers", [])),
            "has_reasoning": has_reasoning(model),
            "supported_parameters": model.get("supported_parameters", []),
            "created": model.get("created", 0),
            "score": get_model_score(model),
            "category": categorize_model(model)
        }
        
        processed["all_free_models"].append(model_info)
        
        # Categorize
        cat = model_info["category"]
        if cat == "reasoning" or cat == "reasoning_flagship":
            processed["reasoning_models"].append(model_info)
        elif cat == "coding":
            processed["coding_models"].append(model_info)
        elif cat == "long_context":
            processed["long_context_models"].append(model_info)
        elif cat == "vision":
            processed["vision_models"].append(model_info)
        elif cat == "agentic":
            processed["agentic_models"].append(model_info)
        else:
            processed["general_models"].append(model_info)
        
        # Always add to free models
        processed["free_models"].append(model_info)
    
    # Sort each category by score
    for key in ["free_models", "reasoning_models", "coding_models", 
                "long_context_models", "vision_models", "agentic_models", "general_models"]:
        processed[key].sort(key=lambda x: x["score"], reverse=True)
    
    print(f"[ModelRegistry] Processed {processed['metadata']['free_count']} free models")
    return processed


def load_existing_registry() -> Dict:
    """Load existing registry if exists."""
    if MODEL_REGISTRY_FILE.exists():
        try:
            with open(MODEL_REGISTRY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_registry(registry: Dict):
    """Save registry to file."""
    with open(MODEL_REGISTRY_FILE, "w") as f:
        json.dump(registry, f, indent=2)
    
    # Update last update timestamp
    with open(LAST_UPDATE_FILE, "w") as f:
        f.write(datetime.utcnow().isoformat() + "Z")


def log_changes(old: Dict, new: Dict):
    """Log model changes to changelog."""
    changes = []
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    old_models = {m["id"]: m for m in old.get("all_free_models", [])}
    new_models = {m["id"]: m for m in new.get("all_free_models", [])}
    
    # New models
    for mid in set(new_models.keys()) - set(old_models.keys()):
        m = new_models[mid]
        changes.append(f"  ➕ **Added**: {mid} ({m['category']}, score: {m['score']:.1f})")
    
    # Removed models
    for mid in set(old_models.keys()) - set(new_models.keys()):
        m = old_models[mid]
        changes.append(f"  ➖ **Removed**: {mid} ({m['category']})")
    
    # Score changes
    for mid in set(old_models.keys()) & set(new_models.keys()):
        old_score = old_models[mid]["score"]
        new_score = new_models[mid]["score"]
        if abs(old_score - new_score) > 5:
            direction = "⬆️" if new_score > old_score else "⬇️"
            changes.append(f"  {direction} **Score change**: {mid} ({old_score:.1f} → {new_score:.1f})")
    
    if changes:
        with open(MODEL_CHANGELOG_FILE, "a") as f:
            f.write(f"\n## {timestamp}\n")
            f.write("\n".join(changes) + "\n")
        print(f"[ModelRegistry] Logged {len(changes)} changes")


def update_registry() -> Dict:
    """Main update function - fetch, process, and save."""
    old_registry = load_existing_registry()
    new_registry = fetch_and_process_models()
    
    if "error" in new_registry:
        return {"success": False, "error": new_registry["error"]}
    
    log_changes(old_registry, new_registry)
    save_registry(new_registry)
    
    return {
        "success": True,
        "free_models": new_registry["metadata"]["free_count"],
        "categories": {k: len(v) for k, v in new_registry.items() if k != "metadata"},
        "updated_at": new_registry["metadata"]["fetched_at"]
    }


def get_fallback_chain(task_type: str) -> List[str]:
    """Get dynamic fallback chain based on current registry."""
    registry = load_existing_registry()
    models = registry.get("free_models", [])
    
    if not models:
        # Hardcoded fallback
        return [
            "google/gemma-4-31b-it:free",
            "nvidia/nemotron-3-super-120b-a12b:free",
            "openai/gpt-oss-120b:free",
            "qwen/qwen3-coder:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "gemini-2.5-pro"
        ]
    
    # Filter by category based on task type
    if task_type == "coding":
        candidates = [m for m in models if m["category"] == "coding"]
        if not candidates:
            candidates = [m for m in models if m["category"] == "general"]
    elif task_type == "reasoning":
        candidates = [m for m in models if m["category"] in ("reasoning", "reasoning_flagship")]
        if not candidates:
            candidates = [m for m in models if m["has_reasoning"]]
    elif task_type == "long_context":
        candidates = [m for m in models if m["category"] == "long_context"]
        if not candidates:
            candidates = [m for m in models if m["context_length"] >= 200000]
    elif task_type == "agentic":
        candidates = [m for m in models if m["category"] == "agentic"]
        if not candidates:
            candidates = [m for m in models if m["category"] == "general"]
    else:
        candidates = [m for m in models if m["category"] == "general"]
    
    # Sort by score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    # Return top 6 model IDs
    return [m["id"] for m in candidates[:6]]


def get_reasoning_models() -> List[Dict]:
    """Get all free reasoning models."""
    registry = load_existing_registry()
    return [
        m for m in registry.get("free_models", [])
        if m["has_reasoning"] or m["category"] in ("reasoning", "reasoning_flagship")
    ]


def get_coding_models() -> List[Dict]:
    """Get all free coding models."""
    registry = load_existing_registry()
    return [m for m in registry.get("free_models", []) if m["category"] == "coding"]


def get_long_context_models(min_context: int = 200000) -> List[Dict]:
    """Get models with large context windows."""
    registry = load_existing_registry()
    return [m for m in registry.get("free_models", []) if m["context_length"] >= min_context]


def get_nvidia_models() -> List[Dict]:
    """Get NVIDIA NIM models (may require API key)."""
    registry = load_existing_registry()
    return [m for m in registry.get("free_models", []) if "nvidia" in m["id"]]


def is_update_needed(max_age_hours: int = 168) -> bool:
    """Check if registry update is needed (default: weekly)."""
    if not LAST_UPDATE_FILE.exists():
        return True
    
    try:
        with open(LAST_UPDATE_FILE) as f:
            last = f.read().strip()
        last_update = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return datetime.utcnow() - last_update > timedelta(hours=max_age_hours)
    except Exception:
        return True


def auto_update_if_needed() -> bool:
    """Auto-update registry if needed (called on startup)."""
    if is_update_needed():
        print("[ModelRegistry] Weekly update needed, fetching latest models...")
        result = update_registry()
        return result.get("success", False)
    return True


# Initialize on import
auto_update_if_needed()


# Export key functions
__all__ = [
    "update_registry",
    "get_fallback_chain",
    "get_reasoning_models",
    "get_coding_models",
    "get_long_context_models",
    "get_nvidia_models",
    "auto_update_if_needed",
    "load_existing_registry",
]