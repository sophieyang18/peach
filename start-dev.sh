#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
HOST="${HOST:-127.0.0.1}"
CONDA_ENV="${CONDA_ENV:-peach}"
FORCE_RESTART=false

BACKEND_PID=""
FRONTEND_PID=""
PNPM_CMD=()

usage() {
  cat <<EOF
Usage: ./start-dev.sh [--restart]

Starts Peach frontend and backend for local development.

Options:
  -r, --restart   Stop services listening on ${BACKEND_PORT}/${FRONTEND_PORT}, then start fresh.
  -h, --help      Show this help.

Environment variables:
  HOST=${HOST}
  BACKEND_PORT=${BACKEND_PORT}
  FRONTEND_PORT=${FRONTEND_PORT}
  CONDA_ENV=${CONDA_ENV}
EOF
}

for arg in "$@"; do
  case "${arg}" in
    -r|--restart)
      FORCE_RESTART=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: ${arg}"
      usage
      exit 1
      ;;
  esac
done

cleanup() {
  if [[ -z "${BACKEND_PID}" && -z "${FRONTEND_PID}" ]]; then
    return
  fi
  echo
  echo "Stopping Peach dev servers started by this script..."
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi
}

port_in_use() {
  local port="$1"
  lsof -iTCP:"${port}" -sTCP:LISTEN -n -P >/dev/null 2>&1
}

pids_on_port() {
  local port="$1"
  lsof -tiTCP:"${port}" -sTCP:LISTEN -n -P 2>/dev/null || true
}

stop_port() {
  local port="$1"
  local pids
  pids="$(pids_on_port "${port}")"
  if [[ -z "${pids}" ]]; then
    return
  fi

  echo "Stopping process(es) on port ${port}: ${pids//$'\n'/ }"
  while IFS= read -r pid; do
    [[ -z "${pid}" ]] && continue
    kill "${pid}" 2>/dev/null || true
  done <<< "${pids}"

  for _ in {1..20}; do
    if ! port_in_use "${port}"; then
      return
    fi
    sleep 0.2
  done

  pids="$(pids_on_port "${port}")"
  while IFS= read -r pid; do
    [[ -z "${pid}" ]] && continue
    kill -9 "${pid}" 2>/dev/null || true
  done <<< "${pids}"
}

print_links() {
  echo
  echo "Peach dev links:"
  echo "  Frontend: http://${HOST}:${FRONTEND_PORT}"
  echo "  Backend:  http://${HOST}:${BACKEND_PORT}"
  echo "  API Docs: http://${HOST}:${BACKEND_PORT}/docs"
  echo
}

trap cleanup EXIT INT TERM

cd "${ROOT_DIR}"

if [[ ! -f ".env" ]]; then
  echo "Missing .env in ${ROOT_DIR}. Backend needs it for database and DeepSeek settings."
  exit 1
fi

if ! command -v conda >/dev/null 2>&1; then
  echo "conda not found. Please open a shell where Miniconda is initialized."
  exit 1
fi

if command -v pnpm >/dev/null 2>&1; then
  PNPM_CMD=(pnpm)
elif conda run -n base pnpm --version >/dev/null 2>&1; then
  PNPM_CMD=(conda run -n base pnpm)
elif [[ -x "${HOME}/miniconda3/bin/pnpm" ]]; then
  PNPM_CMD=("${HOME}/miniconda3/bin/pnpm")
else
  echo "pnpm not found. Tried PATH, conda base, and ${HOME}/miniconda3/bin/pnpm."
  echo "Install it with: conda install -y -n base -c conda-forge pnpm"
  exit 1
fi

BACKEND_RUNNING=false
FRONTEND_RUNNING=false

if port_in_use "${BACKEND_PORT}"; then
  BACKEND_RUNNING=true
fi

if port_in_use "${FRONTEND_PORT}"; then
  FRONTEND_RUNNING=true
fi

if [[ "${FORCE_RESTART}" == true ]]; then
  if [[ "${BACKEND_RUNNING}" == true || "${FRONTEND_RUNNING}" == true ]]; then
    echo "Restart requested. Existing service status:"
    echo "  Backend port ${BACKEND_PORT}: ${BACKEND_RUNNING}"
    echo "  Frontend port ${FRONTEND_PORT}: ${FRONTEND_RUNNING}"
    stop_port "${BACKEND_PORT}"
    stop_port "${FRONTEND_PORT}"
  fi
  BACKEND_RUNNING=false
  FRONTEND_RUNNING=false
elif [[ "${BACKEND_RUNNING}" == true && "${FRONTEND_RUNNING}" == true ]]; then
  echo "Peach frontend and backend already look running."
  print_links
  echo "Use ./start-dev.sh --restart to force restart both."
  exit 0
fi

if [[ "${BACKEND_RUNNING}" == true ]]; then
  echo "Backend already running on http://${HOST}:${BACKEND_PORT}"
else
  echo "Starting Peach backend on http://${HOST}:${BACKEND_PORT}"
  conda run -n "${CONDA_ENV}" uvicorn backend.app.main:app --reload --host "${HOST}" --port "${BACKEND_PORT}" &
  BACKEND_PID="$!"
fi

if [[ "${FRONTEND_RUNNING}" == true ]]; then
  echo "Frontend already running on http://${HOST}:${FRONTEND_PORT}"
else
  echo "Starting Peach frontend on http://${HOST}:${FRONTEND_PORT}"
  (
    cd "${ROOT_DIR}/frontend"
    "${PNPM_CMD[@]}" dev --host "${HOST}" --port "${FRONTEND_PORT}" --strictPort
  ) &
  FRONTEND_PID="$!"
fi

print_links
echo "Press Ctrl+C to stop servers started by this script."

while true; do
  if [[ -n "${BACKEND_PID}" ]] && ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    echo "Backend process exited."
    exit 1
  fi
  if [[ -n "${FRONTEND_PID}" ]] && ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    echo "Frontend process exited."
    exit 1
  fi
  sleep 1
done
