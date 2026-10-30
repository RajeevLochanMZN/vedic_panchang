"""
ui/background.py  --  full-window background picture for the new dial page.

HOW IT WORKS
  * Two pre-made 16:9 files live in data/backgrounds/:
        bg_1920x1080.jpg   (used on screens up to ~1100 px tall)
        bg_3840x2160.jpg   (used on bigger screens, e.g. 50"/100" 4K panels)
  * The picture is scaled ONCE per window size and kept in memory, so
    painting it every frame is just a fast copy (important on a Pi 3B+).
  * "Cover" scaling: the picture always fills the window completely.  On a
    16:9 screen nothing is cut.  On another shape (e.g. 1024x600 = 1.71:1)
    a thin strip is trimmed from the edges, the picture is never stretched.

USE
    class MyPage(BackgroundWidget):
        ...                 # put your child widgets on top as usual
"""
import os
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QPainter, QPixmap, QColor
from PyQt5.QtWidgets import QWidget

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_BG_DIR = os.path.join(_ROOT, "data", "backgrounds")

# (file name, smallest window height that should use it)
_FILES = [
    ("bg_1920x1080.jpg", 0),
    ("bg_3840x2160.jpg", 1100),
]


def _pick_file(window_height):
    """Return the path of the smallest file that is still sharp enough."""
    chosen = _FILES[0][0]
    for name, min_h in _FILES:
        if window_height >= min_h:
            chosen = name
    return os.path.join(_BG_DIR, chosen)


class BackgroundWidget(QWidget):
    """A QWidget that paints the temple background behind its children."""

    FALLBACK_COLOR = QColor("#8a3a0a")      # shown if the file is missing

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None         # the big picture as loaded from disk
        self._source_path = None
        self._scaled = None         # picture scaled for the current size
        self._scaled_for = None     # (w, h) that _scaled was made for

    # ---- internal ---------------------------------------------------------
    def _ensure_scaled(self):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        if self._scaled is not None and self._scaled_for == (w, h):
            return
        path = _pick_file(h)
        if path != self._source_path:
            self._source = QPixmap(path)
            self._source_path = path
        if self._source is None or self._source.isNull():
            self._scaled = None
            self._scaled_for = (w, h)
            return
        # Scale so the picture covers the window, then cut the overflow.
        s = self._source.scaled(w, h, Qt.KeepAspectRatioByExpanding,
                                Qt.SmoothTransformation)
        x = (s.width() - w) // 2
        y = (s.height() - h) // 2
        self._scaled = s.copy(QRect(x, y, w, h))
        self._scaled_for = (w, h)

    # ---- Qt events --------------------------------------------------------
    def resizeEvent(self, event):
        self._scaled = None              # force a re-scale on next paint
        super().resizeEvent(event)

    def paintEvent(self, event):
        self._ensure_scaled()
        p = QPainter(self)
        if self._scaled is None:
            p.fillRect(self.rect(), self.FALLBACK_COLOR)
        else:
            p.drawPixmap(0, 0, self._scaled)
        p.end()
