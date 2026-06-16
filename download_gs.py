#!/usr/bin/env python3
"""
Downloads a portable Ghostscript and places it next to the app.

Windows: Downloads the InnoSetup installer and extracts it using a
         self-contained method (7za from NuGet → 7-Zip NSIS installer → GS).
Linux/macOS: Downloads the source tarball (no pre-built binary available
             from Artifex; use your package manager instead).

Usage:
    python download_gs.py            # Windows (default)
    python download_gs.py --linux    # Linux (download source)
    python download_gs.py --macos    # macOS (download source)
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile


GS_VERSION = "10.07.1"
GS_VERSION_TAG = GS_VERSION.replace(".", "")
VERSION_DIR = f"gs{GS_VERSION_TAG}"

INSTALLER_URL = (
    f"https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/"
    f"gs{GS_VERSION_TAG}/gs{GS_VERSION_TAG}w64.exe"
)
SEVEN_ZIP_NUGET = "https://www.nuget.org/api/v2/package/7-Zip.CommandLine/25.1.0"
SEVEN_ZIP_INSTALLER = "https://github.com/ip7z/7zip/releases/download/26.01/7z2601-x64.exe"

TARBALL_URL = (
    f"https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/"
    f"gs{GS_VERSION_TAG}/ghostpdl-{GS_VERSION}.tar.gz"
)


def get_dest():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def download_file(url, description="Downloading"):
    print(f"  {description}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        total = int(resp.headers.get("Content-Length", 0) or 0)
        data = bytearray()
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            data.extend(chunk)
            if total:
                pct = len(data) / total * 100
                print(f"\r    {len(data)//1024//1024} / {total//1024//1024} MB ({pct:.0f}%)", end="")
    print()
    return bytes(data)


def extract_windows(exe_data, gs_dest):
    os.makedirs(gs_dest, exist_ok=True)
    tmp = tempfile.mkdtemp()
    tmp_exe = os.path.join(tmp, "gs_installer.exe")
    try:
        with open(tmp_exe, "wb") as f:
            f.write(exe_data)

        # 1. Get 7za.exe from NuGet package
        print("  Step 1/4: Downloading 7za.exe...")
        nuget_data = download_file(SEVEN_ZIP_NUGET, "Downloading 7za from NuGet")
        with zipfile.ZipFile(io.BytesIO(nuget_data)) as zf:
            for name in zf.namelist():
                if name.endswith("7za.exe"):
                    zf.extract(name, tmp)
                    seven_za = os.path.join(tmp, name)
                    break
            else:
                print("  ERROR: 7za.exe not found in NuGet package")
                return False

        # 2. Download 7-Zip NSIS installer
        print("  Step 2/4: Downloading 7-Zip installer...")
        seven_data = download_file(SEVEN_ZIP_INSTALLER, "Downloading 7-Zip")
        seven_exe = os.path.join(tmp, "7z_installer.exe")
        with open(seven_exe, "wb") as f:
            f.write(seven_data)

        # 3. Extract 7-Zip installer with 7za (NSIS format)
        print("  Step 3/4: Extracting 7-Zip...")
        seven_dir = os.path.join(tmp, "7z_out")
        os.makedirs(seven_dir, exist_ok=True)
        subprocess.run([seven_za, "x", seven_exe, f"-o{seven_dir}", "-y"],
                       capture_output=True, timeout=60, check=True)
        seven_z = os.path.join(seven_dir, "7z.exe")
        assert os.path.exists(seven_z), "7z.exe not found after extraction"

        # 4. Extract GS installer with full 7z (InnoSetup)
        print("  Step 4/4: Extracting Ghostscript...")
        gs_tmp = os.path.join(tmp, "gs_out")
        os.makedirs(gs_tmp, exist_ok=True)
        subprocess.run([seven_z, "x", tmp_exe, f"-o{gs_tmp}", "-y"],
                       capture_output=True, timeout=120, check=True)

        items = os.listdir(gs_tmp)
        gs_subdirs = [d for d in items
                      if d.startswith("gs") and os.path.isdir(os.path.join(gs_tmp, d))]
        src_dir = os.path.join(gs_tmp, gs_subdirs[0]) if gs_subdirs else gs_tmp
        shutil.copytree(src_dir, gs_dest, dirs_exist_ok=True)

        # Clean installer junk
        for f in ["$PLUGINSDIR", "uninstgs.exe.nsis", "vcredist_x64.exe",
                   "EnVar.dll", "modern-wizard.bmp", "nsDialogs.dll",
                   "nsExec.dll", "System.dll"]:
            p = os.path.join(gs_dest, f)
            if os.path.isfile(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)

        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def download_windows():
    dest = get_dest()
    gs_dest = os.path.join(dest, "gs", VERSION_DIR)
    if os.path.isdir(gs_dest):
        print(f"  ✓ gs/{VERSION_DIR} already exists at: {gs_dest}")
        return True
    print(f"Downloading Ghostscript {GS_VERSION} for Windows...")
    data = download_file(INSTALLER_URL, "Downloading GS installer")
    print("  Extracting...")
    success = extract_windows(data, gs_dest)
    if success:
        print(f"  ✓ Ghostscript {GS_VERSION} → {gs_dest}")
    else:
        print("  ✗ Extraction failed")
    return success


def download_unix():
    dest = get_dest()
    gs_dest = os.path.join(dest, "gs", VERSION_DIR)
    if os.path.isdir(gs_dest):
        print(f"  ✓ gs/{VERSION_DIR} already exists at: {gs_dest}")
        return True
    print(f"Downloading Ghostscript {GS_VERSION} source tarball...")
    print("  NOTE: No pre-built binary available for Linux/macOS from Artifex.")
    print("  Recommend installing via package manager instead:")
    if sys.platform == "darwin":
        print("    brew install ghostscript")
    else:
        print("    sudo apt install ghostscript   # Debian/Ubuntu")
        print("    sudo dnf install ghostscript   # Fedora")
    print(f"\n  Downloading source to gs/{VERSION_DIR} as reference...")
    data = download_file(TARBALL_URL, "Downloading source tarball")
    os.makedirs(gs_dest, exist_ok=True)
    tarball_path = os.path.join(gs_dest, f"ghostpdl-{GS_VERSION}.tar.gz")
    with open(tarball_path, "wb") as f:
        f.write(data)
    print(f"  ✓ Source saved to: {tarball_path}")
    print("  ⚠  gs binary not bundled — app will use system-installed Ghostscript.")
    return True


def main():
    import platform as _platform
    system = _platform.system()
    if "--linux" in sys.argv or system == "Linux":
        download_unix()
    elif "--macos" in sys.argv or system == "Darwin":
        download_unix()
    else:
        download_windows()


if __name__ == "__main__":
    main()
