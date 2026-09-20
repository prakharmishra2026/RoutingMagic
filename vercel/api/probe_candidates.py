#!/usr/bin/env python3
"""Plant-bug probe for OpenRouter free models.

Discovers free models from the OpenRouter ``/models`` endpoint (pricing 0),
runs a fixed benchmark task containing three KNOWN planted defects, scores the
answers, and appends results to ``council_probe_history.json``.

Planted defects (never listed in the prompt — the prompt only carries the buggy
code, precisely so a model cannot simply echo a supplied defect list):

1. no allocation cap
2. truthiness treating 0 as missing
3. bare except returning True

Scoring per model:

* ``found_planted_defects`` — 0..3, keyword-matched against each defect
* ``numbered_output``       — answer uses a numbered/structured list
* ``no_reasoning_leak``     — no raw chain-of-thought leakage in the answer
* ``latency``               — seconds for the completion

``score = found*3 + numbered*1 + no_reasoning_leak*1 - min(latency,60)/30``
``passed = found >= 2 and numbered_output and no_reasoning_leak``

Every request sends ``extra_body={"reasoning": {"enabled": False}}`` so
reasoning models return content instead of burning the token budget thinking.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

_HERE = Path(__file__).resolve().parent
HISTORY_PATH = _HERE / "council_probe_history.json"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

PROBE_MAX_TOKENS = 1200
PROBE_TIMEOUT_SECONDS = 90.0

# ── benchmark task (code only; defects deliberately NOT enumerated) ─────────

PLANTED_CODE = '''\
def allocate_funds(user_requested, portfolio_value):
    amount = user_requested
    return execute_trade(amount)


def get_balance(account):
    balance = account.balance
    if balance:
        return balance
    return 0


def save_record(record, db):
    try:
        db.insert(record)
    except:
        return True
    return True
'''

BENCHMARK_PROMPT = (
    "Review the following Python code for correctness and safety defects.\n"
    "Return ONLY a numbered list of concrete defects. Do not restate the code, "
    "do not explain your thinking, and do not describe the file's purpose.\n\n"
    "```python\n"
    f"{PLANTED_CODE}"
    "```\n"
)

DEFECT_KEYWORDS: Dict[str, Sequence[str]] = {
    "no_allocation_cap": (
        "cap", "limit", "maximum", "max amount", "upper bound", "unbounded",
        "no check", "not validated", "not validate", "no validation", "exceeds",
        "bounds", "boundary",
    ),
    "zero_truthiness": (
        "truthy", "truthiness", "falsy", "falsey", "zero", "0 is", "0 as",
        "treats 0", "consider 0", "missing when", "if balance", "valid value",
        "zero balance",
    ),
    "bare_except_true": (
        "bare except", "bare `except`", "except clause", "catch-all", "catch all",
        "swallow", "suppress", "return true", "returns true", "silently",
        "hides", "mask", "always reports success", "reports success",
    ),
}

REASONING_LEAK_MARKERS = (
    "thinking process", "let me think", "here's my thinking", "here is my thinking",
    "i'm thinking", "i am thinking", "chain of thought", "my reasoning",
    "reasoning:", "let me analyze", "let me review", "first, i need to",
    "the user wants", "we need to review", "okay, let's", "let's break",
)


# ── scoring ─────────────────────────────────────────────────────────────────

def find_planted_defects(content: str) -> List[str]:
    text = (content or "").lower()
    found = []
    for defect, keywords in DEFECT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            found.append(defect)
    return found


def has_numbered_output(content: str) -> bool:
    text = content or ""
    numbered = re.findall(r"(?m)^\s*(?:\d+[\.\):]|[-*]\s+)", text)
    return len(numbered) >= 2


def has_reasoning_leak(content: str) -> bool:
    text = (content or "").lower()
    return any(marker in text for marker in REASONING_LEAK_MARKERS)


def score_output(content: str, latency: float) -> Dict[str, Any]:
    found = find_planted_defects(content)
    numbered = has_numbered_output(content)
    no_leak = not has_reasoning_leak(content)
    raw = len(found) * 3 + int(numbered) + int(no_leak) - min(max(latency, 0.0), 60.0) / 30.0
    return {
        "found_planted_defects": len(found),
        "defects_found": found,
        "numbered_output": numbered,
        "no_reasoning_leak": no_leak,
        "latency": round(float(latency), 3),
        "score": round(raw, 3),
        "passed": len(found) >= 2 and numbered and no_leak,
    }


# ── discovery ───────────────────────────────────────────────────────────────

def _is_zero_price(pricing: Any) -> bool:
    if not isinstance(pricing, dict):
        return False
    for key in ("prompt", "completion"):
        try:
            if float(pricing.get(key, -1)) != 0.0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def fetch_free_models(timeout: float = 30.0) -> List[Dict[str, str]]:
    """Return free OpenRouter models discovered from /models (pricing 0)."""
    req = urllib.request.Request(OPENROUTER_MODELS_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed HTTPS host
        payload = json.loads(resp.read().decode("utf-8"))
    data = payload.get("data", payload if isinstance(payload, list) else [])
    out: List[Dict[str, str]] = []
    for model in data:
        if not isinstance(model, dict) or not model.get("id"):
            continue
        if not _is_zero_price(model.get("pricing")):
            continue
        out.append({
            "id": model["id"],
            "provider": "openrouter",
            "name": model.get("name", model["id"]),
        })
    return out


# ── probing ─────────────────────────────────────────────────────────────────

def _make_client():
    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key, max_retries=0)


def probe_model(
    client: Any,
    model: str,
    timeout: float = PROBE_TIMEOUT_SECONDS,
    prompt: str = BENCHMARK_PROMPT,
) -> Dict[str, Any]:
    started = time.monotonic()
    base = {"model": model, "provider": "openrouter"}
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=PROBE_MAX_TOKENS,
            timeout=timeout,
            extra_body={"reasoning": {"enabled": False}},
        )
        latency = time.monotonic() - started
        content = response.choices[0].message.content or ""
        if not content.strip():
            return {**base, **score_output("", latency), "error": "empty_content",
                    "passed": False}
        return {**base, **score_output(content, latency)}
    except Exception as exc:
        latency = time.monotonic() - started
        return {**base, **score_output("", latency), "passed": False,
                "error": f"{type(exc).__name__}: {exc}"}


def _load_history(path: Path) -> List[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_history(records: List[Dict[str, Any]], path: Optional[Path] = None) -> None:
    target = Path(path) if path else HISTORY_PATH
    history = _load_history(target)
    history.extend(records)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2)
        fh.write("\n")


def probe_openrouter_candidates(
    limit: Optional[int] = None,
    api_key: Optional[str] = None,
    models: Optional[Sequence[Dict[str, str]]] = None,
    client_factory: Optional[Callable[[], Any]] = None,
    save: bool = True,
    log: Callable[[str], None] = print,
) -> List[Dict[str, Any]]:
    """Probe free candidates and return scored records (best score first)."""
    if api_key and not os.environ.get("OPENROUTER_API_KEY"):
        os.environ["OPENROUTER_API_KEY"] = api_key
    candidates = list(models) if models is not None else fetch_free_models()
    if limit is not None:
        candidates = candidates[:limit]
    if client_factory is None:
        client_factory = _make_client
    client = client_factory()

    records: List[Dict[str, Any]] = []
    for candidate in candidates:
        model_id = candidate["id"]
        record = probe_model(client, model_id)
        record["probe_score"] = {
            k: record[k]
            for k in ("found_planted_defects", "defects_found", "numbered_output",
                      "no_reasoning_leak", "latency", "score", "passed")
        }
        records.append(record)
        log(f"PROBE {model_id} score={record['score']} passed={record['passed']}")

    records.sort(key=lambda r: r["score"], reverse=True)
    if save and records:
        try:
            save_history([{**r, "probed_at": datetime.now(timezone.utc).isoformat()}
                          for r in records])
        except OSError as exc:
            log(f"PROBE_HISTORY_SAVE_FAILED {exc}")
    return records


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Probe OpenRouter free models")
    parser.add_argument("--limit", type=int, default=None, help="max candidates")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args(argv)
    records = probe_openrouter_candidates(limit=args.limit, save=not args.no_save)
    print(json.dumps(records, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())