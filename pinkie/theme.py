"""Colors, fonts, the Qt stylesheet and the hand-drawn pixel icons."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

ASSETS = Path(__file__).resolve().parent / "assets"


class C:
    """Palette: lavender + bubblegum holographic, with cream notebook paper."""
    bg = "#f1e6ff"
    bg2 = "#ffe1f1"
    gingham = "#ffcfe3"
    gingham_dark = "#ffbcd8"
    shell = "#ff9ec7"          # bubblegum
    shell_dark = "#e77fb6"
    hot = "#e0569b"            # hot pink accents
    pink_soft = "#ffc8e4"
    lavender = "#cdb4ff"
    lav_mid = "#b79cf5"
    lav_dark = "#8f6fd8"
    plum = "#5b2b6e"           # main text
    plum_soft = "#8d5f9c"
    cream = "#fffaf0"          # notebook paper
    paper_line = "#e6dcff"
    white = "#ffffff"
    mint = "#b8f2e6"
    butter = "#fff1a8"
    star = "#ffd86b"
    screen = "#1a1322"         # black "screen" panels
    screen_edge = "#3a2a4a"
    lcd = "#efe1ff"
    vinyl = "#2b1d2a"


HEADING_FAMILY = "Pixelify Sans"
BODY_FAMILY = "VT323"


def load_fonts() -> None:
    global HEADING_FAMILY, BODY_FAMILY
    fonts = ASSETS / "fonts"
    for fname, attr in (("PixelifySans.ttf", "HEADING_FAMILY"),
                        ("VT323-Regular.ttf", "BODY_FAMILY")):
        fid = QFontDatabase.addApplicationFont(str(fonts / fname))
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams:
            globals()[attr] = fams[0]
        else:
            globals()[attr] = "Courier New"


def heading(px: int, bold: bool = False) -> QFont:
    f = QFont(HEADING_FAMILY)
    f.setPixelSize(px)
    f.setWeight(QFont.Weight.Bold if bold else QFont.Weight.Medium)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def body(px: int) -> QFont:
    f = QFont(BODY_FAMILY)
    f.setPixelSize(px)
    return f


def stylesheet() -> str:
    return f"""
    * {{ color: {C.plum}; }}
    QToolTip {{ background: {C.cream}; color: {C.plum}; border: 2px solid {C.hot};
                padding: 4px; font-family: "{BODY_FAMILY}"; font-size: 18px; }}
    QLineEdit {{ background: {C.white}; border: 3px solid {C.shell}; border-radius: 14px;
                 padding: 4px 12px; selection-background-color: {C.shell}; }}
    QLineEdit:focus {{ border-color: {C.hot}; }}
    QListView, QListWidget {{ background: transparent; border: none; outline: none; }}
    QListWidget::item {{ border-radius: 12px; padding: 4px 6px; margin: 1px 4px; }}
    QListWidget::item:hover {{ background: rgba(255,255,255,0.55); }}
    QListWidget::item:selected {{ background: {C.white}; color: {C.hot}; }}
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 4px 2px; }}
    QScrollBar::handle:vertical {{ background: {C.shell}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {C.hot}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QScrollBar:horizontal {{ height: 0; }}
    QComboBox {{ background: {C.white}; border: 3px solid {C.shell}; border-radius: 12px;
                 padding: 2px 10px; font-size: 18px; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: {C.cream}; border: 2px solid {C.hot};
                 selection-background-color: {C.shell}; selection-color: {C.white}; }}
    QPushButton {{ background: {C.white}; border: 3px solid {C.hot}; border-radius: 16px;
                   padding: 5px 16px; color: {C.hot}; font-family: "{HEADING_FAMILY}";
                   font-size: 15px; }}
    QPushButton:hover {{ background: {C.hot}; color: {C.white}; }}
    QPushButton#primary {{ background: {C.hot}; color: {C.white}; }}
    QPushButton#primary:hover {{ background: {C.shell_dark}; }}
    QDialog {{ background: {C.bg}; }}
    QLabel#hint {{ color: {C.plum_soft}; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 3px solid {C.hot};
                            border-radius: 6px; background: {C.white}; }}
    QCheckBox::indicator:checked {{ background: {C.shell}; }}
    """


# --- pixel icons --------------------------------------------------------------------
# Each icon is a little bitmap: "X" = filled pixel. Drawn crisp at any scale.
ICONS: dict[str, list[str]] = {
    "play": [
        ".XX......",
        ".XXXX....",
        ".XXXXXX..",
        ".XXXXXXX.",
        ".XXXXXXXX",
        ".XXXXXXX.",
        ".XXXXXX..",
        ".XXXX....",
        ".XX......",
    ],
    "pause": [
        ".XXX.XXX.",
        ".XXX.XXX.",
        ".XXX.XXX.",
        ".XXX.XXX.",
        ".XXX.XXX.",
        ".XXX.XXX.",
        ".XXX.XXX.",
        ".XXX.XXX.",
        ".XXX.XXX.",
    ],
    "next": [
        "X.....XX.",
        "XX....XX.",
        "XXX...XX.",
        "XXXX..XX.",
        "XXXXX.XX.",
        "XXXX..XX.",
        "XXX...XX.",
        "XX....XX.",
        "X.....XX.",
    ],
    "prev": [
        ".XX.....X",
        ".XX....XX",
        ".XX...XXX",
        ".XX..XXXX",
        ".XX.XXXXX",
        ".XX..XXXX",
        ".XX...XXX",
        ".XX....XX",
        ".XX.....X",
    ],
    "heart": [
        ".XX...XX.",
        "XXXX.XXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        "XXXXXXXXX",
        ".XXXXXXX.",
        "..XXXXX..",
        "...XXX...",
        "....X....",
    ],
    "heart_outline": [
        ".XX...XX.",
        "X..X.X..X",
        "X...X...X",
        "X.......X",
        "X.......X",
        ".X.....X.",
        "..X...X..",
        "...X.X...",
        "....X....",
    ],
    "shuffle": [
        "........X..",
        "XXX....XXX.",
        "...X..X.X..",
        "....XX.....",
        "....XX.....",
        "...X..X.X..",
        "XXX....XXX.",
        "........X..",
    ],
    "repeat": [
        "......X....",
        ".XXXXXXX...",
        "X.....X..X.",
        "X........X.",
        "X........X.",
        ".X....X..X.",
        "...XXXXXXX.",
        "......X....",
    ],
    "search": [
        "..XXX....",
        ".X...X...",
        "X.....X..",
        "X.....X..",
        "X.....X..",
        ".X...X...",
        "..XXXXX..",
        "......XX.",
        ".......XX",
    ],
    "clock": [
        "..XXXXX..",
        ".X..X..X.",
        "X...X...X",
        "X...X...X",
        "X...XXX.X",
        "X.......X",
        "X.......X",
        ".X.....X.",
        "..XXXXX..",
    ],
    "note": [
        "...XXXXXX",
        "...XXXXXX",
        "...X....X",
        "...X....X",
        "...X....X",
        ".XXX..XXX",
        "XXXX.XXXX",
        "XXXX.XXXX",
        ".XX...XX.",
    ],
    "sparkle": [
        "....X....",
        "....X....",
        "...XXX...",
        "XXXXXXXXX",
        "...XXX...",
        "....X....",
        "....X....",
    ],
    "speaker": [
        "....X....",
        "...XX..X.",
        "XXXXX...X",
        "XXXXX.X.X",
        "XXXXX.X.X",
        "XXXXX...X",
        "...XX..X.",
        "....X....",
    ],
    "close": [
        "XX...XX",
        ".XX.XX.",
        "..XXX..",
        ".XX.XX.",
        "XX...XX",
    ],
    "minus": [
        ".......",
        ".......",
        "XXXXXXX",
        "XXXXXXX",
        ".......",
    ],
    "gear": [
        "...X.X...",
        ".X.XXX.X.",
        "..XXXXX..",
        "XXX...XXX",
        ".XX...XX.",
        "XXX...XXX",
        "..XXXXX..",
        ".X.XXX.X.",
        "...X.X...",
    ],
    "candy": [
        "X....XXXX....X",
        "XX..XXooXX..XX",
        "XXXXXoXXXXXXXX",
        "XXXXXXXXXXXXXX",
        "XXXXXXXXXoXXXX",
        "XX..XXooXX..XX",
        "X....XXXX....X",
    ],
    "star": [
        "....X....",
        "...XXX...",
        "XXXXXXXXX",
        ".XXXXXXX.",
        "..XXXXX..",
        ".XXX.XXX.",
        "XX.....XX",
    ],
    "flower": [
        "...XXX...",
        "..XXXXX..",
        "XX.XXX.XX",
        "XXXoooXXX",
        ".XXoooXX.",
        "XXXoooXXX",
        "XX.XXX.XX",
        "..XXXXX..",
        "...XXX...",
    ],
    "rewind": [
        "...X...X.",
        "..XX..XX.",
        ".XXX.XXX.",
        "XXXXXXXX.",
        ".XXX.XXX.",
        "..XX..XX.",
        "...X...X.",
    ],
    "ffwd": [
        ".X...X...",
        ".XX..XX..",
        ".XXX.XXX.",
        ".XXXXXXXX",
        ".XXX.XXX.",
        ".XX..XX..",
        ".X...X...",
    ],
    "bubble": [
        ".XXXXXXXXX.",
        "XoooooooooX",
        "XooXoXoXooX",
        "XoooooooooX",
        ".XXXXXXXXX.",
        "..XX.......",
        ".X.........",
    ],
    "square": [
        "XXXXXXX",
        "X.....X",
        "X.....X",
        "X.....X",
        "XXXXXXX",
    ],
    "mini": [
        "XXXXXXXXX",
        "X.......X",
        "X.......X",
        "X...XXXXX",
        "X...XoooX",
        "XXXXXXXXX",
    ],
    "device": [
        "XXXXXXXXX",
        "X.......X",
        "X.......X",
        "X.......X",
        "XXXXXXXXX",
        "...XXX...",
        ".XXXXXXX.",
    ],
}


@lru_cache(maxsize=512)
def pixmap(name: str, color: str, px: int = 3, color2: str = "#ffffff") -> QPixmap:
    """Render a pixel icon with each bitmap pixel drawn as a px*px square."""
    grid = ICONS[name]
    w, h = max(len(r) for r in grid), len(grid)
    pm = QPixmap(w * px * 2, h * px * 2)  # 2x so it stays crisp on Retina/HiDPI
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setPen(Qt.PenStyle.NoPen)
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch in "Xo":
                p.setBrush(QColor(color if ch == "X" else color2))
                p.drawRect(QRectF(x * px, y * px, px, px))
    p.end()
    return pm


def icon(name: str, color: str = C.plum, px: int = 3) -> QIcon:
    return still_icon(pixmap(name, color, px))


def still_icon(pm: QPixmap) -> QIcon:
    """QIcon that keeps its colors when selected (Qt tints selected icons by default)."""
    ic = QIcon()
    for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active):
        ic.addPixmap(pm, mode)
    return ic


def draw_icon(p: QPainter, name: str, color: str, cx: float, cy: float, px: float,
              color2: str = "#ffffff") -> None:
    """Draw an icon centred on (cx, cy) directly with a painter (for custom widgets)."""
    grid = ICONS[name]
    w, h = max(len(r) for r in grid), len(grid)
    x0, y0 = cx - w * px / 2, cy - h * px / 2
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    c1, c2 = QColor(color), QColor(color2)
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch in "Xo":
                p.setBrush(c1 if ch == "X" else c2)
                p.drawRect(QRectF(x0 + x * px, y0 + y * px, px + 0.01, px + 0.01))
    p.restore()


EMOJI_FAMILIES = ["Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", "EmojiOne Color"]
OTTER = "\U0001F9A6"       # 🦦  (drawn by the system emoji font: Apple's otter on a Mac)
SPARKLES = "\u2728"        # ✨


def emoji_font(px: int) -> QFont:
    f = QFont()
    f.setFamilies(EMOJI_FAMILIES)
    f.setPixelSize(px)
    return f


def draw_emoji(p: QPainter, text: str, cx: float, cy: float, px: int) -> None:
    """Draw a colour emoji centred on (cx, cy)."""
    p.save()
    p.setFont(emoji_font(px))
    r = QRectF(cx - px, cy - px, px * 2, px * 2)
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
    p.restore()


def draw_outlined(p: QPainter, text: str, x: float, baseline: float, font: QFont,
                  fill: str, outline: str = "#ffffff", shadow: str | None = None,
                  width: float = 4.0) -> float:
    """Bubbly sticker text: shadow, thick outline, then fill. Returns the text width."""
    from PySide6.QtGui import QFontMetricsF, QPainterPath, QPen
    path = QPainterPath()
    path.addText(x, baseline, font, text)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if shadow:
        p.setPen(QPen(QColor(shadow), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor(shadow))
        p.drawPath(path.translated(1.5, 2.5))
    p.setPen(QPen(QColor(outline), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QColor(outline))
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(fill))
    p.drawPath(path)
    p.restore()
    return QFontMetricsF(font).horizontalAdvance(text)
