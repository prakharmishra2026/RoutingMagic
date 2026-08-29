# competitors package - auto-discovered adapters
import os
from pathlib import Path


def _try_import(name: str):
    """Try to import a competitor adapter, return None if not available."""
    try:
        module = __import__(f"adapters.competitors.{name}", fromlist=["scan_" + name])
        return getattr(module, f"scan_{name}", None)
    except ImportError:
        return None


# Auto-discover available competitor adapters
COMPETITOR_ADAPTERS = {}
for name in [
    "cursor", "windsurf", "continue", "aider", "tabnine", "codeium",
    "anthropic_api", "deepseek", "groq", "together", "perplexity", "copilot", "sourcegraph"
]:
    scanner = _try_import(name)
    if scanner:
        COMPETITOR_ADAPTERS[name] = scanner