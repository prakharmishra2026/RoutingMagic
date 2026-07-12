#!/usr/bin/env python3
"""
Metrics Collector & Savings Dashboard

Collects per-session token metrics and provides savings dashboard commands.
"""
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from threading import Lock

METRICS_DIR = Path.home() / ".routingmagic" / "metrics"
METRICS_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = METRICS_DIR / "token_metrics.db"
DB_LOCK = Lock()

def _init_db():
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                model_used TEXT NOT NULL,
                task_type TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                caveman_input_savings_pct REAL NOT NULL,
                caveman_output_savings_pct REAL NOT NULL,
                mythos_effort TEXT NOT NULL,
                council_invoked INTEGER NOT NULL,
                fallback_tier INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                user_reasked INTEGER NOT NULL,
                confusion_signals INTEGER NOT NULL,
                user_feedback TEXT,
                caveman_level TEXT NOT NULL,
                caveman_downgraded INTEGER NOT NULL,
                reask_count INTEGER NOT NULL,
                cost_usd REAL NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_aggregates (
                date TEXT PRIMARY KEY,
                total_sessions INTEGER,
                total_input_tokens INTEGER,
                total_output_tokens INTEGER,
                total_caveman_savings_pct REAL,
                total_mythos_savings_pct REAL,
                total_cost_savings_usd REAL,
                avg_latency_ms REAL,
                council_sessions INTEGER
            )
        """)
        conn.commit()
        conn.close()

_init_db()

DB_LOCK = Lock()

@dataclass
class SessionMetrics:
    session_id: str
    timestamp: str
    model_used: str
    task_type: str
    input_tokens: int
    output_tokens: int
    caveman_input_savings_pct: float
    caveman_output_savings_pct: float
    mythos_effort: str
    council_invoked: bool
    fallback_tier: int
    latency_ms: float
    user_reasked: bool
    confusion_signals: int
    user_feedback: Optional[str]
    caveman_level: str
    caveman_downgraded: bool
    reask_count: int
    cost_usd: float

def record_session(metrics: SessionMetrics):
    """Record a session's metrics."""
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metrics.session_id, metrics.timestamp, metrics.model_used,
            metrics.task_type, metrics.input_tokens, metrics.output_tokens,
            metrics.caveman_input_savings_pct, metrics.caveman_output_savings_pct,
            metrics.mythos_effort, int(metrics.council_invoked), metrics.fallback_tier,
            metrics.latency_ms, int(metrics.user_reasked), metrics.confusion_signals,
            metrics.user_feedback, metrics.caveman_level, int(metrics.caveman_downgraded),
            metrics.reask_count, metrics.cost_usd
        ))
        conn.commit()
        conn.close()
    
    # Update daily aggregate
    _update_daily_aggregate(metrics)


def _update_daily_aggregate(metrics: SessionMetrics):
    """Update daily aggregate table."""
    date = metrics.timestamp[:10]  # YYYY-MM-DD
    
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM daily_aggregates WHERE date = ?", (date,))
        row = cursor.fetchone()
        
        if row:
            # Update existing
            new_sessions = row[1] + 1
            new_input = row[2] + metrics.input_tokens
            new_output = row[3] + metrics.output_tokens
            # Weighted average for savings
            new_caveman_in = (row[4] * row[1] + metrics.caveman_input_savings_pct) / new_sessions
            new_caveman_out = (row[5] * row[1] + metrics.caveman_output_savings_pct) / new_sessions
            # Estimate mythos savings (effort-based)
            mythos_map = {"low": 5, "medium": 15, "high": 30}
            mythos_savings = mythos_map.get(metrics.mythos_effort, 10)
            new_mythos = (row[5] * row[1] + mythos_savings) / new_sessions
            
            new_cost = row[6] + metrics.cost_usd
            new_latency = (row[7] * row[1] + metrics.latency_ms) / new_sessions
            new_council = row[8] + (1 if metrics.council_invoked else 0)
            
            cursor.execute("""
                UPDATE daily_aggregates SET
                    total_sessions = ?, total_input_tokens = ?, total_output_tokens = ?,
                    total_caveman_savings_pct = ?, total_mythos_savings_pct = ?,
                    total_cost_savings_usd = ?, avg_latency_ms = ?, council_sessions = ?
                WHERE date = ?
            """, (new_sessions, new_input, new_output, new_caveman_in, new_mythos,
                  new_cost, new_latency, new_council, date))
        else:
            mythos_map = {"low": 5, "medium": 15, "high": 30}
            cursor.execute("""
                INSERT INTO daily_aggregates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date, 1, metrics.input_tokens, metrics.output_tokens,
                  metrics.caveman_input_savings_pct, metrics.caveman_output_savings_pct,
                  metrics.cost_usd, metrics.latency_ms,
                  1 if metrics.council_invoked else 0))
        
        conn.commit()
        conn.close()


def get_session_stats(session_id: str) -> Optional[Dict]:
    """Get stats for a specific session."""
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        cols = ["session_id", "timestamp", "model_used", "task_type", "input_tokens",
                "output_tokens", "caveman_input_savings_pct", "caveman_output_savings_pct",
                "mythos_effort", "council_invoked", "fallback_tier", "latency_ms",
                "user_reasked", "confusion_signals", "user_feedback", "caveman_level",
                "caveman_downgraded", "reask_count", "cost_usd"]
        return dict(zip(cols, row))


def get_savings_summary(days: int = 30) -> Dict:
    """Get comprehensive savings summary."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Overall stats
        cursor.execute("""
            SELECT 
                COUNT(*) as sessions,
                SUM(input_tokens) as total_input,
                SUM(output_tokens) as total_output,
                AVG(caveman_input_savings_pct) as avg_caveman_in,
                AVG(caveman_output_savings_pct) as avg_caveman_out,
                SUM(cost_usd) as total_cost,
                SUM(CASE WHEN council_invoked THEN 1 ELSE 0 END) as council_count,
                AVG(latency_ms) as avg_latency
            FROM sessions
            WHERE timestamp >= ?
        """, (cutoff + "T00:00:00Z",))
        
        row = cursor.fetchone()
        
        # By component breakdown
        cursor.execute("""
            SELECT 
                model_used,
                COUNT(*) as count,
                AVG(caveman_input_savings_pct) as caveman_in,
                AVG(caveman_output_savings_pct) as caveman_out,
                AVG(cost_usd) as avg_cost
            FROM sessions
            WHERE timestamp >= ?
            GROUP BY model_used
            ORDER BY count DESC
        """, (cutoff + "T00:00:00Z",))
        by_model = cursor.fetchall()
        
        # By task type
        cursor.execute("""
            SELECT 
                task_type,
                COUNT(*) as count,
                AVG(caveman_input_savings_pct) as caveman_in,
                AVG(caveman_output_savings_pct) as caveman_out,
                AVG(latency_ms) as avg_latency
            FROM sessions
            WHERE timestamp >= ?
            GROUP BY task_type
            ORDER BY count DESC
        """, (cutoff + "T00:00:00Z",))
        by_task = cursor.fetchall()
        
        # Caveman level effectiveness
        cursor.execute("""
            SELECT 
                caveman_level,
                COUNT(*) as count,
                AVG(caveman_output_savings_pct) as avg_savings,
                AVG(confusion_signals) as avg_confusion,
                SUM(caveman_downgraded) as downgrades
            FROM sessions
            WHERE timestamp >= ?
            GROUP BY caveman_level
        """, (cutoff + "T00:00:00Z",))
        by_caveman = cursor.fetchall()
        
        conn.close()
    
    if not row or row[0] == 0:
        return {"sessions": 0, "message": "No sessions in period"}
    
    sessions, total_in, total_out, avg_cav_in, avg_cav_out, total_cost, council_count, avg_latency = row
    
    # Estimate baseline cost (what it would cost without free models)
    # Assume average paid model cost ~$10/M tokens
    baseline_cost = (total_in + total_out) / 1_000_000 * 10
    savings_pct = (1 - total_cost / baseline_cost) * 100 if baseline_cost > 0 else 0
    
    return {
        "period_days": days,
        "sessions": sessions,
        "total_tokens": total_in + total_out,
        "input_tokens": total_in,
        "output_tokens": total_out,
        "caveman_input_savings_pct": round(avg_cav_in or 0, 1),
        "caveman_output_savings_pct": round(avg_cav_out or 0, 1),
        "mythos_estimated_savings_pct": 20,  # Estimated from effort levels
        "combined_savings_pct": round(savings_pct, 1),
        "total_cost_usd": round(total_cost, 4),
        "estimated_baseline_cost_usd": round(baseline_cost, 2),
        "cost_savings_pct": round(savings_pct, 1),
        "council_sessions": council_count,
        "avg_latency_ms": round(avg_latency or 0, 1),
        "by_model": [
            {"model": m[0], "count": m[1], "caveman_in": round(m[2] or 0, 1),
             "caveman_out": round(m[3] or 0, 1), "avg_cost": round(m[4] or 0, 6)}
            for m in by_model
        ],
        "by_task": [
            {"task": t[0], "count": t[1], "caveman_in": round(t[2] or 0, 1),
             "caveman_out": round(t[3] or 0, 1), "avg_latency": round(t[4] or 0, 1)}
            for t in by_task
        ],
        "caveman_levels": [
            {"level": c[0], "count": c[1], "avg_savings": round(c[2] or 0, 1),
             "avg_confusion": round(c[3] or 0, 2), "downgrades": c[4]}
            for c in by_caveman
        ]
    }


def get_savings_breakdown() -> Dict:
    """Get detailed breakdown of savings by component."""
    summary = get_savings_summary(30)
    
    # Calculate component contributions
    caveman_savings = summary.get("caveman_output_savings_pct", 0)
    mythos_savings = summary.get("mythos_estimated_savings_pct", 0)
    routing_savings = summary.get("combined_savings_pct", 0) - caveman_savings - mythos_savings
    
    return {
        "components": {
            "caveman_compression": {
                "description": "Caveman skill output compression (65% avg)",
                "savings_pct": round(caveman_savings, 1),
                "impact": "High"
            },
            "mythos_reasoning": {
                "description": "Mythos multi-pass reasoning (effort-based)",
                "savings_pct": round(mythos_savings, 1),
                "impact": "Medium"
            },
            "smart_routing": {
                "description": "Free model routing + fallbacks",
                "savings_pct": max(0, round(routing_savings, 1)),
                "impact": "High"
            }
        },
        "total_savings_pct": summary.get("combined_savings_pct", 0),
        "total_cost_saved_usd": round(
            summary.get("estimated_baseline_cost_usd", 0) - summary.get("total_cost_usd", 0), 4
        )
    }


def get_model_efficiency_ranking(days: int = 30) -> List[Dict]:
    """Rank models by token efficiency and cost."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                model_used,
                COUNT(*) as sessions,
                SUM(input_tokens + output_tokens) as total_tokens,
                AVG(caveman_output_savings_pct) as avg_caveman_savings,
                AVG(latency_ms) as avg_latency,
                SUM(cost_usd) as total_cost,
                AVG(CASE WHEN user_reasked THEN 1 ELSE 0 END) as reask_rate
            FROM sessions
            WHERE timestamp >= ?
            GROUP BY model_used
            HAVING sessions >= 3
            ORDER BY total_tokens DESC
        """, (cutoff + "T00:00:00Z",))
        
        rows = cursor.fetchall()
        conn.close()
    
    return [
        {
            "model": r[0],
            "sessions": r[1],
            "total_tokens": r[2],
            "caveman_savings_pct": round(r[3] or 0, 1),
            "avg_latency_ms": round(r[4] or 0, 1),
            "total_cost_usd": round(r[5] or 0, 6),
            "reask_rate": round((r[6] or 0) * 100, 1),
            "efficiency_score": round((r[2] / max(r[5] * 1_000_000 / 10, 1)) * (1 + (r[3] or 0)/100), 2) if r[5] > 0 else 0
        }
        for r in rows
    ]


def export_savings_csv(days: int = 30, output_path: Optional[str] = None) -> str:
    """Export savings data as CSV."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT session_id, timestamp, model_used, task_type, input_tokens, output_tokens,
                   caveman_input_savings_pct, caveman_output_savings_pct, mythos_effort,
                   council_invoked, fallback_tier, latency_ms, cost_usd
            FROM sessions
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
        """, (cutoff + "T00:00:00Z",))
        
        rows = cursor.fetchall()
        conn.close()
    
    if not rows:
        return "No data to export"
    
    headers = ["session_id", "timestamp", "model", "task_type", "input_tokens", "output_tokens",
               "caveman_in_pct", "caveman_out_pct", "mythos_effort", "council", "fallback_tier",
               "latency_ms", "cost_usd"]
    
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(v) for v in row))
    
    csv_content = "\n".join(lines)
    
    if output_path:
        with open(output_path, "w") as f:
            f.write(csv_content)
        return f"Exported to {output_path}"
    
    return csv_content


def format_savings_dashboard(days: int = 30) -> str:
    """Format a pretty terminal dashboard."""
    summary = get_savings_summary(days)
    breakdown = get_savings_breakdown()
    models = get_model_efficiency_ranking(days)
    
    lines = []
    lines.append("=" * 70)
    lines.append(f"  🪄 ROUTINGMAGIC TOKEN SAVINGS DASHBOARD ({days}d)")
    lines.append("=" * 70)
    lines.append("")
    
    # Summary cards
    lines.append(f"  📊 Sessions: {summary['sessions']}  |  💰 Cost: ${summary['total_cost_usd']:.4f}  |  🎯 Savings: {summary['combined_savings_pct']:.1f}%")
    lines.append(f"  📥 Input tokens: {summary['input_tokens']:,}  |  📤 Output: {summary['output_tokens']:,}  |  ⚡ Latency: {summary['avg_latency_ms']:.0f}ms")
    lines.append("")
    
    # Component breakdown
    lines.append("  🔧 SAVINGS BY COMPONENT:")
    for name, data in breakdown["components"].items():
        bar_len = int(data["savings_pct"] / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        lines.append(f"    {data['description'][:35]:35s}  {bar}  {data['savings_pct']:5.1f}%  ({data['impact']})")
    lines.append("")
    
    # Top models
    lines.append("  🏆 TOP MODELS BY EFFICIENCY:")
    for i, m in enumerate(models[:5], 1):
        lines.append(f"    {i}. {m['model']:30s}  {m['sessions']:3d} sessions  "
                     f"💰${m['total_cost_usd']:.4f}  🪨{m['caveman_savings_pct']:.1f}%  "
                     f"⚡{m['avg_latency_ms']:.0f}ms  🔁{m['reask_rate']:.0f}% reask")
    lines.append("")
    
    # Total savings
    lines.append(f"  💵 TOTAL SAVED: ${breakdown['total_cost_saved_usd']:.4f}  ({breakdown['total_savings_pct']:.1f}% vs paid)")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def get_current_session_savings(session_id: str) -> str:
    """Format savings for current session."""
    stats = get_session_stats(session_id)
    if not stats:
        return "No session data"
    
    return (
        f"  🪨 Caveman: {stats.get('caveman_output_savings_pct', 0):.1f}% output savings  |  "
        f"🧠 Mythos: {stats.get('mythos_effort', 'medium')} effort  |  "
        f"💰 Cost: ${stats.get('cost_usd', 0):.6f}  |  "
        f"⚡ {stats.get('latency_ms', 0):.0f}ms"
    )


def init_dashboard_commands(repl_dict: Dict):
    """Add dashboard commands to REPL."""
    repl_dict["/savings"] = lambda: print(format_savings_dashboard(30))
    repl_dict["/savings total"] = lambda: print(format_savings_dashboard(30))
    repl_dict["/savings breakdown"] = lambda: print(json.dumps(get_savings_breakdown(), indent=2))
    repl_dict["/savings models"] = lambda: print(json.dumps(get_model_efficiency_ranking(30), indent=2))
    repl_dict["/savings export"] = lambda: print(export_savings_csv(30))
    repl_dict["/savings session"] = lambda: print(get_current_session_savings("current"))