# RoutingMagic aliases — https://github.com/prakharmishra2026/RoutingMagic
# Install: source ~/Projects/RoutingMagic/aliases.zsh in ~/.zshrc
# Core philosophy: 4 simple aliases, everything else automatic.

# ── 9router local gateway (free models) ───────────────────────────
# Auto-starts on first use. Falls back to direct OpenRouter if 9router unavailable.
_9r() {
  if ! nc -z 127.0.0.1 20128 2>/dev/null; then
    # Auto-start 9router in background tray mode
    (9router -t >/dev/null 2>&1 &)
    sleep 2
  fi
  if nc -z 127.0.0.1 20128 2>/dev/null; then
    ANTHROPIC_BASE_URL=http://127.0.0.1:20128 \
    ANTHROPIC_AUTH_TOKEN=9router-local \
    ANTHROPIC_API_KEY= \
    claude --model "$1" "${@:2}"
  else
    echo "⚠️  9router unavailable — using direct OpenRouter" >&2
    return 1
  fi
}

# ── FREE models (via 9router → OpenRouter) ────────────────────────
cc()  { _9r openrouter/poolside/laguna-m.1:free "$@"; }                    # general coding (default) · 262k
cch() { _9r openrouter/poolside/laguna-xs.2:free "$@"; }                  # quick edits / one-liners · 262k
cca() { _9r openrouter/nvidia/nemotron-3-super-120b-a12b:free "$@"; }     # large context · 1M
ccc() { _9r openrouter/qwen/qwen3-coder:free "$@"; }                      # UI / frontend / coder (DEFAULT) · 1M · 7 providers
ccg() { _9r openrouter/openai/gpt-oss-120b:free "$@"; }                   # reasoning + tools · 131k · 19 providers ★safe
ccx() { _9r openrouter/qwen/qwen3-next-80b-a3b-instruct:free "$@"; }      # general / agentic · 262k · 6 providers
ccm() { _9r openrouter/google/gemma-4-31b-it:free "$@"; }                 # resilient general · 262k · 11 providers
ccu() { _9r openrouter/nvidia/nemotron-3-ultra-550b-a55b:free "$@"; }     # 550B flagship reasoning · 1M · ⚠ single provider
ccb() { _9r Builder "$@"; }                                               # Builder combo (auto-route)

# ── NATIVE Claude (direct to api.anthropic.com) ──────────────────
ccs() { claude --model claude-sonnet-4-6 "$@"; }                         # Sonnet 4.6 — production, agentic, tools
cco() { claude --model claude-opus-4-8 "$@"; }                           # Opus 4.8 — architecture, hardest reasoning
ccq() { claude --model claude-haiku-4-5-20251001 "$@"; }                 # Haiku 4.5 — fastest native

# ── OpenAI Models (via 9router) ────────────────────────────────────
op()   { _9r openai/gpt-5 "$@"; }                                        # General flagship (GPT-5)
opt()  { _9r openai/gpt-4-turbo "$@"; }                                  # Agentic coding model
opo3() { _9r openai/o3-mini "$@"; }                                      # Reasoning / coding

# ── NVIDIA GLM-5.1 (via 9router) ───────────────────────────────────
glm()  { _9r nvidia/z-ai/glm-5.1 "$@"; }                                 # GLM-5.1 via NVIDIA NIM
ccn()  { python "${HOME}/Projects/RoutingMagic/glm5.py" "$@"; }          # Direct fallback script

# ── CHEATSHEET ────────────────────────────────────────────────────
cc-models() {
  cat <<'EOF'

╔══════════════════════════════════════════════════════════════════════╗
║              ROUTINGMAGIC — MODEL ROUTER (v2)                        ║
╠══════════════════════════════════════════════════════════════════════╣
║ FREE (9router → OpenRouter, :20128)                                  ║
║  cc   Poolside Laguna M.1    general coding     262k                 ║
║  cch  Poolside Laguna XS.2   quick edits        262k                 ║
║  cca  Nemotron 3 Super       large context      1M                   ║
║  ccc  Qwen3-Coder            UI/frontend/coder  1M   7prov DEFAULT  ║
║  ccg  GPT-OSS-120B           reasoning+tools    131k 19prov ★safe   ║
║  ccx  Qwen3-Next-80B         general/agentic    262k 6prov          ║
║  ccm  Gemma-4-31B            resilient general  262k 11prov         ║
║  ccu  Nemotron 3 Ultra       flagship reasoning 1M   ⚠ 1prov        ║
║  ccb  Builder combo          auto multi-model                      ║
╠══════════════════════════════════════════════════════════════════════╣
║ NATIVE (api.anthropic.com, keychain)                                 ║
║  ccs  Sonnet 4.6    cco  Opus 4.8    ccq  Haiku 4.5                ║
╠══════════════════════════════════════════════════════════════════════╣
║ OPENAI & NVIDIA (9router)                                            ║
║  op   GPT-5   opt  GPT-4-Turbo   opo3  o3-mini   glm  GLM-5.1       ║
╠══════════════════════════════════════════════════════════════════════╣
║ 🪨 CAVEMAN COMPRESSION (automatic)                                   ║
║  /caveman lite  = ~30% savings  (complex explanations)               ║
║  /caveman full  = ~65% savings  (daily coding, DEFAULT)             ║
║  /caveman ultra = ~75% savings  (quick lookups)                     ║
║  /caveman-stats = show session token savings                        ║
╠══════════════════════════════════════════════════════════════════════╣
║ 🧠 DEEP REASONING (automatic — no aliases needed)                    ║
║  ask "prove..."          → auto high-effort, multi-pass, reasoning  ║
║  ask deep MC "..."       → Council + deep context + deep reasoning  ║
╠══════════════════════════════════════════════════════════════════════╣
║ 429 FALLBACK CHAINS (auto)                                           ║
║  UI:     ccc→ccm→ccx   Gen:  cc→ccg→ccx   Reason: ccg→ccu→ccx       ║
║  Quick:  cch→ccm       Large: cca→ccc→ccu  Agent: ccg→ccx→cc        ║
╚══════════════════════════════════════════════════════════════════════╝

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
    local rest=("${args[@]:2}")
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
    local rest=("${args[@]:2}")
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
#  SMART MACOS OPEN OVERRIDE
# ═══════════════════════════════════════════════════════════════════
open() {
  if [[ $# -eq 0 ]]; then
    _9r openai/gpt-5
  elif [[ "$1" == "gpt-"* ]] || [[ "$1" == "o1-"* ]] || [[ "$1" == "o3-"* ]]; then
    _9r "openai/$1" "${@:2}"
  elif [[ "$1" == "openai/"* ]]; then
    _9r "$@"
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