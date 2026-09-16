#!/usr/bin/env bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"
if [ -f ".venv/bin/python" ]; then
    exec .venv/bin/python run_server.py "$@"
else
    exec python3 run_server.py "$@"
fi
