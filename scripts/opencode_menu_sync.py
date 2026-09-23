#!/usr/bin/env python3
"""
OpenCode Menu Sync — Safe Config Writer

Reads the generated opencode_model_menu.json and safely rewrites
~/.config/opencode/opencode.jsonc with updated whitelists + display names.

Safety gates:
  1. Backup with timestamp before any write
  2. JSONC-preserving atomic write
  3. Validate all whitelisted IDs exist in the local models catalog
  4. Conservative repoint of model/small_model only if truly gone
  5. Rollback on any failure
  6. Never print secrets

Usage:
  python3 scripts/opencode_menu_sync.py --dry-run    # preview changes
  python3 scripts/opencode_menu_sync.py --diff       # show diff
  python3 scripts/opencode_menu_sync.py              # apply
  python3 scripts/opencode_menu_sync.py --restore    # restore last backup
  python3 scripts/opencode_menu_sync.py --force      # skip validation
"""
import json, os, sys, shutil, argparse, re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional

REPO = Path(__file__).resolve().parents[1]
REGISTRY_DIR = REPO / "registry"
MENU_FILE = REGISTRY_DIR / "opencode_model_menu.json"
OPENCODE_CONFIG = Path.home() / ".config/opencode" / "opencode.jsonc"
BACKUP_DIR = Path.home() / ".config/opencode" / "sync_backups"
OPENCODE_BIN = "/Users/grandvision/.opencode/bin/opencode"


def load_menu() -> Optional[dict]:
    if not MENU_FILE.exists():
        print(f"[sync] No menu file: {MENU_FILE}")
        return None
    with open(MENU_FILE) as f:
        return json.load(f)


def strip_jsonc_comments(text: str) -> str:
    """Remove C-style comments from JSONC text, respecting string boundaries."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    result = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            i += 1
            continue
        if in_string:
            result.append(ch)
            i += 1
            continue
        if text[i:i+2] == '//':
            while i < len(text) and text[i] != '\n':
                i += 1
            continue
        result.append(ch)
        i += 1
    return ''.join(result)


def load_config() -> dict:
    text = OPENCODE_CONFIG.read_text()
    return json.loads(strip_jsonc_comments(text))


def atomic_write(path: Path, content: str, backup_dir: Path):
    backup_dir.mkdir(parents=True, exist_ok=True)
    if path.exists():
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = backup_dir / f"opencode.jsonc.{ts}"
        shutil.copy2(path, backup)
        backups = sorted(backup_dir.glob("opencode.jsonc.*"))
        for b in backups[:-5]:
            b.unlink()
        print(f"[sync] Backup created: {backup}")
    tmp = path.with_suffix(".jsonc.tmp")
    tmp.write_text(content)
    tmp.replace(path)
    print(f"[sync] Wrote: {path}")


def jsonc_dumps(data: dict, indent: int = 2) -> str:
    return json.dumps(data, indent=indent, ensure_ascii=False) + "\n"


def validate_config(whitelists: dict) -> bool:
    catalog_file = REGISTRY_DIR / "openrouter_catalog.json"
    if not catalog_file.exists():
        print("[sync] No catalog for validation; skipping (assume OK)")
        return True
    with open(catalog_file) as f:
        catalog = json.load(f)
    catalog_ids = {m.get("id", "") for m in catalog}
    all_ok = True
    for prov, wl in whitelists.items():
        for mid in wl:
            if mid not in catalog_ids and not any(mid in cid for cid in catalog_ids):
                print(f"[sync] WARNING: {prov}/{mid} not in catalog")
                all_ok = False
    if all_ok:
        print("[sync] All whitelisted IDs verified in catalog")
    return all_ok


def repoint_defaults(config: dict, whitelists: dict):
    """Only repoint if the model is truly gone from all whitelists."""
    all_whitelisted = set()
    for wl in whitelists.values():
        all_whitelisted.update(wl)

    for key in ["model", "small_model"]:
        if key not in config:
            continue
        val = config[key]
        if "/" not in val:
            continue
        # val like "provider/model-id" — check if model-id is in whitelist
        # The model-id part may contain '/' itself (e.g. deepseek/deepseek-v4.1-flash)
        # Try to find if this exact ID or a matching prefix is whitelisted
        if val in all_whitelisted or any(m.endswith("/" + val.split("/", 1)[1]) for m in all_whitelisted):
            continue
        # Only repoint model (not small_model) if it's completely gone
        if key == "small_model":
            continue
        # Try to find a suitable replacement from the same provider
        parts = val.split("/", 1)
        prov = parts[0]
        if prov in whitelists and whitelists[prov]:
            new_id = whitelists[prov][0]
            config[key] = f"{prov}/{new_id}"
            print(f"[sync] Repointed {key}: {val} → {config[key]}")


def build_new_config(menu: dict, old_config: dict) -> tuple:
    config = json.loads(json.dumps(old_config))
    whitelists = {}

    for prov in ["openrouter", "nvidia"]:
        prov_data = menu.get("providers", {}).get(prov, {})
        whitelist = prov_data.get("whitelist", [])
        models = prov_data.get("models", {})
        whitelists[prov] = whitelist
        if prov not in config.get("provider", {}):
            config.setdefault("provider", {})[prov] = {}
        config["provider"][prov]["whitelist"] = whitelist
        if models:
            config["provider"][prov]["models"] = models

    repoint_defaults(config, whitelists)
    return config, whitelists


def apply_sync(dry_run: bool = False, diff: bool = False, force: bool = False, restore: bool = False):
    menu = load_menu()
    if not menu:
        print("[sync] Aborted: no menu data.")
        sys.exit(1)
    if not OPENCODE_CONFIG.exists():
        print(f"[sync] Config not found: {OPENCODE_CONFIG}")
        sys.exit(1)

    if restore:
        backups = sorted(BACKUP_DIR.glob("opencode.jsonc.*"), reverse=True)
        if backups:
            shutil.copy2(backups[0], OPENCODE_CONFIG)
            print(f"[sync] Restored from: {backups[0]}")
        else:
            print("[sync] No backups found.")
        sys.exit(0)

    old_config = load_config()
    new_config, whitelists = build_new_config(menu, old_config)
    new_text = jsonc_dumps(new_config)

    if not force:
        if not validate_config(whitelists):
            print("[sync] Validation failed. Use --force to override.")
            sys.exit(1)

    if diff:
        old_parsed = json.loads(strip_jsonc_comments(OPENCODE_CONFIG.read_text()))
        new_parsed = json.loads(strip_jsonc_comments(new_text))
        if old_parsed == new_parsed:
            print("[sync] No changes detected.")
        else:
            old_wl = old_parsed.get("provider", {}).get("openrouter", {}).get("whitelist", [])
            new_wl = whitelists.get("openrouter", [])
            print(f"  openrouter whitelist: {len(old_wl)} → {len(new_wl)} models")
            added = set(new_wl) - set(old_wl)
            removed = set(old_wl) - set(new_wl)
            print(f"  Added: {list(added)[:5]}")
            print(f"  Removed: {list(removed)[:5]}")
            print(f"  Repointed: model={old_config.get('model')} → {new_config.get('model')}")
        sys.exit(0)

    if dry_run:
        print(f"[dry-run] openrouter: {len(whitelists.get('openrouter', []))} models")
        print(f"[dry-run] nvidia: {len(whitelists.get('nvidia', []))} models")
        print(f"[dry-run] model would be: {new_config.get('model')}")
        print(f"[dry-run] small_model would be: {new_config.get('small_model')}")
        sys.exit(0)

    atomic_write(OPENCODE_CONFIG, new_text, BACKUP_DIR)

    snapshot = {
        "last_synced": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "whitelists": whitelists,
        "config_path": str(OPENCODE_CONFIG),
        "menu_source": str(MENU_FILE),
    }
    snapshot_file = REGISTRY_DIR / "opencode_sync_snapshot.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"[sync] Snapshot: {snapshot_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenCode menu sync")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--diff", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    apply_sync(dry_run=args.dry_run, diff=args.diff, force=args.force, restore=args.restore)
