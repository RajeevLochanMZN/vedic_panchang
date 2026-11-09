"""
tools/screen_test.py -- tells you whether the SCREEN shows round things round.

No project code is used, only PyQt5, so it proves whether a stretched clock comes from the
clock program or from the way the Pi / desktop shows a rotated screen.

Run on the Pi (after the rotation is applied):
    source venv/bin/activate
    export DISPLAY=:0 QT_QPA_PLATFORM=xcb
    python3 tools/screen_test.py            (Ctrl+C or Esc to quit)

It fills the screen and draws:
    a big CIRCLE, a SQUARE (the square's sides are 200 px), two diagonal lines corner to corner,
    an arrow marked UP, and the sizes Qt believes in (screen, window, scale).
Look at the screen:
    circle round, square square   -> the screen is fine, the problem is in the clock page
    circle oval / square a box    -> the picture is stretched AFTER the program draws it
Optional:  python3 tools/screen_test.py --save /tmp/t.png   writes what the program drew, and quits.
"""
import sys
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QPolygonF
from PyQt5.QtWidgets import QApplication, QWidget


class T(QWidget):
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            QApplication.quit()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#101820"))
        d = min(w, h) * 0.86
        cx, cy = w / 2.0, h / 2.0
        p.setPen(QPen(QColor("#f0b323"), 4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(cx - d / 2, cy - d / 2, d, d))                  # circle
        p.setPen(QPen(QColor("#6fd36f"), 3))
        p.drawRect(QRectF(cx - 100, cy - 100, 200, 200))                     # 200 x 200 square
        p.setPen(QPen(QColor("#888888"), 1))
        p.drawLine(0, 0, w, h)
        p.drawLine(w, 0, 0, h)
        p.setPen(QPen(QColor("#ffffff"), 3))
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(QPolygonF([QPointF(cx, 8), QPointF(cx - 22, 52), QPointF(cx + 22, 52)]))   # UP arrow
        p.setFont(QFont("Sans", 16, QFont.Bold))
        p.drawText(QRectF(0, 56, w, 30), Qt.AlignHCenter, "UP")
        scr = QApplication.primaryScreen()
        g = scr.availableGeometry()
        p.setFont(QFont("Sans", 12))
        lines = ["window %d x %d" % (w, h),
                 "screen %d x %d" % (g.width(), g.height()),
                 "pixel ratio %.2f" % self.devicePixelRatioF(),
                 "platform %s" % QApplication.platformName(),
                 "circle round? square square?"]
        y = h - 24 * len(lines) - 10
        for t in lines:
            p.drawText(QRectF(0, y, w, 24), Qt.AlignHCenter, t)
            y += 24
        p.end()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = T()
    size = app.primaryScreen().availableGeometry().size()
    win.resize(size)
    win.setWindowTitle("screen test")
    if "--save" in sys.argv:
        win.show()
        app.processEvents()
        win.grab().save(sys.argv[sys.argv.index("--save") + 1])
        sys.exit(0)
    win.showFullScreen()
    sys.exit(app.exec_())
