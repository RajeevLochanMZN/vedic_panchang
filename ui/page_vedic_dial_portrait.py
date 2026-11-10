"""
ui/page_vedic_dial_portrait.py  --  PORTRAIT layout of the dial home page (Pi 2).

Made for the Waveshare 7-inch screen used upright: 480 wide x 800 tall.
(Any other portrait screen works too: the whole layout is drawn on a 480x800
design grid and scaled by one factor, then centred.)

   +----------------------------------+
   | 09:37:47     [ DIAL 460 ]  27 अक्टू|   IST clock top-left, date top-right,
   |              (10 px margin)      |   in the free corners beside the ring
   |                                  |
   | (swastik)                (swastik)|   two swastik badges, lower corners
   | [ banner: samvat masa paksha tithi vara ]
   | [ LEFT  panel ]  [ RIGHT panel ] |   6 rows each
   | [ festival ]     [ eclipse card ]|
   +----------------------------------+

This file holds ONLY the layout (like page_vedic_dial.py does for landscape):
  PortraitLayoutMixin   replaces resizeEvent and set_data of VedicDialPage
  VedicDialPortraitPage the layout on its own, for the PC preview below
The LIVE page (real engine) is page_vedic_dial_portrait_hi.py, which puts the
same mixin on top of PageVedicDialHi, so Pi 1 keeps the landscape page.

What is different from the landscape page
  * IST clock and Gregorian date sit in the two top corners (no panel rows)
  * every right-panel row is TWO lines: caption + end time on the small line
    ("तिथि · 10 नव 06:30 तक"), the value underneath -- so the captions can be
    about 10 px instead of 7 px
  * the value text is bigger (about 17 px): see InfoPanel.val_frac_* settings

Preview on the PC (no engine needed):
    python ui/page_vedic_dial_portrait.py            # a 480x800 window
    python ui/page_vedic_dial_portrait.py empty      # swastik cards (no festival / eclipse)
    python ui/page_vedic_dial_portrait.py --save x.png   # write a picture and quit
    python ui/page_vedic_dial_portrait.py --check        # also print the sizes really in use
"""
import os
import sys

from PyQt5.QtCore import Qt, QRect, QRectF
from PyQt5.QtGui import QPainter, QPen, QFont, QFontMetrics, QPixmap

_HERE = os.path.dirname(os.path.abspath(__file__))

from page_vedic_dial import VedicDialPage
from info_panels import C_PANEL_BG, C_PANEL_EDGE, C_VALUE, SWASTIK_FILE, fit_font
from PyQt5.QtWidgets import QWidget

# ---------------------------------------------------------------- design grid
# Everything below is in pixels of a 480 x 800 screen; resizeEvent scales it.
DESIGN_W, DESIGN_H = 480, 800

DIAL_DIAMETER = 460          # visible ring
DIAL_TOP = 10                # empty space above the ring (also left and right: 10 px)

BANNER_Y, BANNER_H = 477, 26         # starts below the sunset tag on the ring
PANEL_Y, PANEL_H = 506, 190         # one-line rows need far less height than before
CARD_Y, CARD_H = 699, 72            # cards follow the panels (taller now: the strip at the bottom is used)
CARD_TITLE_PX, CARD_DETAIL_PX = 17, 14   # line 1 (aaj ka parv / grahan) and line 2 (date)
MARGIN, GAP = 6, 4

# corner boxes beside the ring (the circle leaves about 110 x 35 px free there)
IST_BOX = (4, 3, 104, 27)
DATE_BOX = (336, 3, 140, 27)     # wide enough for the longest date, "30 सितम्बर 2026"
IST_PX, DATE_PX = 19, 19     # bold text sizes: the date is the same size as the clock

# two swastik badges in the free lower corners beside the ring (x, y, width, height)
SWASTIK_L = (4, 412, 60, 60)
SWASTIK_R = (416, 412, 60, 60)

# Row heights, the SAME for both panels so the separator lines line up.
# 6 one-line rows in each panel.
ROW_WEIGHTS = [1.0] * 6          # 6 one-line rows in each panel

# Text size (px) of each row, top to bottom.  A line too wide for its panel still
# shrinks a little, so the long cases (a long nakshatra with a date) are never cut off.
SIZES_LEFT = [16, 16, 16, 15, 16, 18]   # sun, dinman, moon, RASHI, ayana, CITY
SIZES_RIGHT = [16, 16, 16, 16, 16, 18]  # tithi, nakshatra, yoga, karana, samvatsara, RITU


class CornerText(QWidget):
    """A small painted box with ONE bold line of text (the IST clock, the date)."""
    def __init__(self, font_family="Noto Sans Devanagari", parent=None):
        super().__init__(parent)
        self.font_family = font_family
        self.text = ""
        self.px = 16
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def set_text(self, text):
        if text != self.text:
            self.text = text
            self.update()

    def set_px(self, px):
        if px != self.px:
            self.px = px
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        p.setBrush(C_PANEL_BG)
        p.setPen(QPen(C_PANEL_EDGE, max(1.0, h * 0.04)))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), h * 0.25, h * 0.25)
        f = QFont(self.font_family)
        f.setBold(True)
        f.setPixelSize(max(6, int(self.px)))
        f = fit_font(f, self.text, w * 0.95)         # shrink only if the text is too wide
        p.setFont(f)
        p.setPen(C_VALUE)
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self.text)
        p.end()


class SwastikBadge(QWidget):
    """Round dark badge with the user's swastik picture (data/images/swastik.png),
    same colours as the panels, so it reads well on any background."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix = None            # original picture, loaded once
        self._scaled = None
        self._side = 0
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()
        p.setBrush(C_PANEL_BG)
        p.setPen(QPen(C_PANEL_EDGE, max(1.0, h * 0.03)))
        p.drawEllipse(QRectF(1, 1, w - 2, h - 2))
        if self._pix is None:
            self._pix = QPixmap(SWASTIK_FILE)
        side = int(min(w, h) * 0.66)
        if not self._pix.isNull() and side > 4:
            if self._scaled is None or self._side != side:
                self._scaled = self._pix.scaled(side, side, Qt.KeepAspectRatio,
                                                Qt.SmoothTransformation)
                self._side = side
            p.drawPixmap(int((w - side) / 2), int((h - side) / 2), self._scaled)
        p.end()


def _tithi_end_text(d):
    """End of the tithi for the caption line: '06:30' when it ends today, else
    '10 नव 06:30'.  Taken from d['tithi_range'] ('9 नव 10:30 से 10 नव 06:30 तक'),
    so the live page needs no change.  Falls back to the whole range."""
    rng = d.get("tithi_range", "")
    till = d["cap"]["till"]
    parts = rng.split()
    if len(parts) >= 8 and parts[-1] == till:
        end_day, end_month, end_time = parts[-4], parts[-3], parts[-2]
        today = d.get("date", "").split()[:1]
        if today and today[0] == end_day:
            return end_time
        return "%s %s %s" % (end_day, end_month, end_time)
    return rng


class PortraitLayoutMixin:
    """Put this BEFORE VedicDialPage in the class list:
           class X(PortraitLayoutMixin, VedicDialPage)
    It keeps VedicDialPage's widgets and methods and changes only how they are
    arranged and which rows they show."""

    # ------------------------------------------------------- one-time setup
    def _check_files(self):
        """The portrait page needs the NEW info_panels.py and dial_vedic.py.  If an
        old copy is in use, the sizes silently stay at the old values, so say so."""
        import inspect
        from info_panels import InfoPanel, CornerCard
        from dial_vedic import VedicDial
        old = []
        if "self.inline" not in inspect.getsource(InfoPanel.__init__):
            old.append("info_panels.py (side panels)")
        if "self.split" not in inspect.getsource(CornerCard.paintEvent):
            old.append("info_panels.py (festival / eclipse cards)")
        if "self.fill" not in inspect.getsource(VedicDial.__init__):
            old.append("dial_vedic.py")
        if old:
            sys.stderr.write("\n*** PORTRAIT PAGE: OLD FILE IN USE -> %s\n"
                             "*** copy the new ui/info_panels.py and ui/dial_vedic.py "
                             "(see INSTALL.txt)\n*** loaded from: %s\n\n"
                             % (", ".join(sorted(set(old))), os.path.dirname(
                                 os.path.abspath(inspect.getsourcefile(InfoPanel)))))

    def _portrait_setup(self):
        """Create the corner boxes and set the portrait sizes.  Called from
        set_data / resizeEvent, so it works whichever of them comes first."""
        if getattr(self, "_portrait_ready", False):
            return
        self._portrait_ready = True
        self._check_files()
        fam = self.dial.font_family
        self.corner_ist = CornerText(fam, self)
        self.corner_date = CornerText(fam, self)
        self.swastik_l = SwastikBadge(self)
        self.swastik_r = SwastikBadge(self)
        # the ring: 460 px wide in a 480 px square, 10 px from the top
        self.dial.fill = DIAL_DIAMETER / float(DESIGN_W)
        self.dial.top_margin = DIAL_TOP / float(DESIGN_W)
        # bigger text in the side panels (landscape values are in info_panels.py)
        for panel in (self.left, self.right):
            panel.inline = True               # one line per entry
            panel.inline_px_frac = 0.60       # text = 60% of the row height (about 17 px)
            panel.inline_min_px_multi = 15    # two-cell rows (rashi!) never go below 15 px
            panel.val_frac_multi = 0.068      # about 17 px on a 244 px panel
            panel.val_frac_single = 0.068
            panel.val_frac_line = 0.068
            panel.cap_min_ratio = 0.60        # captions about 10 px
            panel.cap_min_abs = 9.0
        # festival / eclipse cards: fixed text sizes.  The card draws a size as
        # (fraction of card height) cut to whole pixels, so add 0.01 px to be safe.
        for card in (self.fest_card, self.eclipse_card):
            card.title_frac = (CARD_TITLE_PX + 0.01) / CARD_H
            card.detail_frac = (CARD_DETAIL_PX + 0.01) / CARD_H
            card.split = 0.40               # line 1 on top, line 2 (up to 2 lines) below
            card.font_independent = True    # do not let the font's own line height shrink the text

    # ------------------------------------------------------------- data in
    def set_data(self, d):
        """Same dict as VedicDialPage.set_data, shown differently."""
        self._portrait_setup()
        c = d["cap"]
        till = c["till"]                      # the word "तक"
        self.corner_ist.set_text(d["ist_time"])
        self.corner_date.set_text(d["date"])
        # every cell is ONE line: "caption : value"  (+ small end time)
        self.left.set_rows([
            [(c["sunrise"], d["sunrise"]),     (c["sunset"], d["sunset"])],
            [(c["dinman"], d["dinman"]),       (c["ratriman"], d["ratriman"])],
            [(c["moonrise"], d["moonrise"]),   (c["moonset"], d["moonset"])],
            [(c["sun_rashi"], d["sun_rashi"]), (c["moon_rashi"], d["moon_rashi"])],
            [(c["ayana"], d["ayana"])],
            [("", d["city"])],                         # no caption
        ], ROW_WEIGHTS, SIZES_LEFT)
        self.right.set_rows([
            [(c["tithi"], d["tithi"], "%s %s" % (_tithi_end_text(d), till))],
            [(c["nakshatra"], d["nakshatra"], "%s %s" % (d["nakshatra_end"], till))],
            [(c["yoga"], d["yoga"], "%s %s" % (d["yoga_end"], till))],
            [(c["karana"], d["karana"], "%s %s" % (d["karana_end"], till))],
            [(c["samvatsara"], d["samvatsara"])],
            [("", d["ritu"])],                         # no caption, e.g. "शरद ऋतु"
        ], ROW_WEIGHTS, SIZES_RIGHT)
        # banner: samvat, masa, paksha, TITHI, weekday
        line1 = "%s  %s  %s  %s  %s" % (d["samvat"], d["masa"], d["paksha"],
                                        d["tithi"], d["weekday"])
        self.banner.set_lines(line1, [])

    # ------------------------------------------------------------- layout
    def resizeEvent(self, event):
        self._portrait_setup()
        W, H = self.width(), self.height()
        # one scale factor.  The height that matters is the part really used (to the bottom of the
        # cards), not the full 800: with square pixels on a panel that needs a shorter page
        # (e.g. 480 x 743) the whole layout then shrinks a little instead of being cut off.
        used_h = CARD_Y + CARD_H + 1
        u = min(W / float(DESIGN_W), H / float(used_h))
        ox = (W - DESIGN_W * u) / 2.0                           # centre sideways if not exactly 3:5
        oy = 0.0                                                # any extra height stays at the BOTTOM

        def rect(x, y, w, h):
            return QRect(int(round(ox + x * u)), int(round(oy + y * u)),
                         int(round(w * u)), int(round(h * u)))

        # dial widget = a 480 x 480 square at the top; the dial draws its own margins
        self.dial.setGeometry(rect(0, 0, DESIGN_W, DESIGN_W))

        self.corner_ist.setGeometry(rect(*IST_BOX))
        self.corner_date.setGeometry(rect(*DATE_BOX))
        self.corner_ist.set_px(IST_PX * u)
        self.corner_date.set_px(DATE_PX * u)
        self.corner_ist.raise_()
        self.corner_date.raise_()
        self.swastik_l.setGeometry(rect(*SWASTIK_L))
        self.swastik_r.setGeometry(rect(*SWASTIK_R))

        side_w = (DESIGN_W - 2 * MARGIN - GAP) / 2.0
        xl, xr = MARGIN, MARGIN + side_w + GAP
        self.banner.setGeometry(rect(MARGIN, BANNER_Y, DESIGN_W - 2 * MARGIN, BANNER_H))
        self.left.setGeometry(rect(xl, PANEL_Y, side_w, PANEL_H))
        self.right.setGeometry(rect(xr, PANEL_Y, side_w, PANEL_H))
        self.fest_card.setGeometry(rect(xl, CARD_Y, side_w, CARD_H))
        self.eclipse_card.setGeometry(rect(xr, CARD_Y, side_w, CARD_H))
        # skip VedicDialPage.resizeEvent (it is the LANDSCAPE layout); go on to
        # the background's own resize handling
        super(VedicDialPage, self).resizeEvent(event)


class VedicDialPortraitPage(PortraitLayoutMixin, VedicDialPage):
    """The portrait layout on its own (sample data, PC preview)."""
    pass


# =============================================================================
# PC preview with sample data (no engine, no GPIO)
# =============================================================================
SAMPLE = {
    "cap": {
        "ist": "भारतीय मानक समय", "date": "दिनांक",
        "sunrise": "सूर्योदय", "sunset": "सूर्यास्त",
        "dinman": "दिनमान", "ratriman": "रात्रिमान",
        "moonrise": "चन्द्रोदय", "moonset": "चन्द्रास्त",
        "sun_rashi": "सूर्य राशि", "moon_rashi": "चन्द्र राशि",
        "tithi": "तिथि", "nakshatra": "नक्षत्र", "yoga": "योग", "karana": "करण",
        "ayana": "अयन", "samvatsara": "संवत्सर", "till": "तक", "city": "", "ritu": "",
    },
    "ist_time": "10:20:07", "date": "27 अक्टूबर 2026",
    "sunrise": "06:29", "sunset": "17:52", "dinman": "11:23", "ratriman": "12:37",
    "moonrise": "18:37", "moonset": "07:30",
    "sun_rashi": "तुला", "moon_rashi": "मेष",
    "tithi": "द्वितीया", "tithi_range": "27 अक्टू 10:30 से 28 अक्टू 06:30 तक",
    "nakshatra": "भरणी", "nakshatra_end": "21:05",
    "yoga": "सिद्धि", "yoga_end": "13:30",
    "karana": "बालव", "karana_end": "07:55",
    "samvat": "विक्रम संवत् 2083", "masa": "कार्तिक", "paksha": "कृष्ण पक्ष",
    "weekday": "मंगलवार", "ritu": "शरद ऋतु", "samvatsara": "सिद्धार्थी",
    "ayana": "दक्षिणायन", "city": "मुज़फ़्फ़रनगर",
}

if __name__ == "__main__":
    from PyQt5.QtGui import QFontDatabase
    from PyQt5.QtWidgets import QApplication

    args = sys.argv[1:]
    save_to = args[args.index("--save") + 1] if "--save" in args else None
    app = QApplication(sys.argv)
    for name in ("NotoSansDevanagari-Regular.ttf", "NotoSansDevanagari-Bold.ttf"):
        QFontDatabase.addApplicationFont(os.path.join(_HERE, "..", "data", "fonts", name))

    page = VedicDialPortraitPage(font_family="Noto Sans Devanagari")
    page.resize(480, 800)
    page.set_data(SAMPLE)
    page.set_dial(9 * 60 / 24.0 + 6.0, 28.4)          # a morning time; day = 28.4 ghati
    if "empty" in args:
        page.set_notices(None, None)
    else:
        page.set_notices(("आज का पर्व : दीपावली", "9/10 नवम्बर"),
                         ("चन्द्र ग्रहण", "28 अगस्त 2026, 09:12 से 10:48 तक"))
    page.setWindowTitle("Portrait dial page (preview)")
    page.show()
    if "--check" in args:
        app.processEvents()
        W, H = page.width(), page.height()
        u = min(W / 480.0, H / 800.0)
        sc = app.primaryScreen()
        print("window now      : %d x %d   (asked for 480 x 800)" % (W, H))
        print("scale factor    : %.3f   (1.000 = exact 480x800 design)" % u)
        print("screen (logical): %d x %d   devicePixelRatio %.2f   dpi %.0f" % (
            sc.availableGeometry().width(), sc.availableGeometry().height(),
            sc.devicePixelRatio(), sc.logicalDotsPerInch()))
        for name, card in (("festival card", page.fest_card), ("eclipse card ", page.eclipse_card)):
            print("%s: %d x %d px   line 1 = %d px   line 2 = %d px" % (
                name, card.width(), card.height(),
                int(card.height() * card.title_frac), int(card.height() * card.detail_frac)))
        for name, panel in (("left panel ", page.left), ("right panel", page.right)):
            print("%s: %d x %d px   row sizes %s" % (name, panel.width(), panel.height(),
                                                    panel.sizes))
        import inspect, info_panels
        print("info_panels.py  :", os.path.abspath(inspect.getsourcefile(info_panels)))
    if save_to:
        app.processEvents()
        page.grab().save(save_to)
        sys.exit(0)
    sys.exit(app.exec_())
