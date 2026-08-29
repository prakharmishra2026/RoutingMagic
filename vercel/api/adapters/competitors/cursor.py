#!/usr/bin/env python3
"""
Cursor Adapter — ~/.cursor/ local database.
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional


CURSOR_DB_PATHS = [
    Path.home() / ".cursor" / "state.vscdb",
    Path.home() / ".cursor" / "User" / "globalStorage" / "state.vscdb",
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


def scan_cursor(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan Cursor usage from local VS Code database."""
    paths = [db_path] if db_path else CURSOR_DB_PATHS

    for path in paths:
        conn = _safe_connect(path)
        if not conn:
            continue

        try:
            # Cursor uses VS Code's storage - look for relevant tables
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [t["name"] for t in tables]

            # Try to find AI usage data
            # This is speculative - actual schema depends on Cursor version
            if "ItemTable" in table_names:
                rows = conn.execute("""
                    SELECT key, value FROM ItemTable
                    WHERE key LIKE '%copilot%' OR key LIKE '%ai%' OR key LIKE '%usage%'
                """).fetchall()

                results = []
                for r in rows:
                    try:
                        data = json.loads(r["value"])
                        if isinstance(data, dict) and "tokens" in str(data).lower():
                            results.append({
                                "source": "cursor",
                                "session_id": f"cursor-{r['key']}",
                                "timestamp": data.get("timestamp", ""),
                                "model": data.get("model", "cursor"),
                                "input_tokens": data.get("input_tokens", 0),
                                "output_tokens": data.get("output_tokens", 0),
                                "cache_read": 0,
                                "cache_write": 0,
                                "reasoning_tokens": 0,
                                "cost": 0.0,
                                "project": "cursor",
                                "source_metadata": json.dumps(data),
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
    rows = scan_cursor()
    print(f"Found {len(rows)} Cursor usage records")