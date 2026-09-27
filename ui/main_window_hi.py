"""
ui/main_window_hi.py

Hindi/Devanagari twin of main_window.py. SEPARATE FILE --
main_window.py is not modified here; imports the three Hindi pages
(page_home_hi.py, page_panchang_hi.py, page_calendar_hi.py) instead
of their English counterparts, and the on-screen navigation buttons
show Hindi labels. Page-switching logic, window sizing, and the
opens-on-Home/no-auto-rotation behavior are all identical to
main_window.py -- see that file's own docstring for the full
reasoning behind those decisions.

This is the language a given device's launch script picks -- per the
project's decision, there's no runtime switch between this and
main_window.py; each physical device runs one or the other.

BOTTOM ROW: the on-screen navigation buttons (_build_test_button_row,
kept below as a commented-out reference) have been replaced with a
plain "वैदिक घड़ी" banner -- navigation is now handled by the 4
physical hardware buttons (hardware/buttons.py) instead. The old
button code is preserved in a comment rather than deleted, in case
on-screen buttons are ever wanted again (e.g. as a fallback if the
hardware buttons aren't connected). go_to_page() itself is UNCHANGED
and still needed -- hardware/buttons.py's ButtonController will call
it (via whatever callbacks main_window_hi.py wires up) exactly the
same way the old on-screen buttons did.
"""

import os
import sys

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel,
)
from PyQt5.QtCore import Qt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
from ephemeris import init_ephemeris

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hardware"))
from buttons import ButtonController
from wifi_setup import enter_wifi_setup_mode

from page_home_hi import PageHomeHi
from page_panchang_hi import PagePanchangHi
from page_calendar_hi import PageCalendarHi
from scaling import px
from translations_hi import get_devanagari_font_family


class MainWindowHi(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("पंचांग क्लॉक")

        self.font_family = get_devanagari_font_family()

        screen_size = QApplication.instance().primaryScreen().availableGeometry().size()
        self.resize(screen_size.width(), screen_size.height())

        self.stacked_widget = QStackedWidget()

        self.page1 = PageHomeHi()
        self.page2 = PagePanchangHi()
        self.page3 = PageCalendarHi()

        for page in (self.page1, self.page2, self.page3):
            self.stacked_widget.addWidget(page)
        # Opens on Page 1 (Home), same as main_window.py.

        central = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.stacked_widget)
        main_layout.addWidget(self._build_banner_row())
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # Wires the 4 physical hardware buttons to this window's own
        # go_to_page() -- the SAME method the old on-screen buttons
        # used to call, now the only way pages are switched since the
        # banner replaced them. self.button_controller MUST be kept
        # as an instance attribute (not a local variable) -- gpiozero
        # stops listening for button presses if this object gets
        # garbage-collected. Wi-Fi Setup (button 4) still uses the
        # placeholder from hardware/buttons.py until that feature is
        # built -- swap it for the real function once it exists.
        # NOTE: this only works when actually running on the Pi
        # itself (needs real GPIO hardware) -- it will fail if this
        # file is ever run on a plain PC.
        #
        # IMPORTANT: .connect(), not constructor callbacks -- see
        # hardware/buttons.py's module docstring for why. In short:
        # gpiozero fires button events on its own background thread,
        # and calling Qt GUI code (like go_to_page, which touches
        # self.stacked_widget) directly from that thread crashed the
        # app outright (a segfault was hit during testing). Signals
        # connected this way are safely queued onto the main GUI
        # thread by Qt automatically instead.
        self.button_controller = ButtonController()
        self.button_controller.home_pressed.connect(lambda: self.go_to_page(1))
        self.button_controller.panchang_pressed.connect(lambda: self.go_to_page(2))
        self.button_controller.calendar_pressed.connect(lambda: self.go_to_page(3))
        self.button_controller.wifi_setup_pressed.connect(enter_wifi_setup_mode)

    def go_to_page(self, page_number: int):
        """page_number is 1-3, matching Button 1-3. Identical to
        main_window.py -- this is what hardware/buttons.py will call
        on the Pi regardless of which language build is running."""
        self.stacked_widget.setCurrentIndex(page_number - 1)

    def _build_banner_row(self) -> QWidget:
        """
        Replaces the old on-screen nav buttons (see the commented-out
        _build_test_button_row below) with a plain "वैदिक घड़ी" banner,
        now that navigation is handled by the 4 physical hardware
        buttons instead. Same row height (px(60), matching the old
        buttons' setMinimumHeight) and same row background/margins as
        before, so the overall window layout is unaffected.

        Font size 40px chosen via headless measurement against the
        real Noto Sans Devanagari font: the true max that fits within
        this row's 60px height is ~44px (58px tall) before clipping,
        but 40px was chosen instead for ~12% safety headroom, given
        this project's own prior history of cross-platform Devanagari
        text-shaping differences (Windows DirectWrite vs the Pi's
        Linux/HarfBuzz rendering) causing real clipping bugs elsewhere
        (see page_calendar_hi.py's cell-height fix for the same issue).
        """
        row = QWidget()
        # No font-family here -- pure background container; the label
        # below sets its own explicit stylesheet regardless (same
        # reasoning as the old button row's identical comment).
        row.setStyleSheet("background-color: #1a1a1a;")
        layout = QHBoxLayout()
        layout.setContentsMargins(px(10), px(10), px(10), px(10))

        banner_label = QLabel("वैदिक घड़ी")
        banner_label.setAlignment(Qt.AlignCenter)
        banner_label.setMinimumHeight(px(60))
        # Saffron/gold (#f39c12) matches the accent color already used
        # in this project's title bars (e.g. page_calendar_hi.py).
        banner_label.setStyleSheet(f"""
            font-size: {px(40)}px;
            font-weight: bold;
            font-family: '{self.font_family}';
            color: #f39c12;
        """)
        layout.addWidget(banner_label)

        row.setLayout(layout)
        return row

    # -------------------------------------------------------------------
    # REPLACED by _build_banner_row() above -- kept here, commented out,
    # as a reference in case on-screen nav buttons are ever wanted again
    # (e.g. as a fallback if the hardware buttons aren't connected).
    # -------------------------------------------------------------------
    # def _build_test_button_row(self) -> QWidget:
    #     row = QWidget()
    #     # No font-family here -- pure background container, no text of
    #     # its own (see page_home_hi.py etc.'s identical fix/comment
    #     # for why: font-family would inherit down to any child that
    #     # doesn't set its own -- irrelevant here anyway since every
    #     # button below sets its own explicit stylesheet regardless).
    #     row.setStyleSheet("background-color: #1a1a1a;")
    #     layout = QHBoxLayout()
    #     layout.setContentsMargins(px(10), px(10), px(10), px(10))
    #     layout.setSpacing(px(8))
    #
    #     # font-family added here (English version's button_style has
    #     # none) since these buttons now show genuine Devanagari text.
    #     button_style = f"""
    #         QPushButton {{
    #             background-color: #ecf0f1;
    #             color: #1a1a1a;
    #             font-size: {px(14)}px;
    #             font-weight: bold;
    #             font-family: '{self.font_family}';
    #             border: {px(2)}px solid #7f8c8d;
    #             border-radius: {px(6)}px;
    #             padding: {px(8)}px;
    #         }}
    #         QPushButton:hover {{
    #             background-color: #d0d7d9;
    #         }}
    #         QPushButton:pressed {{
    #             background-color: #bdc3c7;
    #         }}
    #     """
    #
    #     # Hindi button labels. "मुख्य पृष्ठ" (Home/main page), "पंचांग"
    #     # (matches the Panchang page's own title word), "कैलेंडर"
    #     # (Calendar, common transliteration) -- adjust wording here if
    #     # you'd prefer different phrasing.
    #     labels_and_actions = [
    #         ("मुख्य पृष्ठ", lambda: self.go_to_page(1)),
    #         ("पंचांग", lambda: self.go_to_page(2)),
    #         ("कैलेंडर", lambda: self.go_to_page(3)),
    #     ]
    #
    #     for label_text, action in labels_and_actions:
    #         btn = QPushButton(label_text)
    #         btn.setMinimumHeight(px(60))
    #         btn.setStyleSheet(button_style)
    #         btn.clicked.connect(action)
    #         layout.addWidget(btn)
    #
    #     row.setLayout(layout)
    #     return row


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    app = QApplication(sys.argv)
    window = MainWindowHi()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
