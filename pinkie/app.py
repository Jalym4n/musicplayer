"""Entry point: ``python -m pinkie`` (add ``--demo`` to preview without Spotify)."""
from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from . import config, theme


def app_icon() -> QIcon:
    ic = QIcon()
    for size in (16, 32, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(theme.C.shell))
        p.setPen(QColor(theme.C.hot))
        p.drawRoundedRect(1, 1, size - 2, size - 2, size * .22, size * .22)
        theme.draw_icon(p, "heart", theme.C.white, size / 2, size / 2 + size * .02, size / 13)
        p.end()
        ic.addPixmap(pm)
    return ic


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pinkie", description="Pinkie Player")
    ap.add_argument("--demo", action="store_true", help="preview with fake music, no login")
    ap.add_argument("--screenshot", metavar="PNG", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    app = QApplication(sys.argv[:1])
    app.setApplicationName(config.APP_NAME)
    app.setOrganizationName("Pinkie")
    app.setWindowIcon(app_icon())
    theme.load_fonts()
    app.setFont(theme.body(20))
    app.setStyleSheet(theme.stylesheet())

    from .main_window import MainWindow
    win = MainWindow(config.Settings.load(), demo=args.demo)
    win.show()
    if not win.start():
        return 0

    if args.screenshot:  # used for automated visual checks
        def shoot():
            win.grab().save(args.screenshot)
            app.quit()
        if args.demo:
            QTimer.singleShot(400, lambda: win.play_row(2))
        QTimer.singleShot(3000, shoot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
