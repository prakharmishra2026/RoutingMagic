"""Database utilities for Vercel deployment."""
import os
import sqlite3
from pathlib import Path

# In Vercel, use /tmp for writable storage
DB_PATH = Path(os.environ.get("ROUTINGMAGIC_USAGE_DB", "/tmp/usage_unified.db"))

def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn):
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
            row_count   INTEGER DEFAULT 0,
            status      TEXT DEFAULT 'ok'
        );
        CREATE TABLE IF NOT EXISTS adapter_state (
            name        TEXT PRIMARY KEY,
            state       TEXT,
            last_seen   TEXT,
            last_shallow TEXT,
            cli_ok      INTEGER,
            api_ok      INTEGER,
            paths_found TEXT,
            error_msg   TEXT
        );
        CREATE TABLE IF NOT EXISTS quota_budgets (
            provider    TEXT PRIMARY KEY,
            budget_type TEXT,
            config_json TEXT,
            updated_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS quota_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            provider    TEXT,
            model       TEXT,
            timestamp   TEXT,
            consumed    INTEGER,
            remaining   INTEGER,
            limit_value INTEGER,
            pct_used    REAL,
            window_start TEXT,
            window_end   TEXT
        );
        CREATE TABLE IF NOT EXISTS budget_alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            provider    TEXT,
            model       TEXT,
            timestamp   TEXT,
            level       TEXT,
            message     TEXT,
            pct_used    REAL,
            acknowledged INTEGER DEFAULT 0
        );
    """)
    conn.commit()
