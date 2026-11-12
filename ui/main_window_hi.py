"""
ui/main_window_hi.py

BUTTONS (default scheme "three"; settings.yaml button_scheme: three | four, see __init__):
  button 1 = toggle Home <-> Calendar   button 2 = Setup   button 3 = Shutdown (press twice within 5 s)
  Calendar returns to Home after idle_return_seconds.  Older "four" scheme described below:

PAGES AND BUTTONS (scheme "four"):
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
import time

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QLayout, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, QSize, QObject, QEvent

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
from page_vedic_dial_portrait_hi import PageVedicDialPortraitHi
from page_calendar_hi import PageCalendarHi
from page_calendar_portrait_hi import PageCalendarPortraitHi
from touch_bar import TouchBar, BAR_HEIGHT
from popup_card import PopupCard, C_RED
import wifi_setup as wifi_setup_module
from touch_raw import connect_touch
from rotated_host import RotatedHost, logical_size
from scaling import px
from translations_hi import get_devanagari_font_family


def app_rotation():
    """How much the PROGRAM turns its own picture: 0, 90, 180 or 270.
    Used when the desktop's own rotation (wlr-randr) stretches the picture (Pi 2).
    First valid answer wins:  environment variable VEDICGHADI_APP_ROTATION, then the file
    ~/.config/vedicghadi/app_rotation.txt  (normal | 90 | 180 | 270; per device, outside git).
    Set it with:  bash tools/set_display.sh app-rotate 90      (then sudo reboot)"""
    def norm(value):
        v = str(value or "").strip().lower()
        return {"90": 90, "180": 180, "270": 270, "0": 0, "normal": 0}.get(v)
    v = norm(os.environ.get("VEDICGHADI_APP_ROTATION"))
    if v is not None:
        return v
    path = os.path.join(os.path.expanduser("~"), ".config", "vedicghadi", "app_rotation.txt")
    try:
        with open(path, encoding="utf-8") as f:
            v = norm(f.readline())
    except OSError:
        v = None
    return v or 0


def pixel_aspect():
    """How much WIDER than tall one pixel of this panel is (1.0 = square pixels).
    Many cheap 7-inch 800 x 480 panels are about 1.076: without the correction a round dial
    comes out an oval.  First valid answer wins:  environment variable VEDICGHADI_PIXEL_ASPECT,
    then the file ~/.config/vedicghadi/pixel_aspect.txt (per device, outside git).
    Set it with:  bash tools/set_display.sh pixel-aspect 1.076      (only used with app_rotation)"""
    def norm(value):
        try:
            v = float(str(value or "").strip())
        except ValueError:
            return None
        return v if 0.8 <= v <= 1.3 else None
    v = norm(os.environ.get("VEDICGHADI_PIXEL_ASPECT"))
    if v is not None:
        return v
    path = os.path.join(os.path.expanduser("~"), ".config", "vedicghadi", "pixel_aspect.txt")
    try:
        with open(path, encoding="utf-8") as f:
            v = norm(f.readline())
    except OSError:
        v = None
    return v or 1.0


def touch_buttons_mode():
    """"off" (default, Pi 1), "on" (the buttons react to ordinary mouse / touch clicks) or "raw"
    (also read the Pi 2's USB touch chip directly, see ui/touch_raw.py).
    First valid answer wins:  environment variable VEDICGHADI_TOUCH_BUTTONS, then the file
    ~/.config/vedicghadi/touch_buttons.txt  (off | on | raw; per device, outside git).
    Set it with:  bash tools/set_display.sh touch-buttons raw"""
    def norm(value):
        v = str(value or "").strip().lower()
        if v in ("1", "on", "yes", "true"):
            return "on"
        if v in ("0", "off", "no", "false"):
            return "off"
        if v == "raw":
            return "raw"
        return None
    v = norm(os.environ.get("VEDICGHADI_TOUCH_BUTTONS"))
    if v is not None:
        return v
    path = os.path.join(os.path.expanduser("~"), ".config", "vedicghadi", "touch_buttons.txt")
    try:
        with open(path, encoding="utf-8") as f:
            v = norm(f.readline())
    except OSError:
        v = None
    return v or "off"


def touch_buttons_enabled():
    return touch_buttons_mode() != "off"


def choose_layout(screen_size):
    """Which dial page to build: ("portrait" | "landscape", where the choice came from).
    First one that gives a valid answer wins:
      1. environment variable  VEDICGHADI_LAYOUT=portrait|landscape   (testing)
      2. ~/.config/vedicghadi/screen_layout.txt   one word on the first line;
         per device, outside git (same place as display_mode.txt)  <- use this on Pi 2
      3. settings.yaml   screen_layout: auto | portrait | landscape
      4. automatic: a screen taller than wide gets portrait, anything else landscape
    "auto", an empty file or a missing key all mean: go on to the next one."""
    def norm(value, source):
        v = str(value or "").strip().lower()
        if v in ("portrait", "landscape"):
            return v
        if v and v != "auto":
            print("[display] ignoring screen_layout %r from %s "
                  "(use portrait, landscape or auto)" % (v, source), flush=True)
        return ""

    v = norm(os.environ.get("VEDICGHADI_LAYOUT"), "VEDICGHADI_LAYOUT")
    if v:
        return v, "environment variable VEDICGHADI_LAYOUT"
    path = os.path.join(os.path.expanduser("~"), ".config", "vedicghadi", "screen_layout.txt")
    try:
        with open(path, encoding="utf-8") as f:
            v = norm(f.readline(), path)
    except OSError:
        v = ""
    if v:
        return v, path
    try:
        v = norm(load_settings().get("screen_layout"), "settings.yaml")
    except Exception:
        v = ""
    if v:
        return v, "settings.yaml screen_layout"
    return ("portrait" if screen_size.height() > screen_size.width() else "landscape",
            "automatic (screen shape)")


class OverlayPlacer(QObject):
    """Keeps the touch buttons at the BOTTOM edge of the content and the pop-up centred above them.
    They are drawn OVER the pages (not in the layout), so the page background continues behind the
    buttons and they look like the other cards."""
    def __init__(self, central, bar, popup):
        super().__init__(central)
        self.c, self.bar, self.popup = central, bar, popup
        central.installEventFilter(self)
        self.place()

    def eventFilter(self, obj, ev):
        if obj is self.c and ev.type() == QEvent.Resize:
            self.place()
        return False

    def place(self):
        w, h = self.c.width(), self.c.height()
        if self.bar is not None:
            self.bar.setGeometry(0, h - self.bar.height(), w, self.bar.height())
            self.bar.raise_()
        self.popup.reposition()


class MainWindowHi(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("पंचांग क्लॉक")

        self.font_family = get_devanagari_font_family()

        phys_size = QApplication.instance().primaryScreen().availableGeometry().size()
        self.resize(phys_size.width(), phys_size.height())
        # the program may turn its own picture (app_rotation); the pages are then laid out at the
        # LOGICAL size, e.g. 480 x 800 on an 800 x 480 panel turned by 90
        self.app_rot = app_rotation()
        self.pix_aspect = pixel_aspect() if self.app_rot else 1.0
        lw, lh = logical_size(phys_size.width(), phys_size.height(), self.app_rot, self.pix_aspect)
        screen_size = QSize(lw, lh)

        self.stacked_widget = QStackedWidget()

        # button 1: Home (the dial page): PORTRAIT or LANDSCAPE page, see choose_layout()
        layout, why = choose_layout(screen_size)
        portrait = (layout == "portrait")
        print("[display] screen %d x %d%s -> %s dial page  (decided by: %s)" % (
            screen_size.width(), screen_size.height(),
            (" (program turns the picture by %d, panel is %d x %d, pixel aspect %.3f)" % (
                self.app_rot, phys_size.width(), phys_size.height(), self.pix_aspect))
            if self.app_rot else "",
            layout.upper(), why), flush=True)
        if portrait:
            self.page1 = PageVedicDialPortraitHi()
        else:
            self.page1 = PageVedicDialHi()
        # button 2: Calendar - the portrait layout (7 narrow columns) on a portrait screen
        self.page2 = PageCalendarPortraitHi() if portrait else PageCalendarHi()

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
        # THREE ON-SCREEN TOUCH BUTTONS (ui/touch_bar.py), only where switched on for this device.
        # They do exactly what the physical buttons do: 1 = clock <-> Calendar (the Calendar
        # returns to the clock after idle_return_seconds), 2 = Wi-Fi/location setup,
        # 3 = shutdown (touch twice within 5 s).  Every touch restarts the idle countdown.
        self.touch_bar = None
        if touch_buttons_enabled():
            self.touch_bar = TouchBar(self.font_family, central)     # drawn over the page, see OverlayPlacer
            self.touch_bar.button1.connect(self.toggle_page)
            self.touch_bar.button2.connect(self.setup_button_pressed)
            self.touch_bar.button3.connect(self.shutdown_button_pressed)
            for sig in (self.touch_bar.button1, self.touch_bar.button2, self.touch_bar.button3):
                sig.connect(self._restart_idle)
            # "raw": the desktop sees no touch from this panel's chip, so read the chip ourselves and
            # turn its touches into clicks on the screen point (ui/touch_raw.py)
            self.raw_touch = None
            if touch_buttons_mode() == "raw":
                self.raw_touch = connect_touch(phys_size.width(), phys_size.height())
        # the dial page has its own banner, so the plain banner row is hidden there
        self.stacked_widget.currentChanged.connect(self._on_page_changed)
        central.setLayout(main_layout)
        self._content = central
        # pop-up card (setup instructions, shutdown question) + placement of bar and pop-up
        self.popup = PopupCard(self.font_family, central)
        self.popup.reserve_bottom = BAR_HEIGHT if self.touch_bar is not None else 0
        self._placer = OverlayPlacer(central, self.touch_bar, self.popup)
        if hasattr(self.page2, "reserve_bottom"):          # keep the bottom strip of the Calendar free
            self.page2.reserve_bottom = BAR_HEIGHT if self.touch_bar is not None else 0
            self.page2.relayout()
        self._setup_state = "idle"                    # idle | countdown | running
        self._setup_left = 0
        self._setup_timer = QTimer(self)
        self._setup_timer.timeout.connect(self._setup_tick)
        self._shutdown_deadline = 0.0
        self._shutdown_tick_timer = QTimer(self)
        self._shutdown_tick_timer.timeout.connect(self._shutdown_tick)
        if self.app_rot:
            # inside the rotating view the content must take EXACTLY the logical size,
            # whatever the minimum size of its pages is
            main_layout.setSizeConstraint(QLayout.SetNoConstraint)
            central.setMinimumSize(0, 0)
            # a page with a large minimum size (the Calendar: 7 columns) would make the content
            # wider than the screen and push the dial page off-centre, so the pages' own size
            # wishes are ignored here: the content is always exactly the logical screen size
            for w in (self.stacked_widget, self.page1, self.page2):
                w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
            self.setCentralWidget(RotatedHost(central, phys_size.width(), phys_size.height(),
                                              self.app_rot, self.pix_aspect))
        else:
            self.setCentralWidget(central)
        QTimer.singleShot(2500, self._print_geometry)      # one line for diagnosing a wrong picture

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
        # BUTTON SCHEME -- settings.yaml  button_scheme:
        #   "three" (DEFAULT, both Pis): button 1 toggles Home <-> Calendar, button 2 = Setup,
        #           button 3 = Shutdown (press twice within 5 s).  Button 4 is not used.
        #   "four"  (the old scheme, only if ever wanted again): button 1 Home, button 2 Calendar,
        #           button 3 Setup, button 4 unused; shutdown = hold buttons 2 + 3 for 3 s.
        # The signal names come from hardware/buttons.py and still follow the OLD wiring names:
        #   home_pressed (GPIO17, button 1)   panchang_pressed (GPIO27, button 2)
        #   calendar_pressed (GPIO22, button 3)   wifi_setup_pressed (GPIO23, button 4)
        self.button_scheme = str(load_settings().get("button_scheme", "three")).strip().lower()
        if self.button_scheme == "three":
            self.button_controller.home_pressed.connect(self.toggle_page)
            self.button_controller.panchang_pressed.connect(self.setup_button_pressed)
            self.button_controller.calendar_pressed.connect(self.shutdown_button_pressed)
        else:
            self.button_controller.home_pressed.connect(lambda: self.go_to_page(1))
            self.button_controller.panchang_pressed.connect(lambda: self.go_to_page(2))
            self.button_controller.calendar_pressed.connect(self.setup_button_pressed)
        self.button_controller.shutdown_requested.connect(self.safe_shutdown)
        self._shutting_down = False
        # "three" scheme: the first press of the shutdown button only ARMS it for 5 seconds
        self._shutdown_armed = False
        self._disarm_timer = QTimer(self)
        self._disarm_timer.setSingleShot(True)
        self._disarm_timer.timeout.connect(self._disarm_shutdown)

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
        # (with the touch buttons the pop-up cards replace the banner, so the Calendar gets the room)
        self.banner_row.setVisible(index != 0 and self.touch_bar is None)
        if self.touch_bar is not None:
            self.touch_bar.set_page(index)
        self._restart_idle()

    def _restart_idle(self):
        if self.stacked_widget.currentIndex() != 0 and self.idle_seconds > 0:
            self.idle_timer.start(self.idle_seconds * 1000)
        else:
            self.idle_timer.stop()

    # ------------------------------------------------------------------
    # THREE-BUTTON SCHEME (settings.yaml: button_scheme: three)
    # ------------------------------------------------------------------
    def toggle_page(self):
        """Button 1: Home <-> Calendar.  The Calendar page returns to Home by itself
        after idle_return_seconds with no button press."""
        self.go_to_page(2 if self.stacked_widget.currentIndex() == 0 else 1)

    def shutdown_button_pressed(self):
        """Button 3: press once -> a pop-up card asks to press again; press again within
        5 seconds -> clean shutdown.  One accidental press does nothing (the card goes away)."""
        if self._shutdown_armed:
            self._disarm_shutdown()
            self.safe_shutdown()
            return
        if self._setup_state == "countdown":          # a pending setup start is cancelled first
            self._cancel_setup()
        self._shutdown_armed = True
        self._disarm_timer.start(5000)
        self._shutdown_deadline = time.monotonic() + 5.0
        self._shutdown_tick_timer.start(100)
        if self.touch_bar is not None:
            self.touch_bar.set_armed(True)
        self.popup.show_card(
            "shutdown", "बंद करें?",
            [("", "बंद करने के लिए", ""), ("", "", "बन्द करें"), ("", "बटन फिर से दबाएँ", "")],
            footer="5 सेकंड में अपने आप रद्द हो जाएगा", progress=1.0, accent=C_RED, center=True)

    def _shutdown_tick(self):
        left = self._shutdown_deadline - time.monotonic()
        if left > 0:
            self.popup.set_progress(left / 5.0)

    def _disarm_shutdown(self):
        self._shutdown_armed = False
        self._disarm_timer.stop()
        self._shutdown_tick_timer.stop()
        if self.touch_bar is not None:
            self.touch_bar.set_armed(False)
        if not self._shutting_down and self.popup.kind == "shutdown":
            self.popup.close_card()

    # ---- Wi-Fi / location setup: instructions card, with a few seconds to cancel a mistaken press
    SETUP_DELAY_S = 8

    def _setup_steps(self):
        ssid = getattr(wifi_setup_module, "HOTSPOT_SSID", "VedicGhadi-Setup")
        url = getattr(wifi_setup_module, "SETUP_URL", "http://10.42.0.1:5000")
        pwd = getattr(wifi_setup_module, "HOTSPOT_PASSWORD", None)
        steps = [("1", "मोबाइल में Wi-Fi खोलें और इस नेटवर्क से जुड़ें:", ssid)]
        if pwd:
            steps.append(("2", "पासवर्ड डालें:", pwd))
        steps.append((str(len(steps) + 1), "मोबाइल के ब्राउज़र में यह पता खोलें:", url))
        steps.append((str(len(steps) + 1), "Wi-Fi और स्थान भरकर सेव करें", ""))
        return steps

    def _show_setup_card(self):
        if self._setup_state == "running":
            footer = "सेटअप चालू है — ऊपर के चरण पूरे करें।  यह कार्ड छिपाने/दिखाने के लिए ‘सेटअप’ दबाएँ"
            progress = None
        else:
            footer = ("सेटअप %d सेकंड में शुरू होगा (तब घड़ी का Wi-Fi बंद होगा)।  "
                      "गलती से दबाया हो तो फिर ‘सेटअप’ दबाएँ" % self._setup_left)
            progress = self._setup_left / float(self.SETUP_DELAY_S)
        self.popup.show_card("setup", "Wi-Fi / स्थान सेटअप", self._setup_steps(), footer, progress)

    def setup_button_pressed(self):
        """Button 2 (physical or touch).
          first press   : instructions card + countdown; setup starts when it reaches 0
          second press  : while counting -> cancelled, nothing has happened
                          after the start -> hides / shows the card again (setup keeps running)"""
        if self._setup_state == "countdown":
            self._cancel_setup()
            return
        if self._setup_state == "running":
            if self.popup.isVisible() and self.popup.kind == "setup":
                self.popup.close_card()
            else:
                self._show_setup_card()
            return
        if self._shutdown_armed:
            self._disarm_shutdown()
        self._setup_state = "countdown"
        self._setup_left = self.SETUP_DELAY_S
        self._show_setup_card()
        self._setup_timer.start(1000)

    def _cancel_setup(self):
        self._setup_timer.stop()
        self._setup_state = "idle"
        if self.popup.kind == "setup":
            self.popup.close_card()

    def _setup_tick(self):
        self._setup_left -= 1
        if self._setup_left > 0:
            self._show_setup_card()
            return
        self._setup_timer.stop()
        self._setup_state = "running"
        self._show_setup_card()
        QApplication.processEvents()                  # paint the card before the Wi-Fi goes away
        enter_wifi_setup_mode()

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
        self.popup.show_card("shutdown_now", "बंद हो रहा है…",
                             [("", "कृपया प्रतीक्षा करें", "")], accent=C_RED, center=True)
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
            self.popup.close_card()
            self._shutting_down = False

    def _print_geometry(self):
        """One start-up line with the sizes really in use (to diagnose a trimmed / shifted picture)."""
        scr = QApplication.instance().primaryScreen()
        g = scr.availableGeometry()
        msg = "[display] window %d x %d | screen %d x %d (full %d x %d) | pixel ratio %.2f" % (
            self.width(), self.height(), g.width(), g.height(),
            scr.geometry().width(), scr.geometry().height(), self.devicePixelRatioF())
        c = self._content
        msg += " | content %d x %d (page 1: %d x %d, minimum %d x %d)" % (
            c.width(), c.height(), self.page1.width(), self.page1.height(),
            c.minimumSizeHint().width(), c.minimumSizeHint().height())
        print(msg, flush=True)

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

    if sys.platform.startswith("linux"):
        app.setOverrideCursor(Qt.BlankCursor)

    window = MainWindowHi()
    if os.environ.get("VEDICGHADI_WINDOWED"):
        window.show()            # development: an ordinary window you can move and close
    else:
        window.showFullScreen()  # kiosk: no title bar, covers the whole screen incl. the taskbar
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
