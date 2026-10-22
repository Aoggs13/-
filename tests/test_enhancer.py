import logging
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from enhancer import models, photo, video  # noqa: E402

HAVE_SR = (models.MODELS_DIR / "clear_reality_x4.onnx").exists()


def test_target_size_caps_at_4k_and_x4():
    assert photo.target_size(960, 444) == (3840, 1776)
    assert photo.target_size(300, 200) == (1200, 800)          # never more than x4
    assert photo.target_size(5000, 3000)[0] == 5000            # never shrinks


def test_grade_keeps_shape_and_whites():
    img = np.full((120, 160, 3), 240, np.uint8)
    img[40:80, 40:120] = (40, 90, 200)
    out = photo.grade(img)
    assert out.shape == img.shape and out.dtype == np.uint8
    w = out[5:30, 5:30].reshape(-1, 3).astype(int)
    assert np.abs(w.max(1) - w.min(1)).max() <= 6              # neutral white stays neutral


def test_before_after_has_label_bar():
    a = np.zeros((100, 50, 3), np.uint8)
    b = np.zeros((400, 200, 3), np.uint8)
    out = photo.before_after(a, b, height=300)
    assert out.shape[0] > 300 and out.shape[1] == 150 + 12 + 150


@pytest.mark.skipif(not HAVE_SR, reason="SR model not downloaded")
def test_upscale_x4_any_size():
    img = (np.random.default_rng(0).random((37, 53, 3)) * 255).astype(np.uint8)
    out = photo.upscale(img, "clear_reality_x4", tile=16, pad=4)
    assert out.shape == (148, 212, 3)


def test_token_never_logged(caplog):
    import bot
    secret = "1234567890:" + "A" * 35
    f = bot.RedactingFilter(secret)
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "url https://api.telegram.org/bot%s/getMe", (secret,), None)
    f.filter(rec)
    assert secret not in rec.getMessage() and "***" in rec.getMessage()


def _clip(path: Path, w=160, h=288, n=30, fps=30):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                          "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
                         stdin=subprocess.PIPE)
    for i in range(n):
        fr = np.zeros((h, w, 3), np.uint8)
        cv2.circle(fr, (20 + i * 4, h // 2), 15, (0, 200, 255), -1)
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()


def test_video_plan_and_pipeline_without_ai(tmp_path):
    src, dst = tmp_path / "in.mp4", tmp_path / "out.mp4"
    _clip(src)
    p = video.probe(src)
    assert (p.width, p.height) == (160, 288) and p.has_audio
    work, out = video.plan(p, 1080)
    assert out[0] % 2 == 0 and out[1] % 2 == 0 and min(out) <= 4 * 160
    info = video.enhance_video(src, dst, out_short=320, use_ai=False, workers=2)
    assert round(info.fps) == 120 and info.has_audio
    assert dst.stat().st_size < 48 * 1024 * 1024
    assert abs(info.duration - p.duration) < 0.2
