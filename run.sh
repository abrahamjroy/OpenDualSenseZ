#!/usr/bin/env bash
# OpenDSZ Launch Script for Linux and macOS
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if command -v python3 &>/dev/null; then
    exec python3 run.py "$@"
elif command -v python &>/dev/null; then
    exec python run.py "$@"
else
    echo "Python 3 is required to run OpenDSZ."
    exit 1
fi
