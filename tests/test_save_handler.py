import pytest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from save_handler import parse_llm_json

def test_parse_llm_json():
    # Test valid JSON
    valid_json = '{"progress": "Done", "lessons": "None", "scratchpad": "", "memory": ""}'
    res = parse_llm_json(valid_json)
    assert res["progress"] == "Done"
    
    # Test JSON wrapped in markdown ticks
    markdown_json = '```json\n{"progress": "Parsed", "lessons": "None", "scratchpad": "", "memory": ""}\n```'
    res = parse_llm_json(markdown_json)
    assert res["progress"] == "Parsed"
    
    # Test JSON with text around it
    messy_json = 'Here is your output:\n```\n{"progress": "Cleaned", "lessons": "None", "scratchpad": "", "memory": ""}\n```\nHope it helps.'
    res = parse_llm_json(messy_json)
    assert res["progress"] == "Cleaned"
    
    # Test invalid JSON returns None
    invalid = "This is not json at all."
    assert parse_llm_json(invalid) is None


# ── pm-mode (projects with a pm/ folder, e.g. Investogram) ─────────────────────
from save_handler import detect_layout, apply_pm_entries, trim_checkpoints


def test_detect_layout_prefers_pm_dir(tmp_path):
    assert detect_layout(str(tmp_path))["mode"] == "root"
    (tmp_path / "pm").mkdir()
    lay = detect_layout(str(tmp_path))
    assert lay["mode"] == "pm"
    assert lay["paths"]["lessons.md"].endswith(os.path.join("pm", "lessons.md"))


def _files():
    return {
        "progress.md": "# Progress\n\n## Session 2026-09-01: old\n- [x] a\n",
        "memory.md": "# Memory\n\n## Recently Completed: old\n- fact\n",
        "lessons.md": "# Lessons\n> purpose\n\n## L-001 — old\nbody\n",
        "scratchpad.md": "# Scratch\n\n## SESSION CHECKPOINT — 3\nc\n\n## Checkpoint 2\nb\n\n## SESSION CHECKPOINT — 1\na\n",
    }


def test_apply_pm_entries_inserts_at_top_and_keeps_history():
    old = _files()
    new = apply_pm_entries(old, {
        "progress_entry": "## Session 2026-09-24: new\n- [x] b",
        "memory_facts": "",
        "lessons_entry": "## L-002 — new\nbody",
        "scratchpad_checkpoint": "## SESSION CHECKPOINT — 4\nd",
    })
    assert "memory.md" not in new                      # empty entry -> untouched
    p = new["progress.md"]
    assert p.index("2026-09-24") < p.index("2026-09-01") and p.endswith(old["progress.md"][len("# Progress\n\n"):])
    assert new["lessons.md"].index("L-002") < new["lessons.md"].index("L-001")
    s = new["scratchpad.md"]
    assert "CHECKPOINT — 4" in s and "Checkpoint 2" in s and "CHECKPOINT — 1" not in s  # rolling 3


def test_apply_pm_entries_never_shrinks_history():
    old = _files()
    # A model that returns junk must not be able to wipe a history file.
    new = apply_pm_entries(old, {"progress_entry": "   ", "lessons_entry": ""})
    assert new == {}


def test_trim_checkpoints_noop_when_three_or_fewer():
    t = "# S\n\n## Checkpoint a\nx\n"
    assert trim_checkpoints(t) == t
