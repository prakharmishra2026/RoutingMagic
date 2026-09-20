"""Council self-maintenance: strike accounting, benching, retirement, roster guard.

Root cause this encodes (Investogram wrong-consensus post-mortem): the bad run was
caused by a CONTAMINATED PROMPT, not model weakness. The orchestrator listed the
suspected defects inside the prompt and all four models echoed them back. Therefore
``prompt_echo`` is a first-class outcome that is IGNORED and NEVER counts as a strike.

Strike rules (mirrored in README "Council Self-Maintenance"):

* A strike is recorded ONLY for: empty_content, timeout, provider_error,
  wrong_finding_verified.
* prompt_echo and ok never strike.
* 3 strikes inside a rolling 14-day window bench the model.
* Strikes older than 14 days expire (pruned on every read/write).
* A run where EVERY member fails is an infrastructure fault: nobody is struck.
* A model benched twice inside 60 days is retired.
* Newly added models get a 3-run grace period where only empty_content or
  timeout strike (provider_error / wrong_finding_verified are exempt).
* When benching would drop ACTIVE below 3, candidates are probed first and the
  best passers promoted. If no candidate passes, the bench is withheld and
  LOW_ROSTER_HOLD is logged.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = _HERE / "council_registry.json"

MIN_ACTIVE = 3
STRIKE_WINDOW_DAYS = 14
RETIRE_WINDOW_DAYS = 60
GRACE_RUNS = 3

STRIKE_OUTCOMES = frozenset(
    {"empty_content", "timeout", "provider_error", "wrong_finding_verified"}
)
GRACE_STRIKE_OUTCOMES = frozenset({"empty_content", "timeout"})
NEVER_STRIKE_OUTCOMES = frozenset({"ok", "prompt_echo"})
FAILURE_OUTCOMES = STRIKE_OUTCOMES


class RegistryUnreadable(Exception):
    """Raised when council_registry.json cannot be loaded."""


# ── time helpers ────────────────────────────────────────────────────────────

def _utcnow(now: Optional[datetime] = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    return now if now.tzinfo else now.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── registry IO ─────────────────────────────────────────────────────────────

def registry_path(path: Optional[Path] = None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get("COUNCIL_REGISTRY_PATH")
    return Path(env) if env else DEFAULT_REGISTRY_PATH


def load_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the registry or raise :class:`RegistryUnreadable`."""
    target = registry_path(path)
    try:
        with open(target, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        raise RegistryUnreadable(str(exc)) from exc
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        raise RegistryUnreadable("registry missing 'models' object")
    data.setdefault("min_active", MIN_ACTIVE)
    data.setdefault("strike_window_days", STRIKE_WINDOW_DAYS)
    data.setdefault("retire_window_days", RETIRE_WINDOW_DAYS)
    data.setdefault("grace_runs", GRACE_RUNS)
    return data


def try_load_registry(path: Optional[Path] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Non-throwing load: ``(registry, None)`` or ``(None, error)``."""
    try:
        return load_registry(path), None
    except RegistryUnreadable as exc:
        return None, str(exc)


def save_registry(registry: Dict[str, Any], path: Optional[Path] = None) -> None:
    target = registry_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".council_registry.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(registry, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── roster queries ──────────────────────────────────────────────────────────

def active_models(registry: Optional[Dict[str, Any]]) -> List[str]:
    if not registry:
        return []
    return [
        mid
        for mid, entry in registry.get("models", {}).items()
        if entry.get("status") == "active"
    ]


def roster_for_council(
    registry: Optional[Dict[str, Any]],
) -> List[Tuple[str, str]]:
    """Return ``[(provider, model_id), ...]`` for active members, insertion order."""
    if not registry:
        return []
    out: List[Tuple[str, str]] = []
    for mid, entry in registry.get("models", {}).items():
        if entry.get("status") == "active":
            out.append((entry.get("provider", "openrouter"), mid))
    return out


# ── strike bookkeeping ──────────────────────────────────────────────────────

def _prune_strikes(entry: Dict[str, Any], now: datetime) -> None:
    window = timedelta(days=STRIKE_WINDOW_DAYS)
    kept = []
    for strike in entry.get("strikes", []):
        when = _parse(strike.get("date"))
        if when is None or (now - when) <= window:
            kept.append(strike)
    entry["strikes"] = kept


def _prune_benches(entry: Dict[str, Any], now: datetime) -> None:
    window = timedelta(days=RETIRE_WINDOW_DAYS)
    kept = []
    for when in entry.get("bench_history", []):
        parsed = _parse(when)
        if parsed is None or (now - parsed) <= window:
            kept.append(when)
    entry["bench_history"] = kept


def _log(log: Callable[[str], None], message: str) -> None:
    try:
        log(message)
    except Exception:
        pass


# ── promotion / probing ─────────────────────────────────────────────────────

def _default_prober():
    from probe_candidates import probe_openrouter_candidates  # lazy import

    return probe_openrouter_candidates()


def _promote(registry: Dict[str, Any], candidate: Dict[str, Any], now: datetime) -> str:
    model_id = candidate["model"]
    models = registry.setdefault("models", {})
    entry = models.get(model_id)
    if entry is None:
        models[model_id] = {
            "provider": candidate.get("provider", "openrouter"),
            "added_at": _iso(now),
            "last_verified": _iso(now),
            "status": "active",
            "runs_observed": 0,
            "probe_score": candidate.get("probe_score", {}),
            "strikes": [],
            "bench_history": [],
        }
    else:
        entry["status"] = "active"
        entry["last_verified"] = _iso(now)
        entry["probe_score"] = candidate.get("probe_score", entry.get("probe_score", {}))
        entry["strikes"] = []
    return model_id


def probe_and_promote(
    registry: Dict[str, Any],
    needed: int,
    now: datetime,
    prober: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None,
    log: Callable[[str], None] = print,
) -> List[str]:
    """Probe candidates and promote up to ``needed`` best-scoring passers."""
    if needed <= 0:
        return []
    if prober is None:
        try:
            prober = _default_prober
        except Exception as exc:  # pragma: no cover - import guard
            _log(log, f"COUNCIL_PROBE_UNAVAILABLE {exc}")
            return []
    try:
        scored = list(prober() or [])
    except Exception as exc:
        _log(log, f"COUNCIL_PROBE_FAILED {exc}")
        return []

    passers = sorted(
        (c for c in scored if c.get("passed")),
        key=lambda c: c.get("probe_score", {}).get("score", 0.0),
        reverse=True,
    )
    promoted: List[str] = []
    for candidate in passers:
        if len(promoted) >= needed:
            break
        promoted.append(_promote(registry, candidate, now))
    return promoted


# ── bench / retire ──────────────────────────────────────────────────────────

def _bench_or_retire(
    registry: Dict[str, Any],
    model_id: str,
    entry: Dict[str, Any],
    now: datetime,
    prober: Optional[Callable[[], Sequence[Dict[str, Any]]]],
    log: Callable[[str], None],
) -> Dict[str, Any]:
    others = [m for m in active_models(registry) if m != model_id]
    needed = max(0, MIN_ACTIVE - len(others))

    promoted: List[str] = []
    if needed > 0:
        promoted = probe_and_promote(registry, needed, now, prober=prober, log=log)
        if len(others) + len(promoted) < MIN_ACTIVE:
            _log(
                log,
                f"LOW_ROSTER_HOLD model={model_id} active_without_this={len(others)} "
                f"promoted={len(promoted)} needed={MIN_ACTIVE} — bench withheld",
            )
            return {"benched": False, "retired": False, "promoted": promoted,
                    "low_roster_hold": True}

    _prune_benches(entry, now)
    entry.setdefault("bench_history", []).append(_iso(now))
    entry["status"] = "retired" if len(entry["bench_history"]) >= 2 else "benched"
    entry["strikes"] = []
    outcome = {"benched": entry["status"] == "benched",
               "retired": entry["status"] == "retired",
               "promoted": promoted, "low_roster_hold": False}
    _log(log, f"COUNCIL_{'RETIRE' if outcome['retired'] else 'BENCH'} model={model_id}")
    return outcome


# ── core outcome application ────────────────────────────────────────────────

def classify_result(result: Dict[str, Any]) -> str:
    """Map a council member result (or explicit outcome) to a strike outcome."""
    explicit = result.get("outcome")
    if explicit in STRIKE_OUTCOMES or explicit in NEVER_STRIKE_OUTCOMES:
        return explicit
    if result.get("success"):
        return "ok"
    error = str(result.get("error", "")).lower()
    if "timeout" in error or "timed out" in error:
        return "timeout"
    if "empty" in error:
        return "empty_content"
    return "provider_error"


def apply_outcome(
    registry: Dict[str, Any],
    run_id: str,
    model_id: str,
    outcome: str,
    now: datetime,
    prober: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None,
    log: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """Apply one outcome to one model. Mutates ``registry``; returns an action dict."""
    models = registry.get("models", {})
    entry = models.get(model_id)
    if entry is None:
        _log(log, f"COUNCIL_UNKNOWN_MODEL {model_id} run={run_id}")
        return {"model": model_id, "strike": False, "benched": False,
                "retired": False, "reason": "unknown_model"}

    if outcome == "prompt_echo":
        _log(log, f"COUNCIL_PROMPT_ECHO_IGNORED model={model_id} run={run_id}")
        return {"model": model_id, "strike": False, "benched": False,
                "retired": False, "reason": "prompt_echo"}

    entry["last_verified"] = _iso(now)
    _prune_strikes(entry, now)
    prior_runs = int(entry.get("runs_observed", 0))
    entry["runs_observed"] = prior_runs + 1

    if outcome == "ok":
        return {"model": model_id, "strike": False, "benched": False,
                "retired": False, "reason": "ok"}

    if outcome not in STRIKE_OUTCOMES:
        return {"model": model_id, "strike": False, "benched": False,
                "retired": False, "reason": f"non_strike_outcome:{outcome}"}

    in_grace = prior_runs < registry.get("grace_runs", GRACE_RUNS)
    if in_grace and outcome not in GRACE_STRIKE_OUTCOMES:
        _log(log, f"COUNCIL_GRACE_EXEMPT model={model_id} outcome={outcome} run={run_id}")
        return {"model": model_id, "strike": False, "benched": False,
                "retired": False, "reason": "grace_exempt"}

    entry.setdefault("strikes", []).append(
        {"run_id": run_id, "date": _iso(now), "reason": outcome}
    )
    if len(entry["strikes"]) < 3:
        return {"model": model_id, "strike": True, "benched": False,
                "retired": False,
                "reason": f"strike {len(entry['strikes'])}/3"}

    bench = _bench_or_retire(registry, model_id, entry, now, prober, log)
    bench.update({"model": model_id, "strike": True,
                  "reason": bench.get("reason", "threshold")})
    return bench


def record_run(
    run_id: str,
    model: str,
    outcome: str,
    registry_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    prober: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None,
    log: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """Record one model's outcome. Never raises on unreadable registry."""
    moment = _utcnow(now)
    registry, error = try_load_registry(registry_path)
    if registry is None:
        _log(log, f"COUNCIL_REGISTRY_UNREADABLE {error} — run {run_id} not recorded")
        return {"ok": False, "error": error, "model": model, "run_id": run_id}

    action = apply_outcome(registry, run_id, model, outcome, moment,
                           prober=prober, log=log)
    try:
        registry["updated_at"] = _iso(moment)
        save_registry(registry, registry_path)
    except OSError as exc:
        _log(log, f"COUNCIL_REGISTRY_WRITE_FAILED {exc}")
        return {**action, "ok": False, "error": str(exc)}
    return {**action, "ok": True}


def record_council_results(
    run_id: str,
    results: Iterable[Dict[str, Any]],
    registry_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    prober: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None,
    log: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """Record a whole council run.

    If EVERY member failed, the run is an infrastructure fault and no member is
    struck. Otherwise strikeable failures are applied per member.
    """
    moment = _utcnow(now)
    classified = [
        (r.get("model", "unknown"), classify_result(r)) for r in results
    ]
    if not classified:
        return {"ok": True, "infrastructure_fault": False, "actions": []}

    if all(outcome in FAILURE_OUTCOMES for _, outcome in classified):
        _log(log, f"COUNCIL_INFRA_FAULT run={run_id} — all {len(classified)} members "
                  "failed; no strikes recorded")
        return {"ok": True, "infrastructure_fault": True, "actions": []}

    registry, error = try_load_registry(registry_path)
    if registry is None:
        _log(log, f"COUNCIL_REGISTRY_UNREADABLE {error} — run {run_id} not recorded")
        return {"ok": False, "error": error, "infrastructure_fault": False, "actions": []}

    actions = []
    for model_id, outcome in classified:
        if outcome in NEVER_STRIKE_OUTCOMES:
            apply_outcome(registry, run_id, model_id, outcome, moment,
                          prober=prober, log=log)
            continue
        actions.append(apply_outcome(registry, run_id, model_id, outcome, moment,
                                     prober=prober, log=log))
    try:
        registry["updated_at"] = _iso(moment)
        save_registry(registry, registry_path)
    except OSError as exc:
        _log(log, f"COUNCIL_REGISTRY_WRITE_FAILED {exc}")
        return {"ok": False, "error": str(exc), "infrastructure_fault": False,
                "actions": actions}
    return {"ok": True, "infrastructure_fault": False, "actions": actions}


def ensure_min_active(
    registry_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    prober: Optional[Callable[[], Sequence[Dict[str, Any]]]] = None,
    log: Callable[[str], None] = print,
) -> Dict[str, Any]:
    """Top the roster back up to MIN_ACTIVE using benchmark passers."""
    moment = _utcnow(now)
    registry, error = try_load_registry(registry_path)
    if registry is None:
        return {"ok": False, "error": error, "promoted": []}
    needed = max(0, MIN_ACTIVE - len(active_models(registry)))
    promoted = probe_and_promote(registry, needed, moment, prober=prober, log=log)
    if needed and not promoted:
        _log(log, f"LOW_ROSTER_HOLD active={len(active_models(registry))} "
                  f"needed={needed} — no candidate passed the benchmark")
    if promoted:
        try:
            registry["updated_at"] = _iso(moment)
            save_registry(registry, registry_path)
        except OSError as exc:
            return {"ok": False, "error": str(exc), "promoted": promoted}
    return {"ok": True, "promoted": promoted, "active": len(active_models(registry))}