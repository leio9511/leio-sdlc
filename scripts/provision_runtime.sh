#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <staging-skill-root>" >&2
  exit 2
fi

STAGING_ROOT="$1"
RUNTIME_VENV="${STAGING_ROOT}/.venv"
RUNTIME_PYTHON="${RUNTIME_VENV}/bin/python"
REQUIREMENTS_FILE="${STAGING_ROOT}/requirements.txt"
RUNTIME_SMOKE="${STAGING_ROOT}/scripts/runtime_smoke.py"

if [[ ! -d "${STAGING_ROOT}" ]]; then
  echo "❌ Runtime provisioning failed: staging skill root does not exist: ${STAGING_ROOT}" >&2
  exit 1
fi

if [[ ! -f "${REQUIREMENTS_FILE}" ]]; then
  echo "❌ Runtime provisioning failed: staged requirements.txt is missing." >&2
  exit 1
fi

if [[ ! -f "${RUNTIME_SMOKE}" ]]; then
  echo "❌ Runtime provisioning failed: staged scripts/runtime_smoke.py is missing." >&2
  exit 1
fi

rm -rf "${RUNTIME_VENV}"
python3 -m venv "${RUNTIME_VENV}"
"${RUNTIME_PYTHON}" -m pip install --upgrade -r "${REQUIREMENTS_FILE}"

echo "🐍 Running minimal import smoke..."
"${RUNTIME_PYTHON}" -c "import sys; from pathlib import Path; scripts_dir = Path(${STAGING_ROOT@Q}) / 'scripts'; sys.path.insert(0, str(scripts_dir)); import yaml; import config; import utils_json; import runtime_launch_guard"

echo "🐍 Running official runtime smoke..."
"${RUNTIME_PYTHON}" "${RUNTIME_SMOKE}" --skill-root "${STAGING_ROOT}"
