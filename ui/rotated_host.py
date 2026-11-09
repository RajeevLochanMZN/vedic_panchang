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
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene


def logical_size(physical_w, physical_h, rotation):
    """Size the content is laid out at, for a screen of physical_w x physical_h."""
    return (physical_h, physical_w) if rotation in (90, 270) else (physical_w, physical_h)


class RotatedHost(QGraphicsView):
    def __init__(self, content, physical_w, physical_h, rotation, parent=None):
        scene = QGraphicsScene(0, 0, physical_w, physical_h)
        super().__init__(scene, parent)
        self.rotation = rotation
        lw, lh = logical_size(physical_w, physical_h, rotation)

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
        if rotation == 90:
            self.proxy.setRotation(90)
            self.proxy.setPos(physical_w, 0)
        elif rotation == 270:
            self.proxy.setRotation(270)
            self.proxy.setPos(0, physical_h)
        elif rotation == 180:
            self.proxy.setRotation(180)
            self.proxy.setPos(physical_w, physical_h)

    def resizeEvent(self, event):
        # the scene is exactly the screen size; keep the view showing it from the top-left
        self.setSceneRect(self.scene().sceneRect())
        super().resizeEvent(event)
