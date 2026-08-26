# RoutingMagic 🪄

**Zero-cost AI routing for your terminal.** Routes prompts to the best free models across NVIDIA NIM (Tier 1), OpenRouter Free (Tier 2), and opencode Built-in (Tier 3) with automatic fallback chains, Model Council deliberation, token compression, and unified usage dashboard.

---

## Quick Start (30 seconds)

```bash
# 1. Clone and install
git clone https://github.com/prakharmishra2026/RoutingMagic.git ~/Projects/RoutingMagic
cd ~/Projects/RoutingMagic
chmod +x install.sh && ./install.sh

# 2. Add your API keys (auto-opens ~/.routingmagic/.env in your editor)
# The installer creates ~/.routingmagic/.env with placeholders — just fill them in

# 3. Start using it
ask "What does this project do?"
```

**That's it.** You only need one free key (NVIDIA NIM or OpenRouter).

---

## Model Priority (Zero-Cost)

| Tier | Source | Models | Rate Limit | Use Case |
|------|--------|--------|------------|----------|
| **1** | **NVIDIA NIM Direct** | 50+ | ~40 RPM | **Primary** — same models that cost $ on OpenRouter |
| **2** | **OpenRouter Free** | 20+ | Shared bucket | Fallback when NIM rate-limited |
| **3** | **opencode Built-in** | 2 | No key needed | Last resort |

### Tier 1: NVIDIA NIM (Recommended — No credit card)
- `deepseek-ai/deepseek-v4-flash` — **Coding**
- `z-ai/glm-5.2` — **Agent/Coding (1M context)**
- `nvidia/nemotron-3-ultra-550b-a55b` — **Flagship reasoning**
- `qwen/qwen3-coder-480b-a35b-instruct` — **Agentic coding (256K)**
- `minimaxai/minimax-m2.7` — **Financial modeling**
- `google/gemma-4-31b-it` — **General + vision**

### Tier 2: OpenRouter Free (When NIM rate-limited)
- `poolside/laguna-s-2.1:free` — Best free coding (70.2% Terminal-Bench)
- `nvidia/nemotron-3-ultra-550b-a55b:free`
- `z-ai/glm-5.2:free`
- `cohere/north-mini-code:free`

### Tier 3: opencode Built-in (No API key)
- `nemotron-3-ultra-free`
- `nemotron-3.5-lightning-free`

---

## The 4 Core Commands

| Command | What it does |
|---------|-------------|
| `ask "question"` | Quick answer using best free model for your task |
| `ask deep "question"` | Same, but reads your project files for context |
| `ask MC "question"` | **Model Council** — 3 AI models debate your question |
| `ask deep MC "question"` | Council + full project context |

All MC variants work case-insensitively: `ask mc`, `ask MC`, `ask Mc`, `ask mC` all work.

### REPL Mode (Conversations)

Just type `ask` (or any variant without a question) to enter interactive mode:
```
>>> What does this function do?
>>> /savings          # see your token savings
>>> /council refactor this   # trigger Model Council
>>> exit
```

### Slash Commands (Inside REPL)

| Command | What it does |
|---------|-------------|
| `/council <prompt>` | 3-model deliberation |
| `/mc <prompt>` | Shortcut for council |
| `/savings` | Show token savings dashboard |
| `/savings breakdown` | Breakdown by component |
| `/savings models` | Model efficiency ranking |
| `/savings export` | Export as CSV |
| `/dashboard` | Open unified usage dashboard (localhost:9898) |
| `/cost` | Session cost and rate limits |
| `/model` | Switch active model |
| `/safe` | Git snapshot (undo point) |
| `/restore` | Undo to last `/safe` |
| `/run <command>` | Run a command; if it fails, AI fixes it |
| `/test <command>` | Run tests; if they fail, AI fixes them |
| `/clear` | Clear conversation history |
| `/paste` | Paste clipboard images for analysis |
| `/caveman-feedback <good\|terse\|...>` | Report compression quality |

### One-Shot Mode (Single Answers)

```
ask "Explain this error"
ask deep "Are there security issues?"
ask MC "Should we use Postgres or SQLite?"
ask MC deep "Design the auth system"
```

---

## 📊 Unified Usage Dashboard

Track usage across **all your AI tools** in one place:

```bash
dashboard open      # Scan + open browser at localhost:9898
dashboard scan      # Scan all sources (Claude, OpenCode, Hermes, Codex, 9router, RoutingMagic)
dashboard stop      # Stop the dashboard server
```

Or from inside REPL: `/dashboard`

**Sources tracked:** Claude Code, OpenCode, Hermes, Codex CLI, 9router, RoutingMagic internal metrics

---

## 🪨 Caveman Compression (Token Savings)

Automatically compresses AI responses to save tokens — **never breaks code, errors, or file paths**.

| Level | Output Savings | Best For |
|-------|---------------|----------|
| `lite` | ~30% | Complex explanations, learning |
| `full` (default) | ~65% | Daily coding, debugging |
| `ultra` | ~75% | Quick lookups, known patterns |

**Quality guarantees:**
- ✅ Code blocks, inline code — never compressed
- ✅ Error messages, stack traces — preserved exactly
- ✅ File paths, URLs — always intact
- ✅ If you re-ask or say "what?" — compression auto-downgrades
- ✅ `/caveman-feedback too terse` to manually adjust

Type `/savings` in any session to see your token savings dashboard.

---

## 🧠 Model Council (3-Model Deliberation)

`ask MC "your question"` triggers **three diverse models** to debate your question:

- **Models selected from different providers** (NIM, OpenRouter, direct APIs)
- **Health-checked** — never picks degraded models
- **Synthesized answer** — best insights from all three

```bash
ask MC "Should we use Postgres or SQLite for this project?"
ask deep MC "Design the authentication system"
```

---

## ⚡ Power User Aliases

### NVIDIA NIM Direct (Tier 1 — Primary)
```bash
nd   # DeepSeek-V4-Flash (coding)
ng   # GLM-5.2 (agent/coding 1M ctx)
nm   # MiniMax-M2.7 (financial)
nk   # Qwen3-Coder-480B (agentic coding)
nl   # Nemotron-3-Ultra-550B (flagship reasoning)
nu   # Nemotron-3-Super-120B (agent/multi-step)
ngg  # Gemma-4-31B-IT (general + vision)
```

### OpenRouter Free (Tier 2 — Fallback)
```bash
cc   # Poolside Laguna S 2.1 (best free coding)
ccc  # Qwen3-Coder (UI/frontend/coder)
ccz  # GLM-5.2 (agent/coding)
ccg  # GPT-OSS-120B (reasoning + tools)
ccx  # Qwen3-Next-80B (general/agentic)
ccm  # Gemma-4-31B-IT (resilient general)
ccu  # Nemotron-3-Ultra-550B (flagship)
cca  # Nemotron-3-Super-120B (large context)
cch  # Laguna XS 2.1 (quick edits)
ccb  # Smart auto-route
```

### Direct Fast Free (Gemini, Z.ai)
```bash
ccgem  # Google Gemini 2.5 Flash (direct)
ccglm  # Z.ai GLM-4.5 Flash (direct)
```

### Native & OpenAI
```bash
ccs  # Claude Sonnet 4.6 (native)
cco  # Claude Opus 4.8 (native)
ccq  # Claude Haiku 4.5 (native)
op   # GPT-5 (OpenAI direct)
opt  # GPT-4-Turbo (OpenAI direct)
opo3 # o3-mini (OpenAI direct)
```

---

## 🔄 Daily Auto-Updates

**GitHub Action runs daily at 1 AM UTC** to fetch latest free models:

1. Fetches NVIDIA NIM models (using `NVAPI_KEY` secret)
2. Fetches OpenRouter free models (using `OPENROUTER_API_KEY` secret)
3. Merges with priority: NIM → OpenRouter → opencode
4. Runs health checks on all models
5. Commits updated `registry/` to repo

**To enable for your fork:**
1. Go to Settings → Secrets and variables → Actions
2. Add: `NVAPI_KEY` (from https://build.nvidia.com/nim/dashboard)
3. Add: `OPENROUTER_API_KEY` (from https://openrouter.ai/keys)

---

## 🔐 Secure Key Setup

On first install, `~/.routingmagic/.env` is **auto-created with placeholders** and **auto-opens in your editor**:

```bash
# TIER 1: NVIDIA NIM (Primary — get at build.nvidia.com/nim/dashboard)
NVAPI_KEY=nvapi-YOUR_KEY_HERE

# TIER 2: OpenRouter Free (Fallback — get at openrouter.ai/keys)
OPENROUTER_API_KEY=sk-or-v1-YOUR_KEY_HERE

# OPTIONAL: Direct providers
GEMINI_API_KEY=AIza-YOUR_KEY_HERE
ZAI_API_KEY=YOUR_KEY_HERE
OPENAI_API_KEY=sk-YOUR_KEY_HERE
```

**File permissions:** 600 (owner read/write only) — never in git.

### Get Your Keys

| Provider | Free Tier | Get Key |
|----------|-----------|---------|
| **NVIDIA NIM** | 50+ models, 40 RPM | https://build.nvidia.com/nim/dashboard |
| **OpenRouter** | 20+ free models | https://openrouter.ai/keys |
| **Google Gemini** | Flash models | https://aistudio.google.com/apikey |
| **Z.ai / Zhipu** | GLM-4.5-Flash permanent | https://open.bigmodel.cn |
| **OpenAI** | GPT-5, o3-mini | https://platform.openai.com/api-keys |

---

## 🛠️ Advanced Features

### Vision Paste
Copy an image/screenshot (`Cmd+C`), then:
```bash
ask "Analyze this chart" --paste
```

### Git Snapshot Failsafe
```bash
/safe        # Creates git snapshot before risky operations
/restore     # Undo to last /safe
```

### Run/Test Auto-Fix
```bash
/run pytest tests/        # If fails, AI fixes and retries
/test npm test            # Same for tests
```

### Smart Routing (MoE-Style)
Automatically selects best model for task type:
- **Coding** → Qwen3-Coder / DeepSeek-V4-Flash
- **Reasoning** → Nemotron Ultra / GPT-OSS-120B
- **Long Context** → Nemotron 3 Super 120B (1M)
- **Financial** → MiniMax-M2.7
- **General** → Gemma 4 31B

---

## 🔄 Self-Improving System

- **Daily model registry updates** via GitHub Action
- **Routing learner** tracks which models work best for your tasks
- **Quality loop** detects when compression is too aggressive
- **Lesson persistence** records what works and what doesn't

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "No API keys found" | Run `python3 ~/Projects/RoutingMagic/setup_keys.py` |
| "OpenRouter key not found" | Get free key at https://openrouter.ai/keys |
| Council not working | Council requires OpenRouter or NIM key |
| Output too terse | Type `/caveman-feedback too terse` |
| Model failed | Auto-fallback to next in chain (never blocks) |

---

## Why RoutingMagic?

- **Zero cost**: All models free via NVIDIA NIM + OpenRouter
- **Automatic fallback**: Never blocks — chains through 37+ models
- **Context-aware**: Reads project files for relevant context
- **Token-efficient**: Caveman compression saves 65% on output
- **Self-improving**: Daily model updates, learns from usage
- **Your keys, your control**: Local `.env`, 600 perms, no cloud dependency
- **Unified dashboard**: Track all AI tools (Claude, OpenCode, Codex, etc.) in one view

---

## License

MIT — Use freely, modify, distribute.