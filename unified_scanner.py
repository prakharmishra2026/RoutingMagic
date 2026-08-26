"""
unified_scanner.py - Orchestrates all source adapters, writes unified usage DB.

Reads from Claude Code, OpenCode, 9router, Hermes, Codex CLI, and RoutingMagic.
Writes a single unified SQLite database at ~/.routingmagic/metrics/usage_unified.db.

The unified schema adds a 'source' column to the standard Claude dashboard schema,
making it trivial to filter and aggregate across tools.
"""
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict

from dashboard_adapters import scan_all, SOURCE_ORDER, SOURCE_DISPLAY_NAMES

DB_PATH = Path(os.environ.get(
    "ROUTINGMAGIC_USAGE_DB",
    Path.home() / ".routingmagic" / "metrics" / "usage_unified.db"
))


def get_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS unified_turns (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source          TEXT NOT NULL,
            session_id      TEXT NOT NULL,
            timestamp       TEXT,
            model           TEXT,
            input_tokens    INTEGER DEFAULT 0,
            output_tokens   INTEGER DEFAULT 0,
            cache_read      INTEGER DEFAULT 0,
            cache_write     INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            cost            REAL DEFAULT 0.0,
            project         TEXT,
            source_metadata TEXT
        );

        CREATE TABLE IF NOT EXISTS unified_sessions (
            session_id      TEXT PRIMARY KEY,
            source          TEXT NOT NULL,
            project         TEXT,
            first_timestamp TEXT,
            last_timestamp  TEXT,
            model           TEXT,
            total_input     INTEGER DEFAULT 0,
            total_output    INTEGER DEFAULT 0,
            total_cache_read INTEGER DEFAULT 0,
            total_cache_write INTEGER DEFAULT 0,
            total_reasoning INTEGER DEFAULT 0,
            total_cost      REAL DEFAULT 0.0,
            turn_count      INTEGER DEFAULT 0,
            topic           TEXT
        );

        CREATE TABLE IF NOT EXISTS scan_state (
            source      TEXT PRIMARY KEY,
            last_scan   TEXT,
            row_count   INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_ut_source ON unified_turns(source);
        CREATE INDEX IF NOT EXISTS idx_ut_timestamp ON unified_turns(timestamp);
        CREATE INDEX IF NOT EXISTS idx_ut_model ON unified_turns(model);
        CREATE INDEX IF NOT EXISTS idx_us_source ON unified_sessions(source);
    """)
    conn.commit()


def _aggregate_sessions(rows: List[Dict]) -> Dict[str, Dict]:
    """Aggregate turn-level rows into session-level summaries."""
    sessions = {}
    for r in rows:
        sid = f"{r['source']}:{r['session_id']}"
        if sid not in sessions:
            sessions[sid] = {
                "session_id": sid,
                "source": r["source"],
                "project": r.get("project", "unknown"),
                "first_timestamp": r["timestamp"],
                "last_timestamp": r["timestamp"],
                "model": r["model"],
                "total_input": 0,
                "total_output": 0,
                "total_cache_read": 0,
                "total_cache_write": 0,
                "total_reasoning": 0,
                "total_cost": 0.0,
                "turn_count": 0,
                "topic": "",
            }
        s = sessions[sid]
        s["total_input"] += r["input_tokens"]
        s["total_output"] += r["output_tokens"]
        s["total_cache_read"] += r["cache_read"]
        s["total_cache_write"] += r["cache_write"]
        s["total_reasoning"] += r["reasoning_tokens"]
        s["total_cost"] += r["cost"]
        s["turn_count"] += 1

        ts = r.get("timestamp", "")
        if ts and (not s["first_timestamp"] or ts < s["first_timestamp"]):
            s["first_timestamp"] = ts
        if ts and (not s["last_timestamp"] or ts > s["last_timestamp"]):
            s["last_timestamp"] = ts

        # Try to extract topic from metadata
        meta = {}
        try:
            meta = json.loads(r.get("source_metadata", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass
        if not s["topic"]:
            s["topic"] = meta.get("title", "") or meta.get("topic", "")

    return sessions


def upsert_turns(conn: sqlite3.Connection, rows: List[Dict]):
    if not rows:
        return
    conn.executemany("""
        INSERT INTO unified_turns
            (source, session_id, timestamp, model, input_tokens, output_tokens,
             cache_read, cache_write, reasoning_tokens, cost, project, source_metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        (r["source"], r["session_id"], r["timestamp"], r["model"],
         r["input_tokens"], r["output_tokens"], r["cache_read"], r["cache_write"],
         r["reasoning_tokens"], r["cost"], r["project"],
         r.get("source_metadata", "{}"))
        for r in rows
    ])


def upsert_sessions(conn: sqlite3.Connection, sessions: Dict[str, Dict]):
    for s in sessions.values():
        existing = conn.execute(
            "SELECT total_input FROM unified_sessions WHERE session_id = ?",
            (s["session_id"],)
        ).fetchone()

        if existing is None:
            conn.execute("""
                INSERT INTO unified_sessions
                    (session_id, source, project, first_timestamp, last_timestamp,
                     model, total_input, total_output, total_cache_read,
                     total_cache_write, total_reasoning, total_cost, turn_count, topic)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s["session_id"], s["source"], s["project"],
                s["first_timestamp"], s["last_timestamp"], s["model"],
                s["total_input"], s["total_output"], s["total_cache_read"],
                s["total_cache_write"], s["total_reasoning"], s["total_cost"],
                s["turn_count"], s["topic"]
            ))
        else:
            conn.execute("""
                UPDATE unified_sessions SET
                    last_timestamp = MAX(COALESCE(last_timestamp, ''), ?),
                    total_input = total_input + ?,
                    total_output = total_output + ?,
                    total_cache_read = total_cache_read + ?,
                    total_cache_write = total_cache_write + ?,
                    total_reasoning = total_reasoning + ?,
                    total_cost = total_cost + ?,
                    turn_count = turn_count + ?
                WHERE session_id = ?
            """, (
                s["last_timestamp"],
                s["total_input"], s["total_output"],
                s["total_cache_read"], s["total_cache_write"],
                s["total_reasoning"], s["total_cost"],
                s["turn_count"], s["session_id"]
            ))


def scan(sources: Optional[List[str]] = None, verbose: bool = True) -> Dict:
    """Run full scan of all sources and write to unified DB."""
    conn = get_db()
    init_db(conn)

    if verbose:
        print("Scanning all sources...")

    all_rows = scan_all(sources)
    total_rows = 0
    total_sessions = 0

    for source_name, rows in all_rows.items():
        if verbose:
            print(f"  [{source_name}] {len(rows)} turns")

        if rows:
            # For sources with existing data, we need to be smarter about dedup.
            # Simple approach: delete old data for this source and re-insert.
            # This is safe because adapters return ALL rows (not incremental).
            conn.execute("DELETE FROM unified_turns WHERE source = ?", (source_name,))
            conn.execute("DELETE FROM unified_sessions WHERE source LIKE ? || ':%'",
                         (source_name,))

            upsert_turns(conn, rows)
            sessions = _aggregate_sessions(rows)
            upsert_sessions(conn, sessions)

            total_rows += len(rows)
            total_sessions += len(sessions)

            conn.execute("""
                INSERT OR REPLACE INTO scan_state (source, last_scan, row_count)
                VALUES (?, ?, ?)
            """, (
                source_name,
                datetime.now(timezone.utc).isoformat(),
                len(rows),
            ))

        conn.commit()

    # Recompute session totals from actual turns (correctness guarantee)
    if total_rows > 0:
        conn.execute("""
            UPDATE unified_sessions SET
                total_input = COALESCE((
                    SELECT SUM(input_tokens) FROM unified_turns
                    WHERE unified_turns.session_id = unified_sessions.session_id
                      AND unified_turns.source = unified_sessions.source
                ), 0),
                total_output = COALESCE((
                    SELECT SUM(output_tokens) FROM unified_turns
                    WHERE unified_turns.session_id = unified_sessions.session_id
                      AND unified_turns.source = unified_sessions.source
                ), 0),
                total_cache_read = COALESCE((
                    SELECT SUM(cache_read) FROM unified_turns
                    WHERE unified_turns.session_id = unified_sessions.session_id
                      AND unified_turns.source = unified_sessions.source
                ), 0),
                total_cache_write = COALESCE((
                    SELECT SUM(cache_write) FROM unified_turns
                    WHERE unified_turns.session_id = unified_sessions.session_id
                      AND unified_turns.source = unified_sessions.source
                ), 0),
                total_reasoning = COALESCE((
                    SELECT SUM(reasoning_tokens) FROM unified_turns
                    WHERE unified_turns.session_id = unified_sessions.session_id
                      AND unified_turns.source = unified_sessions.source
                ), 0),
                turn_count = COALESCE((
                    SELECT COUNT(*) FROM unified_turns
                    WHERE unified_turns.session_id = unified_sessions.session_id
                      AND unified_turns.source = unified_sessions.source
                ), 0)
        """)
        conn.commit()

    conn.close()

    if verbose:
        print(f"\nScan complete:")
        print(f"  Total turns:    {total_rows}")
        print(f"  Total sessions: {total_sessions}")
        print(f"  DB path:        {DB_PATH}")

    return {"turns": total_rows, "sessions": total_sessions}


if __name__ == "__main__":
    scan()
