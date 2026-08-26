# RoutingMagic aliases — https://github.com/prakharmishra2026/RoutingMagic
# Install: source ~/Projects/RoutingMagic/aliases.zsh in ~/.zshrc
# Core philosophy: 4 simple aliases, everything else automatic.

# ── DIRECT MULTI-PROVIDER ROUTING (OpenRouter, Gemini, Z.ai, NVIDIA, OpenAI) ──
_rm() {
  python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" "$@"
}

# Helper: Direct OpenRouter
_or() { _rm "openrouter/$1" "${@:2}"; }

# Helper: Direct NVIDIA NIM
_nim() { _rm "nvidia/$1" "${@:2}"; }

# ── FREE & RESILIENT MODELS (direct OpenRouter + Multi-Provider Fallback) ──
cc()   { _or poolside/laguna-s-2.1:free "$@"; }                          # Best free coding (70.2% Terminal-Bench) · 262k
cch()  { _or poolside/laguna-xs-2.1:free "$@"; }                        # Quick edits / one-liners · 262k
cca()  { _or nvidia/nemotron-3-super-120b-a12b:free "$@"; }             # Large context / agentic · 1M
ccc()  { _or qwen/qwen3-coder:free "$@"; }                              # UI / frontend / coder (DEFAULT) · 1M
ccg()  { _or openai/gpt-oss-120b:free "$@"; }                           # Reasoning + tools · 131k
ccx()  { _or qwen/qwen3-next-80b-a3b-instruct:free "$@"; }             # General / agentic · 262k
ccm()  { _or google/gemma-4-31b-it:free "$@"; }                         # Resilient general · 262k
ccu()  { _or nvidia/nemotron-3-ultra-550b-a55b:free "$@"; }             # 550B flagship reasoning · 1M
ccz()  { _or z-ai/glm-5.2:free "$@"; }                                  # GLM-5.2 · 1M
ccb()  { _rm smart "$@"; }                                              # Smart auto-route

# ── NVIDIA NIM DIRECT (Tier 1 — Primary, same models that cost $ on OpenRouter) ──
nd()   { _nim deepseek-ai/deepseek-v4-flash "$@"; }                     # ⭐ Coding
ng()   { _nim z-ai/glm-5.2 "$@"; }                                      # ⭐ Agent/Coding 1M ctx
nm()   { _nim minimaxai/minimax-m2.7 "$@"; }                            # Financial modeling
nk()   { _nim qwen/qwen3-coder-480b-a35b-instruct "$@"; }               # Agentic coding 256K
nl()   { _nim nvidia/nemotron-3-ultra-550b-a55b "$@"; }                 # Flagship reasoning
nu()   { _nim nvidia/nemotron-3-super-120b-a12b "$@"; }                 # Agent/multi-step 1M
ngg()  { _nim google/gemma-4-31b-it "$@"; }                             # General + vision

# ── DIRECT FAST FREE MODELS (Google Gemini & Z.ai) ──────────────────────
ccgem() { _rm gemini-2.5-flash "$@"; }                                  # Google Gemini 2.5 Flash (Direct API)
ccglm() { _rm glm-4.5-flash "$@"; }                                     # Z.ai GLM-4.5 Flash (Direct API)

# ── NATIVE Claude (direct to api.anthropic.com) ─────────────────────────
ccs() { claude --model claude-sonnet-4-6 "$@"; }                        # Sonnet 4.6 — production, agentic, tools
cco() { claude --model claude-opus-4-8 "$@"; }                          # Opus 4.8 — architecture, hardest reasoning
ccq() { claude --model claude-haiku-4-5-20251001 "$@"; }                # Haiku 4.5 — fastest native

# ── OpenAI Models (via direct API / OpenRouter) ─────────────────────────
op()   { _rm openai/gpt-5 "$@"; }                                       # General flagship (GPT-5)
opt()  { _rm openai/gpt-4-turbo "$@"; }                                 # Agentic coding model
opo3() { _rm openai/o3-mini "$@"; }                                     # Reasoning / coding

# ── CHEATSHEET ──────────────────────────────────────────────────────────
cc-models() {
  cat <<'EOF'

╔═══════════════════════════════════════════════════════════════════════╗
║              ROUTINGMAGIC — MODEL ROUTER (v2.2)                      ║
╠═══════════════════════════════════════════════════════════════════════╣
║ TIER 1: NVIDIA NIM DIRECT (Primary — 40 RPM, no credit card)         ║
║  nd   DeepSeek-V4-Flash      coding                  1M              ║
║  ng   GLM-5.2                agent/coding            1M              ║
║  nm   MiniMax-M2.7           financial modeling      1M              ║
║  nk   Qwen3-Coder-480B       agentic coding          256K            ║
║  nl   Nemotron-3-Ultra-550B  flagship reasoning       1M              ║
║  nu   Nemotron-3-Super-120B  agent/multi-step        1M              ║
║  ngg  Gemma-4-31B-IT         general + vision         1M              ║
╠═══════════════════════════════════════════════════════════════════════╣
║ TIER 2: OPENROUTER FREE (Fallback when NIM rate-limited)             ║
║  cc   Poolside Laguna S 2.1   best free coding       262k            ║
║  ccc  Qwen3-Coder             UI/frontend/coder      1M              ║
║  ccz  GLM-5.2                 agent/coding           1M              ║
║  ccg  GPT-OSS-120B            reasoning+tools        131k            ║
║  ccx  Qwen3-Next-80B          general/agentic        262k            ║
║  ccm  Gemma-4-31B-IT          resilient general      262k            ║
║  ccu  Nemotron-3-Ultra-550B   flagship reasoning     1M              ║
║  cca  Nemotron-3-Super-120B   large context          1M              ║
║  cch  Laguna XS 2.1           quick edits            262k            ║
║  ccb  Smart auto-router       best model for task                    ║
╠═══════════════════════════════════════════════════════════════════════╣
║ DIRECT FAST FREE (Gemini, Z.ai)                                       ║
║  ccgem  Gemini 2.5 Flash      fast Google direct     1M              ║
║  ccglm  GLM-4.5 Flash         fast Z.ai direct       128k            ║
╠═══════════════════════════════════════════════════════════════════════╣
║ NATIVE (api.anthropic.com, keychain)                                 ║
║  ccs  Sonnet 4.6    cco  Opus 4.8    ccq  Haiku 4.5                ║
╠═══════════════════════════════════════════════════════════════════════╣
║ OPENAI & NVIDIA DIRECT                                               ║
║  op   GPT-5   opt  GPT-4-Turbo   opo3  o3-mini   glm  GLM-5.1        ║
╠═══════════════════════════════════════════════════════════════════════╣
║ 🪨 CAVEMAN COMPRESSION (automatic)                                   ║
║  /caveman lite  = ~30% savings  (complex explanations)               ║
║  /caveman full  = ~65% savings  (daily coding, DEFAULT)             ║
║  /caveman ultra = ~75% savings  (quick lookups)                     ║
║  /caveman-stats = show session token savings                        ║
╠═══════════════════════════════════════════════════════════════════════╣
║ 🧠 DEEP REASONING (automatic — no aliases needed)                    ║
║  ask "prove..."          → auto high-effort, multi-pass, reasoning  ║
║  ask deep MC "..."       → Council + deep context + deep reasoning  ║
╠═══════════════════════════════════════════════════════════════════════╣
║ 429 FALLBACK CHAINS (auto)                                           ║
║  UI:     ccc→ccm→ccx   Gen:  cc→ccg→ccx   Reason: ccg→ccu→ccx       ║
║  Quick:  cch→ccm       Large: cca→ccc→ccu  Agent: ccg→ccx→cc        ║
╠═══════════════════════════════════════════════════════════════════════╣
║ 📊 UNIFIED USAGE DASHBOARD (all AI tools)                            ║
║  dashboard open   → scan + open browser (localhost:9898)             ║
║  dashboard scan   → scan all sources (Claude, OpenCode, Hermes...)   ║
║  dashboard stop   → stop the dashboard server                        ║
║  /dashboard       → same from inside REPL                            ║
╚═══════════════════════════════════════════════════════════════════════╝

EOF
}

# ═══════════════════════════════════════════════════════════════════
#  4 CORE ALIASES — case-insensitive MC
# ═══════════════════════════════════════════════════════════════════
# Usage:
#   ask "question"           → quick answer, no repo context
#   ask deep "question"      → deep repo context (reads memory.md, etc.)
#   ask MC "question"        → Model Council + deep context
#   ask deep MC "question"   → same as ask MC (explicit)
# Case-insensitive: MC, mc, Mc, mC all work
# ═══════════════════════════════════════════════════════════════════

ask() {
  local args=("$@")
  # Check if first arg is "deep"
  if [[ ${#args[@]} -ge 1 && "${args[1]:l}" == "deep" ]]; then
    local rest=("${args[@]:1}")
    local normalized=()
    for arg in "${rest[@]}"; do
      if [[ "${arg:l}" == "mc" ]]; then
        normalized+=("MC")
      else
        normalized+=("$arg")
      fi
    done
    if [[ ${#normalized[@]} -gt 0 && "${normalized[1]:l}" == "mc" ]]; then
      # ask deep MC ...
      python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council deep "${normalized[@]:1}"
    else
      # ask deep ...
      python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" smart deep "${normalized[@]}"
    fi
  elif [[ ${#args[@]} -ge 1 && "${args[1]:l}" == "mc" ]]; then
    # ask MC ...
    local rest=("${args[@]:1}")
    local normalized=()
    for arg in "${rest[@]}"; do
      if [[ "${arg:l}" == "mc" ]]; then
        normalized+=("MC")
      else
        normalized+=("$arg")
      fi
    done
    python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "${normalized[@]}"
  else
    # ask "question"
    python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" smart "${args[@]}"
  fi
}

# Also support "askdeep" as single word
askdeep() {
  ask deep "$@"
}

# ═══════════════════════════════════════════════════════════════════
#  REPL COMMANDS (inside ask/ask deep REPL)
# ═══════════════════════════════════════════════════════════════════

# Global Model Council aliases
"/council"() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }
"/MC"()      { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }
"/mc"()      { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }
mc() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }
MC() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }

# ═══════════════════════════════════════════════════════════════════
#  UNIFIED USAGE DASHBOARD (all AI tools)
# ═══════════════════════════════════════════════════════════════════
dashboard() {
  local cmd="${1:-open}"
  local script="${HOME}/Projects/RoutingMagic/dashboard_server.py"
  case "$cmd" in
    scan)
      python3 "$script" scan
      ;;
    open|start)
      python3 "$script" &
      sleep 1.5
      open "http://localhost:9898" 2>/dev/null
      echo "Dashboard: http://localhost:9898"
      ;;
    stop)
      pkill -f dashboard_server.py 2>/dev/null && echo "Dashboard stopped." || echo "Dashboard not running."
      ;;
    *)
      echo "Usage: dashboard [open|scan|stop]"
      ;;
  esac
}

# ═══════════════════════════════════════════════════════════════════
#  SMART MACOS OPEN OVERRIDE
# ══════════════════════════════════════════════════════════════════
open() {
  if [[ $# -eq 0 ]]; then
    _rm openai/gpt-5
  elif [[ "$1" == "gpt-"* ]] || [[ "$1" == "o1-"* ]] || [[ "$1" == "o3-"* ]]; then
    _rm "openai/$1" "${@:2}"
  elif [[ "$1" == "openai/"* ]]; then
    _rm "$@"
  else
    command open "$@"
  fi
}

# ═══════════════════════════════════════════════════════════════════
#  AUTO-PLACEMENT OF save_handler.py AT REPOSITORY ROOTS
# ═══════════════════════════════════════════════════════════════════
_routing_magic_save_handler_sync() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    local repo_root
    repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
    if [ -n "$repo_root" ] && [ ! -f "$repo_root/save_handler.py" ]; then
      local src="${HOME}/Projects/RoutingMagic/save_handler.py"
      if [ -f "$src" ]; then
        cp "$src" "$repo_root/save_handler.py"
        chmod +x "$repo_root/save_handler.py"
        local exclude_file="$repo_root/.git/info/exclude"
        if [ -f "$exclude_file" ]; then
          if ! grep -q "^save_handler.py" "$exclude_file"; then
            echo "save_handler.py" >> "$exclude_file"
          fi
        fi
        echo "🪄  RoutingMagic: Auto-placed save_handler.py at repository root (ignored locally)."
      fi
    fi
  fi
}

# Run once on shell startup/alias source
_routing_magic_save_handler_sync

# Hook into directory changes (cd)
typeset -g -a chpwd_functions
if [[ ${chpwd_functions[(r)_routing_magic_save_handler_sync]} != _routing_magic_save_handler_sync ]]; then
  chpwd_functions+=(_routing_magic_save_handler_sync)
fi