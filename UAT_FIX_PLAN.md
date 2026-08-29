# UAT Audit — Unified Usage Dashboard
## Verified Findings (evidence-based, ordered by severity)

### CRITICAL — data correctness

**1. Sessions table shows 0 turns / 0 tokens for ALL sessions (206/206 confirmed).**
- `unified_scanner.py` stores a *composite* `session_id` (`"claude:89128567-..."`) in `unified_sessions.session_id` (from `_aggregate_sessions`, line 130), but `unified_turns.session_id` stores the *raw* id (`"89128567-..."`).
- The recompute `UPDATE` (lines 278–310) joins `t.session_id = s.session_id`, which NEVER matches. Result: every session's `turn_count`, `total_input/output`, cache, reasoning gets overwritten to 0.
- Verified: a real session's stored `turn_count=0, total_input=0` while its turns table actually has 300 turns / 18,605 input tokens. `sessions matching composite join: 0`.
- Impact: the entire "Recent Sessions" table, session turn counts, per-source/day cost charts (all derived from sessions) are broken/empty.

**2. Stale data persists when a source returns empty.**
- `scan()` (lines 250–256) only deletes+re-inserts when `rows` is truthy. An adapter that returns `[]` (missing DB, transient read error, or a source you removed — exactly what happened with 9router) leaves the *old* rows in place and leaves `scan_state` untouched.
- Dashboard then shows stale data as if current, with no indication it's stale.
- Verified by reading the control flow; we hit this live when removing 9router.

**3. Cost is unreliable / heavily undercounted.**
- **3a.** `FREE_MODELS`/`_is_free` uses `if kw in m` with bare keywords `"nemotron"`, `"glm"`, `"nvidia"`, `"deepseek-v4-flash"`. Verified: `nvidia/nemotron-3-ultra-550b-a55b` (a PAID NIM model) is classified FREE → shows $0.00 despite 18.5M input + 91.9M cache tokens.
- **3b.** `scan_claude` always sets `cost: 0.0`, so virtually all real cost comes only from the `calc_cost` fallback in `get_dashboard_data` (when `total_cost == 0.0`). Combined with 3a, most paid usage is reported as $0.
- **3c.** `get_pricing` uses `model.startswith(key)` which fails for provider-prefixed models (`openai/gpt-5.6-sol`); the loose `"gpt-5" in m` fallback then misbuckets.
- **3d.** Frontend "Free Usage %" (line 805) uses a *different* free rule (`:free` substring or `routingmagic`) than the server `_is_free`, so the two displays disagree.

### HIGH

**4. Port tracking is broken / hardcoded.**
- `get_running_dashboard_port()` (line 70) and `ensure_dashboard_running()` (line 102) hardcode `9898`, ignoring that `find_free_port()` may return 9899+. The PID file stores only a pid, not the port. `dashboard open/stop` can therefore target the wrong port or report "running" on a dead port.

**5. Monthly budget / daily cap hardcoded** (`$50.00` / `2,000,000` tokens) in `get_budget_status()` with no config source → fabricated budget figures.

**6. Stored-XSS in the dashboard.**
- `renderSessions()` (line 895) renders `topic` **unescaped** (`<td>${topic}</td>`). `topic` is populated from Claude session titles / source_metadata — free-form user text. A session title containing `<img onerror=...>` or `<script>` executes in the dashboard. Other model/source fields ARE escaped via `esc()`, so this is an inconsistency bug with security impact.

**7. `/api/rescan` + CORS `*` — unrestricted.**
- Any local client (and any website, since `Access-Control-Allow-Origin: *`) can trigger an expensive blocking rescan with no concurrency guard or rate limit. Repeated hits spawn unbounded scan threads.

**8. Recompute overwrites correct data** (mechanism of bug 1) — should only update, never zero, mismatched rows.

### MEDIUM

**9. No caching in `get_dashboard_data`** — full aggregation rerun on every `/api/data` call (every 30s auto-refresh). Fine at 4k rows, degrades as data grows.

**10. Timestamps assumed ISO-8601** — `substr(timestamp,1,10)` and `datetime.fromisoformat` break silently on non-ISO source timestamps (wrong day buckets, duration=0).

**11. Chart.js loaded from CDN** — dashboard charts break when offline, contradicting the "zero-dependency local tool" promise.

**12. WebSocket layer is dead code** — the HTML never uses WebSocket (it polls every 30s); `_ws_recv` only handles single unfragmented frames, has no read timeout, and a huge `payload_len` (case 127) can loop reading indefinitely.

### LOW

**13. Free-turns stat (JS) and server free-rule disagree** (see 3d).

**14. Cost charts keyed off broken sessions** — `renderCostDaily`/`renderCostModel`/`renderCostTable` all read `sessions_all`, so they inherit bug 1 and stay empty.

---

## Proposed Fix Plan (draft — for council review)

1. **Unify session-id scheme** (fix bug 1 & 8): store the SAME identifier in `unified_turns.session_id` and `unified_sessions.session_id`. Recommended: keep composite `source:raw` in BOTH, drop `source` from the recompute join, and make the recompute preserve correct values (only recompute when matching turns exist; never zero). Or store raw in both and use a separate composite key column for uniqueness. Decision needed on UX impact (session ids shown to user).
2. **Delete-by-source regardless of emptiness** (fix bug 2): always `DELETE` source rows + remove from `scan_state`, then insert whatever the adapter returned this run (including 0). Add stale/error flag if adapter raised.
3. **Fix pricing** (fix bug 3): explicit `:free` + delimited token match (e.g. split on `/`,`-`,`.`) instead of substring; add missing paid models; centralize one `is_free` used by both server and (serialized) client.
4. **Port correctness** (fix bug 4): persist actual port in PID file (`<pid>\n<port>`), read it back in `get_running_dashboard_port`.
5. **Configurable budget** (fix bug 5): read `monthly_budget`/`daily_cap` from a config (env or `~/.routingmagic/quotas.yaml`), default to current values.
6. **Escape `topic`** (fix bug 6): wrap in `esc()` in `renderSessions`.
7. **Guard rescan** (fix bug 7): single-flight lock, reject concurrent rescans (409), drop `Access-Control-Allow-Origin: *` (localhost only).
8. **Add caching** (fix bug 9): cache the aggregated payload with a short TTL or invalidate on rescan.
9. **Robust timestamps** (fix bug 10): normalize/none-safe parsing.
10. **Vendor Chart.js locally** (fix bug 11): ship `chart.umd.min.js` alongside, or degrade gracefully with a message when offline.
11. **Remove or fix WS** (fix bug 12): either wire the frontend to WS or delete the dead layer.
12. **Reconcile free-rule** (fix 13/14) and add a smoke test for the unified scanner + pricing.

---

## Model Council Verdict (appended after UAT)

Ran the plan through RoutingMagic's Model Council (`ask MC`). Committee agreed on almost everything and delivered a decisive order:

**(a) Per-fix verdict — ALL ACCEPT except one revision:**
- Fixes 1,2,3,4,5,6,7,9,10,11,12 → **Accept**
- **Fix 8 "add caching" → REVISE**: caching was mislabeled as fixing the zeroing bug. Caching is a *performance* improvement for `get_dashboard_data`, NOT the fix for the recompute-zeroing bug — that root cause is only solved by Fix 1 (correct recompute). Keep caching but as a separate perf task.

**(b) Council corrections (do differently):**
- **Fix 7 (CORS)**: don't just remove `Access-Control-Allow-Origin: *` — restrict it to same-origin so legit local access still works while closing the hole.
- **Fix 3 (cost)**: also make `scan_claude` stop hardcoding `cost: 0.0`; one shared paid/free rule across server + adapters + frontend.
- **Fix 5 (budget)**: validate inputs (positive ints); a configurable budget no one can set safely is a foot-gun.
- **Fix 6 (escape)**: escaping must be context-aware (HTML vs attribute vs JS), not a blanket call.
- **Fix 2 (stale)**: when a source returns empty, set `scan_state` to "empty", not "stale" — so it's visibly empty, not silently untracked.
- **Fix 4 (port)**: write the pid file atomically to avoid a race on quick restart.

**(c) Missed risks the council flagged:**
- Recompute fix must be regression-tested against real data (must never zero correct totals again).
- Budget enforcement without config is useless — tie enforcement to the config.
- Smoke tests (Fix 12) should be written AFTER the other fixes so they actually verify them.

**(d) Final recommended execution order (council-endorsed):**
1. CRIT-1 unify session_id + fix recompute (stops the all-zeros bug)
2. CRIT-2 always delete+flag empty sources (stops stale data)
3. CRIT-3 fix is_free + unify paid/free cost rules
4. HIGH-6 escape topic (XSS)
5. HIGH-7 rescan lock + restrict CORS
6. HIGH-4 persist actual port
7. HIGH-5 configurable + validated budget
8. MED-9 caching with TTL (perf only)
9. MED-10 robust timestamp parsing
10. MED-11 vendor Chart.js locally
11. MED-12 remove dead WebSocket layer
12. LOW-13/14 scanner + pricing smoke tests (verify all above)

*Note: The Model Council transport itself had a crash bug (unhashable ModelInfo passed to set()) during this UAT; a one-line normalization fix was applied in openai_wrapper.py and the council then ran successfully. Worth a regression test / lessons entry.*
