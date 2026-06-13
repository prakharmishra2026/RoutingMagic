# Project Lessons: RoutingMagic

## Gotchas & Pitfalls
- **Token Bleed in Background Tasks:** Proactively scanning codebase context every time the REPL starts is too expensive. We shifted to a reactive approach where `stderr` logs are captured *only* when an error is thrown, and we prioritize reading localized `.md` files for deep context.
- **Upstream Rate Limiting:** Free models (like OpenRouter's Kimi or NVIDIA's NIMs) can arbitrarily rate limit. Hardcoding a single model crashes the tool. Implementing a dynamic multi-model fallback chain (Free A -> Free B -> Paid) is essential for CLI robustness.

## Best Practices
- Keep `.zshrc` aliases decoupled from Python logic so the terminal commands `ask`, `chat`, and `save` inject cleanly into any workspace.
- Rely on local `git reset --hard` for the `undo/restore` functionality rather than trying to track specific LLM file modifications manually.
- **Systematic Debugging:** Implementing a structured debugging process (like the systematic-debugging skill) helps prevent shortcuts and ensures root cause resolution, reducing recurring issues.
}
