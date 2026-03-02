"""
ROI Canvas Overlay for PapayaMeter CameraDialog
------------------------------------------------
Transparent widget that sits on top of the video QLabel.
- Click to place polygon vertices
- Points connected by lines in real time
- Closing segment shown as dashed line from last to first point
- "SET ROI" button saves polygon to DB and disables drawing mode
"""

from PyQt5 import QtCore, QtGui, QtWidgets


class RoiCanvas(QtWidgets.QWidget):
    """
    Transparent overlay drawn over the camera video_label.
    Emits roi_confirmed(list) when the user clicks 'Set ROI'.
    """
    roi_confirmed = QtCore.pyqtSignal(list)   # list of [x, y] pairs (video-space coords)
    roi_cleared   = QtCore.pyqtSignal()

    # Drawing style constants
    _DOT_RADIUS   = 6
    _LINE_WIDTH   = 2
    _DOT_COLOR    = QtGui.QColor(0, 212, 255)        # cyan dots
    _LINE_COLOR   = QtGui.QColor(255, 214, 0)        # yellow lines
    _CLOSE_COLOR  = QtGui.QColor(255, 214, 0, 120)   # translucent yellow (closing edge)
    _FILL_COLOR   = QtGui.QColor(0, 212, 255, 40)    # translucent cyan fill
    _POLY_COLOR   = QtGui.QColor(39, 174, 96)        # green – confirmed polygon

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self._points: list[QtCore.QPoint] = []   # polygon vertices in widget coords
        self._cursor_pos: QtCore.QPoint | None = None
        self._drawing = False       # True while draw mode is active
        self._confirmed = False     # True after SET ROI is pressed
        self._existing_roi: list[list[int]] = []  # previously saved roi (video-space)

        self.hide()

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def start_drawing(self):
        """Enable drawing mode – clears any in-progress polygon."""
        self._points.clear()
        self._cursor_pos = None
        self._confirmed = False
        self._drawing = True
        self.show()
        self.update()
        self.setCursor(QtCore.Qt.CrossCursor)

    def stop_drawing(self):
        """Disable / hide the canvas without saving."""
        self._drawing = False
        self._points.clear()
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

    def show_existing_roi(self, video_points: list, video_w: int, video_h: int):
        """
        Draw a previously saved ROI (in video coordinates) onto the canvas.
        Call after resizing is finalised so coordinates can be scaled properly.
        """
        if not video_points:
            return
        self._existing_roi = video_points
        self._confirmed = True
        self._drawing = False
        self.show()
        self._rescale_existing(video_w, video_h)
        self.update()

    def reset(self):
        self._points.clear()
        self._existing_roi = []
        self._confirmed = False
        self._drawing = False
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.hide()
        self.roi_cleared.emit()

    def get_video_points(self, video_w: int, video_h: int) -> list:
        """
        Convert widget-space polygon points to video-frame coordinates.
        Returns a list of [x, y] pairs.
        """
        if not self._points:
            return []
        sw, sh = self.width(), self.height()
        return [
            [int(p.x() * video_w / sw), int(p.y() * video_h / sh)]
            for p in self._points
        ]

    # ------------------------------------------------------------------ #
    #  Qt Events                                                           #
    # ------------------------------------------------------------------ #

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if not self._drawing:
            return
        if event.button() == QtCore.Qt.LeftButton:
            self._points.append(event.pos())
            self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if self._drawing:
            self._cursor_pos = event.pos()
            self.update()

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        """Double-click = auto-close polygon (same as pressing 'Set ROI')."""
        if self._drawing and len(self._points) >= 3:
            self._confirmed = True
            self._drawing = False
            self.setCursor(QtCore.Qt.ArrowCursor)
            self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        pts = self._points

        if self._confirmed and pts:
            # ── Draw confirmed (filled) polygon ──────────────────────── #
            poly = QtGui.QPolygon([QtCore.QPoint(p.x(), p.y()) for p in pts])
            painter.setBrush(self._FILL_COLOR)
            painter.setPen(QtGui.QPen(self._POLY_COLOR, self._LINE_WIDTH + 1))
            painter.drawPolygon(poly)
            for p in pts:
                painter.setBrush(self._POLY_COLOR)
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawEllipse(p, self._DOT_RADIUS, self._DOT_RADIUS)
            return

        if not self._drawing or not pts:
            return

        # ── Draw in-progress polygon ──────────────────────────────────── #
        pen = QtGui.QPen(self._LINE_COLOR, self._LINE_WIDTH)
        painter.setPen(pen)

        # Edges between placed points
        for i in range(1, len(pts)):
            painter.drawLine(pts[i - 1], pts[i])

        # Cursor rubber-band line
        if self._cursor_pos and pts:
            pen.setColor(self._CLOSE_COLOR)
            pen.setStyle(QtCore.Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(pts[-1], self._cursor_pos)

            # Closing rubber-band to first point (if enough points)
            if len(pts) >= 3:
                pen.setColor(self._CLOSE_COLOR)
                painter.setPen(pen)
                painter.drawLine(pts[0], self._cursor_pos)

        # Dots on placed points
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self._DOT_COLOR)
        for p in pts:
            painter.drawEllipse(p, self._DOT_RADIUS, self._DOT_RADIUS)

    def resizeEvent(self, event):
        super().resizeEvent(event)

    # ------------------------------------------------------------------ #
    #  Private helpers                                                     #
    # ------------------------------------------------------------------ #

    def _rescale_existing(self, video_w: int, video_h: int):
        """Convert stored video-space points to current widget-space points."""
        if not self._existing_roi or not video_w or not video_h:
            return
        sw, sh = self.width(), self.height()
        self._points = [
            QtCore.QPoint(int(p[0] * sw / video_w), int(p[1] * sh / video_h))
            for p in self._existing_roi
        ]
