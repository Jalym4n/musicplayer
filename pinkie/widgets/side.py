"""Left sidebar: search, library sections with sticker headers, and the otter pal."""
from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import (QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from .. import personal, theme
from ..images import ImageLoader
from ..models import Playlist
from ..theme import C
from .panels import tile_pixmap

ROLE_PL = Qt.ItemDataRole.UserRole
ROLE_HEADER = Qt.ItemDataRole.UserRole + 1
STRIP = 22  # width of the starry strip down the left edge


class SideDelegate(QStyledItemDelegate):
    def __init__(self, images: ImageLoader, parent=None):
        super().__init__(parent)
        self.images = images
        self.f_head = theme.heading(19, True)
        self.f_item = theme.heading(14, True)

    def sizeHint(self, option, index):
        return QSize(200, 40 if index.data(ROLE_HEADER) else 50)

    def paint(self, p: QPainter, option, index):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect)
        header = index.data(ROLE_HEADER)
        if header:
            theme.draw_outlined(p, header, r.left() + 8, r.bottom() - 11, self.f_head,
                                "#b08cff", C.white, shadow="#6f4fc4", width=5)
            p.restore()
            return
        pl: Playlist = index.data(ROLE_PL)
        sel = option.state & QStyle.StateFlag.State_Selected
        hover = option.state & QStyle.StateFlag.State_MouseOver
        box = r.adjusted(4, 2, -6, -2)
        if sel or hover:
            p.setPen(QPen(QColor(C.hot), 2) if sel else Qt.PenStyle.NoPen)
            bg = QColor(C.white)
            bg.setAlpha(235 if sel else 120)
            p.setBrush(bg)
            p.drawRoundedRect(box, 12, 12)
        size = 38
        icon_r = QRectF(box.left() + 6, box.center().y() - size / 2, size, size)
        if pl.kind in ("liked", "recent", "favorites"):
            pm = tile_pixmap(pl.kind, size)
        else:
            pm = self.images.get(pl.image_url, size, 8)
        p.drawPixmap(icon_r, pm, QRectF(pm.rect()))
        if pl.id in (index.data(ROLE_PL + 10) or ()):
            theme.draw_icon(p, "star", C.star, icon_r.right() - 2, icon_r.top() + 3, 1.1)
        tx = icon_r.right() + 10
        tr = QRectF(tx, box.top(), box.right() - tx - 4, box.height())
        p.setFont(self.f_item)
        p.setPen(QColor(C.hot if sel else C.plum))
        fm = QFontMetrics(self.f_item)
        # up to two lines, like little sticker labels
        words, lines, cur = pl.name.split(), [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if fm.horizontalAdvance(test) <= tr.width() or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        if len(lines) > 2:
            lines = [lines[0], fm.elidedText(" ".join(lines[1:]), Qt.TextElideMode.ElideRight,
                                             int(tr.width()))]
        lines = [fm.elidedText(ln, Qt.TextElideMode.ElideRight, int(tr.width())) for ln in lines]
        lh = fm.height()
        y0 = tr.center().y() - lh * len(lines) / 2
        for i, ln in enumerate(lines):
            p.drawText(QRectF(tr.left(), y0 + i * lh, tr.width(), lh),
                       Qt.AlignmentFlag.AlignVCenter, ln)
        p.restore()


class OtterPal(QWidget):
    """A little egg-shaped gadget with the otter inside, saying sweet notes."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self._i = random.randrange(len(personal.NOTES))
        self._t = 0
        self._hearts: list[list[float]] = []
        self.setFixedHeight(112)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("boop the otter ♡")
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(50)
        n = QTimer(self)
        n.timeout.connect(self.next_note)
        n.start(9000)

    def set_name(self, name: str):
        self.name = name
        self.update()

    @property
    def note(self) -> str:
        return personal.NOTES[self._i % len(personal.NOTES)].format(name=self.name)

    def next_note(self):
        self._i += 1
        self.update()

    def mouseReleaseEvent(self, e):
        self.next_note()
        for _ in range(5):
            self._hearts.append([46 + random.uniform(-14, 14), 56, random.uniform(-0.6, 0.6), 1.0])

    def _tick(self):
        self._t += 1
        for h in self._hearts:
            h[0] += h[2]
            h[1] -= 1.6
            h[3] -= 0.02
        self._hearts = [h for h in self._hearts if h[3] > 0]
        if self.isVisible():
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # egg gadget
        egg = QRectF(8, 14, 76, 88)
        path = QPainterPath()
        path.addEllipse(egg)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.lav_dark))
        p.drawPath(path.translated(0, 3))
        g = QLinearGradient(egg.topLeft(), egg.bottomRight())
        g.setColorAt(0, QColor("#e7dcff"))
        g.setColorAt(1, QColor("#b9e7ff"))
        p.setBrush(g)
        p.setPen(QPen(QColor(C.white), 3))
        p.drawPath(path)
        screen = QRectF(egg.left() + 15, egg.top() + 18, egg.width() - 30, 38)
        p.setPen(QPen(QColor(C.lav_dark), 2))
        p.setBrush(QColor("#f4fff6"))
        p.drawRoundedRect(screen, 8, 8)
        bob = math.sin(self._t / 6) * 2.5
        theme.draw_emoji(p, theme.OTTER, screen.center().x(), screen.center().y() + bob, 26)
        for i, col in enumerate((C.shell, C.butter, C.mint)):
            p.setBrush(QColor(col))
            p.setPen(QPen(QColor(C.lav_dark), 1.5))
            p.drawEllipse(QPointF(egg.left() + 24 + i * 14, egg.bottom() - 18), 5, 5)
        for x, y, _dx, a in self._hearts:
            c = QColor(C.hot)
            c.setAlphaF(max(0.0, a))
            theme.draw_icon(p, "heart", c.name(QColor.NameFormat.HexArgb), x, y, 1.4)
        # speech bubble
        bub = QRectF(96, 10, self.width() - 104, 72)
        tail = QPainterPath()
        tail.moveTo(bub.left() + 4, bub.bottom() - 18)
        tail.lineTo(bub.left() - 12, bub.bottom() - 4)
        tail.lineTo(bub.left() + 16, bub.bottom() - 8)
        p.setPen(QPen(QColor(C.lav_mid), 2))
        p.setBrush(QColor(C.white))
        p.drawPath(tail)
        p.drawRoundedRect(bub, 14, 14)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(QRectF(bub.left() + 1, bub.bottom() - 17, 14, 8))
        p.setFont(theme.body(19))
        p.setPen(QColor(C.plum))
        p.drawText(bub.adjusted(10, 6, -8, -6),
                   Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.note)
        p.end()


class Sidebar(QWidget):
    searchSubmitted = Signal(str)
    selected = Signal(object)          # Playlist
    favoritesChanged = Signal(list)

    def __init__(self, images: ImageLoader, name: str, favorites: list | None = None,
                 parent=None):
        super().__init__(parent)
        self.images = images
        self.favorites = list(favorites or [])
        self._playlists: list[Playlist] = []
        self.setFixedWidth(262)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(STRIP + 8, 12, 8, 8)
        lay.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("search songs...")
        self.search.addAction(theme.icon("search", C.hot, 2),
                              QLineEdit.ActionPosition.LeadingPosition)
        self.search.returnPressed.connect(
            lambda: self.search.text().strip() and self.searchSubmitted.emit(self.search.text().strip()))
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setItemDelegate(SideDelegate(images, self.list))
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.currentItemChanged.connect(self._changed)
        self.list.setStyleSheet("QListWidget::item, QListWidget::item:selected,"
                                "QListWidget::item:hover { background: transparent; }")
        lay.addWidget(self.list, 1)
        self.pal = OtterPal(name)
        lay.addWidget(self.pal)
        self._items: dict[str, QListWidgetItem] = {}
        images.loaded.connect(lambda _u: self.list.viewport().update())
        self.specials = {
            "liked": Playlist("__liked", "Liked Songs", kind="liked"),
            "recent": Playlist("__recent", "Recently Played", kind="recent"),
        }
        self.set_playlists([])

    # -- building the list --------------------------------------------------------------
    def set_playlists(self, playlists: list[Playlist]):
        self._playlists = list(playlists)
        self._rebuild()

    def _rebuild(self):
        cur = self.current()
        self.list.blockSignals(True)
        self.list.clear()
        self._items.clear()
        self._header("MY LIBRARY")
        self._add(self.specials["liked"])
        self._header("DISCOVER")
        self._add(self.specials["recent"])
        favs = [pl for pl in self._playlists if pl.id in self.favorites]
        if favs:
            self._header("FAVORITES")
            for pl in favs:
                self._add(pl, key=f"fav:{pl.id}")
        if self._playlists:
            self._header("PLAYLISTS")
            for pl in self._playlists:
                self._add(pl)
        if cur:
            self.select_id(cur.id)
        self.list.blockSignals(False)

    def _header(self, text: str):
        it = QListWidgetItem()
        it.setData(ROLE_HEADER, text)
        it.setFlags(Qt.ItemFlag.NoItemFlags)
        self.list.addItem(it)

    def _add(self, pl: Playlist, key: str | None = None):
        it = QListWidgetItem(pl.name)
        it.setData(ROLE_PL, pl)
        it.setData(ROLE_PL + 10, tuple(self.favorites))
        tip = pl.name + (f"\nby {pl.owner}" if pl.owner else "")
        if pl.total:
            tip += f"\n{pl.total} songs"
        if pl.kind == "playlist":
            tip += "\n(right-click to favorite ☆)"
        it.setToolTip(tip)
        self.list.addItem(it)
        self._items.setdefault(pl.id, it)
        if key:
            self._items[key] = it

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        pl = it.data(ROLE_PL) if it else None
        if not pl or pl.kind != "playlist":
            return
        m = QMenu(self)
        fav = pl.id in self.favorites
        act = m.addAction("remove from favorites" if fav else "☆ add to favorites")
        if m.exec(self.list.viewport().mapToGlobal(pos)) == act:
            if fav:
                self.favorites.remove(pl.id)
            else:
                self.favorites.append(pl.id)
            self.favoritesChanged.emit(list(self.favorites))
            self._rebuild()

    def _changed(self, cur, _prev):
        if cur and cur.data(ROLE_PL):
            self.selected.emit(cur.data(ROLE_PL))

    def current(self) -> Playlist | None:
        it = self.list.currentItem()
        return it.data(ROLE_PL) if it else None

    def select_id(self, pid: str):
        it = self._items.get(pid)
        if it:
            self.list.setCurrentItem(it)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#ffd6ec"))
        g.setColorAt(1, QColor("#f3d9ff"))
        p.setPen(QPen(QColor(C.white), 3))
        p.setBrush(g)
        p.drawRoundedRect(r, 18, 18)
        # starry strip down the left edge
        strip = QRectF(r.left() + 5, r.top() + 8, STRIP - 4, r.height() - 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 110))
        p.drawRoundedRect(strip, 8, 8)
        cols = [C.star, C.white, C.shell, C.lav_mid]
        y, i = strip.top() + 14, 0
        while y < strip.bottom() - 6:
            name = "star" if i % 3 != 1 else "sparkle"
            theme.draw_icon(p, name, cols[i % 4], strip.center().x(), y, 1.2)
            y += 26
            i += 1
        p.setPen(QPen(QColor(C.lav_mid), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 20, 20)
        p.end()
