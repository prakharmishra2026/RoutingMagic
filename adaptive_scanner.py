#!/usr/bin/env python3
"""
Adaptive Scanner — Auto-discovers AI tools, loads only ACTIVE adapters for deep tracking.
STALE gets shallow scan. CONFIGURED shows hint. MISSING hidden.
"""

import json
import subprocess
import urllib.request
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime, timezone
import sqlite3
import threading


@dataclass
class AdapterStatus:
    name: str
    state: str  # ACTIVE, STALE, CONFIGURED, MISSING
    paths_found: List[str]
    cli_ok: bool
    api_ok: bool
    last_seen: Optional[str] = None
    last_shallow: Optional[str] = None
    error_msg: Optional[str] = None


ADAPTER_PROBES = {
    "claude": {
        "paths": [
            "~/.claude/usage.db",
            "~/.claude/projects/",
        ],
        "cli_check": ["claude", "--version"],
        "api_check": None,
    },
    "opencode": {
        "paths": ["~/.local/share/opencode/opencode.db"],
        "cli_check": ["opencode", "--version"],
        "api_check": None,
    },
    "codex": {
        "paths": ["~/.codex/state_5.sqlite"],
        "cli_check": ["codex", "--version"],
        "api_check": None,
    },
    "hermes": {
        "paths": ["~/.hermes/state.db"],
        "cli_check": ["hermes", "--version"],
        "api_check": None,
    },
    "routingmagic": {
        "paths": ["~/.routingmagic/metrics/token_metrics.db"],
        "cli_check": None,
        "api_check": None,
    },
    "ollama": {
        "paths": ["~/.ollama/"],
        "cli_check": ["ollama", "list"],
        "api_check": "http://localhost:11434/api/tags",
        "proxy_path": "~/.routingmagic/metrics/ollama_usage.db",
    },
    "antigravity": {
        "paths": [
            "~/Library/Application Support/Antigravity/",
            "~/Library/Application Support/Antigravity IDE/",
        ],
        "cli_check": ["agy", "/usage", "--json"],
        "api_check": None,
    },
    "chatgpt": {
        "paths": [],
        "cli_check": None,
        "api_check": "https://api.openai.com/v1/usage",
    },
    "gemini": {
        "paths": [],
        "cli_check": None,
        "api_check": "https://generativelanguage.googleapis.com/v1beta/models",
    },
}

COMPETITOR_ADAPTERS = {
    "cursor": {"paths": ["~/.cursor/"], "cli_check": ["cursor", "--version"]},
    "windsurf": {"paths": ["~/.windsurf/"], "cli_check": ["windsurf", "--version"]},
    "continue": {"paths": ["~/.continue/"], "cli_check": ["continue", "--version"]},
    "aider": {"paths": ["~/.aider/"], "cli_check": ["aider", "--version"]},
    "sourcegraph": {"paths": [], "api_check": "https://api.sourcegraph.com/"},
    "copilot": {"paths": [], "api_check": "https://api.github.com/copilot/usage"},
    "tabnine": {"paths": ["~/.tabnine/"], "cli_check": ["tabnine", "--version"]},
    "codeium": {"paths": ["~/.codeium/"], "cli_check": ["codeium", "--version"]},
    "deepseek": {"paths": [], "api_check": "https://api.deepseek.com/usage"},
    "anthropic_api": {"paths": [], "api_check": "https://api.anthropic.com/v1/usage"},
    "groq": {"paths": [], "api_check": "https://api.groq.com/openai/v1/usage"},
    "together": {"paths": [], "api_check": "https://api.together.xyz/usage"},
    "perplexity": {"paths": [], "api_check": "https://api.perplexity.ai/usage"},
}


def expand_paths(paths: List[str]) -> List[str]:
    return [str(Path(p).expanduser()) for p in paths]


def check_cli(cmd: List[str]) -> bool:
    try:
        subprocess.run(cmd, capture_output=True, timeout=3)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def check_api(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=3)
        return True
    except Exception:
        return False


def get_configured_adapters() -> List[str]:
    """Read configured adapters from quota config YAML."""
    config_path = Path.home() / ".routingmagic" / "quotas.yaml"
    if not config_path.exists():
        return []
    try:
        import yaml
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return list(data.get("budgets", {}).get("providers", {}).keys())
    except Exception:
        return []


class AdaptiveScanner:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(Path.home() / ".routingmagic" / "metrics" / "usage_unified.db")
        self.adapter_status: Dict[str, AdapterStatus] = {}
        self.active_adapters: List[str] = []
        self.stale_adapters: List[str] = []
        self._lock = threading.Lock()

    def discover(self) -> Dict[str, AdapterStatus]:
        """Run discovery probes for all known adapters."""
        results = {}
        all_probes = {**ADAPTER_PROBES, **COMPETITOR_ADAPTERS}
        configured = set(get_configured_adapters())

        for name, probe in all_probes.items():
            paths = probe.get("paths", [])
            expanded_paths = expand_paths(paths)
            paths_exist = any(Path(p).exists() for p in expanded_paths)

            cli_ok = False
            if probe.get("cli_check"):
                cli_ok = check_cli(probe["cli_check"])

            api_ok = False
            if probe.get("api_check"):
                api_ok = check_api(probe["api_check"])

            if paths_exist and (cli_ok or api_ok):
                state = "ACTIVE"
            elif paths_exist:
                state = "STALE"
            elif name in configured:
                state = "CONFIGURED"
            else:
                state = "MISSING"

            results[name] = AdapterStatus(
                name=name,
                state=state,
                paths_found=[p for p in expanded_paths if Path(p).exists()],
                cli_ok=cli_ok,
                api_ok=api_ok,
            )

        return results

    def _record_discovery_state(self):
        """Persist adapter state to SQLite."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS adapter_state (
                name TEXT PRIMARY KEY,
                state TEXT,
                last_seen TEXT,
                last_shallow TEXT,
                cli_ok INTEGER,
                api_ok INTEGER,
                paths_found TEXT,
                error_msg TEXT
            )
        """)

        now = datetime.now(timezone.utc).isoformat()
        for name, status in self.adapter_status.items():
            conn.execute("""
                INSERT OR REPLACE INTO adapter_state
                (name, state, last_seen, last_shallow, cli_ok, api_ok, paths_found, error_msg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                status.state,
                status.last_seen,
                status.last_shallow,
                1 if status.cli_ok else 0,
                1 if status.api_ok else 0,
                json.dumps(status.paths_found),
                status.error_msg,
            ))

        conn.commit()
        conn.close()

    def _load_existing_state(self):
        """Load previous adapter states from DB."""
        if not Path(self.db_path).exists():
            return
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM adapter_state").fetchall()
        conn.close()

        for row in rows:
            self.adapter_status[row["name"]] = AdapterStatus(
                name=row["name"],
                state=row["state"],
                paths_found=json.loads(row["paths_found"] or "[]"),
                cli_ok=bool(row["cli_ok"]),
                api_ok=bool(row["api_ok"]),
                last_seen=row["last_seen"],
                last_shallow=row["last_shallow"],
                error_msg=row["error_msg"],
            )

    def scan(self, verbose: bool = True) -> Dict:
        """Main scan: discover state, deep-scan ACTIVE, shallow-scan STALE."""
        with self._lock:
            self._load_existing_state()
            discovered = self.discover()
            self.adapter_status = discovered

            self.active_adapters = [n for n, s in discovered.items() if s.state == "ACTIVE"]
            self.stale_adapters = [n for n, s in discovered.items() if s.state == "STALE"]

            if verbose:
                print(f"🔍 Discovery: {len(self.active_adapters)} ACTIVE, {len(self.stale_adapters)} STALE")
                for name in self.active_adapters:
                    print(f"  ✅ {name}")
                for name in self.stale_adapters:
                    print(f"  ⏳ {name} (stale)")

            # Deep scan active adapters
            deep_results = {}
            for name in self.active_adapters:
                try:
                    rows = self._scan_adapter(name)
                    deep_results[name] = rows
                    self.adapter_status[name].last_seen = datetime.now(timezone.utc).isoformat()
                    if verbose:
                        print(f"  📥 {name}: {len(rows)} records")
                except Exception as e:
                    self.adapter_status[name].error_msg = str(e)
                    if verbose:
                        print(f"  ❌ {name}: {e}")

            # Shallow scan stale adapters
            for name in self.stale_adapters:
                self.adapter_status[name].last_shallow = datetime.now(timezone.utc).isoformat()

            self._record_discovery_state()

            return {
                "active": self.active_adapters,
                "stale": self.stale_adapters,
                "configured": [n for n, s in discovered.items() if s.state == "CONFIGURED"],
                "missing": [n for n, s in discovered.items() if s.state == "MISSING"],
                "deep_results": deep_results,
            }

    def _scan_adapter(self, name: str) -> List[Dict]:
        """Call the appropriate adapter scanner. Returns list of usage records."""
        # Import lazily to avoid circular deps
        from dashboard_adapters import (
            scan_claude, scan_opencode, scan_codex, scan_hermes, scan_routingmagic
        )

        scanner_map = {
            "claude": scan_claude,
            "opencode": scan_opencode,
            "codex": scan_codex,
            "hermes": scan_hermes,
            "routingmagic": scan_routingmagic,
        }

        if name in scanner_map:
            return scanner_map[name]()

        # For Ollama, Antigravity, ChatGPT, Gemini, competitors - handled in Phase 2
        if name in ["ollama", "antigravity", "chatgpt", "gemini"]:
            return []

        return []

    def get_adapter_status(self) -> Dict[str, AdapterStatus]:
        return self.adapter_status


if __name__ == "__main__":
    scanner = AdaptiveScanner()
    result = scanner.scan()
    print(json.dumps({
        "active": result["active"],
        "stale": result["stale"],
        "configured": result["configured"],
        "total_active": len(result["active"]),
        "total_stale": len(result["stale"]),
    }, indent=2))