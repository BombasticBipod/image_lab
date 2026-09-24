"""Background removal: predict a soft alpha matte for an image with BiRefNet. No Qt.

The model is the MIT-licensed ONNX export of BiRefNet (`onnx-community/BiRefNet-ONNX`),
run with onnxruntime. onnxruntime and numpy are the optional `bg` extra, so they are
imported only when needed and the rest of the app works without them. The model file
(about 1 GB) is downloaded on first use into the user's app data folder, never into
the repository.

The processing follows the ComfyUI RMBG node: resize to a 1024 square, ImageNet
normalization, sigmoid of the model's output, bilinear resize back to the image size.

The app runs the model through `ProcessRemover`, in a child process: onnxruntime holds
Python's GIL for seconds while it loads the model, which would freeze the window if it
ran in the app's own process.
"""

import importlib.util
import multiprocessing
import os
import threading
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


class Cancelled(Exception):
    """A removal was stopped on purpose (Cancel, a new image, or closing the app)."""


def serve(conn, path: str, factory: Callable[[Path], Remover] | None = None):
    """Child-process loop: build the remover once, then answer each image sent on
    `conn` with `("ok", matte)` or `("error", message)`. Ends when the pipe closes."""
    remover = (factory or Remover)(Path(path))
    while True:
        try:
            img = conn.recv()
        except EOFError:
            return
        try:
            matte = remover.predict(img)
        except Exception as exc:
            conn.send(("error", str(exc) or type(exc).__name__))
        else:
            conn.send(("ok", matte))


class ProcessRemover:
    """Predicts mattes like `Remover`, but in one persistent child process.

    The child starts on the first `predict` and keeps its model loaded between calls.
    `predict` blocks the calling thread, not the GIL, while the child works.
    `cancel` stops the child mid-run; the next `predict` starts a new one.
    """

    def __init__(self, path: Path | None = None, factory: Callable[[Path], Remover] | None = None):
        self.path = path or model_path()
        # Must be picklable (a top-level callable): the spawned child receives it.
        self._factory = factory
        self._process = None
        self._conn = None
        # The child stopped by cancel(), so predict can tell a cancel from a crash.
        self._cancelled_process = None
        # A cancelled run's thread may still be cleaning up when the next run starts.
        self._lock = threading.Lock()

    @property
    def pid(self) -> int | None:
        """Process id of the child, or None before the first run."""
        return self._process.pid if self._process is not None else None

    def _start(self):
        # Spawn, not fork: the child must not inherit the parent's Qt state or threads.
        ctx = multiprocessing.get_context("spawn")
        self._conn, child_conn = ctx.Pipe()
        self._process = ctx.Process(
            target=serve,
            args=(child_conn, str(self.path), self._factory),
            name="image_lab-matting",
            daemon=True,
        )
        self._process.start()
        child_conn.close()

    def _discard(self, process, conn):
        """End `process` and forget it if it is still the current child; the next
        `predict` then starts a new one."""
        if process is not None:
            process.terminate()
            process.join(5)
        if conn is not None:
            conn.close()
        with self._lock:
            if self._process is process:
                self._process = None
                self._conn = None

    def predict(self, img: Image.Image) -> Image.Image:
        """Soft alpha matte ("L") for `img`, computed in the child process.

        Raises `Cancelled` if `cancel` stopped it, and RuntimeError if the model failed
        or the child died.
        """
        with self._lock:
            if self._process is not None and not self._process.is_alive():
                self._process.join(5)
                self._conn.close()
                self._process = None
            if self._process is None:
                self._start()
            process, conn = self._process, self._conn
        try:
            conn.send(img)
            status, value = conn.recv()
        except (EOFError, OSError) as exc:
            # The child is gone: terminated by cancel(), or it crashed.
            cancelled = process is self._cancelled_process
            self._discard(process, conn)
            if cancelled:
                raise Cancelled() from exc
            raise RuntimeError("Background removal stopped unexpectedly") from exc
        if status == "error":
            raise RuntimeError(value)
        return value

    def cancel(self):
        """Stop a running `predict` (it raises `Cancelled`). Safe to call at any time."""
        with self._lock:
            process = self._process
            self._cancelled_process = process
        # Only terminate here; `predict` cleans up in its own thread when its read fails.
        if process is not None:
            process.terminate()

    def close(self):
        """End the child process, for example when the app closes."""
        self.cancel()
        with self._lock:
            process, conn = self._process, self._conn
            self._process = None
            self._conn = None
        if process is not None:
            process.join(5)
        if conn is not None:
            conn.close()
