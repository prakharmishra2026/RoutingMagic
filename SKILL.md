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

### Agent Guidelines:
- If you find yourself rate-limited or out of tokens on a major model, use the `ask` alias as a fallback to continue zero-cost troubleshooting.
- The `ask` alias automatically accesses all necessary API keys via the user's `~/.env` and `~/global.env`. You do not need to supply keys.
- Do not attempt to pipe multi-line files directly into `ask` without formatting; keep the prompt string enclosed in double quotes.
