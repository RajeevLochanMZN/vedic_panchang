"""
ui/touch_bar.py  --  three big on-screen touch buttons for the bottom of the screen (Pi 2).

    [ कैलेण्डर / घड़ी ]   [ सेटअप ]   [ बन्द करें ]
         button 1            button 2     button 3

  button 1  toggles the clock (dial) page <-> the Calendar page.  Its label always names the page
            it will go TO:  on the clock page it says "कैलेण्डर", on the Calendar page "घड़ी".
  button 2  Wi-Fi + location setup (the same as the physical button 2)
  button 3  shutdown: the first touch ARMS it (the label changes to "फिर दबाएँ" for 5 seconds),
            the second touch inside those 5 seconds shuts the Pi down cleanly.

The bar only draws and reports touches (signals button1 / button2 / button3); what each button
DOES lives in ui/main_window_hi.py, exactly as for the physical buttons.  It is a normal widget:
inside the rotated view (ui/rotated_host.py) Qt turns every touch back into these coordinates.

Switched on per device (default OFF, so Pi 1 is not affected):
    ~/.config/vedicghadi/touch_buttons.txt      on | off        (bash tools/set_display.sh touch-buttons on)
    or the environment variable VEDICGHADI_TOUCH_BUTTONS=1      (quick test)
"""
import time

from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import QWidget

from info_panels import C_PANEL_BG, C_PANEL_EDGE, C_VALUE, fit_font, draw_line, LINE_H

BAR_HEIGHT = 76                  # px of the page; the buttons are 60 px tall inside it
BUTTON_H = 60
TOP_GAP = 6
SIDE = 6
GAP = 6
LABEL_PX = 20

C_NORMAL = C_PANEL_BG                 # exactly like the other cards (dark maroon, see-through)
C_PRESSED = QColor(240, 179, 35, 235)
C_ARMED = QColor(150, 30, 20, 240)


class TouchButton(QWidget):
    pressed_signal = pyqtSignal()

    def __init__(self, font_family, parent=None):
        super().__init__(parent)
        self.font_family = font_family
        self.label = ""
        self.armed = False
        self._down = False
        self._last = 0.0
        self.setAttribute(Qt.WA_AcceptTouchEvents, False)

    def set_label(self, text, armed=False):
        if (text, armed) != (self.label, self.armed):
            self.label, self.armed = text, armed
            self.update()

    def mousePressEvent(self, event):
        now = time.monotonic()
        if now - self._last < 0.35:                  # ignore a double report of one touch
            return
        self._last = now
        self._down = True
        self.update()
        self.pressed_signal.emit()

    def mouseReleaseEvent(self, event):
        self._down = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        fill = C_PRESSED if self._down else (C_ARMED if self.armed else C_NORMAL)
        p.setBrush(fill)
        p.setPen(QPen(C_PANEL_EDGE, max(1.5, h * 0.035)))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), h * 0.22, h * 0.22)
        f = QFont(self.font_family)
        f.setBold(True)
        f.setPixelSize(LABEL_PX)
        f = fit_font(f, self.label, w * 0.88)
        colour = QColor("#2a0d05") if self._down else C_VALUE
        top = (h - LINE_H * f.pixelSize()) / 2.0
        draw_line(p, f, colour, 0, w, top, self.label)       # font-independent line height
        p.end()


class TouchBar(QWidget):
    button1 = pyqtSignal()
    button2 = pyqtSignal()
    button3 = pyqtSignal()

    LABEL_CALENDAR = "कैलेण्डर"      # shown on the clock page: touch it to go to the Calendar
    LABEL_CLOCK = "घड़ी"              # shown on the Calendar page: touch it to go back
    LABEL_SETUP = "सेटअप"
    LABEL_SHUTDOWN = "बन्द करें"
    LABEL_ARMED = "फिर दबाएँ"

    def __init__(self, font_family="Noto Sans Devanagari", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)    # no background of its own: the page shows through
        self.setFixedHeight(BAR_HEIGHT)
        self.b1 = TouchButton(font_family, self)
        self.b2 = TouchButton(font_family, self)
        self.b3 = TouchButton(font_family, self)
        self.b1.pressed_signal.connect(self.button1)
        self.b2.pressed_signal.connect(self.button2)
        self.b3.pressed_signal.connect(self.button3)
        self.b1.set_label(self.LABEL_CALENDAR)
        self.b2.set_label(self.LABEL_SETUP)
        self.b3.set_label(self.LABEL_SHUTDOWN)

    def set_page(self, index):
        """0 = clock page, anything else = Calendar (or another page)."""
        self.b1.set_label(self.LABEL_CALENDAR if index == 0 else self.LABEL_CLOCK)

    def set_armed(self, armed):
        self.b3.set_label(self.LABEL_ARMED if armed else self.LABEL_SHUTDOWN, armed)

    def resizeEvent(self, event):
        w, h = self.width(), self.height()
        bw = (w - 2 * SIDE - 2 * GAP) / 3.0
        bh = min(BUTTON_H, h - TOP_GAP)
        for i, b in enumerate((self.b1, self.b2, self.b3)):
            b.setGeometry(int(round(SIDE + i * (bw + GAP))), TOP_GAP, int(round(bw)), int(bh))
        super().resizeEvent(event)
