#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
HOST="${HOST:-127.0.0.1}"
LOCAL_API_BASE_URL="${LOCAL_API_BASE_URL:-}"
LOCAL_API_TARGET="${LOCAL_API_TARGET:-http://${HOST}:${BACKEND_PORT}}"
CONDA_ENV="${CONDA_ENV:-peach}"
FORCE_RESTART=false
BACKEND_LOG="${ROOT_DIR}/.local/backend.log"
FRONTEND_LOG="${ROOT_DIR}/.local/frontend.log"
POSTGRES_DIR="${ROOT_DIR}/.local/postgres"
POSTGRES_LOG="${ROOT_DIR}/.local/postgres/server.log"

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
  DATABASE_URL=${DATABASE_URL:-read from .env or SQLite fallback}
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

backend_health_ok() {
  curl -fsS "http://${HOST}:${BACKEND_PORT}/api/health" >/dev/null 2>&1
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

  for _ in {1..20}; do
    if ! port_in_use "${port}"; then
      return
    fi
    sleep 0.2
  done

  echo "Port ${port} is still occupied after stop attempts."
  echo "Please stop it manually, then rerun ./start-dev.sh --restart."
  exit 1
}

print_links() {
  echo
  echo "Peach dev links:"
  echo "  Frontend: http://${HOST}:${FRONTEND_PORT}"
  echo "  Backend:  http://${HOST}:${BACKEND_PORT}"
  echo "  API Docs: http://${HOST}:${BACKEND_PORT}/docs"
  echo "  Backend log: ${BACKEND_LOG}"
  echo "  Frontend log: ${FRONTEND_LOG}"
  echo
}

start_local_postgres() {
  if [[ ! -d "${POSTGRES_DIR}" ]]; then
    echo "Local PostgreSQL data dir not found at ${POSTGRES_DIR}."
    echo "Create it first with: mkdir -p .local/postgres && initdb -D .local/postgres"
    exit 1
  fi

  if conda run -n "${CONDA_ENV}" pg_ctl -D "${POSTGRES_DIR}" status >/dev/null 2>&1; then
    echo "PostgreSQL already running."
    return
  fi

  echo "Starting PostgreSQL from ${POSTGRES_DIR}"
  conda run -n "${CONDA_ENV}" pg_ctl -D "${POSTGRES_DIR}" -l "${POSTGRES_LOG}" start >/dev/null
}

effective_database_url() {
  if [[ -n "${DATABASE_URL:-}" ]]; then
    echo "${DATABASE_URL}"
    return
  fi

  local line=""
  line="$(grep -E '^[[:space:]]*DATABASE_URL=' "${ROOT_DIR}/.env" 2>/dev/null | tail -n 1 || true)"
  if [[ -n "${line}" ]]; then
    line="${line#*=}"
    line="${line%\"}"
    line="${line#\"}"
    line="${line%\'}"
    line="${line#\'}"
    echo "${line}"
    return
  fi

  echo "sqlite+aiosqlite:///./data/peach-local.db"
}

uses_local_postgres() {
  local url="$1"
  [[ "${url}" == postgresql* ]] && {
    [[ "${url}" == *"//localhost"* ]] || [[ "${url}" == *"//127.0.0.1"* ]] || [[ "${url}" == *"@localhost"* ]] || [[ "${url}" == *"@127.0.0.1"* ]]
  }
}

use_sqlite_fallback() {
  mkdir -p "${ROOT_DIR}/data"
  export DATABASE_URL="sqlite+aiosqlite:///./data/peach-local.db"
  export SYNC_DATABASE_URL="sqlite:///./data/peach-local.db"
  echo "Falling back to SQLite for this dev run: ${DATABASE_URL}"
}

prepare_database() {
  local db_url
  db_url="$(effective_database_url)"

  if [[ "${db_url}" == sqlite* ]]; then
    mkdir -p "${ROOT_DIR}/data"
    echo "Using SQLite for local development."
    return
  fi

  if uses_local_postgres "${db_url}"; then
    if ! conda run -n "${CONDA_ENV}" pg_ctl --version >/dev/null 2>&1; then
      echo "Local PostgreSQL is configured, but pg_ctl is not available in conda env ${CONDA_ENV}."
      use_sqlite_fallback
      return
    fi
    if [[ ! -f "${POSTGRES_DIR}/PG_VERSION" ]]; then
      echo "Local PostgreSQL is configured, but ${POSTGRES_DIR} is not an initialized data directory."
      use_sqlite_fallback
      echo "To use local PostgreSQL, initialize it first with: mkdir -p .local/postgres && initdb -D .local/postgres"
      return
    fi
    start_local_postgres
    return
  fi

  echo "Using configured remote database; skipping local PostgreSQL startup."
}

wait_for_backend() {
  echo "Waiting for backend health check..."
  for _ in {1..35}; do
    if backend_health_ok; then
      echo "Backend health check passed."
      return
    fi
    if [[ -n "${BACKEND_PID}" ]] && ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
      echo "Backend process exited during startup."
      echo
      echo "Last backend log lines:"
      tail -n 80 "${BACKEND_LOG}" 2>/dev/null || true
      exit 1
    fi
    sleep 0.4
  done

  echo "Backend did not become healthy on http://${HOST}:${BACKEND_PORT}/api/health."
  echo
  echo "Last backend log lines:"
  tail -n 80 "${BACKEND_LOG}" 2>/dev/null || true
  exit 1
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

if backend_health_ok; then
  BACKEND_RUNNING=true
fi

if port_in_use "${FRONTEND_PORT}"; then
  FRONTEND_RUNNING=true
fi

if [[ "${FORCE_RESTART}" == true ]]; then
  echo "Restart requested. Existing service status:"
  echo "  Backend health on ${BACKEND_PORT}: ${BACKEND_RUNNING}"
  echo "  Backend port ${BACKEND_PORT}: $(port_in_use "${BACKEND_PORT}" && echo true || echo false)"
  echo "  Frontend port ${FRONTEND_PORT}: ${FRONTEND_RUNNING}"
  stop_port "${BACKEND_PORT}"
  stop_port "${FRONTEND_PORT}"
  BACKEND_RUNNING=false
  FRONTEND_RUNNING=false
elif [[ "${BACKEND_RUNNING}" == true && "${FRONTEND_RUNNING}" == true ]]; then
  echo "Peach frontend and backend already look running."
  print_links
  echo "Use ./start-dev.sh --restart to force restart both."
  exit 0
fi

if [[ "${BACKEND_RUNNING}" == false ]] && port_in_use "${BACKEND_PORT}"; then
  echo "Port ${BACKEND_PORT} is occupied, but backend health check failed."
  echo "Use ./start-dev.sh --restart to stop the stale process and start fresh."
  exit 1
fi

prepare_database

if [[ "${BACKEND_RUNNING}" == true ]]; then
  echo "Backend already running on http://${HOST}:${BACKEND_PORT}"
else
  mkdir -p "${ROOT_DIR}/.local"
  : > "${BACKEND_LOG}"
  echo "Starting Peach backend on http://${HOST}:${BACKEND_PORT}"
  conda run -n "${CONDA_ENV}" uvicorn backend.app.main:app --reload --host "${HOST}" --port "${BACKEND_PORT}" > "${BACKEND_LOG}" 2>&1 &
  BACKEND_PID="$!"
  wait_for_backend
fi

if [[ "${FRONTEND_RUNNING}" == true ]]; then
  echo "Frontend already running on http://${HOST}:${FRONTEND_PORT}"
else
  mkdir -p "${ROOT_DIR}/.local"
  : > "${FRONTEND_LOG}"
  echo "Starting Peach frontend on http://${HOST}:${FRONTEND_PORT}"
  echo "Frontend API base: ${LOCAL_API_BASE_URL:-same-origin /api proxy}"
  echo "Frontend API proxy target: ${LOCAL_API_TARGET}"
  (
    cd "${ROOT_DIR}/frontend"
    export VITE_API_BASE_URL="${LOCAL_API_BASE_URL}"
    export VITE_DEV_API_TARGET="${LOCAL_API_TARGET}"
    "${PNPM_CMD[@]}" dev --host "${HOST}" --port "${FRONTEND_PORT}" --strictPort
  ) > "${FRONTEND_LOG}" 2>&1 &
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
