"""Telegram bot: send a reaper skin (standard pose), get idle / fly / attack frames posed like the black reaper.

Env:  BOT_TOKEN (or TELEGRAM_BOT_TOKEN) is required and is read only from the environment.
      MODELS_DIR (LaMa inpainting model is downloaded there on first start), LOG_LEVEL,
      EVOSKIN_THREADS (2) CPU threads per job, JOB_TIMEOUT (480 s), STATE_DIR (/data/state).

Every job runs in its own process (python -m evoskin.worker): when it runs out of memory or
time it is retried once without LaMa, and the bot itself never goes down with it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(50_000_000))   # refuse decompression bombs

from aiogram import Bot, Dispatcher, F  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.filters import Command, CommandStart  # noqa: E402
from aiogram.types import BotCommand, BufferedInputFile, Message  # noqa: E402

from evoskin import inpaint  # noqa: E402

log = logging.getLogger("evoskin_bot")

TG_DOWNLOAD_LIMIT = 20 * 1024 * 1024          # Bot API getFile limit
UPLOAD_TIMEOUT = 300
MAX_PER_USER = 3
JOB_TIMEOUT = float(os.environ.get("JOB_TIMEOUT", 480))
STATE_DIR = Path(os.environ.get("STATE_DIR", "/data/state"))
ROOT = Path(__file__).resolve().parent
_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")

TXT = {
    "start": ("Сәлем! Маған reaper скинін жібер (black reaper сияқты стандарт қалыпта, орағы қолында) — "
              "black reaper-дегідей кадрларын жасап беремін:\n"
              "• idle — 6 кадр\n• fly — 5 кадр\n• attack — 8 кадр\n\n"
              "Бас, дене (құйрығымен бірге), екі қол және орақ бөлек қозғалады; қол мен орақ ашқан жерлер "
              "скиннің өз түсімен толтырылады.\n"
              "Ең жақсы нәтиже үшін скинді <b>файл</b> ретінде жібер (мөлдір фонды PNG).\n\n"
              "Привет! Пришли скин жнеца в стандартной позе — верну кадры idle / fly / attack как у black reaper."),
    "queued": "⏳ Кезекте: {pos}. / В очереди: {pos}.",
    "work": "🎨 Скинді бөліктерге бөліп, 19 кадр жасап жатырмын… ~1–2 мин",
    "too_big": "Файл тым үлкен ({mb:.1f} МБ). 20 МБ-қа дейін жібер.",
    "busy_user": "Сенің {n} скиның кезекте тұр — солар біткен соң жібер.",
    "bad_image": "Бұл суретті аша алмадым (PNG/JPG/WEBP жібер).",
    "no_skull": ("⚠️ Скиннен бас сүйекті таба алмадым — кадрлар қисық шығуы мүмкін. "
                 "Скин black reaper сияқты стандарт қалыпта болуы керек."),
    "done": ("✅ Дайын: idle 6, fly 5, attack 8 кадр ({w}×{h}).\n"
             "ZIP ішінде: frames/ — мөлдір PNG кадрлар, layers/ — бөлек қабаттар."),
    "fail": "😔 Өңдеу кезінде қате шықты. Басқа файлмен қайталап көр.",
    "slow": "⏳ Жады жетпеді — жеңіл режимде қайталап жатырмын…",
    "restart": "Бот қайта іске қосылып жатыр — скинді қайта жібер.",
    "lost": "Бот қайта іске қосылды, бұл скин өңделмей қалды — қайта жібер.",
    "unsupported": "Скин суретін жібер (PNG файл ретінде жақсырақ).",
    "compressed": "💡 Келесі жолы скинді «Файл» ретінде жібер — Telegram фотоны сығып, шеттерін бұзады.",
}


class RedactingFilter(logging.Filter):
    """Bot API URLs contain the token: make sure it can never reach the logs."""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self.secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        if self.secret:
            msg = msg.replace(self.secret, "***")
        record.msg, record.args = _TOKEN_RE.sub("***:***", msg), ()
        if record.exc_info:
            text = logging.Formatter().formatException(record.exc_info)
            record.exc_text = _TOKEN_RE.sub("***:***", text.replace(self.secret, "***") if self.secret else text)
            record.exc_info = None
        return True


class Worker:
    """One CPU-heavy job at a time; everyone else waits in line."""

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.waiting = 0
        self.per_user: dict[int, int] = {}

    async def run(self, user_id: int, message: Message, job) -> None:
        n = self.per_user.get(user_id, 0)
        if n >= MAX_PER_USER:
            await message.reply(TXT["busy_user"].format(n=n))
            return
        self.per_user[user_id] = n + 1
        queued = self.lock.locked()
        try:
            if queued:
                self.waiting += 1
                await message.reply(TXT["queued"].format(pos=self.waiting))
            async with self.lock:
                if queued:
                    self.waiting -= 1
                    queued = False
                await job()
        finally:
            if queued:
                self.waiting -= 1
            left = self.per_user.get(user_id, 1) - 1
            if left > 0:
                self.per_user[user_id] = left
            else:
                self.per_user.pop(user_id, None)


worker = Worker()
dp = Dispatcher()


@dp.message(CommandStart())
@dp.message(Command("help"))
async def on_start(message: Message) -> None:
    await message.answer(TXT["start"])


class JobFailed(Exception):
    pass


async def run_worker(data: bytes, lama: bool) -> dict:
    """Run the pipeline in a child process; returns the output files as bytes."""
    tmp = Path(tempfile.mkdtemp(prefix="skin_"))
    try:
        src = tmp / "in.bin"
        src.write_bytes(data)
        env = dict(os.environ, EVOSKIN_LAMA="1" if lama else "0")
        proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "evoskin.worker", str(src), str(tmp / "out"),
                                                    cwd=str(ROOT), env=env)
        try:
            rc = await asyncio.wait_for(proc.wait(), timeout=JOB_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise JobFailed("timeout")
        if rc == 3:
            raise ValueError("not an image")
        if rc != 0:
            raise JobFailed(f"worker exit {rc}")
        out = tmp / "out"
        return dict(zip=(out / "frames.zip").read_bytes(), sheet=(out / "sheet.png").read_bytes(),
                    info=json.loads((out / "info.json").read_text()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _pending_path(message: Message, status: Message) -> Path:
    return STATE_DIR / f"{message.chat.id}_{status.message_id}.json"


def mark_pending(message: Message, status: Message) -> Path | None:
    with contextlib.suppress(Exception):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p = _pending_path(message, status)
        p.write_text(json.dumps({"chat": message.chat.id, "status": status.message_id}))
        return p
    return None


async def notify_lost_jobs(bot: Bot) -> None:
    """Jobs that were running when the container restarted get an honest message."""
    if not STATE_DIR.exists():
        return
    for p in STATE_DIR.glob("*.json"):
        with contextlib.suppress(Exception):
            d = json.loads(p.read_text())
            with contextlib.suppress(Exception):
                await bot.edit_message_text(TXT["lost"], chat_id=d["chat"], message_id=d["status"])
        with contextlib.suppress(Exception):
            p.unlink()


async def send_result(message: Message, res: dict) -> None:
    info = res["info"]
    await message.bot(message.answer_photo(BufferedInputFile(res["sheet"], "frames.png")),
                      request_timeout=UPLOAD_TIMEOUT)
    await message.bot(message.answer_document(BufferedInputFile(res["zip"], "skin_frames.zip"),
                                              caption=TXT["done"].format(w=info["width"], h=info["height"])),
                      request_timeout=UPLOAD_TIMEOUT)


async def handle_skin(message: Message, bot: Bot, file_id: str, size: int | None, compressed: bool) -> None:
    if size and size > TG_DOWNLOAD_LIMIT:
        await message.reply(TXT["too_big"].format(mb=size / 1048576))
        return

    async def job() -> None:
        status = None
        pending = None
        try:
            status = await message.answer(TXT["work"])
            pending = mark_pending(message, status)
            buf = await bot.download(file_id, timeout=120)
            data = buf.read()
            try:
                try:
                    res = await run_worker(data, lama=True)
                except JobFailed as e:
                    log.warning("job failed (%s), retrying without LaMa", e)
                    with contextlib.suppress(Exception):
                        await status.edit_text(TXT["slow"])
                    res = await run_worker(data, lama=False)
            except ValueError:
                await status.edit_text(TXT["bad_image"])
                return
            if not res["info"].get("skull_found", True):
                await message.answer(TXT["no_skull"])
            await send_result(message, res)
            if compressed:
                await message.answer(TXT["compressed"])
            log.info("skin done %s", res["info"])
            with contextlib.suppress(Exception):
                await status.delete()
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await message.answer(TXT["restart"])
            raise
        except Exception:
            log.exception("skin job failed")
            if status:
                with contextlib.suppress(Exception):
                    await status.edit_text(TXT["fail"])
        finally:
            if pending is not None:
                with contextlib.suppress(Exception):
                    pending.unlink()

    await worker.run(message.from_user.id, message, job)


@dp.message(F.photo)
async def on_photo(message: Message, bot: Bot) -> None:
    ph = message.photo[-1]
    await handle_skin(message, bot, ph.file_id, ph.file_size, compressed=True)


@dp.message(F.document)
async def on_document(message: Message, bot: Bot) -> None:
    d = message.document
    mime = (d.mime_type or "").lower()
    name = (d.file_name or "").lower()
    if mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")):
        await handle_skin(message, bot, d.file_id, d.file_size, compressed=False)
    else:
        await message.reply(TXT["unsupported"])


@dp.message()
async def on_other(message: Message) -> None:
    await message.reply(TXT["unsupported"])


async def main() -> None:
    token = os.environ.pop("BOT_TOKEN", "") or os.environ.pop("TELEGRAM_BOT_TOKEN", "")   # children never inherit it
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RedactingFilter(token))
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), handlers=[handler],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not token:
        log.error("BOT_TOKEN is not set")
        sys.exit(2)
    log.info("preparing models…")
    await asyncio.to_thread(inpaint.ensure_model)      # download only; jobs load it in their own process
    bot = Bot(token, default=DefaultBotProperties(parse_mode="HTML", allow_sending_without_reply=True))
    await notify_lost_jobs(bot)
    await bot.set_my_commands([BotCommand(command="start", description="Бастау / Начать"),
                               BotCommand(command="help", description="Көмек / Помощь")])
    log.info("bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
