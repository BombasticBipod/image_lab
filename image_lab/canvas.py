"""ImageCanvas: the central widget that draws the image and handles edge dragging and painting.

All geometry comes from `model.py`; this module only maps it to the screen and
turns mouse movement into `adjust_edge` calls. The image is drawn through the
model's orientation matrix, so the one pixmap from load serves every rotation.
Dragging from inside the image (not on an edge) asks the window to drag the
edited image out as a file. In paint mode, dragging paints instead: left erases,
right restores. Painted pixels, and background taken away by background removal, are
shown at 50% transparency; the export makes them fully transparent.
"""

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QApplication, QWidget

from image_lab.model import (
    IDENTITY,
    RGBA,
    SIDES,
    TRANSPARENT,
    Edges,
    Matte,
    Rect,
    Stroke,
    Transform,
    adjust_edge,
    affine,
    output_box,
    render_mask,
    transformed_size,
    view_to_source,
    visible_rect,
)
from image_lab.qtimage import mask_to_qimage

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
BRUSH_OUTLINE = QColor(255, 255, 255)
BRUSH_OUTLINE_DARK = QColor(0, 0, 0)
# Painted pixels are previewed this transparent; the export makes them fully transparent.
PAINT_PREVIEW_OPACITY = 0.5
DEFAULT_BRUSH_SIZE = 40

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
    """Custom-painted view of the image with draggable edges and a paint mode.

    Geometry is in view-image pixels (the original after `transform`). The view is
    a uniform scale plus an origin: screen = origin + scale * view_pixel. Both stay
    frozen during a drag so the image doesn't move under the cursor; the view refits
    when the drag ends.
    """

    # Emitted whenever the edges change, including every step of a drag.
    edgesChanged = Signal()
    # Emitted once when a drag ends with different edges: one undo step per drag.
    editFinished = Signal()
    # Emitted when the user drags from inside the image, away from the edges.
    dragOutRequested = Signal()
    # Emitted once when a paint stroke ends: one undo step per stroke.
    strokeFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self._pixmap: QPixmap | None = None
        self._edges = Edges()
        self._transform = IDENTITY
        self._scale = 1.0
        self._origin = QPointF(0, 0)
        self._hover: str | None = None
        self._drag: _Drag | None = None
        # Press position of a possible drag-out; it starts once the mouse moves far enough.
        self._drag_out_from: QPointF | None = None
        self._fill: RGBA = TRANSPARENT
        self._checker = _checker_brush()
        self._paint_mode = False
        self._brush_size = DEFAULT_BRUSH_SIZE
        self._strokes: tuple[Stroke, ...] = ()
        self._matte: Matte | None = None
        # Erased pixels (alpha 255) in original-image pixels, or None with no strokes and
        # no matte. Rebuilt from the model when the strokes or the matte change, not per
        # repaint.
        self._mask: QImage | None = None
        # The stroke being painted: its points (original-image) and whether it erases.
        self._stroke_points: list[tuple[float, float]] | None = None
        self._stroke_erase = True
        # Screen position of the brush outline in paint mode, or None when not shown.
        self._brush_pos: QPointF | None = None

    # --- public state ---------------------------------------------------------

    @property
    def scale(self) -> float:
        """Screen pixels per view-image pixel."""
        return self._scale

    @property
    def origin(self) -> QPointF:
        """Screen position of view-image pixel (0, 0)."""
        return QPointF(self._origin)

    @property
    def edges(self) -> Edges:
        return self._edges

    @property
    def transform(self) -> Transform:
        """Orientation of the original in the view (flip and rotation)."""
        return self._transform

    @property
    def hovered_edge(self) -> str | None:
        """Side under the cursor, or being dragged; None otherwise."""
        return self._hover

    @property
    def is_dragging(self) -> bool:
        """True while an edge drag or a paint stroke is in progress."""
        return self._drag is not None or self._stroke_points is not None

    @property
    def paint_mode(self) -> bool:
        return self._paint_mode

    def set_paint_mode(self, on: bool):
        """In paint mode the mouse paints; edges and drag-out are unavailable."""
        if self.is_dragging:
            return
        self._paint_mode = on
        self._brush_pos = None
        self._set_hover(None)
        self.update()

    @property
    def brush_size(self) -> int:
        """Brush diameter in image pixels."""
        return self._brush_size

    def set_brush_size(self, size: int):
        self._brush_size = max(1, int(size))
        self.update()

    @property
    def strokes(self) -> tuple[Stroke, ...]:
        """Paint strokes in original-image points, oldest first."""
        return self._strokes

    def set_strokes(self, strokes: tuple[Stroke, ...]):
        """Replace the strokes (for reset and undo/redo) and rebuild the mask preview."""
        self._strokes = strokes
        self._stroke_points = None
        self._rebuild_mask()
        self.update()

    @property
    def matte(self) -> Matte | None:
        """Background-removal matte in original-image pixels, or None."""
        return self._matte

    def set_matte(self, matte: Matte | None):
        """Replace the matte and rebuild the mask preview. Removed background shows like
        painted pixels, and the restore brush brings it back."""
        self._matte = matte
        self._rebuild_mask()
        self.update()

    def _rebuild_mask(self):
        # The model draws the mask, so the preview shows exactly what the export erases.
        if self._pixmap is None or (not self._strokes and self._matte is None):
            self._mask = None
        else:
            mask = render_mask(self._source_size(), self._strokes, self._matte)
            self._mask = mask_to_qimage(mask)

    def has_image(self) -> bool:
        return self._pixmap is not None

    @property
    def fill(self) -> RGBA:
        """Padding color shown in the preview (RGBA)."""
        return self._fill

    def set_image(self, pixmap: QPixmap):
        """Show a new image upright with edges reset. The caller converts once; we reuse
        the pixmap."""
        self._pixmap = pixmap
        self._strokes = ()
        self._matte = None
        self._stroke_points = None
        self._rebuild_mask()
        self.set_transform(IDENTITY, Edges())

    def reset_edges(self):
        """Set all edges back to zero and refit. The orientation is kept."""
        self.set_edges(Edges())

    def set_edges(self, edges: Edges):
        """Replace the edges (for reset and undo/redo), cancel any drag, and refit."""
        self.set_transform(self._transform, edges)

    def set_transform(self, transform: Transform, edges: Edges):
        """Replace orientation and edges together (edges are in the new view's pixels),
        cancel any drag, and refit."""
        self._transform = transform
        self._edges = edges
        self._drag = None
        self._fit()
        self.update()
        self.edgesChanged.emit()

    def set_fill(self, fill: RGBA):
        """Change the padding color; the fill is independent of the edges."""
        self._fill = fill
        self.update()

    # --- geometry -------------------------------------------------------------

    def _source_size(self) -> tuple[int, int]:
        return (self._pixmap.width(), self._pixmap.height())

    def _image_size(self) -> tuple[int, int]:
        """Size of the view image, which the edges and all screen geometry refer to."""
        return transformed_size(self._source_size(), self._transform)

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

    def _inside(self, pos: QPointF) -> bool:
        return self._pixmap is not None and self._output_screen_rect().contains(pos)

    def _hit(self, pos: QPointF) -> str | None:
        if self._pixmap is None or self._paint_mode:
            return None
        r = self._output_screen_rect()
        return hit_edge((r.left(), r.top(), r.right(), r.bottom()), pos.x(), pos.y())

    def _set_hover(self, side: str | None, inside: bool = False):
        """Track the hovered edge and pick the cursor: resize on edges, open hand inside,
        a cross in paint mode."""
        if self._paint_mode and self._pixmap is not None:
            self.setCursor(Qt.CrossCursor)
        elif side is not None:
            self.setCursor(CURSORS[side])
        elif inside:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.unsetCursor()
        if side != self._hover:
            self._hover = side
            self.update()

    def _hover_at(self, pos: QPointF):
        self._set_hover(self._hit(pos), self._inside(pos))

    # --- paint strokes ------------------------------------------------------------

    def _source_point(self, pos: QPointF) -> tuple[float, float]:
        # Screen -> view-image pixels (scale and origin) -> original pixels (model).
        view = (
            (pos.x() - self._origin.x()) / self._scale,
            (pos.y() - self._origin.y()) / self._scale,
        )
        return view_to_source(view, self._source_size(), self._transform)

    def _start_stroke(self, pos: QPointF, erase: bool):
        if self._mask is None:
            w, h = self._source_size()
            self._mask = QImage(w, h, QImage.Format_Alpha8)
            self._mask.fill(0)
        self._stroke_points = []
        self._stroke_erase = erase
        self._extend_stroke(pos)

    def _extend_stroke(self, pos: QPointF):
        """Add a point and draw the new piece straight into the mask, so the preview
        follows the mouse without rebuilding the whole mask."""
        point = self._source_point(pos)
        last = self._stroke_points[-1] if self._stroke_points else point
        self._stroke_points.append(point)
        painter = QPainter(self._mask)
        # Source mode writes the alpha as is, so overlapping pieces don't compound.
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        color = QColor(0, 0, 0, 255 if self._stroke_erase else 0)
        painter.setPen(QPen(color, self._brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(QPointF(*last), QPointF(*point))
        painter.end()
        self.update()

    def _finish_stroke(self):
        stroke = Stroke(tuple(self._stroke_points), self._brush_size / 2, self._stroke_erase)
        self.set_strokes((*self._strokes, stroke))
        self.strokeFinished.emit()

    # --- mouse ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if self._paint_mode:
            if self._pixmap is not None and self._stroke_points is None:
                if event.button() in (Qt.LeftButton, Qt.RightButton):
                    self._start_stroke(event.position(), event.button() == Qt.LeftButton)
            return
        if event.button() != Qt.LeftButton:
            return
        pos = event.position()
        side = self._hit(pos)
        if side is not None:
            self._drag = _Drag(side, pos, self._edges)
            self._set_hover(side)
        elif self._inside(pos):
            self._drag_out_from = pos

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._paint_mode:
            self._brush_pos = pos if self._pixmap is not None else None
            if self._stroke_points is not None:
                self._extend_stroke(pos)
            else:
                self._set_hover(None)
                self.update()
            return
        if self._drag_out_from is not None:
            if (pos - self._drag_out_from).manhattanLength() >= QApplication.startDragDistance():
                self._drag_out_from = None
                self.dragOutRequested.emit()
            return
        if self._drag is None:
            self._hover_at(pos)
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
        if self._stroke_points is not None:
            # The stroke ends when the button that started it is released.
            if event.button() == (Qt.LeftButton if self._stroke_erase else Qt.RightButton):
                self._finish_stroke()
            return
        if event.button() != Qt.LeftButton:
            return
        self._drag_out_from = None
        if self._drag is None:
            return
        changed = self._edges != self._drag.start
        self._drag = None
        self._fit()
        self._hover_at(event.position())
        self.update()
        if changed:
            self.editFinished.emit()

    def leaveEvent(self, event):
        if self._brush_pos is not None:
            self._brush_pos = None
            self.update()
        if self._drag is None:
            self._set_hover(None)
        super().leaveEvent(event)

    def resizeEvent(self, event):
        if not self.is_dragging:
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
        vis_screen = self._to_screen(vis)
        # The checkerboard marks transparent padding and transparent image pixels.
        painter.fillRect(out, self._checker)
        if self._fill[3] > 0:
            # Fill only the padding, not under the image: export pastes the image
            # over the fill, so transparent image pixels stay transparent there too.
            padding = QPainterPath()
            padding.addRect(out)
            image_area = QPainterPath()
            image_area.addRect(vis_screen)
            painter.fillPath(padding.subtracted(image_area), QColor(*self._fill))
        if self._scale < 1.0 or not self._transform.is_right_angle:
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.save()
        painter.setClipRect(vis_screen)
        painter.setTransform(self._source_to_screen())
        painter.drawPixmap(0, 0, self._pixmap)
        painter.restore()
        if self._mask is not None:
            self._paint_mask(painter, vis_screen)

        # Width 0 is Qt's cosmetic pen: always 1 screen pixel.
        painter.setPen(QPen(BORDER_COLOR, 0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(out)
        if self._paint_mode:
            self._paint_brush(painter)
        else:
            self._paint_handles(painter, out)

    def _source_to_screen(self) -> QTransform:
        # Original pixels -> view pixels (model matrix) -> screen (scale, then origin).
        # QTransform maps row vectors, so in a product the left matrix applies first.
        a, b, c, d, e, f = affine(self._source_size(), self._transform)
        view_to_screen = QTransform(
            self._scale, 0, 0, self._scale, self._origin.x(), self._origin.y()
        )
        return QTransform(a, d, b, e, c, f) * view_to_screen

    def _paint_mask(self, painter: QPainter, vis_screen: QRectF):
        """Show painted and background-removed pixels at 50% transparency: the
        checkerboard, cut to the mask's shape, is drawn over them at half opacity."""
        overlay = QImage(self.size(), QImage.Format_ARGB32_Premultiplied)
        overlay.fill(Qt.transparent)
        p = QPainter(overlay)
        if self._scale < 1.0 or not self._transform.is_right_angle:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setTransform(self._source_to_screen())
        p.drawImage(0, 0, self._mask)
        p.resetTransform()
        # Keep the checkerboard only where the mask put alpha.
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(overlay.rect(), self._checker)
        p.end()
        painter.save()
        painter.setClipRect(vis_screen)
        painter.setOpacity(PAINT_PREVIEW_OPACITY)
        painter.drawImage(0, 0, overlay)
        painter.restore()

    def _paint_brush(self, painter: QPainter):
        if self._brush_pos is None:
            return
        radius = self._brush_size * self._scale / 2
        painter.setBrush(Qt.NoBrush)
        # Two outlines so the brush shows on light and dark pixels.
        painter.setPen(QPen(BRUSH_OUTLINE_DARK, 0))
        painter.drawEllipse(self._brush_pos, radius + 1, radius + 1)
        painter.setPen(QPen(BRUSH_OUTLINE, 0))
        painter.drawEllipse(self._brush_pos, radius, radius)

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
