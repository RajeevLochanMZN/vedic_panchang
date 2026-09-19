"""
ui/main_window.py

Top-level PyQt window. Holds a QStackedWidget with all 3 real pages
(Home, merged Panchang+Sun/Time, Calendar), handles page-switching
(called by hardware/buttons.py callbacks on the Pi, or by the
on-screen test buttons here on PC).

RESOLUTION SCALING: sized to the actual detected screen at startup
(matching how fullscreen/kiosk mode will work on the Pi later), and
the test-button row's pixel values go through scaling.px() -- see
ui/scaling.py for details. Each page (page_home.py, page_panchang.py,
page_calendar.py) handles its own internal scaling already.

Button mapping (3 buttons for 3 pages -- auto-rotation and the
4th "Auto ON/OFF" button were REMOVED per user request; the app
now opens on Page 1/Home and stays there until a button is pressed,
no automatic cycling):
  Button 1 -> Home
  Button 2 -> Panchang (merged Core Panchang + Sun/Time)
  Button 3 -> Calendar
"""

import os
import sys

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QPushButton,
)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
from ephemeris import init_ephemeris

from page_home import PageHome
from page_panchang import PagePanchang
from page_calendar import PageCalendar
from scaling import px


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Panchang Clock")

        # Size to the actual detected screen -- matches how the real
        # Pi fullscreen/kiosk launch will work, and is what makes
        # scaling.px() throughout every page produce a genuinely
        # full-screen, correctly-scaled result rather than a small
        # fixed-size window sitting inside a bigger screen.
        screen_size = QApplication.instance().primaryScreen().availableGeometry().size()
        self.resize(screen_size.width(), screen_size.height())

        self.stacked_widget = QStackedWidget()

        self.page1 = PageHome()
        self.page2 = PagePanchang()
        self.page3 = PageCalendar()

        for page in (self.page1, self.page2, self.page3):
            self.stacked_widget.addWidget(page)
        # Opens on Page 1 (Home) by default -- QStackedWidget starts
        # on the first-added widget, no explicit call needed.

        central = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.stacked_widget)
        main_layout.addWidget(self._build_test_button_row())  # kept at the bottom
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    # -------------------------------------------------------------------
    # Page-switching -- exactly what hardware/buttons.py will call on
    # the Pi. The on-screen buttons below call this same method, so PC
    # testing exercises the real navigation logic, not a separate
    # test-only path.
    # -------------------------------------------------------------------

    def go_to_page(self, page_number: int):
        """page_number is 1-3, matching Button 1-3."""
        self.stacked_widget.setCurrentIndex(page_number - 1)

    # -------------------------------------------------------------------
    # PC-only: on-screen buttons standing in for the 3 physical GPIO
    # buttons, so navigation is testable without any hardware. Kept at
    # the bottom of the window, below the page content.
    # -------------------------------------------------------------------

    def _build_test_button_row(self) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background-color: #1a1a1a;")
        layout = QHBoxLayout()
        layout.setContentsMargins(px(10), px(10), px(10), px(10))
        layout.setSpacing(px(8))

        button_style = f"""
            QPushButton {{
                background-color: #ecf0f1;
                color: #1a1a1a;
                font-size: {px(14)}px;
                font-weight: bold;
                border: {px(2)}px solid #7f8c8d;
                border-radius: {px(6)}px;
                padding: {px(8)}px;
            }}
            QPushButton:hover {{
                background-color: #d0d7d9;
            }}
            QPushButton:pressed {{
                background-color: #bdc3c7;
            }}
        """

        labels_and_actions = [
            ("Home", lambda: self.go_to_page(1)),
            ("Panchang", lambda: self.go_to_page(2)),
            ("Calendar", lambda: self.go_to_page(3)),
        ]

        for label_text, action in labels_and_actions:
            btn = QPushButton(label_text)
            btn.setMinimumHeight(px(60))
            btn.setStyleSheet(button_style)
            btn.clicked.connect(action)
            layout.addWidget(btn)

        row.setLayout(layout)
        return row


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)  # must happen before any page does engine calculations

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
