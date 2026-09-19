"""
ui/page_panchang.py

Page 2: "Dainik Panchang" -- single combined title, Core Panchang
(left half) + Sun & Time Divisions (right half), 50:50 split, no
divider line between them. Both halves use a matching 2-column grid
(heading | value) with the same spacing and font sizes, so the
heading-to-value gap looks identical on both sides.

RESOLUTION SCALING: all pixel values go through scaling.px() -- see
ui/scaling.py for details.

Left: Nakshatra, Yoga, Karana, Chandra Rashi, Surya Rashi.
Right: Sunrise, Sunset, Dinman, Ratriman, Day Length, Ayana,
Abhijit Muhurta, Brahma Muhurta.

Single refresh timer for both halves together.
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
from panchang import get_nakshatra_details, get_yoga_details, get_karana_details
from rashi import get_chandra_rashi_details, get_surya_rashi_details
from sun_times import get_sun_times_details, get_sunrise_jd, get_moonrise_jd, get_moonset_jd
from masa import get_ayana
from muhurta import get_muhurta_details, get_brahma_muhurta
from eclipse_banner import get_eclipse_display_info, format_two_lines
from config_loader import get_location, load_settings, load_page_layout
from scaling import px

IST_OFFSET = timedelta(hours=5, minutes=30)

# Unified font sizes for BOTH panels -- roughly halfway between the
# original left (30px) and right (20px) panel sizes, per user request.
MAIN_FONT = 25
DETAIL_FONT = 15


def _format_short(ist_string: str) -> str:
    """Convert 'YYYY-MM-DD HH:MM:SS IST' into 'DD-MM-YY HH:MM:SS'
    (no IST suffix -- shown once as a footer note instead)."""
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


class PagePanchang(QWidget):
    REFRESH_INTERVAL_MS = 60 * 1000

    def __init__(self):
        super().__init__()
        self.lat, self.lon = get_location()
        settings = load_settings()
        self.location_name = settings.get("location", {}).get("name", "")
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(self.REFRESH_INTERVAL_MS)

        self.eclipse_timer = QTimer(self)
        self.eclipse_timer.timeout.connect(self._update_eclipse)
        self.eclipse_timer.start(60 * 60 * 1000)  # 60 min, same as Page 1

        self._update()
        self._update_eclipse()

    # -------------------------------------------------------------------
    # UI layout -- single title, 50:50 split, no divider
    # -------------------------------------------------------------------

    def _build_ui(self):
        self.setStyleSheet("background-color: #241a3e; color: white;")
        outer = QVBoxLayout()
        outer.setContentsMargins(px(10), px(10), px(10), px(10))
        outer.setSpacing(px(10))

        title = QLabel("Dainik Panchang")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"font-size: {px(48)}px; font-weight: bold; color: #f39c12;")
        outer.addWidget(title)
        outer.addSpacing(px(20))

        panels_row = QHBoxLayout()
        panels_row.setSpacing(px(20))

        left_panel, self.panchang_labels = self._build_panchang_panel()
        right_panel, self.suntime_labels = self._build_suntime_panel()

        panels_row.addWidget(left_panel, 1)
        panels_row.addWidget(right_panel, 1)

        outer.addLayout(panels_row)
        self.setLayout(outer)

    def _build_field_grid(self, field_defs):
        """
        field_defs: list of (key, heading_text, num_detail_lines) tuples,
        where num_detail_lines is 0, 1, or 2. Returns (container_widget,
        labels_dict). Both panels use this exact same builder, unchanged,
        with natural tight spacing (no row stretch) -- this is the
        original left-panel behavior, restored as the only behavior.

        labels_dict contains, per field: key (value label), key+"_range"
        (first detail line, if any), key+"_range2" (second detail line,
        if any -- used by Eclipse's two-line display), and key+"_row"
        (a list of every widget in that row, for hiding/showing the
        whole entry at once, e.g. when there's no near-term eclipse).
        """
        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(px(30), 0, 0, 0)  # left margin for both columns

        grid = QGridLayout()
        grid.setHorizontalSpacing(px(14))
        grid.setVerticalSpacing(px(10))
        grid.setColumnStretch(2, 1)  # value column absorbs extra width

        labels = {}
        row = 0
        for key, heading_text, num_detail_lines in field_defs:
            row_widgets = []

            heading = QLabel(heading_text)
            heading.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            heading.setStyleSheet(f"font-size: {px(MAIN_FONT)}px; font-weight: bold; color: #bb86fc;")
            grid.addWidget(heading, row, 0)
            row_widgets.append(heading)

            colon = QLabel(":")
            colon.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            colon.setStyleSheet(f"font-size: {px(MAIN_FONT)}px; font-weight: bold; color: #bb86fc;")
            grid.addWidget(colon, row, 1)
            row_widgets.append(colon)

            value = QLabel("...")
            value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            value.setWordWrap(True)
            value.setStyleSheet(f"font-size: {px(MAIN_FONT)}px; font-weight: bold;")
            grid.addWidget(value, row, 2)
            labels[key] = value
            row_widgets.append(value)
            row += 1

            for i in range(num_detail_lines):
                detail_label = QLabel("")
                detail_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                detail_label.setWordWrap(True)
                detail_label.setStyleSheet(f"font-size: {px(DETAIL_FONT)}px; color: #cccccc;")
                grid.addWidget(detail_label, row, 2)
                detail_key = key + "_range" if i == 0 else key + f"_range{i + 1}"
                labels[detail_key] = detail_label
                row_widgets.append(detail_label)
                row += 1

            labels[key + "_row"] = row_widgets

        layout.addLayout(grid)
        layout.addStretch()

        container.setLayout(layout)
        return container, labels

    def _build_panchang_panel(self):
        # Unchanged, original spacing -- this panel is the reference
        # the right panel now aligns itself to.
        field_defs = [
            (f["key"], f["heading"], f["detail_lines"])
            for f in load_page_layout()["page_panchang_left"]
        ]
        return self._build_field_grid(field_defs)

    def _build_suntime_panel(self):
        # The left panel's 7 top rows (Nakshatra..Brahma) each carry
        # 1 detail line, which is what gives them their row height.
        # This panel's matching 7 rows (Sunrise..Day Length) have no
        # real detail line of their own, so -- to land at the same
        # row height as the left panel WITHOUT changing anything on
        # the left -- each reserves one blank, unused detail-line row
        # here too. Eclipse (the 8th/last row) keeps its real 2 lines;
        # it won't line up with Ayana (left's 8th row, which has no
        # detail line), but that's the one row where the two panels'
        # content genuinely differs in height, and Eclipse is hidden
        # entirely whenever there's no near-term eclipse anyway.
        field_defs = []
        for f in load_page_layout()["page_panchang_right"]:
            key, heading, detail_lines = f["key"], f["heading"], f["detail_lines"]
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

        details = {
            "nakshatra": nakshatra, "yoga": yoga, "karana": karana,
            "chandra_rashi": chandra, "surya_rashi": surya,
        }
        for field, d in details.items():
            self.panchang_labels[field].setText(d["name"])
            start_short = _format_short(d["start_ist"])
            end_short = _format_short(d["end_ist"])
            self.panchang_labels[field + "_range"].setText(f"({start_short} to {end_short})")

        # Abhijit and Brahma Muhurta now live in this panel too.
        muhurta = get_muhurta_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
        self.panchang_labels["abhijit"].setText("Abhijit")
        self.panchang_labels["abhijit_range"].setText(
            f"({_format_short(muhurta['abhijit_start_ist'])} to {_format_short(muhurta['abhijit_end_ist'])})"
        )

        brahma = get_brahma_muhurta(sunrise_jd)
        self.panchang_labels["brahma"].setText("Brahma")
        self.panchang_labels["brahma_range"].setText(
            f"({_format_short(brahma['start_ist'])} to {_format_short(brahma['end_ist'])})"
        )

        # Ayana moved here (left panel) per user request -- it's a
        # purely solar/Panchang attribute, and now sits as the last
        # entry in the left column instead of the right one.
        self.panchang_labels["ayana"].setText(get_ayana(jd_now))

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

        # Moonrise/moonset, searched forward from today's local midnight
        # -- same approach as sunrise/sunset, via the same rise_trans
        # mechanism (see engine/sun_times.py get_moonrise_jd/get_moonset_jd).
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
    page = PagePanchang()
    screen_size = app.primaryScreen().availableGeometry().size()
    page.resize(screen_size.width(), screen_size.height())
    page.setWindowTitle("Page 2: Dainik Panchang (standalone test)")
    page.show()
    sys.exit(app.exec_())
