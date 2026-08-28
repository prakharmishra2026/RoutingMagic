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

### 9router auto-start
- `_ensure_9router_running()` called at module load (before `_check_api_keys()`)
- Checks if 9router is on `:20128` via `is_port_open()`
- If not running, tries `9router -t` (tray/background)
- Waits up to 5 seconds, polling every 1s
- `FileNotFoundError` gracefully returns `False`
- If already running (port open), returns `True` immediately

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

## Unified Dashboard Plan (Next)
- Adaptive scanner: auto-discovers active tools (Claude, OpenCode, Codex, Ollama, Antigravity, ChatGPT, 9router, Hermes, RoutingMagic)
- Quota engine: multi-dimensional (rate limits, subscriptions, credits, custom caps)
- Ollama proxy: middleware server logging tokens to SQLite
- Antigravity adapter: parses `agy /usage --json` and `agy /credits --json`
- ChatGPT adapter: OpenAI API /v1/usage endpoint
- Dashboard UI: budget header, quota panel, WebSocket alerts
- Standalone package: `pipx install routingmagic-dashboard`
- REPL integration: auto-start daemon, `/quota`, `/sources` commands
- Plan doc: `UNIFIED_DASHBOARD_PLAN.md`
