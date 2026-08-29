# Lessons Learned

## 001 — Full-file write on large files breaks streaming
**What broke**: Multiple attempts to full-rewrite `openai_wrapper.py` (2529 lines, ~110KB) timed out or failed mid-stream.
**Root cause**: The model cannot generate 110KB reliably in one shot via streaming API.
**Rule**: Never full-rewrite files >500 lines. Use surgical `edit` operations with unique oldString matching. One edit at a time, verify after each.

## 002 — Don't bundle integration points
**What broke**: Previous sessions tried to integrate all Caveman/metrics/quality/learner modules into openai_wrapper.py in one massive pass.
**Root cause**: Integration touches 8+ scattered locations in the file. Trying to do them all at once creates too many simultaneous edit operations.
**Rule**: One edit per integration point. Each edit is small (<20 lines changed), targeting a unique oldString. Verify syntax after each.

## 003 — Verify module imports exist before importing
**What broke**: `caveman_quality_loop.py` imported `get_metrics` from `metrics_collector.py`, but that function never existed in the module.
**Root cause**: Function was referenced in the import but never implemented in the source module.
**Rule**: After writing any module that imports from another local module, run the full import chain (`python3 -c "import openai_wrapper"`) to catch missing exports.

## 004 — 9router auto-start order
**Rule**: 9router auto-start should happen BEFORE API key checks. If 9router starts successfully, it provides OpenRouter access without needing OPENROUTER_API_KEY.

## 005 — 9router auto-start must happen before API key check
**What broke**: Module-level `_check_api_keys()` ran before 9router was auto-started, causing false "no API access" errors.
**Root cause**: 9router can provide OpenRouter access without needing OPENROUTER_API_KEY, but only if it's running first.
**Rule**: Call `_ensure_9router_running()` before `_check_api_keys()` at module load.

## 006 — Caveman confusion detection needs narrow patterns
**What broke**: Broad patterns like "explain" would trigger false-positive confusion signals on normal requests like "explain how X works".
**Root cause**: Natural language has many phrases that overlap with re-ask/complaint patterns.
**Rule**: Use specific multi-word patterns ("didn't understand", "not what i asked") instead of single words. Test against common false positives.

## 007 — Surgical edits beat file writes for large files
**What worked**: Replacing full-file rewrites with 6 small targeted `edit` operations completed the entire integration without a single streaming failure.
**Root cause**: Each edit targets ≤20 lines with a unique oldString, fits in one API call.
**Rule**: For files >500 lines, always plan integration as a series of targeted edits. Never attempt a single-edit or full-file approach.

## 008 — Pre-existing test failures
**Rule**: `test_smart_route_logic` and `test_get_client_and_model` were already failing before our changes. Don't fix unrelated test failures during feature integration. Note them and move on.

## 009 — Always verify SQLite table column count against INSERT statements
**What broke**: `CREATE TABLE sessions` created 19 columns, but `INSERT OR REPLACE INTO sessions VALUES` had 18 placeholders `?`.
**Rule**: Always verify `len(columns)` equals `len(placeholders)` in SQL insert queries.

## 010 — Test suite maintenance
**Rule**: Keeping the automated test suite at 100% passing (`pytest tests/ -v`) ensures regression-free surgical edits on large codebases.

## 011 — Internal OpenAI Client Retries (Hidden Timeouts)
**What broke**: Model Council hung for 75s and triggered false quorum cancellations.
**Root cause**: The `openai` python client automatically retries failed API requests up to 2 times. If a request is stuck, it hangs for `timeout * 3` seconds, completely bypassing our manual 35-second thread limits and falling out of sync with the quorum racing mechanism.
**Rule**: ALWAYS explicitly pass `max_retries=0` when instantiating `OpenAI(api_key=..., timeout=..., max_retries=0)`. We want the client to fail fast so our custom fallback logic can instantly route to a different provider.

## 012 — Real Caveman Integration (System Prompts vs CLI)
**What broke**: Attempted to use a non-existent `caveman-compress` CLI binary via `subprocess.run()`, which always failed and fell through to simple truncation.
**Root cause**: Caveman is actually implemented as a SYSTEM PROMPT INJECTION (instructing the LLM to output caveman-speak), not a post-processing binary.
**Rule**: Always inspect the upstream project (like Caveman's `SKILL.md`) to understand its architecture before implementing an integration. Do not hallucinate CLI tools.

## 013 — GitHub Actions pip Cache Requires requirements.txt
**What broke**: `actions/setup-python@v5` with `cache: 'pip'` failed immediately with "no file in requirements.txt or pyproject.toml" — workflow died in 4 seconds.
**Root cause**: Pip cache action requires a dependency file to compute cache key. Standalone script projects without `requirements.txt` cannot use this cache.
**Rule**: Either add minimal `requirements.txt` for cache, or remove `cache: 'pip'`. For single-script projects, adding `requirements.txt` is trivial and enables caching.

## 014 — Health Checks Must Be Optional When Secrets Missing
**What broke**: Model registry health checks crashed in GitHub Actions because `NVAPI_KEY` secret wasn't configured, but workflow unconditionally ran `asyncio.run(run_health_checks(...))` which tried to call NVIDIA API without auth.
**Root cause**: Workflow assumed secrets exist; health check function had no graceful degradation for missing credentials.
**Rule**: Make health checks conditional on secret availability. Add workflow step to detect missing secrets, set env var (e.g., `SKIP_HEALTH_CHECKS=true`), and have code respect it.

## 015 — Parameter Shadowing Function Name
**What broke**: Renamed `run_health_checks` parameter to `do_health_checks` to avoid shadowing the `run_health_checks()` function, but forgot to update the call site — got `TypeError: 'bool' object is not callable` when `asyncio.run(run_health_checks(...))` tried to call the boolean parameter.
**Root cause**: Parameter name matched function name; inside function scope, parameter shadows outer function.
**Rule**: Never name parameters the same as functions they call. Use `do_` prefix for boolean action parameters (e.g., `do_health_checks`, `run_health_checks` → `do_health_checks`).

## 016 — Session ID Unification Must Be Bidirectional
**What broke**: `unified_sessions.session_id` stored composite `source:raw` but `unified_turns.session_id` stored raw ID. Recompute JOIN `t.session_id = s.session_id` never matched → all session totals zeroed.
**Root cause**: Adapter returns raw session_id; `_aggregate_sessions` prefixed for sessions table but `upsert_turns` didn't prefix for turns table.
**Rule**: When changing session ID format, update BOTH write paths (turns and sessions). Verify with `SELECT COUNT(*) FROM sessions s LEFT JOIN turns t ON t.session_id=s.session_id WHERE t.session_id IS NULL` — must be 0.

## 017 — Stale Data Persists When Adapter Returns Empty
**What broke**: Adapter returning `[]` (missing DB, transient error, or removed source) left old rows in `unified_turns` and `unified_sessions` because `scan()` only DELETE+reinsert when `rows` is truthy.
**Root cause**: `scan()` conditional on `if rows:` before DELETE. Removing a source (e.g., 9router) left its stale data visible with no indication.
**Rule**: ALWAYS DELETE source rows + remove from `scan_state` regardless of adapter result. If adapter returns `[]`, set `scan_state.status='empty'` so UI shows "empty" not stale data.

## 018 — Free/Paid Classification Must Be Token-Based, Not Substring
**What broke**: `FREE_MODELS` set used `if kw in model` substring matching. `"nemotron" in "nvidia/nemotron-3-ultra-550b-a55b"` → True, but this model is PAID on OpenRouter (only `:free` suffix is free).
**Root cause**: Substring matching catches false positives across provider boundaries.
**Rule**: Use token-based matching — split on `/`, `-`, `.`, `_`, `:` → tokens. Free if: provider prefix in `{nvidia, nim, opencode}`, `:free` suffix, `-free` token, or known free tokens `{gpt-oss, big-pickle, laguna}`. Single shared `is_free(model, source)` used by server + serialized to frontend.

## 019 — CORS Wildcard Is a Security Hole
**What broke**: All API endpoints sent `Access-Control-Allow-Origin: *`, allowing any website to trigger expensive rescans and read usage data.
**Root cause**: CORS wildcard added for convenience during development, never restricted.
**Rule**: Restrict CORS to same-origin only. Check `Origin` header; allow only `http://localhost:*` and `http://127.0.0.1:*`. Return 409 for concurrent rescans (single-flight lock).

## 020 — PID File Must Store Actual Port
**What broke**: `write_pid_file(port)` ignored the port argument; `get_running_dashboard_port()` hardcoded `return 9898`. If `find_free_port()` returned 9899+, dashboard open/stop targeted wrong port.
**Root cause**: PID file only stored PID, not port. Daemon port selection was dynamic but tracking wasn't.
**Rule**: PID file format `pid\nport` (two lines). Write atomically: temp file + `os.replace()`. Read both lines; validate PID alive before returning port.

## 021 — Budget Config Must Be Validated
**What broke**: Hardcoded `$50.00` / `2,000,000` in `get_budget_status()`. User couldn't configure; no validation meant negative/zero values could break UI.
**Root cause**: Budget defaults only in code, not user-editable config.
**Rule**: Read `monthly_usd` and `daily_tokens` from `~/.routingmagic/quotas.yaml` (same file as provider budgets). Validate positive numbers; fallback to defaults.

## 022 — Timestamp Normalization at Ingestion
**What broke**: `substr(timestamp, 1, 10)` and `datetime.fromisoformat()` silently fail on non-ISO timestamps (Unix epoch, numeric strings) → wrong day buckets, duration=0.
**Root cause**: Adapters passed raw timestamps; only some used `_ts_to_iso()`. Claude usage.db returns ISO but other sources may not.
**Rule**: Normalize ALL timestamps at ingestion via `_ts_to_iso(ts)` handling: ISO string, Unix epoch (sec/ms), numeric string, int/float. Then `substr(day, 1, 10)` is always correct.

## 023 — Cache Invalidation via File Mtime
**What worked**: `get_dashboard_data()` caching with mtime-based invalidation (`st_mtime_ns`) + lock is simple and correct. No stale reads; cache auto-invalidates when scan rewrites DB.
**Rule**: For read-heavy APIs with periodic writes, use `stat().st_mtime_ns` as cache key. Invalidate on mtime change. No TTL needed.

## 024 — Dead Code Removal (WebSocket)
**What broke**: WebSocket layer (100+ lines) was never used by frontend (polling every 30s). `ws_broadcast` called in quota monitor but no client connected. `_ws_recv` had infinite loop risk on large frames.
**Root cause**: Feature added but never wired; security risk from malformed frames.
**Rule**: Remove dead WebSocket code entirely. Frontend polling (30s) is sufficient for dashboard updates. Keep quota monitor for alert persistence (saves to DB), remove broadcast calls.

## 025 — Atomic PID File Write
**What worked**: `write_pid_file` uses `tempfile.NamedTemporaryFile` + `os.replace()` for atomic PID+port write. No partial reads on quick restart.
**Rule**: Always write PID/state files atomically: temp file in same directory + `os.replace()` (POSIX atomic rename).
