"""Tests for matting.ProcessRemover: the model runs in a real spawned child process.

A small fake model stands in for BiRefNet, so neither onnxruntime nor the model file
is needed. The fake must be a top-level class: the child imports it by name.
"""

import os
import threading
import time

import pytest
from PIL import Image

from image_lab import matting

SLOW_WIDTH = 13  # the fake sleeps on images this wide, so a run can be stopped midway
ERROR_WIDTH = 7  # the fake raises on images this wide


class ChildFake:
    """Fake model for the child: the matte's value counts how often it was built."""

    builds = 0

    def __init__(self, path):
        ChildFake.builds += 1

    def predict(self, img):
        if img.width == SLOW_WIDTH:
            time.sleep(30)
        if img.width == ERROR_WIDTH:
            raise ValueError("bad image")
        return Image.new("L", img.size, ChildFake.builds)


@pytest.fixture
def remover(tmp_path):
    r = matting.ProcessRemover(tmp_path / "m.onnx", factory=ChildFake)
    yield r
    r.close()


def _later(seconds, action):
    timer = threading.Timer(seconds, action)
    timer.start()
    return timer


def test_predict_runs_in_a_child_process(remover):
    matte = remover.predict(Image.new("RGBA", (5, 3)))
    assert matte.mode == "L" and matte.size == (5, 3)
    assert remover.pid is not None and remover.pid != os.getpid()


def test_model_is_built_once_per_child(remover):
    remover.predict(Image.new("RGB", (4, 4)))
    pid = remover.pid
    matte = remover.predict(Image.new("RGB", (4, 4)))
    assert remover.pid == pid
    assert matte.getpixel((0, 0)) == 1


def test_model_error_is_raised(remover):
    with pytest.raises(RuntimeError, match="bad image"):
        remover.predict(Image.new("RGB", (ERROR_WIDTH, 2)))
    # The child survives a model error.
    assert remover.predict(Image.new("RGB", (4, 4))).size == (4, 4)


def test_cancel_stops_a_run_and_the_next_run_recovers(remover):
    remover.predict(Image.new("RGB", (4, 4)))  # start the child first
    first_pid = remover.pid
    timer = _later(0.5, remover.cancel)
    start = time.monotonic()
    with pytest.raises(matting.Cancelled):
        remover.predict(Image.new("RGB", (SLOW_WIDTH, 2)))
    assert time.monotonic() - start < 10
    timer.join()
    assert remover.predict(Image.new("RGB", (4, 4))).size == (4, 4)
    assert remover.pid != first_pid


def test_child_crash_is_an_error(remover):
    remover.predict(Image.new("RGB", (4, 4)))
    timer = _later(0.5, lambda: remover._process.kill())
    with pytest.raises(RuntimeError, match="stopped unexpectedly"):
        remover.predict(Image.new("RGB", (SLOW_WIDTH, 2)))
    timer.join()


def test_close_ends_the_child(remover):
    remover.predict(Image.new("RGB", (4, 4)))
    process = remover._process
    remover.close()
    assert not process.is_alive()


def test_cancelled_download_leaves_no_file(tmp_path):
    src = tmp_path / "src.bin"
    src.write_bytes(b"x" * (3 * matting.DOWNLOAD_CHUNK))
    dest = tmp_path / "m.onnx"

    def stop(done, total):
        raise matting.Cancelled()

    with pytest.raises(matting.Cancelled):
        matting.download_model(dest, stop, src.as_uri(), 3 * matting.DOWNLOAD_CHUNK)
    assert not dest.exists()
    assert not dest.with_name("m.onnx.part").exists()
