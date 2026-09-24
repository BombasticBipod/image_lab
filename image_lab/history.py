"""Undo/redo history of edit states. Pure Python, no Qt.

Only edits are tracked (background matte, paint strokes, orientation, edges and
padding fill). Loading or pasting an image starts a new history with `reset`.
"""

from dataclasses import dataclass

from image_lab.model import IDENTITY, RGBA, TRANSPARENT, Edges, Matte, Stroke, Transform


@dataclass(frozen=True)
class EditState:
    """Everything the user can undo: the edges, the padding fill, the orientation,
    the paint strokes and the background matte."""

    edges: Edges = Edges()
    fill: RGBA = TRANSPARENT
    transform: Transform = IDENTITY
    strokes: tuple[Stroke, ...] = ()
    matte: Matte | None = None


class History:
    """Linear undo/redo stack. `current` is always the state on screen."""

    def __init__(self, initial: EditState | None = None):
        self.reset(initial or EditState())

    def reset(self, state: EditState):
        """Forget everything; `state` becomes the only entry."""
        self._undo: list[EditState] = []
        self._redo: list[EditState] = []
        self.current = state

    def push(self, state: EditState):
        """Record a new state after an edit. A new edit clears the redo list."""
        if state == self.current:
            return
        self._undo.append(self.current)
        self._redo.clear()
        self.current = state

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> EditState | None:
        """Step back; returns the state to show, or None if there is nothing to undo."""
        return self._move(self._undo, self._redo)

    def redo(self) -> EditState | None:
        """Step forward; returns the state to show, or None if there is nothing to redo."""
        return self._move(self._redo, self._undo)

    def _move(self, src: list[EditState], dst: list[EditState]) -> EditState | None:
        if not src:
            return None
        dst.append(self.current)
        self.current = src.pop()
        return self.current
