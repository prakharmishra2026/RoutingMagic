#!/usr/bin/env python3
"""
DeepSeek Adapter — DeepSeek /usage endpoint.
Requires DEEPSEEK_API_KEY in ~/.routingmagic/.env
"""

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv(Path.home() / ".routingmagic" / ".env")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")

USAGE_DB_PATH = Path.home() / ".routingmagic" / "metrics" / "deepseek_usage.db"


def init_usage_db():
    USAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(USAGE_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS deepseek_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0.0,
            date_bucket TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_du_timestamp ON deepseek_usage(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_du_model ON deepseek_usage(model)")
    conn.commit()
    conn.close()


def fetch_deepseek_usage(start_date: str, end_date: str) -> List[Dict]:
    if not DEEPSEEK_API_KEY:
        return []

    url = "https://api.deepseek.com/usage"
    params = {"start_date": start_date, "end_date": end_date}
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}

    all_data = []
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            all_data = data.get("data", [])
    except Exception:
        pass

    return all_data


def sync_deepseek_usage(days_back: int = 30) -> int:
    init_usage_db()
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)

    usage_data = fetch_deepseek_usage(start_date.isoformat(), end_date.isoformat())
    if not usage_data:
        return 0

    conn = sqlite3.connect(str(USAGE_DB_PATH))
    saved = 0

    for item in usage_data:
        date_str = item.get("date", "")
        model = item.get("model", "deepseek")
        input_tokens = item.get("prompt_tokens", 0)
        output_tokens = item.get("completion_tokens", 0)
        cost = (input_tokens * 0.27 + output_tokens * 1.10) / 1_000_000

        conn.execute("""
            INSERT OR REPLACE INTO deepseek_usage (timestamp, model, input_tokens, output_tokens, cost_usd, date_bucket)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date_str, model, input_tokens, output_tokens, cost, date_str))
        saved += 1

    conn.commit()
    conn.close()
    return saved


def scan_deepseek(db_path: Optional[Path] = None) -> List[Dict]:
    db = db_path or USAGE_DB_PATH
    if not db.exists() or db.stat().st_size == 0:
        sync_deepseek_usage(30)
        if not db.exists() or db.stat().st_size == 0:
            return []

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT timestamp, model, input_tokens, output_tokens, cost_usd
            FROM deepseek_usage
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
            "source": "deepseek",
            "session_id": f"deepseek-{r['model']}-{r['timestamp']}",
            "timestamp": r["timestamp"],
            "model": r["model"],
            "input_tokens": r["input_tokens"] or 0,
            "output_tokens": r["output_tokens"] or 0,
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": r["cost_usd"] or 0.0,
            "project": "deepseek",
            "source_metadata": json.dumps({}),
        })
    return results


if __name__ == "__main__":
    count = sync_deepseek_usage(30)
    print(f"Synced {count} days")

    rows = scan_deepseek()
    print(f"Found {len(rows)} DeepSeek usage records")