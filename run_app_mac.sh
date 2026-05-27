#!/bin/bash
# Stocky non Stop — macOS launcher
cd "$(dirname "$0")"
export PYTHONPATH="$(pwd):$PYTHONPATH"

VENV_PY=".venv/bin/python3"

echo "Starting Stocky non Stop..."
echo "Project folder: $(pwd)"

if [ -f "$VENV_PY" ]; then
    "$VENV_PY" main.py
elif command -v python3 &>/dev/null; then
    python3 main.py
else
    echo "Python3 not found."
    echo "Install: brew install python python-tk"
    exit 1
fi
