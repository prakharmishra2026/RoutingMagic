# OpenCode Model Menu — Consumer Migration Guide

## Overview
The OpenCode model picker menu is now auto-maintained by RoutingMagic. The pipeline:
1. **Daily (GitHub Action at 1AM UTC):** fetches benchmarks → builds rankings → builds menu → syncs to `opencode_model_menu.json`
2. **On launch (`oc` command):** checks staleness (>12h), rebuilds if needed, then launches opencode
3. **Daily (launchd at 6AM):** backstop refresh to catch missed GitHub Action runs

## Files Produced
| File | Purpose |
|------|---------|
| `registry/opencode_model_menu.json` | Ready-to-consume per-provider whitelists + display names |
| `registry/task_rankings.json` | Per-task ranked models (primary_free + secondary_paid) |
| `registry/benchmark_raw.json` | Raw benchmark data (OpenRouter, Aider, HF Trending) |
| `registry/opencode_sync_snapshot.json` | Diff of last sync (what changed) |

## How to Sync Manually
```bash
# Dry run — shows what would change
python3 scripts/opencode_menu_sync.py --diff

# Apply changes (with backup)
python3 scripts/opencode_menu_sync.py

# Force sync (skip validation)
python3 scripts/opencode_menu_sync.py --force

# Restore last backup
python3 scripts/opencode_menu_sync.py --restore
```

## How to Launch OpenCode
```bash
# Uses ~/.local/bin/oc (auto-refreshes stale menu, then launches opencode)
oc

# Direct launch (skip refresh)
~/.opencode/bin/opencode
```

## Ranking Logic
- **Task taxonomy:** coding, reasoning, agentic, long_context, fast_cheap_chat, vision, finance_numbers
- **Free tier (primary):** models verified free at OpenRouter (confirmed via live API)
- **Paid tier (secondary):** best benchmark-per-dollar, top 10 per task
- **Sources:** Aider Polyglot (181 entries), OpenRouter live pricing, HF Trending, model_aliases.json mapping

## Investogram Migration
The vendored copy at `.agents/skills/routing-magic/` should read from `registry/opencode_model_menu.json` instead of maintaining its own `skills-lock.json`. See:
- `.agents/skills/routing-magic/README.md` (update vendor instructions)
- `.github/workflows/update-models.yml` (already extended to build menu)

## Provider Detection
| Provider | Rule |
|----------|------|
| `nvidia` | Models starting with: `nvidia/`, `deepseek-ai/`, `poolside/`, `minimaxai/`, `moonshotai/`, `cohere/`, `thinkingmachines/`, `dots-studio/` |
| `openrouter` | Everything else (including `deepseek/`, `qwen/`, `google/`, `z-ai/`, `minimax/`) |
