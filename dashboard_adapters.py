"""
dashboard_adapters.py - Source-specific SQLite adapters for unified usage dashboard.

Each adapter reads from an AI tool's native database and returns rows in a
common format that the unified scanner can merge.

Common row schema:
{
    "source": str,           # "claude", "opencode", "hermes", "codex", "routingmagic"
    "session_id": str,
    "timestamp": str,        # ISO8601
    "model": str,
    "input_tokens": int,
    "output_tokens": int,
    "cache_read": int,
    "cache_write": int,
    "reasoning_tokens": int,
    "cost": float,
    "project": str,
    "source_metadata": str,  # JSON blob for source-specific fields
}
"""
import json
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional


def _safe_connect(db_path: Path) -> Optional[sqlite3.Connection]:
    """Open a SQLite DB if it exists and is non-empty."""
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _ts_to_iso(ts) -> str:
    """Convert various timestamp formats to ISO8601 string."""
    if ts is None:
        return ""
    if isinstance(ts, str):
        return ts
    if isinstance(ts, (int, float)):
        # Could be Unix epoch (seconds) or millisecond epoch
        if ts > 1e12:
            ts = ts / 1000
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except (OSError, ValueError):
            return str(ts)
    return str(ts)


def _project_from_path(path: str) -> str:
    """Derive a friendly project name from a path."""
    if not path:
        return "unknown"
    parts = path.replace("\\", "/").rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:])
    return parts[-1] if parts else "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
#  Claude Code — ~/.claude/usage.db (turns table)
# ═══════════════════════════════════════════════════════════════════════════════

def scan_claude_jsonl(projects_dir: Optional[Path] = None) -> List[Dict]:
    """Read Claude Code session logs (~/.claude/projects/*/*.jsonl) directly.

    usage.db is populated by the external `claude-usage` ingester, which can fall
    days behind without anything noticing. The JSONL logs are written live by
    Claude Code itself, so they are the fresher source. Field shape matches
    ~/.claude/token-report.py.
    """
    base = Path(projects_dir) if projects_dir else Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return []

    rows: List[Dict] = []
    for jf in base.glob("*/*.jsonl"):
        try:
            fh = jf.open(errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("type") != "assistant":
                    continue
                msg = o.get("message") or {}
                u = msg.get("usage")
                if not isinstance(u, dict):
                    continue
                inp = u.get("input_tokens", 0) or 0
                out = u.get("output_tokens", 0) or 0
                cr = u.get("cache_read_input_tokens", 0) or 0
                cw = u.get("cache_creation_input_tokens", 0) or 0
                if inp + out + cr + cw == 0:
                    continue
                details = u.get("output_tokens_details") or {}
                rows.append({
                    "source": "claude",
                    "session_id": o.get("sessionId") or jf.stem,
                    "timestamp": o.get("timestamp") or "",
                    "model": msg.get("model") or "unknown",
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cache_read": cr,
                    "cache_write": cw,
                    "reasoning_tokens": details.get("thinking_tokens", 0) or 0,
                    "cost": 0.0,
                    "project": _project_from_path(o.get("cwd") or ""),
                    "source_metadata": json.dumps({"gitBranch": o.get("gitBranch") or ""}),
                })
    return rows


def scan_claude(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan Claude Code usage — prefers the live JSONL logs, falls back to usage.db."""
    if db_path is None:
        live = scan_claude_jsonl()
        if live:
            return live

    db = db_path or Path.home() / ".claude" / "usage.db"
    conn = _safe_connect(db)
    if not conn:
        return []

    try:
        rows = conn.execute("""
            SELECT
                t.session_id,
                t.timestamp,
                t.model,
                t.input_tokens,
                t.output_tokens,
                t.cache_read_tokens,
                t.cache_creation_tokens,
                t.tool_name,
                t.cwd,
                s.project_name,
                s.first_timestamp,
                s.last_timestamp,
                s.topic
            FROM turns t
            LEFT JOIN sessions s ON t.session_id = s.session_id
            WHERE t.input_tokens + t.output_tokens > 0
        """).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    results = []
    for r in rows:
        results.append({
            "source": "claude",
            "session_id": r["session_id"] or "",
            "timestamp": _ts_to_iso(r["timestamp"]),
            "model": r["model"] or "unknown",
            "input_tokens": r["input_tokens"] or 0,
            "output_tokens": r["output_tokens"] or 0,
            "cache_read": r["cache_read_tokens"] or 0,
            "cache_write": r["cache_creation_tokens"] or 0,
            "reasoning_tokens": 0,
            "cost": 0.0,
            "project": r["project_name"] or _project_from_path(r["cwd"] or ""),
            "source_metadata": json.dumps({
                "topic": r["topic"] or "",
                "tool_name": r["tool_name"] or "",
            }),
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  OpenCode — ~/.local/share/opencode/opencode.db (session table)
# ═══════════════════════════════════════════════════════════════════════════════

def scan_opencode(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan OpenCode session table."""
    db = db_path or Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    conn = _safe_connect(db)
    if not conn:
        return []

    try:
        rows = conn.execute("""
            SELECT
                id,
                title,
                model,
                directory,
                cost,
                tokens_input,
                tokens_output,
                tokens_reasoning,
                tokens_cache_read,
                tokens_cache_write,
                time_created,
                time_updated
            FROM session
            WHERE tokens_input + tokens_output > 0
        """).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    results = []
    for r in rows:
        # model is stored as JSON string like '{"id":"big-pickle","providerID":"opencode"}'
        model_raw = r["model"] or "unknown"
        try:
            model_obj = json.loads(model_raw)
            model_name = model_obj.get("id", model_raw)
            provider = model_obj.get("providerID", "")
            if provider and provider not in model_name:
                model_name = f"{provider}/{model_name}"
        except (json.JSONDecodeError, TypeError):
            model_name = model_raw

        results.append({
            "source": "opencode",
            "session_id": r["id"] or "",
            "timestamp": _ts_to_iso(r["time_created"]),
            "model": model_name,
            "input_tokens": r["tokens_input"] or 0,
            "output_tokens": r["tokens_output"] or 0,
            "cache_read": r["tokens_cache_read"] or 0,
            "cache_write": r["tokens_cache_write"] or 0,
            "reasoning_tokens": r["tokens_reasoning"] or 0,
            "cost": r["cost"] or 0.0,
            "project": _project_from_path(r["directory"] or ""),
            "source_metadata": json.dumps({
                "title": r["title"] or "",
            }),
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  Hermes — ~/.hermes/state.db (sessions table)
# ═══════════════════════════════════════════════════════════════════════════════

def scan_hermes(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan Hermes sessions table."""
    db = db_path or Path.home() / ".hermes" / "state.db"
    conn = _safe_connect(db)
    if not conn:
        return []

    try:
        rows = conn.execute("""
            SELECT
                id,
                source,
                model,
                title,
                cwd,
                input_tokens,
                output_tokens,
                cache_read_tokens,
                cache_write_tokens,
                reasoning_tokens,
                estimated_cost_usd,
                actual_cost_usd,
                started_at,
                ended_at
            FROM sessions
            WHERE input_tokens + output_tokens > 0
        """).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    results = []
    for r in rows:
        cost = r["actual_cost_usd"] or r["estimated_cost_usd"] or 0.0
        results.append({
            "source": "hermes",
            "session_id": r["id"] or "",
            "timestamp": _ts_to_iso(r["started_at"]),
            "model": r["model"] or "unknown",
            "input_tokens": r["input_tokens"] or 0,
            "output_tokens": r["output_tokens"] or 0,
            "cache_read": r["cache_read_tokens"] or 0,
            "cache_write": r["cache_write_tokens"] or 0,
            "reasoning_tokens": r["reasoning_tokens"] or 0,
            "cost": cost,
            "project": _project_from_path(r["cwd"] or ""),
            "source_metadata": json.dumps({
                "title": r["title"] or "",
                "source": r["source"] or "",
            }),
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  Codex CLI — ~/.codex/state_5.sqlite (threads table)
# ═══════════════════════════════════════════════════════════════════════════════

def scan_codex(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan Codex CLI threads table."""
    db = db_path or Path.home() / ".codex" / "state_5.sqlite"
    conn = _safe_connect(db)
    if not conn:
        return []

    try:
        rows = conn.execute("""
            SELECT
                id,
                title,
                model,
                model_provider,
                cwd,
                tokens_used,
                git_branch,
                created_at,
                updated_at,
                reasoning_effort
            FROM threads
            WHERE tokens_used > 0
        """).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    results = []
    for r in rows:
        model = r["model"] or r["model_provider"] or "unknown"
        provider = r["model_provider"] or ""
        if provider and provider not in model:
            model = f"{provider}/{model}"

        results.append({
            "source": "codex",
            "session_id": r["id"] or "",
            "timestamp": _ts_to_iso(r["created_at"]),
            "model": model,
            "input_tokens": r["tokens_used"] or 0,
            "output_tokens": 0,
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": 0.0,
            "project": _project_from_path(r["cwd"] or ""),
            "source_metadata": json.dumps({
                "title": r["title"] or "",
                "git_branch": r["git_branch"] or "",
                "reasoning_effort": r["reasoning_effort"] or "",
            }),
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  RoutingMagic — ~/.routingmagic/metrics/token_metrics.db
# ═══════════════════════════════════════════════════════════════════════════════

def scan_routingmagic(db_path: Optional[Path] = None) -> List[Dict]:
    """Scan RoutingMagic internal metrics."""
    db = db_path or Path.home() / ".routingmagic" / "metrics" / "token_metrics.db"
    conn = _safe_connect(db)
    if not conn:
        return []

    try:
        rows = conn.execute("""
            SELECT
                session_id,
                timestamp,
                model_used,
                task_type,
                input_tokens,
                output_tokens,
                caveman_input_savings_pct,
                caveman_output_savings_pct,
                mythos_effort,
                council_invoked,
                fallback_tier,
                latency_ms,
                cost_usd,
                caveman_level
            FROM sessions
            WHERE input_tokens + output_tokens > 0
        """).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    results = []
    for r in rows:
        results.append({
            "source": "routingmagic",
            "session_id": r["session_id"] or "",
            "timestamp": _ts_to_iso(r["timestamp"]),
            "model": r["model_used"] or "unknown",
            "input_tokens": r["input_tokens"] or 0,
            "output_tokens": r["output_tokens"] or 0,
            "cache_read": 0,
            "cache_write": 0,
            "reasoning_tokens": 0,
            "cost": r["cost_usd"] or 0.0,
            "project": "routingmagic",
            "source_metadata": json.dumps({
                "task_type": r["task_type"] or "",
                "caveman_savings_in": r["caveman_input_savings_pct"] or 0,
                "caveman_savings_out": r["caveman_output_savings_pct"] or 0,
                "mythos_effort": r["mythos_effort"] or "",
                "council_invoked": bool(r["council_invoked"]),
                "fallback_tier": r["fallback_tier"] or 0,
                "latency_ms": r["latency_ms"] or 0,
                "caveman_level": r["caveman_level"] or "",
            }),
        })
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  Adapter registry
# ═══════════════════════════════════════════════════════════════════════════════

ADAPTERS = {
    "claude": scan_claude,
    "opencode": scan_opencode,
    "hermes": scan_hermes,
    "codex": scan_codex,
    "routingmagic": scan_routingmagic,
}

# Sources ordered by data richness (most detailed first)
SOURCE_ORDER = ["claude", "opencode", "hermes", "codex", "routingmagic"]

# Friendly display names for the UI
SOURCE_DISPLAY_NAMES = {
    "claude": "Claude Code",
    "opencode": "OpenCode",
    "hermes": "Hermes",
    "codex": "Codex CLI",
    "routingmagic": "RoutingMagic",
}


def scan_all(sources: Optional[List[str]] = None) -> Dict[str, List[Dict]]:
    """Run all (or selected) adapters and return {source: [rows]}."""
    targets = sources or SOURCE_ORDER
    results = {}
    for name in targets:
        if name in ADAPTERS:
            try:
                rows = ADAPTERS[name]()
                results[name] = rows
            except Exception as e:
                print(f"  [dashboard] Warning: {name} adapter failed: {e}")
                results[name] = []
    return results
