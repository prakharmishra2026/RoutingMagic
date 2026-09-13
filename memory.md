# Memory — Permanent Project Knowledge

## Architecture Facts

### File sizes & constraints
- `openai_wrapper.py` = ~2600 lines / ~110KB — never full-rewrite, always edit in place
- `caveman_integration.py` = 256 lines — singleton via `get_caveman()`
- `metrics_collector.py` = 473 lines — SQLite DB at `~/.routingmagic/metrics/token_metrics.db`
- `caveman_quality_loop.py` = 336 lines — config + lessons in `~/.routingmagic/quality/`
- `model_registry_updater.py` = 387 lines — registry at `~/.routingmagic/registry/`
- `routing_learner.py` = 543 lines — learning DB at `~/.routingmagic/learning/`

### Integration points in openai_wrapper.py
| Module | Import | Used at | Method |
|--------|--------|---------|--------|
| caveman_integration | `get_caveman()` | chat_oneshot (context), repl (context + output), repl (confusion) | `compress_context()` / `compress_response()` / `record_confusion_signal()` |
| metrics_collector | `record_session()`, `format_savings_dashboard()` | chat_oneshot & repl completion, `/savings` | Session metrics recording, dashboard formatting |
| caveman_quality_loop | `get_quality_loop()` | repl (confusion + feedback) | `/caveman-feedback`, confusion detection |
| model_registry_updater | `auto_update_if_needed()` | main() startup | Weekly fetch |
| routing_learner | `get_routing_learner()` | chat_oneshot & repl completion | `record_outcome()` |

### Editing strategy
- NEVER full-file write on openai_wrapper.py (causes streaming failures)
- Always use surgical `edit` with unique oldString
- Verify syntax after each edit
- Run `python3 -m pytest tests/ -v` after each batch

## API Key Architecture
- Keys in `~/.routingmagic/.env` (0600 perms)
- Loaded via python-dotenv: `~/.routingmagic/.env` > `~/global.env` > env vars
- No hardcoded keys in repo
- `.env.example` committed as template

## OpenAI Client Standards
- **Always disable retries**: `OpenAI(..., max_retries=0)` MUST be used. Internal client retries bypass our thread-level timeouts (`f.result(timeout=35.0)`) and will cause the Model Council quorum racing mechanism to hang indefinitely if an API provider is stuck.
- **Fail Fast**: The entire fallback architecture relies on failing fast within 15-25 seconds and immediately trying a different API provider.

## User-facing commands
| Command | Function |
|---------|----------|
| `ask` | REPL (context-aware) |
| `ask deep` | REPL (with codebase scan) |
| `ask MC` | REPL with Model Council |
| `ask deep MC` | Council + deep context |
| `/savings` | Token savings dashboard |
| `/savings breakdown` | Savings by component |
| `/savings models` | Model efficiency ranking |
| `/savings export` | CSV export |
| `/caveman-feedback` | Report compression quality |

## GitHub Actions CI Fix (2026-08-27)
- Workflow failed in 4s: pip cache error (no requirements.txt) + health checks crashed without NVAPI_KEY secret
- Fix: requirements.txt, SKIP_HEALTH_CHECKS env var, API key detection step
- Now runs daily at 1 AM UTC; health checks only when NVAPI_KEY configured
- File: `.github/workflows/update-models.yml`, `model_registry_updater.py`

## Unified Dashboard — COMPLETED (UAT Fixes Done)
- Adaptive scanner: `adaptive_scanner.py` — auto-discovers active tools, loads only ACTIVE adapters
- Quota engine: `quota_engine.py` — multi-dimensional (rate limits, subscriptions, credits, custom caps)
- Ollama proxy: `ollama_proxy.py` — middleware server logging tokens to SQLite
- Antigravity adapter: `adapters/antigravity.py` — parses `agy /usage --json` and `agy /credits --json` (agy CLI not installed on this machine)
- ChatGPT adapter: `adapters/chatgpt.py` — OpenAI API /v1/usage endpoint
- Competitor adapters: `adapters/competitors/` — 10+ scaffolded (Cursor, Windsurf, Copilot, etc.)
- Dashboard UI: budget header, quota panel, WebSocket alerts (WebSocket removed, polling-based)
- Daemon mode: auto-port (9898+), PID file with port, double-fork
- REPL integration: auto-start daemon, `/quota`, `/sources` commands planned
- Plan doc: `UNIFIED_DASHBOARD_PLAN.md`

### UAT Fixes (12/12 Complete)
| Fix | Description |
|-----|-------------|
| CRIT-1 | Session ID unified: composite `source:raw` in both tables; recompute only updates matching turns |
| CRIT-2 | Empty sources flagged: always DELETE + `scan_state.status='empty'` |
| CRIT-3 | is_free unified: token-based (provider prefix, :free suffix, -free tokens) |
| HIGH-6 | XSS fix: topic escaped with esc(), onclick with escJs() |
| HIGH-7 | Rescan lock + same-origin CORS: single-flight, 10s rate limit, localhost-only CORS |
| HIGH-4 | PID file: `pid\nport` atomic write via temp+replace |
| HIGH-5 | Budget from quotas.yaml: validated positive numbers |
| MED-9 | Caching: mtime-based invalidation with lock |
| MED-10 | Timestamps: _ts_to_iso handles epoch, numeric strings, ISO |
| MED-11 | Chart.js: vendored to assets/, local-first with CDN fallback |
| MED-12 | WebSocket removed: dead code deleted, polling-based updates |
| LOW-13/14 | 11/11 pytest pass, smoke tests verified |

All 11 pytest tests pass.

## Model Council — VERIFIED FREE MEMBERS (2026-09-13)
- `nvidia/nemotron-3-super-120b-a12b` (NIM direct, Tier 1) — 5/5 probe, ~1.2s
- `nex-agi/nex-n2.5-mini:free` (OpenRouter) — 5/5 probe, ~2.8s
- `nvidia/nemotron-3.5-lightning:free` (OpenRouter) — 5/5 probe, ~4.5s (occasionally 30s first-token)
- Defined in `vercel/api/council.py` COUNCIL_MODELS; local council engine (`openai_wrapper.py`)
  sources from `registry/model_registry.json` via `_get_council_fallback_models()`.
- Health proof: `python3 scripts/council_health.py` (free-only, exit≠0 on failure).
- KEY FACT: health = HTTP 200 + NON-EMPTY content. A verbatim "OK" match falsely degrades
  verbose-but-healthy models (Nemotron super-120b). 429/transient 5xx ≠ dead.

## Dead-model graveyard (2026-09-13, verified ABSENT from live OpenRouter catalog)
`google/gemma-2-9b-it:free`, `mistralai/mistral-7b-instruct:free`, `openai/gpt-oss-120b:free`,
`qwen/qwen3-coder:free`, `qwen/qwen-2.5-72b-instruct:free`, `meta-llama/llama-3.1-8b-instruct:free`,
`microsoft/phi-3-mini-128k-instruct:free`, `microsoft/phi-4-mini-reasoning:free`,
`meta-llama/llama-3.3-70b-instruct:free`, `z-ai/glm-5.2:free`, `minimax/minimax-m2.7:free`,
`deepseek/deepseek-v4-flash:free`, `qwen/qwen-2.5-coder-32b-instruct:free`.
Never restore these from memory — they are delisted.

## OmniRouter — NOT in this repo
- No file matches omni/omnirouter. Grep found only `nemotron-3-nano-omni-*` model ids.
- Selector sources are `model_registry_updater.py` + `registry/model_registry.json`
  (`merged_fallback_chain`, `openrouter_free_models`, `nim_free_models`).
- Any doc referencing "OmniRouter lives in RoutingMagic" is unverified.

## Council architecture facts (2026-09-13, audited)
- `vercel/api/council.py` COUNCIL_MODELS = the Vercel path. The LOCAL `run_council` in
  `openai_wrapper.py` is REGISTRY-driven: picks members RANDOMLY from registry top-5 per
  source (nim/openrouter/opencode) + direct gemini/zai when keys present. Edit
  `_get_council_fallback_models()` (line ~104) only pads fallbacks, it does not pin members.
- Chairman: high-reasoning regex (`audit|proof|algorithm|...`) → `get_dynamic_model(free=False)`
  default `openai/o3-mini` — PAID path for audit-style prompts. General → free.
- Vision chain: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` (probed LIVE, vision)
  then `openai/gpt-4o-mini` (paid last resort). No free vision alternative works via this wrapper.
- NIM direct: only `nvidia/nemotron-3-super-120b-a12b` verified 5/5. `deepseek-ai/deepseek-v4-flash-0731`
  returns EMPTY content (registry chain leader — self-heals downstream). vision-instruct 500s, omni 403.
- NIM id convention: provider-native BARE ids (`deepseek-ai/...`); local `nvidia/`/`openrouter/`
  prefixes are wrapper-local and stripped before the call.
- Verified-live free models (2026-09-13 probe evidence): super-120b (NIM), nex-n2.5-mini:free,
  nemotron-3.5-lightning:free (OR), nemotron-3-nano-omni-30b-a3b-reasoning:free (OR, vision).

## Model Council automation (2026-09-13)
- **Pinned free pool** = `registry/verified_free_models.json` (single source of truth; NEVER hand-edit). council: super-120b + nex-n2.5-mini:free + lightning:free; chairman: nex-n2.5-mini:free; vision: omni :free.
- **`scripts/verify_free_models.py`** probes pool → GHA daily 1 AM UTC (`update-models.yml` step after registry refresh), `--fix` auto-rotates, exit 1 breaks the run. `rewrite_council_py` uses line-slicing (regex = catastrophic backtracking, LESSONS #031).
- **Runtime load order**: verified pool first → registry random draw (provider-diverse ≥3 sources); plan: get_dynamic_model free only.
- **Chairman is ALWAYS free** (o3-mini path removed 2026-09-13). Ultimate chain: no paid members.
- **Vision reality**: only free vision-capable id = omni model; image path flaps at OR (choices=None on 200 is transient); runtime chain = omni → paid gpt-4o-mini last resort. Never treat a text probe of a vision model as vision-capable proof.
