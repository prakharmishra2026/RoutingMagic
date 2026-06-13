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
    assert "nemotron-3-super" in model
    assert task == "financial_math_reasoning"
    
    # Test long context / planning
    model, task = smart_route("Here is a large repo codebase architecture plan")
    assert "nemotron-3-super-120b" in model
    assert task == "long_context_agentic"
    
    # Test coding regex
    model, task = smart_route("Can you fix this bug in the React code?")
    assert "qwen3-coder" in model
    assert task == "fast_coding"
    
    # Test default fallback
    model, task = smart_route("Hello how are you?")
    assert "gemma-4-31b-it" in model
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
