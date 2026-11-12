"""
ui/touch_raw.py  --  read the Pi 2's USB touch chip (0eef:0005 "RPI_TOUCH By ZH851") DIRECTLY.

Why: the Linux kernel makes no touch device for this chip (its USB report description is only
"25 bytes of vendor data"), so the desktop never sees a touch.  The chip does send its touches, in
a small fixed format (captured on the real Pi, 25 bytes per report, read from /dev/hidrawN):

    aa 01 XX XX YY YY bb 01 ...  cc      finger DOWN   X, Y = 16-bit big-endian, in panel pixels
    aa 00 00 00 00 00 bb 00 ...          finger UP     (the "...": slots for more fingers, ignored)

X runs 0..800 (the panel's long side), Y runs 0..480: exactly the pixels of the 800x480 panel.

This module finds the chip, reads its reports and
  * emits  pressed(x, y)  moved(x, y)  released()   (raw chip coordinates),
  * turns a touch into the same mouse press / release that a finger would make, delivered to
    whatever widget is at that point of the screen (TouchInjector).  The on-screen buttons
    (ui/touch_bar.py) therefore work unchanged, also inside the rotated view (ui/rotated_host.py).

The chip file needs permission for the normal user: tools/install_touch_rule.sh installs a udev rule
(once, with sudo).  Switched on with:  bash tools/set_display.sh touch-buttons raw

Direction fix, if a touch lands mirrored: ~/.config/vedicghadi/touch_map.txt with one or more words
  flipx  flipy  swap       (bash tools/set_display.sh touch-map flipx)   or env VEDICGHADI_TOUCH_MAP
"""
import glob
import os
import sys

from PyQt5.QtCore import QObject, QPoint, QPointF, QSocketNotifier, QTimer, QEvent, Qt, pyqtSignal
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication

VENDOR_PRODUCT = "0003:00000EEF:00000005"      # HID_ID of the chip
RAW_W, RAW_H = 800, 480                         # the chip reports in these pixels
REPORT_LEN = 25


def find_device():
    """'/dev/hidrawN' of the touch chip, or None."""
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        try:
            with open(uevent, encoding="utf-8") as f:
                if "HID_ID=" + VENDOR_PRODUCT in f.read().upper():
                    return "/dev/" + uevent.split("/")[4]
        except OSError:
            continue
    return None


def parse_report(data):
    """(touching, x, y) from one 25-byte report, or None if it is not a touch report."""
    if len(data) < 7 or data[0] != 0xAA or data[6] != 0xBB:
        return None
    return data[1] != 0, (data[2] << 8) | data[3], (data[4] << 8) | data[5]


class TouchMap:
    """Raw chip coordinates -> pixel of the (unrotated) screen.  Default: straight through."""
    def __init__(self, words=None):
        if words is None:
            words = os.environ.get("VEDICGHADI_TOUCH_MAP")
            if words is None:
                try:
                    with open(os.path.join(os.path.expanduser("~"), ".config", "vedicghadi",
                                           "touch_map.txt"), encoding="utf-8") as f:
                        words = f.readline()
                except OSError:
                    words = ""
        w = set(str(words).replace(",", " ").lower().split())
        self.swap, self.flipx, self.flipy = "swap" in w, "flipx" in w, "flipy" in w

    def map(self, x, y, screen_w, screen_h):
        x = min(max(x, 0), RAW_W - 1)
        y = min(max(y, 0), RAW_H - 1)
        if self.swap:
            x, y = y * RAW_W / float(RAW_H), x * RAW_H / float(RAW_W)
        if self.flipx:
            x = RAW_W - 1 - x
        if self.flipy:
            y = RAW_H - 1 - y
        return int(x * screen_w / float(RAW_W)), int(y * screen_h / float(RAW_H))


class RawTouchReader(QObject):
    pressed = pyqtSignal(int, int)
    moved = pyqtSignal(int, int)
    released = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fd = None
        self._notifier = None
        self._down = False
        self.error = ""
        self.path = None

    def start(self):
        """True when the chip is open and being read."""
        self.path = find_device()
        if not self.path:
            self.error = "touch chip 0eef:0005 not found (no matching /dev/hidraw)"
            return False
        try:
            self._fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            self.error = ("no permission for %s -- run once:  bash tools/install_touch_rule.sh" % self.path)
            return False
        except OSError as e:
            self.error = "cannot open %s: %s" % (self.path, e)
            return False
        self._notifier = QSocketNotifier(self._fd, QSocketNotifier.Read, self)
        self._notifier.activated.connect(self._readable)
        return True

    def stop(self):
        if self._notifier is not None:
            self._notifier.setEnabled(False)
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def _readable(self, _fd=None):
        while True:
            try:
                data = os.read(self._fd, REPORT_LEN)
            except BlockingIOError:
                return
            except OSError:
                return
            if not data:
                return
            self.feed(data)

    def feed(self, data):
        """One report (also used by the tests)."""
        r = parse_report(data)
        if r is None:
            return
        touching, x, y = r
        if touching and not self._down:
            self._down = True
            self.pressed.emit(x, y)
        elif touching:
            self.moved.emit(x, y)
        elif self._down:
            self._down = False
            self.released.emit()


class TouchInjector(QObject):
    """Makes a mouse press / release at a SCREEN pixel, sent to the widget found there."""
    def __init__(self, screen_w, screen_h, touch_map=None, parent=None):
        super().__init__(parent)
        self.w, self.h = screen_w, screen_h
        self.map = touch_map or TouchMap()
        self._target = None
        self._last = QPoint(0, 0)

    def _send(self, kind, gp, w, buttons):
        lp = w.mapFromGlobal(gp)
        ev = QMouseEvent(kind, QPointF(lp), QPointF(gp), Qt.LeftButton, buttons, Qt.NoModifier)
        QApplication.sendEvent(w, ev)

    def press(self, rx, ry):
        x, y = self.map.map(rx, ry, self.w, self.h)
        gp = QPoint(x, y)
        self._last = gp
        w = QApplication.widgetAt(gp)
        self._target = w
        if w is not None:
            self._send(QEvent.MouseButtonPress, gp, w, Qt.LeftButton)

    def release(self):
        w = self._target
        self._target = None
        if w is not None:
            self._send(QEvent.MouseButtonRelease, self._last, w, Qt.NoButton)


def connect_touch(window_screen_w, window_screen_h):
    """Start reading the chip and inject its touches.  Returns (reader, injector) or (None, None)."""
    reader = RawTouchReader()
    if not reader.start():
        print("[touch] raw touch not started: %s" % reader.error, flush=True)
        return None, None
    inj = TouchInjector(window_screen_w, window_screen_h)
    reader.pressed.connect(inj.press)
    reader.released.connect(inj.release)
    print("[touch] reading the touch chip from %s  (map: swap=%s flipx=%s flipy=%s)" % (
        reader.path, inj.map.swap, inj.map.flipx, inj.map.flipy), flush=True)
    return reader, inj
