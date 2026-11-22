"""Track list: model + delegate that paints each row like a little sticker."""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate

from .. import theme
from ..images import ImageLoader
from ..models import Track
from ..theme import C

TrackRole = Qt.ItemDataRole.UserRole + 1
ROW_H = 54
THUMB = 40


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
    def __init__(self, model: TrackModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.f_title = theme.heading(15)
        self.f_sub = theme.body(19)

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), ROW_H)

    def paint(self, p: QPainter, option, index):
        t: Track = index.data(TrackRole)
        r = QRectF(option.rect).adjusted(4, 3, -8, -3)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        current = t.uri == self.model.current_uri
        hover = option.state & QStyle.StateFlag.State_MouseOver
        selected = option.state & QStyle.StateFlag.State_Selected
        if current or selected or hover:
            bg = QColor(C.white)
            if not (current or selected):
                bg.setAlpha(140)
            p.setPen(QPen(QColor(C.hot), 2) if current else Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, 14, 14)
        # index number or a heart for the playing song
        num_r = QRectF(r.left() + 4, r.top(), 30, r.height())
        if current:
            theme.draw_icon(p, "heart", C.hot, num_r.center().x(), num_r.center().y(), 2.2)
        else:
            p.setFont(self.f_sub)
            p.setPen(QColor(C.plum_soft))
            p.drawText(num_r, Qt.AlignmentFlag.AlignCenter, str(index.row() + 1))
        # thumbnail
        thumb = self.model.images.get(t.image_url, THUMB, 8)
        ty = r.top() + (r.height() - THUMB) / 2
        p.drawPixmap(QRectF(num_r.right() + 4, ty, THUMB, THUMB), thumb, QRectF(thumb.rect()))
        # duration
        dur_r = QRectF(r.right() - 58, r.top(), 50, r.height())
        p.setFont(self.f_sub)
        p.setPen(QColor(C.plum_soft))
        p.drawText(dur_r, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   t.duration_text)
        # text
        tx = num_r.right() + THUMB + 16
        tw = dur_r.left() - tx - 10
        p.setFont(self.f_title)
        p.setPen(QColor(C.hot if current else C.plum))
        title = QFontMetrics(self.f_title).elidedText(t.name, Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, r.top() + 5, tw, 22), Qt.AlignmentFlag.AlignVCenter, title)
        p.setFont(self.f_sub)
        p.setPen(QColor(C.plum_soft))
        sub = f"{t.artists}  ·  {t.album}" if t.album else t.artists
        sub = QFontMetrics(self.f_sub).elidedText(sub, Qt.TextElideMode.ElideRight, int(tw))
        p.drawText(QRectF(tx, r.top() + 25, tw, 20), Qt.AlignmentFlag.AlignVCenter, sub)
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
