"""Model Council contract tests for /api/council.

Network-free: _council_query_one and _select_council_models are both patched so
no model is called and candidate selection is deterministic.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dashboard_server as ds

CANDIDATES = [
    ("m1:free", "openrouter"), ("m2:free", "openrouter"), ("m3:free", "openrouter"),
    ("m4:free", "openrouter"), ("m5:free", "openrouter"), ("m6:free", "openrouter"),
]


@pytest.fixture(autouse=True)
def _deterministic(monkeypatch):
    monkeypatch.setattr(ds, "_registry_age_hours", lambda: 1.0)  # never stale
    monkeypatch.setattr(ds, "_select_council_models",
                        lambda prompt, n=ds.COUNCIL_SIZE, want=None: (list(CANDIDATES), False, 20))


def _fake_query(succeed):
    def q(model, provider, prompt):
        if model in succeed:
            return {"model": model, "provider": provider, "success": True,
                    "error": "", "content": f"answer from {model}"}
        return {"model": model, "provider": provider, "success": False,
                "error": "RateLimitError: 429", "content": ""}
    return q


def test_full_council_returns_three_members_and_synthesis(monkeypatch):
    monkeypatch.setattr(ds, "_council_query_one", _fake_query({"m1:free", "m2:free", "m3:free"}))
    out = ds.run_local_council("what is 2+2?")
    assert out.get("error") is None
    assert len(out["results"]) == ds.COUNCIL_SIZE
    assert all(m["success"] for m in out["results"])
    assert out["degraded"] is False
    assert out["degraded_note"] == ""
    assert out["synthesis"]


def test_partial_council_is_flagged_degraded(monkeypatch):
    monkeypatch.setattr(ds, "_council_query_one", _fake_query({"m1:free"}))
    out = ds.run_local_council("what is 2+2?")
    assert out["degraded"] is True
    assert "degraded" in out["degraded_note"]
    assert len(out["results"]) == ds.COUNCIL_SIZE  # padded with failures it tried


def test_over_selection_recovers_a_full_council(monkeypatch):
    # only 3 of the 6 candidates answer, but the council still comes back full & clean
    monkeypatch.setattr(ds, "_council_query_one", _fake_query({"m2:free", "m4:free", "m6:free"}))
    out = ds.run_local_council("q")
    assert out["degraded"] is False
    assert len(out["results"]) == ds.COUNCIL_SIZE
    assert all(m["success"] for m in out["results"])


def test_total_failure_still_returns_a_shaped_payload(monkeypatch):
    monkeypatch.setattr(ds, "_council_query_one", _fake_query(set()))
    out = ds.run_local_council("q")
    assert out["degraded"] is True
    assert out["results"] and all(not m["success"] for m in out["results"])
    assert out["synthesis"] == ""


def test_stale_registry_refuses(monkeypatch):
    monkeypatch.setattr(ds, "_registry_age_hours", lambda: ds.COUNCIL_STALE_HOURS + 5)
    out = ds.run_local_council("q")
    assert out["results"] == [] and ("old" in out["error"] or "stale" in out["error"])


def _drive_post(body: str) -> tuple:
    """Run DashboardHandler.do_POST against a fake request, return (code, payload)."""
    sent = {}

    class Fake:
        _send_json = ds.DashboardHandler._send_json
        do_POST = ds.DashboardHandler.do_POST
        path = "/api/council"

        def __init__(self, b):
            self._b = b.encode()
            self.headers = {"Content-Length": str(len(self._b))}

        class _RF:
            def __init__(self, b): self._b = b
            def read(self, n): return self._b
        @property
        def rfile(self): return Fake._RF(self._b)
        def send_response(self, c): sent["code"] = c
        def send_header(self, *a): pass
        def end_headers(self): pass
        class _WF:
            def write(s, b): sent["body"] = b
        wfile = _WF()

    Fake(body).do_POST()
    return sent["code"], json.loads(sent["body"])


def test_do_post_council_ok(monkeypatch):
    monkeypatch.setattr(ds, "_council_query_one", _fake_query({"m1:free", "m2:free", "m3:free"}))
    code, payload = _drive_post(json.dumps({"prompt": "hi"}))
    assert code == 200
    assert len(payload["results"]) == ds.COUNCIL_SIZE and payload["synthesis"]


def test_do_post_empty_prompt_is_400():
    code, payload = _drive_post(json.dumps({"prompt": "   "}))
    assert code == 400
