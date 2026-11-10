"""
tools/screen_test.py -- tells you whether the SCREEN shows round things round.

No project code is used, only PyQt5, so it proves whether a stretched clock comes from the
clock program or from the way the Pi / desktop shows a rotated screen.

Run on the Pi (after the rotation is applied):
    source venv/bin/activate
    export DISPLAY=:0 QT_QPA_PLATFORM=xcb
    python3 tools/screen_test.py            (Ctrl+C in the terminal, or Esc / Q on the Pi's keyboard, quits)

It fills the screen and draws:
    a big CIRCLE, a SQUARE (the square's sides are 200 px), two diagonal lines corner to corner,
    an arrow marked UP, and the sizes Qt believes in (screen, window, scale).
Look at the screen:
    circle round, square square   -> the screen is fine, the problem is in the clock page
    circle oval / square a box    -> the picture is stretched AFTER the program draws it
Optional:  python3 tools/screen_test.py --save /tmp/t.png   writes what the program drew, and quits.

FINDING THE RIGHT ASPECT BY EYE (nothing to measure, nothing to type between steps):
    python3 tools/screen_test.py --rotate 270 --sweep
  shows the same picture again and again, 5 seconds each, with a different aspect value written
  at the bottom (0.94 ... 1.13).  Watch the panel upright and note the value where the circle is
  ROUND and the square is a SQUARE.  Ctrl+C stops it.  Then:  bash tools/set_display.sh pixel-aspect <value>

IN-PROGRAM ROTATION (what the clock does with app_rotation.txt):
    python3 tools/screen_test.py --rotate 90      the test picture is turned by the program itself
    python3 tools/screen_test.py --rotate 270     (the desktop's own rotation must be "normal")
  Add  --aspect 1.076  to correct panels whose pixels are not square (circle oval along the long side):
    python3 tools/screen_test.py --rotate 270 --aspect 1.076
  The arrow marked UP must point to the TOP of the screen as you look at it, the circle must be
  round and the square square.  The rotation that does that is the one for app_rotation.txt:
    bash tools/set_display.sh app-rotate 90   (or 270)
"""
import sys
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QPolygonF
from PyQt5.QtWidgets import QApplication, QWidget


class T(QWidget):
    extra = ""                      # one more line of text (the sweep shows its aspect value here)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Q):
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
        if self.extra:
            lines.insert(0, self.extra)
        y = h - 24 * len(lines) - 10
        for t in lines:
            p.drawText(QRectF(0, y, w, 24), Qt.AlignHCenter, t)
            y += 24
        p.end()


if __name__ == "__main__":
    import os
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)   # Ctrl+C quits at once
    app = QApplication(sys.argv)
    size = app.primaryScreen().availableGeometry().size()
    rot = int(sys.argv[sys.argv.index("--rotate") + 1]) if "--rotate" in sys.argv else 0
    if "--sweep" in sys.argv and rot:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui"))
        from rotated_host import RotatedHost
        from PyQt5.QtCore import QTimer
        values = [0.94, 0.97, 1.00, 1.03, 1.05, 1.067, 1.08, 1.10, 1.13]
        steps = int(sys.argv[sys.argv.index("--steps") + 1]) if "--steps" in sys.argv else 0   # testing only
        state = {"i": 0, "win": None, "n": 0}

        def next_value():
            v = values[state["i"] % len(values)]
            state["i"] += 1
            state["n"] += 1
            if steps and state["n"] > steps:
                QApplication.quit()
                return
            content = T()
            content.extra = "ASPECT %.3f" % v
            new = RotatedHost(content, size.width(), size.height(), rot, v)
            new.setWindowTitle("screen test")
            new.showFullScreen()
            if state["win"] is not None:
                state["win"].close()
            state["win"] = new

        next_value()
        timer = QTimer()
        timer.timeout.connect(next_value)
        timer.start(5000 if not steps else 200)
        sys.exit(app.exec_())
    if rot:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui"))
        from rotated_host import RotatedHost
        content = T()
        asp = float(sys.argv[sys.argv.index("--aspect") + 1]) if "--aspect" in sys.argv else 1.0
        win = RotatedHost(content, size.width(), size.height(), rot, asp)
    else:
        win = T()
        win.resize(size)
    win.setWindowTitle("screen test")
    if "--save" in sys.argv:
        win.resize(size)
        win.show()
        app.processEvents()
        win.grab().save(sys.argv[sys.argv.index("--save") + 1])
        sys.exit(0)
    win.showFullScreen()
    sys.exit(app.exec_())
