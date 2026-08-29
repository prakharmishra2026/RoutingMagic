#!/usr/bin/env python3
"""
Antigravity Adapter — Google Antigravity CLI (Gemini/Claude/GPT-OSS).
No /usage or /credits commands available in this CLI.
Falls back to Google Generative Language API if GEMINI_API_KEY available.
"""

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional


def run_cli_json(cmd: List[str]) -> Optional[Dict]:
    """Run CLI command and parse JSON output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        pass
    return None


def run_cli_text(cmd: List[str]) -> str:
    """Run CLI command and return text output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
        pass
    return ""


def get_gemini_api_key() -> Optional[str]:
    """Get Gemini API key from env or ~/.routingmagic/.env."""
    # Check env var first
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_AI_API_KEY")
    if key:
        return key
    # Check .env file
    env_path = Path.home() / ".routingmagic" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY=") or line.startswith("GOOGLE_AI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def fetch_gemini_usage(api_key: str) -> Optional[Dict]:
    """Fetch usage from Google Generative Language API."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        req = urllib.request.Request(url, headers={"User-Agent": "RoutingMagic/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode())
    except Exception:
        pass
    return None


def scan_antigravity() -> List[Dict]:
    """Scan Antigravity (Google) usage via CLI or API."""
    rows = []

    # Try CLI first (Google Antigravity CLI has no /usage or /credits commands)
    # These will fail gracefully
    usage_json = run_cli_json(["agy", "/usage", "--json"])
    credits_json = run_cli_json(["agy", "/credits", "--json"])

    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now().date()

    # CLI commands don't exist in Google Antigravity CLI, so try API
    api_key = get_gemini_api_key()
    api_data = None
    if api_key:
        api_data = fetch_gemini_usage(api_key)

    if usage_json and isinstance(usage_json, dict):
        # Original plan: CLI JSON output (not available in this CLI)
        models = usage_json.get("models", [])
        for mq in models:
            rows.append({
                "source": "antigravity",
                "session_id": f"ag-{mq.get('model', 'unknown')}-{today}",
                "timestamp": now,
                "model": mq.get("model", "unknown"),
                "input_tokens": mq.get("input_tokens_used", 0),
                "output_tokens": mq.get("output_tokens_used", 0),
                "cache_read": 0,
                "cache_write": 0,
                "reasoning_tokens": 0,
                "cost": 0.0,
                "project": "antigravity",
                "source_metadata": json.dumps({
                    "quota_limit": mq.get("limit"),
                    "quota_remaining": mq.get("remaining"),
                    "refresh_window_hours": 5,
                    "plan": credits_json.get("plan", "ultra") if credits_json else "ultra",
                }),
            })
    elif api_data and isinstance(api_data, dict):
        # Fallback: Google Generative Language API
        # Note: This API doesn't provide per-model usage, only model list
        # Return a placeholder row indicating API is available but no usage data
        rows.append({
            "source": "antigravity",
            "session_id": f"ag-api-{today}",
            "timestamp": now,
            "model": "gemini (API available, no usage data)",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": 0.0,
            "project": "antigravity",
            "source_metadata": json.dumps({
                "note": "Google Generative Language API accessible but no per-model usage endpoint",
                "models_available": len(api_data.get("models", [])) if "models" in api_data else 0,
            }),
        })
    else:
        # No data available
        rows.append({
            "source": "antigravity",
            "session_id": f"ag-unavailable-{today}",
            "timestamp": now,
            "model": "antigravity (no usage data)",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": 0.0,
            "project": "antigravity",
            "source_metadata": json.dumps({
                "note": "Google Antigravity CLI has no /usage or /credits commands; GEMINI_API_KEY not configured or API unavailable",
            }),
        })

    return rows


if __name__ == "__main__":
    rows = scan_antigravity()
    print(f"Found {len(rows)} Antigravity usage records")
    for r in rows:
        print(f"  {r['model']}: {r['input_tokens']} in + {r['output_tokens']} out, cost=${r['cost']:.2f}")