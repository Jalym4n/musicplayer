"""Build a standalone, double-clickable app with PyInstaller.

    python scripts/build.py

Output:
  Windows -> dist/Pinkie Player/Pinkie Player.exe
  macOS   -> dist/Pinkie Player.app
  Linux   -> dist/Pinkie Player/Pinkie Player

Build on the OS you want to run it on (PyInstaller does not cross-compile).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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


def main() -> int:
    icon = make_icons()
    sep = ";" if sys.platform == "win32" else ":"
    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "Pinkie Player",
        "--icon", str(icon),
        "--add-data", f"{ASSETS}{sep}pinkie/assets",
        # keep the bundle lean: nothing web-engine or QML related is ever loaded
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "tkinter",
        str(ROOT / "run.py"),
    ]
    if sys.platform == "darwin":
        cmd[3:3] = ["--osx-bundle-identifier", "app.pinkie.player"]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
