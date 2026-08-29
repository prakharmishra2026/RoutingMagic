# RoutingMagic — Next Session Continuation Prompt

## Current State (as of 2026-08-29)

### ✅ Completed
- **GitHub Actions CI fixed**: Daily model registry update workflow now runs successfully
  - Added `requirements.txt` for pip cache
  - Health checks skipped gracefully when `NVAPI_KEY` secret missing
  - Workflow runs daily at 1 AM UTC; health checks only when NVIDIA key configured
- **All tests pass**: 11/11 pytest tests passing
- **Unified Dashboard Plan created**: `UNIFIED_DASHBOARD_PLAN.md` (808 lines)

### 🎯 Next Priority: Unified Token Dashboard (Phase 7)

The plan covers adaptive discovery of 8+ AI tools, multi-dimensional quota tracking, and standalone package distribution.

## Immediate Next Steps (in order)

### 1. Verify Antigravity CLI JSON Output
```bash
agy /usage --json
agy /credits --json
```
**Need to know**: Do these output valid JSON? If not, we'll parse TUI text output.

### 2. Test Ollama Proxy Approach
```bash
# Will create ollama_proxy.py that runs `ollama serve` internally
# Proxies :11435 → :11434, logs all requests to SQLite with token counts
# Users run `ollama-proxy serve` instead of `ollama serve`
```

### 3. Add GitHub Secrets (Required for CI Health Checks)
Go to GitHub repo → Settings → Secrets and variables → Actions → New repository secret:
- `NVAPI_KEY` — from https://build.nvidia.com/nim/dashboard
- `OPENROUTER_API_KEY` — from https://openrouter.ai/keys

### 4. Begin Phase 1 Implementation
Create these files in order:
1. `adaptive_scanner.py` — Auto-discovery + state-aware scanning
2. Extend `unified_scanner.py` schema (adapter_state, quota_budgets, quota_snapshots, budget_alerts)
3. `quota_engine.py` — QuotaEngine, budgets, alerts, projections
4. `dashboard_server.py` updates — daemon mode, WebSocket, quota API

## Key Architectural Decisions (Confirmed)

| Decision | Resolution |
|----------|------------|
| **Adaptive discovery** | Auto-scan known paths + CLI + API on every scan; only load ACTIVE adapters |
| **Deep tracking** | 4 states: ACTIVE (full), STALE (shallow), CONFIGURED (hint), MISSING (hidden) |
| **Your tools prioritized** | Ollama (proxy), Antigravity (CLI JSON), ChatGPT (OpenAI API) — all deep-tracked |
| **Competitors** | 10+ adapters auto-load if installed (Cursor, Windsurf, Copilot, etc.) |
| **Quota tracking** | Multi-dimensional: rate limits, subscriptions, credits, custom caps |
| **Budget visibility** | Budget header + per-provider panel with "Used / Remaining" + color bars |
| **Alerts** | 80%/90%/100% → desktop notifications + WebSocket dashboard flash |
| **Packaging** | Standalone `pipx install routingmagic-dashboard` + RoutingMagic integration |

## Files to Reference

| File | Purpose |
|------|---------|
| `UNIFIED_DASHBOARD_PLAN.md` | Full 808-line implementation plan |
| `progress.md` | Phase tracking (74% complete) |
| `memory.md` | Architecture facts, integration points, dashboard plan summary |
| `scratchpad.md` | Session history with CI fix details |
| `lessons.md` | Lessons 013-015 (pip cache, optional health checks, param shadowing) |
| `.github/workflows/update-models.yml` | Fixed CI workflow |
| `model_registry_updater.py` | Updated with SKIP_HEALTH_CHECKS support |
| `requirements.txt` | For pip cache |

## Commands to Resume

```bash
cd /Users/grandvision/Projects/RoutingMagic

# Verify current state
python3 -m pytest tests/ -v
python3 model_registry_updater.py --daily --output-dir ./registry

# Test Antigravity JSON (run and report output)
agy /usage --json
agy /credits --json

# Begin Phase 1: Create adaptive_scanner.py
# ... implementation continues
```

## Context for Next Agent

You are continuing the RoutingMagic project. The GitHub Actions CI is now fixed. The next major feature is the **Unified Token Dashboard** — a universal, agnostic dashboard that:
- Auto-discovers what AI tools are installed/active
- Deep-tracks only active tools (adaptive discovery)
- Shows tokens consumed AND remaining (multi-dimensional quotas)
- Runs as persistent daemon on auto-discovered free port
- Available as standalone package (`pipx install routingmagic-dashboard`) AND integrated into RoutingMagic REPL

The full plan is in `UNIFIED_DASHBOARD_PLAN.md`. Start with verifying Antigravity CLI JSON output, then begin Phase 1 implementation.