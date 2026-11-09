"""
ui/page_vedic_dial_portrait_hi.py  --  the PORTRAIT dial Home page, LIVE (Hindi build).

For Pi 2: Waveshare 7-inch screen used upright (480 x 800).

It is PageVedicDialHi (all the real engine code: dial, panels, festival and
eclipse cards, timers) with the portrait layout of page_vedic_dial_portrait.py
put on top.  Nothing else changes, so a fix in page_vedic_dial_hi.py shows up
on both pages.

ui/main_window_hi.py picks this page by itself when the screen is taller than
it is wide; on a landscape screen (Pi 1) it keeps PageVedicDialHi.

Standalone test on the PC (live engine, no GPIO) -- a 480 x 800 window:
    python ui/page_vedic_dial_portrait_hi.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "engine"))

from page_vedic_dial_hi import PageVedicDialHi
from page_vedic_dial_portrait import PortraitLayoutMixin


class PageVedicDialPortraitHi(PortraitLayoutMixin, PageVedicDialHi):
    """Mixin first: its resizeEvent and set_data replace the landscape ones."""
    pass


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    from ephemeris import init_ephemeris

    init_ephemeris(ephe_path=os.path.join(_HERE, "..", "data", "ephe"))
    app = QApplication(sys.argv)
    page = PageVedicDialPortraitHi()
    page.resize(480, 800)
    page.setWindowTitle("Portrait dial page (Hindi) (standalone test)")
    page.show()
    sys.exit(app.exec_())
