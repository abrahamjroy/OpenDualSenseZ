#!/usr/bin/env bash
# OpenDSZ macOS Application Bundle Build Script
set -e

echo "=== Building OpenDSZ for macOS ==="

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# Ensure dependencies
python3 -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller pyobjc-framework-Quartz

# Run PyInstaller to generate OpenDSZ.app bundle
pyinstaller --noconfirm --clean --windowed \
    --name "OpenDSZ" \
    --icon "opendsz/assets/logo.png" \
    --add-data "profiles:profiles" \
    --add-data "opendsz/assets:opendsz/assets" \
    run.py

# Package release archive
cd dist
zip -r OpenDSZ-macOS-universal.zip OpenDSZ.app OpenDSZ/ 2>/dev/null || zip -r OpenDSZ-macOS-universal.zip OpenDSZ*
echo "[SUCCESS] Generated dist/OpenDSZ-macOS-universal.zip"
