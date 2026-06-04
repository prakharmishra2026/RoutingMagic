# RoutingMagic — Memory (decisions & rules)

Durable decisions about this routing setup. Free-model delegation output also lands here
(`## <Model> — <Rule> — <Date>`) per the SKILL.md delegation protocol.

---

## Single source of truth
The canonical skill lives in THIS repo (`SKILL.md`). The Claude Code skill location
`~/.claude/skills/RoutingMagic` is a **symlink to this repo**, so editing repo files updates the
live skill. Do not keep a second standalone copy — one skill only.

## Kimi is kept, Qwen3-Coder is the UI default
`cck` → Kimi K2.6 is **retained** so it auto-works again if its upstream provider (Crucible)
recovers. But Kimi 429s frequently today, so the UI/frontend **default is `ccc` → Qwen3-Coder**
(1M context, 7 providers). Fallback chain for UI: `ccc → ccz → ccm` (try `cck`/Kimi only if up).

## 429 resilience is the design driver
OpenRouter `:free` models 429 from (1) a global free-tier limit and (2) upstream provider
exhaustion. We only add free models with healthy **provider diversity**, and every role has a
fallback chain. `ccg` (GPT-OSS-120B, 19 providers) is the universal safety net.
Single-provider `ccu` (Nemotron 550B) is a flagship fallback only, flagged ⚠.

## Never pollute global Claude config
The `cc*` free aliases set the 9router gateway **inline per call** (`ANTHROPIC_BASE_URL=...`).
NEVER put a proxy in `~/.claude/settings.json` — the native `/model` picker sends bare model IDs
that a proxy rejects.

## OpenRouter account tier
Account has ~$20 credit. Balance ≥ $10 → higher free-tier daily cap (~1000 req/day vs ~50).
Per-minute (~20/min) and upstream-provider 429s still possible; that's what fallback chains cover.
