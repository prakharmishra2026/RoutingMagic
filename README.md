# RoutingMagic 🪄

**Multi-model orchestration for Claude Code** — route every task to the cheapest model that
can do it perfectly, delegate parallel sub-tasks to free models, and never get stuck when a
free model is rate-limited (429) thanks to built-in **fallback chains**.

Two fully isolated worlds:

- **NATIVE** Claude — Opus 4.8 / Sonnet 4.6 / Haiku 4.5, direct to `api.anthropic.com`.
- **FREE** — 9 OpenRouter free models via the local [9router](https://www.npmjs.com/package/9router)
  gateway (`127.0.0.1:20128`). $0, opt-in via `cc*` aliases only — never pollutes global config.

---

## Why this exists

OpenRouter `:free` models hit `429 — rate-limited upstream` (the **Crucible** error that killed
Kimi K2.6). There's no single free model that never 429s, so RoutingMagic does two things:

1. **Picks resilient models** — only free models with healthy upstream **provider diversity**
   are in the roster (GPT-OSS-120B has 19 providers, Gemma-4-31B has 11). More providers =
   OpenRouter fails over internally = fewer hard-429s.
2. **Gives every role a fallback chain** — if your model 429s, relaunch the same task on the
   next alias in its chain. You always have a backup.

> The only *complete* fix for 429s is BYOK (add your own provider key at
> `https://openrouter.ai/settings/integrations`) or buying ≥$10 of OpenRouter credits to raise
> the daily cap. RoutingMagic minimises the pain until then.

---

## The roster

### FREE (via 9router → OpenRouter, $0)

| Alias | Model | Role | Context | Providers |
|-------|-------|------|--------:|----------:|
| `cc`  | Laguna M.1 | general coding (default) | 262k | — |
| `cch` | Laguna XS.2 | quick edits / one-liners | 262k | — |
| `cca` | Nemotron 3 Super 120B | large context | **1M** | — |
| `ccc` | **Qwen3-Coder** | UI / frontend (default) | **1M** | 7 |
| `cck` | Kimi K2.6 ⚠ | UI (kept) — 429s often, prefer `ccc` | 262k | — |
| `ccg` | **GPT-OSS-120B** ★ | reasoning + tools | 131k | **19** |
| `ccx` | **Qwen3-Next-80B** | general / agentic | 262k | 6 |
| `ccz` | **GLM-4.5-Air** | fast all-rounder | 131k | 4 |
| `ccm` | **Gemma-4-31B** | resilient general | 262k | 11 |
| `ccu` | **Nemotron 3 Ultra 550B** ⚠ | flagship reasoning | **1M** | 1 |
| `ccb` | Builder | auto multi-model | — | — |

★ `ccg` (GPT-OSS-120B) is the **most reliable** free model — the universal fallback.
⚠ `ccu` (Nemotron 550B) is the most *capable* free reasoner but is served by a **single
provider**, so it's more 429-prone — use it as a fallback, not a daily driver.
⚠ `cck` (Kimi K2.6) is **kept** so it auto-works if its upstream recovers, but it 429s
frequently today — the UI default is `ccc` (Qwen3-Coder).

### NATIVE (direct to Anthropic)

| Alias | Model | Role |
|-------|-------|------|
| `ccs` | Sonnet 4.6 | production, agentic, tool-heavy |
| `cco` | Opus 4.8 | architecture, hardest reasoning |
| `ccq` | Haiku 4.5 | fastest native |

---

## 429 fallback chains

When a free model returns 429, jump to the next alias in its role chain:

| Role | Primary | → Fallback 1 | → Fallback 2 |
|------|---------|--------------|--------------|
| UI / frontend | `ccc` | `ccz` | `ccm` (`cck`/Kimi optional) |
| General coding | `cc` | `ccg` | `ccx` |
| Reasoning | `ccg` | `ccu` ⚠ | `ccx` |
| Large context (1M) | `cca` | `ccc` | `ccu` ⚠ |
| Quick / trivial | `cch` | `ccz` | — |
| Agentic / tools | `ccg` | `ccx` | `cc` |

**Universal rule:** when everything 429s, fall back to `ccg`.

---

## Install

**Prerequisites:** [Claude Code](https://claude.com/claude-code), and
[9router](https://www.npmjs.com/package/9router) for the free models
(`npm i -g 9router`, then run `9router` to start the gateway on `:20128`).

```bash
git clone https://github.com/prakharmishra2026/RoutingMagic.git ~/RoutingMagic
cd ~/RoutingMagic
./install.sh
```

`install.sh` will:
1. Append `source ~/RoutingMagic/aliases.zsh` to your `~/.zshrc` (idempotent — won't duplicate).
2. Symlink the skill into `~/.claude/skills/RoutingMagic/` so Claude Code auto-loads it.

Then reload your shell:

```bash
source ~/.zshrc
cc-models        # print the cheatsheet + fallback chains
```

> The aliases set the 9router gateway **inline per call** — they never touch
> `~/.claude/settings.json`, so the native `/model` picker keeps working.

---

## Usage

```bash
# Pick a model directly
ccc                       # launch Claude Code on Qwen3-Coder (UI work)
ccg                       # GPT-OSS-120B (reasoning / safest free)
ccs                       # native Sonnet 4.6

# Let the router decide
cc-route "build a Tailwind modal with a slide-in animation"   # → ccc
cc-route "audit the entire codebase for auth bugs"            # → ccs (security → native)
cc-route "read all files and summarize the architecture"     # → cca (1M context)

# Check things
cc-models                                       # cheatsheet
nc -z 127.0.0.1 20128 && echo UP || echo DOWN   # is 9router running?
```

Inside a Claude Code session, the agent reads `SKILL.md` and follows the **delegation protocol**:
it keeps tool-heavy / security / production work on native Sonnet, and hands self-contained
sub-tasks (UI components, large reads) to free models in parallel terminals, picking up their
output from `scratchpad.md` / `tmp_*` files.

---

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | The skill Claude Code loads — roster, decision tree, fallback chains, delegation protocol |
| `aliases.zsh` | All `cc*` shell functions + `cc-route` + `cc-models` (self-contained) |
| `install.sh` | Idempotent installer (zshrc source line + skill symlink) |
| `memory.md` | Durable routing decisions & rules (also a free-model delegation output target) |
| `progress.md` | Chronological log of what's been built (also a delegation output target) |

---

## Updating the roster

OpenRouter's free catalog changes often (models appear, get renamed, or get retired — e.g.
Kimi K2.6 → Qwen3-Coder). To refresh:

```bash
# list current free models
curl -s https://openrouter.ai/api/v1/models \
  | python3 -c "import json,sys;[print(m['id'],m['context_length']) for m in json.load(sys.stdin)['data'] if float(m['pricing']['prompt'] or 1)==0]"

# check a model's provider count (429 resilience) and tool support
curl -s https://openrouter.ai/api/v1/models/<author>/<slug>/endpoints | python3 -m json.tool
```

Prefer models with **many providers** and **`tools` in `supported_parameters`** (Claude Code
needs tool-calling). Update `aliases.zsh`, `SKILL.md`, and this README together.

---

## License

See [LICENSE](LICENSE).
