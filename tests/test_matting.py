"""Tests for matting.py: pre- and post-processing, the model download, and the CPU fallback.

The real model (about 1 GB) is not needed; one opt-in test runs it when present
and IMAGE_LAB_MODEL_TESTS=1 is set.
"""

import os

import pytest
from PIL import Image, ImageDraw

from image_lab import matting

np = pytest.importorskip("numpy")


def test_is_installed_with_the_bg_extra():
    pytest.importorskip("onnxruntime")
    assert matting.is_installed()


def test_model_dir_is_in_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert matting.model_dir() == tmp_path / "image_lab" / "models"
    assert matting.model_path().parent == matting.model_dir()


def test_model_url_is_pinned_to_a_revision():
    assert matting.MODEL_REVISION in matting.MODEL_URL
    assert "/resolve/main/" not in matting.MODEL_URL


def test_preprocess_shape_and_normalization():
    img = Image.new("RGBA", (300, 100), (255, 0, 128, 0))
    x = matting.preprocess(img)
    assert x.shape == (1, 3, 1024, 1024)
    assert x.dtype == np.float32
    # Alpha is ignored: the RGB under a transparent pixel is what the model sees.
    rgb = (255, 0, 128)
    expected = [(v / 255 - m) / s for v, m, s in zip(rgb, matting.MEAN, matting.STD, strict=True)]
    assert x[0, :, 500, 500] == pytest.approx(expected, abs=1e-5)


def test_preprocess_stretches_to_a_square():
    img = Image.new("RGB", (200, 100), (0, 0, 0))
    img.paste((255, 255, 255), (100, 0, 200, 100))
    x = matting.preprocess(img)
    white = (1 - matting.MEAN[0]) / matting.STD[0]
    assert x[0, 0, 10, 1000] == pytest.approx(white, abs=1e-5)
    assert x[0, 0, 1000, 10] < 0


def test_postprocess_sigmoid_and_size():
    logits = np.zeros((1, 1, 4, 4), dtype=np.float32)
    logits[..., :2] = 20
    logits[..., 2:] = -20
    matte = matting.postprocess(logits, (40, 10))
    assert matte.mode == "L"
    assert matte.size == (40, 10)
    assert matte.getpixel((0, 5)) == 255
    assert matte.getpixel((39, 5)) == 0
    assert matting.postprocess(np.zeros((1, 1, 4, 4)), (4, 4)).getpixel((1, 1)) == 128


def test_has_model_checks_the_size(tmp_path):
    path = tmp_path / "m.onnx"
    assert not matting.has_model(path)
    path.write_bytes(b"x" * 10)
    assert not matting.has_model(path)


def _source(tmp_path, data):
    src = tmp_path / "src.bin"
    src.write_bytes(data)
    return src.as_uri()


def test_download_model_writes_the_file_and_reports_progress(tmp_path):
    data = b"model" * 1000
    dest = tmp_path / "models" / "m.onnx"
    calls = []
    path = matting.download_model(
        dest, lambda done, total: calls.append((done, total)), _source(tmp_path, data), len(data)
    )
    assert path == dest
    assert dest.read_bytes() == data
    assert calls[-1] == (len(data), len(data))
    assert not dest.with_name("m.onnx.part").exists()


def test_incomplete_download_leaves_no_file(tmp_path):
    dest = tmp_path / "m.onnx"
    with pytest.raises(OSError, match="incomplete"):
        matting.download_model(dest, None, _source(tmp_path, b"short"), 100)
    assert not dest.exists()
    assert not dest.with_name("m.onnx.part").exists()


class _FakeSession:
    """Fails on the GPU provider (like an out-of-memory card) and works on the CPU."""

    created = []

    def __init__(self, path, providers):
        self.providers = providers
        _FakeSession.created.append(providers)

    def get_inputs(self):
        class Input:
            name = "input_image"

        return [Input()]

    def run(self, outputs, feed):
        if "DmlExecutionProvider" in self.providers:
            raise RuntimeError("Not enough memory resources")
        return [np.full((1, 1, 8, 8), 20.0, dtype=np.float32)]


@pytest.fixture
def fake_ort(monkeypatch):
    ort = pytest.importorskip("onnxruntime")
    _FakeSession.created = []
    monkeypatch.setattr(ort, "InferenceSession", _FakeSession)
    monkeypatch.setattr(
        ort, "get_available_providers", lambda: ["DmlExecutionProvider", "CPUExecutionProvider"]
    )
    return _FakeSession


def test_gpu_failure_falls_back_to_cpu_and_stays(fake_ort, tmp_path):
    remover = matting.Remover(tmp_path / "m.onnx")
    img = Image.new("RGB", (30, 20))
    matte = remover.predict(img)
    assert matte.size == (30, 20)
    assert matte.getpixel((5, 5)) == 255
    remover.predict(img)
    # GPU first, then the CPU once; the second prediction reuses the CPU session.
    assert fake_ort.created == [
        ["DmlExecutionProvider", "CPUExecutionProvider"],
        ["CPUExecutionProvider"],
    ]


def test_cpu_failure_is_raised(fake_ort, monkeypatch, tmp_path):
    def broken(self, outputs, feed):
        raise RuntimeError("broken model")

    monkeypatch.setattr(_FakeSession, "run", broken)
    with pytest.raises(RuntimeError, match="broken model"):
        matting.Remover(tmp_path / "m.onnx").predict(Image.new("RGB", (8, 8)))


@pytest.mark.skipif(
    os.environ.get("IMAGE_LAB_MODEL_TESTS") != "1" or not matting.has_model(),
    reason="opt-in: set IMAGE_LAB_MODEL_TESTS=1 with the model downloaded",
)
def test_real_model_separates_a_disc_from_a_plain_background():
    img = Image.new("RGB", (600, 400), (235, 235, 240))
    ImageDraw.Draw(img).ellipse((200, 100, 400, 300), fill=(200, 40, 40))
    matte = matting.Remover().predict(img)
    assert matte.size == img.size
    assert matte.getpixel((300, 200)) > 200
    assert matte.getpixel((20, 20)) < 50
