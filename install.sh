#!/usr/bin/env bash
# RoutingMagic installer — idempotent.
# 1) sources aliases.zsh from ~/.zshrc
# 2) symlinks the skill for Claude Code
# 3) creates ~/.routingmagic/.env with placeholders if missing and AUTO-OPENS it
# 4) runs interactive API key setup if not configured
# 5) sets up unified usage dashboard
# 6) initializes model registry
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZSHRC="${HOME}/.zshrc"
SOURCE_LINE="source ${REPO_DIR}/aliases.zsh"
SKILL_LINK="${HOME}/.claude/skills/RoutingMagic"
RM_DIR="${HOME}/.routingmagic"
RM_ENV="${RM_DIR}/.env"
ENV_EXAMPLE="${REPO_DIR}/.env.example"

echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                    RoutingMagic Installer v2.2                        ║"
echo "║         Zero-cost AI routing: NVIDIA NIM → OpenRouter → opencode     ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo "  Repo: ${REPO_DIR}"
echo ""

# 0) Create ~/.routingmagic/.env from template if missing + AUTO-OPEN ------
mkdir -p "${RM_DIR}"
if [ ! -f "${RM_ENV}" ] && [ -f "${ENV_EXAMPLE}" ]; then
  cp "${ENV_EXAMPLE}" "${RM_ENV}"
  chmod 600 "${RM_ENV}"
  echo "  ✓ created ${RM_ENV} with placeholders (chmod 600)"
  
  # Auto-open .env in user's default editor
  echo ""
  echo "┌────────────────────────────────────────────────────────────────────┐"
  echo "│  🔑 API KEY SETUP REQUIRED                                         │"
  echo "│                                                                    │"
  echo "│  The ~/.routingmagic/.env file has been created with placeholders. │"
  echo "│  It will now OPEN in your default editor — just fill in your keys. │"
  echo "│                                                                    │"
  echo "│  You need AT LEAST ONE of these (free):                            │"
  echo "│    • NVAPI_KEY          — https://build.nvidia.com/nim/dashboard  │"
  echo "│    • OPENROUTER_API_KEY — https://openrouter.ai/keys              │"
  echo "│                                                                    │"
  echo "│  Optional (direct providers):                                      │"
  echo "│    • GEMINI_API_KEY     — https://aistudio.google.com/apikey       │"
  echo "│    • ZAI_API_KEY        — https://open.bigmodel.cn                 │"
  echo "│    • OPENAI_API_KEY     — https://platform.openai.com/api-keys     │"
  echo "└────────────────────────────────────────────────────────────────────┘"
  echo ""
  echo "  Opening ~/.routingmagic/.env in your editor..."
  
  # Detect editor and open
  if command -v code >/dev/null 2>&1; then
    code "${RM_ENV}" && sleep 1
  elif command -v vim >/dev/null 2>&1; then
    vim "${RM_ENV}"
  elif command -v nano >/dev/null 2>&1; then
    nano "${RM_ENV}"
  elif [ -n "${EDITOR:-}" ]; then
    "${EDITOR}" "${RM_ENV}"
  else
    open "${RM_ENV}"  # macOS default
  fi
  
  echo ""
  echo "  ✓ Edit complete. Press any key to continue..."
  read -n 1 -s -r
  echo ""
fi

# 1) zshrc source line (idempotent) ----------------------------------
if [ -f "${ZSHRC}" ] && grep -Fq "${SOURCE_LINE}" "${ZSHRC}"; then
  echo "  ✓ aliases already sourced in ${ZSHRC}"
else
  {
    echo ""
    echo "# RoutingMagic — Zero-cost AI model routing (https://github.com/prakharmishra2026/RoutingMagic)"
    echo "${SOURCE_LINE}"
  } >> "${ZSHRC}"
  echo "  ✓ added source line to ${ZSHRC}"
fi

# 2) skill symlink (idempotent) --------------------------------------
mkdir -p "${HOME}/.claude/skills"
if [ -L "${SKILL_LINK}" ] && [ "$(readlink "${SKILL_LINK}")" = "${REPO_DIR}" ]; then
  echo "  ✓ skill already symlinked"
elif [ -e "${SKILL_LINK}" ]; then
  echo "  ! ${SKILL_LINK} exists and is not a link to this repo."
  echo "    Back it up and re-run, or point it here manually:"
  echo "    ln -sfn \"${REPO_DIR}\" \"${SKILL_LINK}\""
else
  ln -s "${REPO_DIR}" "${SKILL_LINK}"
  echo "  ✓ symlinked skill → ${SKILL_LINK}"
fi

# 3) Verify API keys configured --------------------------------------
echo ""
echo "  Checking API key configuration..."
if [ -f "${RM_ENV}" ]; then
  has_nvim=false
  has_or=false
  has_gem=false
  has_zai=false
  has_oai=false
  
  if grep -q "^NVAPI_KEY=nvapi-" "${RM_ENV}" 2>/dev/null; then
    has_nvim=true
    echo "  ✓ NVIDIA NIM key configured (Tier 1 — Primary)"
  fi
  if grep -q "^OPENROUTER_API_KEY=sk-or-" "${RM_ENV}" 2>/dev/null; then
    has_or=true
    echo "  ✓ OpenRouter key configured (Tier 2 — Fallback)"
  fi
  if grep -q "^GEMINI_API_KEY=" "${RM_ENV}" 2>/dev/null && ! grep -q "GEMINI_API_KEY=$" "${RM_ENV}" 2>/dev/null; then
    has_gem=true
    echo "  ✓ Google Gemini key configured"
  fi
  if grep -q "^ZAI_API_KEY=" "${RM_ENV}" 2>/dev/null && ! grep -q "ZAI_API_KEY=$" "${RM_ENV}" 2>/dev/null; then
    has_zai=true
    echo "  ✓ Z.ai key configured"
  fi
  if grep -q "^OPENAI_API_KEY=" "${RM_ENV}" 2>/dev/null && ! grep -q "OPENAI_API_KEY=$" "${RM_ENV}" 2>/dev/null; then
    has_oai=true
    echo "  ✓ OpenAI key configured"
  fi
  
  if ! $has_nvim && ! $has_or; then
    echo ""
    echo "┌────────────────────────────────────────────────────────────────────┐"
    echo "│  ⚠  NO TIER 1/2 KEYS DETECTED                                     │"
    echo "│                                                                    │"
    echo "│  You need AT LEAST ONE of:                                         │"
    echo "│    • NVAPI_KEY          — https://build.nvidia.com/nim/dashboard  │"
    echo "│    • OPENROUTER_API_KEY — https://openrouter.ai/keys              │"
    echo "│                                                                    │"
    echo "│  Run the interactive setup to add them:                            │"
    echo "│    python3 ~/Projects/RoutingMagic/setup_keys.py                   │"
    echo "└────────────────────────────────────────────────────────────────────┘"
  fi
fi

# 4) Initialize model registry (if not exists or stale) ---------------
echo ""
echo "  Initializing model registry..."
if python3 "${REPO_DIR}/model_registry_updater.py" --daily --no-health-check 2>/dev/null; then
  echo "  ✓ Model registry updated (NIM + OpenRouter free models)"
else
  echo "  ! Registry init skipped (will run on first use)"
fi

# 5) Dashboard — initial scan (non-interactive, creates unified DB) ---
echo ""
echo "  Setting up unified usage dashboard..."
mkdir -p "${RM_DIR}/metrics"
if python3 "${REPO_DIR}/unified_scanner.py" 2>/dev/null; then
  echo "  ✓ Dashboard DB initialized at ${RM_DIR}/metrics/usage_unified.db"
else
  echo "  ! Dashboard scan skipped (will run on first 'dashboard' command)"
fi
echo "  ✓ Dashboard alias: 'dashboard' (open|scan|stop)"
echo "  ✓ In REPL: '/dashboard' (open|scan|stop)"

# 6) Final summary ----------------------------------------------------
echo ""
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                        INSTALL COMPLETE ✨                             ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Next steps:"
echo "    1. Reload shell:  source ~/.zshrc"
echo "    2. See all models:  cc-models"
echo "    3. Try it:  ask \"What does this project do?\""
echo "    4. Try Council:  ask MC \"Should we use Postgres or SQLite?\""
echo ""
echo "  Dashboard:"
echo "    dashboard open    # Scan + open browser at localhost:9898"
echo "    /dashboard        # From inside REPL"
echo ""
echo "  Key management (anytime):"
echo "    python3 ~/Projects/RoutingMagic/setup_keys.py"
echo ""
echo "  📅 DAILY AUTO-UPDATES (GitHub Action):"
echo "    This repo includes a GitHub Action that runs daily at 1 AM UTC"
echo "    to fetch the latest free models from NVIDIA NIM & OpenRouter."
echo "    To enable for your fork:"
echo "      1. Go to repo Settings → Secrets and variables → Actions"
echo "      2. Add: NVAPI_KEY (from https://build.nvidia.com/nim/dashboard)"
echo "      3. Add: OPENROUTER_API_KEY (from https://openrouter.ai/keys)"
echo ""
echo "  Local alternative (no GitHub):"
echo "    0 1 * * * cd ~/Projects/RoutingMagic && python3 model_registry_updater.py --daily >> ~/.routingmagic/cron.log 2>&1"