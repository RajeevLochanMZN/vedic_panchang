"""
ui/page_calendar_hi.py

Hindi/Devanagari twin of page_calendar.py. SEPARATE FILE --
page_calendar.py is not modified or imported here; same layout,
colors, and spacing, with headings/values rendered in Devanagari.

NUMERALS: day numbers and the year stay in international form (0-9),
same policy as every other Hindi page in this project.

FONT HANDLING -- two different techniques used on this page:
  - Plain QLabels (title bar, weekday headers) go through self._f(),
    same self._f() helper pattern as page_home_hi.py/page_panchang_hi.py.
  - Each day cell is a QWidget containing TWO separate labels (not one
    combined RichText block): a day-number+Tithi label (HTML table,
    day number in plain font, Tithi with inline font-family since it's
    genuine Devanagari text) and a separate festival label (its own
    QSS stylesheet font-family, only added when a festival exists).
    Splitting into two widgets (with a stretch between them) is what
    lets the festival text pin to the BOTTOM of the cell with a
    flexible empty gap above it -- a single RichText document has no
    way to do that (no flexbox/justify-content support in Qt's rich
    text engine). Font-family is still never applied to the plain
    day-number text, same reasoning as page_home_hi.py's digit-
    clipping bug elsewhere in this project.
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

from translations_hi import (
    HEADINGS_HI, translate_value, translate_masa, translate_month,
    translate_weekday_short, get_devanagari_font_family,
)

IST_OFFSET = timedelta(hours=5, minutes=30)


def get_day_panchang_summary_hi(day_dt_ist: datetime, lat: float, lon: float) -> dict:
    """
    Same computation as page_calendar.py's get_day_panchang_summary(),
    plus Hindi translation of the display strings. Kept as a separate
    function (not imported from page_calendar.py) since it returns
    Hindi-translated fields instead of English ones -- everything
    else about the calculation is identical.
    """
    midnight_jd = get_local_midnight_jd_ut(day_dt_ist)
    sunrise_jd = get_sunrise_jd(midnight_jd, lat, lon)

    tithi_number = get_tithi_number(sunrise_jd)
    tithi_name, paksha = get_tithi_name_and_paksha(tithi_number)

    festivals = get_todays_festivals(sunrise_jd, sunrise_jd - 1.0)
    festival_names = [f["name"] for f in festivals]

    return {
        "paksha_hi": translate_value("paksha", paksha),
        "tithi_name_hi": translate_value("tithi", tithi_name),
        "festivals_hi": [translate_value("festival", name) for name in festival_names],
        "has_festival": bool(festival_names),
    }


class PageCalendarHi(QWidget):
    def __init__(self):
        super().__init__()
        self.lat, self.lon = get_location()
        self.font_family = get_devanagari_font_family()
        self._build_ui()
        self._render_current_month()

    def _f(self, css: str) -> str:
        return css + f" font-family: '{self.font_family}';"

    def _build_ui(self):
        # No self._f() here -- pure background/color container, no
        # text of its own (see page_home_hi.py/page_panchang_hi.py's
        # identical fix for why this matters: Qt Style Sheets inherit
        # font-family to any descendant that doesn't declare its own).
        self.setStyleSheet("background-color: #4a1520; color: white;")
        self.main_layout = QVBoxLayout()

        title_bar = QWidget()
        # Also a pure container -- no font-family here either.
        title_bar.setStyleSheet("background-color: #f39c12;")
        title_row = QHBoxLayout()
        # Top/bottom margin reduced from px(10) -- measured this is
        # genuine adjustable padding (title bar height = margins +
        # the title label's own font-driven box height exactly, no
        # hidden extra), unlike a label's own box height which isn't
        # safely reducible.
        title_row.setContentsMargins(px(30), px(4), px(30), px(4))

        self.samvat_label = QLabel("...")
        self.samvat_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # Mixes "विक्रम संवत्:" with a plain numeral year in one short
        # label -- fine to font the whole thing (unlike the Home
        # page's giant standalone digit displays, this is a small,
        # single-line label with genuine Devanagari text in it, so
        # there's no clipping-height risk from doing so).
        self.samvat_label.setStyleSheet(self._f(f"font-size: {px(26)}px; font-weight: bold; color: #1a1a1a;"))
        title_row.addWidget(self.samvat_label)

        title_row.addStretch()

        self.title_label = QLabel("...")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(self._f(f"font-size: {px(48)}px; font-weight: bold; color: #1a1a1a;"))
        title_row.addWidget(self.title_label)

        title_row.addStretch()

        self.masa_label = QLabel("...")
        self.masa_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.masa_label.setStyleSheet(self._f(f"font-size: {px(26)}px; font-weight: bold; color: #1a1a1a;"))
        title_row.addWidget(self.masa_label)

        title_bar.setLayout(title_row)
        self.main_layout.addWidget(title_bar)

        self.grid_container = QWidget()
        self.main_layout.addWidget(self.grid_container)

        self.setLayout(self.main_layout)

    def _render_current_month(self):
        now_ist = datetime.now(timezone.utc) + IST_OFFSET
        today_day = now_ist.day
        # Month + year combined, Hindi month name -- numerals for the
        # year stay international form.
        month_hi = translate_month(now_ist.strftime("%B"))
        self.title_label.setText(f"{month_hi} {now_ist.strftime('%Y')}")

        month_weeks = calendar.monthcalendar(now_ist.year, now_ist.month)

        first_day_num = min(d for week in month_weeks for d in week if d != 0)
        last_day_num = max(d for week in month_weeks for d in week if d != 0)
        first_day_dt = datetime(now_ist.year, now_ist.month, first_day_num)
        last_day_dt = datetime(now_ist.year, now_ist.month, last_day_num)

        first_midnight_jd = get_local_midnight_jd_ut(first_day_dt)
        first_sunrise_jd = get_sunrise_jd(first_midnight_jd, self.lat, self.lon)
        last_midnight_jd = get_local_midnight_jd_ut(last_day_dt)
        last_sunrise_jd = get_sunrise_jd(last_midnight_jd, self.lat, self.lon)

        # Equality check stays on the raw English names (matching
        # page_calendar.py's own logic exactly); only the DISPLAY
        # strings are translated, via translate_masa() (not plain
        # translate_value()) since get_purnimanta_masa_name() can
        # carry an Adhik/Kshaya suffix -- see translations_hi.py's
        # translate_masa() docstring.
        masa_first = get_purnimanta_masa_name(first_sunrise_jd)
        masa_last = get_purnimanta_masa_name(last_sunrise_jd)
        masa_first_hi = translate_masa(masa_first)
        masa_last_hi = translate_masa(masa_last)
        masa_display = masa_first_hi if masa_first == masa_last else f"{masa_first_hi}/{masa_last_hi}"
        self.masa_label.setText(masa_display)

        vikram_year = get_vikram_samvat_year(first_sunrise_jd)
        self.samvat_label.setText(f"{HEADINGS_HI['vikram_samvat']}: {vikram_year}")

        grid = QGridLayout()
        grid.setSpacing(px(3))

        weekday_headers = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for col, day_name in enumerate(weekday_headers):
            header = QLabel(translate_weekday_short(day_name))
            header.setAlignment(Qt.AlignCenter)
            header.setStyleSheet(self._f(f"font-size: {px(30)}px; font-weight: bold; color: #e67e22;"))
            grid.addWidget(header, 0, col)

        for row, week in enumerate(month_weeks, start=1):
            for col, day_num in enumerate(week):
                if day_num == 0:
                    continue

                day_dt = datetime(now_ist.year, now_ist.month, day_num)
                summary = get_day_panchang_summary_hi(day_dt, self.lat, self.lon)

                is_today = (day_num == today_day)
                has_festival = summary["has_festival"]
                bg_color = "#f39c12" if is_today else ("#5a2a10" if has_festival else "#2c0f18")
                text_color = "#1a1a1a" if is_today else "white"
                festival_color = "#1a1a1a" if is_today else "#ffcf70"

                # Redesigned layout: day number (left) and Paksha+Tithi
                # (right-aligned, same row, vertically centered to the
                # date via a 1-row HTML table -- Qt RichText supports
                # basic table vertical-align reliably, unlike CSS
                # float). Verified widths with the real font first:
                # even the widest realistic Paksha+Tithi combo
                # ("शुक्ल त्रयोदशी" etc.) comfortably fits beside the
                # day number in a ~140px cell (110px combined vs
                # ~128px usable).
                #
                # Day-number cell: no font-family override, same
                # reasoning as before -- plain digits don't need it.
                day_tithi_html = (
                    f"<table width='100%'><tr>"
                    f"<td style='font-size:{px(36)}px; font-weight:bold; color:{text_color};'>{day_num}</td>"
                    f"<td align='right' style='font-size:{px(14)}px; color:{text_color}; "
                    f"font-family:\"{self.font_family}\";'>{summary['paksha_hi']} {summary['tithi_name_hi']}</td>"
                    f"</tr></table>"
                )

                # Cell is now a QWidget containing TWO separate labels
                # with a stretch between them, rather than one QLabel
                # with stacked HTML -- a single RichText document can't
                # pin part of its content to the bottom with a flexible
                # gap above it (no CSS flexbox/justify-content support
                # in Qt's rich text engine). This structure pins the
                # festival label to the bottom: normally it sits with
                # empty space above it (stretch absorbs the gap), and
                # only grows upward on its own if the text wraps to a
                # second line (a two-festival day) -- the day/tithi
                # row at the top never moves either way.
                cell = QWidget()
                cell.setAttribute(Qt.WA_StyledBackground, True)  # plain QWidget doesn't auto-paint QSS background/radius otherwise
                cell.setStyleSheet(f"background-color: {bg_color}; border-radius: {px(4)}px;")
                cell_layout = QVBoxLayout()
                cell_layout.setContentsMargins(px(6), px(6), px(6), px(6))
                cell_layout.setSpacing(0)

                day_tithi_label = QLabel(day_tithi_html)
                day_tithi_label.setTextFormat(Qt.RichText)
                cell_layout.addWidget(day_tithi_label)

                cell_layout.addStretch()

                if summary["festivals_hi"]:
                    festival_text = ", ".join(summary["festivals_hi"])
                    festival_label = QLabel(festival_text)
                    festival_label.setWordWrap(True)
                    festival_label.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
                    festival_label.setStyleSheet(
                        f"font-size:{px(12)}px; font-weight:bold; color:{festival_color}; "
                        f"font-family:'{self.font_family}';"
                    )
                    cell_layout.addWidget(festival_label)

                cell.setLayout(cell_layout)
                # Re-measured headlessly (offscreen Qt, real Noto Sans
                # Devanagari, worst-case strings) against this exact
                # widget structure: no-festival cells need ~59px,
                # single-festival ~75px, a two-festival wrapped day
                # ~91px. This is a MINIMUM, not a fixed height, so a
                # genuine two-festival day still grows taller on its
                # own via the festival label's word-wrap -- the floor
                # only needs to cover the common (0-1 festival) case,
                # not the rare worst case. The previous px(108) forced
                # EVERY cell in EVERY row up to 108px regardless of
                # content, which -- since QGridLayout sizes each row
                # by its tallest cell -- padded most rows 30-50px
                # taller than needed and pushed the whole 6-row grid
                # taller than the window, clipping the last week's row
                # at the bottom. px(85) leaves ~13% headroom above the
                # single-festival case (75px) to absorb platform text-
                # shaping differences (Windows DirectWrite vs this
                # Linux/HarfBuzz test env -- see project notes on
                # Devanagari row-height cross-platform disagreement).
                cell.setMinimumHeight(px(85))
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
    page = PageCalendarHi()
    screen_size = app.primaryScreen().availableGeometry().size()
    page.resize(screen_size.width(), screen_size.height())
    page.setWindowTitle("Page 4: Calendar (Hindi) (standalone test)")
    page.show()
    sys.exit(app.exec_())
