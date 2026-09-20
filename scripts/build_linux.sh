#!/usr/bin/env bash
# OpenDSZ Linux Standalone Executable & Package Build Script
set -e

echo "=== Building OpenDSZ for Linux (x86_64) ==="

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# Ensure dependencies
python3 -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller

# 1. Build Single-File Standalone Linux Binary
echo "--- Building Single-File Binary (OpenDSZ-Linux-x86_64) ---"
pyinstaller --noconfirm --clean --onefile --windowed \
    --name "OpenDSZ-Linux-x86_64" \
    --icon "opendsz/assets/logo.png" \
    --add-data "profiles:profiles" \
    --add-data "opendsz/assets:opendsz/assets" \
    run.py

# 2. Build Directory Package & Tarball
echo "--- Building Portable Tarball (OpenDSZ-Linux-x86_64.tar.gz) ---"
pyinstaller --noconfirm --onedir --windowed \
    --name "OpenDSZ" \
    --icon "opendsz/assets/logo.png" \
    --add-data "profiles:profiles" \
    --add-data "opendsz/assets:opendsz/assets" \
    run.py

cd dist
tar -czvf OpenDSZ-Linux-x86_64.tar.gz OpenDSZ/
echo "[SUCCESS] Generated dist/OpenDSZ-Linux-x86_64 and dist/OpenDSZ-Linux-x86_64.tar.gz"
