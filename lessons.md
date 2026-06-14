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
- **Live Model Refresh:** Statically defined model lists rot immediately (e.g., `deepseek-r1:free` vanished from OpenRouter). Live querying from the OpenRouter model registry `/api/v1/models` is necessary to prevent outages and auto-discover new cost-optimal free models.
- **Deterministic Floor/Safety Gates:** Never trust an LLM "Judge" or "Committee" to enforce final safety limits (e.g. margin of safety, leverage limits). During tests, the LLM Judge correctly computed breaches but still output a `BUY` recommendation. Safety must be enforced by a hardcoded Python gate that can downgrade but never upgrade a verdict.
- **Latency vs. Reasoning:** Reasoning models introduce significant latency (~32s p95). Non-reasoning models must be utilized for time-sensitive interactive flows, reserving reasoning models only for asynchronous advisory audits and explanations.
- **Latency Mitigation in Multi-Agent Deliberation:** Running multiple LLM calls sequentially in a multi-stage deliberation protocol (e.g. LLM Council) multiplies latency. Implementing concurrent calls using Python's `ThreadPoolExecutor` ensures that Stage 1 (opinions) and Stage 2 (reviews) are executed in parallel, bounding total stage latency by the slowest single API call instead of the sum of all calls.
- **Dynamic Model Selection and Freshness Sorting:** Hardcoding specific reasoning models (like `deepseek/deepseek-r1`) introduces model rot because the model landscape changes rapidly. Instead, dynamically query OpenRouter's `/api/v1/models` and filter candidates based on required capabilities (e.g., `"reasoning"` parameter support). By sorting candidates by their creation timestamp (`created` parameter) in descending order, the system automatically routes tasks to the latest and most capable reasoning models (such as `qwen/qwen3-max-thinking` or `openai/o3-mini`) rather than stale, outdated models.

