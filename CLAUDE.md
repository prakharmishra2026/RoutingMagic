# CLAUDE.md — RoutingMagic

## Token economy rules

1. Reply terse. Drop filler ("I'd be happy to", "Let me help you with", "Here's what I found"). Say the thing.
2. Code changes: show the diff, not a paragraph about the diff.
3. Errors: name error + fix. No stack trace unless asked.
4. One file at a time unless multi-file is unavoidable. Read neighbors for context, don't dump them.
5. Never re-read a file you just edited — cache it mentally.
6. Grep/glob first, read second. Don't read entire files to find one function.
7. Skip "here's a summary" postambles. The code IS the answer.
8. Comments in code: only if logic is non-obvious. No "imports os" style comments.
9. When editing, prefer `edit` over `read`+`write` — smaller context.
10. Compress CLAUDE.md, SKILL.md, README before each session if >500 lines.

## Project

RoutingMagic — zero-cost LLM router for terminal. Routes prompts to free models via
OpenRouter/NVIDIA NIM with fallback chains. Key features: smart_route heuristic,
Model Council (3-model deliberation), git snapshot failsafe, vision paste.

**v2 Mythos**: Enhanced with OpenMythos-inspired techniques:
- ACT (Adaptive Computation Time): Dynamic effort selection (low/medium/high)
- MoE-style routing: Task-specific expert selection
- Multi-pass prompting: Structured reasoning templates for complex tasks
- Reasoning tokens: Latent-space thinking via OpenRouter API

## Structure

- `openai_wrapper.py` — core: routing, REPL, council, vision, fallback chains, 9router auto-start
- `aliases.zsh` — 4-core-alias system (ask, ask deep, ask MC, ask deep MC), power-user cc* aliases
- `setup_keys.py` — interactive API key setup (stores in ~/.routingmagic/.env, 0600 perms)
- `caveman_integration.py` — Caveman compression pipeline (65% output savings, quality guardrails)
- `metrics_collector.py` — SQLite token metrics + savings dashboard (/savings commands)
- `caveman_quality_loop.py` — auto-downgrade on confusion, feedback collection, self-improving prompts
- `model_registry_updater.py` — weekly OpenRouter model fetch, free model filtering, changelog
- `routing_learner.py` — per-task success rate tracking, model quality DB, lesson generation
- `save_handler.py` — auto-updates project memory files after sessions
- `glm5.py` — direct NVIDIA GLM-5.1 fallback script
- `install.sh` — installer: zshrc + skill symlink + key setup

## API key flow

Keys live in `~/.routingmagic/.env`. Load order: that file → ~/global.env → env vars.
No hardcoded paths. Users own their keys.

## Build/test

No build step. Python 3.10+, `pip install openai python-dotenv`.
Tests in `tests/`: `python3 -m pytest tests/ -v`

## Mythos-Inspired Features

### Adaptive Computation Time (ACT)
```python
# Maps prompt complexity to reasoning effort
effort = select_reasoning_effort(prompt, task_type)
# Returns: "low" | "medium" | "high"
```

### Multi-pass Prompting
```python
# High-effort tasks get structured reasoning templates
if effort == "high":
    enhanced_prompt = get_multi_pass_prompt(prompt, task_type)
    # Templates: reasoning, coding, analysis
```

### Reasoning Tokens (Latent-space thinking)
```python
# Models with reasoning support
REASONING_MODELS = {
    "zhipu/glm-4.5-air": {"effort": True},
    "nvidia/nemotron-3-ultra-550b-a55b": {"effort": True},
    "openai/gpt-oss-120b": {"effort": True},
    "qwen/qwen3-coder:free": {"effort": True},
}
```

### MoE-style Expert Selection (Council)
- Task-specific model selection based on domain
- High-effort tasks prefer models with reasoning support
- Council members selected by: reasoning, coding, agentic, general
