"""
ui/popup_card.py  --  a pop-up card drawn over the clock page (setup instructions, shutdown question).

One widget, painted like the other cards (dark maroon, gold edge), big text, optional countdown bar:

    +--------------------------------------+
    |        वाई-फ़ाई / स्थान सेटअप          |   title
    | 1. मोबाइल में Wi-Fi खोलें और जुड़ें:   |   numbered steps, wrapped
    |    VedicGhadi-Setup                   |   key words (names, addresses) in bold gold
    | ...                                   |
    | सेटअप 8 सेकंड में शुरू होगा ...        |   footer
    | ======================-------         |   countdown bar (shrinks)
    +--------------------------------------+

It never takes touches (WA_TransparentForMouseEvents): the three buttons below stay usable.
All text uses font-independent line heights (info_panels.LINE_H), like the panels and cards.
Placed by ui/main_window_hi.py (OverlayPlacer), centred in the area above the touch buttons.
"""
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QFontMetrics
from PyQt5.QtWidgets import QWidget

from info_panels import C_PANEL_EDGE, C_VALUE, C_CAPTION, LINE_H, ASCENT, fit_font

WIDTH = 456
PAD = 16
NUM_W = 26                       # width of the "1." column of a numbered step
C_FILL = QColor(46, 12, 6, 240)
C_GOLD = QColor("#f6b730")
C_RED = QColor("#ff5a45")
C_SOFT = QColor("#f3dcae")
TITLE_PX, BODY_PX, KEY_PX, FOOT_PX = 24, 18, 20, 16
BAR_H = 8


def _font(family, px, bold=False):
    f = QFont(family)
    f.setPixelSize(int(px))
    f.setBold(bold)
    return f


def wrap_words(font, text, max_w):
    """Greedy word wrap by measured width -> list of lines."""
    fm = QFontMetrics(font)
    lines, cur = [], ""
    for word in text.split(" "):
        trial = word if not cur else cur + " " + word
        if not cur or fm.horizontalAdvance(trial) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class PopupCard(QWidget):
    def __init__(self, font_family="Noto Sans Devanagari", parent=None):
        super().__init__(parent)
        self.font_family = font_family
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.title = ""
        self.steps = []              # (number or "", text, key)   key = bold gold line under the text
        self.footer = ""
        self.progress = None         # None = no bar, else 1.0 .. 0.0
        self.accent = C_GOLD
        self.center = False          # True: every line centred (the shutdown question)
        self.kind = ""               # "setup" | "shutdown" | "" (what is shown now)
        self.reserve_bottom = 0      # px at the bottom that must stay free (the touch buttons)
        self._ops = []
        self.hide()

    # ------------------------------------------------------------------ content
    def show_card(self, kind, title, steps, footer="", progress=None, accent=None, center=False):
        self.kind = kind
        self.center = center
        self.title, self.steps, self.footer = title, list(steps), footer
        self.progress = progress
        self.accent = accent or C_GOLD
        self._build()
        self._place()
        self.show()
        self.raise_()
        self.update()

    def set_progress(self, progress, footer=None):
        changed = False
        if progress != self.progress:
            self.progress, changed = progress, True
        if footer is not None and footer != self.footer:
            self.footer, changed = footer, True
            self._build()
            self._place()
        if changed:
            self.update()

    def close_card(self):
        self.kind = ""
        self.hide()

    # ------------------------------------------------------------------ layout
    def _build(self):
        """Wrap everything and compute the height.  Fills self._ops with draw instructions."""
        fam = self.font_family
        inner = WIDTH - 2 * PAD
        ops, y = [], PAD
        tf = fit_font(_font(fam, TITLE_PX, True), self.title, inner)
        ops.append(("center", tf, self.accent, y, self.title))
        y += tf.pixelSize() * LINE_H + 10
        bf, kf = _font(fam, BODY_PX), _font(fam, KEY_PX, True)
        for num, text, key in self.steps:
            x = PAD + (NUM_W if num else 0)
            width = inner - (NUM_W if num else 0)
            lines = wrap_words(bf, text, width) if text else []
            first = True
            for line in lines:
                if first and num:
                    ops.append(("left", _font(fam, BODY_PX, True), self.accent, PAD, y, num + "."))
                first = False
                if self.center:
                    ops.append(("center", bf, C_VALUE, y, line))
                else:
                    ops.append(("left", bf, C_VALUE, x, y, line))
                y += BODY_PX * LINE_H
            if key:
                kfit = fit_font(kf, key, width)
                if self.center:
                    ops.append(("center", kfit, C_GOLD, y, key))
                else:
                    ops.append(("left", kfit, C_GOLD, x, y, key))
                y += kfit.pixelSize() * LINE_H
            y += 6
        if self.footer:
            y += 2
            ff = _font(fam, FOOT_PX)
            for line in wrap_words(ff, self.footer, inner):
                ops.append(("center", ff, C_SOFT, y, line))
                y += FOOT_PX * LINE_H
        if self.progress is not None:
            y += 6
            ops.append(("bar", y))
            y += BAR_H
        self._ops = ops
        self._height = int(y + PAD)

    def _place(self):
        p = self.parentWidget()
        if p is None:
            return
        avail_h = p.height() - self.reserve_bottom
        self.setGeometry(int((p.width() - WIDTH) / 2), int(max(6, (avail_h - self._height) / 2)),
                         WIDTH, self._height)

    def reposition(self):
        if self._ops:
            self._place()

    # ------------------------------------------------------------------ painting
    def paintEvent(self, event):
        if not self._ops:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        p.setBrush(C_FILL)
        p.setPen(QPen(self.accent, 3))
        p.drawRoundedRect(QRectF(1.5, 1.5, w - 3, h - 3), 18, 18)
        for op in self._ops:
            kind = op[0]
            if kind == "center":
                _k, font, colour, y, text = op
                p.setFont(font)
                p.setPen(colour)
                tw = QFontMetrics(font).horizontalAdvance(text)
                p.drawText(QPointF((w - tw) / 2.0, y + ASCENT * font.pixelSize()), text)
            elif kind == "left":
                _k, font, colour, x, y, text = op
                p.setFont(font)
                p.setPen(colour)
                p.drawText(QPointF(x, y + ASCENT * font.pixelSize()), text)
            elif kind == "bar":
                y = op[1]
                full = QRectF(PAD, y, w - 2 * PAD, BAR_H)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 40))
                p.drawRoundedRect(full, BAR_H / 2.0, BAR_H / 2.0)
                if self.progress and self.progress > 0:
                    p.setBrush(self.accent)
                    p.drawRoundedRect(QRectF(PAD, y, (w - 2 * PAD) * min(1.0, self.progress), BAR_H),
                                      BAR_H / 2.0, BAR_H / 2.0)
        p.end()
