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
"""

import os
import sys

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QPushButton,
)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
from ephemeris import init_ephemeris

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
        main_layout.addWidget(self._build_test_button_row())
        central.setLayout(main_layout)
        self.setCentralWidget(central)

    def go_to_page(self, page_number: int):
        """page_number is 1-3, matching Button 1-3. Identical to
        main_window.py -- this is what hardware/buttons.py will call
        on the Pi regardless of which language build is running."""
        self.stacked_widget.setCurrentIndex(page_number - 1)

    def _build_test_button_row(self) -> QWidget:
        row = QWidget()
        # No font-family here -- pure background container, no text of
        # its own (see page_home_hi.py etc.'s identical fix/comment
        # for why: font-family would inherit down to any child that
        # doesn't set its own -- irrelevant here anyway since every
        # button below sets its own explicit stylesheet regardless).
        row.setStyleSheet("background-color: #1a1a1a;")
        layout = QHBoxLayout()
        layout.setContentsMargins(px(10), px(10), px(10), px(10))
        layout.setSpacing(px(8))

        # font-family added here (English version's button_style has
        # none) since these buttons now show genuine Devanagari text.
        button_style = f"""
            QPushButton {{
                background-color: #ecf0f1;
                color: #1a1a1a;
                font-size: {px(14)}px;
                font-weight: bold;
                font-family: '{self.font_family}';
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

        # Hindi button labels. "मुख्य पृष्ठ" (Home/main page), "पंचांग"
        # (matches the Panchang page's own title word), "कैलेंडर"
        # (Calendar, common transliteration) -- adjust wording here if
        # you'd prefer different phrasing.
        labels_and_actions = [
            ("मुख्य पृष्ठ", lambda: self.go_to_page(1)),
            ("पंचांग", lambda: self.go_to_page(2)),
            ("कैलेंडर", lambda: self.go_to_page(3)),
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
    init_ephemeris(ephe_path=ephe_path)

    app = QApplication(sys.argv)
    window = MainWindowHi()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
