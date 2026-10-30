"""
ui/main_window_hi.py

PAGES AND BUTTONS (current):
  button 1  Home      = the dial page (ui/page_vedic_dial_hi.py)
  button 2  Calendar  = ui/page_calendar_hi.py
  button 3  Setup     = Wi-Fi + location setup (hardware/wifi_setup.py)
  The Panchang page and the old Home page are no longer used (their files stay in the
  project, just not imported).  Physical wiring is UNCHANGED: buttons 1-4 are still
  GPIO17 / 27 / 22 / 23, and the shutdown combo (hold the 2nd and 3rd button for 3 s,
  i.e. Calendar + Setup) works exactly as before.  The 4th button now does nothing.
  After idle_return_seconds (settings.yaml, default 300) on the Calendar page with no
  button press, the clock goes back to the dial page.

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

KIOSK BEHAVIOUR (added together with setup.sh / launch.sh):
  - Starts in real FULLSCREEN (no title bar, covers the desktop taskbar).
    For development set VEDICGHADI_WINDOWED=1 to get a normal window
    instead, e.g.:  VEDICGHADI_WINDOWED=1 ./launch.sh
  - Holding Panchang + Calendar together for 3 s shuts the Pi down
    cleanly (hardware/buttons.py emits shutdown_requested; see
    safe_shutdown() below). Wait for the screen to go blank AND the
    green activity LED to stop flickering before removing power.
  - At startup the system clock is set from the DS3231 RTC (unless NTP
    has already corrected it), and once an hour maybe_sync_rtc_from_system()
    checks whether the monthly RTC re-sync is due -- see hardware/rtc.py.
"""

import os
import subprocess
import sys

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel,
)
from PyQt5.QtCore import Qt, QTimer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
from ephemeris import init_ephemeris
from config_loader import load_settings

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hardware"))
from buttons import ButtonController
from rtc import (
    is_system_clock_ntp_synced, sync_system_clock_from_rtc, maybe_sync_rtc_from_system,
)
from wifi_setup import enter_wifi_setup_mode

from page_vedic_dial_hi import PageVedicDialHi
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

        self.page1 = PageVedicDialHi()    # button 1: Home (the dial page)
        self.page2 = PageCalendarHi()     # button 2: Calendar

        for page in (self.page1, self.page2):
            self.stacked_widget.addWidget(page)
        # Opens on Page 1 (Home), same as main_window.py.

        central = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.stacked_widget)
        self.banner_row = self._build_banner_row()
        main_layout.addWidget(self.banner_row)
        # the dial page has its own banner, so the plain banner row is hidden there
        self.stacked_widget.currentChanged.connect(self._on_page_changed)
        central.setLayout(main_layout)
        self.setCentralWidget(central)

        # Wires the 4 physical hardware buttons to this window's own
        # go_to_page() -- the SAME method the old on-screen buttons
        # used to call, now the only way pages are switched since the
        # banner replaced them. self.button_controller MUST be kept
        # as an instance attribute (not a local variable) -- gpiozero
        # stops listening for button presses if this object gets
        # garbage-collected. Button 4 runs the real Wi-Fi Setup
        # feature (hardware/wifi_setup.py).
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
        # Signal names come from hardware/buttons.py and still follow the OLD wiring
        # names; what each physical button does now:
        #   home_pressed      (GPIO17, button 1) -> Home (dial page)
        #   panchang_pressed  (GPIO27, button 2) -> Calendar page
        #   calendar_pressed  (GPIO22, button 3) -> Wi-Fi / location Setup
        #   wifi_setup_pressed(GPIO23, button 4) -> unused
        self.button_controller.home_pressed.connect(lambda: self.go_to_page(1))
        self.button_controller.panchang_pressed.connect(lambda: self.go_to_page(2))
        self.button_controller.calendar_pressed.connect(enter_wifi_setup_mode)
        self.button_controller.shutdown_requested.connect(self.safe_shutdown)
        self._shutting_down = False

        # IDLE RETURN: on any page except Home, no button press for idle_return_seconds
        # -> back to Home.  Every button press restarts the countdown.
        self.idle_seconds = int(load_settings().get("idle_return_seconds", 300))
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(lambda: self.go_to_page(1))
        for signal in (self.button_controller.home_pressed,
                       self.button_controller.panchang_pressed,
                       self.button_controller.calendar_pressed,
                       self.button_controller.wifi_setup_pressed):
            signal.connect(self._restart_idle)
        self._on_page_changed(self.stacked_widget.currentIndex())

        # RTC upkeep (hardware/rtc.py). maybe_sync_rtc_from_system() is
        # cheap and does nothing unless BOTH the system clock is
        # NTP-synced AND ~30 days have passed since the last RTC
        # write, so checking hourly is plenty. The first check waits a
        # couple of minutes after startup so NTP has had time to
        # finish -- before that it would just (correctly) do nothing.
        self.rtc_timer = QTimer(self)
        self.rtc_timer.timeout.connect(maybe_sync_rtc_from_system)
        self.rtc_timer.start(60 * 60 * 1000)
        QTimer.singleShot(2 * 60 * 1000, maybe_sync_rtc_from_system)

    def _on_page_changed(self, index):
        """Banner row on every page except the dial page (index 0); the idle countdown
        runs only away from Home."""
        self.banner_row.setVisible(index != 0)
        self._restart_idle()

    def _restart_idle(self):
        if self.stacked_widget.currentIndex() != 0 and self.idle_seconds > 0:
            self.idle_timer.start(self.idle_seconds * 1000)
        else:
            self.idle_timer.stop()

    def safe_shutdown(self):
        """
        Triggered by holding Panchang + Calendar together for 3 s
        (hardware/buttons.py). Shows a message on the banner so you can
        see it registered, then runs a CLEAN shutdown -- yanking power
        instead risks SD-card corruption. `sudo -n` means "never ask for
        a password": it fails immediately if the passwordless-sudo rule
        (written by setup.sh) is missing, rather than hanging forever.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        print("[main_window] Shutdown combo held -- shutting the Pi down cleanly.")
        self.banner_label.setText("बंद हो रहा है… कृपया प्रतीक्षा करें")
        self.page1.show_message("बंद हो रहा है… कृपया प्रतीक्षा करें")   # dial page banner
        QApplication.processEvents()  # paint the message before the system starts closing things down
        try:
            result = subprocess.run(
                ["sudo", "-n", "shutdown", "-h", "now"],
                capture_output=True, text=True, timeout=15,
            )
            failed = result.returncode != 0
            detail = result.stderr.strip()
        except Exception as e:
            failed, detail = True, str(e)
        if failed:
            # Don't leave a false "shutting down" message on screen.
            print(f"[main_window] Shutdown command failed: {detail}")
            self.banner_label.setText("वैदिक घड़ी")
            self.page1.show_message(None)
            self._shutting_down = False

    def go_to_page(self, page_number: int):
        """page_number is 1-2: 1 = Home (dial page), 2 = Calendar.  Called by the
        button signals above."""
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
        self.banner_label = banner_label  # kept so safe_shutdown() can show a message here
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
    # Give the Pi a correct clock BEFORE anything reads the time: set
    # the system clock from the RTC -- but only if NTP hasn't already
    # corrected it (a fresh network time beats the RTC's). Never
    # raises; if it can't, the clock simply stays as it was.
    if not is_system_clock_ntp_synced():
        sync_system_clock_from_rtc()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    ephe_path = os.path.join(script_dir, "..", "data", "ephe")
    init_ephemeris(ephe_path=ephe_path)

    app = QApplication(sys.argv)
    window = MainWindowHi()
    if os.environ.get("VEDICGHADI_WINDOWED"):
        window.show()            # development: an ordinary window you can move and close
    else:
        window.showFullScreen()  # kiosk: no title bar, covers the whole screen incl. the taskbar
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
