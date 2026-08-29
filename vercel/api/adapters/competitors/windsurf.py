#!/usr/bin/env python3
"""
Windsurf Adapter — ~/.windsurf/ local database.
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional


WINDSURF_DB_PATHS = [
    Path.home() / ".windsurf" / "state.vscdb",
    Path.home() / ".windsurf" / "User" / "globalStorage" / "state.vscdb",
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


def scan_windsurf(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan Windsurf usage from local VS Code database."""
    paths = [db_path] if db_path else WINDSURF_DB_PATHS

    for path in paths:
        conn = _safe_connect(path)
        if not conn:
            continue

        try:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            table_names = [t["name"] for t in tables]

            if "ItemTable" in table_names:
                rows = conn.execute("""
                    SELECT key, value FROM ItemTable
                    WHERE key LIKE '%codeium%' OR key LIKE '%windsurf%' OR key LIKE '%ai%'
                """).fetchall()

                results = []
                for r in rows:
                    try:
                        data = json.loads(r["value"])
                        if isinstance(data, dict):
                            results.append({
                                "source": "windsurf",
                                "session_id": f"windsurf-{r['key']}",
                                "timestamp": data.get("timestamp", ""),
                                "model": data.get("model", "windsurf"),
                                "input_tokens": data.get("input_tokens", 0),
                                "output_tokens": data.get("output_tokens", 0),
                                "cache_read": 0,
                                "cache_write": 0,
                                "reasoning_tokens": 0,
                                "cost": 0.0,
                                "project": "windsurf",
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
    rows = scan_windsurf()
    print(f"Found {len(rows)} Windsurf usage records")