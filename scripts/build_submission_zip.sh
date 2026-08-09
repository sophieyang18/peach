#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/dist-submission"
ZIP_NAME="${1:-peach-agent-submission.zip}"

cd "${ROOT_DIR}"
mkdir -p "${OUT_DIR}"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git archive --format=zip --output="${OUT_DIR}/${ZIP_NAME}" HEAD
else
  echo "This script expects a git repository so secrets ignored by git are not packed."
  exit 1
fi

echo "Created ${OUT_DIR}/${ZIP_NAME}"
echo "This zip is built from tracked git files only, so .env, .local, node_modules and dist are excluded."
