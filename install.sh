#!/usr/bin/env bash
# RoutingMagic installer — idempotent.
# 1) sources aliases.zsh from ~/.zshrc   2) symlinks the skill for Claude Code.
# 3) creates ~/.routingmagic/.env from template if missing.
# 4) runs interactive API key setup if not configured.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZSHRC="${HOME}/.zshrc"
SOURCE_LINE="source ${REPO_DIR}/aliases.zsh"
SKILL_LINK="${HOME}/.claude/skills/RoutingMagic"
RM_DIR="${HOME}/.routingmagic"
RM_ENV="${RM_DIR}/.env"
ENV_EXAMPLE="${REPO_DIR}/.env.example"

echo "RoutingMagic install — repo at: ${REPO_DIR}"

# 0) Create ~/.routingmagic/.env from template if missing ------------
mkdir -p "${RM_DIR}"
if [ ! -f "${RM_ENV}" ] && [ -f "${ENV_EXAMPLE}" ]; then
  cp "${ENV_EXAMPLE}" "${RM_ENV}"
  chmod 600 "${RM_ENV}"
  echo "  ✓ created ${RM_ENV} from template (chmod 600)"
fi

# 1) zshrc source line (idempotent) ----------------------------------
if [ -f "${ZSHRC}" ] && grep -Fq "${SOURCE_LINE}" "${ZSHRC}"; then
  echo "  ✓ aliases already sourced in ${ZSHRC}"
else
  {
    echo ""
    echo "# RoutingMagic — Claude Code model aliases (https://github.com/prakharmishra2026/RoutingMagic)"
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

# 3) API key setup (interactive, skip if already configured) ---------
if [ -f "${RM_ENV}" ] && grep -q "OPENROUTER_API_KEY=sk-" "${RM_ENV}" 2>/dev/null; then
  echo "  ✓ API keys already configured (${RM_ENV})"
else
  echo ""
  echo "┌──────────────────────────────────────────────────────────┐"
  echo "│  API Key Setup Required                                  │"
  echo "│                                                          │"
  echo "│  RoutingMagic needs at least an OpenRouter API key       │"
  echo "│  to access free models and Model Council.                │"
  echo "│                                                          │"
  echo "│  Sign up free: https://openrouter.ai/keys                │"
  echo "└──────────────────────────────────────────────────────────┘"
  echo ""
  read -p "  Run API key setup now? [Y/n] " -n 1 -r
  echo ""
  if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    python3 "${REPO_DIR}/setup_keys.py"
  else
    echo "  Skipped. Run manually: python3 ${REPO_DIR}/setup_keys.py"
  fi
fi

echo ""
echo "Done. Now run:  source ~/.zshrc  &&  cc-models"
echo "(Configure multi-provider free keys anytime: python3 ~/Projects/RoutingMagic/setup_keys.py)"
