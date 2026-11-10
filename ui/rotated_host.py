"""
ui/rotated_host.py  --  show a normal widget turned by 90 / 180 / 270 degrees INSIDE the program.

Why: on the Pi 2 the desktop (labwc + XWayland) stretches every program on a screen rotated with
wlr-randr (tools/screen_test.py shows a round circle as an oval).  So the screen is left as it is
(800 x 480) and the program turns its own picture instead.  Nothing about the desktop changes.

How: the whole window content is put into a QGraphicsView as a proxy widget and the proxy is
rotated.  Qt then redraws only the part of the screen that changed, turned the right way.

    host = RotatedHost(content_widget, physical_w, physical_h, 90)
    window.setCentralWidget(host)

content_widget is laid out at its LOGICAL size: physical_h x physical_w for 90 / 270
(480 x 800 on an 800 x 480 panel), physical_w x physical_h for 0 / 180.
  90   the TOP of the content is at the RIGHT edge of the screen
  270  the TOP of the content is at the LEFT  edge of the screen
Try the other one if the picture is upside down.

PIXEL ASPECT: many cheap 7-inch 800 x 480 panels have pixels that are NOT square: each pixel is
about 7.6 % wider (0.1926 x 0.179 mm) along the 800-pixel side, so every circle comes out an oval
(vertical on an upright panel).  aspect = 1.076 corrects it: the content is laid out on a grid of
square pixels, 800 * 1.076 = 861 long on that side, and squeezed back to the 800 real pixels.
aspect = 1.0 (default) changes nothing.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTransform
from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene


def logical_size(physical_w, physical_h, rotation, aspect=1.0):
    """Size (square pixels) the content is laid out at, for a screen of physical_w x physical_h
    whose pixels are `aspect` times wider than tall."""
    wide = int(round(physical_w * aspect))          # the panel's long side, in square pixels
    return (physical_h, wide) if rotation in (90, 270) else (wide, physical_h)


class RotatedHost(QGraphicsView):
    def __init__(self, content, physical_w, physical_h, rotation, aspect=1.0, parent=None):
        scene = QGraphicsScene(0, 0, physical_w, physical_h)
        super().__init__(scene, parent)
        self.rotation = rotation
        lw, lh = logical_size(physical_w, physical_h, rotation, aspect)

        self.setFrameShape(QGraphicsView.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setBackgroundBrush(QColor("#000000"))
        self.setViewportUpdateMode(QGraphicsView.MinimalViewportUpdate)
        self.setOptimizationFlags(QGraphicsView.DontSavePainterState)
        self.setFocusPolicy(Qt.NoFocus)

        self.proxy = scene.addWidget(content)       # the content now lives in the scene
        self.proxy.resize(lw, lh)
        # ONE transform: first squeeze the square-pixel grid onto the real pixels (only when
        # aspect != 1), then rotate, then move the rotated picture back onto the screen.
        # QTransform applies its steps to a point in REVERSE order of the calls below.
        if rotation in (90, 270):
            sx, sy = 1.0, physical_w / float(lh)       # the long side (logical y) is squeezed
        else:
            sx, sy = physical_w / float(lw), 1.0       # the long side (logical x) is squeezed
        pos = {0: (0, 0), 90: (physical_w, 0), 180: (physical_w, physical_h),
               270: (0, physical_h)}.get(rotation, (0, 0))
        t = QTransform()
        t.translate(pos[0], pos[1])
        if rotation:
            t.rotate(rotation)
        t.scale(sx, sy)
        self.proxy.setTransform(t)

    def resizeEvent(self, event):
        # the scene is exactly the screen size; keep the view showing it from the top-left
        self.setSceneRect(self.scene().sceneRect())
        super().resizeEvent(event)
