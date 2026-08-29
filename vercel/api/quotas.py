"""GET /api/quotas - Quota snapshots."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("ROUTINGMAGIC_USAGE_DB", "/tmp/usage_unified.db"))

def handler(request):
    if not DB_PATH.exists():
        return {"error": "Database not found"}, 404

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT provider, model, timestamp, consumed, remaining, limit_value, pct_used,
               window_start, window_end
        FROM quota_snapshots
        WHERE id IN (
            SELECT MAX(id) FROM quota_snapshots GROUP BY provider, model
        )
        ORDER BY provider, model
    """).fetchall()
    conn.close()

    return {
        "snapshots": [dict(r) for r in rows],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }, 200
