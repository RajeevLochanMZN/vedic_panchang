"""
ui/page_calendar_portrait_hi.py  --  the Calendar page for the PORTRAIT screen (Pi 2, 480 wide).

Same data and colours as page_calendar_hi.py (it uses that file's day computation), but a layout made
for a narrow tall screen: 7 columns of about 64 px.  Every day cell is painted directly:

    +--------+
    |12      |   day number (big)
    |शु तृतीया|   paksha (शु = शुक्ल, कृ = कृष्ण) and the tithi at sunrise, on ONE line
    |गोवर्धन |   festivals (wrapped, as many lines as fit, "…" if more)
    |पूजा    |
    +--------+

  * TRANSPOSED = True (default): the weekdays run DOWN the left side (7 rows) and the weeks run across
    (5 or 6 columns), so every cell is about 14 % wider than with 7 columns; False = the usual layout
  * today = orange cell, a day with a festival = lighter maroon
  * the page re-reads the date every time it is shown (the old page drew the month once at start)
  * the bottom `reserve_bottom` px stay empty: the touch buttons are drawn over them
Used by ui/main_window_hi.py when the portrait dial page is used.  The landscape page is not changed.
"""
import calendar
from datetime import datetime, timezone

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QColor, QFont, QFontMetrics, QPen
from PyQt5.QtWidgets import QWidget

from page_calendar_hi import PageCalendarHi, get_day_panchang_summary_hi, IST_OFFSET
from masa import get_purnimanta_masa_name, get_vikram_samvat_year
from sun_times import get_local_midnight_jd_ut, get_sunrise_jd
from config_loader import get_location
from translations_hi import (HEADINGS_HI, translate_masa, translate_month,
                             translate_weekday_short, get_devanagari_font_family)
from info_panels import LINE_H, ASCENT, fit_font
from popup_card import wrap_words

C_BG = QColor("#4a1520")
C_TITLE = QColor("#f39c12")
C_DARK = QColor("#1a1a1a")
C_HEAD = QColor("#e67e22")
C_CELL = QColor("#2c0f18")
C_CELL_FEST = QColor("#5a2a10")
C_FEST_TEXT = QColor("#ffcf70")
C_MUTED = QColor("#c9a79a")

MARGIN = 6
GAP = 3
TITLE_H = 66
HEAD_H = 26
LABEL_W = 22          # width of the weekday labels (turned sideways) in the transposed layout
TRANSPOSED = True     # weekdays down the left, weeks across (wider cells); False = weekdays across the top
REF_W = 64.3          # cell width the text sizes were chosen for; wider cells grow the text up to 12 %


def _font(family, px, bold=False):
    f = QFont(family)
    f.setPixelSize(max(6, int(px)))
    f.setBold(bold)
    return f


class DayCell(QWidget):
    def __init__(self, family, parent=None):
        super().__init__(parent)
        self.family = family
        self.day = ""
        self.paksha = ""
        self.tithi = ""
        self.festivals = []
        self.today = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_data(self, day, paksha, tithi, festivals, today):
        self.day, self.paksha, self.tithi = str(day), paksha, tithi
        self.festivals, self.today = festivals, today
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        if self.today:
            bg, fg, sub, fest = C_TITLE, C_DARK, C_DARK, C_DARK
        else:
            bg = C_CELL_FEST if self.festivals else C_CELL
            fg, sub, fest = QColor("white"), C_MUTED, C_FEST_TEXT
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, h), 5, 5)
        k = min(1.12, max(1.0, w / REF_W))          # text grows a little in wider cells
        pad = max(3, REF_W * 0.05 * k)
        inner = w - 2 * pad
        y = 2.0
        # day number
        nf = _font(self.family, REF_W * 0.40 * k, True)
        p.setFont(nf)
        p.setPen(fg)
        p.drawText(QRectF(pad, y, inner, nf.pixelSize() * LINE_H), Qt.AlignLeft | Qt.AlignTop, self.day)
        y += nf.pixelSize() * LINE_H
        # second line: paksha letters + tithi, side by side (both shrink together if the line is too wide)
        if self.tithi:
            t_px = max(6, int(REF_W * 0.21 * k))
            while True:
                tf = _font(self.family, t_px)
                pf = _font(self.family, max(6, round(t_px * 0.85)), True)
                pw = QFontMetrics(pf).horizontalAdvance(self.paksha) if self.paksha else 0
                gap = 3 if self.paksha else 0
                total = pw + gap + QFontMetrics(tf).horizontalAdvance(self.tithi)
                if total <= inner or t_px <= 8:
                    break
                t_px -= 1
            x = pad
            if self.paksha:
                p.setFont(pf)
                p.setPen(C_DARK if self.today else (C_FEST_TEXT if self.paksha == "शु" else C_MUTED))
                p.drawText(QRectF(x, y, pw + 2, pf.pixelSize() * LINE_H), Qt.AlignLeft | Qt.AlignTop, self.paksha)
                x += pw + gap
            p.setFont(tf)
            p.setPen(sub if not self.today else C_DARK)
            p.drawText(QRectF(x, y, inner, tf.pixelSize() * LINE_H), Qt.AlignLeft | Qt.AlignTop, self.tithi)
            y += tf.pixelSize() * LINE_H + 1
        # festivals: wrapped, as many lines as fit
        if self.festivals:
            ff = _font(self.family, REF_W * 0.19 * k, True)
            lines = []
            for name in self.festivals:
                lines += wrap_words(ff, name, inner)
            line_h = ff.pixelSize() * LINE_H
            fit = max(1, int((h - y - 2) // line_h))
            if len(lines) > fit:
                lines = lines[:fit]
                # the last visible line ends in "…" and is cut so that it still fits the cell
                lines[-1] = QFontMetrics(ff).elidedText(lines[-1].rstrip() + " …", Qt.ElideRight, int(inner))
                if not lines[-1].endswith("…"):
                    lines[-1] = lines[-1][:-1] + "…"
            p.setFont(ff)
            p.setPen(fest)
            for line in lines:
                p.drawText(QRectF(pad, y, inner, line_h), Qt.AlignLeft | Qt.AlignTop, line)
                y += line_h
        p.end()


class PageCalendarPortraitHi(PageCalendarHi):
    def __init__(self):
        # QWidget init only: the base class would build the wide landscape layout
        QWidget.__init__(self)
        self.lat, self.lon = get_location()
        self.font_family = get_devanagari_font_family()
        self.reserve_bottom = 0          # px kept free at the bottom (the touch buttons)
        self._key = None
        self._cells = []                 # (DayCell, row, col)
        self._title1 = self._title2 = ""
        self._weeks = 0
        self._render_current_month()

    # ------------------------------------------------------------------ data
    def _render_current_month(self):
        now_ist = datetime.now(timezone.utc) + IST_OFFSET
        key = (now_ist.year, now_ist.month, now_ist.day)
        if key == self._key:
            return
        self._key = key
        month_hi = translate_month(now_ist.strftime("%B"))
        weeks = calendar.monthcalendar(now_ist.year, now_ist.month)
        self._weeks = len(weeks)
        first, last = [d for w in weeks for d in w if d][0], [d for w in weeks for d in w if d][-1]
        sr_first = get_sunrise_jd(get_local_midnight_jd_ut(datetime(now_ist.year, now_ist.month, first)), self.lat, self.lon)
        sr_last = get_sunrise_jd(get_local_midnight_jd_ut(datetime(now_ist.year, now_ist.month, last)), self.lat, self.lon)
        m1, m2 = get_purnimanta_masa_name(sr_first), get_purnimanta_masa_name(sr_last)
        h1, h2 = translate_masa(m1), translate_masa(m2)
        masa = h1 if m1 == m2 else "%s/%s" % (h1, h2)
        self._title1 = "%s %s" % (month_hi, now_ist.year)
        self._title2 = "%s: %s    %s" % (HEADINGS_HI["vikram_samvat"], get_vikram_samvat_year(sr_first), masa)

        for cell, _r, _c in self._cells:
            cell.deleteLater()
        self._cells = []
        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if not day:
                    continue
                s = get_day_panchang_summary_hi(datetime(now_ist.year, now_ist.month, day), self.lat, self.lon)
                paksha = "शु" if "शुक्ल" in s["paksha_hi"] else "कृ"
                cell = DayCell(self.font_family, self)
                cell.set_data(day, paksha, s["tithi_name_hi"], s["festivals_hi"], day == now_ist.day)
                cell.show()
                self._cells.append((cell, r, c))
        self._layout()
        self.update()

    # ------------------------------------------------------------------ layout / painting
    def _layout(self):
        W, H = self.width(), self.height()
        if W < 50 or H < 50:
            return
        weeks = max(1, self._weeks)
        if TRANSPOSED:
            self._top = MARGIN + TITLE_H + 4
            left = MARGIN + LABEL_W + GAP
            grid_h = H - self.reserve_bottom - MARGIN - self._top
            cw = (W - MARGIN - left - (weeks - 1) * GAP) / float(weeks)
            ch = min(150.0, (grid_h - 6 * GAP) / 7.0)
            self._left, self._cw, self._ch = left, cw, ch
            for cell, r, c in self._cells:          # r = week (column), c = weekday (row)
                cell.setGeometry(int(round(left + r * (cw + GAP))), int(round(self._top + c * (ch + GAP))),
                                 int(round(cw)), int(round(ch)))
        else:
            self._top = MARGIN + TITLE_H + 4 + HEAD_H + 3
            grid_h = H - self.reserve_bottom - MARGIN - self._top
            cw = (W - 2 * MARGIN - 6 * GAP) / 7.0
            ch = min(140.0, (grid_h - (weeks - 1) * GAP) / weeks)
            self._left, self._cw, self._ch = MARGIN, cw, ch
            for cell, r, c in self._cells:
                cell.setGeometry(int(round(MARGIN + c * (cw + GAP))), int(round(self._top + r * (ch + GAP))),
                                 int(round(cw)), int(round(ch)))

    def resizeEvent(self, event):
        self._layout()
        super(PageCalendarHi, self).resizeEvent(event)

    def relayout(self):
        self._layout()
        self.update()

    def showEvent(self, event):
        self._render_current_month()          # a new day / month since last time -> redraw
        super(PageCalendarHi, self).showEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        W = self.width()
        p.fillRect(self.rect(), C_BG)
        # title bar
        p.setBrush(C_TITLE)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(MARGIN, MARGIN, W - 2 * MARGIN, TITLE_H), 8, 8)
        f1 = fit_font(_font(self.font_family, 34, True), self._title1, W - 2 * MARGIN - 20)
        p.setFont(f1)
        p.setPen(C_DARK)
        p.drawText(QRectF(MARGIN, MARGIN + 3, W - 2 * MARGIN, f1.pixelSize() * LINE_H), Qt.AlignHCenter | Qt.AlignTop, self._title1)
        f2 = fit_font(_font(self.font_family, 16, True), self._title2, W - 2 * MARGIN - 20)
        p.setFont(f2)
        p.drawText(QRectF(MARGIN, MARGIN + 3 + f1.pixelSize() * LINE_H - 2, W - 2 * MARGIN, f2.pixelSize() * LINE_H),
                   Qt.AlignHCenter | Qt.AlignTop, self._title2)
        names = [translate_weekday_short(n) for n in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]]
        hf = _font(self.font_family, 16, True)
        p.setFont(hf)
        p.setPen(C_HEAD)
        if TRANSPOSED:
            # weekday names turned sideways, one per row, in the narrow column at the left
            for i, name in enumerate(names):
                cy = self._top + i * (self._ch + GAP) + self._ch / 2.0
                p.save()
                p.translate(MARGIN + LABEL_W / 2.0, cy)
                p.rotate(-90)
                p.drawText(QRectF(-self._ch / 2.0, -LABEL_W / 2.0, self._ch, LABEL_W), Qt.AlignCenter, name)
                p.restore()
        else:
            cw = (W - 2 * MARGIN - 6 * GAP) / 7.0
            top = MARGIN + TITLE_H + 4
            for i, name in enumerate(names):
                p.drawText(QRectF(MARGIN + i * (cw + GAP), top, cw, HEAD_H), Qt.AlignCenter, name)
        p.end()
