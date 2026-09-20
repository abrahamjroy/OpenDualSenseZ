"""
OpenDSZ Standalone Executable Build Script
Uses PyInstaller to generate zero-dependency standalone executables and portable archives.
"""

import os
import sys
import subprocess
import shutil
import zipfile
from PIL import Image

def ensure_multi_res_icon(assets_dir: str):
    """Generates a full 7-resolution Windows .ico from logo.png for crystal clear taskbar and explorer display."""
    logo_path = os.path.join(assets_dir, "logo.png")
    icon_path = os.path.join(assets_dir, "icon.ico")
    if os.path.exists(logo_path):
        img = Image.open(logo_path).convert("RGBA")
        sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        img.save(icon_path, format="ICO", sizes=sizes, bitmap_format="bmp")
        print(f"[ICON] Generated multi-resolution Windows ICO with {len(sizes)} resolutions (BMP-DIB + PNG format).")

def build():
    print("=== Building OpenDSZ Standalone Executables ===")
    root_dir = os.path.dirname(os.path.abspath(__file__))

    dist_dir = os.path.join(root_dir, "dist")
    build_dir = os.path.join(root_dir, "build")
    assets_src = os.path.join(root_dir, "opendsz", "assets")
    icon_path = os.path.join(assets_src, "icon.ico")
    os.makedirs(dist_dir, exist_ok=True)

    # 1. Regenerate multi-resolution icon with standard BMP/PNG hybrid format
    ensure_multi_res_icon(assets_src)

    # 2. Clean previous build caches
    if os.path.exists(build_dir):
        try:
            shutil.rmtree(build_dir)
        except Exception:
            pass

    # =========================================================================
    # Phase A: Build Single-File Standalone Executable (Zero Dependencies)
    # =========================================================================
    print("\n--- Phase A: Building Single-File Standalone Executable (OpenDSZ-DualSense.exe) ---")
    cmd_onefile = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "OpenDSZ-DualSense",
        "--icon", icon_path,
        "--add-data", f"profiles{os.pathsep}profiles",
        "--add-data", f"{assets_src}{os.pathsep}opendsz/assets",
        "run.py"
    ]
    print(f"Running Onefile Build: {' '.join(cmd_onefile)}")
    res_onefile = subprocess.run(cmd_onefile, cwd=root_dir)
    if res_onefile.returncode != 0:
        print("\n[ERROR] Single-file build failed.")
        sys.exit(res_onefile.returncode)

    # =========================================================================
    # Phase B: Build Portable Onedir Package & Zip Archive
    # =========================================================================
    print("\n--- Phase B: Building Portable Onedir Package (OpenDSZ-Windows-x64.zip) ---")
    cmd_onedir = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "OpenDSZ",
        "--icon", icon_path,
        "--add-data", f"profiles{os.pathsep}profiles",
        "--add-data", f"{assets_src}{os.pathsep}opendsz/assets",
        "run.py"
    ]
    print(f"Running Onedir Build: {' '.join(cmd_onedir)}")
    res_onedir = subprocess.run(cmd_onedir, cwd=root_dir)
    if res_onedir.returncode != 0:
        print("\n[ERROR] Onedir build failed.")
        sys.exit(res_onedir.returncode)

    # Copy assets and profiles directly into dist/OpenDSZ root as well
    target_dist = os.path.join(dist_dir, "OpenDSZ")
    dist_assets = os.path.join(target_dist, "opendsz", "assets")
    dist_profiles = os.path.join(target_dist, "profiles")
    os.makedirs(dist_assets, exist_ok=True)
    os.makedirs(dist_profiles, exist_ok=True)

    for item in os.listdir(assets_src):
        s = os.path.join(assets_src, item)
        d = os.path.join(dist_assets, item)
        if os.path.isfile(s):
            shutil.copy2(s, d)

    profiles_src = os.path.join(root_dir, "profiles")
    if os.path.exists(profiles_src):
        for item in os.listdir(profiles_src):
            s = os.path.join(profiles_src, item)
            d = os.path.join(dist_profiles, item)
            if os.path.isfile(s):
                shutil.copy2(s, d)

    # Ensure OpenDSZ-DualSense.exe is also inside dist/OpenDSZ/
    primary_exe = os.path.join(target_dist, "OpenDSZ.exe")
    alt_exe = os.path.join(target_dist, "OpenDSZ-DualSense.exe")
    if os.path.exists(primary_exe):
        shutil.copy2(primary_exe, alt_exe)

    # Generate portable zip archive OpenDSZ-Windows-x64.zip
    zip_path = os.path.join(dist_dir, "OpenDSZ-Windows-x64.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(target_dist):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dist_dir)
                zf.write(full_path, rel_path)
    print(f"[ZIP] Generated portable archive: {zip_path}")

    # Clean intermediate build dir
    if os.path.exists(build_dir):
        try:
            shutil.rmtree(build_dir)
        except Exception:
            pass

    # Invalidate Windows Shell icon cache
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
            standalone_exe = os.path.join(dist_dir, "OpenDSZ-DualSense.exe")
            ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0005, standalone_exe, None)
            ctypes.windll.shell32.SHChangeNotify(0x00001000, 0x0005, dist_dir, None)
            print("[SHELL] Flushed Windows Explorer Shell Icon Cache notifications.")
        except Exception:
            pass

    print(f"\n[SUCCESS] Build artifacts ready in dist/:")
    print(f"  - Direct Single-File Executable: {os.path.join(dist_dir, 'OpenDSZ-DualSense.exe')}")
    print(f"  - Portable Zip Package:          {zip_path}")

if __name__ == "__main__":
    build()
