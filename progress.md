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

## Backlog / Next Steps
- [ ] Push latest changes to GitHub repository.
- [ ] Test the `! <cmd>` error interception in a real node/python project.
- [ ] Monitor rate-limit hits for OpenRouter free models to ensure the fallback chain shifts smoothly.
