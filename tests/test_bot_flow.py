"""Bot handlers end to end with a fake Telegram side (no network, no token)."""

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402
from enhancer import models  # noqa: E402

HAVE_MODELS = all((models.MODELS_DIR / f"{n}.onnx").exists() for n in ("real_esrgan_x4", "yoloface_8n"))


class FakeStatus:
    def __init__(self, log):
        self.log = log

    async def edit_text(self, text):
        self.log.append(("edit", text))

    async def delete(self):
        self.log.append(("delete",))


class FakeMessage:
    def __init__(self, user_id=1):
        self.log, self.sent = [], []
        self.from_user = SimpleNamespace(id=user_id)

        async def call(method, request_timeout=None):
            self.sent.append((type(method).__name__, request_timeout, method))
        self.bot = call

    async def answer(self, text):
        self.log.append(("answer", text))
        return FakeStatus(self.log)

    async def reply(self, text):
        self.log.append(("reply", text))
        return FakeStatus(self.log)

    def answer_document(self, f, caption=None):
        shutil.copy(f.path, Path(self._out) / Path(f.filename).name)
        return SimpleNamespace(kind="document", caption=caption, name=f.filename)

    def answer_photo(self, f, caption=None):
        return SimpleNamespace(kind="photo", caption=caption)

    def answer_video(self, f, caption=None, **kw):
        shutil.copy(f.path, Path(self._out) / Path(f.filename).name)
        return SimpleNamespace(kind="video", caption=caption, **kw)


class FakeBot:
    def __init__(self, src):
        self.src = src

    async def download(self, file_id, destination, timeout=30):
        shutil.copy(self.src, destination)


@pytest.mark.skipif(not HAVE_MODELS, reason="models not downloaded")
def test_photo_flow_sends_result_then_preview(tmp_path):
    src = tmp_path / "p.png"
    img = np.zeros((90, 120, 3), np.uint8)
    cv2.rectangle(img, (20, 20), (100, 70), (40, 120, 220), -1)
    cv2.imwrite(str(src), img)
    m = FakeMessage()
    m._out = tmp_path
    asyncio.run(bot.handle_photo(m, FakeBot(src), "fid", 1000, compressed=False))
    kinds = [s[2].kind for s in m.sent]
    assert kinds[0] == "document" and "photo" in kinds                # result first, preview after
    assert all(s[1] == bot.UPLOAD_TIMEOUT for s in m.sent)
    out = cv2.imread(str(tmp_path / "enhanced_4k.jpg"))
    assert out.shape[:2] == (360, 480)                                 # x4 for a small input


def test_oversized_file_is_refused_before_queueing(tmp_path):
    m = FakeMessage()
    asyncio.run(bot.handle_photo(m, FakeBot(tmp_path / "none"), "fid", 30 * 1024 * 1024, compressed=True))
    assert m.log and m.log[0][0] == "reply" and not m.sent


def test_video_flow_without_ai(tmp_path, monkeypatch):
    src = tmp_path / "v.mp4"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "96x160",
                          "-r", "30", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
                         stdin=subprocess.PIPE)
    for i in range(30):
        fr = np.zeros((160, 96, 3), np.uint8)
        cv2.circle(fr, (10 + i * 2, 80), 8, (0, 200, 255), -1)
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()
    real = bot.video.enhance_video
    monkeypatch.setattr(bot.video, "enhance_video",
                        lambda s, d, o, f, mb, ai, w, pr, ms, st: real(s, d, 192, f, mb, False, 2, pr, ms, st))
    m = FakeMessage()
    m._out = tmp_path
    asyncio.run(bot.handle_video(m, FakeBot(src), "fid", 1000, 1.0))
    kinds = [s[2].kind for s in m.sent]
    assert kinds[0] == "video"
    assert (tmp_path / "enhanced_120fps.mp4").exists()
    assert not any(e[0] == "edit" and e[1] == bot.TXT["fail"] for e in m.log)
