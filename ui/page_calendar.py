"""
ui/page_calendar.py

Page 4 (Calendar): one-month calendar view, styled after the
Prokerala Hindu Calendar reference the user pointed to -- each day
cell shows a mini Panchang summary: Paksha+Tithi and any festival(s),
not just a bare date.

RESOLUTION SCALING: all pixel values go through scaling.px() -- see
ui/scaling.py for details. The 7-column grid already distributes
width evenly by default, so no fixed-width fix was needed here (only
Page 1 had that issue, from using setFixedWidth panels).

This means real per-day ephemeris calls (sunrise + Tithi at that
day's sunrise, skipping the more expensive start/end boundary search
since the calendar only needs the identity, not exact timing). ~30
days x a handful of calls is noticeably heavier than the other
pages, but this is a button-triggered page computed once per
month-view, not something refreshed continuously -- acceptable even
on Pi hardware.
"""

import calendar
import os
import sys
from datetime import datetime, timezone, timedelta

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel
from PyQt5.QtCore import Qt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

from ephemeris import init_ephemeris, datetime_to_julday
from panchang import get_tithi_number, get_tithi_name_and_paksha
from sun_times import get_local_midnight_jd_ut, get_sunrise_jd
from festivals import get_todays_festivals
from config_loader import get_location
from scaling import px
from masa import get_purnimanta_masa_name, get_vikram_samvat_year

IST_OFFSET = timedelta(hours=5, minutes=30)


def get_day_panchang_summary(day_dt_ist: datetime, lat: float, lon: float) -> dict:
    """
    Everything a calendar cell needs for one day, evaluated AT that
    day's sunrise (matching how printed Hindu calendars show it --
    the Tithi "of the day" is whichever one prevails at sunrise).
    Only computes what's actually displayed (Tithi + festivals) --
    sunrise/sunset and Rashi/Nakshatra were dropped from the cell
    display, so skipping those calls too keeps this faster.
    """
    midnight_jd = get_local_midnight_jd_ut(day_dt_ist)
    sunrise_jd = get_sunrise_jd(midnight_jd, lat, lon)

    tithi_number = get_tithi_number(sunrise_jd)
    tithi_name, paksha = get_tithi_name_and_paksha(tithi_number)
    paksha_short = "Shu." if paksha == "Shukla" else "Kri."

    festivals = get_todays_festivals(sunrise_jd, sunrise_jd - 1.0)
    festival_names = [f["name"] for f in festivals]

    return {
        "paksha": paksha,
        "paksha_short": paksha_short,
        "tithi_name": tithi_name,
        "festivals": festival_names,
    }


class PageCalendar(QWidget):
    def __init__(self):
        super().__init__()
        self.lat, self.lon = get_location()
        self._build_ui()
        self._render_current_month()

    def _build_ui(self):
        self.setStyleSheet("background-color: #4a1520; color: white;")
        self.main_layout = QVBoxLayout()

        title_bar = QWidget()
        title_bar.setStyleSheet("background-color: #f39c12;")  # ONE solid bar, matching the 'today' cell's accent color
        title_row = QHBoxLayout()
        title_row.setContentsMargins(px(30), px(10), px(30), px(10))  # margin from left/right/top/bottom

        self.samvat_label = QLabel("...")
        self.samvat_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.samvat_label.setStyleSheet(f"font-size: {px(26)}px; font-weight: bold; color: #1a1a1a;")
        title_row.addWidget(self.samvat_label)

        title_row.addStretch()

        self.title_label = QLabel("...")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(f"font-size: {px(48)}px; font-weight: bold; color: #1a1a1a;")
        title_row.addWidget(self.title_label)

        title_row.addStretch()

        self.masa_label = QLabel("...")
        self.masa_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.masa_label.setStyleSheet(f"font-size: {px(26)}px; font-weight: bold; color: #1a1a1a;")
        title_row.addWidget(self.masa_label)

        title_bar.setLayout(title_row)
        self.main_layout.addWidget(title_bar)

        self.grid_container = QWidget()
        self.main_layout.addWidget(self.grid_container)

        self.setLayout(self.main_layout)

    def _render_current_month(self):
        now_ist = datetime.now(timezone.utc) + IST_OFFSET
        today_day = now_ist.day
        self.title_label.setText(now_ist.strftime("%B %Y"))

        month_weeks = calendar.monthcalendar(now_ist.year, now_ist.month)

        # Samvat + Masa name(s) for this displayed month, evaluated at
        # the first and last real day's sunrise (matching how each day
        # cell computes its own Tithi/Masa) -- shown as a single name
        # if the whole month falls in one Masa, or "First/Second" if
        # the Gregorian month spans a Masa transition (common, since
        # Masa boundaries don't align with Gregorian month boundaries).
        first_day_num = min(d for week in month_weeks for d in week if d != 0)
        last_day_num = max(d for week in month_weeks for d in week if d != 0)
        first_day_dt = datetime(now_ist.year, now_ist.month, first_day_num)
        last_day_dt = datetime(now_ist.year, now_ist.month, last_day_num)

        first_midnight_jd = get_local_midnight_jd_ut(first_day_dt)
        first_sunrise_jd = get_sunrise_jd(first_midnight_jd, self.lat, self.lon)
        last_midnight_jd = get_local_midnight_jd_ut(last_day_dt)
        last_sunrise_jd = get_sunrise_jd(last_midnight_jd, self.lat, self.lon)

        masa_first = get_purnimanta_masa_name(first_sunrise_jd)
        masa_last = get_purnimanta_masa_name(last_sunrise_jd)
        masa_display = masa_first if masa_first == masa_last else f"{masa_first}/{masa_last}"
        self.masa_label.setText(masa_display)

        vikram_year = get_vikram_samvat_year(first_sunrise_jd)
        self.samvat_label.setText(f"Samvat: {vikram_year}")

        grid = QGridLayout()
        grid.setSpacing(px(3))

        weekday_headers = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for col, day_name in enumerate(weekday_headers):
            header = QLabel(day_name)
            header.setAlignment(Qt.AlignCenter)
            header.setStyleSheet(f"font-size: {px(30)}px; font-weight: bold; color: #e67e22;")
            grid.addWidget(header, 0, col)

        for row, week in enumerate(month_weeks, start=1):
            for col, day_num in enumerate(week):
                if day_num == 0:
                    continue

                day_dt = datetime(now_ist.year, now_ist.month, day_num)
                summary = get_day_panchang_summary(day_dt, self.lat, self.lon)

                is_today = (day_num == today_day)
                has_festival = bool(summary["festivals"])
                bg_color = "#f39c12" if is_today else ("#5a2a10" if has_festival else "#2c0f18")
                text_color = "#1a1a1a" if is_today else "white"
                festival_color = "#1a1a1a" if is_today else "#ffcf70"

                cell_html = (
                    f"<div style='font-size:{px(36)}px; font-weight:bold; color:{text_color};'>"
                    f"{day_num}</div>"
                    f"<div style='font-size:{px(14)}px; color:{text_color};'>"
                    f"{summary['paksha']} {summary['tithi_name']}</div>"
                )
                if summary["festivals"]:
                    festival_text = ", ".join(summary["festivals"])
                    cell_html += (
                        f"<div style='font-size:{px(12)}px; font-weight:bold; color:{festival_color};'>"
                        f"{festival_text}</div>"
                    )

                cell = QLabel(cell_html)
                cell.setTextFormat(Qt.RichText)
                cell.setWordWrap(True)
                cell.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                cell.setStyleSheet(
                    f"background-color: {bg_color}; border-radius: {px(4)}px; padding: {px(6)}px;"
                )
                cell.setMinimumHeight(px(90))
                grid.addWidget(cell, row, col)

        old_container = self.grid_container
        self.grid_container = QWidget()
        self.grid_container.setLayout(grid)
        self.main_layout.replaceWidget(old_container, self.grid_container)
        old_container.deleteLater()


# =============================================================================
# Standalone test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    app = QApplication(sys.argv)
    page = PageCalendar()
    screen_size = app.primaryScreen().availableGeometry().size()
    page.resize(screen_size.width(), screen_size.height())
    page.setWindowTitle("Page 4: Calendar (standalone test)")
    page.show()
    sys.exit(app.exec_())
