# Project Memory: RoutingMagic

## Tech Stack & Core Decisions
- **Environment:** macOS, Zsh, Python 3
- **Core Architecture:** A dual-layer CLI tool comprising `aliases.zsh` for fast shell routing and `openai_wrapper.py` for dynamic LLM interactions.
- **Model Ecosystem:** Supports NVIDIA NIM (GLM-5.1, Nemotron, DeepSeek), OpenAI, and OpenRouter for free/paid fallbacks.
- **Save Handler (`save_handler.py`):** An automated documentation updater that reads git diffs and uses an LLM to automatically maintain this exact set of 4 files (memory, progress, scratchpad, lessons).
- **Agent Skills:** Added `.agents/skills` directory containing reusable skills (e.g., systematic-debugging) to enhance the AI agent's ability to develop and maintain the project.

## Durable Rules & Constraints
- **Global Availability:** `ask`, `chat`, and `save` are global zsh aliases so they can be run from any project directory.
- **Token Limits (Free Models):** Prioritize free models (NVIDIA -> OpenRouter). Strict tracking of RPM (~40 limit) and RPD (50 limit) to avoid 429 Too Many Requests errors.
- **Failsafe System:** `/safe` and `/restore` commands rely natively on local `git` snapshots to provide instant undo capabilities.
- **Error Interception:** Proactive codebase scanning is disabled for performance. Error interception works reactively via `stderr` capture when a command fails.
