"""
ui/page_sun_time.py

Page 3 (Sun & Time Divisions): sunrise, sunset, Dinman, Ratriman,
day length, Ritu, Ayana, Muhurta, Shubh Muhurta, Pahar.

Single refresh timer -- nothing here needs per-second updates.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QGridLayout, QLabel
from PyQt5.QtCore import QTimer, Qt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

from ephemeris import init_ephemeris, datetime_to_julday
from sun_times import get_sun_times_details, get_sunrise_jd
from masa import get_ritu, get_ayana
from muhurta import get_muhurta_details, get_brahma_muhurta, get_pahar_details
from config_loader import get_location

IST_OFFSET = timedelta(hours=5, minutes=30)


class PageSunTime(QWidget):
    REFRESH_INTERVAL_MS = 20 * 1000  # 20s for debugging; bump to 60s+ later

    def __init__(self):
        super().__init__()
        self.lat, self.lon = get_location()
        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update)
        self.timer.start(self.REFRESH_INTERVAL_MS)

        self._update()

    def _build_ui(self):
        self.setStyleSheet("background-color: #0d3b36; color: white;")
        layout = QVBoxLayout()

        title = QLabel("Sun & Time Divisions")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 40px; font-weight: bold; color: #f39c12;")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.labels = {}

        field_titles = [
            ("sunrise", "Sunrise"),
            ("sunset", "Sunset"),
            ("dinman", "Dinman (Day)"),
            ("ratriman", "Ratriman (Night)"),
            ("day_length", "Day Length"),
            ("ritu", "Ritu"),
            ("ayana", "Ayana"),
            ("muhurta", "Current Muhurta"),
            ("abhijit", "Abhijit Muhurta"),
            ("brahma", "Brahma Muhurta"),
            ("pahar", "Current Pahar"),
        ]

        for row, (field, title_text) in enumerate(field_titles):
            heading = QLabel(title_text)
            heading.setStyleSheet("font-size: 24px; font-weight: bold; color: #4ecdc4;")
            grid.addWidget(heading, row, 0)

            value_label = QLabel("...")
            value_label.setStyleSheet("font-size: 26px;")
            self.labels[field] = value_label
            grid.addWidget(value_label, row, 1)

        layout.addLayout(grid)
        self.setLayout(layout)

    def _update(self):
        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc + IST_OFFSET
        jd_now = datetime_to_julday(now_utc)

        sun = get_sun_times_details(now_ist, self.lat, self.lon)
        sunrise_jd = sun["sunrise_jd"]
        sunset_jd = sun["sunset_jd"]
        next_sunrise_jd = get_sunrise_jd(sunset_jd, self.lat, self.lon)

        self.labels["sunrise"].setText(sun["sunrise_ist"])
        self.labels["sunset"].setText(sun["sunset_ist"])
        self.labels["dinman"].setText(sun["dinman"])
        self.labels["ratriman"].setText(sun["ratriman"])
        self.labels["day_length"].setText(sun["day_length"])

        self.labels["ritu"].setText(get_ritu(jd_now))
        self.labels["ayana"].setText(get_ayana(jd_now))

        muhurta = get_muhurta_details(jd_now, sunrise_jd, sunset_jd)
        if muhurta["current_muhurta_number"]:
            self.labels["muhurta"].setText(
                f"{muhurta['current_muhurta_number']}/15 -- {muhurta['current_muhurta_name']}"
            )
        else:
            self.labels["muhurta"].setText("(nighttime)")
        self.labels["abhijit"].setText(f"{muhurta['abhijit_start_ist']}  to  {muhurta['abhijit_end_ist']}")

        brahma = get_brahma_muhurta(sunrise_jd)
        self.labels["brahma"].setText(f"{brahma['start_ist']}  to  {brahma['end_ist']}")

        pahar = get_pahar_details(jd_now, sunrise_jd, sunset_jd, next_sunrise_jd)
        self.labels["pahar"].setText(f"{pahar['name']}  ({pahar['start_ist']}  to  {pahar['end_ist']})")


# =============================================================================
# Standalone test
# =============================================================================

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    app = QApplication(sys.argv)
    page = PageSunTime()
    page.resize(1024, 768)
    page.setWindowTitle("Page 3: Sun & Time Divisions (standalone test)")
    page.show()
    sys.exit(app.exec_())
