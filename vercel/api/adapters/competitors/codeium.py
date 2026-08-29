#!/usr/bin/env python3
"""
Codeium Adapter — ~/.codeium/ local database.
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional


CODEIUM_DB_PATHS = [
    Path.home() / ".codeium" / "state.db",
    Path.home() / ".codeium" / "usage.db",
]


def _safe_connect(db_path: Path) -> Optional[sqlite3.Connection]:
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def scan_codeium(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan Codeium usage from local database."""
    paths = [db_path] if db_path else CODEIUM_DB_PATHS

    for path in paths:
        conn = _safe_connect(path)
        if not conn:
            continue

        try:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [t["name"] for t in tables]

            for table in ["usage", "completions", "sessions", "events"]:
                if table in table_names:
                    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                    results = []
                    for r in rows:
                        try:
                            row_dict = dict(r)
                            results.append({
                                "source": "codeium",
                                "session_id": f"codeium-{row_dict.get('id', '')}",
                                "timestamp": row_dict.get("timestamp", ""),
                                "model": row_dict.get("model", "codeium"),
                                "input_tokens": row_dict.get("input_tokens", row_dict.get("prompt_tokens", 0)),
                                "output_tokens": row_dict.get("output_tokens", row_dict.get("completion_tokens", 0)),
                                "cache_read": 0,
                                "cache_write": 0,
                                "reasoning_tokens": 0,
                                "cost": 0.0,
                                "project": "codeium",
                                "source_metadata": json.dumps(row_dict),
                            })
                        except Exception:
                            continue
                    if results:
                        return results

        except Exception:
            pass
        finally:
            conn.close()

    return []


if __name__ == "__main__":
    rows = scan_codeium()
    print(f"Found {len(rows)} Codeium usage records")