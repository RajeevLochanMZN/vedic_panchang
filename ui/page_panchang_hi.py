"""
ui/page_panchang_hi.py

Hindi/Devanagari twin of page_panchang.py. SEPARATE FILE --
page_panchang.py is not modified or imported here.

ARCHITECTURE NOTE -- why this is ONE unified 7-column QGridLayout
(columns 0-2 = left heading/colon/value, 3 = spacer gap, 4-6 = right
heading/colon/value) instead of two separate grids side by side:

An earlier version of this file (like page_home_hi.py and
page_panchang.py itself) built the left and right panels as two
INDEPENDENT QGridLayout instances, each computing its own row heights
from its own content. On this project's Linux test environment those
two grids always agreed. On real Windows hardware they did NOT --
real screenshots showed a small, consistent, growing per-row drift
between the panels, most likely from the OS's Devanagari text-shaping
engine (DirectWrite) computing very slightly different natural label
heights than Linux's (HarfBuzz) for the identical font/size. Several
fixes were tried and failed or only partially worked: guessing a
safe row-height margin from QFontMetrics (too small, then flipped
which panel fell behind when enlarged), and measuring+syncing row
heights at runtime via heightForWidth() after layout (workable, but
still reactive -- fixing a mismatch after the fact each refresh).

Merging both panels into ONE grid removes the mismatch at its root:
since a given field's left and right entries now share the literal
same grid ROW (just different columns), Qt computes that row's
height ONCE, as the max of every widget in it -- both sides
automatically included in a single computation. There are no longer
two independent computations that could ever disagree, on any
platform, so this isn't something margins or after-the-fact syncing
needs to compensate for anymore.

NUMERALS: dates/times in the range lines (e.g. "28-08-26 14:32:10")
intentionally stay in international form (0-9) -- see
translations_hi.py's module docstring.

FONT: loads the bundled Devanagari font once via
translations_hi.get_devanagari_font_family() and appends
`font-family: '<name>';` to every label's stylesheet through the
self._f() helper below, same pattern as page_home_hi.py. Container/
background-only stylesheets (self.setStyleSheet on the page itself)
deliberately do NOT include font-family -- see page_home_hi.py's
comments on why Qt Style Sheet inheritance makes that matter.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QGridLayout, QLabel,
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

# Unified font sizes
MAIN_FONT = 25
DETAIL_FONT = 12


def _format_short(ist_string: str) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS IST' into 'DD-MM-YY HH:MM:SS'"""
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

        # Load the bundled Devanagari font once
        self.font_family = get_devanagari_font_family()

        # Compute tight row pixel bounds using font metrics
        self._main_row_height, self._detail_row_height = self._compute_row_heights()

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(self.REFRESH_INTERVAL_MS)

        self.eclipse_timer = QTimer(self)
        self.eclipse_timer.timeout.connect(self._update_eclipse)
        self.eclipse_timer.start(60 * 60 * 1000)  # 60 min

        self._update()
        self._update_eclipse()

    def _f(self, css: str) -> str:
        return css + f" font-family: '{self.font_family}';"

    def _compute_row_heights(self):
        # Small cosmetic buffer only -- unlike the earlier two-grid
        # version, this margin is NOT what keeps the panels aligned
        # anymore (that's now structural -- see the module docstring).
        # It just adds a little breathing room above the bare font-
        # metric height.
        margin = px(2)

        main_font = QFont(self.font_family)
        main_font.setPixelSize(px(MAIN_FONT))
        main_font.setBold(True)
        main_height = QFontMetrics(main_font).height() + margin

        detail_font = QFont(self.font_family)
        detail_font.setPixelSize(px(DETAIL_FONT))
        detail_height = QFontMetrics(detail_font).height() + margin

        return main_height, detail_height

    # -------------------------------------------------------------------
    # UI layout -- Unified Grid Alignment Fix
    # -------------------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet("background-color: #241a3e; color: white;")
        outer = QVBoxLayout()
        outer.setContentsMargins(px(10), px(10), px(10), px(10))
        outer.setSpacing(px(4))

        # Title Section
        title = QLabel("दैनिक पंचांग")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(self._f(f"font-size: {px(48)}px; font-weight: bold; color: #f39c12;"))
        outer.addWidget(title)

        # Container for the panels
        panels_container = QWidget()
        grid = QGridLayout(panels_container)
        
        # Left margin restored to px(70) per original design, added right margin for layout symmetry
        grid.setContentsMargins(px(70), 0, px(70), 0)
        grid.setHorizontalSpacing(px(14))
        grid.setVerticalSpacing(0)

        # 6-Column Unified Structure layout:
        # Col 0: Left Heading | Col 1: Left Colon | Col 2: Left Value
        # Col 3: Spacer Gap Column separating left/right sides
        # Col 4: Right Heading | Col 5: Right Colon | Col 6: Right Value
        grid.setColumnStretch(2, 1)  # Expand left value space
        grid.setColumnMinimumWidth(3, px(60))  # Clear visual boundary separating panels
        grid.setColumnStretch(6, 1)  # Expand right value space

        # Extract layouts from config
        left_layout = load_page_layout()["page_panchang_left"]
        right_layout = load_page_layout()["page_panchang_right"]

        self.panchang_labels = {}
        self.suntime_labels = {}

        max_fields = max(len(left_layout), len(right_layout))
        current_grid_row = 0

        for i in range(max_fields):
            # --- PROCESS LEFT PANEL ELEMENT ---
            left_key = None
            left_details_count = 0
            if i < len(left_layout):
                f = left_layout[i]
                left_key = f["key"]
                heading_text = HEADINGS_HI.get(left_key, f["heading"])
                left_details_count = f["detail_lines"]

                heading = QLabel(heading_text)
                heading.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                heading.setStyleSheet(self._f(f"font-size: {px(MAIN_FONT)}px; font-weight: bold; color: #bb86fc;"))
                
                colon = QLabel(":")
                colon.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                colon.setStyleSheet(self._f(f"font-size: {px(MAIN_FONT)}px; font-weight: bold; color: #bb86fc;"))
                
                value = QLabel("...")
                value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                value.setWordWrap(True)
                value.setStyleSheet(self._f(f"font-size: {px(MAIN_FONT)}px; font-weight: bold;"))

                grid.addWidget(heading, current_grid_row, 0)
                grid.addWidget(colon, current_grid_row, 1)
                grid.addWidget(value, current_grid_row, 2)
                
                self.panchang_labels[left_key] = value
                self.panchang_labels[left_key + "_row"] = [heading, colon, value]

            # --- PROCESS RIGHT PANEL ELEMENT ---
            right_key = None
            right_details_count = 0
            if i < len(right_layout):
                f = right_layout[i]
                right_key = f["key"]
                heading_text = HEADINGS_HI.get(right_key, f["heading"])
                right_details_count = f["detail_lines"]
                
                # Align logic: reserve at least one blank row for non-eclipse right elements
                if right_key != "eclipse":
                    right_details_count = max(right_details_count, 1)

                heading = QLabel(heading_text)
                heading.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                heading.setStyleSheet(self._f(f"font-size: {px(MAIN_FONT)}px; font-weight: bold; color: #bb86fc;"))
                
                colon = QLabel(":")
                colon.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                colon.setStyleSheet(self._f(f"font-size: {px(MAIN_FONT)}px; font-weight: bold; color: #bb86fc;"))
                
                value = QLabel("...")
                value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                value.setWordWrap(True)
                value.setStyleSheet(self._f(f"font-size: {px(MAIN_FONT)}px; font-weight: bold;"))

                grid.addWidget(heading, current_grid_row, 4)
                grid.addWidget(colon, current_grid_row, 5)
                grid.addWidget(value, current_grid_row, 6)
                
                self.suntime_labels[right_key] = value
                self.suntime_labels[right_key + "_row"] = [heading, colon, value]

            # Force matching main row height dynamically
            grid.setRowMinimumHeight(current_grid_row, self._main_row_height)
            current_grid_row += 1

            # --- PROCESS DETAIL SUB-ROWS SPANNING BOTH SIDES ---
            max_details = max(left_details_count, right_details_count)
            for d_idx in range(max_details):
                # Handle left detail label setup (Placed cleanly under value column space)
                if left_key and d_idx < left_details_count:
                    d_label = QLabel("")
                    d_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    d_label.setWordWrap(True)
                    d_label.setStyleSheet(self._f(f"font-size: {px(DETAIL_FONT)}px; color: #cccccc; margin-left: {px(20)}px;"))
                    
                    grid.addWidget(d_label, current_grid_row, 2)
                    
                    d_key = left_key + "_range" if d_idx == 0 else left_key + f"_range{d_idx + 1}"
                    self.panchang_labels[d_key] = d_label
                    self.panchang_labels[left_key + "_row"].append(d_label)

                # Handle right detail label setup (Placed cleanly under value column space)
                if right_key and d_idx < right_details_count:
                    d_label = QLabel("")
                    d_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    d_label.setWordWrap(True)
                    d_label.setStyleSheet(self._f(f"font-size: {px(DETAIL_FONT)}px; color: #cccccc; margin-left: {px(20)}px;"))
                    
                    grid.addWidget(d_label, current_grid_row, 6)
                    
                    d_key = right_key + "_range" if d_idx == 0 else right_key + f"_range{d_idx + 1}"
                    self.suntime_labels[d_key] = d_label
                    self.suntime_labels[right_key + "_row"].append(d_label)

                # Force matching detail row height across both cells
                grid.setRowMinimumHeight(current_grid_row, self._detail_row_height)
                current_grid_row += 1

        grid.setRowStretch(current_grid_row, 1)  # Push layouts upwards cleanly, preventing stretching deformation
        outer.addWidget(panels_container)
        self.setLayout(outer)

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