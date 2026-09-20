"""Offline tests for the council self-maintenance strike engine."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "vercel" / "api"
sys.path.insert(0, str(API_DIR))

import council_audit as ca  # noqa: E402
import probe_candidates as pc  # noqa: E402

T0 = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat()


def base_registry(ids, status="active", runs_observed=5, strikes=None, bench_history=None):
    models = {}
    for mid in ids:
        models[mid] = {
            "provider": "openrouter",
            "added_at": iso(T0),
            "last_verified": iso(T0),
            "status": status,
            "runs_observed": runs_observed,
            "probe_score": {},
            "strikes": list(strikes or []),
            "bench_history": list(bench_history or []),
        }
    return {"version": 1, "min_active": 3, "strike_window_days": 14,
            "retire_window_days": 60, "grace_runs": 3, "models": models}


def strike(run_id, days_ago, reason="timeout"):
    return {"run_id": run_id, "date": iso(T0 - timedelta(days=days_ago)), "reason": reason}


def apply_many(reg, model, outcome, n, now=T0, prober=None, prefix="r"):
    last = None
    for i in range(n):
        last = ca.apply_outcome(reg, f"{prefix}{i}", model, outcome, now,
                                prober=prober, log=lambda *_: None)
    return last


# ── prompt_echo / ok never strike ───────────────────────────────────────────

def test_prompt_echo_never_strikes():
    reg = base_registry(["a", "b", "c"])
    apply_many(reg, "a", "prompt_echo", 10)
    assert reg["models"]["a"]["strikes"] == []
    assert reg["models"]["a"]["status"] == "active"


def test_ok_never_strikes():
    reg = base_registry(["a", "b", "c"])
    apply_many(reg, "a", "ok", 10)
    assert reg["models"]["a"]["strikes"] == []


# ── basic strikes and benching ──────────────────────────────────────────────

@pytest.mark.parametrize("outcome", ["empty_content", "timeout", "provider_error",
                                     "wrong_finding_verified"])
def test_strikeable_outcomes_count(outcome):
    reg = base_registry(["a", "b", "c"])
    ca.apply_outcome(reg, "r1", "a", outcome, T0, log=lambda *_: None)
    assert len(reg["models"]["a"]["strikes"]) == 1


def test_three_strikes_in_window_bench():
    reg = base_registry(["a", "b", "c", "d"])
    apply_many(reg, "a", "timeout", 3)
    assert reg["models"]["a"]["status"] == "benched"
    assert reg["models"]["a"]["strikes"] == []


def test_only_two_strikes_stay_active():
    reg = base_registry(["a", "b", "c"])
    apply_many(reg, "a", "empty_content", 2)
    assert reg["models"]["a"]["status"] == "active"


# ── expiry ──────────────────────────────────────────────────────────────────

def test_strikes_older_than_14_days_expire():
    old = [strike("o1", 20), strike("o2", 30)]
    reg = base_registry(["a", "b", "c"], strikes=old)
    ca.apply_outcome(reg, "new", "a", "timeout", T0, log=lambda *_: None)
    assert len(reg["models"]["a"]["strikes"]) == 1
    assert reg["models"]["a"]["status"] == "active"


def test_expiry_does_not_bench_across_window():
    old = [strike("o1", 20), strike("o2", 20)]
    reg = base_registry(["a", "b", "c"], strikes=old)
    apply_many(reg, "a", "timeout", 2)
    assert len(reg["models"]["a"]["strikes"]) == 2
    assert reg["models"]["a"]["status"] == "active"


# ── all-fail infrastructure fault ───────────────────────────────────────────

def test_all_fail_is_infrastructure_fault(tmp_path):
    regfile = tmp_path / "reg.json"
    regfile.write_text(json.dumps(base_registry(["a", "b", "c"])))
    results = [
        {"model": "a", "success": False, "error": "timeout"},
        {"model": "b", "success": False, "error": "timeout"},
        {"model": "c", "success": False, "error": "provider down"},
    ]
    out = ca.record_council_results("run1", results, registry_path=regfile,
                                    now=T0, log=lambda *_: None)
    assert out["infrastructure_fault"] is True
    saved = json.loads(regfile.read_text())
    assert all(not m["strikes"] for m in saved["models"].values())


def test_partial_failure_strikes_each(tmp_path):
    regfile = tmp_path / "reg.json"
    regfile.write_text(json.dumps(base_registry(["a", "b", "c"])))
    results = [
        {"model": "a", "success": True, "content": "ok"},
        {"model": "b", "success": False, "error": "timeout"},
        {"model": "c", "success": False, "error": "empty content"},
    ]
    out = ca.record_council_results("run1", results, registry_path=regfile,
                                    now=T0, log=lambda *_: None)
    assert out["infrastructure_fault"] is False
    saved = json.loads(regfile.read_text())
    assert len(saved["models"]["b"]["strikes"]) == 1
    assert len(saved["models"]["c"]["strikes"]) == 1
    assert saved["models"]["a"]["strikes"] == []


# ── grace period ────────────────────────────────────────────────────────────

def test_grace_exempts_provider_error_and_wrong_finding():
    reg = base_registry(["a", "b", "c"], runs_observed=0)
    ca.apply_outcome(reg, "r1", "a", "provider_error", T0, log=lambda *_: None)
    ca.apply_outcome(reg, "r2", "a", "wrong_finding_verified", T0, log=lambda *_: None)
    assert reg["models"]["a"]["strikes"] == []


def test_grace_counts_empty_content_and_timeout():
    reg = base_registry(["a", "b", "c"], runs_observed=0)
    ca.apply_outcome(reg, "r1", "a", "empty_content", T0, log=lambda *_: None)
    ca.apply_outcome(reg, "r2", "a", "timeout", T0, log=lambda *_: None)
    assert len(reg["models"]["a"]["strikes"]) == 2


def test_grace_ends_after_three_runs():
    reg = base_registry(["a", "b", "c"], runs_observed=0)
    apply_many(reg, "a", "ok", 3)  # 3 observed runs consume grace
    ca.apply_outcome(reg, "r4", "a", "provider_error", T0, log=lambda *_: None)
    assert len(reg["models"]["a"]["strikes"]) == 1


# ── retirement ──────────────────────────────────────────────────────────────

def test_bench_twice_in_60_days_retires():
    reg = base_registry(["a", "b", "c", "d"])
    apply_many(reg, "a", "timeout", 3, now=T0, prefix="first")
    assert reg["models"]["a"]["status"] == "benched"
    reg["models"]["a"]["status"] = "active"  # as if re-promoted
    apply_many(reg, "a", "timeout", 3, now=T0 + timedelta(days=10), prefix="second")
    assert reg["models"]["a"]["status"] == "retired"


def test_second_bench_after_60_days_does_not_retire():
    reg = base_registry(["a", "b", "c", "d"])
    apply_many(reg, "a", "timeout", 3, now=T0, prefix="first")
    reg["models"]["a"]["status"] = "active"
    apply_many(reg, "a", "timeout", 3, now=T0 + timedelta(days=70), prefix="second")
    assert reg["models"]["a"]["status"] == "benched"
    assert len(reg["models"]["a"]["bench_history"]) == 1


# ── low-roster hold and promotion ───────────────────────────────────────────

def test_low_roster_hold_when_no_candidate_passes():
    reg = base_registry(["a", "b", "c"])
    logs = []
    last = None
    for i in range(3):
        last = ca.apply_outcome(reg, f"r{i}", "a", "timeout", T0,
                                prober=lambda: [], log=logs.append)
    assert last["low_roster_hold"] is True
    assert reg["models"]["a"]["status"] == "active"
    assert len(reg["models"]["a"]["strikes"]) == 3
    assert any("LOW_ROSTER_HOLD" in line for line in logs)


def test_probe_and_promote_keeps_roster_at_three():
    reg = base_registry(["a", "b", "c"])
    def prober():
        return [
            {"model": "new1", "provider": "openrouter", "passed": True,
             "probe_score": {"score": 12.0}},
            {"model": "new2", "provider": "openrouter", "passed": False,
             "probe_score": {"score": 1.0}},
        ]
    last = None
    for i in range(3):
        last = ca.apply_outcome(reg, f"r{i}", "a", "timeout", T0,
                                prober=prober, log=lambda *_: None)
    assert last["benched"] is True
    assert reg["models"]["a"]["status"] == "benched"
    assert "new1" in reg["models"] and reg["models"]["new1"]["status"] == "active"
    assert "new2" not in reg["models"]
    assert len(ca.active_models(reg)) == 3


def test_no_probe_when_roster_stays_healthy():
    reg = base_registry(["a", "b", "c", "d"])
    called = {"n": 0}
    def prober():
        called["n"] += 1
        return []
    apply_many(reg, "a", "timeout", 3, prober=prober)
    assert reg["models"]["a"]["status"] == "benched"
    assert called["n"] == 0


def test_ensure_min_active_promotes(tmp_path):
    regfile = tmp_path / "reg.json"
    reg = base_registry(["a", "b"], status="active")
    regfile.write_text(json.dumps(reg))
    def prober():
        return [{"model": "new1", "passed": True, "probe_score": {"score": 5.0}}]
    out = ca.ensure_min_active(registry_path=regfile, now=T0, prober=prober,
                               log=lambda *_: None)
    assert out["promoted"] == ["new1"]


# ── registry unreadable ─────────────────────────────────────────────────────

def test_record_run_unreadable_registry_never_raises(tmp_path):
    missing = tmp_path / "nope.json"
    out = ca.record_run("r1", "a", "timeout", registry_path=missing, now=T0,
                        log=lambda *_: None)
    assert out["ok"] is False
    assert "error" in out


def test_council_falls_back_to_hardcoded_roster(monkeypatch, tmp_path):
    import council
    monkeypatch.setattr(council, "council_audit", None)
    assert council.load_active_roster() == list(council.COUNCIL_MODELS)


def test_council_falls_back_when_registry_missing(monkeypatch, tmp_path):
    import council
    monkeypatch.setenv("COUNCIL_REGISTRY_PATH", str(tmp_path / "absent.json"))
    assert council.load_active_roster() == list(council.COUNCIL_MODELS)


def test_council_reads_active_roster(monkeypatch, tmp_path):
    import council
    regfile = tmp_path / "reg.json"
    reg = base_registry(["good", "benched-one", "third"])
    reg["models"]["benched-one"]["status"] = "benched"
    regfile.write_text(json.dumps(reg))
    monkeypatch.setenv("COUNCIL_REGISTRY_PATH", str(regfile))
    roster = council.load_active_roster()
    ids = [m for _, m in roster]
    assert "good" in ids and "third" in ids and "benched-one" not in ids


# ── probe scoring (offline) ─────────────────────────────────────────────────

def test_score_output_full_marks():
    answer = (
        "1. No upper bound / allocation cap on user_requested.\n"
        "2. `if balance:` treats 0 as missing (truthiness bug).\n"
        "3. Bare except returns True and silently swallows the error.\n"
    )
    scored = pc.score_output(answer, 5.0)
    assert scored["found_planted_defects"] == 3
    assert scored["numbered_output"] is True
    assert scored["no_reasoning_leak"] is True
    assert scored["passed"] is True


def test_score_output_reasoning_leak_fails():
    answer = "Let me think. My reasoning: 1. cap missing. 2. zero bug.\n"
    scored = pc.score_output(answer, 3.0)
    assert scored["no_reasoning_leak"] is False
    assert scored["passed"] is False


def test_score_output_empty_fails():
    scored = pc.score_output("", 1.0)
    assert scored["found_planted_defects"] == 0
    assert scored["passed"] is False


def test_probe_model_sends_reasoning_disabled():
    captured = {}
    class Msg:
        content = "1. cap\n2. zero truthiness\n3. bare except returns True"
    class Choice:
        message = Msg()
    class Resp:
        choices = [Choice()]
        usage = None
    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return Resp()
    class Client:
        chat = type("c", (), {"completions": Completions()})()
    pc.probe_model(Client(), "free/model:free")
    assert captured["extra_body"] == {"reasoning": {"enabled": False}}


def test_probe_history_roundtrip(tmp_path):
    path = tmp_path / "hist.json"
    pc.save_history([{"model": "x", "score": 5}], path=path)
    pc.save_history([{"model": "y", "score": 6}], path=path)
    saved = json.loads(path.read_text())
    assert [r["model"] for r in saved] == ["x", "y"]


def test_discover_filters_nonzero_pricing():
    assert pc._is_zero_price({"prompt": "0", "completion": "0"}) is True
    assert pc._is_zero_price({"prompt": "0.000001", "completion": "0"}) is False


def test_classify_result():
    assert pc is not None
    assert ca.classify_result({"success": True}) == "ok"
    assert ca.classify_result({"success": False, "error": "timeout"}) == "timeout"
    assert ca.classify_result({"success": False, "error": "empty content"}) == "empty_content"
    assert ca.classify_result({"success": False, "error": "400 bad request"}) == "provider_error"
    assert ca.classify_result({"outcome": "prompt_echo"}) == "prompt_echo"