#!/usr/bin/env python3
"""
Gemini Adapter — Google AI Studio API.
Requires GEMINI_API_KEY or GOOGLE_API_KEY in ~/.routingmagic/.env
"""

import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Optional

import requests
from dotenv import load_dotenv

# Load API key from ~/.routingmagic/.env
load_dotenv(Path.home() / ".routingmagic" / ".env")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_JULES_API_KEY")

USAGE_DB_PATH = Path.home() / ".routingmagic" / "metrics" / "gemini_usage.db"


def init_usage_db():
    USAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(USAGE_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gemini_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            model TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0.0,
            date_bucket TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gu_timestamp ON gemini_usage(timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gu_model ON gemini_usage(model)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gu_date ON gemini_usage(date_bucket)")
    conn.commit()
    conn.close()


def fetch_gemini_usage() -> List[Dict]:
    """Fetch usage from Google AI Studio / Generative Language API."""
    if not GEMINI_API_KEY:
        return []

    # Google AI Studio usage endpoint (may vary)
    url = "https://generativelanguage.googleapis.com/v1beta/models"
    params = {"key": GEMINI_API_KEY}

    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return []
        data = resp.json()
        # This returns model list, not usage. Usage API may need different endpoint.
        # For now, return empty - can be extended when usage API is confirmed
        return []
    except Exception:
        return []


def sync_gemini_usage(days_back: int = 30) -> int:
    """Sync usage to local DB. Placeholder for when API is available."""
    init_usage_db()
    # TODO: Implement when Google provides usage API
    return 0


def scan_gemini(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan Gemini usage from local DB."""
    db = db_path or USAGE_DB_PATH
    if not db.exists() or db.stat().st_size == 0:
        sync_gemini_usage(30)
        if not db.exists() or db.stat().st_size == 0:
            return []

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        rows = conn.execute("""
            SELECT timestamp, model, input_tokens, output_tokens, cost_usd
            FROM gemini_usage
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
            "source": "gemini",
            "session_id": f"gemini-{r['model']}-{r['timestamp']}",
            "timestamp": r["timestamp"],
            "model": r["model"],
            "input_tokens": r["input_tokens"] or 0,
            "output_tokens": r["output_tokens"] or 0,
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": r["cost_usd"] or 0.0,
            "project": "gemini",
            "source_metadata": json.dumps({}),
        })
    return results


if __name__ == "__main__":
    rows = scan_gemini()
    print(f"Found {len(rows)} Gemini usage records")
    for r in rows[:5]:
        print(f"  {r['model']}: {r['input_tokens']} in + {r['output_tokens']} out, ${r['cost']:.4f}")