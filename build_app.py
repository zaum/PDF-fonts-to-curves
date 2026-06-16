#!/usr/bin/env python3
"""
Build script for PDF Fonts to Curves Converter.
Creates standalone executables for Windows, macOS, and Linux.

Usage:
    python build_app.py              # build for current platform
    python build_app.py --linux      # force Linux build
    python build_app.py --macos      # force macOS build (run on macOS)
    python build_app.py --nowindows  # skip Windows-specific deps

Requires: PyInstaller
    pip install pyinstaller
"""
import os
import sys
import platform
import shutil
import subprocess


APP_NAME = "PDFtoCurves"
MAIN_SCRIPT = "PDF fonts to curves.py"
BUILD_DIR = "build"
DIST_DIR = "dist"

SYSTEM = platform.system()


def build():
    force_linux = "--linux" in sys.argv
    force_macos = "--macos" in sys.argv
    effective = "Linux" if force_linux else ("Darwin" if force_macos else SYSTEM)

    old_dist = os.path.join(os.getcwd(), DIST_DIR)
    if os.path.exists(old_dist):
        shutil.rmtree(old_dist)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", APP_NAME,
    ]

    # Platform-specific flags
    if effective == "Windows":
        cmd.append("--noconsole")
        cmd.append("--icon=NONE")
    elif effective == "Darwin":
        cmd.append("--noconsole")
        cmd.append("--osx-bundle-identifier", "com.pdf2curves.app")
    else:
        cmd.append("--noconsole")

    # tkinterdnd2 is Windows-only
    if effective == "Windows":
        try:
            import tkinterdnd2
            tkdnd_dir = os.path.join(os.path.dirname(tkinterdnd2.__file__), "tkdnd")
            dnd_py = os.path.join(os.path.dirname(tkinterdnd2.__file__), "TkinterDnD.py")
            if os.path.isdir(tkdnd_dir):
                cmd.extend(["--add-data", _data_sep(tkdnd_dir, "tkinterdnd2/tkdnd", effective)])
            if os.path.isfile(dnd_py):
                cmd.extend(["--add-data", _data_sep(dnd_py, "tkinterdnd2", effective)])
        except ImportError:
            pass

    cmd.extend(["--collect-all", "customtkinter"])
    cmd.extend(["--hidden-import", "PIL._tkinter_finder"])

    if effective == "Windows":
        try:
            import tkinterdnd2
            cmd.extend(["--collect-all", "tkinterdnd2"])
        except ImportError:
            pass

    # Optionally bundle portable Ghostscript
    gs_path = os.path.join(os.path.dirname(__file__), "gs")
    if os.path.isdir(gs_path):
        print("  Bundling portable Ghostscript (gs/)...")
        cmd.extend(["--add-data", _data_sep(gs_path, "gs", effective)])
    else:
        print("  No gs/ folder found — Ghostscript not bundled.")
        print("  Run download_gs.py first to bundle it.")

    cmd.append(MAIN_SCRIPT)

    print(f"Building for {effective}...")
    subprocess.run(cmd, check=True)
    print(f"\nDone! Executable in: {DIST_DIR}/")


def _data_sep(src, dst, system=None):
    sep = ";" if (system or SYSTEM) == "Windows" else ":"
    return f"{src}{sep}{dst}"


if __name__ == "__main__":
    build()
