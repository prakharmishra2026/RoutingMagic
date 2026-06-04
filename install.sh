#!/usr/bin/env bash
# RoutingMagic installer — idempotent.
# 1) sources aliases.zsh from ~/.zshrc   2) symlinks the skill for Claude Code.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZSHRC="${HOME}/.zshrc"
SOURCE_LINE="source ${REPO_DIR}/aliases.zsh"
SKILL_LINK="${HOME}/.claude/skills/RoutingMagic"

echo "RoutingMagic install — repo at: ${REPO_DIR}"

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

echo ""
echo "Done. Now run:  source ~/.zshrc  &&  cc-models"
echo "(Free models need 9router running:  npm i -g 9router  then  9router)"
