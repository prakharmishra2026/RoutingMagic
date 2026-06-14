# ═══════════════════════════════════════════════════════════════════
#  RoutingMagic — Claude Code model aliases
#  https://github.com/prakharmishra2026/RoutingMagic
# ───────────────────────────────────────────────────────────────────
#  TWO ISOLATED WORLDS
#
#   NATIVE Claude  →  ccs / cco / ccq  (or plain `claude` + /model picker)
#                     Talks DIRECT to api.anthropic.com via keychain login.
#                     Default everywhere. Global ~/.claude/settings.json
#                     stays clean — never put a proxy in it.
#
#   FREE models    →  cc cch cca cck ccc ccg ccx ccz ccm ccu ccb
#                     Route through your local 9router gateway
#                     (127.0.0.1:20128 → OpenRouter). Set INLINE per-call so
#                     they never touch global config.
#
#  WHY SO MANY FREE MODELS? — 429 RESILIENCE.
#  OpenRouter free models share a global rate limit AND can be throttled by
#  their upstream provider ("rate-limited upstream", e.g. the Crucible 429
#  that broke Kimi K2.6). The cure is a FALLBACK CHAIN: if your first pick
#  429s, jump to the next model in the same role. See the chains below.
#
#  KIMI NOTE: cck (Kimi K2.6) is KEPT for when its upstream provider recovers,
#  but it 429s frequently today — use ccc (Qwen3-Coder) as the UI default.
#
#  To install: add this line to your ~/.zshrc, then `source ~/.zshrc`
#     source ~/RoutingMagic/aliases.zsh
# ═══════════════════════════════════════════════════════════════════

# ── 9router local gateway (free models) ───────────────────────────
# Sets the gateway INLINE so it never pollutes native/global config.
# Guards on the port so a stopped gateway fails legibly.
_9r() {
  if ! nc -z 127.0.0.1 20128 2>/dev/null; then
    echo "⚠️  9router is not running on :20128 — start it (run: 9router), then retry." >&2
    return 1
  fi
  ANTHROPIC_BASE_URL=http://127.0.0.1:20128 \
  ANTHROPIC_AUTH_TOKEN=9router-local \
  ANTHROPIC_API_KEY= \
  claude --model "$1" "${@:2}"
}

# ── FREE models (via 9router → OpenRouter) ────────────────────────
# Each comment shows: ROLE · context · provider-count (429 resilience)
cc()  { _9r openrouter/poolside/laguna-m.1:free "$@"; }                       # general coding (default) · 262k
cch() { _9r openrouter/poolside/laguna-xs.2:free "$@"; }                      # quick edits / one-liners · 262k
cca() { _9r openrouter/nvidia/nemotron-3-super-120b-a12b:free "$@"; }         # large context · 1M
cck() { _9r openrouter/moonshotai/kimi-k2.6:free "$@"; }                      # UI (Kimi) · 262k · ⚠ 429s often — prefer ccc
ccc() { _9r openrouter/qwen/qwen3-coder:free "$@"; }                          # UI / frontend / coder (DEFAULT) · 1M · 7 providers
ccg() { _9r openrouter/openai/gpt-oss-120b:free "$@"; }                       # reasoning + tools · 131k · 19 providers (MOST reliable)
ccx() { _9r openrouter/qwen/qwen3-next-80b-a3b-instruct:free "$@"; }          # general / agentic · 262k · 6 providers
ccz() { _9r openrouter/z-ai/glm-4.5-air:free "$@"; }                          # fast all-rounder · 131k · 4 providers
ccm() { _9r openrouter/google/gemma-4-31b-it:free "$@"; }                     # resilient general · 262k · 11 providers
ccu() { _9r openrouter/nvidia/nemotron-3-ultra-550b-a55b:free "$@"; }         # 550B flagship reasoning · 1M · ⚠ single provider
ccb() { _9r Builder "$@"; }                                                   # Builder combo (auto-route)

# ── NVIDIA GLM‑5.1 (via 9router) ───────────────────────────────────────────
glm() { _9r nvidia/z-ai/glm-5.1 "$@"; }                                       # GLM‑5.1 model via NVIDIA NIM
ccn() { python "${HOME}/Projects/RoutingMagic/glm5.py" "$@"; }                # Direct fallback script

# ── OpenAI Models (via 9router) ───────────────────────────────────────────
op()   { _9r openai/gpt-5 "$@"; }                                             # General purpose flagship (GPT-5)
opt()  { _9r openai/gpt-4-turbo "$@"; }                                       # Agentic coding model
opo3() { _9r openai/o3-mini "$@"; }                                           # Reasoning / coding


# ── NATIVE Claude (direct to api.anthropic.com, keychain login) ───
ccs() { claude --model claude-sonnet-4-6 "$@"; }                              # Sonnet 4.6 — production, agentic, tools
cco() { claude --model claude-opus-4-8 "$@"; }                                # Opus 4.8 — architecture, hardest reasoning
ccq() { claude --model claude-haiku-4-5-20251001 "$@"; }                      # Haiku 4.5 — fastest native

# ── CHEATSHEET ────────────────────────────────────────────────────
cc-models() {
  cat <<'EOF'

╔════════════════════════════════════════════════════════════════════╗
║                 ROUTINGMAGIC — CLAUDE CODE MODEL ROUTER             ║
╠════════════════════════════════════════════════════════════════════╣
║  FREE  (via 9router → OpenRouter, :20128)                           ║
║  cc    Laguna M.1            general coding (default)   262k        ║
║  cch   Laguna XS.2           quick edits / one-liners   262k        ║
║  cca   Nemotron 3 Super      large context              1M          ║
║  ccc   Qwen3-Coder           UI / frontend (DEFAULT)    1M    7 prov ║
║  cck   Kimi K2.6             UI (kept) ⚠ 429s often — prefer ccc    ║
║  ccg   GPT-OSS-120B          reasoning + tools  131k  19 prov ★safe ║
║  ccx   Qwen3-Next-80B        general / agentic   262k         6 prov ║
║  ccz   GLM-4.5-Air           fast all-rounder    131k         4 prov ║
║  ccm   Gemma-4-31B           resilient general   262k        11 prov ║
║  ccu   Nemotron 3 Ultra 550B flagship reasoning  1M  ⚠ 1 provider   ║
║  ccb   Builder combo         auto multi-model                       ║
╠════════════════════════════════════════════════════════════════════╣
║  OPENAI & NVIDIA  (via 9router)                                    ║
║  open  GPT-5                 General purpose flagship               ║
║  opt   GPT-4-Turbo           Agentic coding model                   ║
║  opo3  o3-mini               Reasoning & Coding                     ║
║  glm   GLM-5.1               NVIDIA NIM model                       ║
║  chat  [model]               Direct Chat REPL (No tool cost, 0 limit)║
╠════════════════════════════════════════════════════════════════════╣
║  NATIVE  (direct to api.anthropic.com, keychain login)             ║
║  claude            default — then /model to switch                  ║
║  ccs   Sonnet 4.6            balanced, production, tools            ║
║  cco   Opus 4.8              architecture, hardest reasoning        ║
║  ccq   Haiku 4.5             fastest native                         ║
╠════════════════════════════════════════════════════════════════════╣
║  429 FALLBACK CHAINS  (if a free model is rate-limited, go next →)  ║
║  UI / frontend   :  ccc → ccz → ccm        (cck/Kimi if available) ║
║  General coding  :  cc  → ccg → ccx                                 ║
║  Reasoning       :  ccg → ccu → ccx                                 ║
║  Large context   :  cca → ccc → ccu       (all 1M)                  ║
║  Quick / trivial :  cch → ccz                                       ║
║  Agentic / tools :  ccg → ccx → cc        (★ gpt-oss = best tools)  ║
╠════════════════════════════════════════════════════════════════════╣
║  SMART ROUTER                                                       ║
║  cc-route "task"   analyse → pick best model → launch               ║
╚════════════════════════════════════════════════════════════════════╝
  Native = default & Antigravity.  Free = explicit cc* only.
  9router up?  nc -z 127.0.0.1 20128 && echo UP || echo DOWN

EOF
}

# ═══════════════════════════════════════════════════════════════════
#  INTELLIGENT MODEL ROUTER  —  task-aware auto-routing
#    cc-route "describe your task"   → picks best model + launches
#  First match wins (top = highest priority).
# ═══════════════════════════════════════════════════════════════════
_cc_route_match() {
  # Returns: "model|tier_label|human_reason|mode"  (mode = native | 9r)
  local t="$1"

  # ── NATIVE: Architecture / Strategy ──────────────────────────────
  if echo "$t" | grep -qiE \
    "(architect|system design|design decision|trade.?off|ADR|PRD|refactor entire|full migration|database schema|schema migration|domain model|event sourcing|CQRS|strategic plan|long.term roadmap|restructure)"; then
    echo "claude-opus-4-8|⚡ NATIVE|Architecture/Design → Opus 4.8|native"

  # ── NATIVE: Critical / Security / Production ─────────────────────
  elif echo "$t" | grep -qiE \
    "(\bproduction\b|\bcritical\b|security|vuln|CVE|\bauth\b.*(bug|error|fail|issue|broken)|\bdeploy fail|race condition|SEBI|compliance|breach|exploit|sql inject|RLS bypass|privilege escalat|data leak|\bpayment\b|financial logic|\b403\b|hotfix|regression|emergency)"; then
    echo "claude-sonnet-4-6|⚡ NATIVE|Critical/Security → Sonnet 4.6|native"

  # ── FREE: UI / Frontend / Design System ──────────────────────────
  elif echo "$t" | grep -qiE \
    "\bUI\b|\bUX\b|\bcomponent\b|frontend|tailwind|framer|figma|design system|layout|responsive|mobile.first|dark mode|glassmorphism|neo.luxury|color scheme|typography|\bcard\b|\bmodal\b|sidebar|navbar|dashboard UI|loading state|skeleton|animation|\bCSS\b"; then
    echo "openrouter/qwen/qwen3-coder:free|🟢 FREE|UI / Frontend → Qwen3-Coder (ccc; fallback: ccz, ccm)|9r"

  # ── FREE: Agent / Automation / Tool Use ──────────────────────────
  elif echo "$t" | grep -qiE \
    "\bagent\b|tool use|function call|\bpipeline\b|orchestrat|workflow|multi.step|\bMCP\b|\bRAG\b|vector store|\bn8n\b|webhook|integration|react agent|tool.?calling|automat"; then
    echo "openrouter/openai/gpt-oss-120b:free|🟢 FREE|Agent / Tools → GPT-OSS-120B (ccg; fallback: ccx, cc)|9r"

  # ── FREE: Large Context / Full Codebase ──────────────────────────
  elif echo "$t" | grep -qiE \
    "(entire codebase|full audit|all files|large context|comprehensive review|read everything|scan all|full repo|every file|summarize the whole|inventory all|full analysis|deep dive)"; then
    echo "openrouter/nvidia/nemotron-3-super-120b-a12b:free|🟢 FREE|Large Context → Nemotron 3 Super 1M (cca; fallback: ccc, ccu)|9r"

  # ── FREE: Heavy Reasoning ────────────────────────────────────────
  elif echo "$t" | grep -qiE \
    "(reason|think through|step by step|prove|derive|complex logic|algorithm design|optimi[sz]e|math|analy[sz]e deeply)"; then
    echo "openrouter/openai/gpt-oss-120b:free|🟢 FREE|Reasoning → GPT-OSS-120B (ccg; fallback: ccu, ccx)|9r"

  # ── FREE: Quick / Trivial ────────────────────────────────────────
  elif echo "$t" | grep -qiE \
    "(^quick |^just |^simple |one.?liner|typo|rename this|what is |what does |explain this|how does |how do i|just a |fast answer|short answer|definition of|meaning of)"; then
    echo "openrouter/poolside/laguna-xs.2:free|🟢 FREE|Quick / Trivial → Laguna XS.2 (cch; fallback: ccz)|9r"

  # ── DEFAULT: General coding ───────────────────────────────────────
  else
    echo "openrouter/poolside/laguna-m.1:free|🟢 FREE|General Coding → Laguna M.1 (cc; fallback: ccg, ccx)|9r"
  fi
}

_cc_launch() {
  local model="$1" mode="$2"
  if [ "$mode" = "native" ]; then
    claude --model "$model"
  else
    _9r "$model"
  fi
}

cc-route() {
  if [ -z "$*" ]; then
    echo "Usage: cc-route \"describe your task in plain English\"" >&2
    return 1
  fi
  local decision model tier reason mode
  decision="$(_cc_route_match "$*")"
  model="${decision%%|*}"; decision="${decision#*|}"
  tier="${decision%%|*}";  decision="${decision#*|}"
  reason="${decision%%|*}"; mode="${decision##*|}"
  echo ""
  echo "⚡ RoutingMagic"
  echo "   Task : $*"
  echo "   Pick : $tier"
  echo "   Why  : $reason"
  echo "   ───────────────────────────────────────────"
  echo "   Launching: $model"
  echo ""
  _cc_launch "$model" "$mode"
}
co() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" "$@"; }  # OpenAI generic wrapper (python fallback)
chat() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" "${1:-openai/gpt-4o}" "${@:2}"; }
ask() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" smart "$@"; }
save() { python3 "${HOME}/Projects/RoutingMagic/save_handler.py" "$@"; }


# Smart macOS open override
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

# Auto-placement of save_handler.py at repository roots
_routing_magic_save_handler_sync() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    local repo_root
    repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
    if [ -n "$repo_root" ] && [ ! -f "$repo_root/save_handler.py" ]; then
      local src="${HOME}/Projects/RoutingMagic/save_handler.py"
      if [ -f "$src" ]; then
        cp "$src" "$repo_root/save_handler.py"
        chmod +x "$repo_root/save_handler.py"
        
        # Silently exclude from git status locally so it doesn't show as untracked
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
