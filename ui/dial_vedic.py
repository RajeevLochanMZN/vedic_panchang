"""
ui/dial_vedic.py  --  the central Vedic dial (ghati / pal / vipal / muhurta / pahar).

PURE WIDGET: it knows nothing about the engine, GPIO or settings.  A page gives
it plain numbers and names, and it draws them.  That keeps it easy to test on
the PC and easy to wire to the engine later.

THE RINGS (outside -> inside)
  1. Ghati ring   60 ticks, numbers every 5.  Sunrise is at the TOP (0).
                  Going clockwise, 60 ghati = one full day from sunrise to the
                  next sunrise.  1 ghati = 24 min, 1 pal = 24 s, 1 vipal = 0.4 s.
  2. Muhurta ring 30 segments: 15 for the day (sunrise -> sunset) and 15 for
                  the night.  Segment lengths follow the REAL day/night length,
                  so day muhurtas are not exactly 48 min except at the equinox.
  3. Pahar ring   8 segments: 4 for the day and 4 for the night.
  4. Centre disc  ghati : pal : vipal as numbers (one hand cannot show vipal),
                  plus the running pahar and muhurta names.
  The single HAND points at the current ghati and stops short of the centre
  disc so it never covers the numbers.

HOW A PAGE USES IT
    dial = VedicDial(font_family="Noto Sans Devanagari")
    dial.set_names(muhurta_names, pahar_names)     # once (30 names, 8 names)
    dial.set_time(elapsed_ghati, day_ghati)        # every ~100 ms
  elapsed_ghati : float, ghati since today's sunrise (0 <= x < 60)
  day_ghati     : float, length of the day in ghati (= dinman minutes / 24)

PERFORMANCE: the rings are painted ONCE into a cached QPixmap (rebuilt only on
resize or when the names / day length change).  Each frame then draws just the
cached picture + the highlight + the hand + the centre text.
"""
import math
from PyQt5.QtCore import Qt, QPointF, QRectF, QSize
from PyQt5.QtGui import (QPainter, QPixmap, QColor, QPen, QBrush, QFont,
                         QFontMetrics, QPainterPath, QPolygonF, QRadialGradient)
from PyQt5.QtWidgets import QWidget, QSizePolicy

# ---------------------------------------------------------------------------
# Default names (replace with the engine's translated names via set_names()).
# ---------------------------------------------------------------------------
DEFAULT_MUHURTA_NAMES = [
    "रुद्र", "अहि", "मित्र", "पितृ", "वसु", "उदक", "विश्वेदेव", "विधातृ",
    "ब्रह्मा", "इन्द्र", "इन्द्राग्नि", "निरृति", "तोयप", "अर्यमा", "भग",
    "ईश", "अजपाद", "अहिर्बुध्न्य", "पूषा", "अश्विनी", "यम", "अग्नि",
    "धातृ", "वृद्धि", "चन्द्र", "अदिति", "विष्णु", "अर्क", "त्वष्ट्र", "वायु",
]
DEFAULT_PAHAR_NAMES = [            # 4 day pahars then 4 night pahars
    "पूर्वाह्न", "मध्याह्न", "अपराह्न", "सायंकाल",
    "प्रदोष", "निशीथ", "त्रियामा", "उषा",
]
DEFAULT_LABELS = {
    "sunrise": "सूर्योदय", "sunset": "सूर्यास्त",
    "abhijit": "अभिजित", "brahma": "ब्रह्म मुहूर्त",
    "ghati": "घटी", "pal": "पल", "vipal": "विपल",
}

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
C_OUTER      = QColor("#7a3b12")        # ghati ring (dark brown)
C_OUTER_EDGE = QColor("#fff4dc")
C_TICK       = QColor("#fff4dc")
C_NUMBER     = QColor("#fff4dc")
C_MUH_DAY    = QColor("#e8981a")        # muhurta ring, day half
C_MUH_NIGHT  = QColor("#a8610f")        # muhurta ring, night half
C_MUH_TEXT   = QColor("#fff7e6")
C_LINE       = QColor("#fff4dc")
C_CENTRE     = QColor("#f9e3a0")
C_CENTRE_TXT = QColor("#4a1304")
C_HAND       = QColor("#5e0a05")
C_HAND_EDGE  = QColor("#e8b84a")
C_GOLD       = QColor("#f0b323")
# Pahar ring: day pahars light, night pahars dark (so day/night is obvious)
PAHAR_COLORS = [
    QColor("#fbe9b0"), QColor("#f8dc8a"), QColor("#f5cc6e"), QColor("#f1b254"),
    QColor("#7a4a6e"), QColor("#4a3a6e"), QColor("#33336a"), QColor("#5a4478"),
]
PAHAR_TEXT = [QColor("#4a1304")] * 4 + [QColor("#fdf1d6")] * 4

# Dial size and position, as fractions of the widget HEIGHT.
#   DIAL_FILL       diameter of the dial            (0.85 = 85% of the height)
#   DIAL_TOP_MARGIN empty space above the dial      (0.05 = 5%)
# Whatever is left goes below the dial: 1 - 0.85 - 0.05 = 10% bottom margin.
# (The bottom margin is where the banner / text strip will go later.)
DIAL_FILL = 0.85
DIAL_TOP_MARGIN = 0.05

# Ring radii as a fraction of the outer radius R
R_OUT, R_TICKS_IN = 1.00, 0.895
R_MUH_IN          = 0.615
R_PAH_IN          = 0.395

# Widest the ghati:pal:vipal digit row may be, as a fraction of the radius R.
# The centre disc is 2*0.395 = 0.79 R wide; 0.70 keeps a small gap at each side.
DIGITS_MAX_W = 0.70


def _sector(cx, cy, r_out, r_in, ang_a, ang_b):
    """
    Ring segment (a 'slice of a doughnut') from clockwise-from-top angle
    ang_a to ang_b, in degrees, between radius r_in and r_out.
    Qt measures arcs counter-clockwise from 3 o'clock, so we convert.
    """
    outer = QRectF(cx - r_out, cy - r_out, 2 * r_out, 2 * r_out)
    inner = QRectF(cx - r_in, cy - r_in, 2 * r_in, 2 * r_in)
    start = 90.0 - ang_a
    sweep = -(ang_b - ang_a)
    path = QPainterPath()
    path.arcMoveTo(outer, start)
    path.arcTo(outer, start, sweep)
    path.arcTo(inner, start + sweep, -sweep)
    path.closeSubpath()
    return path


def _polar(cx, cy, r, ang):
    """Point at radius r, clockwise-from-top angle ang (degrees)."""
    a = math.radians(ang)
    return QPointF(cx + r * math.sin(a), cy - r * math.cos(a))


class VedicDial(QWidget):
    def __init__(self, font_family="Noto Sans Devanagari", parent=None):
        super().__init__(parent)
        self.font_family = font_family
        self.muhurta_names = list(DEFAULT_MUHURTA_NAMES)
        self.pahar_names = list(DEFAULT_PAHAR_NAMES)
        self.labels = dict(DEFAULT_LABELS)
        self.elapsed_ghati = 0.0
        self.day_ghati = 30.0
        # Abhijit / Brahma muhurta as (start, end) in ghati since sunrise.
        # None = use the classical default (see _spans()).
        self.abhijit_span = None
        self.brahma_span = None
        self._cache = None
        self._cache_key = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ------------------------------------------------------------------ API
    def set_names(self, muhurta_names=None, pahar_names=None, labels=None):
        """30 muhurta names (day 15 then night 15), 8 pahar names (4 + 4)."""
        if muhurta_names:
            self.muhurta_names = list(muhurta_names)
        if pahar_names:
            self.pahar_names = list(pahar_names)
        if labels:
            self.labels.update(labels)
        self._cache = None
        self.update()

    def set_marked_spans(self, abhijit=None, brahma=None):
        """Optional: give the engine's own Abhijit / Brahma muhurta as
        (start, end) in ghati since sunrise.  Brahma muhurta is before the
        next sunrise, so its numbers are close to 60 (e.g. 55.8 .. 57.9)."""
        self.abhijit_span = abhijit
        self.brahma_span = brahma
        self._cache = None
        self.update()

    def _spans(self):
        """(abhijit, brahma) spans.  Defaults, if the engine gave none:
          Abhijit = 8th of the 15 DAY muhurtas  (centred on local noon)
          Brahma  = 14th of the 15 NIGHT muhurtas (just before sunrise)"""
        d = self.day_ghati
        n = 60.0 - d
        abhijit = self.abhijit_span or (d * 7 / 15.0, d * 8 / 15.0)
        brahma = self.brahma_span or (d + n * 13 / 15.0, d + n * 14 / 15.0)
        return abhijit, brahma

    def set_time(self, elapsed_ghati, day_ghati):
        """Call every ~100 ms.  The static rings are rebuilt only if the day
        length changed by more than ~0.05 ghati (about a minute)."""
        self.elapsed_ghati = elapsed_ghati % 60.0
        if abs(day_ghati - self.day_ghati) > 0.05:
            self.day_ghati = day_ghati
            self._cache = None
        self.update()

    def sizeHint(self):
        return QSize(700, 700)

    # ----------------------------------------------------------- geometry
    def _geometry(self):
        """Centre point and outer radius.  Margin leaves room for the
        'सूर्योदय' tag that sits on the ring at the top."""
        w, h = self.width(), self.height()
        side = min(w, h)
        R = side / 2.0 * DIAL_FILL
        if h <= w:                      # height is the limit: use the margins
            cy = h * DIAL_TOP_MARGIN + R
        else:                           # narrow widget: just centre it
            cy = h / 2.0
        return w / 2.0, cy, R

    def _font(self, R, frac, bold=False):
        """Font whose pixel size is a fraction of the dial radius, so
        everything scales with the screen (no px() needed here)."""
        f = QFont(self.font_family)
        f.setPixelSize(max(6, int(R * frac)))
        f.setBold(bold)
        return f

    # ------------------------------------------------- muhurta / pahar maths
    def _boundaries(self, parts_day, parts_night):
        """Angles (degrees) of the segment edges: parts_day segments across
        the day, parts_night across the night.  Returns list of (a, b)."""
        day_deg = self.day_ghati * 6.0
        night_deg = 360.0 - day_deg
        out = []
        for i in range(parts_day):
            out.append((day_deg * i / parts_day, day_deg * (i + 1) / parts_day))
        for i in range(parts_night):
            out.append((day_deg + night_deg * i / parts_night,
                        day_deg + night_deg * (i + 1) / parts_night))
        return out

    def _index_at(self, segments, ghati):
        ang = ghati * 6.0
        for i, (a, b) in enumerate(segments):
            if a <= ang < b:
                return i
        return len(segments) - 1

    def current_muhurta_index(self):
        return self._index_at(self._boundaries(15, 15), self.elapsed_ghati)

    def current_pahar_index(self):
        return self._index_at(self._boundaries(4, 4), self.elapsed_ghati)

    # --------------------------------------------------- static ring picture
    def _build_cache(self):
        w, h = self.width(), self.height()
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        cx, cy, R = self._geometry()

        # --- 1. ghati ring ------------------------------------------------
        p.setPen(Qt.NoPen)
        p.setBrush(C_OUTER)
        p.drawEllipse(QPointF(cx, cy), R * R_OUT, R * R_OUT)
        p.setPen(QPen(C_OUTER_EDGE, max(1.5, R * 0.006)))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R * R_OUT, R * R_OUT)

        # gold bands for Abhijit and Brahma muhurta on the inner edge of the
        # ghati ring (labels are added at the end, as tags on the outer edge)
        abh, brh = self._spans()
        p.setPen(Qt.NoPen)
        p.setBrush(C_GOLD)
        for a, b in (abh, brh):
            p.drawPath(_sector(cx, cy, R * (R_TICKS_IN + 0.027), R * (R_TICKS_IN + 0.002),
                               a * 6.0, b * 6.0))

        for g in range(60):
            ang = g * 6.0
            major = (g % 5 == 0)
            r1 = R * R_OUT
            r0 = r1 - R * (0.045 if major else 0.025)
            p.setPen(QPen(C_TICK, max(1.2, R * (0.007 if major else 0.004)),
                          Qt.SolidLine, Qt.RoundCap))
            p.drawLine(_polar(cx, cy, r0, ang), _polar(cx, cy, r1, ang))
        # numbers every 5, kept UPRIGHT (easier to read than rotated text)
        p.setFont(self._font(R, 0.052, bold=True))
        p.setPen(C_NUMBER)
        fm = QFontMetrics(p.font())
        for g in range(0, 60, 5):
            pt = _polar(cx, cy, R * 0.945, g * 6.0)
            txt = str(g)
            p.drawText(QPointF(pt.x() - fm.horizontalAdvance(txt) / 2.0,
                               pt.y() + fm.ascent() / 2.0 - fm.descent() / 2.0),
                       txt)

        # --- 2. muhurta ring ---------------------------------------------
        muh = self._boundaries(15, 15)
        for i, (a, b) in enumerate(muh):
            p.setPen(QPen(C_LINE, max(1.0, R * 0.0035)))
            p.setBrush(C_MUH_DAY if i < 15 else C_MUH_NIGHT)
            p.drawPath(_sector(cx, cy, R * R_TICKS_IN, R * R_MUH_IN, a, b))
            self._radial_text(p, cx, cy, R * (R_TICKS_IN + R_MUH_IN) / 2.0,
                              (a + b) / 2.0, self.muhurta_names[i],
                              self._font(R, 0.066), C_MUH_TEXT,
                              max_len=R * (R_TICKS_IN - R_MUH_IN) * 0.90)

        # --- 3. pahar ring -----------------------------------------------
        pah = self._boundaries(4, 4)
        for i, (a, b) in enumerate(pah):
            p.setPen(QPen(C_LINE, max(1.0, R * 0.0035)))
            p.setBrush(PAHAR_COLORS[i])
            p.drawPath(_sector(cx, cy, R * R_MUH_IN, R * R_PAH_IN, a, b))
            self._horizontal_text(p, cx, cy, R * (R_MUH_IN + R_PAH_IN) / 2.0,
                                  (a + b) / 2.0, self.pahar_names[i],
                                  self._font(R, 0.060, bold=True),
                                  PAHAR_TEXT[i],
                                  max_w=R * (R_MUH_IN - R_PAH_IN) * 0.98)

        # --- 4. centre disc ----------------------------------------------
        grad = QRadialGradient(QPointF(cx, cy), R * R_PAH_IN)
        grad.setColorAt(0.0, QColor("#fff3c8"))
        grad.setColorAt(1.0, C_CENTRE)
        p.setPen(QPen(C_LINE, max(1.5, R * 0.005)))
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(cx, cy), R * R_PAH_IN, R * R_PAH_IN)

        # --- sunrise / sunset markers on the outer edge -------------------
        self._tag(p, cx, cy, R, 0.0, self.labels["sunrise"])
        self._tag(p, cx, cy, R, self.day_ghati * 6.0, self.labels["sunset"])
        # smaller tags for the two special muhurtas, at the middle of each arc
        self._tag(p, cx, cy, R, (abh[0] + abh[1]) * 3.0, self.labels["abhijit"], 0.040)
        self._tag(p, cx, cy, R, (brh[0] + brh[1]) * 3.0, self.labels["brahma"], 0.040)

        p.end()
        return pm

    # ------------------------------------------------------- text helpers
    def _fit_font(self, font, text, max_px):
        """Shrink the font until `text` fits in max_px pixels wide."""
        f = QFont(font)
        while f.pixelSize() > 6 and QFontMetrics(f).horizontalAdvance(text) > max_px:
            f.setPixelSize(f.pixelSize() - 1)
        return f

    def _radial_text(self, p, cx, cy, r_mid, ang, text, font, color, max_len):
        """Text laid along the radius.  Flipped on the left half so it is
        never upside down (right half already reads upright)."""
        font = self._fit_font(font, text, max_len)
        p.save()
        p.translate(cx, cy)
        p.rotate(ang)                 # now 'up' (-y) points along the radius
        p.translate(0, -r_mid)
        p.rotate(-90)                 # text now runs inside -> outside
        if ang % 360.0 > 180.0:
            p.rotate(180)             # LEFT half: flip so text is never upside down
        fm = QFontMetrics(font)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QPointF(-fm.horizontalAdvance(text) / 2.0,
                           fm.ascent() / 2.0 - fm.descent() / 2.0), text)
        p.restore()

    def _horizontal_text(self, p, cx, cy, r_mid, ang, text, font, color, max_w):
        """Upright text centred on a ring segment."""
        font = self._fit_font(font, text, max_w)
        fm = QFontMetrics(font)
        pt = _polar(cx, cy, r_mid, ang)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QPointF(pt.x() - fm.horizontalAdvance(text) / 2.0,
                           pt.y() + fm.ascent() / 2.0 - fm.descent() / 2.0), text)

    def _tag(self, p, cx, cy, R, ang, text, size=0.048):
        """Small gold label sitting on the outer ring (sunrise / sunset)."""
        font = self._font(R, size, bold=True)
        fm = QFontMetrics(font)
        pt = _polar(cx, cy, R * 0.985, ang)
        tw = fm.horizontalAdvance(text) + R * 0.06
        th = fm.height() + R * 0.012
        rect = QRectF(pt.x() - tw / 2.0, pt.y() - th / 2.0, tw, th)
        # keep the tag inside the widget
        if rect.top() < 2:
            rect.moveTop(2)
        p.setPen(QPen(C_OUTER_EDGE, max(1.0, R * 0.004)))
        p.setBrush(C_GOLD)
        p.drawRoundedRect(rect, R * 0.012, R * 0.012)
        p.setFont(font)
        p.setPen(QColor("#4a1304"))
        p.drawText(rect, Qt.AlignCenter, text)

    # -------------------------------------------------------------- paint
    def paintEvent(self, event):
        key = (self.width(), self.height(), tuple(self.muhurta_names),
               tuple(self.pahar_names), round(self.day_ghati, 2),
               tuple(sorted(self.labels.items())), self._spans())
        if self._cache is None or self._cache_key != key:
            self._cache = self._build_cache()
            self._cache_key = key

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.drawPixmap(0, 0, self._cache)
        cx, cy, R = self._geometry()

        # --- highlight the RUNNING muhurta and pahar ----------------------
        mi = self.current_muhurta_index()
        a, b = self._boundaries(15, 15)[mi]
        p.setBrush(QColor(255, 255, 255, 55))
        p.setPen(QPen(C_GOLD, max(2.0, R * 0.008)))
        p.drawPath(_sector(cx, cy, R * R_TICKS_IN, R * R_MUH_IN, a, b))
        pi = self.current_pahar_index()
        a, b = self._boundaries(4, 4)[pi]
        p.setBrush(QColor(255, 255, 255, 28))
        p.drawPath(_sector(cx, cy, R * R_MUH_IN, R * R_PAH_IN, a, b))

        # --- the hand -------------------------------------------------------
        self._draw_hand(p, cx, cy, R, self.elapsed_ghati * 6.0)

        # --- centre readout -------------------------------------------------
        self._draw_centre(p, cx, cy, R, mi, pi)
        p.end()

    def _draw_hand(self, p, cx, cy, R, ang):
        """Tapered hand from the edge of the centre disc to the tick ring."""
        r_in, r_out = R * (R_PAH_IN + 0.01), R * 0.975
        half_base = R * 0.026
        a = math.radians(ang)
        ux, uy = math.sin(a), -math.cos(a)        # along the hand
        nx, ny = -uy, ux                           # sideways
        tip = QPointF(cx + ux * r_out, cy + uy * r_out)
        b1 = QPointF(cx + ux * r_in + nx * half_base, cy + uy * r_in + ny * half_base)
        b2 = QPointF(cx + ux * r_in - nx * half_base, cy + uy * r_in - ny * half_base)
        p.setBrush(C_HAND)
        p.setPen(QPen(C_HAND_EDGE, max(1.0, R * 0.003)))
        p.drawPolygon(QPolygonF([b1, tip, b2]))
        # round hub where the hand meets the centre disc
        p.setBrush(C_HAND)
        p.drawEllipse(QPointF(cx + ux * r_in, cy + uy * r_in), half_base, half_base)

    def _draw_centre(self, p, cx, cy, R, mi, pi):
        g = self.elapsed_ghati
        gh = int(g)
        pal_f = (g - gh) * 60.0
        pal = int(pal_f)
        vipal = int((pal_f - pal) * 60.0)

        # running pahar name (top of the disc)
        f = self._fit_font(self._font(R, 0.075, bold=True),
                           self.pahar_names[pi], R * 0.60)
        p.setFont(f)
        p.setPen(C_CENTRE_TXT)
        p.drawText(QRectF(cx - R * 0.33, cy - R * 0.34, R * 0.66, R * 0.12),
                   Qt.AlignCenter, self.pahar_names[pi])

        # ghati : pal : vipal  -- three fixed-width boxes so digits never jitter
        # The three digit boxes must fit inside the centre disc whatever font
        # the Pi uses, so start at a comfortable size and shrink until the
        # whole "88 : 88 : 88" row is at most DIGITS_MAX_W of the radius wide.
        f = self._font(R, 0.175, bold=True)
        while True:
            fm = QFontMetrics(f)
            box_w = fm.horizontalAdvance("88") + R * 0.015
            colon_w = fm.horizontalAdvance(":") + R * 0.008
            total = 3 * box_w + 2 * colon_w
            if total <= R * DIGITS_MAX_W or f.pixelSize() <= 8:
                break
            f.setPixelSize(f.pixelSize() - 1)
        p.setFont(f)
        x = cx - total / 2.0
        top = cy - R * 0.16
        hgt = R * 0.21
        for i, val in enumerate((gh, pal, vipal)):
            p.drawText(QRectF(x, top, box_w, hgt), Qt.AlignCenter, "%02d" % val)
            if i < 2:
                p.drawText(QRectF(x + box_w, top, colon_w, hgt), Qt.AlignCenter, ":")
            # small caption under each box
            cap = (self.labels["ghati"], self.labels["pal"], self.labels["vipal"])[i]
            cf = self._font(R, 0.052)
            p.setFont(cf)
            p.drawText(QRectF(x, top + hgt - R * 0.01, box_w, R * 0.08),
                       Qt.AlignCenter, cap)
            p.setFont(f)
            x += box_w + (colon_w if i < 2 else 0)

        # running muhurta name (bottom of the disc)
        name = self.muhurta_names[mi]
        f = self._fit_font(self._font(R, 0.075, bold=True), name, R * 0.60)
        p.setFont(f)
        p.setPen(QColor("#8a2a05"))
        p.drawText(QRectF(cx - R * 0.33, cy + R * 0.18, R * 0.66, R * 0.12),
                   Qt.AlignCenter, name)
