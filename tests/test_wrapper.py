import pytest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai_wrapper import get_client_and_model, NO_TEMPERATURE_MODELS

def test_get_client_and_model():
    # Test NVIDIA routing
    client, model = get_client_and_model("nvidia/z-ai/glm-5.1")
    assert model == "z-ai/glm-5.1"
    assert "nvidia" in client.base_url.host

    # Test OpenRouter routing
    client, model = get_client_and_model("google/gemma-4-31b-it:free")
    assert model == "google/gemma-4-31b-it:free"
    assert "openrouter" in client.base_url.host or "127.0.0.1" in client.base_url.host

    # Test OpenAI direct routing
    client, model = get_client_and_model("openai/o3-mini")
    assert model == "o3-mini"
    assert "openai" in client.base_url.host

def test_no_temperature_models():
    # Ensure o3-mini and o1 are tracked correctly
    assert "o3-mini" in NO_TEMPERATURE_MODELS
    assert "o1" in NO_TEMPERATURE_MODELS
    assert "o1-mini" in NO_TEMPERATURE_MODELS

def test_read_prompt_normal(mocker):
    from openai_wrapper import read_prompt
    
    # Mock input to return a single line
    mocker.patch("builtins.input", return_value="hello")
    # Mock select.select to indicate no additional data
    mocker.patch("select.select", return_value=((), (), ()))
    
    res = read_prompt()
    assert res == "hello"

def test_read_prompt_bracketed_single_line(mocker):
    from openai_wrapper import read_prompt
    
    # Mock input to return single line bracketed paste
    mocker.patch("builtins.input", return_value="\x1b[200~hello\x1b[201~")
    
    res = read_prompt()
    assert res == "hello"

def test_read_prompt_bracketed_multiline(mocker):
    from openai_wrapper import read_prompt
    
    # Mock input to return start of bracketed paste
    mocker.patch("builtins.input", return_value="\x1b[200~hello")
    
    # Mock sys.stdin.readline to simulate subsequent lines arriving
    readline_mock = mocker.patch("sys.stdin.readline", side_effect=["world\n", "end\x1b[201~\n"])
    
    res = read_prompt()
    assert res == "hello\nworld\nend"
    assert readline_mock.call_count == 2

def test_read_prompt_fallback_piped(mocker):
    from openai_wrapper import read_prompt
    
    mocker.patch("builtins.input", return_value="line1")
    
    # Mock select.select: ready on first check, not ready on second check
    mocker.patch("select.select", side_effect=[(([sys.stdin], [], [])), (([], [], ()))])
    
    # Mock sys.stdin.readline
    mocker.patch("sys.stdin.readline", return_value="line2\n")
    
    res = read_prompt()
    assert res == "line1\nline2"

def test_read_prompt_bracketed_hybrid(mocker):
    from openai_wrapper import read_prompt
    
    # Mock input to return typed prefix and bracketed paste start
    mocker.patch("builtins.input", return_value="Prefix \x1b[200~hello")
    
    # Mock sys.stdin.readline
    readline_mock = mocker.patch("sys.stdin.readline", side_effect=["world\n", "end\x1b[201~\n"])
    
    res = read_prompt()
    assert res == "Prefix hello\nworld\nend"
    assert readline_mock.call_count == 2


