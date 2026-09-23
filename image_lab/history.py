"""Undo/redo history of edit states. Pure Python, no Qt.

Only edits are tracked (orientation, edges and padding fill). Loading or pasting an image
starts a new history with `reset`.
"""

from dataclasses import dataclass

from image_lab.model import IDENTITY, RGBA, TRANSPARENT, Edges, Transform


@dataclass(frozen=True)
class EditState:
    """Everything the user can undo: the edges, the padding fill and the orientation."""

    edges: Edges = Edges()
    fill: RGBA = TRANSPARENT
    transform: Transform = IDENTITY


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
        if not self._undo:
            return None
        self._redo.append(self.current)
        self.current = self._undo.pop()
        return self.current

    def redo(self) -> EditState | None:
        """Step forward; returns the state to show, or None if there is nothing to redo."""
        if not self._redo:
            return None
        self._undo.append(self.current)
        self.current = self._redo.pop()
        return self.current
