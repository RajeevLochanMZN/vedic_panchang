"""
tools/touch_test.py -- do touches reach the clock program, and where do they land?

    source venv/bin/activate
    export DISPLAY=:0 QT_QPA_PLATFORM=xcb
    python3 tools/touch_test.py --rotate 270 --aspect 1.067        (same two numbers as the clock uses)
    python3 tools/touch_test.py                                     (plain screen, no rotation)

Touch the screen: a ring appears exactly where Qt thinks you touched, the counters at the bottom
count what arrived (mouse = touch turned into a mouse click, touch = a real touch event), and the
terminal prints every event.  Ctrl+C in the terminal quits.
  * nothing appears, counters stay 0     -> the touches never reach the program (driver / USB / desktop)
  * ring appears at the finger           -> touch works; the clock buttons will work too
  * ring appears somewhere else          -> the touch is not mapped to the rotated picture: tell me
                                             where you touched and where the ring came (e.g. mirrored)
"""
import os
import signal
import sys

from PyQt5.QtCore import Qt, QEvent, QPointF, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont
from PyQt5.QtWidgets import QApplication, QWidget


class T(QWidget):
    def __init__(self):
        super().__init__()
        self.dots = []                     # (x, y, kind) in this widget's own coordinates
        self.n_mouse = 0
        self.n_touch = 0
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)

    def _add(self, x, y, kind):
        self.dots.append((x, y, kind))
        self.dots = self.dots[-6:]
        print("%-6s at (%4d, %4d) of a %d x %d picture" % (kind, x, y, self.width(), self.height()), flush=True)
        self.update()

    def mousePressEvent(self, e):
        self.n_mouse += 1
        self._add(e.pos().x(), e.pos().y(), "mouse")

    def event(self, e):
        if e.type() in (QEvent.TouchBegin, QEvent.TouchUpdate) and e.type() == QEvent.TouchBegin:
            self.n_touch += 1
            for tp in e.touchPoints():
                self._add(int(tp.pos().x()), int(tp.pos().y()), "touch")
            e.accept()
            return True
        return super().event(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Q):
            QApplication.quit()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#101820"))
        p.setPen(QPen(QColor("#444444"), 1))
        for i in range(1, 10):                                   # a light grid, every tenth of the picture
            p.drawLine(int(w * i / 10), 0, int(w * i / 10), h)
            p.drawLine(0, int(h * i / 10), w, int(h * i / 10))
        p.setPen(QPen(QColor("#ffffff"), 3))
        p.setBrush(QColor("#ffffff"))
        from PyQt5.QtGui import QPolygonF
        from PyQt5.QtCore import QPointF as P
        p.drawPolygon(QPolygonF([P(w / 2, 8), P(w / 2 - 20, 46), P(w / 2 + 20, 46)]))      # UP arrow
        p.setBrush(Qt.NoBrush)
        for i, (x, y, kind) in enumerate(self.dots):
            c = QColor("#f0b323") if kind == "mouse" else QColor("#6fd36f")
            c.setAlpha(120 + 22 * i)
            p.setPen(QPen(c, 4))
            p.drawEllipse(QPointF(x, y), 32, 32)
            p.drawLine(int(x - 40), int(y), int(x + 40), int(y))
            p.drawLine(int(x), int(y - 40), int(x), int(y + 40))
        p.setPen(QColor("#ffffff"))
        p.setFont(QFont("Sans", 13))
        p.drawText(QRectF(0, 60, w, 26), Qt.AlignHCenter, "UP  - touch the screen")
        p.drawText(QRectF(0, h - 52, w, 24), Qt.AlignHCenter, "picture %d x %d" % (w, h))
        p.drawText(QRectF(0, h - 28, w, 24), Qt.AlignHCenter,
                   "mouse clicks: %d    touch events: %d" % (self.n_mouse, self.n_touch))
        p.end()


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    size = app.primaryScreen().availableGeometry().size()
    rot = int(sys.argv[sys.argv.index("--rotate") + 1]) if "--rotate" in sys.argv else 0
    asp = float(sys.argv[sys.argv.index("--aspect") + 1]) if "--aspect" in sys.argv else 1.0
    if rot:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui"))
        from rotated_host import RotatedHost
        win = RotatedHost(T(), size.width(), size.height(), rot, asp)
    else:
        win = T()
        win.resize(size)
    win.setWindowTitle("touch test")
    win.showFullScreen()
    sys.exit(app.exec_())
