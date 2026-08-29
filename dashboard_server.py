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
import random
import concurrent.futures
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from datetime import datetime, timedelta, timezone

from unified_scanner import get_db, init_db, DB_PATH, scan

VERSION = "2.0.0"


def parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse timestamp from various formats, return timezone-aware datetime or None."""
    if not ts:
        return None
    s = ts.strip()
    # Try ISO format with Z suffix
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    # Try common formats
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


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
FREE_PROVIDER_TOKENS = {"opencode"}
# Provider tokens that have a FREE TIER (use :free suffix check)
FREE_TIER_PROVIDERS = {"nvidia", "nim", "openrouter", "deepseek-ai", "openai"}
# Model families always free regardless of provider
FREE_MODEL_TOKENS = {"gpt-oss", "big-pickle", "laguna", "nemotron-3-ultra-free", "nemotron-3.5-lightning-free"}
# Dynamically loaded free model sets from registry (updated daily)
_freemodel_cache = {"nim": set(), "openrouter": set(), "mtime": 0}

def _load_free_models_from_registry() -> tuple[set, set]:
    """Load free model sets from registry JSON. Returns (nim_free, openrouter_free).
    
    Registry format (from model_registry_updater) has:
    - nim_free_models: list of free NIM model IDs
    - openrouter_free_models: list of free OpenRouter model IDs
    - all_free_models: list of all free models (legacy format)
    - Categories: free_models, reasoning_models, etc.
    """
    global _freemodel_cache
    registry_path = Path.home() / ".routingmagic" / "registry" / "model_registry.json"
    if not registry_path.exists():
        return set(), set()
    
    mtime = registry_path.stat().st_mtime
    if _freemodel_cache["mtime"] == mtime and (_freemodel_cache["nim"] or _freemodel_cache["openrouter"]):
        return _freemodel_cache["nim"], _freemodel_cache["openrouter"]
    
    try:
        with open(registry_path) as f:
            data = json.load(f)
        
        # Parse new format: nim_free_models and openrouter_free_models
        nim_free = set()
        or_free = set()
        
        if "nim_free_models" in data:
            nim_free = set(m.lower() for m in data.get("nim_free_models", []))
        if "openrouter_free_models" in data:
            or_free = set(m.lower() for m in data.get("openrouter_free_models", []))
        
        # Fallback: parse all_free_models (legacy format)
        if not nim_free and not or_free and "all_free_models" in data:
            for m in data.get("all_free_models", []):
                mid = m.get("id")
                if mid:
                    mid_lower = mid.lower()
                    # Heuristic: NIM models don't have :free suffix
                    if mid_lower.startswith(("nvidia/", "deepseek-ai/", "openai/", "poolside/", "minimaxai/", "moonshotai/", "google/", "stepfun-ai/", "z-ai/")):
                        nim_free.add(mid_lower)
                    else:
                        or_free.add(mid_lower)
        
        _freemodel_cache = {"nim": nim_free, "openrouter": or_free, "mtime": mtime}
        return nim_free, or_free
    except Exception:
        return set(), set()


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
            # Load free models from registry (cached, updated daily)
            nim_free, or_free = _load_free_models_from_registry()
            if m in nim_free or m in or_free:
                return True
            return False  # free-tier providers need :free suffix or registry entry
    if tokens & FREE_MODEL_TOKENS:
        return True
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
            t1 = parse_timestamp(r["first_timestamp"])
            t2 = parse_timestamp(r["last_timestamp"])
            if t1 and t2:
                duration_min = round((t2 - t1).total_seconds() / 60, 1)
            else:
                duration_min = 0
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


# ════════════════════════════════════════════════════════════════════════════════
#  Model Council  (POST /api/council)
#
#  Registry-driven: members are picked from the live free-model pool written by
#  model_registry_updater.py — never a hardcoded list. Synchronous end to end so
#  it is safe to call straight from a request thread (ThreadingHTTPServer).
# ════════════════════════════════════════════════════════════════════════════════

# documented load order: ~/.routingmagic/.env, then ~/global.env, then real env vars
RM_ENV_FILES = (Path.home() / ".routingmagic" / ".env", Path.home() / "global.env")
RM_REGISTRY_DIR = Path.home() / ".routingmagic" / "registry"
COUNCIL_SIZE = 3
COUNCIL_MEMBER_TIMEOUT = 45.0
COUNCIL_STALE_HOURS = 48

# prompt keyword groups -> model-name substrings that suit that kind of task
_COUNCIL_TASK_HINTS = [
    (("code", "bug", "refactor", "function", "regex", "sql", "python", "typescript", "javascript", "react"),
     ("coder", "code", "deepseek", "qwen")),
    (("plan", "architecture", "strategy", "design", "reason", "analy", "trade-off", "tradeoff", "proof", "algorithm"),
     ("nemotron", "reason", "gpt-oss", "glm", "ultra")),
    (("finance", "financial", "valuation", "dcf", "stock", "invest", "earnings", "portfolio"),
     ("minimax", "nemotron", "glm")),
]

# free-pool entries that are not general chat models (music/vision/OCR/moderation/
# meta-route aliases) — never send council prompts to these
_COUNCIL_EXCLUDE_SUBSTR = (
    "lyria", "whisper", "parakeet", "canary", "embed", "-ocr", "-tts", "-rerank",
    "content-safety", "guard", "moderation", "stable-diffusion", "sdxl", "flux",
    "imagen", "sana", "-vl-", "vision-", "clip-", "-clip", "voicechat",
    "inkling",  # thinkingmachines/inkling* — gated to "agentic harnesses", 403 on plain chat
)
_COUNCIL_EXCLUDE_EXACT = {"openrouter/free"}


def _load_rm_env():
    """Best-effort load of RoutingMagic env files into os.environ.

    Never overwrites a value already set (real env vars win). Empty assignments
    like ``NVAPI_KEY=`` are ignored so they cannot shadow a real key in a later
    file — this is exactly the ~/.routingmagic/.env vs ~/global.env case.
    """
    for path in RM_ENV_FILES:
        try:
            lines = path.read_text().splitlines()
        except (OSError, ValueError):
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and not os.environ.get(k):
                os.environ[k] = v


def _registry_age_hours() -> float:
    """Hours since model_registry.json was last written (data-freshness signal)."""
    try:
        mtime = (RM_REGISTRY_DIR / "model_registry.json").stat().st_mtime
        return (time.time() - mtime) / 3600.0
    except OSError:
        return float("inf")


def _load_degraded_models() -> set:
    """Model IDs the daily health check flagged degraded (health_cache.json keys)."""
    try:
        data = json.loads((RM_REGISTRY_DIR / "health_cache.json").read_text())
        return {k.lower() for k in data} if isinstance(data, dict) else set()
    except (OSError, ValueError):
        return set()


def _is_chat_model(model: str) -> bool:
    """False for free-pool entries that are not general chat models."""
    m = model.lower()
    if m in _COUNCIL_EXCLUDE_EXACT:
        return False
    return not any(s in m for s in _COUNCIL_EXCLUDE_SUBSTR)


def _select_council_models(prompt: str, n: int = COUNCIL_SIZE, want: int = None):
    """Pick free models from the live registry: task-suited first, then random.

    Returns up to ``want`` (default n) candidates as (model_id, provider) pairs.
    Free models fail often (429/404/503), so callers over-select and keep the
    first n that answer. ``provider`` comes from which registry set the model is
    in (nim_free_models -> nvidia, openrouter_free_models -> openrouter), NOT the
    ':free' suffix, which some NIM-list and Google-on-OpenRouter entries lack.
    Returns (picks, degraded_relaxed, pool_size); degraded_relaxed means health
    checks knocked the pool below n and degraded models were allowed back in.
    """
    want = want or n
    nim_free, or_free = _load_free_models_from_registry()
    provider_of = {}
    for m in or_free:
        provider_of[m] = "openrouter"
    for m in nim_free:
        provider_of.setdefault(m, "nvidia")  # nim list wins only if not already OR

    # collapse "<id>" and "<id>:free" to one entry (same model, two providers)
    by_base = {}
    for m in provider_of:
        by_base.setdefault(m[:-5] if m.endswith(":free") else m, m)
    provider_of = {v: provider_of[v] for v in by_base.values()}

    pool = sorted(m for m in provider_of if _is_chat_model(m))
    degraded = _load_degraded_models()
    healthy = [m for m in pool if m not in degraded]
    working = healthy if len(healthy) >= n else pool
    degraded_relaxed = len(healthy) < n and bool(degraded)

    pl = (prompt or "").lower()
    preferred = []
    for kws, hints in _COUNCIL_TASK_HINTS:
        if any(k in pl for k in kws):
            preferred = [m for m in working if any(h in m for h in hints)]
            break

    picked = []
    for m in preferred:
        if m not in picked:
            picked.append(m)
        if len(picked) >= want:
            break
    rest = [m for m in working if m not in picked]
    random.shuffle(rest)
    picked.extend(rest[: max(0, want - len(picked))])
    return [(m, provider_of[m]) for m in picked[:want]], degraded_relaxed, len(pool)


def _council_client(provider: str):
    from openai import OpenAI  # lazy: the dashboard still starts if openai is absent
    if provider == "nvidia":
        key = os.environ.get("NVAPI_KEY") or os.environ.get("NVIDIA_API_KEY")
        if not key:
            raise RuntimeError("NVAPI_KEY not set")
        return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=key,
                      max_retries=0, timeout=COUNCIL_MEMBER_TIMEOUT)
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                  max_retries=0, timeout=COUNCIL_MEMBER_TIMEOUT)


def _council_query_one(model: str, provider: str, prompt: str) -> dict:
    try:
        resp = _council_client(provider).chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
        return {"model": model, "provider": provider, "success": True, "error": "",
                "content": (resp.choices[0].message.content or "").strip()}
    except Exception as e:
        return {"model": model, "provider": provider, "success": False,
                "error": f"{type(e).__name__}: {str(e)[:200]}", "content": ""}


def _council_synthesize(prompt: str, members: list) -> str:
    ok = [m for m in members if m["success"] and m["content"]]
    if not ok:
        return ""
    if len(ok) == 1:
        return ok[0]["content"]
    joined = "\n\n".join(f"### Member {i + 1} ({m['model']})\n{m['content']}"
                         for i, m in enumerate(ok))
    syn_prompt = (
        f"You are the chair of a model council. {len(ok)} models independently answered "
        "the question below. Synthesise one decisive answer: note where they agree, flag "
        "where they disagree, and give the best combined recommendation.\n\n"
        f"QUESTION:\n{prompt}\n\n{joined}"
    )
    for m in ok:  # reuse a member that already worked as the synthesiser
        r = _council_query_one(m["model"], m["provider"], syn_prompt)
        if r["success"] and r["content"]:
            return r["content"]
    return ok[0]["content"]


def run_local_council(prompt: str) -> dict:
    """Registry-driven Model Council. Synchronous; safe from a request thread."""
    _load_rm_env()
    prompt = (prompt or "").strip()
    if not prompt:
        return {"error": "empty prompt", "results": [], "synthesis": "",
                "degraded": True, "degraded_note": ""}

    age = _registry_age_hours()
    if age > COUNCIL_STALE_HOURS:
        return {"error": (f"model registry is {age:.0f}h old (>{COUNCIL_STALE_HOURS}h); "
                          "refusing to run — listed models may no longer be free. "
                          "Run model_registry_updater.py."),
                "results": [], "synthesis": "", "degraded": True, "degraded_note": ""}

    # Over-select: free models fail often, so try up to 2x and keep the first
    # COUNCIL_SIZE that actually answer. _select_council_models caps `want` at
    # the number of candidates actually available.
    picks, degraded_relaxed, pool_size = _select_council_models(
        prompt, want=COUNCIL_SIZE * 2)
    if not picks:
        return {"error": f"no free chat models in registry (pool={pool_size}); "
                         "run model_registry_updater.py",
                "results": [], "synthesis": "", "degraded": True, "degraded_note": ""}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(picks)) as ex:
        tried = list(ex.map(lambda mp: _council_query_one(mp[0], mp[1], prompt), picks))

    good = [m for m in tried if m["success"]]
    bad = [m for m in tried if not m["success"]]
    members = good[:COUNCIL_SIZE] or bad[:COUNCIL_SIZE]
    if len(good) < COUNCIL_SIZE:  # pad with failures so the UI shows what was tried
        members = good + bad[: COUNCIL_SIZE - len(good)]

    ok = len(good)
    if ok < COUNCIL_SIZE:
        note = (f"degraded: only {ok} of {COUNCIL_SIZE} members answered "
                f"({len(picks)} models tried)")
    elif degraded_relaxed:
        note = "warning: health cache exhausted the free pool; degraded models were allowed"
    else:
        note = ""
    return {
        "results": members,
        "synthesis": _council_synthesize(prompt, members),
        "degraded": ok < COUNCIL_SIZE,
        "degraded_note": note,
        "models": [m["model"] for m in members],
        "tried": [m["model"] for m in tried],
        "pool_size": pool_size,
        "registry_age_hours": round(age, 1),
    }


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress request logging

    def _send_json(self, obj, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        _apply_cors(self)
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/council":
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(n) if n > 0 else b"{}"
                prompt = json.loads(raw or b"{}").get("prompt", "")
            except (ValueError, TypeError):
                self._send_json({"error": "invalid JSON body", "results": []}, 400)
                return
            if not str(prompt).strip():
                self._send_json({"error": "empty prompt", "results": []}, 400)
                return
            try:
                result = run_local_council(prompt)
            except Exception as e:
                self._send_json({"error": f"{type(e).__name__}: {e}", "results": []}, 500)
                return
            self._send_json(result, 200 if not result.get("error") else 503)
            return
        self.send_response(404)
        self.end_headers()

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

        if parsed.path == "/api/export":
            data = export_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            _apply_cors(self)
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            return

        if parsed.path == "/api/export/csv":
            data = export_csv()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Disposition", 'attachment; filename="routingmagic-usage.csv"')
            _apply_cors(self)
            self.end_headers()
            self.wfile.write(data.encode())
            return

        if parsed.path == "/api/insights":
            data = get_insights()
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


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>RoutingMagic Usage Dashboard</title>
<script src="/assets/chart.umd.min.js"></script>
<style>
:root{--bg:#0d0d0e;--card:#161617;--border:#2C2D2E;--text:#BFBFBF;--muted:#4F4F50;--accent:#d97757;--blue:#48A0C7;--green:#74C991;--red:#C74E39;--purple:#9B7EC7;--amber:#D9A84E;--teal:#5BB8A3;--mauve:#C77E9B;--raised:#1E1F20;--selected:#262626;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}
header{background:var(--card);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;justify-content:space-between;}
header h1{font-size:17px;font-weight:600;}
header .meta{color:var(--muted);font-size:11px;text-align:right;}
#rescan-btn{background:var(--card);border:1px solid var(--border);color:var(--muted);padding:4px 12px;border-radius:6px;cursor:pointer;font-size:12px;}
#rescan-btn:hover{color:var(--text);border-color:var(--accent);}
#filter-bar{background:var(--card);border-bottom:1px solid var(--border);padding:8px 24px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.filter-label{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);white-space:nowrap;}
.filter-sep{width:1px;height:22px;background:var(--border);}
.chip-group{display:flex;gap:4px;flex-wrap:wrap;}
.chip{padding:3px 10px;border-radius:12px;border:1px solid var(--border);background:transparent;color:var(--muted);font-size:11px;cursor:pointer;transition:all .12s;}
.chip:hover{border-color:var(--accent);color:var(--text);}
.chip.active{background:var(--accent);border-color:var(--accent);color:#fff;}
.chip .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:middle;}
.range-select select{appearance:none;-webkit-appearance:none;min-width:130px;padding:4px 28px 4px 10px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:12px;cursor:pointer;}
.range-select::after{content:"\25BE";position:absolute;right:10px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:10px;pointer-events:none;}
.range-select{position:relative;}
.container{max-width:1400px;margin:0 auto;padding:20px 24px;}
.stats-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px;}
.stat-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;}
.stat-card .label{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;}
.stat-card .value{font-size:20px;font-weight:700;}
.stat-card .sub{color:var(--muted);font-size:10px;margin-top:3px;}
.charts-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px;}
.chart-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;min-width:0;}
.chart-card.wide{grid-column:1/-1;}
.chart-card h2{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:12px;}
.chart-wrap{position:relative;height:220px;}
.chart-wrap.tall{height:280px;}
table{width:100%;border-collapse:collapse;}
th{text-align:left;padding:7px 10px;font-size:10px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);border-bottom:1px solid var(--border);white-space:nowrap;}
th.sortable{cursor:pointer;user-select:none;}
th.sortable:hover{color:var(--text);}
td{padding:8px 10px;border-bottom:1px solid var(--border);font-size:12px;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:var(--raised);}
.table-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:20px;overflow-x:auto;}
.section-title{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px;}
.source-tag{display:inline-block;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;}
.source-claude{background:rgba(217,119,87,0.2);color:var(--accent);}
.source-opencode{background:rgba(72,160,199,0.2);color:var(--blue);}
.source-9router{background:rgba(155,126,199,0.2);color:var(--purple);}
.source-hermes{background:rgba(91,184,163,0.2);color:var(--teal);}
.source-codex{background:rgba(217,168,78,0.2);color:var(--amber);}
.source-routingmagic{background:rgba(116,201,145,0.2);color:var(--green);}
.model-tag{display:inline-block;padding:2px 6px;border-radius:4px;font-size:10px;background:rgba(72,160,199,0.15);color:var(--blue);}
.cost{color:var(--green);font-family:monospace;}
.cost-na{color:var(--muted);font-family:monospace;font-size:10px;}
.num{font-family:monospace;}
.free-tag{color:var(--green);font-size:10px;font-weight:600;}
.muted{color:var(--muted);}
.topic-cell{max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;color:var(--text);}
.show-more-btn{background:transparent;border:1px solid var(--border);color:var(--muted);padding:3px 10px;border-radius:6px;cursor:pointer;font-size:11px;}
.show-more-btn:hover{color:var(--text);border-color:var(--accent);}
.footer-content{border-top:1px solid var(--border);padding:16px 24px;margin-top:8px;}
.footer-content p{color:var(--muted);font-size:11px;line-height:1.6;}
.footer-content a{color:var(--blue);text-decoration:none;}
@media(max-width:768px){.charts-grid{grid-template-columns:1fr;}.chart-card.wide{grid-column:1;}}
.header-actions{display:flex;gap:8px;flex-wrap:wrap;}
.btn{background:var(--card);border:1px solid var(--border);color:var(--text);padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;transition:all .15s;display:inline-flex;align-items:center;gap:6px;}
.btn:hover{border-color:var(--accent);color:var(--accent);}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff;}
.btn:disabled{opacity:.5;cursor:not-allowed;}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.8);display:none;align-items:center;justify-content:center;z-index:1000;padding:20px;}
.modal-overlay.open{display:flex;}
.modal{background:var(--card);border:1px solid var(--border);border-radius:16px;max-width:900px;width:100%;max-height:90vh;overflow:hidden;display:flex;flex-direction:column;animation:slideUp .2s ease;}
@keyframes slideUp{from{opacity:0;transform:translateY(20px);}to{opacity:1;transform:translateY(0);}}
.modal-header{padding:20px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
.modal-title{font-size:16px;font-weight:700;}
.modal-close{background:transparent;border:none;color:var(--muted);font-size:24px;cursor:pointer;padding:0;line-height:1;}
.modal-close:hover{color:var(--text);}
.modal-body{padding:24px;overflow-y:auto;flex:1;}
.modal-footer{padding:16px 24px;border-top:1px solid var(--border);display:flex;justify-content:flex-end;gap:12px;}
.council-prompt{width:100%;min-height:110px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:12px;font-family:inherit;font-size:14px;resize:vertical;margin-bottom:14px;}
.council-prompt:focus{outline:none;border-color:var(--accent);}
.council-note{color:var(--amber);font-size:12px;margin-bottom:12px;padding:8px 10px;border:1px solid var(--amber);border-radius:6px;background:rgba(217,168,78,.08);}
.council-results{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;}
.council-member{background:var(--bg);border:1px solid var(--border);border-radius:10px;padding:16px;min-width:0;}
.council-member-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px;gap:8px;}
.council-member-model{flex:1;min-width:0;font-weight:600;font-size:12px;font-family:monospace;color:var(--accent);overflow-wrap:anywhere;}
.council-member-status{flex-shrink:0;font-size:11px;padding:2px 8px;border-radius:4px;}
.council-member-status.success{background:rgba(110,224,163,.2);color:var(--green);}
.council-member-status.error{background:rgba(232,92,78,.2);color:var(--red);}
.council-member-content{font-size:13px;line-height:1.6;color:var(--text);white-space:pre-wrap;max-height:220px;overflow-y:auto;}
.council-synthesis{grid-column:1/-1;margin-top:4px;padding:16px;background:rgba(217,119,87,.08);border:1px solid var(--accent);border-radius:10px;}
.council-synthesis h4{font-size:13px;font-weight:600;margin-bottom:8px;color:var(--accent);}
.council-synthesis p{font-size:13px;line-height:1.6;color:var(--text);white-space:pre-wrap;}
.loading{display:inline-flex;align-items:center;gap:8px;color:var(--muted);}
.spinner{width:16px;height:16px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
</style>
</head>
<body>
<header>
  <div><h1>RoutingMagic Desk</h1></div>
  <div class="meta" id="meta">Loading...</div>
  <div class="header-actions">
    <button class="btn" id="export-json-btn" onclick="exportJSON()" title="Export all data as JSON">Export JSON</button>
    <button class="btn" id="export-csv-btn" onclick="exportCSV()" title="Export sessions as CSV">Export CSV</button>
    <button class="btn" id="insights-btn" onclick="showInsights()">Insights</button>
    <button class="btn" id="council-btn" onclick="openCouncil()">Model Council</button>
    <button class="btn" id="rescan-btn" onclick="rescan()" title="Rescan all sources">Rescan</button>
  </div>
</header>
<div id="filter-bar">
  <span class="filter-label">Sources</span>
  <div class="chip-group" id="source-chips"></div>
  <div class="filter-sep"></div>
  <span class="filter-label">Models</span>
  <div class="chip-group" id="model-chips"></div>
  <div class="filter-sep"></div>
  <span class="filter-label">Range</span>
  <div class="range-select">
    <select id="range-select" onchange="setRange(this.value)">
      <option value="today">Today</option>
      <option value="week">This Week</option>
      <option value="30d" selected>Last 30 Days</option>
      <option value="90d">Last 90 Days</option>
      <option value="all">All Time</option>
    </select>
  </div>
</div>
<div class="container">
  <div class="stats-row" id="stats-row"></div>
  <div class="charts-grid">
    <div class="chart-card wide" id="sec-daily"><h2>Daily Token Usage by Source</h2><div class="chart-wrap tall"><canvas id="chart-daily"></canvas></div></div>
    <div class="chart-card" id="sec-source"><h2>Tokens by Source</h2><div class="chart-wrap"><canvas id="chart-source"></canvas></div></div>
    <div class="chart-card" id="sec-model"><h2>Tokens by Model</h2><div class="chart-wrap"><canvas id="chart-model"></canvas></div></div>
    <div class="chart-card wide" id="sec-source-daily"><h2>Daily Cost by Source</h2><div class="chart-wrap"><canvas id="chart-cost-daily"></canvas></div></div>
    <div class="chart-card" id="sec-reasoning"><h2>Reasoning Tokens by Source</h2><div class="chart-wrap"><canvas id="chart-reasoning"></canvas></div></div>
    <div class="chart-card" id="sec-cost-model"><h2>Cost by Model</h2><div class="chart-wrap"><canvas id="chart-cost-model"></canvas></div></div>
  </div>
  <div class="table-card" id="sec-sessions">
    <div class="section-title">Recent Sessions</div>
    <table><thead><tr>
      <th>Source</th><th>Project</th><th>Title</th><th>Last Active</th><th>Model</th>
      <th>Turns</th><th>Input</th><th>Output</th><th>Cache</th><th>Cost</th>
    </tr></thead><tbody id="sessions-body"></tbody></table>
    <div style="margin-top:10px;text-align:center;" id="sessions-foot"></div>
  </div>
  <div class="table-card" id="sec-cost-table">
    <div class="section-title">Cost by Model (All Sources)</div>
    <table><thead><tr>
      <th>Source</th><th>Model</th><th>Turns</th><th>Input</th><th>Output</th><th>Cache</th><th>Reasoning</th><th>Cost</th>
    </tr></thead><tbody id="cost-body"></tbody></table>
  </div>
</div>
<div class="footer-content">
  <p>RoutingMagic Usage Dashboard v""" + VERSION + r""" &mdash; Unified view of Claude Code, OpenCode, Hermes, Codex CLI, 9router, and RoutingMagic usage.</p>
  <p>Cost estimates use API pricing. Free models (NVIDIA NIM, OpenRouter :free) show $0.00. RoutingMagic-specific metrics (Caveman savings, Mythos effort) shown separately.</p>
</div>
<script>
const C={text:'#BFBFBF',muted:'#4F4F50',axis:'#6F6F70',border:'#2C2D2E',accent:'#d97757',blue:'#48A0C7',green:'#74C991',red:'#C74E39',purple:'#9B7EC7',amber:'#D9A84E',teal:'#5BB8A3',mauve:'#C77E9B'};
const SOURCE_COLORS={claude:'#d97757',opencode:'#48A0C7','9router':'#9B7EC7',hermes:'#5BB8A3',codex:'#D9A84E',routingmagic:'#74C991'};
const SOURCE_NAMES={claude:'Claude Code',opencode:'OpenCode','9router':'9router',hermes:'Hermes',codex:'Codex CLI',routingmagic:'RoutingMagic'};
let rawData=null,selectedSources=new Set(),selectedModels=new Set(),allModelsList=[],selectedRange='30d',charts={},sessionsLimit=10;

// Export & Insights functions
function exportJSON(){
  const btn=document.getElementById('export-json-btn');
  btn.disabled=true;btn.textContent='Exporting...';
  fetch('/api/export').then(r=>r.json()).then(data=>{
    const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download='routingmagic-usage-'+new Date().toISOString().slice(0,10)+'.json';
    a.click();URL.revokeObjectURL(url);
    btn.disabled=false;btn.textContent='Export JSON';
  }).catch(e=>{btn.disabled=false;btn.textContent='Export JSON';alert('Export failed: '+e);});
}

function exportCSV(){
  const btn=document.getElementById('export-csv-btn');
  btn.disabled=true;btn.textContent='Exporting...';
  fetch('/api/export/csv').then(r=>r.text()).then(csv=>{
    const blob=new Blob([csv],{type:'text/csv'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download='routingmagic-sessions-'+new Date().toISOString().slice(0,10)+'.csv';
    a.click();URL.revokeObjectURL(url);
    btn.disabled=false;btn.textContent='Export CSV';
  }).catch(e=>{btn.disabled=false;btn.textContent='Export CSV';alert('Export failed: '+e);});
}

function showInsights(){
  document.getElementById('insights-modal').classList.add('open');
  document.getElementById('insights-loading').style.display='inline-flex';
  document.getElementById('insights-content').style.display='none';
  fetch('/api/insights').then(r=>r.json()).then(data=>{
    renderInsights(data);
    document.getElementById('insights-loading').style.display='none';
    document.getElementById('insights-content').style.display='block';
  }).catch(e=>{
    document.getElementById('insights-loading').style.display='none';
    document.getElementById('insights-content').innerHTML='<div style="color:var(--red);padding:16px;">Error loading insights: '+e+'</div>';
    document.getElementById('insights-content').style.display='block';
  });
  document.getElementById('insights-modal').classList.add('open');
}

function closeInsights(){
  document.getElementById('insights-modal').classList.remove('open');
}

// ── Model Council ──────────────────────────────────────────────────────────────
function openCouncil(){
  document.getElementById('council-modal').classList.add('open');
  const r=document.getElementById('council-results');r.style.display='none';r.innerHTML='';
  document.getElementById('council-note').style.display='none';
  setTimeout(()=>document.getElementById('council-prompt').focus(),50);
}
function closeCouncil(){
  document.getElementById('council-modal').classList.remove('open');
}
function runCouncil(){
  const prompt=document.getElementById('council-prompt').value.trim();
  if(!prompt){alert('Enter a prompt for the council');return;}
  const btn=document.getElementById('council-run');
  const loading=document.getElementById('council-loading');
  const results=document.getElementById('council-results');
  const note=document.getElementById('council-note');
  btn.disabled=true;loading.style.display='inline-flex';results.style.display='none';note.style.display='none';
  fetch('/api/council',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})})
    .then(resp=>resp.json().then(data=>({ok:resp.ok,status:resp.status,data})))
    .then(({ok,status,data})=>renderCouncilResults(data,status))
    .catch(e=>{
      results.innerHTML='<div style="color:var(--red);padding:16px;">Request failed: '+esc(e.message||String(e))+' &mdash; is the dashboard server running on this port?</div>';
      results.style.display='block';
    })
    .finally(()=>{btn.disabled=false;loading.style.display='none';});
}
function renderCouncilResults(data,status){
  const results=document.getElementById('council-results');
  const note=document.getElementById('council-note');
  if(data && data.error){
    results.innerHTML='<div style="color:var(--red);padding:16px;">'+esc(data.error)+(status?' (HTTP '+status+')':'')+'</div>';
    results.style.display='block';return;
  }
  if(data.degraded_note){note.textContent='⚠ '+data.degraded_note;note.style.display='block';}
  let html='';
  (data.results||[]).forEach((r,i)=>{
    const short=(r.error||'failed').split(':')[0];
    html+='<div class="council-member">'
      +'<div class="council-member-header">'
      +'<span class="council-member-model">'+esc(r.model||('member '+(i+1)))+'</span>'
      +'<span class="council-member-status '+(r.success?'success':'error')+'">'+(r.success?'✓ ok':'✗ '+esc(short))+'</span>'
      +'</div>'
      +'<div class="council-member-content">'+esc(r.success?(r.content||'(no response)'):(r.error||'(failed)'))+'</div>'
      +'</div>';
  });
  if(data.synthesis){
    html+='<div class="council-synthesis"><h4>Synthesis</h4><p>'+esc(data.synthesis)+'</p></div>';
  }
  results.innerHTML=html||'<div style="padding:16px;color:var(--muted);">No council members responded.</div>';
  results.style.display='block';
}

function renderInsights(data){
  const container=document.getElementById('insights-content');
  if(!data.insights || data.insights.length===0){
    container.innerHTML='<div style="padding:20px;color:var(--muted);text-align:center;">No insights available</div>';
    return;
  }
  let html='';
  data.insights.forEach(insight=>{
    html+='<div class="insight-card" style="background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:16px;">';
    html+='<h4 style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--accent);">'+esc(insight.title)+'</h4>';
    if(insight.type==='top_cost_models' || insight.type==='top_projects' || insight.type==='model_efficiency'){
      html+='<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>';
      const keys=Object.keys(insight.data[0]||{});
      keys.forEach(k=>html+='<th style="text-align:left;padding:4px 8px;font-size:10px;text-transform:uppercase;color:var(--muted);">'+esc(k)+'</th>');
      html+='</tr></thead><tbody>';
      insight.data.forEach(row=>{
        html+='<tr>';
        keys.forEach(k=>{
          let v=row[k];
          if(k==='cost' || k==='cost_per_dollar')v=typeof v==='number'?'$'+v.toFixed(2):v;
          if(k==='tokens_per_dollar')v=typeof v==='number'?v.toLocaleString():v;
          if(k==='tokens' || k==='free_tokens' || k==='paid_tokens')v=typeof v==='number'?v.toLocaleString():v;
          html+='<td style="padding:4px 8px;border-bottom:1px solid var(--border);">'+esc(v)+'</td>';
        });
        html+='</tr>';
      });
      html+='</tbody></table>';
    }else if(insight.type==='free_ratio'){
      const d=insight.data;
      html+='<div style="display:flex;gap:16px;margin-top:8px;">';
      html+='<div style="flex:1;background:rgba(110,224,163,0.1);border:1px solid var(--green);border-radius:8px;padding:12px;text-align:center;">';
      html+='<div style="font-size:24px;font-weight:700;color:var(--green);">'+d.free_pct+'%</div>';
      html+='<div style="font-size:11px;color:var(--muted);">Free Usage</div>';
      html+='<div style="font-size:12px;font-family:monospace;">'+d.free_tokens.toLocaleString()+' tokens</div>';
      html+='</div>';
      html+='<div style="flex:1;background:rgba(232,92,78,0.1);border:1px solid var(--red);border-radius:8px;padding:12px;text-align:center;">';
      html+='<div style="font-size:24px;font-weight:700;color:var(--red);">'+(100-d.free_pct).toFixed(1)+'%</div>';
      html+='<div style="font-size:11px;color:var(--muted);">Paid Usage</div>';
      html+='<div style="font-size:12px;font-family:monospace;">'+d.paid_tokens.toLocaleString()+' tokens</div>';
      html+='</div>';
      html+='</div>';
    }else if(insight.type==='daily_trend'){
      html+='<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr>';
      html+='<th style="text-align:left;padding:4px 8px;font-size:10px;text-transform:uppercase;color:var(--muted);">Day</th>';
      html+='<th style="text-align:left;padding:4px 8px;font-size:10px;text-transform:uppercase;color:var(--muted);">Tokens</th>';
      html+='<th style="text-align:left;padding:4px 8px;font-size:10px;text-transform:uppercase;color:var(--muted);">Cost</th>';
      html+='</tr></thead><tbody>';
      insight.data.forEach(r=>html+='<tr><td style="padding:4px 8px;border-bottom:1px solid var(--border);">'+esc(r.day)+'</td><td style="padding:4px 8px;border-bottom:1px solid var(--border);font-family:monospace;">'+r.tokens.toLocaleString()+'</td><td style="padding:4px 8px;border-bottom:1px solid var(--border);color:var(--green);">$'+r.cost.toFixed(2)+'</td></tr>');
      html+='</tbody></table>';
    }else if(insight.type==='budget_health'){
      const statusColors={'healthy':'var(--green)','warning':'var(--amber)','critical':'var(--red)'};
      const c=statusColors[d.status]||'var(--muted)';
      html+='<div style="display:flex;align-items:center;gap:12px;">';
      html+='<div style="width:12px;height:12px;border-radius:50%;background:'+c+';"></div>';
      html+='<div><div style="font-size:14px;font-weight:600;color:'+c+';">'+d.status.toUpperCase()+'</div>';
      html+='<div style="font-size:12px;color:var(--muted);">Monthly: '+d.monthly_pct+'% | Daily: '+d.daily_pct+'%</div></div></div>';
    }
    html+='</div>';
  });
  document.getElementById('insights-content').innerHTML=html;
  document.getElementById('insights-content').style.display='block';
}


function esc(s){const d=document.createElement('div');d.textContent=String(s);return d.innerHTML;}
function fmt(n){if(n>=1e9)return(n/1e9).toFixed(1)+'B';if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(1)+'K';return String(n);}
function fmtCost(c){return c===0?'$0.00':c<0.01?'<$0.01':'$'+c.toFixed(2);}

function isFiltered(r){
  if(selectedSources.size>0&&!selectedSources.has(r.source))return false;
  if(selectedModels.size>0&&!selectedModels.has(r.model))return false;
  return true;
}
function filterByRange(rows){
  if(selectedRange==='all')return rows;
  const now=new Date();
  let cutoff;
  switch(selectedRange){
    case'today':cutoff=new Date(now.getFullYear(),now.getMonth(),now.getDate());break;
    case'week':cutoff=new Date(now-7*864e5);break;
    case'30d':cutoff=new Date(now-30*864e5);break;
    case'90d':cutoff=new Date(now-90*864e5);break;
    default:cutoff=new Date(0);
  }
  const co=cutoff.toISOString().slice(0,10);
  return rows.filter(r=>(r.day||r.last_date||r.timestamp||'').slice(0,10)>=co);
}

function setRange(v){selectedRange=v;render();}
function toggleSource(s){
  if(selectedSources.has(s))selectedSources.delete(s);else selectedSources.add(s);
  renderSourceChips();render();
}
function toggleModel(m){
  if(selectedModels.has(m))selectedModels.delete(m);else selectedModels.add(m);
  renderModelChips();render();
}

function renderSourceChips(){
  const el=document.getElementById('source-chips');
  if(!rawData||!rawData.sources){el.innerHTML='';return;}
  el.innerHTML=rawData.sources.map(s=>{
    const active=selectedSources.size===0||selectedSources.has(s.source);
    return `<button class="chip ${active?'active':''}" onclick="toggleSource('${s.source}')" style="${active?'':'opacity:0.5'}"><span class="dot" style="background:${SOURCE_COLORS[s.source]||'#666'}"></span>${SOURCE_NAMES[s.source]||s.source} (${fmt(s.tokens)})</button>`;
  }).join('');
}
function renderModelChips(){
  const el=document.getElementById('model-chips');
  if(!rawData||!rawData.all_models){el.innerHTML='';return;}
  const top10=rawData.all_models.slice(0,12);
  el.innerHTML=top10.map(m=>{
    const active=selectedModels.size===0||selectedModels.has(m.model);
    const short=m.model.length>25?m.model.slice(0,25)+'...':m.model;
    return `<button class="chip ${active?'active':''}" onclick="toggleModel('${esc(m.model)}')" style="${active?'':'opacity:0.5'}"><span class="dot" style="background:${SOURCE_COLORS[m.source]||'#666'}"></span>${esc(short)}</button>`;
  }).join('');
}

function renderStats(){
  const el=document.getElementById('stats-row');
  if(!rawData){el.innerHTML='';return;}
  let daily=filterByRange(rawData.daily_by_model);
  daily=daily.filter(r=>isFiltered(r));
  let sessions=filterByRange(rawData.sessions_all);
  sessions=sessions.filter(r=>isFiltered(r));

  const totalInput=daily.reduce((s,r)=>s+r.input,0);
  const totalOutput=daily.reduce((s,r)=>s+r.output,0);
  const totalCache=daily.reduce((s,r)=>s+r.cache_read+r.cache_write,0);
  const totalReasoning=daily.reduce((s,r)=>s+r.reasoning,0);
  const totalTurns=daily.reduce((s,r)=>s+r.turns,0);
  const totalCost=sessions.reduce((s,r)=>s+(r.cost||0),0);
  const freeTurns=daily.filter(r=>r.model.indexOf(':free')>-1||r.source==='routingmagic').reduce((s,r)=>s+r.turns,0);
  const freePct=totalTurns>0?Math.round(freeTurns/totalTurns*100):0;

  const sources=new Set(daily.map(r=>r.source));

  el.innerHTML=`
    <div class="stat-card"><div class="label">Total Turns</div><div class="value">${fmt(totalTurns)}</div><div class="sub">${sources.size} source${sources.size!==1?'s':''}</div></div>
    <div class="stat-card"><div class="label">Input Tokens</div><div class="value">${fmt(totalInput)}</div><div class="sub">prompt tokens</div></div>
    <div class="stat-card"><div class="label">Output Tokens</div><div class="value">${fmt(totalOutput)}</div><div class="sub">generated tokens</div></div>
    <div class="stat-card"><div class="label">Cache</div><div class="value">${fmt(totalCache)}</div><div class="sub">read + write</div></div>
    <div class="stat-card"><div class="label">Reasoning</div><div class="value">${fmt(totalReasoning)}</div><div class="sub">thinking tokens</div></div>
    <div class="stat-card"><div class="label">Est. Cost</div><div class="value">${fmtCost(totalCost)}</div><div class="sub">API pricing equiv.</div></div>
    <div class="stat-card"><div class="label">Free Usage</div><div class="value">${freePct}%</div><div class="sub">${fmt(freeTurns)} free turns</div></div>
    <div class="stat-card"><div class="label">Sessions</div><div class="value">${sessions.length}</div><div class="sub">${selectedRange}</div></div>`;
}

function destroyChart(key){if(charts[key]){charts[key].destroy();delete charts[key];}}

function renderDailyChart(){
  destroyChart('daily');
  let daily=filterByRange(rawData.daily_by_model).filter(r=>isFiltered(r));
  const byDay={};
  daily.forEach(r=>{if(!byDay[r.day])byDay[r.day]={};byDay[r.day][r.source]=(byDay[r.day][r.source]||0)+r.input+r.output;});
  const days=Object.keys(byDay).sort();
  const sources=[...new Set(daily.map(r=>r.source))];
  const datasets=sources.map(s=>({label:SOURCE_NAMES[s]||s,data:days.map(d=>byDay[d][s]||0),backgroundColor:SOURCE_COLORS[s]+'cc',borderColor:SOURCE_COLORS[s],borderWidth:1}));
  charts.daily=new Chart(document.getElementById('chart-daily'),{type:'bar',data:{labels:days,datasets},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:C.axis,font:{size:10}}}},scales:{x:{stacked:true,ticks:{color:C.muted,font:{size:9}},grid:{color:C.border}},y:{stacked:true,ticks:{color:C.muted,font:{size:9},callback:v=>fmt(v)},grid:{color:C.border}}}}});
}

function renderSourcePie(){
  destroyChart('source');
  let daily=filterByRange(rawData.daily_by_model).filter(r=>isFiltered(r));
  const bySrc={};daily.forEach(r=>{bySrc[r.source]=(bySrc[r.source]||0)+r.input+r.output;});
  const srcs=Object.keys(bySrc);
  charts.source=new Chart(document.getElementById('chart-source'),{type:'doughnut',data:{labels:srcs.map(s=>SOURCE_NAMES[s]||s),datasets:[{data:srcs.map(s=>bySrc[s]),backgroundColor:srcs.map(s=>(SOURCE_COLORS[s]||'#666')+'cc'),borderColor:'#161617',borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{color:C.axis,font:{size:10},padding:8}}}}});
}

function renderModelBar(){
  destroyChart('model');
  let daily=filterByRange(rawData.daily_by_model).filter(r=>isFiltered(r));
  const byM={};daily.forEach(r=>{byM[r.model]=(byM[r.model]||0)+r.input+r.output;});
  const sorted=Object.entries(byM).sort((a,b)=>b[1]-a[1]).slice(0,10);
  const colors=sorted.map(([m])=>{for(const s in SOURCE_COLORS){if(m.toLowerCase().includes(s))return SOURCE_COLORS[s];}return C.blue;});
  charts.model=new Chart(document.getElementById('chart-model'),{type:'bar',data:{labels:sorted.map(([m])=>m.length>20?m.slice(0,20)+'...':m),datasets:[{data:sorted.map(([,v])=>v),backgroundColor:colors.map(c=>c+'cc'),borderColor:colors,borderWidth:1}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{color:C.muted,font:{size:9},callback:v=>fmt(v)},grid:{color:C.border}},y:{ticks:{color:C.axis,font:{size:9}},grid:{display:false}}}}});
}

function renderCostDaily(){
  destroyChart('costDaily');
  let sessions=filterByRange(rawData.sessions_all).filter(r=>isFiltered(r));
  const byDaySrc={};
  sessions.forEach(r=>{const d=r.last_date;if(!byDaySrc[d])byDaySrc[d]={};byDaySrc[d][r.source]=(byDaySrc[d][r.source]||0)+(r.cost||0);});
  const days=Object.keys(byDaySrc).sort();
  const sources=[...new Set(sessions.map(r=>r.source))];
  const datasets=sources.map(s=>({label:SOURCE_NAMES[s]||s,data:days.map(d=>byDaySrc[d]?.[s]||0),backgroundColor:SOURCE_COLORS[s]+'cc',borderColor:SOURCE_COLORS[s],borderWidth:1}));
  charts.costDaily=new Chart(document.getElementById('chart-cost-daily'),{type:'bar',data:{labels:days,datasets},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:C.axis,font:{size:10}}}},scales:{x:{stacked:true,ticks:{color:C.muted,font:{size:9}},grid:{color:C.border}},y:{stacked:true,ticks:{color:C.muted,font:{size:9},callback:v=>fmtCost(v)},grid:{color:C.border}}}}});
}

function renderReasoning(){
  destroyChart('reasoning');
  let daily=filterByRange(rawData.daily_by_model).filter(r=>isFiltered(r));
  const bySrc={};daily.forEach(r=>{bySrc[r.source]=(bySrc[r.source]||0)+r.reasoning;});
  const srcs=Object.keys(bySrc).filter(s=>bySrc[s]>0);
  if(srcs.length===0){document.getElementById('chart-reasoning').parentElement.style.display='none';return;}
  document.getElementById('chart-reasoning').parentElement.style.display='';
  charts.reasoning=new Chart(document.getElementById('chart-reasoning'),{type:'doughnut',data:{labels:srcs.map(s=>SOURCE_NAMES[s]||s),datasets:[{data:srcs.map(s=>bySrc[s]),backgroundColor:srcs.map(s=>(SOURCE_COLORS[s]||'#666')+'cc'),borderColor:'#161617',borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{color:C.axis,font:{size:10},padding:8}}}}});
}

function renderCostModel(){
  destroyChart('costModel');
  let sessions=filterByRange(rawData.sessions_all).filter(r=>isFiltered(r));
  const byM={};sessions.forEach(r=>{byM[r.model]=(byM[r.model]||0)+(r.cost||0);});
  const sorted=Object.entries(byM).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]).slice(0,8);
  if(sorted.length===0){document.getElementById('chart-cost-model').parentElement.style.display='none';return;}
  document.getElementById('chart-cost-model').parentElement.style.display='';
  charts.costModel=new Chart(document.getElementById('chart-cost-model'),{type:'doughnut',data:{labels:sorted.map(([m])=>m.length>25?m.slice(0,25)+'...':m),datasets:[{data:sorted.map(([,v])=>v),backgroundColor:[C.accent,C.blue,C.green,C.purple,C.amber,C.teal,C.mauve,C.red],borderColor:'#161617',borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right',labels:{color:C.axis,font:{size:10},padding:6}}}}});
}

function renderSessions(){
  const body=document.getElementById('sessions-body');
  const foot=document.getElementById('sessions-foot');
  if(!rawData){body.innerHTML='';foot.innerHTML='';return;}
  let sessions=filterByRange(rawData.sessions_all).filter(r=>isFiltered(r));
  sessions.sort((a,b)=>(b.last||'').localeCompare(a.last||''));
  const shown=sessions.slice(0,sessionsLimit);
  body.innerHTML=shown.map(r=>{
    const costStr=r.cost>0?fmtCost(r.cost):'<span class="free-tag">FREE</span>';
    const topic=r.topic ? esc(r.topic) : '<span class="muted">untitled</span>';
    return `<tr>
      <td><span class="source-tag source-${r.source}">${SOURCE_NAMES[r.source]||r.source}</span></td>
      <td class="topic-cell">${esc(r.project)}</td>
      <td class="topic-cell">${topic}</td>
      <td class="muted">${esc(r.last)}</td>
      <td><span class="model-tag">${esc(r.model)}</span></td>
      <td class="num">${r.turns}</td>
      <td class="num">${fmt(r.input)}</td>
      <td class="num">${fmt(r.output)}</td>
      <td class="num">${fmt(r.cache_read+r.cache_write)}</td>
      <td class="cost">${costStr}</td>
    </tr>`;
  }).join('');
  if(sessions.length>sessionsLimit){
    foot.innerHTML=`<button class="show-more-btn" onclick="sessionsLimit+=15;renderSessions()">Show ${Math.min(15,sessions.length-sessionsLimit)} more</button>`;
  }else{foot.innerHTML='';}
}

function renderCostTable(){
  const body=document.getElementById('cost-body');
  if(!rawData){body.innerHTML='';return;}
  let sessions=filterByRange(rawData.sessions_all).filter(r=>isFiltered(r));
  const bySM={};
  sessions.forEach(r=>{
    const k=r.source+'|'+r.model;
    if(!bySM[k])bySM[k]={source:r.source,model:r.model,turns:0,input:0,output:0,cache:0,reasoning:0,cost:0};
    const b=bySM[k];b.turns+=r.turns;b.input+=r.input;b.output+=r.output;b.cache+=r.cache_read+r.cache_write;b.reasoning+=r.reasoning;b.cost+=r.cost||0;
  });
  const rows=Object.values(bySM).sort((a,b)=>b.cost-a.cost);
  body.innerHTML=rows.map(r=>{
    const costStr=r.cost>0?fmtCost(r.cost):'<span class="free-tag">FREE</span>';
    return `<tr>
      <td><span class="source-tag source-${r.source}">${SOURCE_NAMES[r.source]||r.source}</span></td>
      <td><span class="model-tag">${esc(r.model)}</span></td>
      <td class="num">${r.turns}</td>
      <td class="num">${fmt(r.input)}</td>
      <td class="num">${fmt(r.output)}</td>
      <td class="num">${fmt(r.cache)}</td>
      <td class="num">${fmt(r.reasoning)}</td>
      <td class="cost">${costStr}</td>
    </tr>`;
  }).join('');
}

function render(){
  renderStats();renderDailyChart();renderSourcePie();renderModelBar();
  renderCostDaily();renderReasoning();renderCostModel();
  renderSessions();renderCostTable();
}

function rescan(){
  document.getElementById('rescan-btn').disabled=true;
  document.getElementById('rescan-btn').textContent='Scanning...';
  fetch('/api/rescan').then(()=>setTimeout(()=>loadData().then(()=>{document.getElementById('rescan-btn').disabled=false;document.getElementById('rescan-btn').textContent='\u21bb Rescan';}),2000));
}

function loadData(){
  return fetch('/api/data').then(r=>r.json()).then(data=>{
    if(data.error){document.getElementById('meta').textContent=data.error;return;}
    rawData=data;
    document.getElementById('meta').textContent=`Updated: ${data.generated_at}`;
    allModelsList=data.all_models||[];
    renderSourceChips();renderModelChips();render();
  });
}

setInterval(loadData,30000);
loadData();
</script>

<!-- Insights Modal -->
<div class="modal-overlay" id="insights-modal">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title">Insights</span>
      <button class="modal-close" onclick="closeInsights()">&times;</button>
    </div>
    <div class="modal-body" id="insights-body">
      <div class="loading" id="insights-loading"><div class="spinner"></div>Loading insights...</div>
      <div id="insights-content" style="display:none;"></div>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="closeInsights()">Close</button>
    </div>
  </div>
</div>

<!-- Council Modal -->
<div class="modal-overlay" id="council-modal">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title">Model Council</span>
      <button class="modal-close" onclick="closeCouncil()">&times;</button>
    </div>
    <div class="modal-body">
      <textarea class="council-prompt" id="council-prompt" placeholder="Ask the council a question. It queries 3 free models from the live registry in parallel, then synthesises one answer."></textarea>
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;">
        <button class="btn primary" id="council-run" onclick="runCouncil()">Run Council</button>
        <span class="loading" id="council-loading" style="display:none;"><span class="spinner"></span>Deliberating&hellip;</span>
      </div>
      <div class="council-note" id="council-note" style="display:none;"></div>
      <div class="council-results" id="council-results" style="display:none;"></div>
    </div>
    <div class="modal-footer">
      <button class="btn" onclick="closeCouncil()">Close</button>
    </div>
  </div>
</div>

</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI entry point
# ═══════════════════════════════════════════════════════════════════════════════

def serve(host="localhost", port=9898):
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"Dashboard running at http://{host}:{port}")
    server.serve_forever()




def export_data() -> dict:
    """Export all usage data as JSON for sharing/collaboration."""
    from unified_scanner import get_db, init_db, DB_PATH
    import json
    
    if not DB_PATH.exists():
        return {"error": "Database not found"}
    
    conn = get_db(DB_PATH)
    init_db(conn)
    
    turns = conn.execute("SELECT * FROM unified_turns ORDER BY timestamp").fetchall()
    sessions = conn.execute("SELECT * FROM unified_sessions ORDER BY last_timestamp").fetchall()
    scan_state = conn.execute("SELECT * FROM scan_state").fetchall()
    adapter_state = conn.execute("SELECT * FROM adapter_state").fetchall()
    quota_snapshots = conn.execute("SELECT * FROM quota_snapshots ORDER BY timestamp DESC LIMIT 100").fetchall()
    budget_alerts = conn.execute("SELECT * FROM budget_alerts ORDER BY timestamp DESC LIMIT 100").fetchall()
    
    conn.close()
    
    def row_to_dict(row):
        return {k: row[k] for k in row.keys()}
    
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": "2.0",
        "turns": [row_to_dict(r) for r in turns],
        "sessions": [row_to_dict(r) for r in sessions],
        "scan_state": [row_to_dict(r) for r in scan_state],
        "adapter_state": [row_to_dict(r) for r in adapter_state],
        "quota_snapshots": [row_to_dict(r) for r in quota_snapshots],
        "budget_alerts": [row_to_dict(r) for r in budget_alerts],
    }


def export_csv() -> str:
    """Export usage data as CSV for spreadsheet analysis."""
    from unified_scanner import get_db, init_db, DB_PATH
    import csv
    import io
    
    if not DB_PATH.exists():
        return "error,Database not found\n"
    
    conn = get_db(DB_PATH)
    init_db(conn)
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(["session_id", "source", "project", "first_timestamp", "last_timestamp",
                     "model", "turns", "input_tokens", "output_tokens", 
                     "cache_read", "cache_write", "reasoning_tokens", "cost", "topic"])
    
    rows = conn.execute("""
        SELECT session_id, source, project, first_timestamp, last_timestamp,
               model, turn_count, total_input, total_output,
               total_cache_read, total_cache_write, total_reasoning, total_cost, topic
        FROM unified_sessions ORDER BY last_timestamp DESC
    """).fetchall()
    
    for r in rows:
        writer.writerow([
            r["session_id"], r["source"], r["project"], r["first_timestamp"], r["last_timestamp"],
            r["model"], r["turn_count"], r["total_input"], r["total_output"],
            r["total_cache_read"], r["total_cache_write"], r["total_reasoning"], 
            r["total_cost"], r["topic"] or ""
        ])
    
    conn.close()
    return output.getvalue()


def get_insights() -> dict:
    """Generate actionable insights from usage data."""
    from unified_scanner import get_db, init_db, DB_PATH
    from datetime import datetime, timezone, timedelta
    from dashboard_server import get_budget_status
    
    if not DB_PATH.exists():
        return {"error": "Database not found"}
    
    conn = get_db(DB_PATH)
    init_db(conn)
    
    now = datetime.now(timezone.utc)
    week_ago = (now - timedelta(days=7)).isoformat()
    month_ago = (now - timedelta(days=30)).isoformat()
    
    insights = []
    
    # 1. Most expensive models
    top_cost = conn.execute("""
        SELECT source, model, SUM(cost) as total_cost, SUM(input_tokens + output_tokens) as tokens
        FROM unified_turns WHERE cost > 0
        GROUP BY source, model ORDER BY total_cost DESC LIMIT 5
    """).fetchall()
    if top_cost:
        insights.append({
            "type": "top_cost_models",
            "title": "Most Expensive Models",
            "data": [{"model": f"{r['source']}/{r['model']}", "cost": round(r["total_cost"], 4), "tokens": r["tokens"]} for r in top_cost]
        })
    
    # 2. Free vs paid ratio
    free_stats = conn.execute("""
        SELECT 
            SUM(CASE WHEN source='routingmagic' OR model LIKE '%:free%' OR model LIKE '%/nemotron-%' OR model LIKE '%/big-pickle%' OR model LIKE '%/gpt-oss%' THEN input_tokens+output_tokens ELSE 0 END) as free_tokens,
            SUM(input_tokens + output_tokens) as total_tokens
        FROM unified_turns
    """).fetchone()
    if free_stats and free_stats["total_tokens"]:
        free_pct = (free_stats["free_tokens"] / free_stats["total_tokens"]) * 100
        insights.append({
            "type": "free_ratio",
            "title": "Free vs Paid Usage",
            "data": {"free_pct": round(free_pct, 1), "free_tokens": free_stats["free_tokens"], "paid_tokens": free_stats["total_tokens"] - free_stats["free_tokens"]}
        })
    
    # 3. Daily trend (last 7 days)
    daily = conn.execute("""
        SELECT substr(timestamp, 1, 10) as day, SUM(input_tokens + output_tokens) as tokens, SUM(cost) as cost
        FROM unified_turns WHERE timestamp >= ? GROUP BY day ORDER BY day
    """, (week_ago,)).fetchall()
    if daily:
        insights.append({
            "type": "daily_trend",
            "title": "Last 7 Days Trend",
            "data": [{"day": r["day"], "tokens": r["tokens"], "cost": round(r["cost"], 4)} for r in daily]
        })
    
    # 4. Top projects by cost
    projects = conn.execute("""
        SELECT project, SUM(cost) as cost, SUM(input_tokens + output_tokens) as tokens, COUNT(DISTINCT session_id) as sessions
        FROM unified_turns GROUP BY project ORDER BY cost DESC LIMIT 10
    """).fetchall()
    if projects:
        insights.append({
            "type": "top_projects",
            "title": "Top Projects by Cost",
            "data": [{"project": r["project"], "cost": round(r["cost"], 4), "tokens": r["tokens"], "sessions": r["sessions"]} for r in projects]
        })
    
    # 5. Model efficiency (tokens per $)
    efficiency = conn.execute("""
        SELECT source, model, 
               SUM(input_tokens + output_tokens) * 1.0 / NULLIF(SUM(cost), 0) as tokens_per_dollar,
               SUM(cost) as cost
        FROM unified_turns WHERE cost > 0
        GROUP BY source, model HAVING cost > 0.01
        ORDER BY tokens_per_dollar DESC LIMIT 10
    """).fetchall()
    if efficiency:
        insights.append({
            "type": "model_efficiency",
            "title": "Most Efficient Models (Tokens/$)",
            "data": [{"model": f"{r['source']}/{r['model']}", "tokens_per_dollar": round(r["tokens_per_dollar"], 0), "cost": round(r["cost"], 4)} for r in efficiency]
        })
    
    # 6. Budget health
    budget = get_budget_status()
    budget_health = "healthy"
    if budget["monthly"]["pct"] >= 90:
        budget_health = "critical"
    elif budget["monthly"]["pct"] >= 75:
        budget_health = "warning"
    insights.append({
        "type": "budget_health",
        "title": "Budget Health",
        "data": {"status": budget_health, "monthly_pct": round(budget["monthly"]["pct"], 1), "daily_pct": round(budget["daily"]["pct"], 1)}
    })
    
    conn.close()
    
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "insights": insights,
    }




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
            print(f"  --port   Port (default: 9898)")
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

    serve(host=host, port=port)


if __name__ == "__main__":
    main()


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

