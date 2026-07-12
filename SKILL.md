---
name: routing-magic
description: "An intelligent, zero-cost CLI routing engine that seamlessly categorizes and distributes LLM prompts across NVIDIA NIM, OpenRouter, and OpenAI based on task complexity and reasoning requirements."
---

# RoutingMagic Skill

This skill allows Antigravity agents (and humans) to instantly access a globally installed, heavily optimized CLI router for zero-cost execution of LLM prompts. By bypassing heavy agentic context payloads, the router saves tens of thousands of tokens per prompt, relying on a keyword-based heuristic to assign tasks to the perfect model from the NVIDIA NIM catalog or OpenRouter.

## Usage Instructions

This skill has configured the host's terminal with the `ask` alias. When the user asks you to trigger the magic router or run a zero-cost fallback, you must invoke the router using a shell command.

### How to execute the router:

You can pass any prompt string to the `ask` alias. The routing engine will automatically:
1. Parse the prompt.
2. Select the optimal model.
3. Stream the output.

**Example Command:**
```bash
zsh -c 'source ~/RoutingMagic/aliases.zsh && ask "Write a Python script to calculate Fibonacci sequence"'
```

### Routing Logic (For your awareness):
- **Deep Reasoning**: Prompts containing words like `reason deeply, architecture, strategy, plan` are routed to **Nemotron-3-Ultra-550B**.
- **Fast Coding**: Prompts containing `code, fix bug, refactor, regex, sql` are routed to **DeepSeek-V4-Flash**.
- **Agentic Workflows**: Prompts containing `large repo, multi-step coding` are routed to **Kimi-k2.6**.
- **Safety / Policy**: Prompts containing `moderation, unsafe content` are routed to **Nemotron-3.5-Content-Safety**.
- **General Chat**: Anything else is routed to **GLM-5.1**.

### Mythos-Inspired Features (v2):

**Adaptive Computation Time (ACT):**
- Dynamically selects reasoning effort: low/medium/high
- High-effort tasks get reasoning models with hidden thinking

**Reasoning Tokens (Latent-Space Thinking):**
- Models with reasoning support enable hidden multi-step thinking
- Internal only — no user-facing aliases

**MoE-Style Expert Selection (Council):**
- Task-specific model selection based on domain
- High-effort tasks prefer models with reasoning support

**Multi-Pass Prompting:**
- High-effort tasks receive structured reasoning templates
- Three-pass approach: analyze → verify → finalize

### Agent Guidelines:
- If you find yourself rate-limited or out of tokens on a major model, use the `ask` alias as a fallback to continue zero-cost troubleshooting.
- The `ask` alias automatically loads API keys from `~/.routingmagic/.env` (user setup) and `~/global.env` (legacy). You do not need to supply keys.
- If keys are missing, the tool prints setup instructions. Run: `python3 ~/Projects/RoutingMagic/setup_keys.py`
- Do not attempt to pipe multi-line files directly into `ask` without formatting; keep the prompt string enclosed in double quotes.
- Deep reasoning is handled internally by ACT effort selection — no special aliases needed.
