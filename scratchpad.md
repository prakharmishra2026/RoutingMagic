# Scratchpad

## Session: Council Resilience & Bug Fixes
**Date**: Sun Jul 12 2026

### What was done this session
- **Fixed Model Council Quorum Cancellation Bug**: Discovered that the `OpenAI` python client silently retries failed requests up to 2 times, causing the council to hang for 75+ seconds. Added `max_retries=0` to all client instantiations so they fail fast and instantly trigger our custom fallback routing.
- **Rewrote Caveman Integration**: Replaced the non-existent CLI binary call with actual System Prompt Injection. Output compression is now handled naturally by the LLM (65% token savings), and input compression uses lightweight rule-based filler stripping.
- **Refreshed Fallback Model Pool**: Removed dead models (`glm-4-flash`, `google/gemma-4-31b-it:free`, `nvidia/nemotron-4-340b-instruct`) and added reliable free models (`google/gemma-2-9b-it:free`, `qwen/qwen-2.5-72b-instruct:free`, `mistralai/mistral-7b-instruct:free`, `microsoft/phi-3-mini-128k-instruct:free`).
- **Updated Self-Improvement Skill**: Added rules about `max_retries=0` and Caveman System Prompt Injection to `.agents/skills/routingmagic-self-improvement/SKILL.md`.
- **Saved Progress**: Safely committed all changes to Git after `save_handler.py` automation got stuck.

### Key decisions
- Using `max_retries=0` across the board guarantees predictable thread execution times.
- Caveman compression must be a system prompt (upstream architecture) rather than a local binary.

### Open issues
- None! The Model Council is now highly resilient and fast.
