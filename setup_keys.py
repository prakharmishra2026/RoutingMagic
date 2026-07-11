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
KEYS_FILE = "~/.routingmagic/.env"
OR_SIGNUP = "https://openrouter.ai/keys"
NV_SIGNUP = "https://build.nvidia.com/nim/dashboard"
OAI_SIGNUP = "https://platform.openai.com/api-keys"


def _mask(k: str) -> str:
    return k[:4] + "*" * max(0, len(k) - 8) + k[-4:] if len(k) >= 8 else "***"


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
            # AppleScript has no native password dialog — use Python approach
            return None
        script = f'display dialog "{message}" default answer "" with title "{title}"'
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            # Parse: {textReturned:"xxx", buttonReturned:"OK"}
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
        val = _prompt_macos("RoutingMagic Setup", f"{label}{hint}{suffix}")
        if val is not None:
            return val

    return _prompt_terminal(f"{label}{hint}{suffix}", is_secret=is_secret) or cur or None


def run_setup():
    print("\n\033[95m╔══════════════════════════════════════════════════════╗")
    print("║       RoutingMagic — Secure API Key Setup            ║")
    print("╚══════════════════════════════════════════════════════╝\033[0m\n")

    existing = _load_existing()
    if existing:
        print(f"  Found existing config: {CONFIG_FILE}")
        print("  Press Enter to keep current values, paste new key to update.\n")

    print("  \033[96m┌──────────────────────────────────────────────────────┐")
    print("  │  RECOMMENDATION: OpenRouter first                   │")
    print("  │                                                      │")
    print("  │  Free models + full Model Council (/council, /mc).  │")
    print("  │  No credit card needed for free tier.               │")
    print(f"  │  Sign up: \033[4m{OR_SIGNUP}\033[0m\033[96m                   │")
    print("  └──────────────────────────────────────────────────────┘\033[0m\n")

    keys = {}

    # OpenRouter
    print("  \033[93mStep 1/3: OpenRouter API Key (RECOMMENDED)\033[0m")
    print("  Required for: free models (cc*, ask), Model Council (/mc)")
    val = _prompt_key("OpenRouter key (sk-or-...)", "OPENROUTER_API_KEY", existing)
    if val:
        keys["OPENROUTER_API_KEY"] = val

    # NVIDIA NIM
    print(f"\n  \033[93mStep 2/3: NVIDIA NIM API Key (OPTIONAL)\033[0m")
    print(f"  Enables: GLM-5.1, Nemotron Ultra, Vision, OCR")
    print(f"  Skip if you only need free OpenRouter models.")
    val = _prompt_key("NVIDIA NIM key (nvapi-...)", "NVAPI_KEY", existing)
    if val:
        keys["NVAPI_KEY"] = val

    # OpenAI
    print(f"\n  \033[93mStep 3/3: OpenAI API Key (OPTIONAL)\033[0m")
    print(f"  Enables: GPT-5, o3-mini, GPT-4-Turbo (paid)")
    val = _prompt_key("OpenAI key (sk-...)", "OPENAI_API_KEY", existing)
    if val:
        keys["OPENAI_API_KEY"] = val

    merged = {**existing, **keys}
    _save(merged)

    print(f"\n  \033[92m✓ Keys saved securely to {CONFIG_FILE}\033[0m")
    print(f"    File permissions: 600 (owner read/write only)")
    print(f"    Keys are NOT in any git repo or shared location.\n")

    has_or = bool(merged.get("OPENROUTER_API_KEY"))
    has_nv = bool(merged.get("NVAPI_KEY"))
    has_oai = bool(merged.get("OPENAI_API_KEY"))

    print("  \033[96mStatus:\033[0m")
    print(f"    OpenRouter : {'✓' if has_or else '✗ not set — free models unavailable'}")
    print(f"    NVIDIA NIM : {'✓' if has_nv else '○ skipped'}")
    print(f"    OpenAI     : {'✓' if has_oai else '○ skipped'}")

    if not has_or:
        print(f"\n  \033[93m⚠ OpenRouter strongly recommended for Model Council.\033[0m")
        print(f"  Re-run: python3 ~/Projects/RoutingMagic/setup_keys.py")

    print(f"\n  \033[92mNext:\033[0m source ~/.zshrc && cc-models\n")


if __name__ == "__main__":
    run_setup()
