#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_PYTHON="${SKILL_ROOT}/.venv/bin/python"

if [[ ! -x "${RUNTIME_PYTHON}" ]]; then
  echo "Missing deployed runtime Python: ${RUNTIME_PYTHON}" >&2
  echo "Expected deployed leio-sdlc skill root .venv, rebuilt per release in staging before atomic swap." >&2
  exit 1
fi

export LEIO_SDLC_SKILL_ROOT="${SKILL_ROOT}"
export LEIO_SDLC_RUNTIME_PYTHON="${RUNTIME_PYTHON}"

if [[ -n "${LEIO_DEPLOY_TEST_LOG:-}" ]]; then
  printf 'runtime-python-wrapper:%s:%s\n' "$0" "$*" >> "${LEIO_DEPLOY_TEST_LOG}"
fi

if [[ $# -eq 0 ]]; then
  exec "${RUNTIME_PYTHON}"
fi

exec "${RUNTIME_PYTHON}" "$@"
