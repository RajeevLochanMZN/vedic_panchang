"""
ui/eclipse_date_preview.py

TEMPORARY preview-only script (safe to delete). Shows the REAL
Page 2 (Panchang) exactly as it would look on Aug 27, 2026 -- one
day before the real Aug 28, 2026 lunar eclipse, so it falls inside
the "next 3 days" window and the Eclipse entry actually shows.

Uses the real PagePanchang widget at full screen size (same as the
real app), not a mockup or split view -- just forces the eclipse
calculation to the chosen date and writes the result into the page's
real widgets using the exact same formatting code the real page uses.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))

from ephemeris import init_ephemeris, datetime_to_julday
from eclipse import get_next_eclipse

from PyQt5.QtWidgets import QApplication

from page_panchang import PagePanchang, _format_eclipse_time

IST_OFFSET = timedelta(hours=5, minutes=30)

# One day before the real Aug 28, 2026 lunar eclipse -- inside the
# "next 3 days" window the page checks.
FORCED_DATE_IST = datetime(2026, 8, 27, 12, 0, 0)


def force_eclipse_display(page):
    """Recompute and display the eclipse using FORCED_DATE_IST instead
    of the real current time, writing into the page's real widgets."""
    dt_utc = (FORCED_DATE_IST - IST_OFFSET).replace(tzinfo=timezone.utc)
    jd_now = datetime_to_julday(dt_utc)

    eclipse = get_next_eclipse(jd_now, page.lat, page.lon)
    if not eclipse or "error" in eclipse:
        return

    start_short = _format_eclipse_time(eclipse["start_ist"])
    end_short = _format_eclipse_time(eclipse["end_ist"])

    page.suntime_labels["eclipse"].setText(eclipse["type"])
    page.suntime_labels["eclipse_range"].setText(f"{start_short} to {end_short}")

    detail2 = ""
    if "visibility_percent" in eclipse:
        detail2 = f"{eclipse['visibility_percent']:.0f}%"
        if eclipse.get("visible_at_max") is False:
            detail2 += f", not visible in {page.location_name}"
    page.suntime_labels["eclipse_range2"].setText(detail2)

    for w in page.suntime_labels["eclipse_row"]:
        w.show()


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    app = QApplication(sys.argv)

    page = PagePanchang()
    force_eclipse_display(page)
    page.setWindowTitle(f"Page 2 (Panchang) -- forced date {FORCED_DATE_IST.date()}")

    screen_size = app.primaryScreen().availableGeometry().size()
    page.resize(screen_size.width(), screen_size.height())
    page.show()

    sys.exit(app.exec_())
