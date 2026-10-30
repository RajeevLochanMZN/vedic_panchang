"""
ui/page_vedic_dial.py  --  the NEW dial home page (the old Home page is untouched).

   +--------------------------------------------------------------+
   |  [ LEFT PANEL ]        (   VEDIC DIAL   )      [ RIGHT PANEL ] |
   |  sun & moon times                                 panchang      |
   | [festival card]  [ bottom banner: date line ]  [eclipse card]   |
   +--------------------------------------------------------------+

The page only DISPLAYS.  Someone else (the engine glue, later) calls
    page.set_dial(elapsed_ghati, day_ghati)      # ~10 times a second
    page.set_data(data)                          # once a second is plenty
`data` is a plain dict of already-translated strings (see SAMPLE in
dial_preview.py for every key).

Layout is done by hand in resizeEvent so it follows the dial exactly:
  * the dial widget is a square as tall as the page, centred
  * the panels fill the free space either side of the dial's ring
  * the banner sits in the bottom margin under the dial
"""
from PyQt5.QtCore import QRect

from background import BackgroundWidget
from dial_vedic import VedicDial, DIAL_FILL, DIAL_TOP_MARGIN
from info_panels import InfoPanel, BannerBar, CornerCard


# Relative row heights, the SAME for both panels so that the separator lines of
# the left and right panel sit at exactly the same height.
#                  1st    2nd-5th rows           6th   7th (one compact line)
ROW_WEIGHTS = [0.90, 1.12, 1.12, 1.12, 1.12, 0.90, 0.60]


class VedicDialPage(BackgroundWidget):
    def __init__(self, font_family="Noto Sans Devanagari", parent=None):
        super().__init__(parent)
        self.dial = VedicDial(font_family=font_family, parent=self)
        self.left = InfoPanel(font_family, self)
        self.right = InfoPanel(font_family, self)
        self.banner = BannerBar(font_family, self)
        self.fest_card = CornerCard(font_family, self)     # bottom-left
        self.eclipse_card = CornerCard(font_family, self)   # bottom-right

    # ------------------------------------------------------------- data in
    def set_dial(self, elapsed_ghati, day_ghati):
        self.dial.set_time(elapsed_ghati, day_ghati)

    def set_data(self, d):
        """d: dict of strings.  Keys:
        sunrise sunset dinman ratriman moonrise moonset sun_rashi moon_rashi
        tithi nakshatra yoga karana (+ _end for each)  |  samvat masa paksha
        weekday ritu samvatsara ayana date city  |  ist_time  |  tithi_range
        (+ the captions in d['cap'], see SAMPLE in dial_preview.py)"""
        c = d["cap"]
        till = c["till"]                      # the word "तक"
        self.left.set_rows([
            # IST as a digital clock (HH:MM:SS), full width, top of the panel
            [(c["ist"], d["ist_time"])],
            [(c["sunrise"], d["sunrise"]),   (c["sunset"], d["sunset"])],
            [(c["dinman"], d["dinman"]),     (c["ratriman"], d["ratriman"])],
            [(c["moonrise"], d["moonrise"]), (c["moonset"], d["moonset"])],
            [(c["sun_rashi"], d["sun_rashi"]), (c["moon_rashi"], d["moon_rashi"])],
            [(c["ayana"], d["ayana"])],
            [("", d["city"])],                       # one compact line, no caption
        ], ROW_WEIGHTS)
        self.right.set_rows([
            # Gregorian date at the top, mirroring the IST clock on the left
            [(c["date"], d["date"])],
            # tithi shows its full range with dates, e.g. "9 नव॰ 10:30 से 10 नव॰ 06:30 तक"
            [(c["tithi"], d["tithi"], d["tithi_range"])],
            [(c["nakshatra"], d["nakshatra"], "%s %s" % (d["nakshatra_end"], till))],
            [(c["yoga"], d["yoga"], "%s %s" % (d["yoga_end"], till))],
            [(c["karana"], d["karana"], "%s %s" % (d["karana_end"], till))],
            [(c["samvatsara"], d["samvatsara"])],
            [("", d["ritu"])],                       # one compact line, e.g. "शरद ऋतु"
        ], ROW_WEIGHTS)
        # banner: one big line = samvat, masa, paksha, weekday
        line1 = "%s  %s  %s  %s" % (d["samvat"], d["masa"], d["paksha"], d["weekday"])
        self.banner.set_lines(line1, [])

    def set_notices(self, festival=None, eclipse=None):
        """Each is (line1, line2) or None.  None / empty line1 = nothing to
        announce, and the card shows a swastik symbol instead.
        festival, today's, normal day : ("आज का पर्व : दीपावली", "")
        festival, today's, on a tie   : ("आज का पर्व : दीपावली", "9/10 नवम्बर")
        festival, coming in <= 2 days : ("अगला पर्व : दीपावली", "9 नवम्बर")
        no festival within 2 days     : None   (swastik)
        eclipse                       : ("चन्द्र ग्रहण", "28 अगस्त, 09:12 से 10:48 तक") or None"""
        self.fest_card.set_content(*(festival or ("", "")))
        self.eclipse_card.set_content(*(eclipse or ("", "")))

    def set_marked_spans(self, abhijit=None, brahma=None):
        """Pass-through to the dial (Abhijit / Brahma muhurta arcs)."""
        self.dial.set_marked_spans(abhijit, brahma)

    # ------------------------------------------------------------- layout
    def resizeEvent(self, event):
        W, H = self.width(), self.height()
        # dial: a square, full height, centred.  It draws its own margins.
        self.dial.setGeometry((W - H) // 2, 0, H, H)

        ring_d = DIAL_FILL * H                      # visible diameter of the dial
        m = int(0.02 * W)                           # outer margin
        gap = int(0.02 * W)                         # gap between panel and ring
        side_w = int((W - ring_d) / 2 - m - gap)
        side_w = max(100, min(side_w, int(0.27 * W)))
        top = int(DIAL_TOP_MARGIN * H)
        ph = int(ring_d)                            # panels as tall as the ring
        self.left.setGeometry(m, top, side_w, ph)
        self.right.setGeometry(W - m - side_w, top, side_w, ph)

        # bottom strip: the two cards are exactly as wide as the side panels,
        # and the banner takes the space left between them
        by = int(0.910 * H)
        bh = int(0.085 * H)
        self.fest_card.setGeometry(m, by, side_w, bh)
        self.eclipse_card.setGeometry(W - m - side_w, by, side_w, bh)
        bx = m + side_w + gap // 2
        self.banner.setGeometry(bx, by, W - 2 * bx, bh)
        super().resizeEvent(event)
