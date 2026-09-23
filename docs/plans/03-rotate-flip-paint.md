# Plan 03: rotation, flips, paint to transparency

## Request (verbatim)

> We need to add rotation, vertical/horizontal flip, and painting onto the image to generate a transparency that will contained in the image and used for inpainting in other software

## Clarifications (answers from the user)

- Rotation: both 90° steps and a free angle.
- Paint tool: erase plus restore brush, hard-edged and round, adjustable size, "except we will display it as 50% transparency. The actual export will have the painted sections at 100% transparency."
- Erased pixels keep their original RGB under alpha 0 in the export.
- The three untracked test PNGs in the project root move to the git-ignored `scratch/` folder.
- The user approved these invariant changes: edges are measured in pixels of the rotated/flipped image; export order is mask, then transform, then edges; the transparent corners of a free-angle rotation are image pixels, not padding, so the fill does not cover them.

## Implementation steps

Each step is its own mini-iteration with a minor version bump, changelog entry, STATUS update, commit and tag.

- A (0.12.0): 90° rotation and horizontal/vertical flips, with exact edge permutation, preview, export and undo.
- B (0.13.0): free-angle rotation (affine math in `model.py`, bicubic export, angle spin box, edges clamped).
- C (0.14.0): paint mode: erase and restore strokes in source pixels, shown at 50% transparency, exported fully transparent with original RGB kept.
