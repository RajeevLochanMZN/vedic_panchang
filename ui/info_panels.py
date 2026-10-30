"""
ui/info_panels.py  --  the side panels and the bottom banner of the dial page.

Both widgets are PAINTED directly (no child labels), which is light on a Pi and
lets every font size scale with the widget's own height, so the same code looks
right on 1024x600, 1920x1080 and a 4K / 100-inch screen.

InfoPanel   a glass-like rounded panel with rows.  A row has 1 or 2 cells, and
            each cell is a small gold caption over a big cream value, with an
            OPTIONAL third item: a small detail line under the value.
                rows = [ [("सूर्योदय", "06:29"), ("सूर्यास्त", "17:52")],
                         [("तिथि", "द्वितीया", "तक 18:42")] ]
BannerBar   a dark banner with a big first line and a smaller second line.
            The second line is a list of parts in priority order; parts that
            do not fit are dropped from the end instead of shrinking the text
            too small.
"""
import os
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics, QLinearGradient, QPixmap
from PyQt5.QtWidgets import QWidget

SWASTIK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "data", "images", "swastik.png")

C_PANEL_BG   = QColor(58, 16, 6, 170)       # dark maroon, see-through
C_PANEL_EDGE = QColor("#e8b84a")
C_CAPTION    = QColor("#f0b323")            # gold
C_VALUE      = QColor("#fff4dc")            # cream
C_RULE       = QColor(232, 184, 74, 110)    # thin separator lines


def fit_font(font, text, max_px):
    """Shrink `font` until `text` is at most max_px pixels wide."""
    f = QFont(font)
    while f.pixelSize() > 6 and QFontMetrics(f).horizontalAdvance(text) > max_px:
        f.setPixelSize(f.pixelSize() - 1)
    return f


# FONT-INDEPENDENT LINE METRICS.  Different fonts report different line heights
# (ascent + descent), which made the spacing between caption / value / detail
# differ from one PC to another.  So spacing is computed from the pixel size only:
# a line box is LINE_H * px tall and its baseline sits ASCENT * px below its top.
LINE_H = 1.30
ASCENT = 1.00


def draw_line(p, font, color, x0, width, top, text):
    """Draw `text` centred horizontally in [x0, x0+width] with its BASELINE at
    top + ASCENT * pixel size, so the spacing never depends on the font."""
    p.setFont(font)
    p.setPen(color)
    tw = QFontMetrics(font).horizontalAdvance(text)
    p.drawText(QPointF(x0 + (width - tw) / 2.0, top + ASCENT * font.pixelSize()), text)


def _font(family, px, bold=False):
    f = QFont(family)
    f.setPixelSize(max(6, int(px)))
    f.setBold(bold)
    return f


class InfoPanel(QWidget):
    def __init__(self, font_family="Noto Sans Devanagari", parent=None):
        super().__init__(parent)
        self.font_family = font_family
        self.rows = []
        self.weights = None
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_rows(self, rows, weights=None):
        """rows: list of rows; each row is a list of 1 or 2 cells
        (caption, value[, detail]).  An EMPTY caption makes a compact one-line row.
        weights: optional relative height of each row.  Give the SAME weights to
        the left and right panel and their separator lines line up exactly."""
        if rows != self.rows or weights != self.weights:
            self.rows = rows
            self.weights = weights
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        n = max(1, len(self.rows))
        pad = h * 0.02
        radius = min(w, h) * 0.05

        # panel body
        p.setBrush(C_PANEL_BG)
        p.setPen(QPen(C_PANEL_EDGE, max(1.5, h * 0.003)))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), radius, radius)

        # Row heights are weighted: rows with a detail line get more room,
        # single-value rows (clock, date, ayana, samvatsara) a little less.
        if self.weights and len(self.weights) == len(self.rows):
            weights = list(self.weights)
        else:
            weights = []
            for cells in self.rows:
                if any(len(c) > 2 for c in cells):
                    weights.append(1.15)
                elif len(cells) == 1:
                    weights.append(0.90)
                else:
                    weights.append(1.0)
        unit = (h - 2 * pad) / max(0.001, sum(weights))
        y_cursor = pad
        for i, cells in enumerate(self.rows):
            row_h = unit * weights[i]
            y0 = y_cursor
            y_cursor += row_h
            cell_w = (w - 2 * pad) / max(1, len(cells))

            # horizontal rule between rows
            if i > 0:
                p.setPen(QPen(C_RULE, max(1.0, h * 0.002)))
                p.drawLine(int(pad * 2), int(y0), int(w - pad * 2), int(y0))

            for k, cell in enumerate(cells):
                caption, value = cell[0], cell[1]
                detail = cell[2] if len(cell) > 2 else ""
                x0 = pad + k * cell_w
                # vertical rule between the two cells of a row
                if k > 0:
                    p.setPen(QPen(C_RULE, max(1.0, h * 0.002)))
                    p.drawLine(int(x0), int(y0 + row_h * 0.18),
                               int(x0), int(y0 + row_h * 0.82))
                text_w = cell_w * 0.90

                # BIG VALUE: its size is based on the PANEL height (not the row
                # height), so adding rows does not shrink it.
                if not caption:
                    val_px0 = h * 0.046          # compact one-line row (city, ritu)
                else:
                    val_px0 = h * (0.055 if (detail or len(cells) == 2) else 0.048)
                # Captions must stay readable: never below ~56% of the value size.
                cap_min = max(9.0, val_px0 * 0.56)
                cap_px = max(cap_min, row_h * 0.20)
                det_px = max(cap_min * 0.92, row_h * 0.19)
                val_px = val_px0
                gap = row_h * 0.01
                while True:
                    vf = fit_font(_font(self.font_family, val_px, True), value, text_w)
                    hv = vf.pixelSize() * LINE_H
                    cf = fit_font(_font(self.font_family, cap_px), caption, text_w)
                    hc = cf.pixelSize() * LINE_H if caption else 0
                    df, hd = None, 0
                    if detail:
                        df = fit_font(_font(self.font_family, det_px), detail, text_w)
                        hd = df.pixelSize() * LINE_H
                    total = hc + hv + hd + gap * ((1 if caption else 0) + (1 if detail else 0))
                    if total <= row_h * 0.90:
                        break
                    # 1st: shrink caption/detail, but only down to their minimum
                    if cap_px > cap_min:
                        cap_px -= 1
                        det_px = max(cap_min * 0.92, det_px - 1)
                    # 2nd (last resort): shrink the big value, at most to 85%
                    elif val_px > val_px0 * 0.85:
                        val_px -= 1
                    else:
                        break

                top = y0 + (row_h - total) / 2.0          # centre the stack in the row
                y_val = top
                if caption:
                    draw_line(p, cf, C_CAPTION, x0, cell_w, top, caption)
                    y_val = top + hc + gap
                draw_line(p, vf, C_VALUE, x0, cell_w, y_val, value)
                if detail:
                    draw_line(p, df, QColor("#f3dcae"), x0, cell_w, y_val + hv + gap, detail)
        p.end()


class BannerBar(QWidget):
    SEP = "   |   "

    def __init__(self, font_family="Noto Sans Devanagari", parent=None):
        super().__init__(parent)
        self.font_family = font_family
        self.line1 = ""
        self.parts = ()
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_lines(self, line1, parts):
        """line1: string.  parts: list of (priority, text) in DISPLAY order.
        Priority 1 is kept longest; the highest numbers are dropped first
        when the line is too long."""
        parts = tuple(parts)
        if (line1, parts) != (self.line1, self.parts):
            self.line1, self.parts = line1, parts
            self.update()

    def _line2_text(self, h, width):
        """Longest combination of parts that fits `width` at a readable size."""
        min_px = max(6, int(h * 0.21))
        keep = sorted({pr for pr, _ in self.parts})
        while keep:
            text = self.SEP.join(t for pr, t in self.parts if pr <= keep[-1])
            f = _font(self.font_family, min_px)
            if QFontMetrics(f).horizontalAdvance(text) <= width:
                return text
            keep.pop()
        return self.parts[0][1] if self.parts else ""

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor(70, 22, 14, 235))
        grad.setColorAt(1.0, QColor(40, 10, 8, 235))
        p.setBrush(grad)
        p.setPen(QPen(C_PANEL_EDGE, max(1.5, h * 0.03)))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), h * 0.18, h * 0.18)

        tw = w * 0.94
        line2 = self._line2_text(h, tw)
        if not line2:
            # only one line: use the full height of the banner and a bigger font
            f1 = fit_font(_font(self.font_family, h * 0.56, True), self.line1, tw)
            p.setFont(f1)
            p.setPen(QColor("#f6b730"))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self.line1)
            p.end()
            return
        f1 = fit_font(_font(self.font_family, h * 0.46, True), self.line1, tw)
        p.setFont(f1)
        p.setPen(QColor("#f6b730"))
        p.drawText(QRectF(0, h * 0.04, w, h * 0.55), Qt.AlignCenter, self.line1)
        f2 = fit_font(_font(self.font_family, h * 0.28), line2, tw)
        p.setFont(f2)
        p.setPen(C_VALUE)
        p.drawText(QRectF(0, h * 0.58, w, h * 0.38), Qt.AlignCenter, line2)
        p.end()


class CornerCard(QWidget):
    """
    Card for the bottom corners (festival / eclipse notice).

      line 1  BIG gold text   (e.g. "आज का पर्व : दीपावली"  /  "चन्द्र ग्रहण")
      line 2  optional, smaller cream text under it
              (festival on a tie: "9/10 नवम्बर"; eclipse: its date and timing).
              With no line 2, line 1 uses the whole card.
      EMPTY line 1  ->  the card shows a swastik symbol instead (nothing to announce)

    Each line is fitted to the card: the font is the largest size (up to a
    limit) at which the wrapped text still fits.
    """
    def __init__(self, font_family="Noto Sans Devanagari", parent=None):
        super().__init__(parent)
        self.font_family = font_family
        self.line1 = ""
        self.line2 = ""
        self._swastik = None            # original picture, loaded once
        self._swastik_scaled = None     # scaled copy for the current card size
        self._swastik_side = 0
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_content(self, line1="", line2=""):
        """Empty line1 = nothing to announce -> swastik is shown."""
        if (line1, line2) != (self.line1, self.line2):
            self.line1, self.line2 = line1, line2
            self.update()

    def _draw_fitted(self, p, box, text, start_px, bold, color, min_px=7):
        """Draw `text` wrapped and centred in `box` with the biggest font that fits."""
        flags = Qt.AlignCenter | Qt.TextWordWrap
        px = int(start_px)
        while True:
            f = _font(self.font_family, px, bold)
            r = QFontMetrics(f).boundingRect(box.toRect(), flags, text)
            if (r.height() <= box.height() and r.width() <= box.width() + 1) or px <= min_px:
                break
            px -= 1
        p.setFont(f)
        p.setPen(color)
        p.drawText(box, flags, text)

    def _draw_swastik(self, p, w, h):
        """Swastik symbol centred in the card (scaled once per card size)."""
        side = int(h * 0.80)
        if self._swastik is None:
            self._swastik = QPixmap(SWASTIK_FILE)
        if self._swastik.isNull() or side < 4:
            return
        if self._swastik_scaled is None or self._swastik_side != side:
            self._swastik_scaled = self._swastik.scaled(side, side, Qt.KeepAspectRatio,
                                                        Qt.SmoothTransformation)
            self._swastik_side = side
        p.drawPixmap(int((w - side) / 2), int((h - side) / 2), self._swastik_scaled)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()
        p.setBrush(C_PANEL_BG)
        p.setPen(QPen(C_PANEL_EDGE, max(1.5, h * 0.03)))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), h * 0.18, h * 0.18)
        if not self.line1:
            self._draw_swastik(p, w, h)
            p.end()
            return
        gold = QColor("#f6b730")
        title_px = h * 0.31             # SAME size on the festival and eclipse cards
        if self.line2:
            top = QRectF(w * 0.03, h * 0.04, w * 0.94, h * 0.56)
            bot = QRectF(w * 0.03, h * 0.60, w * 0.94, h * 0.37)
            self._draw_fitted(p, top, self.line1, title_px, True, gold)
            self._draw_fitted(p, bot, self.line2, h * 0.24, False, C_VALUE)
        else:
            # long names wrap onto two lines at the same size; the font shrinks
            # only if even two lines do not fit
            box = QRectF(w * 0.03, h * 0.05, w * 0.94, h * 0.90)
            self._draw_fitted(p, box, self.line1, title_px, True, gold)
        p.end()
