#!/usr/bin/env python3
"""
Ollama Adapter — Reads from Ollama proxy DB (ollama_usage.db).
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional


PROXY_DB_PATH = Path.home() / ".routingmagic" / "metrics" / "ollama_usage.db"


def _safe_connect(db_path: Path) -> Optional[sqlite3.Connection]:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def scan_ollama(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan Ollama proxy usage database."""
    db = db_path or PROXY_DB_PATH
    conn = _safe_connect(db)
    if not conn:
        return []

    try:
        rows = conn.execute("""
            SELECT
                timestamp,
                model,
                prompt_tokens,
                completion_tokens,
                total_duration,
                request_json,
                response_json
            FROM ollama_usage
            WHERE prompt_tokens + completion_tokens > 0
            ORDER BY timestamp
        """).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    results = []
    for r in rows:
        results.append({
            "source": "ollama",
            "session_id": f"ollama-{r['model']}-{r['timestamp'][:10]}",
            "timestamp": r["timestamp"],
            "model": r["model"] or "unknown",
            "input_tokens": r["prompt_tokens"] or 0,
            "output_tokens": r["completion_tokens"] or 0,
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": 0.0,
            "project": "ollama",
            "source_metadata": json.dumps({
                "total_duration_ms": r["total_duration"] or 0,
            }),
        })
    return results


if __name__ == "__main__":
    import sys
    rows = scan_ollama()
    print(f"Found {len(rows)} Ollama usage records")
    for r in rows[:5]:
        print(f"  {r['model']}: {r['input_tokens']} in + {r['output_tokens']} out")