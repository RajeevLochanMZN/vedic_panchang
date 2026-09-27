"""
hardware/buttons.py

gpiozero bindings for the 4 physical GPIO buttons:
  Button 1 (GPIO17) -> Home page
  Button 2 (GPIO27) -> Panchang page
  Button 3 (GPIO22) -> Calendar page
  Button 4 (GPIO23) -> Wi-Fi Setup mode

(Earlier drafts of this file assumed 5 buttons and different page
names -- "Core Panchang"/"Sun & Time Divisions"/an auto-rotate
toggle -- from an earlier version of the project plan. The actual
built pages are Home/Panchang/Calendar, auto-rotation was replaced
by an idle-timeout return-to-home design instead of a button toggle,
and the freed-up 4th button became Wi-Fi Setup instead.)

WIRING (confirmed working on real hardware): each button is a plain
2-leg switch, one leg to its GPIO pin, the other leg to any GND pin
-- no external resistor needed, gpiozero enables the Pi's internal
pull-up by default. (An earlier attempt used 3-pin pull-down MODULE
breakouts instead of plain switches -- those have inverted idle/
pressed logic from what gpiozero's Button() expects by default, and
caused is_pressed to read permanently True. Plain switches with the
default pull-up wiring is what's actually wired up now.)

DEBOUNCE: confirmed via live testing that a single physical press
fires two rapid electrical transitions ("switch bounce", normal for
cheap mechanical switches) -- gpiozero's bounce_time parameter below
filters this so each physical press reliably fires its callback
exactly once.

CRITICAL DESIGN NOTE -- QT SIGNALS, NOT PLAIN CALLBACKS: an earlier
version of this file took plain Python callback functions and called
them directly from gpiozero's when_pressed. That crashed the real
app with a segfault ("QObject::setParent: Cannot set parent, new
parent is in a different thread") the moment a button press tried to
touch a Qt widget (e.g. switching pages via QStackedWidget). Root
cause: gpiozero fires when_pressed callbacks on ITS OWN internal
background thread (used for GPIO edge detection), but Qt widgets can
ONLY be safely touched from the main GUI thread -- calling GUI code
directly from a background thread is not just discouraged, Qt
actively refuses it and can crash outright rather than risk silent
corruption.

THE FIX: ButtonController is a QObject with one pyqtSignal per
button. gpiozero's when_pressed just emits the signal (thread-safe
-- emitting a signal is fine from any thread) instead of calling
navigation code directly. Whatever connects to these signals (e.g.
main_window_hi.py, via .connect()) gets its slot called through
Qt's own event queue instead -- when a signal crosses threads, Qt
automatically delivers it as a QUEUED connection, meaning the actual
slot code runs safely on the main thread's event loop, not on
gpiozero's thread. This is the standard, correct pattern for mixing
gpiozero (or any background-thread event source) with PyQt5.

Usage (from main_window_hi.py, or main_window.py):
    from hardware.buttons import ButtonController
    self.button_controller = ButtonController()  # keep as self.X, see below
    self.button_controller.home_pressed.connect(lambda: self.go_to_page(1))
    self.button_controller.panchang_pressed.connect(lambda: self.go_to_page(2))
    self.button_controller.calendar_pressed.connect(lambda: self.go_to_page(3))
    self.button_controller.wifi_setup_pressed.connect(self.enter_wifi_setup_mode)
(Last line illustrative -- connect to whatever the real Wi-Fi Setup
method ends up being called, once that feature exists; until then,
_placeholder_wifi_setup below is a reasonable stand-in.)

IMPORTANT: keep the ButtonController instance as an attribute on
something long-lived (e.g. self.button_controller on the main
window), never a local variable that goes out of scope -- both
gpiozero's Button objects AND the Qt signal connections stop working
once the ButtonController itself gets garbage-collected.
"""

from gpiozero import Button
from PyQt5.QtCore import QObject, pyqtSignal

# GPIO pin numbers (BCM numbering, matching gpiozero's convention --
# NOT the physical pin numbers on the 40-pin header). Chosen to
# avoid GPIO2/GPIO3 (reserved for the RTC's I2C bus), the UART pins,
# and the SPI pins, in case any of those are ever needed.
PIN_HOME = 17
PIN_PANCHANG = 27
PIN_CALENDAR = 22
PIN_WIFI_SETUP = 23

# How long (seconds) to ignore further electrical transitions after
# a press, to filter out switch bounce. 0.1s (100ms) is a common,
# safe default for tactile switches -- long enough to absorb bounce,
# short enough that a genuine fast double-press still registers as
# two presses if someone ever wants that.
BOUNCE_TIME = 0.1


class ButtonController(QObject):
    """
    Wires the 4 physical buttons to Qt signals (see the module
    docstring above for why signals, not plain callbacks). Construct
    ONE instance of this and keep a reference to it for the lifetime
    of the app (e.g. self.button_controller in the main window's
    __init__) -- if the instance is garbage-collected, gpiozero stops
    listening for button presses.
    """

    home_pressed = pyqtSignal()
    panchang_pressed = pyqtSignal()
    calendar_pressed = pyqtSignal()
    wifi_setup_pressed = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.home_button = Button(PIN_HOME, bounce_time=BOUNCE_TIME)
        self.panchang_button = Button(PIN_PANCHANG, bounce_time=BOUNCE_TIME)
        self.calendar_button = Button(PIN_CALENDAR, bounce_time=BOUNCE_TIME)
        self.wifi_setup_button = Button(PIN_WIFI_SETUP, bounce_time=BOUNCE_TIME)

        # .emit is thread-safe to call from gpiozero's background
        # thread -- this is the whole point of the fix (see module
        # docstring). Do NOT change these back to calling arbitrary
        # functions directly.
        self.home_button.when_pressed = self.home_pressed.emit
        self.panchang_button.when_pressed = self.panchang_pressed.emit
        self.calendar_button.when_pressed = self.calendar_pressed.emit
        self.wifi_setup_button.when_pressed = self.wifi_setup_pressed.emit


def _placeholder_wifi_setup():
    """
    Stand-in for the real Wi-Fi Setup trigger, until that feature
    (hotspot mode + custom web form) is actually built. Replace this
    with the real function once it exists.
    """
    print("[buttons] Wi-Fi Setup button pressed -- feature not built yet.")


# =============================================================================
# Standalone test -- run directly on the Pi to check all 4 buttons
# without needing the full app: `python3 hardware/buttons.py`
#
# Uses a minimal QCoreApplication (not a full QApplication -- no GUI
# needed for this test) so Qt's signal/slot event delivery actually
# runs; without SOME Qt event loop pumping, a queued cross-thread
# signal connection has nothing to deliver it and would just sit
# unprocessed forever.
# =============================================================================

if __name__ == "__main__":
    from PyQt5.QtCore import QCoreApplication

    app = QCoreApplication([])

    controller = ButtonController()
    controller.home_pressed.connect(lambda: print("Button 1 (Home) pressed"))
    controller.panchang_pressed.connect(lambda: print("Button 2 (Panchang) pressed"))
    controller.calendar_pressed.connect(lambda: print("Button 3 (Calendar) pressed"))
    controller.wifi_setup_pressed.connect(_placeholder_wifi_setup)

    print("Press each button... Ctrl+C to stop")
    app.exec_()
