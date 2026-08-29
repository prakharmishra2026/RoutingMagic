# RoutingMagic Model Council — Full Audit Prompt

> **Purpose:** Feed this prompt (with the attached codebase context) to any capable model
> (or to the Council itself) to get an independent audit of RoutingMagic's model selection,
> routing logic, and council architecture. Designed for use with opencode, Claude Code, or
> any agentic coding tool.

---

## THE PROMPT

```
You are auditing RoutingMagic — a terminal-based LLM routing engine and multi-agent
council deliberation system. The codebase lives at ~/Projects/RoutingMagic/.

Read ALL of these files before answering:
  - aliases.zsh (shell routing, model aliases, fallback chains)
  - openai_wrapper.py (smart_route(), run_council(), get_client_and_model(), fallback logic)
  - SKILL.md (agent-facing documentation)
  - memory.md, lessons.md, progress.md (project history)
  - model-inventory-2026-08.md (current model landscape snapshot)

Then audit across these 7 dimensions. For each, give a score (1-10), evidence, and
a prioritized fix list.

═══════════════════════════════════════════════════════════════
DIMENSION 1: MODEL INVENTORY FRESHNESS
═══════════════════════════════════════════════════════════════

Compare every model reference in aliases.zsh and openai_wrapper.py against:
  - The live `opencode models` output (461 models across 3 providers)
  - The model-inventory-2026-08.md snapshot

Check for:
  [ ] Models that have been removed from OpenRouter (e.g. deepseek-r1:free vanished)
  [ ] Models still referenced but 429-prone or deprecated (e.g. Kimi K2.6 free tier)
  [ ] New frontier models NOT yet in RoutingMagic's routing (GLM-5.2, MiniMax M3,
      DeepSeek V4 Flash, Inkling, Laguna S 2.1, North Mini Code, etc.)
  [ ] NVIDIA NIM free models that could replace paid OpenRouter models
  [ ] Stale model IDs (e.g. "openrouter/poolside/laguna-m.1:free" — is this still
      the best Poolside model, or is Laguna S 2.1 superior?)
  [ ] The cc* alias system (10 aliases) vs what opencode natively supports (461 models)

Score: __/10
Evidence: [list specific stale or missing models]
Fixes (priority order):
  1.
  2.
  3.

═══════════════════════════════════════════════════════════════
DIMENSION 2: ROUTING HEURISTIC QUALITY
═══════════════════════════════════════════════════════════════

The current system uses two routing layers:
  Layer 1: smart_route() in openai_wrapper.py — regex keyword matching
  Layer 2: _cc_route_match() in aliases.zsh — grep-based shell routing

Evaluate:
  [ ] False positive rate: how often does "fix this bug in the SQL query" route
      to "fast_coding" instead of "financial_math_reasoning"?
  [ ] Category coverage gaps: are there task types NOT matched by any regex?
      (e.g. "write tests", "review PR", "debug memory leak", "optimize query")
  [ ] Financial domain routing: the primary use case is a production investment
      platform. Is there dedicated routing for: financial calculations, stock
      analysis, data integrity fixes, Screener.in parsing, yfinance integration?
  [ ] Overlap/conflicts: do multiple regexes match the same prompt? Which wins?
  [ ] The prompt classification in run_council() (reasoning/coding/agentic/general)
      — is 4 categories enough? Should there be a "financial" category?
  [ ] Is regex-based routing fundamentally limited? Would embedding-based or
      LLM-classified routing be better? What's the cost/latency tradeoff?

Score: __/10
Evidence: [specific examples of misroutes or gaps]
Fixes (priority order):
  1.
  2.
  3.

═══════════════════════════════════════════════════════════════
DIMENSION 3: COUNCIL ARCHITECTURE
═══════════════════════════════════════════════════════════════

Current architecture:
  Stage 1: 3 council members give independent opinions (parallel)
  Stage 2: Each member reviews the other 2's opinions (parallel)
  Stage 3: 1 Chairman synthesizes (dynamic: paid for reasoning, free for general)

Evaluate:
  [ ] Is 3 council members optimal? Research suggests 3-5 is the deliberation
      sweet spot. Would 4 or 5 improve quality enough to justify the latency?
  [ ] Council member selection: currently dynamic from OpenRouter registry.
      Are the selection functions (select_coder, select_reasoning, etc.) robust?
      Do they actually find distinct models, or do they often converge on the
      same model with different prefixes?
  [ ] Chairman selection: should the chairman ALWAYS see the council's work,
      or should there be a "blind review" mode where the chairman doesn't
      see Stage 1/2 outputs?
  [ ] The peer review stage: each member reviews the others' work. This means
      the reviewer sees its OWN opinion in the anonymized block? (Check if
      the anonymization actually prevents self-review.)
  [ ] Scoring rubric: currently "1-10 based on accuracy, depth, usefulness."
      Should there be domain-specific rubrics? (e.g. for financial code:
      "does the suggestion preserve data integrity?")
  [ ] Should there be a Stage 0 (prompt classification + difficulty assessment)
      BEFORE the council is invoked? Currently classification happens inside
      run_council() but the results aren't used to adjust Stage 1/2 prompts.
  [ ] Token budget: 3 models × 2 stages = 6 API calls minimum. Is there a
      way to reduce this without losing quality? (e.g. skip Stage 2 for
      low-difficulty prompts)

Score: __/10
Evidence: [specific architectural weaknesses]
Fixes (priority order):
  1.
  2.
  3.

═══════════════════════════════════════════════════════════════
DIMENSION 4: FALLBACK CHAIN RESILIENCE
═══════════════════════════════════════════════════════════════

Map every model reference to its actual availability:

  aliases.zsh cc* aliases:
    cc  → poolside/laguna-m.1:free     Status: ?
    cch → poolside/laguna-xs.2:free    Status: ?
    cca → nvidia/nemotron-3-super...   Status: ?
    ccc → qwen/qwen3-coder:free       Status: ?
    cck → moonshotai/kimi-k2.6:free    Status: ?
    ccg → openai/gpt-oss-120b:free     Status: ?
    ccx → qwen/qwen3-next-80b...       Status: ?
    ccz → z-ai/glm-4.5-air:free        Status: ?
    ccm → google/gemma-4-31b-it:free   Status: ?
    ccu → nvidia/nemotron-3-ultra...    Status: ?

  openai_wrapper.py fallback chains:
    smart_route() defaults: ?
    chat_oneshot() fallback: ?
    run_council() fallback: ?
    _query_model_with_fallback_and_timing() backup pool: ?

For each: Status = ACTIVE | 429-PRONE | DEPRECATED | REMOVED | UNKNOWN

Also check:
  [ ] The 9router dependency: is port 20128 checked before routing? What happens
      when 9router is down (it currently IS down)?
  [ ] The NVIDIA_API_MAP: does every model in the map actually exist on NIM?
  [ ] The vision fallback chain: are those models still available?
  [ ] The context compression fallback chain: are those models still available?

Score: __/10
Evidence: [list dead/broken references]
Fixes (priority order):
  1.
  2.
  3.

═══════════════════════════════════════════════════════════════
DIMENSION 5: COST OPTIMIZATION
═══════════════════════════════════════════════════════════════

Current cost structure:
  - Free tier: OpenRouter :free models (20 RPM, 200/day without credits, 1000/day with $10+)
  - NVIDIA NIM free: ~40 RPM, no credit card, ~50+ models
  - Paid fallback: varies by model

Evaluate:
  [ ] Should RoutingMagic shift its PRIMARY free tier from OpenRouter :free
      to NVIDIA NIM? NIM has higher RPM (40 vs 20), more models, and the
      same quality. The only downside is the NIM model catalog changes.
  [ ] The council runs 6+ API calls minimum. At free tier, that's 30% of
      your daily budget per council invocation. Is this sustainable?
  [ ] Is there a "council-lite" mode that uses 2 members + 1 chairman
      for routine tasks, reserving full 3+3 for critical decisions?
  [ ] The dynamic model selection in run_council() fetches the OpenRouter
      registry every time. Should this be cached (with TTL)?
  [ ] The get_deep_context() function calls a summarizer model. Is this
      worth the token cost, or is instant context sufficient for most tasks?

Score: __/10
Evidence: [specific cost waste or optimization opportunity]
Fixes (priority order):
  1.
  2.
  3.

═══════════════════════════════════════════════════════════════
DIMENSION 6: FINANCIAL DOMAIN FITNESS
═══════════════════════════════════════════════════════════════

The primary user works on Investogram — a production investment platform with:
  - Python/FastAPI backend (data_fetcher.py, screener_parser.py, verdict_gate.py)
  - Next.js frontend (screener page, hero cards, filters)
  - Real financial calculations (DCF, ROE, debt-to-equity, margin of safety)
  - Production data from yfinance, Screener.in, BSE filings
  - ZERO tolerance for fabricated financial numbers

Evaluate:
  [ ] Is there ANY financial-domain routing in smart_route() or _cc_route_match()?
      (Hint: "financial analysis" routes to nemotron-3-super, but "stock price",
      "DCF model", "balance sheet parsing" have no dedicated route.)
  [ ] Which free models are SAFEST for financial code? Research shows:
      - DeepSeek V4 Flash: strong at Python, good at following instructions
      - GLM-5.2: best for long-context agent workflows
      - MiniMax M2.7: explicitly handles "financial modeling"
      - Nemotron Ultra 550B: flagship reasoning but single provider
      Are any of these in the current routing? Should they be?
  [ ] The council's system prompt includes "Charlie Munger mental models" —
      is this appropriate for ALL task types, or should financial prompts
      get a different system prompt (e.g. one that emphasizes "never fabricate
      numbers, always check for None vs 0")?
  [ ] For the Investogram project specifically, what model should handle:
      - data integrity fixes (Python backend)?
      - UI/component work (Next.js frontend)?
      - financial reasoning (verdict_gate, math_engine)?
      - production code review before merge?

Score: __/10
Evidence: [specific financial domain gaps]
Fixes (priority order):
  1.
  2.
  3.

═══════════════════════════════════════════════════════════════
DIMENSION 7: DELIBERATION PROTOCOL QUALITY
═══════════════════════════════════════════════════════════════

Review the full Stage 1 → Stage 2 → Stage 3 pipeline in run_council():

  [ ] Stage 1: Are the opinions truly independent? Do council members
      see each other's work? (They shouldn't.)
  [ ] Stage 2: The peer review prompt asks members to "critically evaluate
      each response" — but does the anonymization actually work? If member
      A sees 3 responses and one of them IS its own output, does the model
      recognize itself?
  [ ] Stage 2: The scoring is "1-10 based on accuracy, depth, usefulness."
      Is this too vague? Should there be a structured rubric with sub-scores?
  [ ] Stage 3: The Chairman "synthesizes" — but what does synthesis mean
      concretely? Does it pick the best response? Merge them? Generate a
      new response informed by all three? The prompt doesn't specify.
  [ ] Error handling: if 2 of 3 council members fail, does the system
      degrade gracefully or just show partial results?
  [ ] The council currently has no "confidence" mechanism. If all 3 members
      agree, that's high confidence. If they disagree sharply, the user
      should know. Is this tracked?
  [ ] Is the council actually better than just using the best single model?
      Has anyone measured this? What's the break-even point where council
      overhead is worth it?

Score: __/10
Evidence: [specific protocol weaknesses]
Fixes (priority order):
  1.
  2.
  3.

═══════════════════════════════════════════════════════════════
FINAL VERDICT
═══════════════════════════════════════════════════════════════

Overall Score: __/10 (average of 7 dimensions)

Top 5 Improvements by Impact:
  1. [highest impact] — [effort: low/med/high]
  2. [second impact] — [effort: low/med/high]
  3. [third impact] — [effort: low/med/high]
  4. [fourth impact] — [effort: low/med/high]
  5. [fifth impact] — [effort: low/med/high]

Immediate Actions (do this week):
  -
  -

Strategic Improvements (next month):
  -
  -

Architecture Changes (next quarter):
  -
  -
```

---

## HOW TO USE THIS PROMPT

### Option A: Self-Audit (run the council on itself)
```bash
cd ~/Projects/RoutingMagic
python3 openai_wrapper.py council "$(cat model-council-audit.md)"
```

### Option B: Feed to opencode
```bash
opencode run "Read ~/Projects/RoutingMagic/model-council-audit.md and execute the full audit against the RoutingMagic codebase. Output scores and fixes for all 7 dimensions."
```

### Option C: Feed to Claude Code (native)
```bash
claude -p "$(cat model-council-audit.md)"
```

### Option D: Split into focused audits
Use each dimension as a separate audit session if the full prompt is too long
for a single context window. Run Dimension 1 + 4 together (inventory + fallbacks),
Dimension 2 + 6 together (routing + financial fitness), Dimension 3 + 7 together
(council architecture + protocol), Dimension 5 standalone (cost).

---

## EXPECTED OUTPUT FORMAT

```json
{
  "audit_date": "2026-08-27",
  "dimensions": [
    {"name": "Model Inventory Freshness", "score": 5, "issues": 8, "top_fix": "..."},
    {"name": "Routing Heuristic Quality", "score": 4, "issues": 6, "top_fix": "..."},
    {"name": "Council Architecture", "score": 6, "issues": 5, "top_fix": "..."},
    {"name": "Fallback Chain Resilience", "score": 3, "issues": 10, "top_fix": "..."},
    {"name": "Cost Optimization", "score": 5, "issues": 4, "top_fix": "..."},
    {"name": "Financial Domain Fitness", "score": 2, "issues": 7, "top_fix": "..."},
    {"name": "Deliberation Protocol Quality", "score": 6, "issues": 5, "top_fix": "..."}
  ],
  "overall_score": 4.4,
  "verdict": "NEEDS_OVERHAUL",
  "top_5_fixes": ["..."]
}
```
