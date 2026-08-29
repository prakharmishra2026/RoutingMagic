"""Dashboard server tests: free/paid classification, served-page integrity, council wiring.

Network-free. The council tests exercise selection/filtering logic only; they never
call a model.
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dashboard_server as ds


# ── Phase 3: free-turn classification ────────────────────────────────────────────

def test_nim_free_model_counts_as_free():
    """NVIDIA NIM free models carry no ':free' suffix but must still count as free.

    Regression for the dashboard free-turn %: the frontend used to re-derive
    free-ness with a naive ':free' substring test, undercounting NIM free usage.
    """
    assert ds.is_free("nvidia/nemotron-3-super-120b-a12b", "claude") is True


def test_suffixed_free_model_counts_as_free():
    assert ds.is_free("qwen/qwen3-coder:free", "openrouter") is True


def test_routingmagic_source_is_free():
    assert ds.is_free("whatever/model", "routingmagic") is True


def test_paid_model_is_not_free():
    assert ds.is_free("anthropic/claude-sonnet-4", "claude") is False


def test_frontend_uses_server_free_field_not_substring():
    """The Free Usage stat must read row.free, not re-derive ':free' client-side."""
    html = _served_html()
    assert "daily.filter(r=>r.free)" in html
    assert "r.model.indexOf(':free')" not in html


# ── Phase 8 (brought forward): served-page integrity ─────────────────────────────

def _served_html() -> str:
    src = open(ds.__file__).read()
    i = src.index('DASHBOARD_HTML = r"""')
    j = src.index('</html>"""', i)
    return src[i:j]


def test_every_onclick_handler_is_defined():
    """Would have caught the dead Model Council button (onclick with no function)."""
    html = _served_html()
    handlers = set(re.findall(r'onclick="([a-zA-Z_]\w*)\(', html))
    defined = set(re.findall(r'function ([a-zA-Z_]\w*)\(', html))
    missing = handlers - defined
    assert not missing, f"onclick handlers with no definition: {sorted(missing)}"


def test_council_modal_markup_present():
    html = _served_html()
    for token in ('id="council-modal"', 'id="council-prompt"', 'id="council-results"',
                  'onclick="runCouncil()"'):
        assert token in html, f"missing council markup: {token}"


# ── Phase 2: council model selection (offline) ───────────────────────────────────

def test_council_selection_is_registry_driven_and_chat_only():
    picks, _relaxed, pool = ds._select_council_models("explain recursion", want=6)
    assert pool > 0, "registry produced an empty free pool"
    assert picks, "no council candidates selected"
    for model, provider in picks:
        assert provider in ("nvidia", "openrouter")
        assert ds._is_chat_model(model), f"non-chat model selected: {model}"


def test_council_excludes_non_chat_models():
    assert ds._is_chat_model("google/lyria-3-pro-preview") is False
    assert ds._is_chat_model("nvidia/nemotron-3.5-content-safety") is False
    assert ds._is_chat_model("thinkingmachines/inkling:free") is False
    assert ds._is_chat_model("openrouter/free") is False
    assert ds._is_chat_model("qwen/qwen3-coder:free") is True


def test_council_dedupes_free_suffix_twins():
    picks, _relaxed, _pool = ds._select_council_models("hello", want=12)
    bases = [m[:-5] if m.endswith(":free") else m for m, _ in picks]
    assert len(bases) == len(set(bases)), f"duplicate base models: {bases}"


def test_stale_registry_makes_council_refuse(monkeypatch):
    monkeypatch.setattr(ds, "_registry_age_hours", lambda: ds.COUNCIL_STALE_HOURS + 1)
    out = ds.run_local_council("anything")
    assert out["results"] == []
    assert "stale" in out["error"].lower() or "old" in out["error"].lower()


def test_empty_prompt_rejected():
    out = ds.run_local_council("   ")
    assert out["error"] == "empty prompt"


# ── Phase 8: Claude JSONL scanner (no dependency on the usage.db ingester) ────────

def test_scan_claude_jsonl_reads_live_logs(tmp_path):
    import dashboard_adapters as da

    proj = tmp_path / "-Users-me-Projects-demo"
    proj.mkdir()
    turn = {
        "type": "assistant",
        "timestamp": "2026-08-29T10:00:00.000Z",
        "sessionId": "abc-123",
        "cwd": "/Users/me/Projects/demo",
        "gitBranch": "main",
        "message": {
            "model": "claude-sonnet-5",
            "usage": {
                "input_tokens": 10, "output_tokens": 20,
                "cache_read_input_tokens": 100, "cache_creation_input_tokens": 5,
                "output_tokens_details": {"thinking_tokens": 7},
            },
        },
    }
    noise = {"type": "user", "message": {"content": "hi"}}
    (proj / "sess.jsonl").write_text(json.dumps(noise) + "\n" + json.dumps(turn) + "\n")

    rows = da.scan_claude_jsonl(projects_dir=tmp_path)
    assert len(rows) == 1
    r = rows[0]
    assert r["source"] == "claude"
    assert r["session_id"] == "abc-123"
    assert r["model"] == "claude-sonnet-5"
    assert (r["input_tokens"], r["output_tokens"]) == (10, 20)
    assert (r["cache_read"], r["cache_write"]) == (100, 5)
    assert r["reasoning_tokens"] == 7
    assert r["project"] == "Projects/demo"


def test_scan_claude_jsonl_missing_dir_is_empty(tmp_path):
    import dashboard_adapters as da
    assert da.scan_claude_jsonl(projects_dir=tmp_path / "nope") == []
