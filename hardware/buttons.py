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

DESIGN: this module does NOT hardcode navigation logic itself -- it
takes four callback functions (one per button) and wires GPIO events
to them. This keeps it decoupled from main_window.py's internals
(so it doesn't need to know the exact method names used there) and
means these buttons genuinely act as a SECOND INPUT PATH to the
exact same navigation the on-screen QPushButtons already trigger,
not a separate/parallel implementation of page-switching.

Button 4 (Wi-Fi Setup) is wired up the same way as the other three,
but its actual callback is still a placeholder below -- the real
Wi-Fi hotspot + custom setup-page feature hasn't been built yet
(separate, larger piece of work). Swap in the real function once
that exists.
"""

from gpiozero import Button

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


class ButtonController:
    """
    Wires the 4 physical buttons to the given callback functions.
    Construct ONE instance of this (e.g. in main_window.py's
    __init__) and keep a reference to it for the lifetime of the
    app -- if the instance is garbage-collected, gpiozero stops
    listening for button presses.

    Usage (from main_window.py, once wired up there):
        from hardware.buttons import ButtonController
        self.button_controller = ButtonController(
            home_callback=self.show_home_page,
            panchang_callback=self.show_panchang_page,
            calendar_callback=self.show_calendar_page,
            wifi_setup_callback=self.enter_wifi_setup_mode,
        )
    (Exact method names above are illustrative -- use whatever
    main_window.py's real navigation methods are actually called.)
    """

    def __init__(self, home_callback, panchang_callback, calendar_callback, wifi_setup_callback):
        self.home_button = Button(PIN_HOME, bounce_time=BOUNCE_TIME)
        self.panchang_button = Button(PIN_PANCHANG, bounce_time=BOUNCE_TIME)
        self.calendar_button = Button(PIN_CALENDAR, bounce_time=BOUNCE_TIME)
        self.wifi_setup_button = Button(PIN_WIFI_SETUP, bounce_time=BOUNCE_TIME)

        self.home_button.when_pressed = home_callback
        self.panchang_button.when_pressed = panchang_callback
        self.calendar_button.when_pressed = calendar_callback
        self.wifi_setup_button.when_pressed = wifi_setup_callback


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
# =============================================================================

if __name__ == "__main__":
    from signal import pause

    controller = ButtonController(
        home_callback=lambda: print("Button 1 (Home) pressed"),
        panchang_callback=lambda: print("Button 2 (Panchang) pressed"),
        calendar_callback=lambda: print("Button 3 (Calendar) pressed"),
        wifi_setup_callback=_placeholder_wifi_setup,
    )

    print("Press each button... Ctrl+C to stop")
    pause()
