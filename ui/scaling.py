"""
ui/scaling.py

Shared scaling helper so the UI adapts to different screen
resolutions while keeping the same 16:9 design proportions.

DESIGN BASELINE: 768 (height). Every pixel value in this UI (fonts,
widths, spacing) was tuned by eye inside a fixed 1024x768 TEST
WINDOW -- not a fullscreen window -- even though the monitor itself
is natively 1920x1080. So 768 is the true baseline to scale FROM,
not the monitor's native 1080; using 1080 as the baseline was an
earlier mistake that made the scale factor come out as 1.0 (no
change) while the test window still grew to fill the whole screen,
leaving all the tuned content stranded at its old, smaller size
inside a much bigger window.

SCALE FACTOR: computed once at startup as
    actual_screen_height / 768
and applied to every pixel constant via px(). All target displays
(32in / 50in / 100in panels, the VGA test monitor) are confirmed
16:9 -- just different pixel densities, not different aspect
ratios -- so a single height-based scale factor keeps every
proportion correct across all of them without any layout redesign.

On a genuine 1024x768 window, SCALE == 1.0 exactly. On the actual
1920x1080 monitor running fullscreen, SCALE ~= 1.41, so fonts,
spacing, and widths all grow together to fill the real screen
instead of sitting small inside it.
"""

from PyQt5.QtWidgets import QApplication

DESIGN_HEIGHT = 768

_scale_cache = None


def get_scale() -> float:
    """
    Compute (once, then cache) the scale factor for the actual
    screen this app is running on. Requires a QApplication to
    already exist (call this after QApplication(sys.argv), not
    before).
    """
    global _scale_cache
    if _scale_cache is not None:
        return _scale_cache

    app = QApplication.instance()
    if app is None:
        # No QApplication yet (e.g. called too early) -- fall back
        # to no scaling rather than crashing.
        return 1.0

    screen = app.primaryScreen()
    actual_height = screen.size().height()
    _scale_cache = actual_height / DESIGN_HEIGHT
    return _scale_cache


def px(n: int) -> int:
    """
    Scale a design-baseline pixel value (chosen inside a 1024x768
    test window) to the actual screen's resolution. Always returns
    an int, since Qt stylesheets and setFixedSize/setFixedWidth etc.
    need integers.
    """
    return round(n * get_scale())


def reset_scale_cache_for_testing():
    """Only for standalone test scripts that create multiple
    QApplications in one process -- normal app code never needs this."""
    global _scale_cache
    _scale_cache = None
