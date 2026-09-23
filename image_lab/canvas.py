"""ImageCanvas: the central widget that draws the image and handles edge dragging.

All geometry comes from `model.py`; this module only maps it to the screen and
turns mouse movement into `adjust_edge` calls.
"""

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from image_lab.model import SIDES, Edges, Rect, adjust_edge, output_box, visible_rect

BACKGROUND = QColor(48, 48, 48)
EMPTY_TEXT_COLOR = QColor(170, 170, 170)
EMPTY_TEXT = "Drop an image here"
CHECKER_LIGHT = QColor(204, 204, 204)
CHECKER_DARK = QColor(153, 153, 153)
CHECKER_CELL = 8
BORDER_COLOR = QColor(230, 230, 230)
HANDLE_COLOR = QColor(230, 230, 230)
HANDLE_HOVER_COLOR = QColor(255, 170, 0)
HANDLE_OUTLINE = QColor(20, 20, 20)
HANDLE_LONG = 24
HANDLE_SHORT = 8

# Fraction of the widget the output may fill; the rest is room to drag edges outward.
FIT_FRACTION = 0.8
# How close (screen px) the cursor must be to an edge line to grab it.
HIT_TOLERANCE = 8

CURSORS = {
    "left": Qt.SizeHorCursor,
    "right": Qt.SizeHorCursor,
    "top": Qt.SizeVerCursor,
    "bottom": Qt.SizeVerCursor,
}


def hit_edge(
    box: tuple[float, float, float, float], x: float, y: float, tolerance: float = HIT_TOLERANCE
) -> str | None:
    """Which side of screen box (left, top, right, bottom) the point is on, if any.

    A point counts if it is within `tolerance` of a side's line and within the
    side's extent (plus tolerance). Near a corner, the closer side wins.
    """
    left, top, right, bottom = box
    in_x = left - tolerance <= x <= right + tolerance
    in_y = top - tolerance <= y <= bottom + tolerance
    candidates = []
    if in_y:
        candidates += [(abs(x - left), "left"), (abs(x - right), "right")]
    if in_x:
        candidates += [(abs(y - top), "top"), (abs(y - bottom), "bottom")]
    close = [c for c in candidates if c[0] <= tolerance]
    return min(close)[1] if close else None


def _checker_brush() -> QBrush:
    tile = QPixmap(2 * CHECKER_CELL, 2 * CHECKER_CELL)
    tile.fill(CHECKER_LIGHT)
    painter = QPainter(tile)
    painter.fillRect(0, 0, CHECKER_CELL, CHECKER_CELL, CHECKER_DARK)
    painter.fillRect(CHECKER_CELL, CHECKER_CELL, CHECKER_CELL, CHECKER_CELL, CHECKER_DARK)
    painter.end()
    return QBrush(tile)


@dataclass(frozen=True)
class _Drag:
    side: str
    press_pos: QPointF
    start: Edges


class ImageCanvas(QWidget):
    """Custom-painted view of the image with draggable edges.

    The view is a uniform scale plus an origin:
    screen = origin + scale * image_pixel. Both stay frozen during a drag so the
    image doesn't move under the cursor; the view refits when the drag ends.
    """

    edgesChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self._pixmap: QPixmap | None = None
        self._edges = Edges()
        self._scale = 1.0
        self._origin = QPointF(0, 0)
        self._hover: str | None = None
        self._drag: _Drag | None = None
        self._checker = _checker_brush()

    # --- public state ---------------------------------------------------------

    @property
    def scale(self) -> float:
        """Screen pixels per image pixel."""
        return self._scale

    @property
    def origin(self) -> QPointF:
        """Screen position of image pixel (0, 0)."""
        return QPointF(self._origin)

    @property
    def edges(self) -> Edges:
        return self._edges

    @property
    def hovered_edge(self) -> str | None:
        """Side under the cursor, or being dragged; None otherwise."""
        return self._hover

    def has_image(self) -> bool:
        return self._pixmap is not None

    def set_image(self, pixmap: QPixmap):
        """Show a new image with edges reset. The caller converts once; we reuse the pixmap."""
        self._pixmap = pixmap
        self._edges = Edges()
        self._drag = None
        self._fit()
        self.update()
        self.edgesChanged.emit()

    # --- geometry -------------------------------------------------------------

    def _image_size(self) -> tuple[int, int]:
        return (self._pixmap.width(), self._pixmap.height())

    def _fit(self):
        """Scale down (never up) and center the output box in the widget."""
        if self._pixmap is None:
            return
        x0, y0, x1, y1 = output_box(self._image_size(), self._edges)
        self._scale = min(
            FIT_FRACTION * self.width() / (x1 - x0), FIT_FRACTION * self.height() / (y1 - y0), 1.0
        )
        self._origin = QPointF(
            self.width() / 2 - self._scale * (x0 + x1) / 2,
            self.height() / 2 - self._scale * (y0 + y1) / 2,
        )

    def _to_screen(self, rect: Rect) -> QRectF:
        x0, y0, x1, y1 = rect
        s = self._scale
        return QRectF(
            self._origin.x() + s * x0, self._origin.y() + s * y0, s * (x1 - x0), s * (y1 - y0)
        )

    def _output_screen_rect(self) -> QRectF:
        return self._to_screen(output_box(self._image_size(), self._edges))

    def _hit(self, pos: QPointF) -> str | None:
        if self._pixmap is None:
            return None
        r = self._output_screen_rect()
        return hit_edge((r.left(), r.top(), r.right(), r.bottom()), pos.x(), pos.y())

    # --- mouse ----------------------------------------------------------------

    def _set_hover(self, side: str | None):
        if side == self._hover:
            return
        self._hover = side
        if side is None:
            self.unsetCursor()
        else:
            self.setCursor(CURSORS[side])
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        side = self._hit(event.position())
        if side is not None:
            self._drag = _Drag(side, event.position(), self._edges)
            self._set_hover(side)

    def mouseMoveEvent(self, event):
        if self._drag is None:
            self._set_hover(self._hit(event.position()))
            return
        drag = self._drag
        delta = event.position() - drag.press_pos
        dx = round(delta.x() / self._scale)
        dy = round(delta.y() / self._scale)
        # Convert mouse movement into "outward" movement of the dragged side.
        outward = {"left": -dx, "right": dx, "top": -dy, "bottom": dy}[drag.side]
        symmetric = bool(event.modifiers() & Qt.ShiftModifier)
        edges = adjust_edge(self._image_size(), drag.start, drag.side, outward, symmetric)
        if edges != self._edges:
            self._edges = edges
            self.update()
            self.edgesChanged.emit()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._drag is None:
            return
        self._drag = None
        self._fit()
        self._set_hover(self._hit(event.position()))
        self.update()

    def leaveEvent(self, event):
        if self._drag is None:
            self._set_hover(None)
        super().leaveEvent(event)

    def resizeEvent(self, event):
        if self._drag is None:
            self._fit()
        super().resizeEvent(event)

    # --- painting -------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND)
        if self._pixmap is None:
            painter.setPen(EMPTY_TEXT_COLOR)
            painter.drawText(self.rect(), Qt.AlignCenter, EMPTY_TEXT)
            return

        size = self._image_size()
        out = self._output_screen_rect()
        vis = visible_rect(size, self._edges)
        # The checkerboard marks transparent padding and transparent image pixels.
        painter.fillRect(out, self._checker)
        if self._scale < 1.0:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        source = QRectF(vis[0], vis[1], vis[2] - vis[0], vis[3] - vis[1])
        painter.drawPixmap(self._to_screen(vis), self._pixmap, source)

        # Width 0 is Qt's cosmetic pen: always 1 screen pixel.
        painter.setPen(QPen(BORDER_COLOR, 0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(out)
        self._paint_handles(painter, out)

    def _paint_handles(self, painter: QPainter, out: QRectF):
        painter.setPen(QPen(HANDLE_OUTLINE, 0))
        centers = {
            "left": QPointF(out.left(), out.center().y()),
            "right": QPointF(out.right(), out.center().y()),
            "top": QPointF(out.center().x(), out.top()),
            "bottom": QPointF(out.center().x(), out.bottom()),
        }
        for side in SIDES:
            w, h = (
                (HANDLE_SHORT, HANDLE_LONG)
                if side in ("left", "right")
                else (HANDLE_LONG, HANDLE_SHORT)
            )
            rect = QRectF(0, 0, w, h)
            rect.moveCenter(centers[side])
            painter.setBrush(HANDLE_HOVER_COLOR if side == self._hover else HANDLE_COLOR)
            painter.drawRect(rect)
