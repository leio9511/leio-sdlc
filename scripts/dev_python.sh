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

BOOTSTRAP_MARKER="${VENV_DIR}/.bootstrapped"

ALLOW_FALLBACK=$(REPO_ROOT="${REPO_ROOT}" python3 -c '
import json, os
sdlc_root = os.environ.get("REPO_ROOT", ".")
default_path = os.path.join(sdlc_root, "config", "engines.default.json")
local_path = os.path.join(sdlc_root, "config", "engines.local.json")
val = False
if os.path.exists(default_path):
    try:
        with open(default_path) as f:
            val = json.load(f).get("allow_public_fallback", False)
    except Exception: pass
if os.path.exists(local_path):
    try:
        with open(local_path) as f:
            local_config = json.load(f)
            if "allow_public_fallback" in local_config:
                val = local_config["allow_public_fallback"]
    except Exception: pass
print("true" if val else "false")
')

safe_pip() {
  if ! "${PYTHON_BIN}" -m pip "$@"; then
    if [[ "${ALLOW_FALLBACK}" == "true" ]]; then
      echo "⚠️ Secure pip install failed. Fallback permitted. Retrying with public PyPI..." >&2
      LEIO_DEPLOY_FAKE_FAIL_STEP="" "${PYTHON_BIN}" -m pip "$@" --index-url https://pypi.org/simple
    else
      echo "❌ Compliance Violation: Secure pip install failed and public fallback is forbidden." >&2
      exit 1
    fi
  fi
}


NEED_BOOTSTRAP=0
if [[ ! -x "${PYTHON_BIN}" ]]; then
  NEED_BOOTSTRAP=1
  if [[ -n "${PYTHON_BOOTSTRAP:-}" ]]; then
    "${PYTHON_BOOTSTRAP}" -m venv "${VENV_DIR}"
  else
    python3 -m venv "${VENV_DIR}"
  fi
fi

if [[ -x "${PYTHON_BIN}" ]]; then
  REQS_CHECKSUM="$("${PYTHON_BIN}" -c 'import hashlib; print(hashlib.sha256(open("'${REQUIREMENTS_FILE}'","rb").read()).hexdigest())' 2>/dev/null || echo '')"
  if [[ -n "${REQS_CHECKSUM}" ]] && [[ -f "${BOOTSTRAP_MARKER}" ]]; then
    STORED_CHECKSUM="$(cat "${BOOTSTRAP_MARKER}" 2>/dev/null || :)"
    if [[ "${STORED_CHECKSUM}" != "${REQS_CHECKSUM}" ]]; then
      NEED_BOOTSTRAP=1
    fi
  else
    NEED_BOOTSTRAP=1
  fi
else
  NEED_BOOTSTRAP=1
fi

if [[ "${NEED_BOOTSTRAP}" -eq 1 ]]; then
  safe_pip install --upgrade pip
  safe_pip install -r "${REQUIREMENTS_FILE}"
  if [[ -n "${REQS_CHECKSUM:-}" ]]; then
    printf '%s\n' "${REQS_CHECKSUM}" > "${BOOTSTRAP_MARKER}"
  fi
fi

if [[ $# -eq 0 ]]; then
  exec "${PYTHON_BIN}"
fi

exec "${PYTHON_BIN}" "$@"
