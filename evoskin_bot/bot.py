"""Telegram bot: send a reaper skin (standard pose), get idle / fly / attack frames posed like the black reaper.

Env:  BOT_TOKEN (or TELEGRAM_BOT_TOKEN) is required and is read only from the environment.
      MODELS_DIR (LaMa inpainting model is downloaded there on first start), LOG_LEVEL,
      EVOSKIN_LAMA=0 turns LaMa off for hosts with less than ~1 GB of RAM.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import sys

os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(50_000_000))   # refuse decompression bombs

from aiogram import Bot, Dispatcher, F  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.filters import Command, CommandStart  # noqa: E402
from aiogram.types import BotCommand, BufferedInputFile, Message  # noqa: E402

from evoskin import inpaint, pipeline  # noqa: E402

log = logging.getLogger("evoskin_bot")

TG_DOWNLOAD_LIMIT = 20 * 1024 * 1024          # Bot API getFile limit
UPLOAD_TIMEOUT = 300
MAX_PER_USER = 3
_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")

TXT = {
    "start": ("Сәлем! Маған reaper скинін жібер (black reaper сияқты стандарт қалыпта, орағы қолында) — "
              "black reaper-дегідей анимация кадрларын жасап беремін:\n"
              "• idle — 6 кадр\n• fly — 5 кадр\n• attack — 8 кадр\n\n"
              "Бас, дене (құйрығымен бірге), екі қол және орақ бөлек қозғалады; қол мен орақ ашқан жерлер "
              "скиннің өз түсімен толтырылады.\n"
              "Ең жақсы нәтиже үшін скинді <b>файл</b> ретінде жібер (мөлдір фонды PNG).\n\n"
              "Привет! Пришли скин жнеца в стандартной позе — верну кадры idle / fly / attack как у black reaper."),
    "queued": "⏳ Кезекте: {pos}. / В очереди: {pos}.",
    "work": "🎨 Скинді бөліктерге бөліп, 19 кадр жасап жатырмын… ~1 мин",
    "too_big": "Файл тым үлкен ({mb:.1f} МБ). 20 МБ-қа дейін жібер.",
    "busy_user": "Сенің {n} скиның кезекте тұр — солар біткен соң жібер.",
    "bad_image": "Бұл суретті аша алмадым (PNG/JPG/WEBP жібер).",
    "no_skull": ("⚠️ Скиннен бас сүйекті таба алмадым — кадрлар қисық шығуы мүмкін. "
                 "Скин black reaper сияқты стандарт қалыпта болуы керек."),
    "done": ("✅ Дайын: idle 6, fly 5, attack 8 кадр ({w}×{h}).\n"
             "ZIP ішінде: frames/ — мөлдір PNG кадрлар, layers/ — бөлек қабаттар, preview/ — GIF."),
    "fail": "😔 Өңдеу кезінде қате шықты. Басқа файлмен қайталап көр.",
    "restart": "Бот қайта іске қосылып жатыр — скинді қайта жібер.",
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


async def send_result(message: Message, res: pipeline.Result) -> None:
    w, h = res.frames[0][1].shape[1], res.frames[0][1].shape[0]
    await message.bot(message.answer_photo(BufferedInputFile(res.sheet, "frames.png")),
                      request_timeout=UPLOAD_TIMEOUT)
    for anim in ("idle", "fly", "attack"):
        await message.bot(message.answer_animation(BufferedInputFile(res.gifs[anim], f"{anim}.gif"), caption=anim),
                          request_timeout=UPLOAD_TIMEOUT)
    await message.bot(message.answer_document(BufferedInputFile(res.zip_bytes, "skin_frames.zip"),
                                              caption=TXT["done"].format(w=w, h=h)),
                      request_timeout=UPLOAD_TIMEOUT)


async def handle_skin(message: Message, bot: Bot, file_id: str, size: int | None, compressed: bool) -> None:
    if size and size > TG_DOWNLOAD_LIMIT:
        await message.reply(TXT["too_big"].format(mb=size / 1048576))
        return

    async def job() -> None:
        status = None
        try:
            status = await message.answer(TXT["work"])
            buf = await bot.download(file_id, timeout=120)
            data = buf.read()
            try:
                res = await asyncio.to_thread(pipeline.run, data)
            except ValueError:
                await status.edit_text(TXT["bad_image"])
                return
            if not res.info.get("skull_found", True):
                await message.answer(TXT["no_skull"])
            await send_result(message, res)
            if compressed:
                await message.answer(TXT["compressed"])
            log.info("skin done in %.1fs %s", res.seconds, res.info)
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
    await asyncio.to_thread(inpaint.warm)
    bot = Bot(token, default=DefaultBotProperties(parse_mode="HTML", allow_sending_without_reply=True))
    await bot.set_my_commands([BotCommand(command="start", description="Бастау / Начать"),
                               BotCommand(command="help", description="Көмек / Помощь")])
    log.info("bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
