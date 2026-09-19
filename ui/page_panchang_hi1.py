"""
ui/page_panchang_hi.py

Hindi/Devanagari twin of page_panchang.py. SEPARATE FILE --
page_panchang.py is not modified or imported here; this is a
standalone page with the exact same layout, colors, spacing, and
refresh logic (including the row-alignment fix: the right panel
reserves one blank detail-line row per non-Eclipse field so its rows
land at the same height as the left panel's, without changing the
left panel's own spacing -- see page_panchang.py's own comments for
the full reasoning), just with headings and value text in Devanagari.

NUMERALS: dates/times in the range lines (e.g. "28-08-26 14:32:10")
intentionally stay in international form (0-9) -- see
translations_hi.py's module docstring.

FONT: loads the bundled Devanagari font once via
translations_hi.get_devanagari_font_family() and appends
`font-family: '<name>';` to every label's stylesheet through the
self._f() helper below, same pattern as page_home_hi.py.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

from PyQt5.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QFontMetrics

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

from ephemeris import init_ephemeris, datetime_to_julday
from panchang import get_nakshatra_details, get_yoga_details, get_karana_details
from rashi import get_chandra_rashi_details, get_surya_rashi_details
from sun_times import get_sun_times_details, get_sunrise_jd, get_moonrise_jd, get_moonset_jd
from masa import get_ayana
from muhurta import get_muhurta_details, get_brahma_muhurta
from eclipse_banner import get_eclipse_display_info, format_two_lines
from config_loader import get_location, load_settings, load_page_layout
from scaling import px

from translations_hi import (
    HEADINGS_HI, PHRASE_TO, PHRASE_TILL, LABEL_ABHIJIT, LABEL_BRAHMA_SHUBH,
    translate_value, get_devanagari_font_family,
)

IST_OFFSET = timedelta(hours=5, minutes=30)

# Same unified font sizes as page_panchang.py.
MAIN_FONT = 25
# Reduced from 15 -- the Hindi date-range detail text ("...से...तक")
# is genuinely wider than English's "...to..." at the same pixel size,
# and after the field grid's left margin was shifted to px(70), the
# widest realistic detail line (296px measured) no longer fit in the
# ~266px available in column 2 -- it was wrapping to 2 lines there
# while the RIGHT panel's corresponding reserved blank line stayed 1
# line, creating a creeping misalignment (this is what looked like
# "Day Length landing next to Brahma Muhurta's detail line" -- one
# accumulated extra line of height from an earlier wrapped row).
# DETAIL_FONT=12 measures 237px for the same text, comfortable margin
# below 266px. Hindi-only; page_panchang.py keeps its original 15.
DETAIL_FONT = 12


def _format_short(ist_string: str) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS IST' into 'DD-MM-YY HH:MM:SS'
    -- purely numeric, numerals stay international form, unchanged
    from page_panchang.py."""
    dt = datetime.strptime(ist_string, "%Y-%m-%d %H:%M:%S IST")
    return dt.strftime("%d-%m-%y %H:%M:%S")


def _jd_to_ist_time_only(jd_ut: float) -> str:
    """Julian Day (UT) -> just the 'HH:MM:SS' IST time, no date."""
    import swisseph as swe
    y, m, d, h = swe.revjul(jd_ut)
    hour = int(h)
    minute = int((h - hour) * 60)
    second = int((((h - hour) * 60) - minute) * 60)
    dt_utc = datetime(y, m, d, hour, minute, second, tzinfo=timezone.utc)
    dt_ist = dt_utc + IST_OFFSET
    return dt_ist.strftime("%H:%M:%S")


class PagePanchangHi(QWidget):
    REFRESH_INTERVAL_MS = 60 * 1000

    def __init__(self):
        super().__init__()
        self.lat, self.lon = get_location()
        settings = load_settings()
        self.location_name = settings.get("location", {}).get("name", "")

        # Load the bundled Devanagari font once (requires QApplication
        # to already exist -- true here, same as page_home_hi.py).
        self.font_family = get_devanagari_font_family()

        # Computed ONCE here and reused for every row in BOTH panels
        # via grid.setRowMinimumHeight() in _build_field_grid(). This
        # forces the left and right grids' rows to the exact same
        # height explicitly, rather than relying on Qt's automatic
        # per-grid sizeHint computation to naturally agree between two
        # separate QGridLayout instances -- which, per real-device
        # testing, it does NOT reliably do (a small but real and
        # growing per-row drift was observed on Windows that could not
        # be reproduced in this project's Linux test environment;
        # likely a text-shaping engine difference for Devanagari
        # between platforms -- DirectWrite vs HarfBuzz -- rather than
        # a logic bug). Computed from the ALREADY-SCALED font sizes
        # (px(MAIN_FONT)/px(DETAIL_FONT)), so this stays correct at
        # any screen resolution/scale factor, same as every other
        # pixel value in this app -- it is not a hardcoded constant.
        self._main_row_height, self._detail_row_height = self._compute_row_heights()

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(self.REFRESH_INTERVAL_MS)

        self.eclipse_timer = QTimer(self)
        self.eclipse_timer.timeout.connect(self._update_eclipse)
        self.eclipse_timer.start(60 * 60 * 1000)  # 60 min, same as page_panchang.py

        self._update()
        self._update_eclipse()

    def _f(self, css: str) -> str:
        return css + f" font-family: '{self.font_family}';"

    def _compute_row_heights(self):
        """
        Returns (main_row_height, detail_row_height) in actual pixels,
        computed from QFontMetrics using the SAME already-scaled font
        sizes (px(MAIN_FONT), px(DETAIL_FONT)) and the same font
        family every label in this grid actually uses. This is what
        grid.setRowMinimumHeight() uses (in _build_field_grid) to
        force identical row heights between the left and right panels
        -- see the comment on self._main_row_height in __init__ for
        why this is necessary.

        IMPORTANT: setRowMinimumHeight() only enforces a FLOOR -- if a
        row's actual content naturally needs more than this computed
        value (verified on real hardware: Windows' text-shaping engine
        for Devanagari can compute a genuinely taller natural height
        for the exact same declared font than what a same-platform
        QFontMetrics call reports elsewhere -- a small but real,
        cumulative per-row difference, not reproducible in this
        project's Linux test environment), Qt still grows the row past
        the minimum, silently defeating this fix. A first attempt at
        px(8) wasn't enough -- it actually flipped which panel fell
        behind, confirming the true platform variance exceeds that
        margin. px(20) is large enough to comfortably exceed realistic
        real-content needs on either side, so both panels get pinned
        to the exact same literal forced value no matter the quirk's
        size or direction -- the only cost is a bit more whitespace
        per row, never lost content (unlike shrinking a box below its
        font metrics, this direction carries no clipping risk).
        """
        margin = px(20)

        main_font = QFont(self.font_family)
        main_font.setPixelSize(px(MAIN_FONT))
        main_font.setBold(True)
        main_height = QFontMetrics(main_font).height() + margin

        detail_font = QFont(self.font_family)
        detail_font.setPixelSize(px(DETAIL_FONT))
        detail_height = QFontMetrics(detail_font).height() + margin

        return main_height, detail_height

    # -------------------------------------------------------------------
    # UI layout -- identical structure/colors/spacing to page_panchang.py,
    # including the row-alignment fix (see module docstring).
    # -------------------------------------------------------------------

    def _build_ui(self):
        # No self._f() here -- pure background/color container, no
        # text of its own. See page_home_hi.py's fix/comment for why:
        # Qt Style Sheets inherit font-family to any descendant that
        # doesn't declare its own, so this was an unnecessary (if
        # currently harmless, since every label here already sets its
        # own font-family) inheritance source.
        self.setStyleSheet("background-color: #241a3e; color: white;")
        outer = QVBoxLayout()
        # Top margin restored to its original px(10) -- title stays
        # put; only the gap between title and panels_row (removed
        # below) moves the panels up, not the title itself.
        outer.setContentsMargins(px(10), px(10), px(10), px(10))
        # Reduced from px(10) -- gap between title and first row.
        # Confirmed this is a single, direct gap (outer only ever has
        # title + panels_row as its two top-level items), so this is
        # the exact value that controls it -- no hidden extra like the
        # earlier addSpacing() case, and no risk to either widget's
        # own box height (unlike the heading/detail padding question).
        outer.setSpacing(px(4))

        title = QLabel("दैनिक पंचांग")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(self._f(f"font-size: {px(48)}px; font-weight: bold; color: #f39c12;"))
        outer.addWidget(title)
        # Removed the addSpacing(px(20)) that was here -- it wasn't
        # just adding 20px: outer.setSpacing(px(10)) above applies
        # BETWEEN every pair of items too, so a spacer item counted as
        # its own item and got 10px on EACH side of it (10+20+10=40px
        # total between title and the panels). Removing it outright
        # leaves just the single setSpacing(10) gap directly between
        # title and panels_row -- most of the requested upward shift
        # comes from this one change.
        panels_row = QHBoxLayout()
        panels_row.setSpacing(px(20))

        left_panel, self.panchang_labels = self._build_panchang_panel()
        right_panel, self.suntime_labels = self._build_suntime_panel()

        panels_row.addWidget(left_panel, 1)
        panels_row.addWidget(right_panel, 1)

        outer.addLayout(panels_row)
        self.setLayout(outer)

    def _build_field_grid(self, field_defs):
        """Identical to page_panchang.py's builder -- natural tight
        spacing, no row stretch -- just with self._f() wrapping every
        stylesheet for the Devanagari font-family."""
        container = QWidget()
        layout = QVBoxLayout()
        # Left margin increased from px(30) to px(70) -- shifts the
        # whole field grid (heading|colon|value, same column alignment
        # as before -- left-aligned, unchanged) right on BOTH panels,
        # since this builder is shared by _build_panchang_panel and
        # _build_suntime_panel.
        layout.setContentsMargins(px(70), 0, 0, 0)

        grid = QGridLayout()
        grid.setHorizontalSpacing(px(14))
        # Reduced to 0 -- verified with the real font that
        # QGridLayout.setVerticalSpacing() has no hidden extra spacing
        # (unlike QVBoxLayout's default spacing() bug found earlier),
        # and even at 0 there's still real unused padding inside each
        # label's own box (~14px for headings, ~6px for detail lines)
        # before ink would touch. Hindi-only; page_panchang.py keeps
        # its original px(10).
        grid.setVerticalSpacing(0)
        grid.setColumnStretch(2, 1)

        labels = {}
        row = 0
        for key, heading_text, num_detail_lines in field_defs:
            row_widgets = []

            heading = QLabel(heading_text)
            heading.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            heading.setStyleSheet(self._f(f"font-size: {px(MAIN_FONT)}px; font-weight: bold; color: #bb86fc;"))
            grid.addWidget(heading, row, 0)
            row_widgets.append(heading)

            colon = QLabel(":")
            colon.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            colon.setStyleSheet(self._f(f"font-size: {px(MAIN_FONT)}px; font-weight: bold; color: #bb86fc;"))
            grid.addWidget(colon, row, 1)
            row_widgets.append(colon)

            value = QLabel("...")
            value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            value.setWordWrap(True)
            value.setStyleSheet(self._f(f"font-size: {px(MAIN_FONT)}px; font-weight: bold;"))
            grid.addWidget(value, row, 2)
            labels[key] = value
            row_widgets.append(value)
            # Forces this row to the same height on both panels --
            # see self._main_row_height's comment in __init__.
            grid.setRowMinimumHeight(row, self._main_row_height)
            row += 1

            for i in range(num_detail_lines):
                detail_label = QLabel("")
                detail_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                detail_label.setWordWrap(True)
                detail_label.setStyleSheet(self._f(f"font-size: {px(DETAIL_FONT)}px; color: #cccccc;"))
                grid.addWidget(detail_label, row, 2)
                detail_key = key + "_range" if i == 0 else key + f"_range{i + 1}"
                labels[detail_key] = detail_label
                row_widgets.append(detail_label)
                grid.setRowMinimumHeight(row, self._detail_row_height)
                row += 1

            labels[key + "_row"] = row_widgets

        layout.addLayout(grid)
        layout.addStretch()

        container.setLayout(layout)
        return container, labels

    def _build_panchang_panel(self):
        # Unchanged reference spacing (see page_panchang.py) -- headings
        # come from HEADINGS_HI instead of the YAML's own English
        # `heading` value, same pattern as page_home_hi.py.
        field_defs = [
            (f["key"], HEADINGS_HI.get(f["key"], f["heading"]), f["detail_lines"])
            for f in load_page_layout()["page_panchang_left"]
        ]
        return self._build_field_grid(field_defs)

    def _build_suntime_panel(self):
        # Same row-alignment reservation as page_panchang.py: every
        # non-Eclipse field here gets one reserved blank detail line so
        # it lands at the same height as the left panel's rows, without
        # touching the left panel itself. Eclipse (last row) keeps its
        # real 2 lines and doesn't line up with Ayana -- same accepted
        # exception as the English page.
        field_defs = []
        for f in load_page_layout()["page_panchang_right"]:
            key = f["key"]
            heading = HEADINGS_HI.get(key, f["heading"])
            detail_lines = f["detail_lines"]
            if key != "eclipse":
                detail_lines = max(detail_lines, 1)
            field_defs.append((key, heading, detail_lines))
        return self._build_field_grid(field_defs)

    # -------------------------------------------------------------------
    # Refresh -- both halves together
    # -------------------------------------------------------------------

    def _update(self):
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc + IST_OFFSET
        jd_now = datetime_to_julday(now_utc)

        sun = get_sun_times_details(now_ist, self.lat, self.lon)
        sunrise_jd = sun["sunrise_jd"]
        sunset_jd = sun["sunset_jd"]
        next_sunrise_jd = get_sunrise_jd(sunset_jd, self.lat, self.lon)

        self._update_panchang(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
        self._update_suntime(sun)

    def _update_panchang(self, jd_now, sunrise_jd, sunset_jd, next_sunrise_jd):
        nakshatra = get_nakshatra_details(jd_now)
        yoga = get_yoga_details(jd_now)
        karana = get_karana_details(jd_now)
        chandra = get_chandra_rashi_details(jd_now)
        surya = get_surya_rashi_details(jd_now)

        # category matches translations_hi.py's _VALUE_TABLES keys
        details = {
            "nakshatra": (nakshatra, "nakshatra"),
            "yoga": (yoga, "yoga"),
            "karana": (karana, "karana"),
            "chandra_rashi": (chandra, "rashi"),
            "surya_rashi": (surya, "rashi"),
        }
        for field, (d, category) in details.items():
            self.panchang_labels[field].setText(translate_value(category, d["name"]))
            start_short = _format_short(d["start_ist"])
            end_short = _format_short(d["end_ist"])
            self.panchang_labels[field + "_range"].setText(f"({start_short} {PHRASE_TO} {end_short} {PHRASE_TILL})")

        # Abhijit and Brahma Muhurta -- these are literal fixed labels
        # in page_panchang.py (not sourced from muhurta.py's own name
        # lists), so they use the dedicated LABEL_ constants rather
        # than translate_value("muhurta", ...).
        muhurta = get_muhurta_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
        self.panchang_labels["abhijit"].setText(LABEL_ABHIJIT)
        self.panchang_labels["abhijit_range"].setText(
            f"({_format_short(muhurta['abhijit_start_ist'])} {PHRASE_TO} "
            f"{_format_short(muhurta['abhijit_end_ist'])} {PHRASE_TILL})"
        )

        brahma = get_brahma_muhurta(sunrise_jd)
        self.panchang_labels["brahma"].setText(LABEL_BRAHMA_SHUBH)
        self.panchang_labels["brahma_range"].setText(
            f"({_format_short(brahma['start_ist'])} {PHRASE_TO} {_format_short(brahma['end_ist'])} {PHRASE_TILL})"
        )

        self.panchang_labels["ayana"].setText(translate_value("ayana", get_ayana(jd_now)))

    def _update_eclipse(self):
        now_utc = datetime.now(timezone.utc)
        jd_now = datetime_to_julday(now_utc)

        row_widgets = self.suntime_labels["eclipse_row"]

        info = get_eclipse_display_info(jd_now, self.lat, self.lon, self.location_name)
        if info is None:
            for w in row_widgets:
                w.hide()
            return

        # eclipse "type" (Lunar/Solar) not yet translated -- pending
        # engine/eclipse.py (see translations_hi.py's status note).
        type_value, line1, line2 = format_two_lines(info)
        self.suntime_labels["eclipse"].setText(type_value)
        self.suntime_labels["eclipse_range"].setText(line1)
        self.suntime_labels["eclipse_range2"].setText(line2)

        for w in row_widgets:
            w.show()

    def _update_suntime(self, sun):
        jd_now = datetime_to_julday(datetime.now(timezone.utc))

        sunrise_time_only = datetime.strptime(sun["sunrise_ist"], "%Y-%m-%d %H:%M:%S IST").strftime("%H:%M:%S")
        sunset_time_only = datetime.strptime(sun["sunset_ist"], "%Y-%m-%d %H:%M:%S IST").strftime("%H:%M:%S")

        self.suntime_labels["sunrise"].setText(sunrise_time_only)
        self.suntime_labels["sunset"].setText(sunset_time_only)

        from sun_times import get_local_midnight_jd_ut
        now_ist = datetime.now(timezone.utc) + IST_OFFSET
        midnight_jd = get_local_midnight_jd_ut(now_ist)
        moonrise_jd = get_moonrise_jd(midnight_jd, self.lat, self.lon)
        moonset_jd = get_moonset_jd(midnight_jd, self.lat, self.lon)
        self.suntime_labels["moonrise"].setText(_jd_to_ist_time_only(moonrise_jd))
        self.suntime_labels["moonset"].setText(_jd_to_ist_time_only(moonset_jd))

        # dinman/ratriman/day_length come from sun_times.py as
        # already-formatted strings (not a fixed name-list lookup),
        # so they're passed through unchanged, same as page_panchang.py --
        # ask me to translate sun_times.py's own formatting if you'd
        # rather these be in Devanagari too.
        self.suntime_labels["dinman"].setText(sun["dinman"])
        self.suntime_labels["ratriman"].setText(sun["ratriman"])
        self.suntime_labels["day_length"].setText(sun["day_length"])


# =============================================================================
# Standalone test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    app = QApplication(sys.argv)
    page = PagePanchangHi()
    screen_size = app.primaryScreen().availableGeometry().size()
    page.resize(screen_size.width(), screen_size.height())
    page.setWindowTitle("Page 2: Dainik Panchang (Hindi) (standalone test)")
    page.show()
    sys.exit(app.exec_())
