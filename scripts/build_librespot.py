"""Compile the built-in speaker (librespot) and drop it into pinkie/bin/.

    python scripts/build_librespot.py

Needs Rust (https://rustup.rs). Takes a few minutes the first time. You only need this
when running from source: the downloadable app already has the speaker inside.

Linux also needs ALSA headers:  sudo apt install libasound2-dev pkg-config
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

LIBRESPOT_VERSION = "0.8.0"
# No mDNS discovery (only your account should see the speaker), pure-Rust TLS so there's
# no OpenSSL dependency, and the cross-platform rodio audio output
# (CoreAudio on macOS, WASAPI on Windows, ALSA on Linux).
FEATURES = "rodio-backend,rustls-tls-webpki-roots"

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "pinkie" / "bin"
EXE = "librespot.exe" if sys.platform == "win32" else "librespot"


def main() -> int:
    cargo = shutil.which("cargo") or str(Path.home() / ".cargo" / "bin" / "cargo")
    if not Path(cargo).exists() and not shutil.which("cargo"):
        print("Rust isn't installed. Get it from https://rustup.rs and run this again.")
        return 1
    install_root = ROOT / "build" / "librespot-root"
    cmd = [cargo, "install", "librespot", "--version", LIBRESPOT_VERSION, "--locked",
           "--no-default-features", "--features", FEATURES, "--root", str(install_root)]
    print(" ".join(cmd), flush=True)
    rc = subprocess.call(cmd)
    if rc != 0:
        if sys.platform.startswith("linux"):
            print("\nOn Linux, install ALSA headers first: sudo apt install libasound2-dev pkg-config")
        return rc
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    built = install_root / "bin" / EXE
    shutil.copy2(built, OUT_DIR / EXE)
    print(f"\nBuilt-in speaker ready: {OUT_DIR / EXE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
