"""Track list: model + delegate that paints each row like a little sticker."""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate

from .. import theme
from ..images import ImageLoader
from ..models import Track
from ..theme import C

TrackRole = Qt.ItemDataRole.UserRole + 1
ROW_H = 50
THUMB = 34


class TrackModel(QAbstractListModel):
    def __init__(self, images: ImageLoader, parent=None):
        super().__init__(parent)
        self.tracks: list[Track] = []
        self.current_uri = ""
        self.images = images
        images.loaded.connect(self._image_ready)

    def set_tracks(self, tracks: list[Track]):
        self.beginResetModel()
        self.tracks = list(tracks)
        self.endResetModel()

    def set_current(self, uri: str):
        if uri != self.current_uri:
            self.current_uri = uri
            if self.tracks:
                self.dataChanged.emit(self.index(0), self.index(len(self.tracks) - 1))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.tracks)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        t = self.tracks[index.row()]
        if role == TrackRole:
            return t
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{t.name} - {t.artists}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{t.name}\n{t.artists}\n{t.album}"
        return None

    def _image_ready(self, url: str):
        for i, t in enumerate(self.tracks):
            if t.image_url == url:
                ix = self.index(i)
                self.dataChanged.emit(ix, ix)


class TrackDelegate(QStyledItemDelegate):
    """Notebook-paper rows: number column, little cover, title and "- artist"."""

    def __init__(self, model: TrackModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.f_title = theme.heading(14, True)
        self.f_sub = theme.body(18)
        self.f_num = theme.heading(14, True)

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_H)

    def paint(self, p: QPainter, option, index):
        t: Track = index.data(TrackRole)
        r = QRectF(option.rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        current = t.uri == self.model.current_uri
        hover = option.state & QStyle.StateFlag.State_MouseOver
        selected = option.state & QStyle.StateFlag.State_Selected
        if current or selected or hover:
            bg = QColor(C.pink_soft if current else C.lavender)
            bg.setAlpha(150 if current else (90 if selected else 55))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRect(r.adjusted(0, 0, 0, -1))
        # ruled line + number column divider, like notebook paper
        p.setPen(QPen(QColor(C.paper_line), 1.5))
        p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()))
        num_r = QRectF(r.left(), r.top(), 34, r.height())
        p.setPen(QPen(QColor("#f3b6d3"), 1.5))
        p.drawLine(QPointF(num_r.right(), r.top()), QPointF(num_r.right(), r.bottom()))
        if current:
            theme.draw_icon(p, "heart", C.hot, num_r.center().x(), num_r.center().y(), 1.9)
        else:
            p.setFont(self.f_num)
            p.setPen(QColor(C.plum))
            p.drawText(num_r, Qt.AlignmentFlag.AlignCenter, str(index.row() + 1))
        thumb = self.model.images.get(t.image_url, THUMB, 7)
        ty = r.top() + (r.height() - THUMB) / 2
        p.drawPixmap(QRectF(num_r.right() + 8, ty, THUMB, THUMB), thumb, QRectF(thumb.rect()))
        dur_r = QRectF(r.right() - 50, r.top(), 44, r.height())
        p.setFont(self.f_sub)
        p.setPen(QColor(C.plum_soft))
        p.drawText(dur_r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   t.duration_text)
        tx = num_r.right() + THUMB + 16
        tw = dur_r.left() - tx - 6
        p.setFont(self.f_title)
        p.setPen(QColor(C.hot if current else C.plum))
        title = QFontMetrics(self.f_title).elidedText(t.name, Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, r.top() + 5, tw, 20), Qt.AlignmentFlag.AlignVCenter, title)
        p.setFont(self.f_sub)
        p.setPen(QColor(C.plum_soft))
        sub = QFontMetrics(self.f_sub).elidedText(f"- {t.artists} \u2606",
                                                  Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, r.top() + 24, tw, 20), Qt.AlignmentFlag.AlignVCenter, sub)
        p.restore()


class TrackList(QListView):
    playRequested = Signal(int)

    def __init__(self, images: ImageLoader, parent=None):
        super().__init__(parent)
        self.tmodel = TrackModel(images, self)
        self.setModel(self.tmodel)
        self.setItemDelegate(TrackDelegate(self.tmodel, self))
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(18)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # `activated` covers double-click and Enter (one signal, so no double plays)
        self.activated.connect(lambda ix: self.playRequested.emit(ix.row()))
