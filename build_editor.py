#!/usr/bin/env python3
"""
build_editor.py — one-click builder for CockatriceCardEditor
Run with: python build_editor.py
Produces a standalone executable in the dist/ folder.
Pillow is bundled automatically for full image support (JPG/PNG/etc.)
"""

import sys
import subprocess
import os


def run(cmd):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}\n")
    subprocess.run(cmd, check=True)


def main():
    print("=" * 55)
    print("  Cockatrice Card Editor — Build Script")
    print("=" * 55)

    print("\n[1/4] Installing / upgrading PyInstaller...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])

    print("\n[2/4] Installing Pillow (for full image format support)...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "Pillow"])

    print("\n[3/4] Building executable...")
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "CockatriceCardEditor",
        "--hidden-import", "PIL._tkinter_finder",
        "cockatrice_editor.py",
    ])

    print("\n[4/4] Done!\n")
    dist_dir = os.path.join(os.path.dirname(__file__), "dist")
    exe_name = ("CockatriceCardEditor.exe"
                if sys.platform == "win32" else "CockatriceCardEditor")
    exe_path = os.path.join(dist_dir, exe_name)

    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"  ✓  Executable : {exe_path}")
        print(f"  ✓  Size        : {size_mb:.1f} MB")
    else:
        print("  ✗  Build may have failed — check output above.")
        sys.exit(1)

    print()
    print("  Share the file in dist/ — no Python or Pillow needed to run it.")
    print()


if __name__ == "__main__":
    main()
