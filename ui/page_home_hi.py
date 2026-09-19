"""
ui/page_home_hi.py

Hindi/Devanagari twin of page_home.py. SEPARATE FILE -- page_home.py
is not modified or imported here; this is a standalone page with the
exact same layout, colors, spacing, and refresh logic, just with
headings and value text rendered in Devanagari via translations_hi.py.

NUMERALS: all numbers (clock digits, dates, Vikram Samvat year,
Ghati/Pal/Vipal, muhurta's "4/15", etc.) intentionally stay in
international form (0-9) -- see translations_hi.py's module docstring.

FONT: loads the bundled Devanagari font once via
translations_hi.get_devanagari_font_family() and appends
`font-family: '<name>';` to every label's stylesheet through the
self._f() helper below, so every string in this page (Hindi or the
0-9 numerals) renders in that font consistently.

Everything else -- the two-tier refresh timers, the Pahar background
animation, the contrast-color logic, the panel split ratios -- is
identical to page_home.py; only text content and font-family are
different. See page_home.py's own docstring for the general
architecture notes (resolution scaling, refresh cadence, etc.).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel,
)
from PyQt5.QtCore import QTimer, Qt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

from ephemeris import init_ephemeris, datetime_to_julday
from panchang import get_tithi_details
from masa import get_masa_details, get_purnimanta_masa_name, get_paksha, get_vikram_samvat_year, get_samvatsara_name, get_ritu
from time_systems import get_ist, get_gmt, get_lmt, get_vedic_time, get_vara
from sun_times import get_sun_times_details, get_local_midnight_jd_ut, get_sunrise_jd
from muhurta import get_muhurta_details, get_pahar_details
from festivals import get_todays_festivals
from config_loader import get_location, load_settings, load_page_layout
from scaling import px
from eclipse_banner import get_eclipse_display_info

from translations_hi import (
    HEADINGS_HI, CAPTION_IST, CAPTION_VEDIC_TIME, CAPTION_GHATI, CAPTION_PAL,
    CAPTION_VIPAL, CAPTION_GMT, CAPTION_LMT, PHRASE_TODAY, PHRASE_TILL,
    PHRASE_DAY_NIGHT, PHRASE_TO, LABEL_ECLIPSE_WORD, PHRASE_NOT_VISIBLE_TEMPLATE,
    translate_value, translate_masa, translate_weekday, translate_month,
    translate_location, translate_eclipse_type, hi_date_short,
    get_devanagari_font_family,
)

IST_OFFSET = timedelta(hours=5, minutes=30)

# Same stretch ratios as page_home.py -- keeps the 50:50 panel split
# identical between the English and Hindi builds.
LEFT_WIDTH_BASELINE = 500
RIGHT_WIDTH_BASELINE = 500


def _format_clock_style(vedic: dict) -> str:
    """Ghati/Pal/Vipal as a clock-style 'GG:PP:VV' string -- numerals
    stay international form, unchanged from page_home.py."""
    return f"{vedic['ghati']:02d}:{vedic['pal']:02d}:{vedic['vipal']:02d}"


def _format_tithi_end(ist_string: str) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS IST' into 'DD <Hindi month> HH:MM:SS'
    -- day number and time stay international-numeral, only the month
    name is translated (via strftime('%B'), which always returns the
    English month name regardless of locale, then looked up)."""
    dt = datetime.strptime(ist_string, "%Y-%m-%d %H:%M:%S IST")
    month_hi = translate_month(dt.strftime("%B"))
    return f"{dt.strftime('%d')} {month_hi} {dt.strftime('%H:%M:%S')}"


# =============================================================================
# Animated background -- identical colors/logic to page_home.py, since
# this was purely a visual choice unrelated to language.
# =============================================================================

PAHAR_COLORS = [
    (168, 200, 224),  # 0 Purvahna  -- soft morning blue
    (74, 144, 217),   # 1 Madhyahna -- bright sky blue
    (232, 169, 74),   # 2 Aparahna  -- warm golden
    (217, 98, 42),    # 3 Sayahna   -- orange sunset
    (125, 46, 70),    # 4 Pradosh   -- dusk maroon-purple
    (20, 20, 42),     # 5 Nishitha  -- deep midnight
    (26, 26, 62),     # 6 Trijama   -- deep blue-black
    (26, 47, 92),     # 7 Ushakal   -- pre-dawn blue
]


def _get_pahar_index_and_fraction(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd):
    """Unchanged from page_home.py -- see that file for full notes."""
    if sunrise_jd <= jd_now <= sunset_jd:
        span_start, span_end, base_index = sunrise_jd, sunset_jd, 0
    else:
        span_start, span_end, base_index = sunset_jd, next_sunrise_jd, 4

    span_duration = span_end - span_start
    quarter = span_duration / 4.0
    elapsed = jd_now - span_start
    pahar_offset = elapsed / quarter if quarter > 0 else 0.0
    pahar_offset = max(0.0, min(pahar_offset, 3.999))

    current_index = base_index + int(pahar_offset)
    fraction = pahar_offset - int(pahar_offset)
    next_index = (current_index + 1) % 8
    return current_index, next_index, fraction


def _interpolate_color(c1, c2, t: float) -> str:
    r = int(c1[0] + (c2[0] - c1[0]) * t)
    g = int(c1[1] + (c2[1] - c1[1]) * t)
    b = int(c1[2] + (c2[2] - c1[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _contrast_text_color(r: int, g: int, b: int) -> str:
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#1a1a2e" if luminance > 150 else "#f5f5f5"


def _contrast_caption_color(r: int, g: int, b: int) -> str:
    """
    Color for the secondary caption labels (IST / VEDIC TIME / GHATI /
    PAL / VIPAL / GMT / LMT). Mirrors page_home.py's fix for the same
    bug: a fixed #999999 gray read fine on the darker Pahars but
    washed out against the lighter ones (Aparahna's gold, Purvahna's
    soft blue). Derived from the same live background
    _contrast_text_color() uses, blended partway toward the
    background so it still reads as secondary next to the bold
    primary clock digits, but stays legible on every Pahar.
    """
    primary_hex = _contrast_text_color(r, g, b)
    pr = int(primary_hex[1:3], 16)
    pg = int(primary_hex[3:5], 16)
    pb = int(primary_hex[5:7], 16)
    blend = 0.62
    cr = int(pr * blend + r * (1 - blend))
    cg = int(pg * blend + g * (1 - blend))
    cb = int(pb * blend + b * (1 - blend))
    return f"#{cr:02x}{cg:02x}{cb:02x}"


class PageHomeHi(QWidget):
    def __init__(self):
        super().__init__()
        self.lat, self.lon = get_location()
        self._cached_sunrise_jd = None
        self._cached_sunrise_jd_yesterday = None
        self._cached_sunrise_jd_prev_day_actual = None
        self._cached_sunset_jd = None
        self._cached_next_sunrise_jd = None

        # Load the bundled Devanagari font once (requires QApplication
        # to already exist -- true here since instantiation happens
        # after QApplication(sys.argv), same as page_home.py).
        self.font_family = get_devanagari_font_family()

        self._build_ui()

        self.fast_timer = QTimer(self)
        self.fast_timer.timeout.connect(self._update_fast)
        self.fast_timer.start(1000)

        self.slow_timer = QTimer(self)
        self.slow_timer.timeout.connect(self._update_slow)
        self.slow_timer.start(60 * 1000)

        self.eclipse_timer = QTimer(self)
        self.eclipse_timer.timeout.connect(self._update_eclipse)
        self.eclipse_timer.start(60 * 60 * 1000)

        self._update_slow()
        self._update_fast()
        self._update_eclipse()

    # -------------------------------------------------------------------
    # Small helper: appends this page's Devanagari font-family to any
    # stylesheet string, so every QLabel below stays a one-line call
    # (self._f(f"font-size: {px(36)}px; ...")) instead of repeating
    # the font-family declaration by hand everywhere.
    # -------------------------------------------------------------------

    def _f(self, css: str) -> str:
        return css + f" font-family: '{self.font_family}';"

    # -------------------------------------------------------------------
    # UI layout -- identical structure/colors/spacing to page_home.py
    # -------------------------------------------------------------------

    def _build_ui(self):
        # No self._f() here -- this is a pure background/color
        # container, it renders no text of its own. This mattered more
        # than it looked: Qt Style Sheets INHERIT font-family down to
        # any descendant that doesn't declare its own (verified) --
        # so leaving it here was silently re-applying the Devanagari
        # font to every "plain" label below (digits, IST/GMT/LMT,
        # location) that deliberately omits its own font-family,
        # completely undoing that earlier fix and causing the digit
        # clipping (Noto Sans Devanagari's taller metrics at 96px bold
        # exceeding the label's computed box).
        self.setStyleSheet("background-color: #1a1a2e; color: white;")
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left = self._build_left_panel()
        right = self._build_right_panel()

        outer.addWidget(left, LEFT_WIDTH_BASELINE)
        outer.addWidget(right, RIGHT_WIDTH_BASELINE)
        self.setLayout(outer)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        self.left_panel = panel
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        # Zeroes out Qt's own default inter-widget spacing (which was
        # silently adding ~6px on TOP of every addSpacing() call below,
        # discovered while measuring the real minimum gaps). With this
        # set, every addSpacing(pxN) below now produces exactly pxN of
        # visual gap -- no hidden extra. This makes the whole panel
        # slightly more compact overall (every existing gap tightens
        # by that same ~6px), not just the two gaps below.
        layout.setSpacing(0)
        # Reduced from px(20) -- shifts the whole IST/Vedic Time block
        # upward to make room below for the taller Devanagari line-
        # heights added elsewhere in this panel (see the px(15)/px(9)
        # anti-overlap gaps added just below). Hindi-only; page_home.py
        # keeps its original px(20).
        layout.setContentsMargins(0, px(4), 0, 0)

        ist_heading = QLabel(CAPTION_IST)
        ist_heading.setAlignment(Qt.AlignCenter)
        # No Devanagari font here -- "IST" is a kept Roman abbreviation
        # (see translations_hi.py), so it doesn't need it, and the
        # Devanagari font's taller line-height only cost vertical space
        # here for nothing. Same reasoning applies to every label below
        # marked "plain font".
        ist_heading.setStyleSheet(f"font-size: {px(36)}px; font-weight: bold;")
        layout.addWidget(ist_heading)

        self.ist_label = QLabel("--:--:--")  # plain font -- digits only
        self.ist_label.setAlignment(Qt.AlignCenter)
        self.ist_label.setStyleSheet(f"font-size: {px(96)}px; font-weight: bold;")
        layout.addWidget(self.ist_label)

        # Reduced further (18 -> 3) to shift the whole Vedic Time
        # block (heading + digit row) up ~15px as a unit, per request.
        # The px(15) gap below vedic_heading (further down) is
        # untouched -- that one fixes the earlier heading/row overlap
        # and shouldn't shrink back.
        layout.addSpacing(px(3))

        vedic_heading = QLabel(CAPTION_VEDIC_TIME)
        vedic_heading.setAlignment(Qt.AlignCenter)
        # "वैदिक समय" is real Devanagari text -- this one keeps the font.
        vedic_heading.setStyleSheet(self._f(f"font-size: {px(36)}px; font-weight: bold;"))
        layout.addWidget(vedic_heading)

        # Verified with the real bundled font (see chat) that even a
        # true 0px gap here doesn't cause any visual touching -- both
        # labels have real unused padding inside their own boxes
        # (heading: ~10px, digit: ~39px) beyond what their rendered
        # glyphs actually use.
        layout.addSpacing(0)

        vedic_row = QHBoxLayout()
        vedic_row.setSpacing(px(6))
        vedic_row.setAlignment(Qt.AlignCenter)

        self.clock_value_labels = [(self.ist_label, 96)]
        # See page_home.py's identical comment: captions get their own
        # dynamically-updated, muted-but-legible color (via
        # _contrast_caption_color) instead of the old fixed gray.
        self.clock_caption_labels = [(ist_heading, 36, "bold", False), (vedic_heading, 36, "bold", True)]

        def _build_vedic_col(caption_text: str):
            col = QVBoxLayout()
            # Verified 0px is safe here too, same reasoning as above.
            col.setSpacing(0)
            value_label = QLabel("--")  # plain font -- digits only
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setStyleSheet(f"font-size: {px(96)}px; font-weight: bold;")
            col.addWidget(value_label)
            caption_label = QLabel(caption_text)
            caption_label.setAlignment(Qt.AlignCenter)
            # घटी/पल/विपल are real Devanagari text -- keeps the font.
            caption_label.setStyleSheet(self._f(f"font-size: {px(24)}px; font-weight: normal;"))
            col.addWidget(caption_label)
            self.clock_value_labels.append((value_label, 96))
            self.clock_caption_labels.append((caption_label, 24, "normal", True))
            return col, value_label

        def _build_colon_col():
            col = QVBoxLayout()
            # Matches _build_vedic_col's spacing exactly (now 0) -- see
            # below, this column's second row also matches that one's
            # height, which is what keeps the colon/digit alignment
            # correct.
            col.setSpacing(0)
            colon_label = QLabel(":")  # plain font -- punctuation only
            colon_label.setAlignment(Qt.AlignCenter)
            colon_label.setStyleSheet(f"font-size: {px(96)}px; font-weight: bold;")
            col.addWidget(colon_label)
            # Was an unstyled empty QLabel before -- its natural height
            # (Qt's small default label font) didn't match the digit
            # columns' second row (a real 24px caption), so this
            # column's total height differed from its neighbors' and
            # the colon ended up sitting at a different vertical
            # position than the digits beside it. Giving it the exact
            # same font-size (blank text, so nothing renders) makes
            # every column in this row structurally identical, which
            # is what keeps the colon's baseline lined up with the
            # digits'.
            spacer_label = QLabel("")
            spacer_label.setAlignment(Qt.AlignCenter)
            spacer_label.setStyleSheet(f"font-size: {px(24)}px; font-weight: normal;")
            col.addWidget(spacer_label)
            self.clock_value_labels.append((colon_label, 96))
            return col

        ghati_col, self.ghati_label = _build_vedic_col(CAPTION_GHATI)
        pal_col, self.pal_label = _build_vedic_col(CAPTION_PAL)
        vipal_col, self.vipal_label = _build_vedic_col(CAPTION_VIPAL)

        vedic_row.addLayout(ghati_col)
        vedic_row.addLayout(_build_colon_col())
        vedic_row.addLayout(pal_col)
        vedic_row.addLayout(_build_colon_col())
        vedic_row.addLayout(vipal_col)

        layout.addLayout(vedic_row)

        # Trimmed from px(30)+px(10)=40 -- these were purely decorative
        # spacing (not fixing any specific overlap), tuned for
        # English's shorter total content. With them at full size,
        # total left-panel content was JUST slightly taller than the
        # window, which doesn't push the last widget off-screen -- it
        # makes Qt quietly compress several labels below their natural
        # height instead, clipping the bottom off the big 96px digits
        # (38/30/19 etc.) without anything visibly overflowing. Cutting
        # this to px(16) frees genuine slack so nothing needs to be
        # compressed.
        layout.addSpacing(px(16))

        gmt_lmt_row = QHBoxLayout()
        gmt_lmt_row.setSpacing(px(70))

        gmt_col = QVBoxLayout()
        gmt_col.setSpacing(0)
        gmt_heading = QLabel(CAPTION_GMT)  # plain font -- "GMT" is Roman
        gmt_heading.setAlignment(Qt.AlignCenter)
        gmt_heading.setStyleSheet(f"font-size: {px(24)}px; font-weight: bold;")
        gmt_col.addWidget(gmt_heading)
        gmt_col.addSpacing(px(10))
        self.gmt_label = QLabel("--:--:--")  # plain font -- digits only
        self.gmt_label.setAlignment(Qt.AlignCenter)
        self.gmt_label.setStyleSheet(f"font-size: {px(50)}px;")
        gmt_col.addWidget(self.gmt_label)
        self.clock_value_labels.append((self.gmt_label, 50))
        self.clock_caption_labels.append((gmt_heading, 24, "bold", False))

        lmt_col = QVBoxLayout()
        lmt_col.setSpacing(0)
        lmt_heading = QLabel(CAPTION_LMT)  # plain font -- "LMT" is Roman
        lmt_heading.setAlignment(Qt.AlignCenter)
        lmt_heading.setStyleSheet(f"font-size: {px(24)}px; font-weight: bold;")
        lmt_col.addWidget(lmt_heading)
        lmt_col.addSpacing(px(10))
        self.lmt_label = QLabel("--:--:--")  # plain font -- digits only
        self.lmt_label.setAlignment(Qt.AlignCenter)
        self.lmt_label.setStyleSheet(f"font-size: {px(50)}px;")
        lmt_col.addWidget(self.lmt_label)
        self.clock_value_labels.append((self.lmt_label, 50))
        self.clock_caption_labels.append((lmt_heading, 24, "bold", False))

        gmt_lmt_row.addLayout(gmt_col)
        gmt_lmt_row.addLayout(lmt_col)
        layout.addLayout(gmt_lmt_row)

        # Increased from px(18) -- moves the city name down a bit,
        # per request.
        layout.addSpacing(px(30))
        settings = load_settings()
        # Location name is user-configured free text (settings.yaml),
        # not a fixed engine enum -- LOCATION_HI in translations_hi.py
        # is a small lookup table you extend as needed (currently just
        # "Ujjain"); falls back to the English name if not listed.
        # Now genuinely Devanagari text, so self._f() is back here.
        location_name = settings.get("location", {}).get("name", "")
        self.location_name = location_name  # kept in English internally (used elsewhere, e.g. eclipse "not visible at" text)
        self.location_label = QLabel(translate_location(location_name))
        self.location_label.setAlignment(Qt.AlignCenter)
        self.location_label.setStyleSheet(self._f(f"font-size: {px(32)}px; font-weight: bold;"))
        layout.addWidget(self.location_label)

        panel.setLayout(layout)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        # No self._f() here either -- every label inside this panel
        # already sets its own font-family explicitly (right panel is
        # all genuine Devanagari content), so this declaration was
        # redundant. Removed for consistency with the left panel fix
        # and to avoid the same inheritance trap for any future label
        # added here without its own explicit font-family.
        panel.setStyleSheet("background-color: #14142a;")
        layout = QVBoxLayout()
        # Top margin reduced from px(16) -- part of shifting the whole
        # block up ~50px+, per request (combined with removing the
        # separate day_label line and the tighter gap below).
        layout.setContentsMargins(px(16), px(2), px(16), px(16))
        layout.setSpacing(px(10))

        # Combined into one line ("12 सितंबर 2026, शनिवार") instead of
        # two separate date_label/day_label widgets, per request --
        # also removes a full line + its inter-widget gap, which is
        # most of what shifts everything below upward.
        self.date_label = QLabel("...")
        self.date_label.setAlignment(Qt.AlignCenter)
        self.date_label.setWordWrap(True)
        self.date_label.setStyleSheet(self._f(f"font-size: {px(32)}px; font-weight: bold;"))
        layout.addWidget(self.date_label)

        # Reduced from px(15) -- the rest of the requested upward shift.
        layout.addSpacing(0)

        self.field_labels = {}
        # Same page_layout.yaml page_home order/keys as the English
        # page -- only the displayed heading text differs (HEADINGS_HI
        # instead of the YAML's own `heading` value), so the layout
        # config itself doesn't need a Hindi copy.
        fields = [(f["key"], HEADINGS_HI.get(f["key"], f["heading"])) for f in load_page_layout()["page_home"]]

        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(px(25))
        field_grid.setVerticalSpacing(px(6))
        field_grid.setColumnStretch(2, 1)

        row = 0
        for field, label_text in fields:
            heading = QLabel(label_text)
            heading.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            heading.setStyleSheet(self._f(f"font-size: {px(22)}px;"))
            field_grid.addWidget(heading, row, 0)

            colon = QLabel(":")
            colon.setStyleSheet(self._f(f"font-size: {px(22)}px;"))
            field_grid.addWidget(colon, row, 1)

            value = QLabel("...")
            value.setWordWrap(True)
            value.setStyleSheet(self._f(f"font-size: {px(22)}px; padding-left: {px(20)}px;"))
            field_grid.addWidget(value, row, 2)
            self.field_labels[field] = value
            row += 1

            if field == "tithi":
                till_label = QLabel("")
                till_label.setWordWrap(True)
                till_label.setStyleSheet(self._f(f"font-size: {px(18)}px; padding-left: {px(20)}px;"))
                field_grid.addWidget(till_label, row, 1, 1, 2)
                self.field_labels["tithi_till"] = till_label
                row += 1

        # Shift the whole field grid (headings + colons + values)
        # right by at least 100px, per request -- the combined date
        # line above stays centered as before, only this grid moves.
        # Wrapped in its own row with a left spacer rather than
        # changing the panel's own left margin (which would've shifted
        # the centered date line too).
        field_row = QHBoxLayout()
        field_row.addSpacing(px(100))
        field_row.addLayout(field_grid)
        layout.addLayout(field_row)

        layout.addStretch()

        self.festival_label = QLabel("")
        self.festival_label.setAlignment(Qt.AlignCenter)
        self.festival_label.setStyleSheet(self._f(
            f"font-size: {px(20)}px; font-weight: bold; color: #2ecc71; "
            f"background-color: #0f3d2e; border-radius: {px(8)}px; padding: {px(10)}px;"
        ))
        self.festival_label.setWordWrap(True)
        layout.addWidget(self.festival_label)

        self.eclipse_label = QLabel("")
        self.eclipse_label.setAlignment(Qt.AlignCenter)
        self.eclipse_label.setStyleSheet(self._f(
            f"font-size: {px(20)}px; font-weight: bold; color: #ff7043; "
            f"background-color: #3d1f0f; border-radius: {px(8)}px; padding: {px(10)}px;"
        ))
        self.eclipse_label.setWordWrap(True)
        layout.addWidget(self.eclipse_label)

        panel.setLayout(layout)
        return panel

    # -------------------------------------------------------------------
    # Fast refresh -- live clock only. Numerals stay international
    # form throughout, identical to page_home.py.
    # -------------------------------------------------------------------

    def _update_fast(self):
        now_utc = datetime.now(timezone.utc)
        now_ist = get_ist(now_utc)
        now_gmt = get_gmt(now_utc)
        now_lmt = get_lmt(now_utc, self.lon)

        self.ist_label.setText(now_ist.strftime("%H:%M:%S"))
        self.gmt_label.setText(now_gmt.strftime("%H:%M:%S"))
        self.lmt_label.setText(now_lmt.strftime("%H:%M:%S"))

        if self._cached_sunrise_jd is not None:
            jd_now = datetime_to_julday(now_utc)
            if jd_now >= self._cached_sunrise_jd:
                vedic = get_vedic_time(jd_now, self._cached_sunrise_jd)
                self.ghati_label.setText(f"{vedic['ghati']:02d}")
                self.pal_label.setText(f"{vedic['pal']:02d}")
                self.vipal_label.setText(f"{vedic['vipal']:02d}")
            elif self._cached_sunrise_jd_prev_day_actual is not None:
                vedic = get_vedic_time(jd_now, self._cached_sunrise_jd_prev_day_actual)
                self.ghati_label.setText(f"{vedic['ghati']:02d}")
                self.pal_label.setText(f"{vedic['pal']:02d}")
                self.vipal_label.setText(f"{vedic['vipal']:02d}")
            else:
                self.ghati_label.setText("--")
                self.pal_label.setText("--")
                self.vipal_label.setText("--")

        self._update_background(now_utc)

    def _update_background(self, now_utc):
        """Identical color/contrast logic to page_home.py -- only the
        font-family in the restyled stylesheet differs."""
        if self._cached_sunrise_jd is None or self._cached_sunset_jd is None \
                or self._cached_next_sunrise_jd is None:
            return

        jd_now = datetime_to_julday(now_utc)
        current_idx, next_idx, fraction = _get_pahar_index_and_fraction(
            jd_now, self._cached_sunrise_jd, self._cached_sunset_jd, self._cached_next_sunrise_jd
        )
        bg_r, bg_g, bg_b = (
            int(PAHAR_COLORS[current_idx][i] + (PAHAR_COLORS[next_idx][i] - PAHAR_COLORS[current_idx][i]) * fraction)
            for i in range(3)
        )
        color_hex = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
        # No self._f() here -- this runs every tick, so it was
        # silently re-applying the same inheritance bug fixed above
        # (in _build_ui) on every single refresh, permanently
        # overriding any attempt to keep clock_value_labels plain.
        self.left_panel.setStyleSheet(f"background-color: {color_hex}; color: white;")

        text_color = _contrast_text_color(bg_r, bg_g, bg_b)
        for label, font_size in self.clock_value_labels:
            # No Devanagari font here -- clock_value_labels are all
            # pure digits/colons (see build-time comments above).
            label.setStyleSheet(f"font-size: {px(font_size)}px; font-weight: bold; color: {text_color};")

        # Captions get their own muted-but-legible color too -- see
        # page_home.py's identical fix / comment for why the old fixed
        # gray was a bug, not a style choice. clock_caption_labels is a
        # MIX of plain-Roman captions (IST/GMT/LMT) and real Devanagari
        # ones (वैदिक समय, घटी/पल/विपल) -- each entry's 4th value says
        # which, so the font-family is only applied where it's actually
        # needed rather than uniformly across the whole list.
        caption_color = _contrast_caption_color(bg_r, bg_g, bg_b)
        for label, font_size, weight, needs_devanagari in self.clock_caption_labels:
            css = f"font-size: {px(font_size)}px; font-weight: {weight}; color: {caption_color};"
            label.setStyleSheet(self._f(css) if needs_devanagari else css)

    # -------------------------------------------------------------------
    # Slow refresh -- Tithi, Masa, festivals, fresh sunrise. Engine
    # values are passed through translate_value() (translate_masa()
    # for Masa specifically, to handle its Adhik/Kshaya suffix) --
    # see translations_hi.py for the full name tables.
    # -------------------------------------------------------------------

    def _update_slow(self):
        now_utc = datetime.now(timezone.utc)
        now_ist = get_ist(now_utc)
        jd_now = datetime_to_julday(now_utc)

        sun = get_sun_times_details(now_ist, self.lat, self.lon)
        self._cached_sunrise_jd = sun["sunrise_jd"]
        self._cached_sunrise_jd_yesterday = self._cached_sunrise_jd - 1.0

        yesterday_ist_date = now_ist - timedelta(days=1)
        prev_midnight_jd = get_local_midnight_jd_ut(yesterday_ist_date)
        self._cached_sunrise_jd_prev_day_actual = get_sunrise_jd(prev_midnight_jd, self.lat, self.lon)

        # Date + weekday combined into one line ("12 सितंबर 2026,
        # शनिवार") per request. Day number stays international-numeral,
        # weekday/month names translated. now_ist.strftime("%A")/("%B")
        # both always return English regardless of locale, so
        # translate_weekday/translate_month look them up rather than
        # relying on locale.
        date_part = f"{now_ist.strftime('%d')} {translate_month(now_ist.strftime('%B'))} {now_ist.strftime('%Y')}"
        weekday_part = translate_weekday(now_ist.strftime("%A"))
        self.date_label.setText(f"{date_part}, {weekday_part}")

        masa = get_masa_details(jd_now)
        purnimanta_masa = get_purnimanta_masa_name(jd_now)
        paksha = get_paksha(jd_now)
        vara = get_vara(now_ist)
        vikram_year = get_vikram_samvat_year(jd_now)
        samvatsara = get_samvatsara_name(vikram_year)
        tithi = get_tithi_details(jd_now)

        self.field_labels["masa"].setText(translate_masa(purnimanta_masa))
        self.field_labels["ritu"].setText(translate_value("ritu", get_ritu(jd_now)))
        self.field_labels["paksha"].setText(translate_value("paksha", paksha))
        self.field_labels["vara"].setText(translate_value("vara", vara))
        self.field_labels["vikram_samvat"].setText(str(vikram_year))  # numeral, unchanged
        self.field_labels["samvatsara"].setText(translate_value("samvatsara", samvatsara))
        self.field_labels["tithi"].setText(translate_value("tithi", tithi["name"]))
        self.field_labels["tithi_till"].setText(f"({_format_tithi_end(tithi['end_ist'])} {PHRASE_TILL})")

        sunrise_jd = sun["sunrise_jd"]
        sunset_jd = sun["sunset_jd"]
        next_sunrise_jd = get_sunrise_jd(sunset_jd, self.lat, self.lon)
        self._cached_sunset_jd = sunset_jd
        self._cached_next_sunrise_jd = next_sunrise_jd

        muhurta = get_muhurta_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
        if muhurta["current_muhurta_number"]:
            day_night_en = "Day" if muhurta["is_day"] else "Night"
            day_night = PHRASE_DAY_NIGHT.get(day_night_en, day_night_en)
            muhurta_name = translate_value("muhurta", muhurta["current_muhurta_name"])
            self.field_labels["muhurta"].setText(
                f"{muhurta_name} -- {day_night} {muhurta['current_muhurta_number']}/15"
            )
        else:
            self.field_labels["muhurta"].setText("...")

        pahar = get_pahar_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
        self.field_labels["pahar"].setText(translate_value("pahar", pahar["name"]))

        festivals = get_todays_festivals(self._cached_sunrise_jd, self._cached_sunrise_jd_yesterday)
        if festivals:
            # "festival" is now a wired-up translate_value() category
            # (FESTIVAL_HI in translations_hi.py), but that table is
            # still empty pending config/festivals.yaml's actual name
            # list -- falls back to English per-name until it's filled
            # in, same as every other category here.
            names = ", ".join(translate_value("festival", f["name"]) for f in festivals)
            self.festival_label.setText(f"{PHRASE_TODAY} {names}")
            self.festival_label.show()
        else:
            self.festival_label.setText("")
            self.festival_label.hide()

    def _update_eclipse(self):
        now_utc = datetime.now(timezone.utc)
        jd_now = datetime_to_julday(now_utc)

        info = get_eclipse_display_info(jd_now, self.lat, self.lon, self.location_name)
        if info is None:
            self.eclipse_label.setText("")
            self.eclipse_label.hide()
        else:
            # Hindi version of eclipse_banner.py's format_single_line(),
            # built from the same info dict rather than calling that
            # function -- it composes an English sentence directly, so
            # this reconstructs the equivalent Hindi one field-by-field:
            # translated eclipse type (best-effort -- see
            # translate_eclipse_type()'s docstring on engine/eclipse.py
            # not yet being seen), Hindi month abbreviations in the
            # date range, "से...तक" instead of "to", and a translated
            # location name in the "not visible" note.
            type_hi = translate_eclipse_type(info["type"])
            start_hi = hi_date_short(info["start_short"])
            end_hi = hi_date_short(info["end_short"])
            vis_text = ""
            if info["visibility_percent"] is not None:
                vis_text = f", {info['visibility_percent']:.0f}%"
                if info["visible_at_max"] is False:
                    location_hi = translate_location(info["location_name"])
                    vis_text += f" ({PHRASE_NOT_VISIBLE_TEMPLATE.format(location=location_hi)})"
            text = f"{type_hi} {LABEL_ECLIPSE_WORD}: {start_hi} {PHRASE_TO} {end_hi} {PHRASE_TILL}{vis_text}"
            self.eclipse_label.setText(text)
            self.eclipse_label.show()


# =============================================================================
# Standalone test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    app = QApplication(sys.argv)
    page = PageHomeHi()
    screen_size = app.primaryScreen().availableGeometry().size()
    page.resize(screen_size.width(), screen_size.height())
    page.setWindowTitle("Page 1: Home (Hindi) (standalone test)")
    page.show()
    sys.exit(app.exec_())
