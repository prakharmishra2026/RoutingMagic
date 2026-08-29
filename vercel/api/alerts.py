"""GET /api/alerts - Unacknowledged budget alerts."""
import os
import sqlite3
from pathlib import Path

DB_PATH = Path(os.environ.get("ROUTINGMAGIC_USAGE_DB", "/tmp/usage_unified.db"))

def handler(request):
    if not DB_PATH.exists():
        return [], 200

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM budget_alerts WHERE acknowledged = 0 ORDER BY timestamp DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows], 200
