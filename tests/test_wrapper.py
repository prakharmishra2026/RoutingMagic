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
    
    mocker.patch("os.isatty", return_value=True)
    mocker.patch("sys.stdin.fileno", return_value=0)
    mocker.patch("termios.tcgetattr", return_value=[0, 0, 0, 0, 0, 0, 0])
    mocker.patch("termios.tcsetattr")
    mocker.patch("tty.setcbreak")
    
    # Mock sys.stdin.read to return character by character
    mocker.patch("sys.stdin.read", side_effect=["h", "e", "l", "l", "o", "\n"])
    
    res = read_prompt()
    assert res == "hello"

def test_read_prompt_bracketed_single_line(mocker):
    from openai_wrapper import read_prompt
    
    mocker.patch("os.isatty", return_value=True)
    mocker.patch("sys.stdin.fileno", return_value=0)
    mocker.patch("termios.tcgetattr", return_value=[0, 0, 0, 0, 0, 0, 0])
    mocker.patch("termios.tcsetattr")
    mocker.patch("tty.setcbreak")
    
    # Mock sys.stdin.read to return bracketed paste sequence
    chars = ["\x1b", "[", "2", "0", "0", "~", "h", "e", "l", "l", "o", "\x1b", "[", "2", "0", "1", "~", "\n"]
    read_mock = mocker.patch("sys.stdin.read", side_effect=chars)
    mocker.patch("select.select", return_value=(([sys.stdin], [], [])))
    
    res = read_prompt()
    assert res == "hello"

def test_read_prompt_bracketed_multiline(mocker):
    from openai_wrapper import read_prompt
    
    mocker.patch("os.isatty", return_value=True)
    mocker.patch("sys.stdin.fileno", return_value=0)
    mocker.patch("termios.tcgetattr", return_value=[0, 0, 0, 0, 0, 0, 0])
    mocker.patch("termios.tcsetattr")
    mocker.patch("tty.setcbreak")
    
    # Mock sys.stdin.read to simulate the lines of a bracketed paste
    chars = ["\x1b", "[", "2", "0", "0", "~", "h", "e", "l", "l", "o", "\n", "w", "o", "r", "l", "d", "\n", "e", "n", "d", "\x1b", "[", "2", "0", "1", "~", "\n"]
    mocker.patch("sys.stdin.read", side_effect=chars)
    mocker.patch("select.select", return_value=(([sys.stdin], [], [])))
    
    res = read_prompt()
    assert res == "hello\nworld\nend"

def test_read_prompt_fallback_piped(mocker):
    from openai_wrapper import read_prompt
    
    # Mock os.isatty to False (piped input)
    mocker.patch("os.isatty", return_value=False)
    mocker.patch("sys.stdin.fileno", return_value=0)
    mocker.patch("sys.stdin.read", return_value="line1\nline2")
    
    res = read_prompt()
    assert res == "line1\nline2"

def test_read_prompt_bracketed_hybrid(mocker):
    from openai_wrapper import read_prompt
    
    mocker.patch("os.isatty", return_value=True)
    mocker.patch("sys.stdin.fileno", return_value=0)
    mocker.patch("termios.tcgetattr", return_value=[0, 0, 0, 0, 0, 0, 0])
    mocker.patch("termios.tcsetattr")
    mocker.patch("tty.setcbreak")
    
    # Mock sys.stdin.read to return a typed prefix followed by paste start, then the rest
    chars = ["P", "r", "e", "f", "i", "x", " ", "\x1b", "[", "2", "0", "0", "~", "h", "e", "l", "l", "o", "\n", "w", "o", "r", "l", "d", "\n", "e", "n", "d", "\x1b", "[", "2", "0", "1", "~", "\n"]
    mocker.patch("sys.stdin.read", side_effect=chars)
    mocker.patch("select.select", return_value=(([sys.stdin], [], [])))
    
    res = read_prompt()
    assert res == "Prefix hello\nworld\nend"

def test_read_prompt_bracketed_paste_no_autosubmit(mocker):
    from openai_wrapper import read_prompt
    
    mocker.patch("os.isatty", return_value=True)
    mocker.patch("sys.stdin.fileno", return_value=0)
    mocker.patch("termios.tcgetattr", return_value=[0, 0, 0, 0, 0, 0, 0])
    mocker.patch("termios.tcsetattr")
    mocker.patch("tty.setcbreak")
    
    # Paste ends with a newline: "hello\n"
    # It should NOT submit immediately, but wait for the next character (e.g. typing "world" then "\n")
    chars = ["\x1b", "[", "2", "0", "0", "~", "h", "e", "l", "l", "o", "\n", "\x1b", "[", "2", "0", "1", "~", "w", "o", "r", "l", "d", "\n"]
    mocker.patch("sys.stdin.read", side_effect=chars)
    mocker.patch("select.select", return_value=(([sys.stdin], [], [])))
    
    res = read_prompt()
    assert res == "hello\nworld"


