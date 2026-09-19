"""
ui/page_home.py

Page 1 (Home): split into a left column (IST, Vedic Time, GMT, LMT
-- the "live clock" content) and a right column (date, Masa, Paksha,
Vara, Samvatsara, Tithi, festival banner -- everything else).

RESOLUTION SCALING: all pixel values (fonts, spacing, widths) go
through scaling.px(), which scales them from a 1920x1080 design
baseline to whatever the actual screen resolution is. All target
displays are confirmed 16:9 (just varying pixel density -- VGA test
monitor, 32in/50in/100in panels), so a single height-based scale
factor keeps every proportion correct. On the current 1920x1080
monitor, px(n) == n exactly, so this should look pixel-identical to
the already-approved layout -- see ui/scaling.py for details.

Two-tier refresh, since Tithi/Masa/sunrise involve real ephemeris
calculations and shouldn't be recomputed every second:
  - Fast timer (1s): the live clock (IST/GMT/LMT/Vedic time),
    reusing a cached sunrise value rather than recomputing it.
  - Slow timer (60s): Tithi, Masa, Paksha, Vara, Samvatsara,
    festivals, and a fresh sunrise (for Vedic time's reference point).
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
from eclipse_banner import get_eclipse_display_info, format_single_line

IST_OFFSET = timedelta(hours=5, minutes=30)

# Design-baseline widths (at 1920x1080) -- scaled at runtime via px()
# These are STRETCH RATIOS (not absolute pixels -- see _build_ui).
# Equal split -- 50:50 between the clock panel and the text panel.
LEFT_WIDTH_BASELINE = 500
RIGHT_WIDTH_BASELINE = 500


def _format_clock_style(vedic: dict) -> str:
    """Ghati/Pal/Vipal as a clock-style 'GG:PP:VV' string."""
    return f"{vedic['ghati']:02d}:{vedic['pal']:02d}:{vedic['vipal']:02d}"


def _format_tithi_end(ist_string: str) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS IST' into 'DD Month HH:MM:SS'
    (no year, no IST suffix -- IST is implied throughout for India)."""
    dt = datetime.strptime(ist_string, "%Y-%m-%d %H:%M:%S IST")
    return dt.strftime("%d %B %H:%M:%S")


# =============================================================================
# Animated background: gradual color shift tied to the 8 real Pahar
# divisions (Purvahna..Sayahna by day, Pradosh..Ushakal by night) --
# reuses the sunrise/sunset/next-sunrise data the page already caches,
# rather than duplicating any Pahar-boundary logic from engine/muhurta.py.
# Colors blend continuously across the day, not in 8 discrete jumps.
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
    """
    Returns (current_pahar_index, next_pahar_index, fraction) where
    fraction is 0.0-1.0 progress through the current Pahar -- used to
    blend smoothly between that Pahar's color and the next one's.
    Same day/night quartering as engine/muhurta.py's get_pahar_details,
    computed independently here since this needs the two neighboring
    colors, not just the current Pahar's name.
    """
    if sunrise_jd <= jd_now <= sunset_jd:
        span_start, span_end, base_index = sunrise_jd, sunset_jd, 0
    else:
        # Covers both "after sunset" and the pre-dawn edge case (before
        # today's sunrise) -- both fall within the same night span,
        # same simplification get_pahar_details itself uses.
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
    """Blend two (r,g,b) tuples by fraction t (0-1), return a hex string."""
    r = int(c1[0] + (c2[0] - c1[0]) * t)
    g = int(c1[1] + (c2[1] - c1[1]) * t)
    b = int(c1[2] + (c2[2] - c1[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _contrast_text_color(r: int, g: int, b: int) -> str:
    """
    Pick a readable text color for a given background RGB, using
    perceived luminance -- dark text on light backgrounds (Purvahna's
    soft blue, Aparahna's gold), light text on dark ones (Nishitha,
    Trijama). All the clock value labels (IST, Vedic time, GMT, LMT)
    share this ONE color rather than each having its own fixed color.
    """
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#1a1a2e" if luminance > 150 else "#f5f5f5"


def _contrast_caption_color(r: int, g: int, b: int) -> str:
    """
    Color for the secondary caption labels (IST / VEDIC TIME / GHATI /
    PAL / VIPAL / GMT / LMT). These used to be a fixed #999999 gray,
    which read fine against the darker Pahars but washed out badly
    against the lighter ones (e.g. Aparahna's gold, Purvahna's soft
    blue) -- a mid-gray sits close to both those backgrounds'
    luminance, so contrast collapsed exactly when the background got
    light. Fix: derive the caption color from the SAME live background
    _contrast_text_color() already uses, blended partway toward the
    background so it still reads as visually "secondary" next to the
    bold primary clock digits, but the blend ratio is mild enough that
    it stays legible on every Pahar rather than picking one fixed
    tone that only works for some of them.
    """
    primary_hex = _contrast_text_color(r, g, b)
    pr = int(primary_hex[1:3], 16)
    pg = int(primary_hex[3:5], 16)
    pb = int(primary_hex[5:7], 16)
    blend = 0.62  # 62% toward the primary contrast color, 38% toward the background
    cr = int(pr * blend + r * (1 - blend))
    cg = int(pg * blend + g * (1 - blend))
    cb = int(pb * blend + b * (1 - blend))
    return f"#{cr:02x}{cg:02x}{cb:02x}"


class PageHome(QWidget):
    def __init__(self):
        super().__init__()
        self.lat, self.lon = get_location()
        self._cached_sunrise_jd = None
        self._cached_sunrise_jd_yesterday = None
        self._cached_sunrise_jd_prev_day_actual = None  # precise, for pre-dawn Vedic time
        self._cached_sunset_jd = None
        self._cached_next_sunrise_jd = None  # both cached for the background animation, avoids recomputing every second

        self._build_ui()

        self.fast_timer = QTimer(self)
        self.fast_timer.timeout.connect(self._update_fast)
        self.fast_timer.start(1000)

        self.slow_timer = QTimer(self)
        self.slow_timer.timeout.connect(self._update_slow)
        self.slow_timer.start(60 * 1000)

        self.eclipse_timer = QTimer(self)
        self.eclipse_timer.timeout.connect(self._update_eclipse)
        self.eclipse_timer.start(60 * 60 * 1000)  # 60 min -- eclipse status barely changes minute to minute

        self._update_slow()
        self._update_fast()
        self._update_eclipse()

    # -------------------------------------------------------------------
    # UI layout
    # -------------------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet("background-color: #1a1a2e; color: white;")
        outer = QHBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left = self._build_left_panel()
        right = self._build_right_panel()

        # Stretch ratios (not fixed pixel widths) so the two panels
        # always fill 100% of whatever the actual window width is,
        # split in the same 600:424 proportion regardless of screen
        # resolution or aspect ratio -- fixed pixel widths would leave
        # unfilled background on screens wider than our old 4:3 test
        # window (1024x768) was designed for.
        outer.addWidget(left, LEFT_WIDTH_BASELINE)
        outer.addWidget(right, RIGHT_WIDTH_BASELINE)
        self.setLayout(outer)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        self.left_panel = panel  # kept for the animated background
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        layout.setContentsMargins(0, px(20), 0, 0)

        ist_heading = QLabel("IST")
        ist_heading.setAlignment(Qt.AlignCenter)
        ist_heading.setStyleSheet(f"font-size: {px(36)}px; font-weight: bold;")
        layout.addWidget(ist_heading)

        self.ist_label = QLabel("--:--:--")
        self.ist_label.setAlignment(Qt.AlignCenter)
        self.ist_label.setStyleSheet(f"font-size: {px(96)}px; font-weight: bold;")
        layout.addWidget(self.ist_label)

        layout.addSpacing(px(30))

        vedic_heading = QLabel("VEDIC TIME")
        vedic_heading.setAlignment(Qt.AlignCenter)
        vedic_heading.setStyleSheet(f"font-size: {px(36)}px; font-weight: bold;")
        layout.addWidget(vedic_heading)

        vedic_row = QHBoxLayout()
        vedic_row.setSpacing(px(6))
        vedic_row.setAlignment(Qt.AlignCenter)

        # All the "clock value" labels (IST, Vedic time digits+colons,
        # GMT, LMT) share ONE dynamically-updated contrast color instead
        # of the earlier mixed orange/teal/white scheme -- collected
        # here so _update_background can restyle all of them together
        # each tick, based on the current Pahar background's brightness.
        self.clock_value_labels = [(self.ist_label, 96)]

        # Caption labels (IST / VEDIC TIME / GHATI / PAL / VIPAL / GMT /
        # LMT) get their OWN dynamically-updated color too now (see
        # _contrast_caption_color) instead of a fixed gray -- tracked
        # separately from clock_value_labels since captions keep a
        # muted/secondary tone rather than the full-contrast value
        # color, and some are bold (36px/24px headings) while others
        # are normal weight (24px Ghati/Pal/Vipal captions), so each
        # entry also carries its own font-size + weight to restyle
        # correctly.
        self.clock_caption_labels = [(ist_heading, 36, "bold"), (vedic_heading, 36, "bold")]

        def _build_vedic_col(caption_text: str):
            col = QVBoxLayout()
            col.setSpacing(px(5))
            value_label = QLabel("--")
            value_label.setAlignment(Qt.AlignCenter)
            value_label.setStyleSheet(f"font-size: {px(96)}px; font-weight: bold;")
            col.addWidget(value_label)
            caption_label = QLabel(caption_text)
            caption_label.setAlignment(Qt.AlignCenter)
            caption_label.setStyleSheet(f"font-size: {px(24)}px; font-weight: normal;")
            col.addWidget(caption_label)
            self.clock_value_labels.append((value_label, 96))
            self.clock_caption_labels.append((caption_label, 24, "normal"))
            return col, value_label

        def _build_colon_col():
            col = QVBoxLayout()
            col.setSpacing(px(5))
            colon_label = QLabel(":")
            colon_label.setAlignment(Qt.AlignCenter)
            colon_label.setStyleSheet(f"font-size: {px(96)}px; font-weight: bold;")
            col.addWidget(colon_label)
            spacer_label = QLabel("")  # keeps this column's height matching the value+caption columns
            col.addWidget(spacer_label)
            self.clock_value_labels.append((colon_label, 96))
            return col

        ghati_col, self.ghati_label = _build_vedic_col("GHATI")
        pal_col, self.pal_label = _build_vedic_col("PAL")
        vipal_col, self.vipal_label = _build_vedic_col("VIPAL")

        vedic_row.addLayout(ghati_col)
        vedic_row.addLayout(_build_colon_col())
        vedic_row.addLayout(pal_col)
        vedic_row.addLayout(_build_colon_col())
        vedic_row.addLayout(vipal_col)

        layout.addLayout(vedic_row)

        layout.addSpacing(px(30))
        layout.addSpacing(px(10))

        gmt_lmt_row = QHBoxLayout()
        gmt_lmt_row.setSpacing(px(70))

        gmt_col = QVBoxLayout()
        gmt_col.setSpacing(0)
        gmt_heading = QLabel("GMT")
        gmt_heading.setAlignment(Qt.AlignCenter)
        gmt_heading.setStyleSheet(f"font-size: {px(24)}px; font-weight: bold;")
        gmt_col.addWidget(gmt_heading)
        gmt_col.addSpacing(px(10))
        self.gmt_label = QLabel("--:--:--")
        self.gmt_label.setAlignment(Qt.AlignCenter)
        self.gmt_label.setStyleSheet(f"font-size: {px(50)}px;")
        gmt_col.addWidget(self.gmt_label)
        self.clock_value_labels.append((self.gmt_label, 50))
        self.clock_caption_labels.append((gmt_heading, 24, "bold"))

        lmt_col = QVBoxLayout()
        lmt_col.setSpacing(0)
        lmt_heading = QLabel("LMT")
        lmt_heading.setAlignment(Qt.AlignCenter)
        lmt_heading.setStyleSheet(f"font-size: {px(24)}px; font-weight: bold;")
        lmt_col.addWidget(lmt_heading)
        lmt_col.addSpacing(px(10))
        self.lmt_label = QLabel("--:--:--")
        self.lmt_label.setAlignment(Qt.AlignCenter)
        self.lmt_label.setStyleSheet(f"font-size: {px(50)}px;")
        lmt_col.addWidget(self.lmt_label)
        self.clock_value_labels.append((self.lmt_label, 50))
        self.clock_caption_labels.append((lmt_heading, 24, "bold"))

        gmt_lmt_row.addLayout(gmt_col)
        gmt_lmt_row.addLayout(lmt_col)
        layout.addLayout(gmt_lmt_row)

        layout.addSpacing(px(40))
        settings = load_settings()
        location_name = settings.get("location", {}).get("name", "")
        self.location_name = location_name
        self.location_label = QLabel(location_name)
        self.location_label.setAlignment(Qt.AlignCenter)
        self.location_label.setStyleSheet(f"font-size: {px(32)}px; font-weight: bold;")
        layout.addWidget(self.location_label)

        panel.setLayout(layout)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background-color: #14142a;")
        layout = QVBoxLayout()
        layout.setContentsMargins(px(16), px(16), px(16), px(16))
        layout.setSpacing(px(10))

        self.date_label = QLabel("Loading date...")
        self.date_label.setAlignment(Qt.AlignCenter)
        self.date_label.setWordWrap(True)
        self.date_label.setStyleSheet(f"font-size: {px(32)}px; font-weight: bold;")
        layout.addWidget(self.date_label)

        self.day_label = QLabel("...")
        self.day_label.setAlignment(Qt.AlignCenter)
        self.day_label.setWordWrap(True)
        self.day_label.setStyleSheet(f"font-size: {px(32)}px; font-weight: bold;")
        layout.addWidget(self.day_label)

        layout.addSpacing(px(15))

        self.field_labels = {}
        fields = [(f["key"], f["heading"]) for f in load_page_layout()["page_home"]]

        field_grid = QGridLayout()
        field_grid.setHorizontalSpacing(px(25))
        field_grid.setVerticalSpacing(px(6))
        field_grid.setColumnStretch(2, 1)  # value column absorbs extra width

        row = 0
        for field, label_text in fields:
            heading = QLabel(label_text)
            heading.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            heading.setStyleSheet(f"font-size: {px(22)}px;")
            field_grid.addWidget(heading, row, 0)

            colon = QLabel(":")
            colon.setStyleSheet(f"font-size: {px(22)}px;")
            field_grid.addWidget(colon, row, 1)

            value = QLabel("...")
            value.setWordWrap(True)
            value.setStyleSheet(f"font-size: {px(22)}px; padding-left: {px(20)}px;")
            field_grid.addWidget(value, row, 2)
            self.field_labels[field] = value
            row += 1

            if field == "tithi":
                # "(till ...)" gets its own line below, at 18px (80% of
                # the 22px base size) to maximize its chance of fitting
                # on a single line without wrapping.
                till_label = QLabel("")
                till_label.setWordWrap(True)
                till_label.setStyleSheet(f"font-size: {px(18)}px; padding-left: {px(20)}px;")
                field_grid.addWidget(till_label, row, 1, 1, 2)
                self.field_labels["tithi_till"] = till_label
                row += 1

        layout.addLayout(field_grid)

        layout.addStretch()

        self.festival_label = QLabel("")
        self.festival_label.setAlignment(Qt.AlignCenter)
        self.festival_label.setStyleSheet(
            f"font-size: {px(20)}px; font-weight: bold; color: #2ecc71; "
            f"background-color: #0f3d2e; border-radius: {px(8)}px; padding: {px(10)}px;"
        )
        self.festival_label.setWordWrap(True)
        layout.addWidget(self.festival_label)

        self.eclipse_label = QLabel("")
        self.eclipse_label.setAlignment(Qt.AlignCenter)
        self.eclipse_label.setStyleSheet(
            f"font-size: {px(20)}px; font-weight: bold; color: #ff7043; "
            f"background-color: #3d1f0f; border-radius: {px(8)}px; padding: {px(10)}px;"
        )
        self.eclipse_label.setWordWrap(True)
        layout.addWidget(self.eclipse_label)

        panel.setLayout(layout)
        return panel

    # -------------------------------------------------------------------
    # Fast refresh -- live clock only, cheap
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
                # Normal case: today's sunrise has already happened.
                vedic = get_vedic_time(jd_now, self._cached_sunrise_jd)
                self.ghati_label.setText(f"{vedic['ghati']:02d}")
                self.pal_label.setText(f"{vedic['pal']:02d}")
                self.vipal_label.setText(f"{vedic['vipal']:02d}")
            elif self._cached_sunrise_jd_prev_day_actual is not None:
                # Pre-dawn: still before today's sunrise, so the current
                # Vedic day started at YESTERDAY's sunrise instead.
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
        """
        Smoothly blend the left panel's background through the 8 real
        Pahar colors across the day/night, rather than jumping in 8
        discrete steps. Runs every second (piggybacking the fast timer)
        since the color shift is gradual and near-imperceptible frame
        to frame, but adds up to a genuinely moving sky over a Pahar's
        ~3 hour span.
        """
        if self._cached_sunrise_jd is None or self._cached_sunset_jd is None \
                or self._cached_next_sunrise_jd is None:
            return  # not yet loaded (first tick before _update_slow has run)

        jd_now = datetime_to_julday(now_utc)
        current_idx, next_idx, fraction = _get_pahar_index_and_fraction(
            jd_now, self._cached_sunrise_jd, self._cached_sunset_jd, self._cached_next_sunrise_jd
        )
        bg_r, bg_g, bg_b = (
            int(PAHAR_COLORS[current_idx][i] + (PAHAR_COLORS[next_idx][i] - PAHAR_COLORS[current_idx][i]) * fraction)
            for i in range(3)
        )
        color_hex = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"
        self.left_panel.setStyleSheet(f"background-color: {color_hex}; color: white;")

        # All clock values (IST, Vedic time digits+colons, GMT, LMT)
        # share ONE contrast-adaptive color, computed from the same
        # background so text stays readable across light and dark
        # Pahars, instead of the earlier fixed orange/teal/white mix.
        text_color = _contrast_text_color(bg_r, bg_g, bg_b)
        for label, font_size in self.clock_value_labels:
            label.setStyleSheet(f"font-size: {px(font_size)}px; font-weight: bold; color: {text_color};")

        # Captions (IST / VEDIC TIME / GHATI / PAL / VIPAL / GMT / LMT)
        # get their own muted-but-legible color, also derived from the
        # live background -- replaces the old fixed #999999 gray, which
        # lost contrast against the lighter Pahars (Aparahna's gold,
        # Purvahna's soft blue).
        caption_color = _contrast_caption_color(bg_r, bg_g, bg_b)
        for label, font_size, weight in self.clock_caption_labels:
            label.setStyleSheet(f"font-size: {px(font_size)}px; font-weight: {weight}; color: {caption_color};")

    # -------------------------------------------------------------------
    # Slow refresh -- Tithi, Masa, festivals, fresh sunrise
    # -------------------------------------------------------------------

    def _update_slow(self):
        now_utc = datetime.now(timezone.utc)
        now_ist = get_ist(now_utc)
        jd_now = datetime_to_julday(now_utc)

        sun = get_sun_times_details(now_ist, self.lat, self.lon)
        self._cached_sunrise_jd = sun["sunrise_jd"]
        self._cached_sunrise_jd_yesterday = self._cached_sunrise_jd - 1.0

        # Precise previous-day sunrise (not just "-1.0 day"), for the
        # pre-dawn Vedic-time case: before today's actual sunrise, the
        # current Vedic day is still the one that began at YESTERDAY's
        # actual sunrise, not a rough 24h-earlier approximation.
        yesterday_ist_date = now_ist - timedelta(days=1)
        prev_midnight_jd = get_local_midnight_jd_ut(yesterday_ist_date)
        self._cached_sunrise_jd_prev_day_actual = get_sunrise_jd(prev_midnight_jd, self.lat, self.lon)

        self.date_label.setText(now_ist.strftime("%d %B %Y"))
        self.day_label.setText(now_ist.strftime("%A"))

        masa = get_masa_details(jd_now)
        purnimanta_masa = get_purnimanta_masa_name(jd_now)
        paksha = get_paksha(jd_now)
        vara = get_vara(now_ist)
        vikram_year = get_vikram_samvat_year(jd_now)
        samvatsara = get_samvatsara_name(vikram_year)
        tithi = get_tithi_details(jd_now)

        self.field_labels["masa"].setText(purnimanta_masa)
        self.field_labels["ritu"].setText(get_ritu(jd_now))
        self.field_labels["paksha"].setText(paksha)
        self.field_labels["vara"].setText(vara)
        self.field_labels["vikram_samvat"].setText(str(vikram_year))
        self.field_labels["samvatsara"].setText(samvatsara)
        self.field_labels["tithi"].setText(tithi["name"])
        self.field_labels["tithi_till"].setText(f"(till {_format_tithi_end(tithi['end_ist'])})")

        sunrise_jd = sun["sunrise_jd"]
        sunset_jd = sun["sunset_jd"]
        next_sunrise_jd = get_sunrise_jd(sunset_jd, self.lat, self.lon)
        self._cached_sunset_jd = sunset_jd
        self._cached_next_sunrise_jd = next_sunrise_jd

        muhurta = get_muhurta_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
        if muhurta["current_muhurta_number"]:
            day_night = "Day" if muhurta["is_day"] else "Night"
            self.field_labels["muhurta"].setText(
                f"{muhurta['current_muhurta_name']} -- {day_night} {muhurta['current_muhurta_number']}/15"
            )
        else:
            self.field_labels["muhurta"].setText("...")

        pahar = get_pahar_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
        self.field_labels["pahar"].setText(pahar["name"])

        festivals = get_todays_festivals(self._cached_sunrise_jd, self._cached_sunrise_jd_yesterday)
        if festivals:
            names = ", ".join(f["name"] for f in festivals)
            self.festival_label.setText(f"Today: {names}")
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
            self.eclipse_label.setText(format_single_line(info))
            self.eclipse_label.show()


# =============================================================================
# Standalone test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    app = QApplication(sys.argv)
    page = PageHome()
    # Size the test window to the actual screen, matching how it'll
    # run in fullscreen/kiosk mode later -- this also naturally
    # exercises the scaling.px() logic at whatever resolution this
    # happens to run at.
    screen_size = app.primaryScreen().availableGeometry().size()
    page.resize(screen_size.width(), screen_size.height())
    page.setWindowTitle("Page 1: Home (standalone test)")
    page.show()
    sys.exit(app.exec_())
