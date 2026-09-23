# Plan 05: background removal to alpha

This plan was drafted by Claude from the user's request and approved by the user. The request, the draft and the user's answers are recorded here word for word.

## Request

> We are going to implement background removal (background replacement with alpha), look at my comfyui workflows and find the remove background node, learn how that works and propose a plan to implement it in our image_lab project

## Draft plan (approved)

**Scope**
1. New action Image > Remove Background (disabled until load).
2. Runs BiRefNet on the original image and gets a soft alpha matte at the original size. Same preprocessing as the node: 1024 square, ImageNet normalization, sigmoid, bilinear resize back.
3. The matte becomes part of the edit state, in original-image pixels. The original stays unmodified. `render` order becomes: matte, paint mask, orientation, edges.
4. Undo and redo cover it; Reset clears it.
5. Inference runs off the GUI thread with progress in the status bar. The window stays responsive; a second run is blocked while one runs.
6. The paint brush works on top of the matte: erase removes more; restore brings back what the model cut wrongly.
7. Alpha only. The existing padding fill and the JPEG/BMP flatten onto white are unchanged.

**Structure**
- New module `image_lab/matting.py` (no Qt): `predict_matte(img) -> Image("L")`, plus pure pre- and post-processing helpers that can be tested without the model.
- The ML packages go in an optional extra `pip install -e ".[bg]"`. Without it the app still works and the action says "background removal not installed".
- Tests: pure tests for preprocessing, resizing back, and how the matte combines with strokes and orientation; model tests use a fake predictor (no 844 MB model in CI); a GUI test for the action's enabled state, undo and status text.

**Engine**
- A. ONNX: `onnxruntime` or `onnxruntime-directml` plus numpy. Small install, GPU on Windows through DirectML.

**Out of scope for v1:** sensitivity, blur, offset and invert sliders; color background mode; refine_foreground; other models (BEN2, InSPyReNet).

## User's answers

> Yes you can override the invariants this time but make sure you don't forget it's only once, and update all relevant docs. Model A. Let's try to use only components that are available for commercial use. I am not sure what you mean by model location, we are writing python code to remove the background in the image_lab project. Restore brush should restore background yes. Just stick with alpha not color fill.

> Use app data for the large files, yes the plan looks good.

## Resolved details (from the follow-up, accepted by the user)

- Model: `onnx-community/BiRefNet-ONNX`, `onnx/model.onnx` (fp32, 973 MB), MIT licence. RMBG-2.0 is not used because its licence (CC BY-NC 4.0) forbids commercial use.
- Runtime: `onnxruntime-directml` (MIT) with numpy (BSD). DirectML is used when available, with automatic fallback to the CPU.
- The model file is downloaded on first use with the standard library (`urllib`) into `%LOCALAPPDATA%\image_lab\models\`, with progress in the status bar. It is never committed to the repository.
- The invariant changes (invariant 2: a matte step in `render`; invariant 9: the new dependencies) are approved for this plan only.
