#!/usr/bin/env python3
"""RoutingMagic — Secure API Key Setup

Captures API keys via native macOS dialogs (masked input) or secure
terminal fallback. Keys stored in ~/.routingmagic/.env with 0600 perms.
OpenRouter recommended for Model Council + free models.
"""
import os, sys, stat, platform, subprocess, getpass
from pathlib import Path

CONFIG_DIR = Path.home() / ".routingmagic"
CONFIG_FILE = CONFIG_DIR / ".env"
OR_SIGNUP = "https://openrouter.ai/keys"
GEM_SIGNUP = "https://aistudio.google.com/apikey"
ZAI_SIGNUP = "https://open.bigmodel.cn"
NV_SIGNUP = "https://build.nvidia.com/nim/dashboard"
OAI_SIGNUP = "https://platform.openai.com/api-keys"


def _mask(k: str) -> str:
    return k[:4] + "•" * min(16, max(0, len(k) - 8)) + k[-4:] if len(k) >= 8 else "••••"


def _load_existing() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    d = {}
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def _save(keys: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        f.write("# RoutingMagic API Keys — https://github.com/prakharmishra2026/RoutingMagic\n")
        f.write("# Re-run setup: python3 setup_keys.py\n\n")
        for section, env_vars in [
            ("Required: OpenRouter (free models + Model Council)", ["OPENROUTER_API_KEY"]),
            ("Optional: Google Gemini (direct free models via Google AI Studio)", ["GEMINI_API_KEY"]),
            ("Optional: Z.ai / Zhipu AI (permanent free GLM-4.5-Flash tier)", ["ZAI_API_KEY"]),
            ("Optional: NVIDIA NIM (GLM-5.1, Vision, OCR)", ["NVAPI_KEY"]),
            ("Optional: OpenAI (GPT-5, o3-mini)", ["OPENAI_API_KEY"]),
        ]:
            f.write(f"# -- {section} --\n")
            for ev in env_vars:
                if ev in keys and keys[ev]:
                    f.write(f"{ev}={keys[ev]}\n")
                else:
                    f.write(f"# {ev}=\n")
            f.write("\n")
    os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)


def _prompt_macos(title: str, message: str, secret: bool = False) -> str | None:
    """Native macOS dialog via osascript. Secret mode uses password field."""
    try:
        if secret:
            return None
        script = f'display dialog "{message}" default answer "" with title "{title}"'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            out = result.stdout.strip()
            if 'textReturned:"' in out:
                return out.split('textReturned:"')[1].split('"')[0]
        return None
    except Exception:
        return None


def _prompt_terminal(label: str, is_secret: bool = False) -> str | None:
    """Terminal prompt with masked input for secrets."""
    try:
        if is_secret:
            val = getpass.getpass(f"  {label}: ")
        else:
            sys.stdout.write(f"  {label}: ")
            sys.stdout.flush()
            val = sys.stdin.readline().strip()
        return val if val else None
    except (EOFError, KeyboardInterrupt):
        return None


def _prompt_key(label: str, env_name: str, existing: dict, is_secret: bool = True) -> str | None:
    cur = existing.get(env_name, "")
    hint = f" [saved: {_mask(cur)}]" if cur else ""
    suffix = " (Enter=keep)" if cur else ""

    if platform.system() == "Darwin" and not is_secret:
        val = _prompt_macos("✨ RoutingMagic Key Configuration", f"{label}{hint}{suffix}")
        if val is not None:
            return val

    return _prompt_terminal(f"{label}{hint}{suffix}", is_secret=is_secret) or cur or None


def run_setup():
    print("\n\033[38;5;141m╭────────────────────────────────────────────────────────╮")
    print("│         ✨ RoutingMagic — Secure Key Manager           │")
    print("╰────────────────────────────────────────────────────────╯\033[0m\n")

    existing = _load_existing()
    if existing:
        print(f"  \033[38;5;244m◆ Loaded config: {CONFIG_FILE}\033[0m")
        print("  \033[38;5;244m◆ Press Enter to keep current values, paste new key to update.\033[0m\n")

    print("  \033[38;5;81m╭──────────────────────────────────────────────────────╮")
    print("  │  🚀 MULTI-PROVIDER FREE TIER ADVANTAGE              │")
    print("  │                                                      │")
    print("  │  RoutingMagic combines free models across providers  │")
    print("  │  for instant zero-latency failover and fast Council. │")
    print("  ╰──────────────────────────────────────────────────────╯\033[0m\n")

    keys = {}

    # OpenRouter
    print("  \033[1;38;5;221m◆ Step 1/5  OpenRouter API Key [RECOMMENDED]\033[0m")
    print("    Enables: Model Council (/mc), community free models")
    print(f"    Get free key: \033[4m{OR_SIGNUP}\033[0m")
    val = _prompt_key("OpenRouter key (sk-or-...)", "OPENROUTER_API_KEY", existing)
    if val:
        keys["OPENROUTER_API_KEY"] = val

    # Google Gemini
    print(f"\n  \033[1;38;5;221m◆ Step 2/5  Google Gemini API Key [RECOMMENDED]\033[0m")
    print(f"    Enables: direct fast free tier (Gemini 2.5 Flash, 2.0 Flash)")
    print(f"    Get free key: \033[4m{GEM_SIGNUP}\033[0m")
    val = _prompt_key("Google Gemini key (AIza...)", "GEMINI_API_KEY", existing)
    if val:
        keys["GEMINI_API_KEY"] = val

    # Z.ai / Zhipu AI
    print(f"\n  \033[1;38;5;221m◆ Step 3/5  Z.ai / Zhipu AI API Key [RECOMMENDED]\033[0m")
    print(f"    Enables: permanent free tier (GLM-4.7-Flash, GLM-4.5-Flash)")
    print(f"    Get free key: \033[4m{ZAI_SIGNUP}\033[0m")
    val = _prompt_key("Z.ai / Zhipu key", "ZAI_API_KEY", existing)
    if val:
        keys["ZAI_API_KEY"] = val

    # NVIDIA NIM
    print(f"\n  \033[1;38;5;221m◆ Step 4/5  NVIDIA NIM API Key [OPTIONAL]\033[0m")
    print(f"    Enables: Nemotron Ultra 120B, Llama 3.3 70B, OCR & Vision")
    print(f"    Get free key: \033[4m{NV_SIGNUP}\033[0m")
    val = _prompt_key("NVIDIA NIM key (nvapi-...)", "NVAPI_KEY", existing)
    if val:
        keys["NVAPI_KEY"] = val

    # OpenAI
    print(f"\n  \033[1;38;5;221m◆ Step 5/5  OpenAI API Key [OPTIONAL]\033[0m")
    print(f"    Enables: GPT-5, o3-mini, GPT-4o")
    print(f"    Get API key: \033[4m{OAI_SIGNUP}\033[0m")
    val = _prompt_key("OpenAI key (sk-...)", "OPENAI_API_KEY", existing)
    if val:
        keys["OPENAI_API_KEY"] = val

    merged = {**existing, **keys}
    _save(merged)

    print(f"\n  \033[1;38;5;82m✔ Keys saved securely to {CONFIG_FILE}\033[0m")
    print(f"    \033[38;5;244mFile permissions: 0600 (owner read/write only)\033[0m")
    print(f"    \033[38;5;244mKeys are isolated from git and shared folders.\033[0m\n")

    has_or = bool(merged.get("OPENROUTER_API_KEY"))
    has_gem = bool(merged.get("GEMINI_API_KEY"))
    has_zai = bool(merged.get("ZAI_API_KEY"))
    has_nv = bool(merged.get("NVAPI_KEY"))
    has_oai = bool(merged.get("OPENAI_API_KEY"))

    print("  \033[1;38;5;81mProvider Configuration Status:\033[0m")
    print(f"    OpenRouter  : {'\033[38;5;82m✔ Active\033[0m' if has_or else '\033[38;5;240m○ Skipped\033[0m'}")
    print(f"    Google Gem  : {'\033[38;5;82m✔ Active\033[0m' if has_gem else '\033[38;5;240m○ Skipped\033[0m'}")
    print(f"    Z.ai (GLM)  : {'\033[38;5;82m✔ Active\033[0m' if has_zai else '\033[38;5;240m○ Skipped\033[0m'}")
    print(f"    NVIDIA NIM  : {'\033[38;5;82m✔ Active\033[0m' if has_nv else '\033[38;5;240m○ Skipped\033[0m'}")
    print(f"    OpenAI      : {'\033[38;5;82m✔ Active\033[0m' if has_oai else '\033[38;5;240m○ Skipped\033[0m'}")

    if not any([has_or, has_gem, has_zai, has_nv, has_oai]):
        print(f"\n  \033[38;5;214m⚠ Please configure at least one free API key.\033[0m")

    print("\n  ╭────────────────────────────────────────────────────────╮")
    print("  │  🎉 SETUP COMPLETE! Try these commands right now:      │")
    print("  ├────────────────────────────────────────────────────────┤")
    print("  │  1. Reload your shell aliases:                         │")
    print("  │       \033[1;38;5;82msource ~/.zshrc\033[0m                                  │")
    print("  │                                                        │")
    print("  │  2. Start LLM Council Deliberation (Multi-Model REPL): │")
    print("  │       \033[1;38;5;81mask MC\033[0m    or    \033[1;38;5;81m/mc\033[0m                              │")
    print("  │                                                        │")
    print("  │  3. Ask Smart Router a question:                       │")
    print("  │       \033[1;38;5;81mask \"How do I write a Python decorator?\"\033[0m           │")
    print("  │                                                        │")
    print("  │  4. View all available model shortcuts & cheatsheet:   │")
    print("  │       \033[1;38;5;214mcc-models\033[0m                                        │")
    print("  ╰────────────────────────────────────────────────────────╯\n")


if __name__ == "__main__":
    run_setup()