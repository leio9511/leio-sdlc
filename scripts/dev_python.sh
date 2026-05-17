#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
REQUIREMENTS_FILE="${REPO_ROOT}/requirements.txt"

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
  echo "Missing dependency entry: ${REQUIREMENTS_FILE}" >&2
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${PYTHON_BIN}" -m pip install --upgrade pip
"${PYTHON_BIN}" -m pip install -r "${REQUIREMENTS_FILE}"

if [[ $# -eq 0 ]]; then
  exec "${PYTHON_BIN}"
fi

exec "${PYTHON_BIN}" "$@"
