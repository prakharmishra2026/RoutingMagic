---
name: routingmagic-self-improvement
description: "Self-improving architectural invariants, multi-provider failover rules, quorum timeout safety, and non-coder UX guidelines for maintaining and expanding RoutingMagic."
---

# RoutingMagic Self-Improvement & Engineering Invariants

When modifying, auditing, or extending the `RoutingMagic` codebase (`openai_wrapper.py`, `setup_keys.py`, `aliases.zsh`), agents MUST follow these learned self-improvement guardrails:

## 1. Direct Multi-Provider Architecture (No Local Proxy Daemons)
- **Direct Native APIs**: All requests must connect directly to official provider endpoints (`https://openrouter.ai/api/v1`, Google Gemini, Z.ai, NVIDIA NIM, OpenAI).
- **No Background Proxy Daemons**: Never reintroduce `9router`, port `20128` forwarding, or any local proxy server.
- **Provider Fallback Chain**: If a model returns 404/429/timeout, automatically traverse across alternate providers rather than failing.

## 2. Quorum & Timeout Integrity for Large Pasted Contexts (`--paste`)
- **Per-Attempt Timeout**: Single model queries (`_query_model_with_fallback_and_timing`) must allow at least `35.0` seconds to process large pasted clipboard inputs (`--paste`).
- **Quorum Zero-Member Prohibition**: In multi-model deliberation stages (`Stage 1`, `Stage 2`), **NEVER** early-exit or abort if `0` models have completed (`len(opinions) == 0`).
- **Dynamic Quorum Thresholds**:
  - `elapsed > 20.0s` required for early quorum with 2+ members.
  - `elapsed > 40.0s` required for early quorum with 1 member.
  - `elapsed > 60.0s` hard safety ceiling.

## 3. Copy-Pasteable Non-Coder UX
- **Actionable Completion Guides**: CLI wizards (`setup_keys.py`) and README instructions must always present concrete commands that non-technical users can directly copy and run:
  - `ask MC` (Multi-model deliberation)
  - `ask "your question"` (Smart single-model answer)
  - `cc-models` (Interactive cheatsheet)

## 4. ThreadPoolExecutor `with` Block Timing Trap
- **Problem**: `with ThreadPoolExecutor() as executor:` calls `executor.shutdown(wait=True)` in its `__exit__`, blocking until ALL threads finish — even after early quorum `break` with `shutdown(wait=False)`.
- **Invariant**: Always record `stage_duration = time.time() - stage_start` **INSIDE** the `with` block (after the polling loop, before `__exit__` runs). Never place timing/reporting code OUTSIDE the `with` block.
- **Rationale**: Without this, "Fast Quorum Reached • 20s" followed by "Completed in 54s" confuses users and hides the true benefit of quorum optimization.

## 5. Fallback Model ID Validation
- **No Bogus/Invented Model IDs**: Never add invented model identifiers (e.g., `"openrouter/free"`) to fallback chains. Every model in a fallback list MUST be a real, resolvable model ID that the corresponding provider API accepts.
- **Test**: If unsure whether a model ID is valid, verify it against the live model registry before adding.

## 6. Cancelled Model Transparency
- **No Silent Disappearances**: When a quorum `break` cancels still-running models, always print a cancellation line: `⊘ [model_name] cancelled (quorum reached)`. Users must never see a model start but then silently vanish from the output.

## 7. Multi-Provider Council Spread (Critical)
- **Provider Isolation**: Council members MUST be spread across different API providers (Gemini, Z.ai, OpenRouter, NVIDIA) so that rate limits, 404s, or outages on a single provider cannot kill multiple council members.
- **Slot Priority**: Slot 1 = Direct Gemini API (`gemini-2.5-flash`), Slot 2 = Direct Z.ai API (`glm-4.5-flash`), Slot 3 = Best OpenRouter free model for the task type. Each slot uses a different API endpoint with its own rate-limit bucket.
- **Never All-OpenRouter**: Never select all 3 council members from the same provider's free tier. This is the #1 cause of council failures.

## 8. Model Routing Disambiguation
- **Z.ai vs NVIDIA GLM Conflict**: Models like `glm-4.5-flash` and `glm-4-flash` are Z.ai models and MUST route to `https://open.bigmodel.cn/api/paas/v4/`. Only `nvidia/z-ai/glm-5.1` style models (with `nvidia/` prefix) should route to NVIDIA NIM. The NVIDIA model check must explicitly exclude direct Z.ai prefixes (`glm-`, `z-ai/glm-`, `zhipu/`).

## 9. Caveman Integration = System Prompt Injection (Not CLI Binary)
- **How Caveman actually works**: Caveman (JuliusBrussee/caveman) is a system prompt injection that tells LLMs to respond in compressed caveman-speak. There is no `caveman-compress` CLI binary.
- **Output compression**: Achieved by appending Caveman rules (`get_system_prompt_injection()`) to the system prompt BEFORE the LLM generates a response. The LLM itself responds tersely.
- **Input compression**: Achieved by lightweight rule-based filler stripping (remove articles, hedging, pleasantries) — no subprocess calls needed.
- **Never call non-existent binaries**: Do not use `subprocess.run(["caveman-compress", ...])`. This binary does not exist in the upstream project.

## 10. Disable Internal Client Retries (max_retries=0)
- **The Issue**: By default, the `OpenAI` python client automatically retries failed requests up to 2 times. If a request is stuck, this causes it to hang for `timeout * 3` seconds, bypassing RoutingMagic's manual thread timeouts and fallback logic, leading to massive delays and false quorum cancellations.
- **The Fix**: ALWAYS pass `max_retries=0` when instantiating `OpenAI(api_key=..., timeout=req_timeout, max_retries=0)`. We want the client to fail fast (after exactly `req_timeout`) so that `RoutingMagic` can immediately catch the exception and route to a DIFFERENT fallback provider instead of silently retrying a broken one.
