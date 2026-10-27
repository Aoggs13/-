"""Bot handler end to end with a fake Telegram side (no network, no token)."""

import asyncio
import io
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EVOSKIN_NO_DOWNLOAD", "1")
os.environ["STATE_DIR"] = tempfile.mkdtemp(prefix="evoskin_state_")

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
        self.chat = SimpleNamespace(id=1)

        async def call(method, request_timeout=None):
            self.sent.append(method)

        self.bot = call

    async def answer(self, text):
        self.log.append(("answer", text))
        st = FakeStatus(self.log)
        st.message_id = len(self.log)
        return st

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
    assert msg.sent == [("photo", "frames.png"), ("document", "skin_frames.zip")]   # frames only, no GIFs
    assert ("delete",) in msg.log
    assert not list(bot.STATE_DIR.glob("*.json"))          # nothing left marked as running


def test_bad_file_is_reported():
    msg = FakeMessage()
    asyncio.run(bot.handle_skin(msg, FakeBot(b"garbage"), "file", 10, compressed=False))
    assert msg.sent == []
    assert ("edit", bot.TXT["bad_image"]) in msg.log


def test_too_big_is_rejected_before_download():
    msg = FakeMessage()
    asyncio.run(bot.handle_skin(msg, FakeBot(b""), "file", 30 * 1024 * 1024, compressed=False))
    assert msg.log and msg.log[0][0] == "reply"


def test_worker_crash_falls_back_and_reports(monkeypatch):
    calls = []

    async def fake_worker(data, lama):
        calls.append(lama)
        raise bot.JobFailed("worker exit -9")

    monkeypatch.setattr(bot, "run_worker", fake_worker)
    msg = FakeMessage()
    asyncio.run(bot.handle_skin(msg, FakeBot(b"x"), "file", 10, compressed=False))
    assert calls == [True, False]                          # retried without LaMa
    assert ("edit", bot.TXT["fail"]) in msg.log            # and the user is told, not left waiting


def test_lost_job_is_reported_after_restart():
    bot.STATE_DIR.mkdir(parents=True, exist_ok=True)
    (bot.STATE_DIR / "5_7.json").write_text('{"chat": 5, "status": 7}')
    edits = []

    class B:
        async def edit_message_text(self, text, chat_id, message_id):
            edits.append((text, chat_id, message_id))

    asyncio.run(bot.notify_lost_jobs(B()))
    assert edits == [(bot.TXT["lost"], 5, 7)]
    assert not (bot.STATE_DIR / "5_7.json").exists()

