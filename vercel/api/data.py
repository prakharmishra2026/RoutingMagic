"""GET /api/data - Unified dashboard data endpoint."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from routingmagic.db import get_db, init_db
from routingmagic.pricing import calc_cost, is_free

DB_PATH = Path(os.environ.get("ROUTINGMAGIC_USAGE_DB", "/tmp/usage_unified.db"))

def handler(request):
    if not DB_PATH.exists():
        return {"error": "Database not found. Run scan first."}, 404

    conn = get_db()
    init_db(conn)

    # All models for filter
    model_rows = conn.execute("""
        SELECT source, COALESCE(NULLIF(model, ''), 'unknown') as model
        FROM unified_turns
        GROUP BY source, COALESCE(NULLIF(model, ''), 'unknown')
        ORDER BY SUM(input_tokens + output_tokens) DESC
    """).fetchall()
    all_models = [{"source": r["source"], "model": r["model"], "free": is_free(r["model"], r["source"])} for r in model_rows]

    # All sources for filter
    source_rows = conn.execute("""
        SELECT source, COUNT(*) as turns, SUM(input_tokens + output_tokens) as tokens
        FROM unified_turns
        GROUP BY source
        ORDER BY tokens DESC
    """).fetchall()
    sources = [{"source": r["source"], "turns": r["turns"], "tokens": r["tokens"] or 0} for r in source_rows]

    # Daily per-model per-source
    daily_rows = conn.execute("""
        SELECT
            substr(timestamp, 1, 10) as day,
            source,
            COALESCE(NULLIF(model, ''), 'unknown') as model,
            SUM(input_tokens) as input,
            SUM(output_tokens) as output,
            SUM(cache_read) as cache_read,
            SUM(cache_write) as cache_write,
            SUM(reasoning_tokens) as reasoning,
            COUNT(*) as turns
        FROM unified_turns
        GROUP BY day, source, COALESCE(NULLIF(model, ''), 'unknown')
        ORDER BY day, source, model
    """).fetchall()
    daily_by_model = [{
        "day": r["day"], "source": r["source"], "model": r["model"],
        "input": r["input"] or 0, "output": r["output"] or 0,
        "cache_read": r["cache_read"] or 0, "cache_write": r["cache_write"] or 0,
        "reasoning": r["reasoning"] or 0, "turns": r["turns"] or 0,
        "free": is_free(r["model"], r["source"]),
    } for r in daily_rows]

    # All sessions
    session_rows = conn.execute("""
        SELECT
            session_id, source, project, first_timestamp, last_timestamp,
            total_input, total_output, total_cache_read, total_cache_write,
            total_reasoning, model, turn_count, total_cost, topic
        FROM unified_sessions
        ORDER BY last_timestamp DESC
    """).fetchall()
    sessions_all = []
    for r in session_rows:
        try:
            t1 = datetime.fromisoformat(r["first_timestamp"].replace("Z", "+00:00"))
            t2 = datetime.fromisoformat(r["last_timestamp"].replace("Z", "+00:00"))
            duration_min = round((t2 - t1).total_seconds() / 60, 1)
        except Exception:
            duration_min = 0
        model = r["model"] or "unknown"
        source = r["source"]
        inp = r["total_input"] or 0
        out = r["total_output"] or 0
        cr = r["total_cache_read"] or 0
        cw = r["total_cache_write"] or 0
        cost = r["total_cost"] or 0.0
        if cost == 0.0:
            cost = calc_cost(model, inp, out, cr, cw, source)
        free = is_free(model, source)
        sessions_all.append({
            "session_id": r["session_id"],
            "source": source,
            "project": r["project"] or "unknown",
            "topic": r["topic"] or "",
            "last": (r["last_timestamp"] or "")[:16].replace("T", " "),
            "last_date": (r["last_timestamp"] or "")[:10],
            "duration_min": duration_min,
            "model": model,
            "turns": r["turn_count"] or 0,
            "input": inp, "output": out,
            "cache_read": cr, "cache_write": cw,
            "reasoning": r["total_reasoning"] or 0,
            "cost": cost,
            "free": free,
        })

    # Scan state
    scan_state = {}
    for r in conn.execute("SELECT * FROM scan_state").fetchall():
        scan_state[r["source"]] = {"last_scan": r["last_scan"], "row_count": r["row_count"], "status": r["status"]}

    conn.close()

    return {
        "all_models": all_models,
        "sources": sources,
        "daily_by_model": daily_by_model,
        "sessions_all": sessions_all,
        "scan_state": scan_state,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }, 200
