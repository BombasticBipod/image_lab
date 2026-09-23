# Plan 02: save button, undo/redo, copy/paste, drag out

## Request (verbatim)

> We need a save button on screen, it should default to an folder called out in the image_lab directory. We need control-z, control-control-y, control-c and control-v support. As well as the ability to drag the modified image back out of image_lab.

## Clarifications (answers from the user)

- Save button: defaults to one click, but an arrow attached to the button provides the Save As dialog.
- Ctrl+Z / Ctrl+Y undo scope: edits only (edge drags, Reset, padding color). Loading or pasting a new image starts a fresh history.
- Ctrl+V: pastes image data or an image file copied in Explorer; either replaces the current image.
- Drag out: always PNG.

## Implementation steps

Each step is its own mini-iteration with a minor version bump, changelog entry, STATUS update, commit and tag.

- A (0.8.0): toolbar split Save button; one-click save to `out/<stem>_edited.png` with numbering; arrow opens Save As (which also starts in `out/`).
- B (0.9.0): undo/redo of edits with a Qt-free `history.py`.
- C (0.10.0): Ctrl+C copies the edited image; Ctrl+V pastes image data or a copied image file.
- D (0.11.0): drag the edited image out of the canvas as a PNG written to `out/`.
