import pytest
import os
import tempfile
import sys

# Ensure openai_wrapper can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai_wrapper import smart_route, get_instant_context

def test_smart_route_logic():
    # Test financial/math reasoning logic
    model, task = smart_route("Please reason deeply about this math problem")
    assert task in ("financial_math_reasoning", "mythos_deep_reasoning", "mythos_reasoning_effort")
    
    # Test long context / planning
    model, task = smart_route("Here is a large repo codebase architecture plan")
    assert task == "long_context_agentic"
    
    # Test coding regex
    model, task = smart_route("Can you fix this bug in the React code?")
    assert task == "fast_coding"
    
    # Test default fallback
    model, task = smart_route("Hello how are you?")
    assert task == "default_general"

def test_get_instant_context(mocker):
    # Mock OS directory reading to ensure consistent output
    mocker.patch("os.getcwd", return_value="/tmp/test_project")
    mocker.patch("os.path.basename", return_value="test_project")
    mocker.patch("os.path.exists", side_effect=lambda x: x == "package.json")
    
    # Mock package.json read
    mock_json = '{"dependencies": {"react": "^18.0.0", "next": "^13.0.0"}}'
    mocker.patch("builtins.open", mocker.mock_open(read_data=mock_json))
    
    # Mock os.listdir
    mocker.patch("os.listdir", return_value=["src", "public", ".git"])
    mocker.patch("os.path.isdir", return_value=True)
    
    context = get_instant_context()
    
    assert "Project Context:" in context
    assert "Directory: /tmp/test_project" in context
    assert "Name: test_project" in context
    assert "Tech Stack/Dependencies: react, next" in context
    assert "Root Folders: src, public" in context # Should ignore .git


# Scanner and Pricing Smoke Tests
import re
from pathlib import Path

# Import dashboard modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dashboard_server import is_free, get_pricing, calc_cost, parse_timestamp
from unified_scanner import scan, DB_PATH, get_db
from dashboard_adapters import scan_all, SOURCE_ORDER


def test_is_free_classification():
    """Test that free/paid classification works correctly."""
    # Paid models should not be free
    assert is_free("nvidia/nemotron-3-ultra-550b-a55b") == False
    assert is_free("nvidia/nemotron-3-super-120b-a12b") == True  # Free on NIM
    assert is_free("openai/gpt-5.6-sol") == False
    assert is_free("claude-sonnet-4.6") == False
    
    # Free models should be free
    assert is_free("nvidia/nemotron-3-super-120b-a12b:free") == True
    assert is_free("opencode/big-pickle") == True
    assert is_free("openrouter/z-ai/glm-5.2:free") == True
    assert is_free("moonshotai/kimi-k2.6:free") == True
    
    # RoutingMagic source is always free
    assert is_free("nvidia/nemotron-3-ultra-550b-a55b", source="routingmagic") == True


def test_get_pricing_returns_correct_values():
    """Test that pricing lookup returns expected values."""
    # Known models should have pricing
    p = get_pricing("claude-sonnet-4.6")
    assert p is not None
    assert p["input"] == 3.0
    assert p["output"] == 15.0
    
    p = get_pricing("openai/gpt-5.6-sol")
    assert p is not None
    assert p["input"] == 2.5
    
    # Free models should return zero pricing
    p = get_pricing("opencode/big-pickle")
    assert p == {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    
    p = get_pricing("nvidia/nemotron-3-super-120b-a12b:free")
    assert p == {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    
    # OpenRouter models should work via recursive strip
    p = get_pricing("openrouter/deepseek/deepseek-v4-pro-0813")
    assert p is not None
    # Should fall back to deepseek-v3 pricing
    assert p["input"] == 0.27


def test_calc_cost_computes_correctly():
    """Test cost calculation with known values."""
    # $3.00/M input, $15.00/M output
    cost = calc_cost("claude-sonnet-4.6", 1_000_000, 500_000, 0, 0)
    expected = 1_000_000 * 3.0 / 1_000_000 + 500_000 * 15.0 / 1_000_000
    assert abs(cost - expected) < 0.001
    
    # Free model should have zero cost
    cost = calc_cost("opencode/big-pickle", 1_000_000, 1_000_000, 0, 0)
    assert cost == 0.0


def test_parse_timestamp_handles_formats():
    """Test timestamp parsing handles various formats."""
    # ISO with Z
    dt = parse_timestamp("2026-01-15T10:30:00Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 1
    assert dt.day == 15
    assert dt.tzinfo is not None
    
    # ISO with offset
    dt = parse_timestamp("2026-01-15T10:30:00+05:00")
    assert dt is not None
    
    # ISO without timezone (assumes UTC)
    dt = parse_timestamp("2026-01-15T10:30:00")
    assert dt is not None
    assert dt.tzinfo is not None
    
    # Space separator
    dt = parse_timestamp("2026-01-15 10:30:00")
    assert dt is not None
    
    # Invalid returns None
    dt = parse_timestamp("not-a-timestamp")
    assert dt is None
    
    # Empty returns None
    dt = parse_timestamp("")
    assert dt is None


def test_scan_runs_without_error():
    """Test that scanner runs and produces data."""
    # This is a smoke test - just verify scan() doesn't crash
    result = scan(verbose=False)
    assert "turns" in result
    assert "sessions" in result
    assert result["turns"] >= 0
    assert result["sessions"] >= 0


def test_scan_all_sources_returns_data():
    """Test that scan_all returns data for each source."""
    result = scan_all()
    for source in SOURCE_ORDER:
        assert source in result
        assert isinstance(result[source], list)


def test_unified_db_has_expected_schema():
    """Test that unified DB has expected tables and columns."""
    if not DB_PATH.exists():
        pytest.skip("Unified DB not found")
    
    conn = get_db()
    # Check tables exist
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    assert "unified_turns" in tables
    assert "unified_sessions" in tables
    assert "scan_state" in tables
    
    # Check unified_turns columns
    cols = [r[1] for r in conn.execute("PRAGMA table_info(unified_turns)").fetchall()]
    expected_cols = ["source", "session_id", "timestamp", "model", "input_tokens", "output_tokens"]
    for col in expected_cols:
        assert col in cols, f"Missing column: {col}"
    
    conn.close()


def test_cost_never_negative():
    """Test that calculated costs are never negative."""
    for model in ["claude-sonnet-4.6", "openai/gpt-5.6-sol", "nvidia/nemotron-3-ultra-550b-a55b", "opencode/big-pickle"]:
        cost = calc_cost(model, 100, 100, 0, 0)
        assert cost >= 0, f"Negative cost for {model}: {cost}"


def test_free_models_have_zero_cost():
    """Test that models classified as free have zero cost."""
    free_models = [
        "opencode/big-pickle",
        "nvidia/nemotron-3-super-120b-a12b:free",
        "openrouter/z-ai/glm-5.2:free",
    ]
    for model in free_models:
        cost = calc_cost(model, 1_000_000, 1_000_000, 0, 0)
        assert cost == 0.0, f"Free model {model} has non-zero cost: {cost}"
