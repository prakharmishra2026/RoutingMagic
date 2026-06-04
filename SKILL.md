---
name: RoutingMagic
description: >
  Multi-model orchestration protocol for Claude Code. Combines intelligent model routing
  with a structured delegation system so Sonnet/Opus can offload tasks to free models
  running in parallel terminals via 9router. Includes 429-resilient fallback chains so
  every role has a backup when a free model is rate-limited upstream. Use at the start of
  any session or task, when switching domains, or when the user types /route. Works in any project.
---

# RoutingMagic — Multi-Model Orchestration Protocol

> **One rule:** use the cheapest model that can do the job perfectly.
> **New rule:** when tasks can be parallelized, delegate to free colleagues.
> **Resilience rule:** every role has a 429 fallback chain — if a free model is
> rate-limited upstream, jump to the next model in the same role.
> Every routing decision shows its tier, model, reason, and fallback.

---

## Part 1 — Architecture: Two Isolated Worlds

| World | Gateway | Models | Activation |
|---|---|---|---|
| **NATIVE** | Direct → `api.anthropic.com` (keychain OAuth) | Opus 4.8 · Sonnet 4.6 · Haiku 4.5 | Default `claude`, `/model` picker, `ccs`/`cco`/`ccq` |
| **FREE** | `127.0.0.1:20128` → 9router → OpenRouter | 9 free models (see roster) | `cc*` aliases only |

**Critical rule:** NEVER put `env`, `ANTHROPIC_BASE_URL`, or any proxy in `~/.claude/settings.json`.
The `/model` picker sends bare IDs (`claude-sonnet-4-6`) that any proxy rejects.
`~/.claude/settings.json` should contain ONLY: `{"model":"sonnet","theme":"dark"}`

---

## Part 2 — Understanding the 429 Problem (Why Fallback Chains Exist)

OpenRouter free (`:free`) models can return:

```
429 — "<model> is temporarily rate-limited upstream ... provider_name: Crucible"
```

This happens for two independent reasons:

1. **Global free-tier limit** — OpenRouter caps all `:free` traffic (~20 req/min,
   plus a daily cap that scales with your credit balance). Shared across *every* free model.
2. **Upstream provider exhaustion** — each `:free` model is served by one or more
   free upstream providers. When that provider's free pool is saturated it returns 429.
   Popular, thinly-served models (Kimi K2.6 via Crucible) hit this constantly.

**Mitigations, in order of effectiveness:**

- **Provider diversity** — models served by many providers let OpenRouter fail over
  internally (gpt-oss-120b: 19 providers; gemma-4-31b: 11). These rarely hard-429.
- **Fallback chains** — when your model 429s, relaunch the same task on the next model
  in its role chain (see Part 4). This is what the multi-model roster is *for*.
- **BYOK / credits** — the only true fix. Add your own provider key at
  `https://openrouter.ai/settings/integrations`, or buy ≥$10 credits to raise the daily cap.

**Roster selection rule:** we only configure free models with healthy provider
diversity. The one exception is `ccu` (Nemotron 550B, single provider) — kept as a
flagship-reasoning fallback only, flagged ⚠ everywhere.

---

## Part 3 — Model Roster & Independent Assessment

### NATIVE Models (Anthropic — billed to subscription)

#### Claude Opus 4.8 (`cco`)
The deepest thinker in the roster. Exceptional at multi-step reasoning, system design,
trade-off analysis, structured plans. Activate only when the problem genuinely requires
extended reasoning — architecture, security-critical review, novel algorithms, codebase-wide
refactors. Wasteful for routine coding.
**Best for:** Architecture · ADR/PRD · schema migration · system-level security review · strategy

#### Claude Sonnet 4.6 (`ccs`) — default orchestrator
The primary workhorse. The right model for production code, agentic multi-step operations,
anything that writes to the filesystem or calls external services. The only model with fully
reliable tool-use in Claude Code. When you (Sonnet) read this file, you ARE this model —
your job is to decide what to keep and what to delegate.
**Best for:** Production bugs · auth/security · SEBI/compliance · agentic ops · tool-heavy tasks · integrating free-model output

#### Claude Haiku 4.5 (`ccq`)
Fastest native Claude. Quick utility calls where native tools are needed but the task is simple.
Rarely needed — free models cover most of this at $0.
**Best for:** Rapid native ops when 9router is down

---

### FREE Models (via 9router → OpenRouter, $0)

> Each entry lists context size, provider count (429 resilience), tool-calling support,
> and the role chain it belongs to.

#### GPT-OSS-120B (`ccg` — `openrouter/openai/gpt-oss-120b:free`)  ★ most reliable
**Context:** 131k · **Providers:** 19 · **Tools:** yes · **Reasoning:** yes
OpenAI's open 120B model. The single most *reliable* free model in the roster — 19 upstream
providers mean OpenRouter almost always finds a free slot, so 429s are rare. Strong at
reasoning, agentic tool-use, and general coding. This is the **default agentic/reasoning free
pick** and the first fallback whenever another free model is rate-limited.
**Best for:** Reasoning · agentic/tool-use tasks · general coding · the universal 429 fallback
**Chain:** reasoning (`ccg → ccu → ccx`) · agentic (`ccg → ccx → cc`)

#### Qwen3-Coder (`cck` — `openrouter/qwen/qwen3-coder:free`)  — UI/frontend slot
**Context:** 1M · **Providers:** 7 · **Tools:** yes
Alibaba's dedicated coding model (replaces the chronically rate-limited Kimi K2.6 on the `cck`
slot). Excellent at React/Next.js structure, Tailwind composition, Framer Motion, and idiomatic
TypeScript — give it a design system and it sticks to it. 1M context also makes it a strong
large-codebase coder. First call for any UI/frontend work.
**Best for:** React/Next.js · Tailwind · Framer Motion · glassmorphism · TS components · frontend bugs
**Avoid for:** security-critical code · production deploys without review
**Chain:** UI/frontend (`cck → ccz → ccm`)

#### Qwen3-Next-80B (`ccx` — `openrouter/qwen/qwen3-next-80b-a3b-instruct:free`)
**Context:** 262k · **Providers:** 6 · **Tools:** yes
Strong general-purpose / agentic model with a large context. Good balance of capability and
speed; handles backend logic, API work, and multi-step tasks well. The general/agentic fallback.
**Best for:** General coding · agentic tasks · backend logic · medium-large context
**Chain:** agentic fallback · general-coding fallback

#### GLM-4.5-Air (`ccz` — `openrouter/z-ai/glm-4.5-air:free`)
**Context:** 131k · **Providers:** 4 · **Tools:** yes
Zhipu's fast, lightweight all-rounder. Quick to respond, solid on frontend and general edits.
The primary UI fallback and a fast alternative for quick work.
**Best for:** Fast all-round coding · UI fallback · quick edits
**Chain:** UI fallback (`cck → ccz`) · quick fallback (`cch → ccz`)

#### Gemma-4-31B (`ccm` — `openrouter/google/gemma-4-31b-it:free`)
**Context:** 262k · **Providers:** 11 · **Tools:** yes
Google's Gemma 4. High provider diversity (11) makes it very 429-resistant. Reliable general
model with a large context. The deep UI fallback and a dependable general backup.
**Best for:** Resilient general work · large-context tasks · deep UI fallback
**Chain:** UI deep fallback (`cck → ccz → ccm`)

#### Laguna M.1 (`cc` — `openrouter/poolside/laguna-m.1:free`)  — general default
**Context:** 262k · **Tools:** yes
Poolside AI's flagship coding model and the default free all-rounder. A thinking model —
slower than XS.2 but more accurate. Particularly strong at Python/FastAPI backend, Pydantic,
algorithms, API integration. Use as the default free model unless a specialist fits better.
**Best for:** General coding · Python/FastAPI · API logic · Pydantic · algorithms · tests · bug diagnosis
**Chain:** general default (`cc → ccg → ccx`)

#### Laguna XS.2 (`cch` — `openrouter/poolside/laguna-xs.2:free`)
**Context:** 262k · **Tools:** yes
Smaller, faster Laguna. Best for short reasoning chains: renames, one-liners, small explanations,
scratchpad/memory updates. Not for complex multi-file work — M.1's depth is worth the wait there.
**Best for:** Quick edits · renames · one-liners · "what is X" · formatting · scratchpad updates
**Chain:** quick (`cch → ccz`)

#### Nemotron 3 Super 120B (`cca` — `openrouter/nvidia/nemotron-3-super-120b-a12b:free`)  — large context
**Context:** 1M (genuine) · **Tools:** yes · **Reasoning:** yes
NVIDIA's 120B MoE. The 1M context is real and reliable — the workhorse for ingesting an entire
medium-to-large codebase in one pass. Deliberate, thorough, excellent structured markdown output.
Not a speed demon. Use when breadth of context matters more than speed.
**Best for:** Full codebase audits · large-context analysis (>100k) · whole-file-tree reads · checklists/architecture docs from real code
**Chain:** large context (`cca → cck → ccu`, all 1M)

#### Nemotron 3 Ultra 550B (`ccu` — `openrouter/nvidia/nemotron-3-ultra-550b-a55b:free`)  ⚠ single provider
**Context:** 1M · **Providers:** 1 (DeepInfra) · **Tools:** yes · **Reasoning:** yes
NVIDIA's 550B flagship — the most capable raw reasoner in the free tier, with a genuine 1M
context. **Caveat:** served by a single provider (DeepInfra), so it has no internal failover
and is more 429-prone than the multi-provider models. Kept as a **flagship-reasoning and
large-context fallback only** — reach for it when you need maximum free-tier capability and
can tolerate the occasional retry. Never make it a primary daily driver.
**Best for:** Hardest free-tier reasoning · large-context fallback · when capability > reliability
**Chain:** reasoning fallback (`ccg → ccu`) · large-context fallback (`cca → cck → ccu`)

#### Builder / Auto-Router (`ccb` — 9router combo)
9router's multi-model orchestrator; auto-selects a free model per task. Less predictable than
explicit selection but useful for "figure it out" agentic pipelines.
**Best for:** Agentic pipelines · MCP workflows · when unsure which free model fits

---

## Part 4 — 429 Fallback Chains (the resilience core)

When a free model returns a 429, **do not wait** — relaunch the same task on the next alias in
its role chain. Antigravity / Claude Code always has a backup this way.

| Role | Primary | Fallback 1 | Fallback 2 | Notes |
|---|---|---|---|---|
| **UI / frontend** | `cck` Qwen3-Coder | `ccz` GLM-4.5-Air | `ccm` Gemma-4-31B | all strong on TS/Tailwind |
| **General coding** | `cc` Laguna M.1 | `ccg` GPT-OSS-120B | `ccx` Qwen3-Next-80B | ccg = safest |
| **Reasoning** | `ccg` GPT-OSS-120B | `ccu` Nemotron 550B ⚠ | `ccx` Qwen3-Next-80B | ccu = max capability |
| **Large context (1M)** | `cca` Nemotron Super | `cck` Qwen3-Coder | `ccu` Nemotron 550B ⚠ | all genuine 1M |
| **Quick / trivial** | `cch` Laguna XS.2 | `ccz` GLM-4.5-Air | — | speed first |
| **Agentic / tools** | `ccg` GPT-OSS-120B | `ccx` Qwen3-Next-80B | `cc` Laguna M.1 | ccg = best tool-use |

**Universal rule:** `ccg` (GPT-OSS-120B, 19 providers) is the safest free model in the roster —
when in doubt, or when everything else 429s, fall back to `ccg`.

---

## Part 5 — Routing Decision Tree

```
Is this AGENTIC (filesystem ops, multi-step, production deploy)?
  → ⚡ NATIVE — Sonnet (ccs) stays in control, may delegate sub-tasks

Is this ARCHITECTURE / SYSTEM DESIGN / ADR?
  → ⚡ NATIVE — Opus (cco)

Is this PRODUCTION CODE — security, auth, payments, SEBI, hotfix?
  → ⚡ NATIVE — Sonnet (ccs)

Is this UI/FRONTEND — React, Tailwind, Framer Motion, layout?
  → 🟢 FREE — Qwen3-Coder (cck)      fallback: ccz → ccm

Is this REASONING / AGENTIC / TOOL-USE (free tier)?
  → 🟢 FREE — GPT-OSS-120B (ccg)     fallback: ccu/ccx

Is this LARGE CONTEXT — full codebase, audit, >50k tokens?
  → 🟢 FREE — Nemotron Super (cca)   fallback: cck → ccu  (all 1M)

Is this a QUICK EDIT — rename, one-liner, scratchpad update?
  → 🟢 FREE — Laguna XS.2 (cch)      fallback: ccz

Is this GENERAL CODING — backend logic, algorithm, API, tests?
  → 🟢 FREE — Laguna M.1 (cc)        fallback: ccg → ccx

UNSURE / MIXED?
  → Start with GPT-OSS-120B (ccg) — safest free. Escalate to Sonnet if quality insufficient.

ANY free model returns 429?
  → Jump to its fallback chain (Part 4). When all else fails → ccg.
```

---

## Part 6 — Multi-Model Collaboration Protocol

The core of RoutingMagic: instead of just recommending a model for the whole session, Sonnet
(the orchestrator) identifies sub-tasks that can be delegated to free models running in parallel
terminals. The free model does its work, writes output to a shared file, and Sonnet picks it up.

### 6.1 — When to Delegate
Delegate to a free model when the sub-task is **self-contained**, **parallel**, matches a free
model's specialty, and is **non-security-critical**.
Keep in Sonnet when the task needs **tool use**, goes **directly to production**, involves
**auth/security/SEBI**, or requires **integrating** multiple sources.

### 6.2 — Delegation Handoff Format
When delegating, output EXACTLY this structure. The prompt inside the box must be complete and
self-contained — the user pastes it verbatim into the target alias terminal.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔀 DELEGATE → <MODEL NAME> — launch with: <alias>   (429? fallback: <next alias>)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Why this model: <one line>
I'll wait for you to say "done" before continuing.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 COPY EVERYTHING BELOW THIS LINE AND PASTE INTO <alias> TERMINAL:
┌─────────────────────────────────────────────────────
│ <Complete self-contained prompt. Must include:
│   1. Role: "You are working on the <project>..."
│   2. Context: exact file paths, current state, relevant snippets
│   3. Task: precisely what to produce
│   4. Output: exactly what to write and where
│      e.g. "Append to scratchpad.md under ## <Model> — <Task> — <Date>"
│   5. Constraint: "Do not modify any other files."
│ End with: "When done, write COMPLETE as your final line." >
└─────────────────────────────────────────────────────
```

**Rules:** the free model has NO memory of your conversation — give it everything inline,
including code snippets. Specify the output file path and section heading. One task, one
deliverable, one output location. If the named alias 429s, tell the user the fallback alias.

### 6.3 — Output Targets

| Target | Section format | Use when |
|---|---|---|
| `scratchpad.md` | `## <Model> — <Task> — <Date>` | Analysis, proposals, research |
| `memory.md` | `## <Rule Title>` + 2-3 lines | Decisions, rules, patterns |
| `progress.md` | `## <Phase/Feature>` + status + files | Completed-work summaries |
| new `tmp_*` file | full file content | UI components, large code output |

Never apply free-model code output to production paths without Sonnet reading and approving it.

### 6.4 — How Sonnet Picks Up Results

After the user says "done":
1. Sonnet reads the output file specified in the prompt.
2. Validates: does it match what was requested? Is it complete?
3. For code output: reviews for correctness and security before writing to the real path.
4. Continues the main task using the result as context.

Never apply free-model code output to production paths without Sonnet reading and approving it first.

### 6.5 — Worked Example (Investogram: mobile nav)

This is what a real delegation block looks like — the exact output Sonnet produces.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔀 DELEGATE → Qwen3-Coder — launch with: cck   (429? fallback: ccz → ccm)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Why this model: Tailwind + React mobile nav is Qwen3-Coder's specialty.
I'll wait for you to say "done" before continuing.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 COPY EVERYTHING BELOW THIS LINE AND PASTE INTO cck TERMINAL:
┌─────────────────────────────────────────────────────
You are working on the Investogram project — a Neo-Luxury dark-theme
financial dashboard built with Next.js 14 App Router + Tailwind CSS +
Framer Motion.

Design system:
  Background: #0B0C10  |  Surfaces: #1F2833  |  Text: #F4F5F7
  Gold accent: #C5A059  |  Error: #801B2B
  No borders unless necessary. No bright colours. No rounded-xl overkill.

Current problem:
  The top navigation at frontend/src/components/TopNav.tsx hides all nav
  links (SCREENER, PORTFOLIO, CARDS, FUNDS, IPO, SETTINGS) below 640px
  with no hamburger menu replacement. Mobile users are stuck.

Current nav links array (approximate):
  ['SCREENER /screener', 'PORTFOLIO /portfolio', 'CARDS /cards',
   'FUNDS /funds', 'IPO /ipo', 'SETTINGS /settings']

Task:
  Write a complete replacement <MobileMenu /> React component in TypeScript
  that:
  1. Shows a hamburger icon (3 lines, gold #C5A059) in the top-right at <640px
  2. Tapping it opens a full-screen overlay (bg #0B0C10, 95% opacity)
  3. Nav links listed vertically, uppercase, letter-spaced, gold on hover
  4. Close button (X) top-right of overlay
  5. Uses Framer Motion for open/close animation (slide down, 200ms)
  6. Works with Next.js <Link> for SPA navigation (no window.location.href)
  7. Closes automatically when a link is clicked

Output:
  Write the complete component to the file: tmp_outskill
  Use this exact format — first line must be the file path comment:
  // tmp_outskill — MobileMenu component for Investogram TopNav

Do not modify any other files.
When done, write COMPLETE as your final line.
└─────────────────────────────────────────────────────
```

---

## Part 7 — Project Routing Table (adapt per project)

*(Example: the Investogram project — Neo-Luxury dark-theme financial dashboard.)*

| Task Type | Route To | Alias | 429 fallback |
|---|---|---|---|
| Mobile nav / new UI component | Qwen3-Coder | `cck` | `ccz` → `ccm` |
| Implement `/api/*` backend | Laguna M.1 | `cc` | `ccg` → `ccx` |
| Auth middleware / RLS policy | Sonnet | `ccs` | never delegate |
| Full codebase audit | Nemotron Super | `cca` | `cck` → `ccu` |
| Heavy reasoning / algorithm | GPT-OSS-120B | `ccg` | `ccu` → `ccx` |
| Agentic pipeline / MCP / tools | GPT-OSS-120B | `ccg` | `ccx` → `cc` |
| Update scratchpad / memory | Laguna XS.2 | `cch` | `ccz` |
| Phase planning / ADR | Opus | `cco` | native only |
| Security review | Sonnet + Opus | `ccs`/`cco` | never delegate |
| Python math engine logic | Laguna M.1 | `cc` | `ccg` |
| Quick rename / one-liner | Laguna XS.2 | `cch` | `ccz` |

---

## Part 8 — Quick Alias Reference

```bash
# FREE models (9router must be running)
cc    → Laguna M.1            general coding (default)   262k
cch   → Laguna XS.2           quick edits / one-liners   262k
cca   → Nemotron 3 Super      large context              1M
cck   → Qwen3-Coder           UI / frontend / coder      1M   (7 providers)
ccg   → GPT-OSS-120B          reasoning + tools  131k  (19 providers) ★safest
ccx   → Qwen3-Next-80B        general / agentic          262k (6 providers)
ccz   → GLM-4.5-Air           fast all-rounder           131k (4 providers)
ccm   → Gemma-4-31B           resilient general          262k (11 providers)
ccu   → Nemotron 3 Ultra 550B flagship reasoning  1M  ⚠ single provider
ccb   → Builder               auto multi-model

# NATIVE Claude (direct to Anthropic)
ccs   → Sonnet 4.6   production, agentic, tools
cco   → Opus 4.8     architecture, hardest reasoning
ccq   → Haiku 4.5    fastest native

# Smart routing + cheatsheet
cc-route "task description"   # auto-pick + launch
cc-models                     # print cheatsheet + fallback chains

# Check 9router status
nc -z 127.0.0.1 20128 && echo "9router UP" || echo "9router DOWN"
```

---

## Part 9 — Standard Routing Announcement

```
⚡ RoutingMagic

  Task    : <one-line task summary>
  Tier    : ⚡ NATIVE — <model>   OR   🟢 FREE — <model>
  Why     : <1-3 signal words that matched>
  429?    : fallback → <next alias in chain>

  ─────────────────────────────────────────────────────────
  NATIVE → /model (picker) or: ccs / cco / ccq
  FREE   → open parallel terminal: cc / cch / cca / cck / ccg / ccx / ccz / ccm / ccu / ccb
  ─────────────────────────────────────────────────────────
  9router up?  nc -z 127.0.0.1 20128 && echo up || echo down
```

When delegating a sub-task, follow the format in Part 6.2.

---

## Part 10 — Cost Philosophy

| Tier | Cost | Target usage |
|---|---|---|
| Free (9router) | $0 | ~85% of daily work — coding, UI, reads, exploration |
| Native Sonnet 4.6 | Subscription | ~14% — production, agentic, security, integration |
| Native Opus 4.8 | Subscription | ~1% — architecture sessions only (rare, high-value) |

**Escalation:** start free → escalate to Sonnet if quality/tools insufficient → Opus only for
strategic architecture. **Never** use Opus for what Sonnet can do, or Sonnet for what a free
model can do. **Never** put free-model output into production without Sonnet review.
