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
