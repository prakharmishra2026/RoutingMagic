"""Unified scanner for Vercel - minimal version for scanning."""
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict

DB_PATH = Path(os.environ.get("ROUTINGMAGIC_USAGE_DB", "/tmp/usage_unified.db"))

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS unified_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            session_id TEXT NOT NULL,
            timestamp TEXT,
            model TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read INTEGER DEFAULT 0,
            cache_write INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0,
            project TEXT,
            source_metadata TEXT
        );
        CREATE TABLE IF NOT EXISTS unified_sessions (
            session_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            project TEXT,
            first_timestamp TEXT,
            last_timestamp TEXT,
            model TEXT,
            total_input INTEGER DEFAULT 0,
            total_output INTEGER DEFAULT 0,
            total_cache_read INTEGER DEFAULT 0,
            total_cache_write INTEGER DEFAULT 0,
            total_reasoning INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0.0,
            turn_count INTEGER DEFAULT 0,
            topic TEXT
        );
        CREATE TABLE IF NOT EXISTS scan_state (
            source TEXT PRIMARY KEY,
            last_scan TEXT,
            row_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ok'
        );
        CREATE TABLE IF NOT EXISTS adapter_state (
            name TEXT PRIMARY KEY,
            state TEXT,
            last_seen TEXT,
            last_shallow TEXT,
            cli_ok INTEGER,
            api_ok INTEGER,
            paths_found TEXT,
            error_msg TEXT
        );
        CREATE TABLE IF NOT EXISTS quota_budgets (
            provider TEXT PRIMARY KEY,
            budget_type TEXT,
            config_json TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS quota_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT, model TEXT, timestamp TEXT,
            consumed INTEGER, remaining INTEGER, limit_value INTEGER,
            pct_used REAL, window_start TEXT, window_end TEXT
        );
        CREATE TABLE IF NOT EXISTS budget_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT, model TEXT, timestamp TEXT,
            level TEXT, message TEXT, pct_used REAL,
            acknowledged INTEGER DEFAULT 0
        );
    """)
    conn.commit()

def upsert_turns(conn, rows):
    if not rows: return
    conn.executemany("""
        INSERT INTO unified_turns (source, session_id, timestamp, model, input_tokens, output_tokens,
             cache_read, cache_write, reasoning_tokens, cost, project, source_metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(r["source"], f"{r['source']}:{r['session_id']}", r["timestamp"], r["model"],
         r["input_tokens"], r["output_tokens"], r["cache_read"], r["cache_write"],
         r["reasoning_tokens"], r["cost"], r["project"], r.get("source_metadata", "{}")) for r in rows])

def scan(sources=None, verbose=True):
    from dashboard_adapters import scan_all
    conn = get_db()
    init_db(conn)
    
    all_rows = scan_all(sources)
    total_rows = 0
    total_sessions = 0

    for source_name, rows in all_rows.items():
        if verbose: print(f"  [{source_name}] {len(rows)} turns")
        conn.execute("DELETE FROM unified_turns WHERE source = ?", (source_name,))
        conn.execute("DELETE FROM unified_sessions WHERE source LIKE ? || ':%'", (source_name,))
        
        if rows:
            upsert_turns(conn, rows)
            sessions = _aggregate_sessions(rows)
            upsert_sessions(conn, sessions)
            total_rows += len(rows)
            total_sessions += len(sessions)
            status = "ok"
        else:
            status = "empty"
        
        conn.execute("INSERT OR REPLACE INTO scan_state (source, last_scan, row_count, status) VALUES (?, ?, ?, ?)",
                     (source_name, datetime.now(timezone.utc).isoformat(), len(rows), status))
        conn.commit()

    conn.close()
    if verbose:
        print(f"Scan complete: {total_rows} turns, {total_sessions} sessions")
    return {"turns": total_rows, "sessions": total_sessions}

def _aggregate_sessions(rows):
    sessions = {}
    for r in rows:
        sid = f"{r['source']}:{r['session_id']}"
        if sid not in sessions:
            sessions[sid] = {"session_id": sid, "source": r["source"], "project": r.get("project","unknown"),
                "first_timestamp": r["timestamp"], "last_timestamp": r["timestamp"], "model": r["model"],
                "total_input": 0, "total_output": 0, "total_cache_read": 0, "total_cache_write": 0,
                "total_reasoning": 0, "total_cost": 0.0, "turn_count": 0, "topic": ""}
        s = sessions[sid]
        s["total_input"] += r["input_tokens"]
        s["total_output"] += r["output_tokens"]
        s["total_cache_read"] += r["cache_read"]
        s["total_cache_write"] += r["cache_write"]
        s["total_reasoning"] += r["reasoning_tokens"]
        s["total_cost"] += r["cost"]
        s["turn_count"] += 1
        ts = r.get("timestamp", "")
        if ts and (not s["first_timestamp"] or ts < s["first_timestamp"]): s["first_timestamp"] = ts
        if ts and (not s["last_timestamp"] or ts > s["last_timestamp"]): s["last_timestamp"] = ts
        meta = {}
        try: meta = json.loads(r.get("source_metadata", "{}"))
        except: pass
        if not s["topic"]: s["topic"] = meta.get("title", "") or meta.get("topic", "")
    return sessions

def upsert_sessions(conn, sessions):
    for s in sessions.values():
        existing = conn.execute("SELECT total_input FROM unified_sessions WHERE session_id = ?", (s["session_id"],)).fetchone()
        if existing is None:
            conn.execute("""INSERT INTO unified_sessions
                (session_id, source, project, first_timestamp, last_timestamp, model,
                 total_input, total_output, total_cache_read, total_cache_write,
                 total_reasoning, total_cost, turn_count, topic)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s["session_id"], s["source"], s["project"], s["first_timestamp"], s["last_timestamp"], s["model"],
                 s["total_input"], s["total_output"], s["total_cache_read"], s["total_cache_write"],
                 s["total_reasoning"], s["total_cost"], s["turn_count"], s["topic"]))
        else:
            conn.execute("""UPDATE unified_sessions SET
                last_timestamp = MAX(COALESCE(last_timestamp, ''), ?),
                total_input = total_input + ?, total_output = total_output + ?,
                total_cache_read = total_cache_read + ?, total_cache_write = total_cache_write + ?,
                total_reasoning = total_reasoning + ?, total_cost = total_cost + ?,
                turn_count = turn_count + ? WHERE session_id = ?""",
                (s["last_timestamp"], s["total_input"], s["total_output"], s["total_cache_read"],
                 s["total_cache_write"], s["total_reasoning"], s["total_cost"], s["turn_count"], s["session_id"]))

if __name__ == "__main__":
    scan()
