"""Background removal: predict a soft alpha matte for an image with BiRefNet. No Qt.

The model is the MIT-licensed ONNX export of BiRefNet (`onnx-community/BiRefNet-ONNX`),
run with onnxruntime. onnxruntime and numpy are the optional `bg` extra, so they are
imported only when needed and the rest of the app works without them. The model file
(about 1 GB) is downloaded on first use into the user's app data folder, never into
the repository.

The processing follows the ComfyUI RMBG node: resize to a 1024 square, ImageNet
normalization, sigmoid of the model's output, bilinear resize back to the image size.
"""

import importlib.util
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

from PIL import Image

# Pinned to one revision of the model repository, so the file never changes under us.
MODEL_REVISION = "534d3c82d3bb8b2f0867db6dfbc3a525b8e42f67"
MODEL_URL = (
    f"https://huggingface.co/onnx-community/BiRefNet-ONNX/resolve/{MODEL_REVISION}/onnx/model.onnx"
)
MODEL_BYTES = 972_666_916
MODEL_FILE = "birefnet-general.onnx"

INPUT_SIZE = 1024
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
# DirectML runs on any DirectX 12 GPU; onnxruntime falls back to the CPU without one.
PROVIDERS = ("DmlExecutionProvider", "CPUExecutionProvider")
DOWNLOAD_CHUNK = 1 << 20

# (bytes done, bytes total)
Progress = Callable[[int, int], None]


def is_installed() -> bool:
    """True if the optional packages (onnxruntime, numpy) are installed."""
    return all(importlib.util.find_spec(name) for name in ("onnxruntime", "numpy"))


def model_dir() -> Path:
    """Folder for large downloaded files: `%LOCALAPPDATA%\\image_lab\\models`."""
    base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    return Path(base) / "image_lab" / "models"


def model_path() -> Path:
    return model_dir() / MODEL_FILE


def has_model(path: Path | None = None) -> bool:
    """True if the model file is present and complete."""
    path = path or model_path()
    return path.is_file() and path.stat().st_size == MODEL_BYTES


def download_model(
    dest: Path | None = None,
    progress: Progress | None = None,
    url: str = MODEL_URL,
    expected_bytes: int = MODEL_BYTES,
) -> Path:
    """Download the model to `dest` and return its path. Raises OSError on failure.

    Writes to a `.part` file first and renames it only when complete, so an
    interrupted download is never mistaken for a model.
    """
    dest = dest or model_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    done = 0
    try:
        with urllib.request.urlopen(url) as response, open(part, "wb") as out:
            while chunk := response.read(DOWNLOAD_CHUNK):
                out.write(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, expected_bytes)
        if done != expected_bytes:
            raise OSError(f"Download incomplete: got {done} of {expected_bytes} bytes")
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)
    return dest


def preprocess(img: Image.Image):
    """Model input: a (1, 3, 1024, 1024) float32 array, RGB normalized with ImageNet
    mean and std. Alpha is ignored; the RGB under transparent pixels is used as is."""
    import numpy as np

    rgb = img.convert("RGB").resize((INPUT_SIZE, INPUT_SIZE), Image.BILINEAR)
    x = np.asarray(rgb, dtype=np.float32) / 255.0
    x = (x - np.array(MEAN, dtype=np.float32)) / np.array(STD, dtype=np.float32)
    return x.transpose(2, 0, 1)[np.newaxis]


def postprocess(logits, size: tuple[int, int]) -> Image.Image:
    """Matte ("L") of `size` from the model's logits: 255 keeps a pixel, 0 removes it."""
    import numpy as np

    x = np.asarray(logits, dtype=np.float32).reshape(logits.shape[-2:])
    alpha = 1.0 / (1.0 + np.exp(-x))
    matte = Image.fromarray(np.round(alpha * 255).astype(np.uint8), "L")
    return matte.resize(size, Image.BILINEAR)


class Remover:
    """Predicts mattes with the model at `path`. The session is created on first use
    and reused, because loading the model takes seconds."""

    def __init__(self, path: Path | None = None):
        self.path = path or model_path()
        self._session = None
        self._cpu_only = False

    def _get_session(self):
        if self._session is None:
            import onnxruntime as ort

            wanted = PROVIDERS[-1:] if self._cpu_only else PROVIDERS
            available = ort.get_available_providers()
            providers = [p for p in wanted if p in available]
            self._session = ort.InferenceSession(str(self.path), providers=providers)
        return self._session

    def _run(self, x):
        session = self._get_session()
        return session.run(None, {session.get_inputs()[0].name: x})[0]

    def predict(self, img: Image.Image) -> Image.Image:
        """Soft alpha matte ("L") for `img`, the same size as `img`."""
        x = preprocess(img)
        try:
            logits = self._run(x)
        except Exception:
            # A GPU can accept the session and still fail to run it (for example, out
            # of memory on a 4 GB card). Retry once on the CPU and stay there.
            if self._cpu_only:
                raise
            self._cpu_only = True
            self._session = None
            logits = self._run(x)
        return postprocess(logits, img.size)
