#!/usr/bin/env python3
"""
Quota Engine — Computes multi-dimensional quota snapshots from unified DB.
Supports: subscription (rolling window), credits (USD balance), rate_limit (RPM/TPM), custom_cap (self-imposed).
"""

import json
import yaml
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any
from collections import defaultdict


@dataclass
class QuotaSnapshot:
    provider: str
    model: str
    timestamp: str
    consumed: int
    remaining: int
    limit_value: int
    pct_used: float
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    budget_type: Optional[str] = None


@dataclass
class BudgetConfig:
    provider: str
    budget_type: str  # subscription, credits, rate_limit, custom_cap
    config: Dict[str, Any]

    @classmethod
    def from_yaml(cls, provider: str, data: Dict) -> "BudgetConfig":
        return cls(provider=provider, budget_type=data.get("type", "custom_cap"), config=data)


DEFAULT_BUDGETS = {
    "anthropic": {
        "type": "subscription",
        "plan": "max",
        "periodic_tokens": 1000000,
        "refresh_hours": 5,
    },
    "openrouter": {
        "type": "credits",
        "balance_usd": 10.00,
        "auto_refresh": False,
    },
    "nvidia_nim": {
        "type": "rate_limit",
        "rpm": 40,
        "tpm": 200000,
    },
    "openai": {
        "type": "credits",
        "balance_usd": 5.00,
    },
    "google_vertex": {
        "type": "rate_limit",
        "rpm": 60,
        "project_id": "my-project",
    },
    "ollama": {
        "type": "custom_cap",
        "daily_tokens": 1000000,
        "weekly_tokens": 5000000,
    },
    "antigravity": {
        "type": "subscription",
        "plan": "ultra",
        "periodic_tokens": 5000000,
        "refresh_hours": 5,
        "credits_usd": 50.00,
    },
    "chatgpt": {
        "type": "credits",
        "balance_usd": 20.00,
    },
    "gemini": {
        "type": "credits",
        "balance_usd": 10.00,
    },
}

MODEL_LIMITS = {
    "anthropic": {
        "claude-3-5-sonnet": 1000000,
        "claude-3-5-haiku": 1000000,
        "claude-3-opus": 1000000,
    },
    "nvidia_nim": {
        "nemotron-3-ultra-550b": 200000,
        "deepseek-v4-flash": 200000,
        "glm-5.2": 200000,
    },
}

AVG_COST_PER_MILLION = {
    "anthropic": 3.00,
    "openrouter": 0.50,
    "nvidia_nim": 0.00,
    "openai": 5.00,
    "google_vertex": 2.50,
    "antigravity": 0.00,
    "chatgpt": 5.00,
    "gemini": 1.50,
}


class QuotaEngine:
    def __init__(self, db_path: Optional[str] = None, config_path: Optional[str] = None):
        self.db_path = db_path or str(Path.home() / ".routingmagic" / "metrics" / "usage_unified.db")
        self.config_path = config_path or str(Path.home() / ".routingmagic" / "quotas.yaml")
        self.budgets = self._load_budgets()
        self.alert_thresholds = {
            "warning_pct": 80,
            "critical_pct": 90,
            "exhausted_pct": 100,
            "notify_desktop": True,
        }

    def _load_budgets(self) -> Dict[str, BudgetConfig]:
        budgets = DEFAULT_BUDGETS.copy()

        if Path(self.config_path).exists():
            try:
                with open(self.config_path) as f:
                    data = yaml.safe_load(f) or {}
                user_budgets = data.get("budgets", {}).get("providers", {})
                for provider, config in user_budgets.items():
                    budgets[provider] = config
                alerts = data.get("alerts", {})
                self.alert_thresholds.update(alerts)
            except Exception:
                pass

        return {p: BudgetConfig.from_yaml(p, c) for p, c in budgets.items()}

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def compute_all(self) -> List[QuotaSnapshot]:
        snapshots = []

        for provider, budget in self.budgets.items():
            if budget.budget_type == "subscription":
                snapshots.extend(self._compute_subscription(provider, budget))
            elif budget.budget_type == "credits":
                snapshots.extend(self._compute_credits(provider, budget))
            elif budget.budget_type == "rate_limit":
                snapshots.extend(self._compute_rate_limit(provider, budget))
            elif budget.budget_type == "custom_cap":
                snapshots.extend(self._compute_custom_cap(provider, budget))

        return snapshots

    def _get_window_start(self, refresh_hours: int) -> str:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(hours=refresh_hours)
        return window_start.isoformat()

    def _compute_subscription(self, provider: str, budget: BudgetConfig) -> List[QuotaSnapshot]:
        snapshots = []
        refresh_hours = budget.config.get("refresh_hours", 5)
        periodic_tokens = budget.config.get("periodic_tokens", 1000000)
        window_start = self._get_window_start(refresh_hours)

        conn = self._get_db()
        rows = conn.execute("""
            SELECT model, SUM(input_tokens + output_tokens) as used
            FROM unified_turns
            WHERE source = ? AND timestamp >= ?
            GROUP BY model
        """, (provider, window_start)).fetchall()
        conn.close()

        model_limits = MODEL_LIMITS.get(provider, {})

        for row in rows:
            model = row["model"] or "unknown"
            used = row["used"] or 0
            limit = model_limits.get(model, periodic_tokens)
            remaining = max(0, limit - used)
            pct = (used / limit * 100) if limit else 0

            snapshots.append(QuotaSnapshot(
                provider=provider,
                model=model,
                timestamp=datetime.now(timezone.utc).isoformat(),
                consumed=used,
                remaining=remaining,
                limit_value=limit,
                pct_used=pct,
                window_start=window_start,
                window_end=(datetime.fromisoformat(window_start) + timedelta(hours=refresh_hours)).isoformat(),
                budget_type="subscription",
            ))

        return snapshots

    def _compute_credits(self, provider: str, budget: BudgetConfig) -> List[QuotaSnapshot]:
        balance_usd = budget.config.get("balance_usd", 0.0)
        avg_cost = AVG_COST_PER_MILLION.get(provider, 1.0)

        conn = self._get_db()
        row = conn.execute("""
            SELECT SUM(cost) as total_cost FROM unified_turns WHERE source = ?
        """, (provider,)).fetchone()
        conn.close()

        spent_usd = row["total_cost"] or 0.0
        remaining_usd = max(0.0, balance_usd - spent_usd)

        limit_tokens = int(balance_usd * 1_000_000 / avg_cost) if avg_cost else 0
        consumed_tokens = int(spent_usd * 1_000_000 / avg_cost) if avg_cost else 0
        remaining_tokens = int(remaining_usd * 1_000_000 / avg_cost) if avg_cost else 0
        pct = (spent_usd / balance_usd * 100) if balance_usd else 0

        return [QuotaSnapshot(
            provider=provider,
            model=f"{provider} credits",
            timestamp=datetime.now(timezone.utc).isoformat(),
            consumed=consumed_tokens,
            remaining=remaining_tokens,
            limit_value=limit_tokens,
            pct_used=pct,
            budget_type="credits",
        )]

    def _compute_rate_limit(self, provider: str, budget: BudgetConfig) -> List[QuotaSnapshot]:
        rpm = budget.config.get("rpm", 40)
        tpm = budget.config.get("tpm", 200000)

        conn = self._get_db()
        now = datetime.now(timezone.utc)
        minute_ago = (now - timedelta(minutes=1)).isoformat()
        hour_ago = (now - timedelta(hours=1)).isoformat()

        rpm_used = conn.execute("""
            SELECT COUNT(*) as cnt FROM unified_turns
            WHERE source = ? AND timestamp >= ?
        """, (provider, minute_ago)).fetchone()["cnt"] or 0

        tpm_used = conn.execute("""
            SELECT SUM(input_tokens + output_tokens) as tokens FROM unified_turns
            WHERE source = ? AND timestamp >= ?
        """, (provider, hour_ago)).fetchone()["tokens"] or 0
        conn.close()

        snapshots = []

        rpm_remaining = max(0, rpm - rpm_used)
        rpm_pct = (rpm_used / rpm * 100) if rpm else 0
        snapshots.append(QuotaSnapshot(
            provider=provider,
            model="RPM limit",
            timestamp=now.isoformat(),
            consumed=rpm_used,
            remaining=rpm_remaining,
            limit_value=rpm,
            pct_used=rpm_pct,
            budget_type="rate_limit",
        ))

        tpm_remaining = max(0, tpm - tpm_used)
        tpm_pct = (tpm_used / tpm * 100) if tpm else 0
        snapshots.append(QuotaSnapshot(
            provider=provider,
            model="TPM limit",
            timestamp=now.isoformat(),
            consumed=tpm_used,
            remaining=tpm_remaining,
            limit_value=tpm,
            pct_used=tpm_pct,
            budget_type="rate_limit",
        ))

        return snapshots

    def _compute_custom_cap(self, provider: str, budget: BudgetConfig) -> List[QuotaSnapshot]:
        snapshots = []
        daily_tokens = budget.config.get("daily_tokens", 1000000)
        weekly_tokens = budget.config.get("weekly_tokens", 5000000)

        conn = self._get_db()
        now = datetime.now(timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        daily_used = conn.execute("""
            SELECT SUM(input_tokens + output_tokens) as tokens FROM unified_turns
            WHERE source = ? AND timestamp >= ?
        """, (provider, day_start)).fetchone()["tokens"] or 0

        weekly_used = conn.execute("""
            SELECT SUM(input_tokens + output_tokens) as tokens FROM unified_turns
            WHERE source = ? AND timestamp >= ?
        """, (provider, week_start)).fetchone()["tokens"] or 0
        conn.close()

        daily_remaining = max(0, daily_tokens - daily_used)
        daily_pct = (daily_used / daily_tokens * 100) if daily_tokens else 0
        snapshots.append(QuotaSnapshot(
            provider=provider,
            model="daily cap",
            timestamp=now.isoformat(),
            consumed=daily_used,
            remaining=daily_remaining,
            limit_value=daily_tokens,
            pct_used=daily_pct,
            window_start=day_start,
            window_end=(now.replace(hour=23, minute=59, second=59)).isoformat(),
            budget_type="custom_cap",
        ))

        weekly_remaining = max(0, weekly_tokens - weekly_used)
        weekly_pct = (weekly_used / weekly_tokens * 100) if weekly_tokens else 0
        snapshots.append(QuotaSnapshot(
            provider=provider,
            model="weekly cap",
            timestamp=now.isoformat(),
            consumed=weekly_used,
            remaining=weekly_remaining,
            limit_value=weekly_tokens,
            pct_used=weekly_pct,
            window_start=week_start,
            window_end=(now + timedelta(days=6-now.weekday())).replace(hour=23, minute=59, second=59).isoformat(),
            budget_type="custom_cap",
        ))

        return snapshots

    def save_snapshots(self, snapshots: List[QuotaSnapshot]):
        conn = self._get_db()
        for snap in snapshots:
            conn.execute("""
                INSERT INTO quota_snapshots
                (provider, model, timestamp, consumed, remaining, limit_value, pct_used, window_start, window_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snap.provider, snap.model, snap.timestamp,
                snap.consumed, snap.remaining, snap.limit_value, snap.pct_used,
                snap.window_start, snap.window_end,
            ))
        conn.commit()
        conn.close()

    def check_alerts(self, snapshots: List[QuotaSnapshot]) -> List[Dict]:
        alerts = []
        for snap in snapshots:
            level = None
            if snap.pct_used >= self.alert_thresholds["exhausted_pct"]:
                level = "EXHAUSTED"
            elif snap.pct_used >= self.alert_thresholds["critical_pct"]:
                level = "CRITICAL"
            elif snap.pct_used >= self.alert_thresholds["warning_pct"]:
                level = "WARNING"

            if level:
                msg = self._format_alert(snap, level)
                alerts.append({
                    "provider": snap.provider,
                    "model": snap.model,
                    "level": level,
                    "message": msg,
                    "pct_used": snap.pct_used,
                })
        return alerts

    def _format_alert(self, snap: QuotaSnapshot, level: str) -> str:
        icons = {"WARNING": "🟡", "CRITICAL": "🟠", "EXHAUSTED": "🔴"}
        icon = icons.get(level, "⚠️")
        return f"{icon} {snap.provider} {snap.model} at {snap.pct_used:.0f}% used ({snap.remaining:,} remaining)"

    def save_alerts(self, alerts: List[Dict]):
        if not alerts:
            return
        conn = self._get_db()
        now = datetime.now(timezone.utc).isoformat()
        for alert in alerts:
            conn.execute("""
                INSERT INTO budget_alerts
                (provider, model, timestamp, level, message, pct_used)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                alert["provider"], alert["model"], now,
                alert["level"], alert["message"], alert["pct_used"],
            ))
        conn.commit()
        conn.close()

    def get_unacknowledged_alerts(self) -> List[Dict]:
        conn = self._get_db()
        rows = conn.execute("""
            SELECT * FROM budget_alerts WHERE acknowledged = 0 ORDER BY timestamp DESC
        """).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def acknowledge_alert(self, alert_id: int):
        conn = self._get_db()
        conn.execute("UPDATE budget_alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
        conn.commit()
        conn.close()

    def create_default_config(self):
        """Create default quota config YAML if not exists."""
        config = {
            "budgets": {
                "monthly_usd": 50.00,
                "daily_tokens": 2000000,
                "providers": DEFAULT_BUDGETS,
            },
            "alerts": self.alert_thresholds,
        }
        Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)


if __name__ == "__main__":
    engine = QuotaEngine()
    engine.create_default_config()
    print(f"Created default config at {engine.config_path}")

    snapshots = engine.compute_all()
    print(f"\nComputed {len(snapshots)} quota snapshots:")
    for snap in snapshots:
        bar = "█" * int(snap.pct_used / 10) + "░" * (10 - int(snap.pct_used / 10))
        print(f"  {snap.provider:15} {snap.model:20} {snap.consumed:>10,} / {snap.limit_value:<10,} {bar} {snap.pct_used:5.1f}%")

    alerts = engine.check_alerts(snapshots)
    if alerts:
        print("\n⚠️  ALERTS:")
        for alert in alerts:
            print(f"  {alert['message']}")
    else:
        print("\n✅ No alerts")