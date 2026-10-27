"""Bot handler end to end with a fake Telegram side (no network, no token)."""

import asyncio
import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EVOSKIN_NO_DOWNLOAD", "1")

import bot  # noqa: E402
from evoskin import reference  # noqa: E402


class FakeStatus:
    def __init__(self, log):
        self.log = log

    async def edit_text(self, text):
        self.log.append(("edit", text))

    async def delete(self):
        self.log.append(("delete",))


class FakeMessage:
    def __init__(self):
        self.log, self.sent = [], []
        self.from_user = SimpleNamespace(id=1)

        async def call(method, request_timeout=None):
            self.sent.append(method)

        self.bot = call

    async def answer(self, text):
        self.log.append(("answer", text))
        return FakeStatus(self.log)

    async def reply(self, text):
        self.log.append(("reply", text))

    def answer_photo(self, photo, caption=None):
        return ("photo", photo.filename)

    def answer_animation(self, animation, caption=None):
        return ("animation", animation.filename)

    def answer_document(self, document, caption=None):
        return ("document", document.filename)


class FakeBot:
    def __init__(self, data):
        self.data = data

    async def download(self, file_id, destination=None, timeout=None):
        return io.BytesIO(self.data)


def test_skin_round_trip():
    ok, enc = cv2.imencode(".png", cv2.resize(reference.ref_image(), None, fx=1.5, fy=1.5))
    msg = FakeMessage()
    asyncio.run(bot.handle_skin(msg, FakeBot(enc.tobytes()), "file", 1000, compressed=False))
    assert msg.sent == [("photo", "frames.png"), ("animation", "idle.gif"), ("animation", "fly.gif"),
                        ("animation", "attack.gif"), ("document", "skin_frames.zip")]
    assert ("delete",) in msg.log


def test_bad_file_is_reported():
    msg = FakeMessage()
    asyncio.run(bot.handle_skin(msg, FakeBot(b"garbage"), "file", 10, compressed=False))
    assert msg.sent == []
    assert ("edit", bot.TXT["bad_image"]) in msg.log


def test_too_big_is_rejected_before_download():
    msg = FakeMessage()
    asyncio.run(bot.handle_skin(msg, FakeBot(b""), "file", 30 * 1024 * 1024, compressed=False))
    assert msg.log and msg.log[0][0] == "reply"
