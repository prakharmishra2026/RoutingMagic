"""GET /api/budget - Budget status from quotas.yaml."""
import json
import os
import sqlite3
import yaml
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("ROUTINGMAGIC_USAGE_DB", "/tmp/usage_unified.db"))
QUOTAS_PATH = Path(os.environ.get("ROUTINGMAGIC_QUOTAS_PATH", "/tmp/quotas.yaml"))

def _load_budget_config():
    defaults = {"monthly_usd": 50.00, "daily_tokens": 2000000}
    if not QUOTAS_PATH.exists():
        return defaults
    try:
        with open(QUOTAS_PATH) as f:
            data = yaml.safe_load(f) or {}
        budgets = data.get("budgets", {})
        monthly = budgets.get("monthly_usd", defaults["monthly_usd"])
        daily = budgets.get("daily_tokens", defaults["daily_tokens"])
        if not isinstance(monthly, (int, float)) or monthly <= 0:
            monthly = defaults["monthly_usd"]
        if not isinstance(daily, int) or daily <= 0:
            daily = defaults["daily_tokens"]
        return {"monthly_usd": float(monthly), "daily_tokens": int(daily)}
    except Exception:
        return defaults

def handler(request):
    if not DB_PATH.exists():
        return {"error": "Database not found"}, 404

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    monthly_cost = conn.execute("SELECT COALESCE(SUM(cost), 0) as total FROM unified_turns WHERE timestamp >= ?", (month_start,)).fetchone()["total"]

    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    daily_tokens = conn.execute("SELECT COALESCE(SUM(input_tokens + output_tokens), 0) as total FROM unified_turns WHERE timestamp >= ?", (day_start,)).fetchone()["total"]

    conn.close()

    budget_cfg = _load_budget_config()
    monthly_budget = budget_cfg["monthly_usd"]
    daily_cap = budget_cfg["daily_tokens"]

    return {
        "monthly": {
            "budget": monthly_budget,
            "spent": monthly_cost,
            "remaining": max(0, monthly_budget - monthly_cost),
            "pct": (monthly_cost / monthly_budget * 100) if monthly_budget else 0,
        },
        "daily": {
            "cap": daily_cap,
            "used": daily_tokens,
            "remaining": max(0, daily_cap - daily_tokens),
            "pct": (daily_tokens / daily_cap * 100) if daily_cap else 0,
        },
    }, 200
