"""Build a standalone, double-clickable app with PyInstaller.

    python scripts/build.py

Output:
  Windows -> dist/Aayusha's Music Player/Aayusha's Music Player.exe
  macOS   -> dist/Aayusha's Music Player.app
  Linux   -> dist/Aayusha's Music Player/Aayusha's Music Player

Build on the OS you want to run it on (PyInstaller does not cross-compile).
The built-in speaker (librespot) is compiled first if pinkie/bin/ doesn't have it.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_BUNDLE = "Aayusha's Music Player"   # name of the .app / .exe
ASSETS = ROOT / "pinkie" / "assets"


def make_icons() -> Path:
    """Render the heart app icon to PNG (+ ICO on Windows) using Qt itself."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT))
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    from pinkie.app import app_icon
    ic = app_icon()
    png = ASSETS / "icon.png"
    ic.pixmap(256, 256).save(str(png))
    if sys.platform == "win32":
        ico = ASSETS / "icon.ico"
        ic.pixmap(256, 256).save(str(ico))
        return ico
    return png  # PyInstaller turns a PNG into .icns on macOS if Pillow is installed


def speaker_binary() -> Path | None:
    exe = "librespot.exe" if sys.platform == "win32" else "librespot"
    path = ROOT / "pinkie" / "bin" / exe
    if not path.is_file():
        print("Building the built-in speaker first (scripts/build_librespot.py)...")
        if subprocess.call([sys.executable, str(ROOT / "scripts" / "build_librespot.py")]) != 0:
            return None
    return path if path.is_file() else None


def main() -> int:
    speaker = speaker_binary()
    if speaker is None:
        print("Can't build the app without the built-in speaker. See messages above.")
        return 1
    icon = make_icons()
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", APP_BUNDLE,
        "--icon", str(icon),
        "--add-data", f"{ASSETS}{sep}pinkie/assets",
        "--add-binary", f"{speaker}{sep}librespot",
        # keep the bundle lean: nothing web-engine or QML related is ever loaded
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "tkinter",
        str(ROOT / "run.py"),
    ]
    if sys.platform == "darwin":
        cmd[3:3] = ["--osx-bundle-identifier", "app.pinkie.aayusha"]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
