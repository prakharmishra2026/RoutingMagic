#!/usr/bin/env python3
"""
Antigravity Adapter — Parses `agy /usage --json` and `agy /credits --json`.
Falls back to TUI text parsing if JSON not available.
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any


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


def parse_antigravity_tui(text: str) -> List[Dict]:
    """
    Parse Antigravity TUI text output for /usage.
    Expected format (inferred):
    ┌─────────────────┬──────────────┬──────────────┬──────────────┐
    │ Model           │ Input Tokens │ Output Tokens│ Remaining    │
    ├─────────────────┼──────────────┼──────────────┼──────────────┤
    │ gemini-2.5-pro  │ 1,234,567    │ 2,345,678    │ 3,456,789    │
    │ gpt-4o          │ 567,890      │ 678,901      │ 4,321,098    │
    └─────────────────┴──────────────┴──────────────┴──────────────┘
    """
    rows = []
    lines = text.strip().split("\n")

    # Find table rows (skip header/separator lines)
    in_table = False
    for line in lines:
        if "Model" in line and "Input" in line and "Output" in line:
            in_table = True
            continue
        if in_table and ("┌" in line or "└" in line or "├" in line or "┤" in line or "│" not in line):
            continue
        if in_table and "│" in line:
            parts = [p.strip() for p in line.split("│")]
            if len(parts) >= 4:
                model = parts[1].strip()
                input_tokens = parse_number(parts[2])
                output_tokens = parse_number(parts[3])
                remaining = parse_number(parts[4]) if len(parts) > 4 else 0
                if model and model.lower() != "model":
                    rows.append({
                        "model": model,
                        "input_tokens_used": input_tokens,
                        "output_tokens_used": output_tokens,
                        "limit": input_tokens + output_tokens + remaining,
                        "remaining": remaining,
                    })

    return rows


def parse_number(s: str) -> int:
    """Parse number with commas (e.g., '1,234,567')."""
    try:
        return int(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return 0


def parse_credits_tui(text: str) -> Dict[str, float]:
    """
    Parse Antigravity TUI text output for /credits.
    Expected format (inferred):
    ┌─────────────────┬──────────────┐
    │ Plan            │ Ultra        │
    │ Credits Total   │ $100.00      │
    │ Credits Used    │ $45.00       │
    │ Credits Remaining│ $55.00      │
    └─────────────────┴──────────────┘
    """
    result = {"plan": "ultra", "total_usd": 100.0, "spent_usd": 0.0, "remaining_usd": 100.0}

    for line in text.split("\n"):
        line = line.strip()
        if "Plan" in line and ("Ultra" in line or "Pro" in line or "Free" in line):
            if "Ultra" in line:
                result["plan"] = "ultra"
            elif "Pro" in line:
                result["plan"] = "pro"
            elif "Free" in line:
                result["plan"] = "free"
        elif "Total" in line and "$" in line:
            result["total_usd"] = parse_currency(line)
        elif "Used" in line and "$" in line:
            result["spent_usd"] = parse_currency(line)
        elif "Remaining" in line and "$" in line:
            result["remaining_usd"] = parse_currency(line)

    return result


def parse_currency(s: str) -> float:
    """Parse currency string like '$45.00'."""
    try:
        match = re.search(r"\$([\d,]+\.?\d*)", s)
        if match:
            return float(match.group(1).replace(",", ""))
    except (ValueError, AttributeError):
        pass
    return 0.0


def scan_antigravity() -> List[Dict]:
    """Scan Antigravity usage via CLI."""
    rows = []

    # Try JSON first
    usage_json = run_cli_json(["agy", "/usage", "--json"])
    credits_json = run_cli_json(["agy", "/credits", "--json"])

    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now().date()

    if usage_json and isinstance(usage_json, dict):
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
    else:
        # Fallback: TUI parsing
        usage_text = run_cli_text(["agy", "/usage"])
        if usage_text:
            parsed = parse_antigravity_tui(usage_text)
            for mq in parsed:
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
                        "plan": "ultra",
                    }),
                })

    # Add G1 Credits as separate row
    if credits_json and isinstance(credits_json, dict):
        rows.append({
            "source": "antigravity",
            "session_id": f"ag-credits-{today}",
            "timestamp": now,
            "model": "G1 Credits (overage)",
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": credits_json.get("spent_usd", 0.0),
            "project": "antigravity",
            "source_metadata": json.dumps({
                "credits_total": credits_json.get("total_usd", 0.0),
                "credits_remaining": credits_json.get("remaining_usd", 0.0),
                "credits_spent": credits_json.get("spent_usd", 0.0),
                "plan": credits_json.get("plan", "ultra"),
            }),
        })
    else:
        # TUI fallback for credits
        credits_text = run_cli_text(["agy", "/credits"])
        if credits_text:
            parsed = parse_credits_tui(credits_text)
            rows.append({
                "source": "antigravity",
                "session_id": f"ag-credits-{today}",
                "timestamp": now,
                "model": "G1 Credits (overage)",
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_write": 0,
                "reasoning_tokens": 0,
                "cost": parsed.get("spent_usd", 0.0),
                "project": "antigravity",
                "source_metadata": json.dumps({
                    "credits_total": parsed.get("total_usd", 0.0),
                    "credits_remaining": parsed.get("remaining_usd", 0.0),
                    "credits_spent": parsed.get("spent_usd", 0.0),
                    "plan": parsed.get("plan", "ultra"),
                }),
            })

    return rows


if __name__ == "__main__":
    rows = scan_antigravity()
    print(f"Found {len(rows)} Antigravity usage records")
    for r in rows:
        print(f"  {r['model']}: {r['input_tokens']} in + {r['output_tokens']} out, cost=${r['cost']:.2f}")