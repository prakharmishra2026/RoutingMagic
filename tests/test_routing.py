import pytest
import os
import tempfile
import sys

# Ensure openai_wrapper can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai_wrapper import smart_route, get_instant_context

def test_smart_route_logic():
    # Test planning/reasoning regex
    model, task = smart_route("Please reason deeply about this architecture plan")
    assert "nemotron-3-ultra" in model
    assert task == "deep_reasoning_planning"
    
    # Test coding regex
    model, task = smart_route("Can you fix this bug in the React code?")
    assert "deepseek-v4-flash" in model
    assert task == "fast_coding"
    
    # Test long horizon coding regex
    model, task = smart_route("Here is a large repo we need to restructure over a long workflow")
    assert "kimi-k2.6" in model
    assert task == "long_horizon_agentic_coding"
    
    # Test default fallback
    model, task = smart_route("Hello how are you?")
    assert "glm-5.1" in model
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
