#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="DNG2DATA"
REQ_FILE="requirements.txt"
PY_CMD=""

usage () {
  echo "Usage: $0 [-r requirements.txt] [-p python_executable] [-v venv_dir]"
  echo "  -r  Path to requirements file (default: requirements.txt)"
  echo "  -p  Python executable to use (e.g., python3.11)"
  echo "  -v  Virtualenv directory (default: .venv)"
  exit 1
}

while getopts ":r:p:v:h" opt; do
  case $opt in
    r) REQ_FILE="$OPTARG" ;;
    p) PY_CMD="$OPTARG" ;;
    v) VENV_DIR="$OPTARG" ;;
    h) usage ;;
    \?) echo "Invalid option: -$OPTARG" >&2; usage ;;
    :) echo "Option -$OPTARG requires an argument." >&2; usage ;;
  esac
done

if [[ -z "$PY_CMD" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
  elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
  else
    echo "Python not found. Install Python 3 and try again." >&2
    exit 1
  fi
fi

if [[ ! -f "$REQ_FILE" ]]; then
  echo "Requirements file not found: $REQ_FILE" >&2
  exit 1
fi

echo "Using Python: $($PY_CMD --version 2>&1)"
echo "Creating venv at: $VENV_DIR"
"$PY_CMD" -m venv "$VENV_DIR"

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
pip install -r "$REQ_FILE"

echo
echo "✅ Done."
echo "Activate later with: source $VENV_DIR/bin/activate"