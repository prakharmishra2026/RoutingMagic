# Project Progress: RoutingMagic

## Chronological Log
 - **Phase 1:** Built foundational REPL, `openai_wrapper.py`, and smart routing logic for NVIDIA/OpenAI models.
 - **Phase 2:** Defined Zsh aliases to inject commands globally across all system projects.
 - **Phase 3:** Converted to an advanced IDE-like Terminal Protocol with auto-commit failsafes, cost/rate-limit tracking, model fallback chains, workspace context isolation, and smart `stderr` error interception.
 - **Phase 4:** Built `save_handler.py` to automate maintaining project state via Git diff analysis and LLM summarization.
 - **2025-10-03:** Added systematic-debugging skill to agent's toolkit (.agents/skills/systematic-debugging) to improve root cause analysis during development. This includes CREATION-LOG.md and SKILL.md files.
 - **2025-10-04:**
   * Fixed REPL: added support for bracketed paste mode and prevented terminal deadlocks on macOS (fc9226c).
   * Improved paste collector with rolling-window (200ms) and used shlex.split for shell=False safety (f2e9b5d).
   * Fixed socket leak in is_port_open and sanitize_cmd regex false-positives in systematic-debugging skill (085b24e).
   * Injected Charlie Munger mental models (inversion, first principles) into system prompt for highly rigorous output (6b2fd49).
 - **2025-10-05:**
   * Fixed REPL: added support for hybrid typed+pasted prompts in bracketed paste mode (baba84b).
   * Updated project progress and lessons-learned (f216a10).
   * Saved full progress for phases 5-8, including all 11 bugs, lessons, and systematic-debugging skill (8f32634).
 - **2025-10-06:**
   * Fixed REPL: use non-canonical cbreak mode to prevent terminal freezes on large pastes (562640b)
   * Docs: save progress for hybrid paste fix (cc46ada)
 - **2025-10-07:**
   * Fixed router: replaced vanished deepseek-r1:free with nemotron-3-super and documented learnings from live routing experiment (0a2bf46)
 - **2026-06-14:**
   * Implemented Karpathy-style LLM Council deliberation protocol in `openai_wrapper.py` supporting Stage 1 (opinions), Stage 2 (reviews), and Stage 3 (synthesis).
   * Integrated council deliberation via `ask council "prompt"` keyword and `/council <prompt>` REPL command.
   * Added unit tests for `run_council` and council routing in `test_routing_magic.py`.
   * Updated `README.md` and `lessons.md` to document the council feature and parallel execution latency mitigation.
 - **2026-06-15:**
   * Fixed paste auto-submission, handled empty choices NoneType error, added backup free fallback pool, and implemented in-place reasoning display (dde51fa).
 - **2026-06-16:**
   * Added chpwd directory hook to auto-place `save_handler.py` at repository roots when changing directories (7acf324).
   * Updated README.md with documentation for multi-step pastes and in-place reasoning features (f46b443).
   * Enhanced the LLM Council to use a dynamic 3-model configuration and added REPL aliases (`/council`, `/MC`, `/mc`) and global shell aliases for quick access (ba9f050).

## Backlog / Next Steps
 - [x] Implement LLM Council multi-agent deliberation.
 - [ ] Test the `! <cmd>` error interception in a real node/python project.
 - [ ] Monitor rate-limit hits for OpenRouter free models to ensure the fallback chain shifts smoothly.
