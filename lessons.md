# Project Lessons: RoutingMagic

## Gotchas & Pitfalls
- **Token Bleed in Background Tasks:** Proactively scanning codebase context every time the REPL starts is too expensive. We shifted to a reactive approach where `stderr` logs are captured *only* when an error is thrown, and we prioritize reading localized `.md` files for deep context.
- **Upstream Rate Limiting:** Free models (like OpenRouter's Kimi or NVIDIA's NIMs) can arbitrarily rate limit. Hardcoding a single model crashes the tool. Implementing a dynamic multi-model fallback chain (Free A -> Free B -> Paid) is essential for CLI robustness.
- **Resource Leaks in Utility Functions:** Utility functions like `is_port_open` must ensure resources (like sockets) are properly closed, even in error cases, to avoid file descriptor leaks.
- **Regex False Positives:** Regular expressions used for input sanitization must be rigorously tested to avoid false positives that can break functionality.
- **Terminal Deadlocks in Bracketed Paste Mode:** Failing to properly handle bracketed paste mode can lead to terminal deadlocks, particularly on macOS. Solution: Use a non-blocking input collector with a timeout (e.g., rolling window) and ensure the terminal is restored to its original state after pasting.

## Best Practices
- Keep `.zshrc` aliases decoupled from Python logic so the terminal commands `ask`, `chat`, and `save` inject cleanly into any workspace.
- Rely on local `git reset --hard` for the `undo/restore` functionality rather than trying to track specific LLM file modifications manually.
- **Systematic Debugging:** Implementing a structured debugging process (like the systematic-debugging skill) helps prevent shortcuts and ensures root cause resolution, reducing recurring issues.
