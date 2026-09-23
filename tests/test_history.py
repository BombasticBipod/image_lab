"""Tests for the undo/redo history (pure Python)."""

from image_lab.history import EditState, History
from image_lab.model import Edges, Stroke, Transform

A = EditState(Edges(left=1))
B = EditState(Edges(left=2))
C = EditState(Edges(left=2), fill=(1, 2, 3, 255))


def test_new_history_is_empty():
    h = History()
    assert h.current == EditState()
    assert not h.can_undo and not h.can_redo
    assert h.undo() is None
    assert h.redo() is None


def test_push_undo_redo_round_trip():
    h = History()
    h.push(A)
    h.push(B)
    assert h.undo() == A
    assert h.undo() == EditState()
    assert not h.can_undo
    assert h.redo() == A
    assert h.redo() == B
    assert not h.can_redo


def test_push_clears_redo():
    h = History()
    h.push(A)
    h.push(B)
    h.undo()
    h.push(C)
    assert not h.can_redo
    assert h.undo() == A


def test_duplicate_push_is_ignored():
    h = History()
    h.push(A)
    h.push(A)
    h.undo()
    assert h.current == EditState()
    assert not h.can_undo


def test_fill_change_is_its_own_step():
    h = History()
    h.push(B)
    h.push(C)
    assert h.undo() == B


def test_orientation_change_is_its_own_step():
    h = History()
    h.push(B)
    turned = EditState(Edges(top=2), transform=Transform(90))
    h.push(turned)
    assert h.current.transform == Transform(90)
    assert h.undo() == B
    assert h.redo() == turned


def test_stroke_is_its_own_step():
    h = History()
    h.push(B)
    painted = EditState(Edges(left=2), strokes=(Stroke(((1.0, 1.0),), 3.0),))
    h.push(painted)
    assert h.undo() == B
    assert h.redo() == painted


def test_reset_forgets_everything():
    h = History()
    h.push(A)
    h.reset(B)
    assert h.current == B
    assert not h.can_undo and not h.can_redo
