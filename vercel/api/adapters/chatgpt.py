#!/usr/bin/env python3
"""
ChatGPT Adapter — OpenAI API /v1/usage endpoint.
Requires OPENAI_API_KEY in ~/.routingmagic/.env
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

# Load API key from ~/.routingmagic/.env
load_dotenv(Path.home() / ".routingmagic" / ".env")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY")

USAGE_DB_PATH = Path.home() / ".routingmagic" / "metrics" / "chatgpt_usage.db"


def init_usage_db():
    USAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(USAGE_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chatgpt_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0.0,
            date_bucket TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cu_timestamp ON chatgpt_usage(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cu_model ON chatgpt_usage(model)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cu_date ON chatgpt_usage(date_bucket)")
    conn.commit()
    conn.close()


def fetch_openai_usage(start_date: str, end_date: str) -> List[Dict]:
    """Fetch usage from OpenAI /v1/usage endpoint."""
    if not OPENAI_API_KEY:
        return []

    url = "https://api.openai.com/v1/usage"
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": 100,
    }
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}

    all_data = []
    while True:
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=30)
            if resp.status_code != 200:
                break
            data = resp.json()
            all_data.extend(data.get("data", []))
            if not data.get("has_more", False):
                break
            # Pagination
            if data.get("last_id"):
                params["after"] = data["last_id"]
            else:
                break
        except Exception:
            break

    return all_data


def sync_chatgpt_usage(days_back: int = 30) -> int:
    """Sync last N days of usage to local DB."""
    init_usage_db()

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)

    usage_data = fetch_openai_usage(start_date.isoformat(), end_date.isoformat())
    if not usage_data:
        return 0

    conn = sqlite3.connect(str(USAGE_DB_PATH))
    saved = 0

    for item in usage_data:
        # OpenAI usage returns: date, model, n_context_tokens_total, n_generated_tokens_total, etc.
        date_str = item.get("date")
        model = item.get("snapshot_id", "unknown")  # May need adjustment
        n_context = item.get("n_context_tokens_total", 0)
        n_generated = item.get("n_generated_tokens_total", 0)

        # Estimate cost (rough)
        cost = 0.0
        if "gpt-4" in model.lower():
            cost = (n_context * 30 + n_generated * 60) / 1_000_000
        elif "gpt-3.5" in model.lower():
            cost = (n_context * 0.5 + n_generated * 1.5) / 1_000_000

        conn.execute("""
            INSERT OR REPLACE INTO chatgpt_usage (timestamp, model, input_tokens, output_tokens, cost_usd, date_bucket)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date_str, model, n_context, n_generated, cost, date_str))
        saved += 1

    conn.commit()
    conn.close()
    return saved


def scan_chatgpt(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan ChatGPT usage from local DB (synced from API)."""
    db = db_path or USAGE_DB_PATH
    if not db.exists() or db.stat().st_size == 0:
        # Try to sync if DB empty
        sync_chatgpt_usage(30)
        if not db.exists() or db.stat().st_size == 0:
            return []

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT timestamp, model, input_tokens, output_tokens, cost_usd
            FROM chatgpt_usage
            WHERE input_tokens + output_tokens > 0
            ORDER BY timestamp
        """).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    results = []
    for r in rows:
        results.append({
            "source": "chatgpt",
            "session_id": f"chatgpt-{r['model']}-{r['timestamp']}",
            "timestamp": r["timestamp"],
            "model": r["model"],
            "input_tokens": r["input_tokens"] or 0,
            "output_tokens": r["output_tokens"] or 0,
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": r["cost_usd"] or 0.0,
            "project": "chatgpt",
            "source_metadata": json.dumps({}),
        })
    return results


if __name__ == "__main__":
    print("Syncing ChatGPT usage...")
    count = sync_chatgpt_usage(30)
    print(f"Synced {count} days")

    rows = scan_chatgpt()
    print(f"Found {len(rows)} ChatGPT usage records")
    for r in rows[:5]:
        print(f"  {r['model']}: {r['input_tokens']} in + {r['output_tokens']} out, ${r['cost']:.4f}")