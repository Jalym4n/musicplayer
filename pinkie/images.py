"""Album cover loading with memory + disk caching (Qt networking, no browser)."""
from __future__ import annotations

import random

from PySide6.QtCore import QObject, QRectF, QUrl, Qt, Signal
from PySide6.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPainterPath,
                           QPixmap)
from PySide6.QtNetwork import (QNetworkAccessManager, QNetworkDiskCache,
                               QNetworkReply, QNetworkRequest)

from . import config
from .theme import C, draw_icon

_DEMO_PAIRS = [("#ffb3d1", "#cdb4ff"), ("#ffd1dc", "#fff1a8"), ("#b8f2e6", "#ffb3d1"),
               ("#cdb4ff", "#ffe3ef"), ("#ff9ec7", "#ffd6a5"), ("#a0e7e5", "#cdb4ff"),
               ("#fbc4ab", "#ff9ec7"), ("#e0569b", "#ffb3d1")]


def demo_cover(seed: int, size: int = 300) -> QPixmap:
    rnd = random.Random(seed)
    a, b = rnd.choice(_DEMO_PAIRS)
    pm = QPixmap(size, size)
    p = QPainter(pm)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(a))
    g.setColorAt(1, QColor(b))
    p.fillRect(pm.rect(), g)
    # sprinkle of little pixel motifs, then one big one in the middle
    motifs = ["heart", "sparkle", "note", "heart_outline"]
    for _ in range(9):
        draw_icon(p, rnd.choice(motifs), "#aaffffff" if rnd.random() < .5 else C.cream,
                  rnd.uniform(0.1, 0.9) * size, rnd.uniform(0.1, 0.9) * size,
                  size / rnd.choice((60, 75, 90)))
    draw_icon(p, rnd.choice(["heart", "note", "sparkle"]), C.white,
              size / 2, size / 2, size / 18)
    p.end()
    return pm


def rounded(src: QPixmap, size: int, radius: float) -> QPixmap:
    """Center-crop to a square, scale to `size` and clip to a rounded rect."""
    dpr = 2.0
    out = QPixmap(int(size * dpr), int(size * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    if src.isNull():
        return out
    side = min(src.width(), src.height())
    sq = src.copy((src.width() - side) // 2, (src.height() - side) // 2, side, side)
    sq = sq.scaled(int(size * dpr), int(size * dpr), Qt.AspectRatioMode.IgnoreAspectRatio,
                   Qt.TransformationMode.SmoothTransformation)
    sq.setDevicePixelRatio(dpr)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, sq)
    p.end()
    return out


def placeholder(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor(C.cream))
    p = QPainter(pm)
    draw_icon(p, "note", C.shell, size / 2, size / 2, max(1, size / 22))
    p.end()
    return pm


class ImageLoader(QObject):
    loaded = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.net = QNetworkAccessManager(self)
        disk = QNetworkDiskCache(self)
        disk.setCacheDirectory(str(config.cache_dir() / "covers"))
        disk.setMaximumCacheSize(200 * 1024 * 1024)
        self.net.setCache(disk)
        self._raw: dict[str, QPixmap] = {}
        self._sized: dict[tuple[str, int, int], QPixmap] = {}
        self._pending: set[str] = set()

    def raw(self, url: str) -> QPixmap | None:
        if not url:
            return None
        if url in self._raw:
            return self._raw[url]
        if url.startswith("demo:"):
            pm = demo_cover(int(url[5:]))
            self._raw[url] = pm
            return pm
        if url not in self._pending:
            self._pending.add(url)
            req = QNetworkRequest(QUrl(url))
            req.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                             QNetworkRequest.CacheLoadControl.PreferCache)
            reply = self.net.get(req)
            reply.finished.connect(lambda r=reply, u=url: self._done(r, u))
        return None

    def get(self, url: str, size: int, radius: int = 10) -> QPixmap:
        """Return a rounded cover at `size`, or a placeholder while it downloads."""
        key = (url, size, radius)
        if key in self._sized:
            return self._sized[key]
        src = self.raw(url)
        if src is None:
            return rounded(placeholder(size * 2), size, radius)
        pm = rounded(src, size, radius)
        self._sized[key] = pm
        if len(self._sized) > 1500:
            self._sized.clear()
        return pm

    def _done(self, reply: QNetworkReply, url: str):
        self._pending.discard(url)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            img = QImage.fromData(reply.readAll())
            if not img.isNull():
                self._raw[url] = QPixmap.fromImage(img)
                self.loaded.emit(url)
        reply.deleteLater()

