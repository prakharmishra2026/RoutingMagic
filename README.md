# RoutingMagic 🪄

**Your AI coding assistant, right in the terminal.**

No more copy-pasting code into browser tabs. RoutingMagic sits in your project directory, understands your codebase, and routes your questions to the best free AI model automatically.

---

## Quick Start (30 seconds)

```bash
# 1. Clone and install
git clone https://github.com/prakharmishra2026/RoutingMagic.git ~/Projects/RoutingMagic
cd ~/Projects/RoutingMagic
chmod +x install.sh && ./install.sh

# 2. Set up your API key (free)
python3 setup_keys.py

# 3. Start using it
ask "What does this project do?"
```

That's it. You only need one free [OpenRouter](https://openrouter.ai/keys) key.

---

## The 4 Commands

| Command | What it does |
|---------|-------------|
| `ask "question"` | Quick answer using best free model for your task |
| `ask deep "question"` | Same, but reads your project files for context |
| `ask MC "question"` | **Model Council** — 3 AI models debate your question |
| `ask deep MC "question"` | Council + full project context |

All MC variants work case-insensitively: `ask mc`, `ask MC`, `ask Mc`, `ask mC` all work.

### REPL mode (conversations)

Just type `ask` (or any of the above without a question) to enter interactive mode:
```
>>> What does this function do?
>>> /savings          # see your token savings
>>> /council refactor this   # trigger Model Council
>>> exit
```

### Slash commands (inside REPL)

| Command | What it does |
|---------|-------------|
| `/council <prompt>` | 3-model deliberation |
| `/mc <prompt>` | Shortcut for council |
| `/savings` | Show token savings dashboard |
| `/savings breakdown` | Breakdown by component |
| `/savings models` | Model efficiency ranking |
| `/savings export` | Export as CSV |
| `/cost` | Session cost and rate limits |
| `/model` | Switch active model |
| `/safe` | Git snapshot (undo point) |
| `/restore` | Undo to last `/safe` |
| `/run <command>` | Run a command; if it fails, AI fixes it |
| `/test <command>` | Run tests; if they fail, AI fixes them |
| `/clear` | Clear conversation history |
| `/paste` | Paste clipboard images for analysis |
| `/caveman-feedback <good\|terse\|...>` | Report compression quality |

### One-shot mode (single answers)

```
ask "Explain this error"
ask deep "Are there security issues?"
ask MC "Should we use Postgres or SQLite?"
ask MC deep "Design the auth system"
```

---

## 📋 Effortless Copy-Paste (`--paste` / `/paste`) — No Terminal Paste Errors!

Pasting large, multi-line Markdown files, plans, or code directly into a terminal prompt often causes confusing shell errors (like `zsh: command not found`).

With RoutingMagic, **you never paste into the terminal screen at all.** Instead, you use the `--paste` flag, which tells RoutingMagic to grab whatever is currently copied to your Mac clipboard.

### How it works (Step-by-Step Example)

#### Step 1: Copy any text or document (`Cmd + C`)
Highlight your Markdown plan, code snippet, or error log in any editor or browser and press **`Cmd + C`** to copy it.

#### Step 2: Type `--paste` in your terminal
Do **not** press `Cmd + V` in your terminal. Instead, literally type `--paste` after your command:

```bash
# Literally type this exact command and press Enter:
ask MC --paste
```

RoutingMagic automatically reads the copied text straight from your clipboard:
```text
[Clipboard] Loaded 4,812 characters (142 lines) of text from clipboard.
[LLM Council] Starting deliberation...
```

---

### Adding Instructions to Your Copied Text
Want the Model Council to review or audit the document you just copied? Just add your question in quotes after `--paste`:

```bash
# 1. Copy your plan/doc with Cmd + C
# 2. Run:
ask MC --paste "Audit this implementation plan and list 3 weaknesses"

# Or with normal ask / deep context:
ask --paste "Summarize this text"
ask deep --paste "Find bugs in this code snippet"
```

### Inside Interactive Mode (`>>>`)
If you are already inside an interactive chat session (`>>>`), simply type `/paste`:
```text
>>> /paste
[Clipboard] Loaded 4,812 characters (142 lines) of text from clipboard.
```
*(Note: `/paste` works automatically for **both Text and Images** copied to your macOS clipboard!)*

---

## 🪨 Caveman Compression (Token Savings)

RoutingMagic compresses AI responses automatically to save tokens and money — while **never** breaking code, error messages, or file paths.

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

## 🔄 Self-Improving System

RoutingMagic gets better the more you use it:

- **Model registry**: Auto-fetches latest free models from OpenRouter every week
- **Routing learner**: Tracks which models work best for your tasks
- **Quality loop**: Detects when compression is too aggressive and adjusts
- **Lesson persistence**: Records what works and what doesn't

---

## 🔐 Universal Multi-Provider Free Models & Secure Key Setup

RoutingMagic is **never locked into a single provider**. It dynamically pools and refreshes free models across **OpenRouter**, **Google Gemini**, **Z.ai (Zhipu AI)**, **NVIDIA NIM**, **DeepSeek**, and **OpenAI** so you always get the fastest, highest-quality free models available.

### Step-by-Step Interactive Key Setup
Run the interactive setup script in your terminal:
```bash
python3 ~/Projects/RoutingMagic/setup_keys.py
```

The wizard guides you through 5 optional/recommended API keys:
1. **OpenRouter API Key (`OPENROUTER_API_KEY`)** — Recommended hub for dynamic `:free` models (including DeepSeek-R1 & V3 free pools) & Model Council. Get free key at [openrouter.ai/keys](https://openrouter.ai/keys).
2. **Google Gemini API Key (`GEMINI_API_KEY`)** — Direct access to Google's fast free tier (`Gemini 2.5 Flash`, `Gemini 2.0 Flash`). Get free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
3. **Z.ai / Zhipu AI API Key (`ZAI_API_KEY`)** — Direct access to Zhipu AI's **permanent free tier** (`GLM-4.7-Flash`, `GLM-4.5-Flash`). Get free key at [open.bigmodel.cn](https://open.bigmodel.cn).
4. **NVIDIA NIM API Key (`NVAPI_KEY`)** — Direct access to NVIDIA's free tier (`Nemotron Ultra 120B`, `Llama 3.3 70B`). Get free key at [build.nvidia.com](https://build.nvidia.com/nim/dashboard).
5. **OpenAI API Key (`OPENAI_API_KEY`)** — Direct access to `GPT-5`, `o3-mini`, `GPT-4o-mini`. *(DeepSeek direct API key `DEEPSEEK_API_KEY` is also supported automatically)*.

```text
✓ Keys saved securely to ~/.routingmagic/.env
  File permissions: 600 (owner read/write only)
  Keys are NOT in any git repo or shared location.
```

### 🌐 Multi-Provider Free Model Pooling & Auto-Refresh
* **Zero Provider Lock-In:** If OpenRouter rate-limits a model or returns a `404`, RoutingMagic automatically fails over to your direct **Google Gemini**, **Z.ai (`GLM-4.5-Flash`)**, or **NVIDIA NIM** free models in milliseconds.
* **Timely Auto-Refresh:** RoutingMagic automatically fetches and updates live model registries on a weekly schedule (`[ModelRegistry] Weekly update needed...`) so your Model Council always utilizes the latest working free models across all supported providers.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "No API keys found" | Run `python3 ~/Projects/RoutingMagic/setup_keys.py` |
| "OpenRouter key not found" | Get a free key at https://openrouter.ai/keys |
| Council not working | Council requires OpenRouter key |
| Output too terse | Type `/caveman-feedback too terse` to lower compression |
| Want more savings | Install Caveman skill: `npx skills@latest add JuliusBrussee/skills/caveman` |

---

## Power User Aliases

Direct model access (bypasses smart routing):

| Alias | Model |
|-------|-------|
| `cc` | Qwen3-Coder (best free code) |
| `ccc` | Model Council |
| `ccg` | Gemma-4-31B (best free general) |
| `ccm` | Nemotron Super 120B (reasoning) |
| `ccu` | Nemotron Ultra 550B (flagship) |

---

## Why RoutingMagic?

- **Zero cost**: All models are free via OpenRouter
- **Automatic fallback**: If one model fails, the next one takes over
- **Context-aware**: Reads your project files for relevant context
- **Token-efficient**: Caveman compression saves 65% on output
- **Self-improving**: Learns from your usage patterns
- **Your keys, your control**: No shared API keys, no cloud dependency
