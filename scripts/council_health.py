#!/usr/bin/env python3
"""Council Health Probe - free-only live check of the Model Council.

Sends a trivial completion to every COUNCIL_MODELS member and prints:
    model  status  latency_ms  content_nonempty

Exits non-zero if any member fails (HTTP error, timeout, or empty content).

Keys are read ONLY via the standard loaders (~/.routingmagic/.env then
~/global.env); at most key NAMES + PRESENT/ABSENT are ever shown.

Usage: python3 scripts/council_health.py [--quick]
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "vercel" / "api"))

from council import COUNCIL_MODELS  # noqa: E402

load_dotenv(os.path.expanduser("~/.routingmagic/.env"))
load_dotenv(os.path.expanduser("~/global.env"))

NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

QUICK = "--quick" in sys.argv
PROBES = 1 if QUICK else 3
PROMPT = "Reply with exactly: COUNCIL-PROBE-OK"

PROVIDER_ENV = {
    "nvidia": ("NVAPI_KEY", "NVIDIA_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",),
}


def _present(name: str) -> str:
    return "PRESENT" if os.getenv(name) else "ABSENT"


def main() -> int:
    clients = {}
    for provider, base in (("nvidia", NVIDIA_BASE), ("openrouter", OPENROUTER_BASE)):
        for env_name in PROVIDER_ENV[provider]:
            if os.getenv(env_name):
                clients[provider] = OpenAI(
                    base_url=base, api_key=os.getenv(env_name),
                    max_retries=0, timeout=40.0,
                )
                break

    if not clients:
        print("council_health: no API keys (nvidia: "
              f"{_present('NVAPI_KEY')}, openrouter: {_present('OPENROUTER_API_KEY')})")
        return 2

    failures = 0
    print(f"council_health {len(COUNCIL_MODELS)} members x {PROBES} probe(s) "
          f"({__import__('datetime').datetime.now().__str__()})")
    for provider, model in COUNCIL_MODELS:
        client = clients.get(provider)
        if not client:
            print(f"{model}  SKIP  -  (no {provider} key)")
            failures += 1
            continue
        ok = 0
        lat = []
        last_err = ""
        for _ in range(PROBES):
            t0 = time.time()
            attempts = 0
            while True:
                try:
                    r = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": PROMPT}],
                        temperature=0.1,
                        max_tokens=32,
                    )
                    el = int((time.time() - t0) * 1000)
                    content = (r.choices[0].message.content or "").strip()
                    if content:
                        ok += 1
                        lat.append(el)
                        last_err = ""
                    else:
                        last_err = "EMPTY_CONTENT"
                    break
                except Exception as e:
                    code = getattr(e, "status_code", None) or getattr(e, "status", None)
                    if str(code) in ("429", "500", "502", "503", "504") and attempts < 2:
                        # Transient provider error (NIM is known for brief 503s);
                        # bounded retry, still FAILS if it never recovers.
                        attempts += 1
                        time.sleep(2.0)
                        continue
                    last_err = f"{type(e).__name__}:{code}:{str(e)[:60]}"
                    el = int((time.time() - t0) * 1000)
                    break
            if QUICK:
                break
            time.sleep(1.0)
        median = int(lat[len(lat) // 2]) if lat else -1
        status = "PASS" if ok == PROBES else "FAIL"
        if status == "FAIL":
            failures += 1
        print(f"{model}  {status}  {median}  {ok}/{PROBES}  "
              f"content_nonempty={'yes' if lat else 'no'}"
              + (f"  [{last_err}]" if last_err else ""))
        sys.stdout.flush()

    if failures:
        print(f"council_health: {failures} member(s) FAILED")
        return 1
    print("council_health: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())