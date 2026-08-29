# RoutingMagic Model Inventory — August 2026

> **Snapshot date:** 2026-08-27
> **Source:** `opencode models` output (461 models) + OpenRouter free collection + NVIDIA NIM free tier research
> **Providers configured:** OpenRouter (API key ✅), NVIDIA NIM (API key ✅), opencode built-in (free ✅)

---

## PROVIDER SUMMARY

| Provider | Total Models | Free Tier | Rate Limit | Credit Card |
|----------|-------------|-----------|------------|-------------|
| NVIDIA NIM | ~100 | ~50+ models free | ~40 RPM | No |
| OpenRouter | ~355 | 17 `:free` tagged | 20 RPM / 200 RPD (1000 with $10+) | No for free |
| opencode built-in | 6 | All free | Unlimited | No |

**9router status: DEAD.** Not running. Not needed. opencode routes directly to OpenRouter and NVIDIA NIM via API keys.

---

## TIER 1: FREE MODELS — Exhaust First

### NVIDIA NIM Free (highest priority — best free tier)

These are the SAME models that cost money on other providers, hosted free by NVIDIA.

| Model ID (NIM) | Category | Context | Strength for Investogram |
|----------------|----------|---------|--------------------------|
| `deepseek-ai/deepseek-v4-flash` | Coding | 1M | **#1 pick for Python/FastAPI fixes.** Fast, accurate, instruction-following. |
| `z-ai/glm-5.2` | Agent/Coding | 1M | **#1 pick for multi-file agent work.** Best long-context coding model on NIM. |
| `minimaxai/minimax-m2.7` | Financial | 197K | **Explicitly handles financial modeling.** 56.2% SWE-Pro, 1495 ELO. |
| `minimaxai/minimax-m3` | Multimodal | 1M | 1M context, multimodal. Good for chart/image analysis. |
| `qwen/qwen3-coder-480b-a35b-instruct` | Agentic Coding | 256K | Purpose-built for agentic coding. 480B params. |
| `mistralai/mistral-large-3-675b-instruct-2512` | General | — | 675B flagship. Strong general reasoning. |
| `nvidia/nemotron-3-ultra-550b-a55b` | Reasoning | 1M | 550B flagship. Deep reasoning. Single provider risk. |
| `google/gemma-4-31b-it` | General | 262K | Google's latest. Reliable, multi-provider. |
| `nvidia/nemotron-3.5-lightning` | Fast | 1M | 30B-A3B, fast for quick tasks. |
| `moonshotai/kimi-k3` | UI/Coding | — | Latest Kimi. Check availability. |
| `meta/llama-4-maverick-17b-128e-instruct` | General | — | 128 experts MoE. Popular on NIM. |
| `mistralai/mistral-medium-3.5-128b` | General | — | Good mid-tier option. |

### OpenRouter Free (`:free` tagged)

| Model ID | Category | Context | Providers | Notes |
|----------|----------|---------|-----------|-------|
| `nvidia/nemotron-3-ultra-550b-a55b:free` | Reasoning | 1M | 1 | **Top free model.** 550B flagship. ⚠ single provider. |
| `poolside/laguna-s-2.1:free` | Coding | 262K | — | **Best free coding.** 70.2% Terminal-Bench. |
| `nvidia/nemotron-3-super-120b-a12b:free` | Agent | 1M | — | 120B, 1M context. Good for multi-step. |
| `nvidia/nemotron-3.5-lightning:free` | Fast | 1M | — | 30B-A3B, lightweight. |
| `cohere/north-mini-code:free` | Coding | 256K | — | **Fastest free coding** (69 tok/s). Apache 2.0. |
| `poolside/laguna-xs-2.1:free` | Coding | 262K | — | Compact coding. Good for quick edits. |
| `minimax/minimax-m3:free` | Multimodal | 1.05M | — | 1M context, multimodal. |
| `dots-studio/dots-3-note-preview:free` | Reasoning | 512K | — | 280B MoE, 16B active. |
| `thinkingmachines/inkling:free` | Reasoning | 1.05M | — | 975B total, 41B active. Multimodal. |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | Multimodal | 256K | — | 30B, text/image/audio. |
| `thinkingmachines/inkling-small:free` | Reasoning | 1.05M | — | 276B total, 12B active. |
| `z-ai/glm-5.2:free` | Coding/Agent | 256K | — | **Best for long-context coding/agent.** |
| `minimax/minimax-m2.7:free` | Financial | 197K | — | Financial modeling, debugging. |
| `google/gemma-4-31b-it:free` | General | 262K | — | Google's latest. Vision capable. |
| `google/gemma-4-26b-a4b-it:free` | General | 262K | — | Compact Gemma 4. |
| `liquid/lfm-2.5-2.6b:free` | Reasoning | 66K | — | Small, fast. NOT for coding. |
| `nvidia/nemotron-3.5-content-safety:free` | Safety | — | — | Moderation only. |

### opencode Built-in Free

| Alias | Model | Notes |
|-------|-------|-------|
| `opencode/big-pickle` | opencode/big-pickle | Current session model |
| `opencode/hy3-free` | opencode/hy3-free | Free tier |
| `opencode/mimo-v2.5-free` | opencode/mimo-v2.5-free | Xiaomi Mimo |
| `opencode/muse-spark-1.2-contributor-free` | opencode/muse-spark-1.2-contributor-free | Meta Muse |
| `opencode/nemotron-3-ultra-free` | opencode/nemotron-3-ultra-free | Same 550B, wrapper |
| `opencode/nemotron-3.5-lightning-free` | opencode/nemotron-3.5-lightning-free | Fast fallback |

---

## TIER 2: CHEAPEST PAID (after free exhausted)

| Priority | Model | Cost (in/out per 1M) | Best For |
|----------|-------|---------------------|----------|
| ⭐ 1 | `openrouter/deepseek/deepseek-v4-flash` | ~$0.07 / $0.14 | **Cheapest high-quality coding** |
| 2 | `openrouter/deepseek/deepseek-v3.2` | ~$0.19 / $0.27 | Near-frontier reasoning |
| 3 | `openrouter/google/gemini-2.5-flash` | ~$0.075 / $0.30 | Fast, reliable |
| 4 | `nvidia/nemotron-3-super-120b-a12b` (NIM paid) | $0.085 / $0.40 | If NIM free quota gone |
| 5 | `nvidia/nemotron-3-ultra-550b-a55b` (NIM paid) | $0.50 / $2.50 | Flagship reasoning |
| 6 | `openrouter/anthropic/claude-haiku-4.5` | $1.00 / $5.00 | Best cheap Claude |
| 7 | `openrouter/anthropic/claude-sonnet-4.6` | $2.00 / $10.00 | **Best quality/cost for production** |

---

## TIER 3: NATIVE CLAUDE (direct to Anthropic)

| Alias | Model | Cost | Best For |
|-------|-------|------|----------|
| `ccq` | Claude Haiku 4.5 | Cheapest native | Fast native ops |
| `ccs` | Claude Sonnet 4.6 | Mid-range | Production, agentic, tools |
| `cco` | Claude Opus 4.8 | Most expensive | Architecture, hardest reasoning |

---

## INVESTOGRAM-SPECIFIC RECOMMENDATIONS

### Task: Python Backend Data Integrity (oc/data-truth)
1. **Start:** `nvidia/deepseek-ai/deepseek-v4-flash` (NIM free) — strong Python/FastAPI
2. **Complex multi-file:** `nvidia/z-ai/glm-5.2` (NIM free, 1M context)
3. **Rate-limited:** `openrouter/poolside/laguna-s-2.1:free` (best free coding)
4. **Production final pass:** `openrouter/anthropic/claude-sonnet-4.6` (paid)

### Task: Next.js Frontend (oc/screener-ui)
1. **Start:** `openrouter/poolside/laguna-s-2.1:free` (best free for UI/code)
2. **Complex React/TS:** `nvidia/qwen/qwen3-coder-480b-a35b-instruct` (NIM free)
3. **Visual QA:** `nvidia/google/gemma-4-31b-it` (NIM free, vision capable)
4. **Production final pass:** `openrouter/anthropic/claude-sonnet-4.6` (paid)

### Task: Financial Reasoning (verdict_gate, math_engine)
1. **Start:** `nvidia/minimaxai/minimax-m2.7` (NIM free, explicit financial modeling)
2. **Deep reasoning:** `nvidia/nvidia/nemotron-3-ultra-550b-a55b` (NIM free, flagship)
3. **Production:** `openrouter/anthropic/claude-sonnet-4.6` (paid)

---

## STALE MODEL CHECK

### Models in aliases.zsh cc* aliases — Status:

| Alias | Model | Status | Action |
|-------|-------|--------|--------|
| `cc` | `poolside/laguna-m.1:free` | **REPLACED** | Upgrade to `poolside/laguna-s-2.1:free` (better, newer) |
| `cch` | `poolside/laguna-xs.2:free` | **REPLACED** | Upgrade to `poolside/laguna-xs-2.1:free` (same family, newer) |
| `cca` | `nvidia/nemotron-3-super-120b-a12b:free` | ✅ Active | Keep |
| `cck` | `moonshotai/kimi-k2.6:free` | **429-PRONE** | Demote, use `ccc` as default |
| `ccc` | `qwen/qwen3-coder:free` | ✅ Active | Keep as UI default |
| `ccg` | `openai/gpt-oss-120b:free` | ✅ Active | Keep — most reliable (19 providers) |
| `ccx` | `qwen/qwen3-next-80b-a3b-instruct:free` | ✅ Active | Keep |
| `ccz` | `z-ai/glm-4.5-air:free` | **SUPERSEDED** | Upgrade to `z-ai/glm-5.2:free` |
| `ccm` | `google/gemma-4-31b-it:free` | ✅ Active | Keep |
| `ccu` | `nvidia/nemotron-3-ultra-550b-a55b:free` | ✅ Active | Keep — flagship |
| `ccb` | Builder combo | ✅ Active | Keep |

### Models in openai_wrapper.py fallback chains — Status:

| Chain | Models | Status |
|-------|--------|--------|
| `smart_route()` default | `google/gemma-4-31b-it:free` | ✅ Active |
| `chat_oneshot()` fallback | `gemini-2.5-pro` | ⚠ Check — may not be free |
| `compress_context()` | `google/gemma-4-31b-it:free` | ✅ Active |
| `_query_model_with_fallback` backup pool | `google/gemma-2-9b-it:free`, `qwen/qwen-2.5-coder-32b-instruct:free`, `meta-llama/llama-3-8b-instruct:free`, `microsoft/phi-3-medium-128k-instruct:free` | ⚠ Some may be removed |

---

## NVIDIA NIM FREE TIER NOTES

- **Rate limit:** ~40 RPM (not per-model, global across all NIM calls)
- **No credit card required**
- **Same models** that cost money on other providers
- **OpenAI-compatible** — change base_url to `https://integrate.api.nvidia.com/v1`
- **Key env var:** `NVAPI_KEY` or `NVIDIA_API_KEY`
- **Caveat:** Free tier is for prototyping, not production. No SLA. Model availability can change.
- **Recommendation:** Use NIM free as primary free tier, OpenRouter :free as fallback

---

## KEY RESEARCH FINDINGS

1. **GLM-5.2 is the best free coding model on NIM** — per multiple benchmarks and reviews
2. **DeepSeek V4 Flash is the cheapest paid model** — $0.07/$0.14 per 1M tokens
3. **MiniMax M2.7 explicitly handles financial modeling** — ideal for Investogram
4. **Laguna S 2.1 replaced Laguna M.1** — 70.2% Terminal-Bench, best free coding on OpenRouter
5. **NVIDIA NIM free tier > OpenRouter free tier** — higher RPM (40 vs 20), more models, no credit needed
6. **OpenRouter free models have 20 RPM / 200 RPD limit** — with $10+ credits: 1000 RPD
7. **Qwen3 Coder free tier was deprecated July 2026** — check current status before relying on it
8. **Financial analysis benchmarks:** Claude Fable 5 and GPT-5.6 Sol lead, but for free tier: MiniMax M2.7 and DeepSeek V4 are strongest
