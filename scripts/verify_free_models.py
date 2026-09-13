#!/usr/bin/env python3
"""verify_free_models.py — daily auto-verification + auto-rotation of the pinned
free-tier model pool used across RoutingMagic.

Runs AFTER the registry refresh in .github/workflows/update-models.yml. It
re-probes every member of registry/verified_free_models.json through the SAME
resolver the runtime uses (openai_wrapper.get_client_and_model), records fresh
probe evidence, and with --fix rotates any failed member to a live free
alternative — updating the json, vercel/api/council.py, and
registry/model_changelog.md.

Exit codes (loud for cron / CI):
  0 = every pinned role is filled and healthy
  1 = one or more roles could not be filled with a live free model

Usage:
  python3 scripts/verify_free_models.py                # verify-only, report
  python3 scripts/verify_free_models.py --fix          # verify + auto-rotate
  python3 scripts/verify_free_models.py --fix --report registry/health_report.md
"""
import argparse
import base64
import json
import re
import struct
import subprocess
import sys
import time
import zlib
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from openai_wrapper import get_client_and_model  # noqa: E402

VERIFIED_PATH = REPO / "registry" / "verified_free_models.json"
REGISTRY_PATH = REPO / "registry"
COUNCIL_PATH = REPO / "vercel" / "api" / "council.py"
CHANGELOG_PATH = REGISTRY_PATH / "model_changelog.md"
LAST_UPDATE = REGISTRY_PATH / "last_update.txt"
MAX_WORKERS = 4
RETRIES = 2
RETRY_SLEEP = 3.0
WATCHDOG_SEC = 60.0
ROLE_PROBE_HINTS = {"vision": "vision", "council": "text", "chairman": "text"}


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tiny_png_b64():
    ihdr = struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)
    row = b"\x00\x00\xff\x00" * 64
    raw = row * 64

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data)))

    b = bytearray(b"\x89PNG\r\n\x1a\n")
    b += chunk(b"IHDR", ihdr)
    b += chunk(b"IDAT", zlib.compress(raw))
    b += chunk(b"IEND", b"")
    return base64.b64encode(bytes(b)).decode()


def load_pool():
    try:
        return json.loads(VERIFIED_PATH.read_text())
    except Exception:
        return {"pool": {}}


def last_update_age_hours():
    try:
        ts = LAST_UPDATE.read_text().strip()
        last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - last).total_seconds() / 3600.0
    except Exception:
        return float("inf")


def ensure_registry_fresh():
    age = last_update_age_hours()
    if age is None or age <= 24:
        return True, age
    subprocess.run(
        [sys.executable, str(REPO / "model_registry_updater.py"),
         "--daily", "--force", "--output-dir", "./registry"],
        cwd=REPO, check=False, capture_output=True,
    )
    return False, age


def probe_member(entry):
    cid = entry["id"]
    role = entry.get("role", "council")
    print(f"  [probe] {cid} start", flush=True)
    t0 = time.time()

    def _run():
        client, resolved = get_client_and_model(cid)
        if ROLE_PROBE_HINTS.get(role) == "vision":
            msgs = [{"role": "user", "content": [
                {"type": "text", "text": "What color is this image? Reply in one word."},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{_tiny_png_b64()}"}}]}]
        else:
            msgs = [{"role": "user", "content": "Reply with exactly: OK"}]
        resp = client.chat.completions.create(
            model=resolved, messages=msgs, max_tokens=16, temperature=0)
        if not resp.choices:
            raise RuntimeError("no-choices (transient gate)")
        content = (resp.choices[0].message.content or "").strip()
        return content, resolved

    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_run)
        try:
            content, resolved = fut.result(timeout=WATCHDOG_SEC)
        except concurrent.futures.TimeoutError:
            fut.cancel()
            print(f"  [probe] {cid} WATCHDOG-TIMEOUT {WATCHDOG_SEC}s", flush=True)
            return {"ok": False, "cid": cid, "latency_ms": int(WATCHDOG_SEC * 1000),
                    "resolved": cid, "error": f"watchdog-timeout>{WATCHDOG_SEC}s",
                    "transient": True}
        except Exception as e:
            err = str(e)
            transient = any(s in err for s in ("429", "500", "502", "503", "504",
                                               "RateLimit", "InternalServer",
                                               "NoneType", "subscriptable",
                                               "no-choices"))
            print(f"  [probe] {cid} ERROR {type(e).__name__}: {err[:80]}", flush=True)
            return {"ok": False, "cid": cid, "latency_ms": int((time.time() - t0) * 1000),
                    "resolved": cid, "error": f"{type(e).__name__}: {err[:120]}",
                    "transient": transient}
    dt = int((time.time() - t0) * 1000)
    print(f"  [probe] {cid} done {dt}ms content={'yes' if content else 'no'}", flush=True)
    if content:
        return {"ok": True, "cid": cid, "latency_ms": dt, "resolved": resolved,
                "transient": False}
    return {"ok": False, "cid": cid, "latency_ms": dt, "resolved": resolved,
            "error": "empty-content", "transient": True}


def probe_with_retry(entry):
    last = {"ok": False}
    for _ in range(RETRIES + 1):
        last = probe_member(entry)
        if last["ok"] or not last.get("transient", False):
            break
        time.sleep(RETRY_SLEEP)
    return last


def provider_of(cid, source):
    if source == "nim":
        return "nvidia"
    if source == "openrouter":
        return "openrouter"
    if cid == "gemini-2.5-flash" or cid.startswith("google/"):
        return "google"
    if cid.startswith("glm-") or cid.startswith("z-ai/") or cid.startswith("zhipu/"):
        return "zai"
    return source or "openrouter"


def registry_free_candidates():
    """Candidate ids for rotation from the freshly updated registry."""
    try:
        reg = json.loads((REGISTRY_PATH / "model_registry.json").read_text())
    except Exception:
        return []
    out = []
    for src in ("nim_free_models", "openrouter_free_models"):
        for m in reg.get(src, []):
            cid = m if isinstance(m, str) else m.get("id")
            if not cid:
                continue
            if src == "nim" and not cid.startswith("nvidia/"):
                cid = "nvidia/" + cid
            elif src == "openrouter" and not cid.startswith("openrouter/"):
                cid = "openrouter/" + cid
            out.append((cid, provider_of(cid, src)))
    return out


def find_replacement(role, failed_provider, pool_entries):
    present = {p["provider"] for p in pool_entries}
    others = set()
    for role_alt in pool_entries:
        others.add(role_alt["id"])
    cands = registry_free_candidates()
    # Prefer a provider not already healthy in the pool (invariant #7 spread),
    # then vision-capable ids for the vision role.
    ranked = sorted(set(cands), key=lambda cp: (cp[1] in present, "vl" not in cp[0] if role == "vision" else False))
    for cid, prov in ranked:
        if cid in others:
            continue
        if role == "vision" and not any(t in cid for t in ("vl", "omni", "vision")):
            continue
        yield cid


def write_pool(pool_doc):
    VERIFIED_PATH.write_text(json.dumps(pool_doc, indent=2) + "\n")


def rewrite_council_py(pool_entries):
    """Rewrite COUNCIL_MODELS list in vercel/api/council.py from the council pool.

    Built with line slicing, NOT regex: the lazy (?:.*?\\n)*? + DOTALL pattern is
    catastrophic-backtracking on this file and hangs re.sub forever (regression
    2026-09-13, LESSONS #031).
    """
    src = COUNCIL_PATH.read_text()
    # only never pin members that probe failed (kept-on-fail entries have probes=False)
    council = [e for e in pool_entries
               if e["provider"] in ("openrouter", "nvidia") and e.get("probes")]
    block = "COUNCIL_MODELS = [\n" + "\n".join(
        f'    ("{e["provider"]}", "{e["id"]}"),' for e in council) + "\n]\n"
    start = src.index("COUNCIL_MODELS = [")
    end = src.index("\n]\n", start) + len("\n]\n")
    COUNCIL_PATH.write_text(src[:start] + block + src[end:])


def append_changelog(rotated, ts):
    added, removed = [], []
    for entry in rotated:
        if entry.get("was_id") and entry["was_id"] != entry["id"]:
            removed.append(entry["was_id"])
        added.append(entry["id"])
    new = [
        f"\n## {ts} — verify_free_models.py auto-rotation",
        "  ➕ **Rotated in**: " + ", ".join(added) if added else "",
    ]
    if removed:
        new.append("  ➖ **Rotated out**: " + ", ".join(removed))
    with CHANGELOG_PATH.open("a") as fh:
        fh.write("\n".join(x for x in new if x) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Verify & auto-rotate the pinned free model pool")
    ap.add_argument("--fix", action="store_true",
                    help="rotate failed members to live free alternatives and persist")
    ap.add_argument("--report", metavar="PATH", help="also write a markdown report")
    args = ap.parse_args()

    if not args.fix:
        old_age = last_update_age_hours()
        if old_age and old_age > 24:
            print(f"[warn] registry last update {old_age:.1f}h old — run the updater first")

    doc = load_pool()
    pool = doc["pool"]
    ts = _now()
    failed_roles = {}
    lines = []

    for role, entries in pool.items():
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            results = list(ex.map(probe_with_retry, entries))
        healthy = []
        for entry, res in zip(entries, results):
            entry["last_check"] = ts
            entry["probes"] = res["ok"]
            if res["ok"]:
                entry["median_latency_ms"] = res["latency_ms"]
                healthy.append(entry)
                lines.append(f"  ✓ {role:<8} {entry['id']:<50} {res['latency_ms']}ms")
            else:
                lines.append(f"  ✗ {role:<8} {entry['id']:<50} DEAD/empty: {res['error'][:60]}")
                if args.fix:
                    rotated = False
                    for cid in find_replacement(role, entry["provider"], entries + healthy):
                        cand = {"id": cid, "provider": provider_of(cid.split("/", 1)[1] if len(cid.split("/")) > 1 else cid, "openrouter" if ":free" in cid else "nim"),
                                "role": role}
                        pr = probe_with_retry(cand)
                        if pr["ok"]:
                            entry.update({"id": cid, "provider": cand["provider"],
                                          "was_id": entry["id"], "last_check": ts,
                                          "probes": True,
                                          "median_latency_ms": pr["latency_ms"]})
                            healthy.append(entry)
                            lines.append(f"    ↻ rotated {role} -> {cid} ({pr['latency_ms']}ms)")
                            rotated = True
                            break
                    if not rotated:
                        # keep the pinned member on rotation failure (never vacate a
                        # role on one flaky red) — exit 1 still flags the role loudly
                        healthy.append(entry)
                        failed_roles[role] = entry["id"]
                else:
                    failed_roles[role] = entry["id"]
        pool[role] = healthy if args.fix else pool[role]

    # verify-only: keep failed members (so --fix later knows what to fix) but mark
    if not args.fix and failed_roles:
        pass

    doc["last_verified_at"] = ts
    if args.fix:
        council_entries = pool.get("council", [])
        if council_entries:
            rewrite_council_py(council_entries)
        rotated = [e for role in pool.values() for e in role if "was_id" in e]
        if rotated:
            append_changelog(rotated, ts)
        write_pool(doc)
    else:
        write_pool({**doc, "pool": pool})

    print(f"verify_free_models {ts}")
    print("\n".join(lines))
    ok = not failed_roles
    print(f"summary: {'ALL ROLES HEALTHY' if ok else 'FAILED ROLES: ' + json.dumps(failed_roles)}")

    if args.report:
        rep = Path(args.report)
        rep.parent.mkdir(parents=True, exist_ok=True)
        rep.write_text(f"# Free model pool verification — {ts}\n\n"
                       + "\n".join(f"{l}\n" for l in lines)
                       + f"\n**Summary:** {'ALL HEALTHY' if ok else failed_roles}\n")
        print(f"report written: {rep}")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()