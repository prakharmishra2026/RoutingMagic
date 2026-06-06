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
    
    # Just asserting it exists to prevent regressions where someone re-adds temp to these
