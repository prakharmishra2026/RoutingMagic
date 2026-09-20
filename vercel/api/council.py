"""POST /api/council - Model Council: run 3 free models in parallel for deliberation."""
import json
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from openai import OpenAI

try:  # keep the audit working even if the maintenance module is unavailable
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import council_audit  # type: ignore
except Exception:  # pragma: no cover - defensive
    council_audit = None

# Council roster re-probed live 2026-09-20 with a planted-bug audit task (see
# LESSONS L-208/L-215 in the Investogram repo). Each member below returned a
# clean numbered findings list, found the planted defects, and did not ramble.
#
# ROOT CAUSE of the old roster's unreliability: reasoning models spent their
# whole `max_tokens` budget on internal reasoning and returned EMPTY content
# (or leaked "Here's a thinking process..." into the answer). Disabling
# reasoning output fixes both, so every call now sends
# extra_body={"reasoning": {"enabled": False}}.
#
# Probe results (reasoning disabled, 1200-token cap):
#   nvidia/nemotron-3-ultra-550b-a55b:free   5.8s  7 key defects, numbered
#   inclusionai/ling-3.0-flash-vl:free       8.4s  6-7 key defects, numbered
#   nex-agi/nex-n2.5-pro:free               16.4s  4 key defects, numbered
#   poolside/laguna-s-2.1:free               4.3s  5 key defects, numbered
# Dropped: nvidia/nemotron-3-super-120b-a12b (NIM 503s / empty content),
#   nvidia/nemotron-3.5-lightning:free (usable but 135s), nex-n2.5-mini (empty).
COUNCIL_MODELS = [
    ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    ("openrouter", "inclusionai/ling-3.0-flash-vl:free"),
    ("openrouter", "nex-agi/nex-n2.5-pro:free"),
    ("openrouter", "poolside/laguna-s-2.1:free"),
]

# An audit that takes 4 minutes is still cheaper than a missed defect; the old
# 25s ceiling was the second cause of "council failed" (L-208).
COUNCIL_TIMEOUT_SECONDS = 240.0
COUNCIL_MAX_TOKENS = 8000

# Minimum number of ACTIVE members the maintenance system will not drop below.
MIN_ACTIVE_COUNCIL = 3


def load_active_roster() -> List[Tuple[str, str]]:
    """Return active (provider, model) members from the maintenance registry.

    Falls back to the hard-coded COUNCIL_MODELS list if the registry module or
    file is unreadable. This function MUST NOT raise: an audit is never blocked
    by registry trouble.
    """
    if council_audit is not None:
        try:
            registry = council_audit.load_registry()
            roster = council_audit.roster_for_council(registry)
            if roster:
                return roster
        except Exception:
            pass
        try:
            registry, _ = council_audit.try_load_registry()
            roster = council_audit.roster_for_council(registry)
            if roster:
                return roster
        except Exception:
            pass
    return list(COUNCIL_MODELS)


def _record_council_run(run_id: str, results: List[Dict]) -> None:
    """Best-effort strike accounting. Never raises into the audit path."""
    if council_audit is None:
        return
    try:
        council_audit.record_council_results(run_id, results)
    except Exception:
        pass


def get_clients() -> Dict[str, OpenAI]:
    """Initialize OpenAI clients for different providers."""
    clients = {}
    
    nv_key = os.environ.get("NVAPI_KEY")
    if nv_key:
        clients["nvidia"] = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=nv_key,
            max_retries=0,
        )
    
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if or_key:
        clients["openrouter"] = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=or_key,
            max_retries=0,
        )
    
    return clients

async def run_single_model(
    client: OpenAI, model: str, prompt: str, timeout: float = COUNCIL_TIMEOUT_SECONDS
) -> Dict:
    """Run a single model and return result.

    Reasoning output is disabled: with it on, reasoning models burn the token
    budget thinking and return empty content, which read as a "successful"
    member contributing nothing. Empty content is now an explicit failure.
    """
    try:
        loop = asyncio.get_event_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=COUNCIL_MAX_TOKENS,
                extra_body={"reasoning": {"enabled": False}},
            )),
            timeout=timeout
        )
        content = response.choices[0].message.content or ""
        if not content.strip():
            return {"model": model, "success": False, "error": "empty content", "content": ""}
        return {
            "model": model,
            "success": True,
            "content": content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            } if response.usage else {"prompt_tokens": 0, "completion_tokens": 0}
        }
    except asyncio.TimeoutError:
        return {"model": model, "success": False, "error": "timeout", "content": ""}
    except Exception as e:
        return {"model": model, "success": False, "error": str(e), "content": ""}

async def run_council(prompt: str) -> Dict:
    """Run the Model Council with the active free-model roster."""
    clients = get_clients()
    if not clients:
        return {"error": "No API keys configured", "results": []}

    roster = load_active_roster()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]

    tasks = []
    for provider, model in roster:
        if provider in clients:
            tasks.append(run_single_model(clients[provider], model, prompt))
    
    if not tasks:
        return {"error": "No available models for configured providers", "results": []}
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed = []
    for r in results:
        if isinstance(r, Exception):
            processed.append({"success": False, "error": str(r), "content": ""})
        else:
            processed.append(r)

    _record_council_run(run_id, processed)
    
    successful = [r for r in processed if r.get("success")]
    synthesis = ""
    if successful:
        synthesis = "## Model Council Deliberation\n\n"
        for r in successful:
            synthesis += f"### {r['model']}\n{r['content']}\n\n---\n\n"
        if len(successful) > 1:
            synthesis += "### Synthesis\n"
            synthesis += "The council members provided diverse perspectives. Key agreements and disagreements are noted above."
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
        "members": len(tasks),
        "successful": len(successful),
        "results": processed,
        "synthesis": synthesis,
    }

def handler(request):
    """Handle POST /api/council with JSON body: {prompt: string}."""
    try:
        if request.method != "POST":
            return {"error": "POST required"}, 405
        
        body = request.get_json() if hasattr(request, 'get_json') else json.loads(request.body.decode())
        prompt = body.get("prompt", "")
        
        if not prompt:
            return {"error": "prompt required"}, 400
        
        result = asyncio.run(run_council(prompt))
        return result, 200
        
    except Exception as e:
        return {"error": str(e)}, 500
