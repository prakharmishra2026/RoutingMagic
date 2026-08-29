"""GET /api/adapter-status - Adapter discovery status."""
import os
import sqlite3
from pathlib import Path

from routingmagic.db import get_db, init_db

DB_PATH = Path(os.environ.get("ROUTINGMAGIC_USAGE_DB", "/tmp/usage_unified.db"))

def handler(request):
    if not DB_PATH.exists():
        return {}, 200

    conn = get_db()
    init_db(conn)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM adapter_state").fetchall()
    conn.close()
    return {r["name"]: dict(r) for r in rows}, 200
