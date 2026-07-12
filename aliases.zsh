# RoutingMagic aliases — https://github.com/prakharmishra2026/RoutingMagic
# Two worlds: NATIVE Claude (ccs/cco/ccq) → direct api.anthropic.com
#              FREE models (cc/cch/cca/cck/ccc/ccg/ccx/ccz/ccm/ccu/ccb) → 9router → OpenRouter
# Why many free models? 429 resilience — fallback chains if one gets rate-limited.
# Kimi (cck) 429s often — prefer ccc (Qwen3-Coder) as default.
# Install: source ~/RoutingMagic/aliases.zsh in ~/.zshrc

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
# Updated July 2026: GLM models no longer free, Kimi removed
cc()  { _9r openrouter/poolside/laguna-m.1:free "$@"; }                       # general coding (default) · 262k
cch() { _9r openrouter/poolside/laguna-xs-2.1:free "$@"; }                    # quick edits / one-liners · 262k
cca() { _9r openrouter/nvidia/nemotron-3-super-120b-a12b:free "$@"; }         # large context · 1M
ccc() { _9r openrouter/qwen/qwen3-coder:free "$@"; }                          # UI / frontend / coder (DEFAULT) · 1M · 7 providers
ccg() { _9r openrouter/openai/gpt-oss-120b:free "$@"; }                       # reasoning + tools · 131k · 19 providers (MOST reliable)
ccx() { _9r openrouter/qwen/qwen3-next-80b-a3b-instruct:free "$@"; }          # general / agentic · 262k · 6 providers
ccm() { _9r openrouter/google/gemma-4-31b-it:free "$@"; }                     # resilient general · 262k · 11 providers
ccu() { _9r openrouter/nvidia/nemotron-3-ultra-550b-a55b:free "$@"; }         # 550B flagship reasoning · 1M · ⚠ single provider
ccb() { _9r Builder "$@"; }                                                   # Builder combo (auto-route)

# ── MYTHOS-INSPIRED DEEP REASONING ─────────────────────────────────────────
# Inspired by OpenMythos recurrent-depth transformer architecture
myth()  { _9r openrouter/openai/gpt-oss-120b:free "$@"; }                     # 🧠 Mythos reasoning with effort control
myth3() { _9r openrouter/nvidia/nemotron-3-ultra-550b-a55b:free "$@"; }       # 🧠 Mythos 550B flagship reasoning
myth5() { _9r openrouter/microsoft/phi-4-mini-reasoning:free "$@"; }          # 🧠 Mythos focused reasoning (Phi-4)

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

╔═══════════════════════════════════════════════════════════════════════╗
║              ROUTINGMAGIC — MODEL ROUTER (v2 Mythos)               ║
╠═══════════════════════════════════════════════════════════════════════╣
║ FREE (9router → OpenRouter, :20128) — July 2026                      ║
║  cc   Poolside Laguna M.1   general coding    262k                   ║
║  cch  Poolside Laguna XS.2  quick edits       262k                   ║
║  cca  Nemotron 3 Super      large context     1M                     ║
║  ccc  Qwen3-Coder           UI/frontend/coder 1M   7prov DEFAULT    ║
║  ccg  GPT-OSS-120B          reasoning+tools   131k 19prov ★safe      ║
║  ccx  Qwen3-Next-80B        general/agentic   262k 6prov             ║
║  ccm  Gemma-4-31B           resilient gen     262k 11prov            ║
║  ccu  Nemotron 3 Ultra      flagship reason   1M   ⚠ 1prov           ║
║  ccb  Builder combo         auto multi-model                         ║
╠═══════════════════════════════════════════════════════════════════════╣
║ 🧠 MYTHOS DEEP REASONING (inspired by OpenMythos)                    ║
║  myth   GPT-OSS-120B        reasoning effort  131k  (deep reasoning) ║
║  myth3  Nemotron 3 Ultra    550B reasoning    1M    (flagship deep)  ║
║  myth5  Phi-4 Mini Reason   focused reasoning  32k  (precise)        ║
╠═══════════════════════════════════════════════════════════════════════╣
║ OPENAI & NVIDIA (9router)                                            ║
║  op   GPT-5   opt  GPT-4-Turbo   opo3  o3-mini   glm  GLM-5.1      ║
╠═══════════════════════════════════════════════════════════════════════╣
║ NATIVE (api.anthropic.com, keychain)                                 ║
║  ccs  Sonnet 4.6   cco  Opus 4.8   ccq  Haiku 4.5                   ║
╠═══════════════════════════════════════════════════════════════════════╣
║ 🧠 ACT EFFORT LEVELS (Adaptive Computation Time)                     ║
║  low    = fast, cheap (simple questions)                             ║
║  medium = standard (explanations, comparisons)                       ║
║  high   = deep reasoning (proofs, algorithms, analysis)              ║
╠═══════════════════════════════════════════════════════════════════════╣
║ 429 FALLBACK CHAINS (next → if rate-limited)                         ║
║  UI:     ccc→ccm→ccx   Gen:  cc→ccg→ccx   Reason: ccg→ccu→ccx       ║
║  Quick:  cch→ccm        Large: cca→ccc→ccu  Agent: ccg→ccx→cc        ║
╠═══════════════════════════════════════════════════════════════════════╣
║  cc-route "task"  → analyze → pick best + effort → launch             ║
╚═══════════════════════════════════════════════════════════════════════╝

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

  # ── FREE: Mythos Deep Reasoning (high effort) ────────────────────
  elif echo "$t" | grep -qiE \
    "(prove|derive|formal|axiom|theorem|recursive|latent|multi.?hop|deep reasoning|complex logic|step.?by.?step|chain.?of.?thought)"; then
    echo "openrouter/openai/gpt-oss-120b:free|🧠 MYTHOS|Deep Reasoning → GPT-OSS-120B (reasoning effort)|9r"

  # ── FREE: Mythos Reasoning with Effort (high effort) ─────────────
  elif echo "$t" | grep -qiE \
    "(reason|think through|math|analy[sz]e deeply|algorithm|optimi[sz]e|proof|derive|equation|derivation|critically|audit)"; then
    echo "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free|🧠 MYTHOS|Reasoning → Nemotron 3 Ultra (550B deep reasoning)|9r"

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
  
  # Detect effort level from tier (Mythos-inspired ACT)
  local effort="medium"
  if echo "$tier" | grep -qi "MYTHOS"; then
    effort="high"
  elif echo "$reason" | grep -qi "quick\|trivial"; then
    effort="low"
  fi
  
  echo ""
  echo "⚡ RoutingMagic"
  echo "   Task : $*"
  echo "   Pick : $tier"
  echo "   Why  : $reason"
  echo "   🧠 ACT: $effort effort"
  echo "   ───────────────────────────────────────────"
  echo "   Launching: $model"
  echo ""
  _cc_launch "$model" "$mode"
}
co() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" "$@"; }  # OpenAI generic wrapper (python fallback)
chat() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" "${1:-openai/gpt-4o}" "${@:2}"; }
ask() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" smart "$@"; }
save() { python3 "${HOME}/Projects/RoutingMagic/save_handler.py" "$@"; }

# Global Model Council aliases & functions
"/council"() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }
"/MC"() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }
"/mc"() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }
mc() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }
MC() { python3 "${HOME}/Projects/RoutingMagic/openai_wrapper.py" council "$@"; }



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
