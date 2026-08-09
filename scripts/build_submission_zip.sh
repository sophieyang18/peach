#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/dist-submission"
ZIP_NAME="${1:-peach-agent-submission.zip}"

cd "${ROOT_DIR}"
mkdir -p "${OUT_DIR}"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ -n "$(git status --porcelain)" && "${ALLOW_DIRTY:-0}" != "1" ]]; then
    echo "Git worktree has uncommitted changes."
    echo "Commit the competition version first, then rerun this script."
    echo "If you intentionally want HEAD only, run: ALLOW_DIRTY=1 ./scripts/build_submission_zip.sh"
    exit 1
  fi
  git archive --format=zip --output="${OUT_DIR}/${ZIP_NAME}" HEAD
else
  echo "This script expects a git repository so secrets ignored by git are not packed."
  exit 1
fi

echo "Created ${OUT_DIR}/${ZIP_NAME}"
echo "This zip is built from tracked git files only, so .env, .local, node_modules and dist are excluded."
