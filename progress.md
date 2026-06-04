# RoutingMagic — Progress

Chronological log of what's been built. Free-model delegation output may append here
(`## <Phase/Feature>` + status + files) per the SKILL.md delegation protocol.

---

## 2026-06-05 — Extracted to standalone repo + 429-resilient roster
**Status:** ✅ done · pushed to https://github.com/prakharmishra2026/RoutingMagic

- Packaged the routing protocol as a standalone, installable skill (out of the Investogram
  project so it doesn't pollute it).
- Files: `SKILL.md` (the skill), `aliases.zsh` (all `cc*` functions + `cc-route` + `cc-models`),
  `install.sh` (idempotent installer), `README.md`, `memory.md`, `progress.md`.
- Replaced the chronically rate-limited Kimi K2.6 as the UI default; selected new free models by
  upstream **provider diversity** to minimise the Crucible 429.

## 2026-06-05 — Kept Kimi, added Qwen3-Coder under its own alias
**Status:** ✅ done

- `cck` restored to **Kimi K2.6** (kept for when its upstream recovers).
- `ccc` added → **Qwen3-Coder** (the reliable UI/frontend default).
- New free models added with roles: `ccg` GPT-OSS-120B (reasoning/safest, 19 providers),
  `ccx` Qwen3-Next-80B (general/agentic), `ccz` GLM-4.5-Air (fast all-rounder),
  `ccm` Gemma-4-31B (resilient general, 11 providers), `ccu` Nemotron-3-Ultra-550B (flagship ⚠ single provider).
- Added 429 **fallback chains** for every role (UI: `ccc → ccz → ccm`; universal: `ccg`).
- Updated `SKILL.md`, `aliases.zsh`, `README.md` to match.

## Current roster (11 free + 3 native)
FREE: `cc` Laguna M.1 · `cch` Laguna XS.2 · `cca` Nemotron-3-Super (1M) · `ccc` Qwen3-Coder (1M) ·
`cck` Kimi K2.6 ⚠ · `ccg` GPT-OSS-120B ★ · `ccx` Qwen3-Next-80B · `ccz` GLM-4.5-Air ·
`ccm` Gemma-4-31B · `ccu` Nemotron-3-Ultra-550B ⚠ · `ccb` Builder.
NATIVE: `ccs` Sonnet 4.6 · `cco` Opus 4.8 · `ccq` Haiku 4.5.

## Backlog / ideas
- Consider BYOK (own provider key) to fully eliminate 429s if free-tier limits still bite.
- Refresh roster when OpenRouter's free catalog changes (script in README "Updating the roster").
