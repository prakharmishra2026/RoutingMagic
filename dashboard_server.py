"""
dashboard_server.py - Unified AI Usage Dashboard for RoutingMagic.

HTTP server on localhost:9898 that serves a single-page dashboard showing
usage from all AI tools: Claude Code, OpenCode, Hermes, Codex CLI,
and RoutingMagic's internal metrics.

Zero dependencies — stdlib only (sqlite3, http.server, json).
"""
import json
import os
import sqlite3
import threading
import time
import webbrowser
import socket
import sys
import signal
import atexit
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from datetime import datetime, timedelta, timezone

from unified_scanner import get_db, init_db, DB_PATH, scan

VERSION = "2.0.0"

# Cache for get_dashboard_data
_dashboard_cache = {"mtime": None, "data": None}
_dashboard_cache_lock = threading.Lock()

# ════════════════════════════════════════════════════════════════════════════════
#  Daemon Mode & Port Auto-Discovery
# ════════════════════════════════════════════════════════════════════════════════

PID_FILE = Path.home() / ".routingmagic" / "dashboard.pid"
LOG_FILE = Path.home() / ".routingmagic" / "dashboard.log"


def find_free_port(start: int = 9898, max_tries: int = 100) -> int:
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
    raise RuntimeError(f"No free ports in range {start}-{start + max_tries}")


def write_pid_file(port: int):
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: write to temp file then replace
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', dir=PID_FILE.parent, delete=False, suffix='.tmp') as tf:
        tf.write(f"{os.getpid()}\n{port}\n")
        tmp_path = Path(tf.name)
    try:
        os.replace(tmp_path, PID_FILE)
    except Exception:
        try:
            tmp_path.unlink()
        except Exception:
            pass
        raise
    atexit.register(cleanup_pid_file)


def cleanup_pid_file():
    if PID_FILE.exists():
        PID_FILE.unlink()


def is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_running_dashboard_port() -> Optional[int]:
    if not PID_FILE.exists():
        return None
    try:
        content = PID_FILE.read_text().strip().split()
        if len(content) >= 2:
            pid = int(content[0])
            port = int(content[1])
            if is_process_alive(pid):
                return port
    except Exception:
        pass
    return None


def run_as_daemon(host: str = "localhost", port: int = 9898):
    """Double-fork daemon mode."""
    if os.fork() > 0:
        sys.exit(0)

    os.setsid()
    if os.fork() > 0:
        sys.exit(0)

    sys.stdout.flush()
    sys.stderr.flush()

    log_fh = open(LOG_FILE, 'a')
    os.dup2(log_fh.fileno(), sys.stdout.fileno())
    os.dup2(log_fh.fileno(), sys.stderr.fileno())

    write_pid_file(port)
    serve(host=host, port=port)


def ensure_dashboard_running(host: str = "localhost", preferred_port: int = 9898) -> int:
    """Ensure dashboard daemon is running, return actual port."""
    if PID_FILE.exists():
        try:
            content = PID_FILE.read_text().strip().split()
            if len(content) >= 2:
                pid = int(content[0])
                port = int(content[1])
                if is_process_alive(pid):
                    return port
        except Exception:
            pass

    port = find_free_port(preferred_port)
    run_as_daemon(host, port)
    return port



# ═════════════════════════════════════════════════════════════════════════════════
#  Quota Monitor (background thread)
# ═════════════════════════════════════════════════════════════════════════════════

def start_quota_monitor():
    """Background thread: runs quota checks every 60s, saves alerts."""
    try:
        from quota_engine import QuotaEngine
    except ImportError:
        return

    def loop():
        engine = QuotaEngine()
        while True:
            try:
                snapshots = engine.compute_all()
                engine.save_snapshots(snapshots)

                alerts = engine.check_alerts(snapshots)
                if alerts:
                    engine.save_alerts(alerts)
                    # Note: WebSocket removed; frontend polls /api/alerts

            except Exception as e:
                print(f"Quota monitor error: {e}", file=sys.stderr)

            time.sleep(60)

    threading.Thread(target=loop, daemon=True).start()

# ════════════════════════════════════════════════════════════════════════════════
#  Pricing — all known providers (USD per 1M tokens)
# ════════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════════
#  Pricing — all known providers (USD per 1M tokens)
# ════════════════════════════════════════════════════════════════════════════════

import re

PRICING = {
    "claude-fable-5":    {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_write": 12.50},
    "claude-mythos-5":   {"input": 10.00, "output": 50.00, "cache_read": 1.00, "cache_write": 12.50},
    "claude-opus-4-8":   {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "claude-haiku-4-5":  {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25},
    "gpt-5":             {"input": 2.50, "output": 10.00, "cache_read": 0.25, "cache_write": 2.50},
    "gpt-4-turbo":       {"input": 10.00, "output": 30.00, "cache_read": 0.50, "cache_write": 10.00},
    "o3-mini":           {"input": 1.10, "output": 4.40, "cache_read": 0.11, "cache_write": 1.10},
    "gemini-2.5-flash":  {"input": 0.15, "output": 0.60, "cache_read": 0.0375, "cache_write": 0.15},
    "gemini-2.5-pro":    {"input": 1.25, "output": 10.00, "cache_read": 0.125, "cache_write": 1.25},
    "deepseek-v3":       {"input": 0.27, "output": 1.10, "cache_read": 0.07, "cache_write": 0.27},
    "deepseek-r1":       {"input": 0.55, "output": 2.19, "cache_read": 0.14, "cache_write": 0.55},
    # NVIDIA NIM paid models (approximate pricing)
    "nemotron-3-ultra":  {"input": 1.00, "output": 3.00, "cache_read": 0.10, "cache_write": 1.00},
    "nemotron-3-super":  {"input": 0.50, "output": 1.50, "cache_read": 0.05, "cache_write": 0.50},
    "nemotron-3.5":      {"input": 0.30, "output": 1.00, "cache_read": 0.03, "cache_write": 0.30},
    "glm-5":             {"input": 0.80, "output": 2.50, "cache_read": 0.08, "cache_write": 0.80},
    "deepseek-v4-pro":   {"input": 0.40, "output": 1.20, "cache_read": 0.04, "cache_write": 0.40},
    "minimax-m3":        {"input": 0.60, "output": 2.00, "cache_read": 0.06, "cache_write": 0.60},
    "muse-glimmer":      {"input": 0.20, "output": 0.80, "cache_read": 0.02, "cache_write": 0.20},
}

ZERO_PRICING = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

# Provider tokens that indicate ALWAYS zero-cost (built-in free)
FREE_PROVIDER_TOKENS = {"nvidia", "nim", "opencode"}
# Provider tokens that have a FREE TIER (use :free suffix check)
FREE_TIER_PROVIDERS = {"nvidia", "nim", "openrouter"}
# Model families always free regardless of provider
FREE_MODEL_TOKENS = {"gpt-oss", "big-pickle", "laguna", "nemotron-3-ultra-free", "nemotron-3.5-lightning-free"}

PRICING_KEYS = {k.lower(): v for k, v in PRICING.items()}

# Family token -> pricing key (for paid models only; free handled by is_free)
FAMILY_PRICING = [
    ({"fable", "mythos"}, "claude-fable-5"),
    ({"opus"}, "claude-opus-4-8"),
    ({"sonnet"}, "claude-sonnet-4-6"),
    ({"haiku"}, "claude-haiku-4-5"),
    ({"claude"}, "claude-sonnet-4-6"),  # generic fallback
    ({"deepseek", "r1"}, "deepseek-r1"),
    ({"deepseek"}, "deepseek-v3"),
    ({"deepseek", "v4", "pro"}, "deepseek-v4-pro"),
    ({"gemini", "pro"}, "gemini-2.5-pro"),
    ({"gemini", "flash"}, "gemini-2.5-flash"),
    ({"gemini"}, "gemini-2.5-flash"),
    ({"gpt", "5"}, "gpt-5"),
    ({"gpt", "4"}, "gpt-4-turbo"),
    ({"o3"}, "o3-mini"),
    ({"o1"}, "o3-mini"),
    ({"nemotron", "3", "ultra"}, "nemotron-3-ultra"),
    ({"nemotron", "3", "super"}, "nemotron-3-super"),
    ({"nemotron", "3.5"}, "nemotron-3.5"),
    ({"glm", "5"}, "glm-5"),
    ({"minimax", "m3"}, "minimax-m3"),
    ({"muse", "glimmer"}, "muse-glimmer"),
]

def _model_tokens(model: str) -> set:
    """Split model into delimiter-separated tokens."""
    return set(re.split(r"[/\-._:]+", model.lower()))

def is_free(model: str, source: str = None) -> bool:
    """Unified free/paid determination used by server + serialized to client."""
    if not model:
        return True
    m = model.lower()
    if source == "routingmagic":
        return True
    if ":free" in m:
        return True
    tokens = _model_tokens(m)
    if "free" in tokens:
        return True
    if "/" in m:
        provider = m.split("/", 1)[0]
        if provider in FREE_PROVIDER_TOKENS:
            return True
        if provider in FREE_TIER_PROVIDERS:
            return False  # free-tier providers need :free suffix
    if tokens & FREE_MODEL_TOKENS:
        return True
    return False

def get_pricing(model: str, source: str = None) -> Optional[dict]:
    if not model:
        return None
    if is_free(model, source):
        return ZERO_PRICING
    low = model.lower()
    if low in PRICING_KEYS:
        return PRICING_KEYS[low]
    # Strip provider prefix recursively (openrouter/z-ai/glm-5.2 -> z-ai/glm-5.2 -> glm-5.2)
    if "/" in low:
        _, rest = low.split("/", 1)
        sub = get_pricing(rest, source)
        if sub:
            return sub
    tokens = _model_tokens(low)
    for family_tokens, pricing_key in FAMILY_PRICING:
        if family_tokens.issubset(tokens):
            return PRICING_KEYS[pricing_key]
    return None

def calc_cost(model: str, inp: int, out: int, cache_read: int, cache_write: int, source: str = None) -> float:
    p = get_pricing(model, source)
    if not p:
        return 0.0
    return (
        inp * p["input"] / 1_000_000 +
        out * p["output"] / 1_000_000 +
        cache_read * p["cache_read"] / 1_000_000 +
        cache_write * p["cache_write"] / 1_000_000
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Data API
# ═══════════════════════════════════════════════════════════════════════════════

def get_dashboard_data(db_path: Path = DB_PATH) -> dict:
    if not db_path.exists():
        return {"error": "Database not found. Run: python3 unified_scanner.py"}

    # Cache invalidation based on DB mtime
    mtime = db_path.stat().st_mtime_ns
    with _dashboard_cache_lock:
        if _dashboard_cache["mtime"] == mtime and _dashboard_cache["data"] is not None:
            return _dashboard_cache["data"]

    conn = get_db(db_path)
    conn.execute("PRAGMA busy_timeout = 5000")
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
    sources = [{"source": r["source"], "turns": r["turns"], "tokens": r["tokens"] or 0}
               for r in source_rows]

    # Daily per-model per-source (full history, client filters)
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

    # All sessions (client filters)
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

    # RoutingMagic-specific: caveman savings from source_metadata
    rm_rows = conn.execute("""
        SELECT
            substr(timestamp, 1, 10) as day,
            SUM(input_tokens) as input,
            SUM(output_tokens) as output,
            source_metadata
        FROM unified_turns
        WHERE source = 'routingmagic'
        GROUP BY day
        ORDER BY day
    """).fetchall()
    rm_daily = []
    for r in rm_rows:
        meta = {}
        try:
            meta = json.loads(r["source_metadata"] or "{}")
        except Exception:
            pass
        rm_daily.append({
            "day": r["day"],
            "input": r["input"] or 0,
            "output": r["output"] or 0,
            "caveman_savings": meta.get("caveman_savings_out", 0),
            "mythos_effort": meta.get("mythos_effort", ""),
        })

    # Scan state
    scan_state = {}
    for r in conn.execute("SELECT * FROM scan_state").fetchall():
        scan_state[r["source"]] = {"last_scan": r["last_scan"], "row_count": r["row_count"]}

    conn.close()

    result = {
        "all_models": all_models,
        "sources": sources,
        "daily_by_model": daily_by_model,
        "sessions_all": sessions_all,
        "rm_daily": rm_daily,
        "scan_state": scan_state,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    # Store in cache
    with _dashboard_cache_lock:
        _dashboard_cache["mtime"] = mtime
        _dashboard_cache["data"] = result
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  HTTP Server
# ═══════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════════
#  Rescan Lock & CORS
# ════════════════════════════════════════════════════════════════════════════════

RESCAN_LOCK = threading.Lock()
_last_rescan_ts = 0.0
RESCAN_MIN_INTERVAL = 10.0  # seconds


def _apply_cors(handler):
    """Apply same-origin CORS: only allow localhost origins."""
    origin = handler.headers.get("Origin", "")
    if origin:
        if origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
            handler.send_header("Access-Control-Allow-Origin", origin)
            handler.send_header("Vary", "Origin")
            return True
    return False


def _try_trigger_rescan() -> tuple[bool, str]:
    """Try to trigger a rescan. Returns (success, status)."""
    global _last_rescan_ts
    if not RESCAN_LOCK.acquire(blocking=False):
        return False, "already_scanning"
    now = time.time()
    if now - _last_rescan_ts < RESCAN_MIN_INTERVAL:
        RESCAN_LOCK.release()
        return False, "rate_limited"
    _last_rescan_ts = now
    def _run():
        try:
            scan(verbose=False)
        finally:
            RESCAN_LOCK.release()
    threading.Thread(target=_run, daemon=True).start()
    return True, "scanning"


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress request logging

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/data":
            data = get_dashboard_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            _apply_cors(self)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            return

        if parsed.path == "/api/rescan":
            ok, status = _try_trigger_rescan()
            code = 200 if ok else 409
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            _apply_cors(self)
            self.end_headers()
            self.wfile.write(json.dumps({"status": status}).encode())
            return

        if parsed.path == "/api/quotas":
            data = get_quota_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            _apply_cors(self)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            return

        if parsed.path == "/api/budget":
            data = get_budget_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            _apply_cors(self)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            return

        if parsed.path == "/api/alerts":
            data = get_unacknowledged_alerts()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            _apply_cors(self)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            return

        if parsed.path == "/api/adapter-status":
            data = get_adapter_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            _apply_cors(self)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            return


        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(DASHBOARD_HTML.encode())
            return

        if parsed.path.startswith("/assets/"):
            asset_path = Path(__file__).parent / "assets" / parsed.path[len("/assets/"):]
            if asset_path.exists() and asset_path.is_file():
                self.send_response(200)
                if asset_path.suffix == ".js":
                    self.send_header("Content-Type", "application/javascript")
                elif asset_path.suffix == ".css":
                    self.send_header("Content-Type", "text/css")
                else:
                    self.send_header("Content-Type", "application/octet-stream")
                self.end_headers()
                self.wfile.write(asset_path.read_bytes())
                return
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()


# ════════════════════════════════════════════════════════════════════════════════
#  Quota API Functions
# ════════════════════════════════════════════════════════════════════════════════

def get_quota_data() -> dict:
    """Get latest quota snapshots for all providers."""
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
    }


def _load_budget_config():
    """Load budget config from quotas.yaml with validation."""
    import yaml
    config_path = Path.home() / ".routingmagic" / "quotas.yaml"
    defaults = {"monthly_usd": 50.00, "daily_tokens": 2000000}
    if not config_path.exists():
        return defaults
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        budgets = data.get("budgets", {})
        monthly = budgets.get("monthly_usd", defaults["monthly_usd"])
        daily = budgets.get("daily_tokens", defaults["daily_tokens"])
        # Validate positive numbers
        if not isinstance(monthly, (int, float)) or monthly <= 0:
            monthly = defaults["monthly_usd"]
        if not isinstance(daily, int) or daily <= 0:
            daily = defaults["daily_tokens"]
        return {"monthly_usd": float(monthly), "daily_tokens": int(daily)}
    except Exception:
        return defaults


def get_budget_status() -> dict:
    """Get aggregate budget status for header display."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Monthly spend
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    monthly_cost = conn.execute("""
        SELECT COALESCE(SUM(cost), 0) as total FROM unified_turns WHERE timestamp >= ?
    """, (month_start,)).fetchone()["total"]

    # Daily tokens
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    daily_tokens = conn.execute("""
        SELECT COALESCE(SUM(input_tokens + output_tokens), 0) as total FROM unified_turns WHERE timestamp >= ?
    """, (day_start,)).fetchone()["total"]

    conn.close()

    budget_cfg = _load_budget_config()
    monthly_budget = budget_cfg["monthly_usd"]
    daily_cap = budget_cfg["daily_tokens"]

    return {
        "monthly": {
            "budget": monthly_budget,
            "spent": monthly_cost,
            "remaining": max(0, monthly_budget - monthly_cost),
            "pct": (monthly_cost / monthly_budget * 100) if monthly_budget else 0,
        },
        "daily": {
            "cap": daily_cap,
            "used": daily_tokens,
            "remaining": max(0, daily_cap - daily_tokens),
            "pct": (daily_tokens / daily_cap * 100) if daily_cap else 0,
        },
    }


def get_unacknowledged_alerts() -> list:
    """Get unacknowledged budget alerts."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT * FROM budget_alerts WHERE acknowledged = 0 ORDER BY timestamp DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_adapter_status() -> dict:
    """Get adapter discovery status."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM adapter_state").fetchall()
    conn.close()
    return {r["name"]: dict(r) for r in rows}


def serve(host="localhost", port=9898):
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard running at http://{host}:{port}")
    server.serve_forever()


def main():
    import sys
    host = os.environ.get("HOST", "localhost")
    port = int(os.environ.get("PORT", "9898"))

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--host" and i < len(sys.argv):
            host = sys.argv[i + 1]
        if arg == "--port" and i < len(sys.argv):
            port = int(sys.argv[i + 1])
        if arg == "scan":
            scan()
            return
        if arg in ("-h", "--help"):
            print(f"Usage: python3 dashboard_server.py [scan] [--host HOST] [--port PORT]")
            print(f"  scan     Scan all sources and update unified DB")
            print(f"  --host   Bind address (default: localhost)")
            print(f"  --port   Port (default: 9898")
            return

    # Background scan, serve immediately
    def bg_scan():
        scan(verbose=False)
    threading.Thread(target=bg_scan, daemon=True).start()

    # Open browser
    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://{host}:{port}")
    threading.Thread(target=open_browser, daemon=True).start()

    # Start quota monitor
    start_quota_monitor()

    serve(host=host, port=port)


if __name__ == "__main__":
    main()

