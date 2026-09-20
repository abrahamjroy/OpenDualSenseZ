#!/usr/bin/env bash
# OpenDSZ Linux Standalone Executable Build Script
set -e

echo "=== Building OpenDSZ for Linux (x86_64) ==="

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# Ensure dependencies
python3 -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

# Run PyInstaller
pyinstaller --noconfirm --clean --windowed \
    --name "OpenDSZ" \
    --icon "opendsz/assets/logo.png" \
    --add-data "profiles:profiles" \
    --add-data "opendsz/assets:opendsz/assets" \
    run.py

# Package release archive
cd dist
tar -czvf OpenDSZ-Linux-x86_64.tar.gz OpenDSZ/
echo "[SUCCESS] Generated dist/OpenDSZ-Linux-x86_64.tar.gz"
