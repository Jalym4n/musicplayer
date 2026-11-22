"""Launcher used by PyInstaller and for double-click runs: python run.py [--demo]"""
from pinkie.app import main

if __name__ == "__main__":
    raise SystemExit(main())
