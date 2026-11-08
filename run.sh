#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "========================================================="
echo "  Starting JobHunter Turnkey Copilot"
echo "========================================================="

PYTHON_CMD=""
for cmd in python3 python python3.13 python3.12 python3.11; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "[ERROR] Python 3.11 or newer is required, but none was found."
    echo "Please install Python 3.11+ from https://www.python.org/"
    exit 1
fi

exec "$PYTHON_CMD" run.py "$@"

