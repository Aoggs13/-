"""Telegram bot: send a photo or a short video, get it back enhanced.

Photos: AI x4 super-resolution (Real-ESRGAN), face restoration (GPEN), crisp/vivid finish, 4K on the long side.
Videos: AI upscale on every frame + the same finish, then motion-compensated interpolation to 120 fps.

Env:  BOT_TOKEN (or TELEGRAM_BOT_TOKEN) is required and is read only from the environment.
      MAX_VIDEO_SECONDS (15), VIDEO_SHORT_SIDE (1080), MODELS_DIR, ORT_THREADS, LOG_LEVEL.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", str(50_000_000))   # refuse decompression bombs

import cv2  # noqa: E402
from aiogram import Bot, Dispatcher, F  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.exceptions import TelegramBadRequest, TelegramEntityTooLarge  # noqa: E402
from aiogram.filters import Command, CommandStart  # noqa: E402
from aiogram.types import BotCommand, FSInputFile, Message  # noqa: E402

from enhancer import models, photo, video  # noqa: E402

log = logging.getLogger("enhance_bot")

TG_DOWNLOAD_LIMIT = 20 * 1024 * 1024          # Bot API getFile limit
TG_UPLOAD_LIMIT = 50 * 1024 * 1024            # Bot API upload limit
MAX_VIDEO_SECONDS = float(os.environ.get("MAX_VIDEO_SECONDS", 15))
VIDEO_SHORT_SIDE = int(os.environ.get("VIDEO_SHORT_SIDE", 1080))
MAX_PER_USER = 5                              # an album of photos is queued, not rejected
UPLOAD_TIMEOUT = 600
_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")

TXT = {
    "start": ("Сәлем! Маған фото не қысқа видео жібер — сапасын көтеріп қайтарамын:\n"
              "• фото: бұлыңғырды кетіріп, 4K-ға дейін үлкейтемін, беттерді айқындаймын, түсін қанық қыламын;\n"
              "• видео: әр кадрды ИИ-мен айқындап, 120 FPS қыламын.\n\n"
              "Ең жақсы нәтиже үшін фотоны <b>файл</b> ретінде жібер (Telegram қысып тастамас үшін).\n"
              "Шектеу: файл ≤ 20 МБ, видео ≤ {sec} сек.\n\n"
              "Привет! Пришли фото или короткое видео — верну в высоком качестве (фото до 4K, видео 120 FPS)."),
    "queued": "⏳ Кезекте: {pos}. / В очереди: {pos}.",
    "too_big": ("Файл тым үлкен ({mb:.1f} МБ). Telegram боттарға 20 МБ-қа дейін ғана береді — "
                "қысқартып не сығып жібер.\nФайл больше 20 МБ — Telegram не отдаёт ботам такие файлы."),
    "too_long": "Видео {dur:.0f} сек. Қазір {sec:.0f} сек-қа дейін өңдеймін — қысқартып жібер.",
    "busy_user": "Сенің {n} файлың кезекте тұр — солар біткен соң жібер.",
    "bad_image": "Бұл суретті аша алмадым (JPG/PNG/WEBP жібер, ≤ 50 МП, пропорциясы 20:1-ден аспасын).",
    "restart": "Бот қайта іске қосылып жатыр — файлды қайта жібер.",
    "photo_work": "🔍 Фотоны өңдеп жатырмын (ИИ: айқындық + бет + түс)… ~1–2 мин",
    "video_work": "🎬 Видеоны өңдеп жатырмын… шамамен {eta}",
    "stage": {"upscale": "ИИ кадрларды айқындап жатыр", "interpolate": "120 FPS кадрлар қосылып жатыр",
              "encode": "Видео жиналып жатыр", "done": "Дайын"},
    "photo_done": "✅ Дайын: {w}×{h}. Файл — сығылмаған толық сапа.",
    "video_done": "✅ Дайын: {w}×{h}, {fps:.0f} FPS, {dur:.1f} сек.",
    "ba": "Бұрын / Кейін",
    "fail": "😔 Өңдеу кезінде қате шықты. Басқа файлмен қайталап көр.",
    "unsupported": "Фото не видео жібер.",
    "compressed": "💡 Кеңес: келесі жолы фотоны «Файл» ретінде жібер — сапасы әлдеқайда жақсы болады.",
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


def fmt_eta(sec: float) -> str:
    sec = int(max(5, sec))
    return f"{sec // 60} мин {sec % 60} сек" if sec >= 60 else f"{sec} сек"


class Worker:
    """One CPU-heavy job at a time (the models already use every core); everyone else waits in line."""

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


class Progress:
    """Thread-safe progress holder; an async loop turns it into status-message edits (throttled)."""

    def __init__(self, eta: float) -> None:
        self.stage, self.frac, self.t0, self.eta = "upscale", 0.0, time.time(), eta

    def __call__(self, stage: str, frac: float) -> None:
        self.stage, self.frac = stage, frac

    async def pump(self, status: Message, every: float = 6.0) -> None:
        last = ""
        while True:
            await asyncio.sleep(every)
            left = max(5.0, self.eta - (time.time() - self.t0))
            text = f"🎬 {TXT['stage'].get(self.stage, self.stage)}: {int(self.frac * 100)}% · ~{fmt_eta(left)} қалды"
            if text != last:
                with contextlib.suppress(Exception):
                    await status.edit_text(text)
                last = text


async def stop_pump(task: asyncio.Task | None) -> None:
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task


async def send_file(message: Message, path: Path, name: str, caption: str, as_video: dict | None = None) -> None:
    """Upload with a long timeout; fall back from video to document only if Telegram rejects the video."""
    if path.stat().st_size > TG_UPLOAD_LIMIT:
        raise RuntimeError("result exceeds the upload limit")
    if as_video is not None:
        try:
            await message.bot(message.answer_video(FSInputFile(path, name), caption=caption,
                                                   supports_streaming=True, **as_video),
                              request_timeout=UPLOAD_TIMEOUT)
            return
        except (TelegramBadRequest, TelegramEntityTooLarge):
            pass
    await message.bot(message.answer_document(FSInputFile(path, name), caption=caption),
                      request_timeout=UPLOAD_TIMEOUT)


worker = Worker()
dp = Dispatcher()


@dp.message(CommandStart())
@dp.message(Command("help"))
async def on_start(message: Message) -> None:
    await message.answer(TXT["start"].format(sec=int(MAX_VIDEO_SECONDS)))


def _read_image(path: Path):
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.dtype != "uint8":
        img = cv2.convertScaleAbs(img, alpha=255.0 / max(1, int(img.max())))
    h, w = img.shape[:2]
    if max(h, w) / max(1, min(h, w)) > 20:
        return None
    return img


def _save_photo(out, tmp: Path) -> Path:
    if out.ndim == 3 and out.shape[2] == 4:                      # keep transparency
        res = tmp / "enhanced_4k.png"
        cv2.imwrite(str(res), out, [cv2.IMWRITE_PNG_COMPRESSION, 6])
        return res
    res = tmp / "enhanced_4k.jpg"
    q = 95
    cv2.imwrite(str(res), out, [cv2.IMWRITE_JPEG_QUALITY, q])
    while res.stat().st_size > TG_UPLOAD_LIMIT - 1048576 and q > 60:
        q -= 8
        cv2.imwrite(str(res), out, [cv2.IMWRITE_JPEG_QUALITY, q])
    return res


def _preview(before, after, tmp: Path, height: int) -> Path:
    ba = tmp / "before_after.jpg"
    cv2.imwrite(str(ba), photo.before_after(before, after, height=height), [cv2.IMWRITE_JPEG_QUALITY, 88])
    return ba


async def handle_photo(message: Message, bot: Bot, file_id: str, size: int | None, compressed: bool) -> None:
    if size and size > TG_DOWNLOAD_LIMIT:
        await message.reply(TXT["too_big"].format(mb=size / 1048576))
        return

    async def job() -> None:
        tmp = Path(tempfile.mkdtemp(prefix="ph_"))
        status = None
        try:
            status = await message.answer(TXT["photo_work"])
            src = tmp / "in"
            await bot.download(file_id, destination=src, timeout=120)
            img = await asyncio.to_thread(_read_image, src)
            if img is None:
                await status.edit_text(TXT["bad_image"])
                return
            out = await asyncio.to_thread(photo.enhance_image, img)
            res = await asyncio.to_thread(_save_photo, out, tmp)
            await send_file(message, res, res.name, TXT["photo_done"].format(w=out.shape[1], h=out.shape[0]))
            with contextlib.suppress(Exception):                    # the preview must never cost the result
                ba = await asyncio.to_thread(_preview, img, out, tmp, 1600)
                await message.bot(message.answer_photo(FSInputFile(ba), caption=TXT["ba"]),
                                  request_timeout=UPLOAD_TIMEOUT)
            if compressed:
                await message.answer(TXT["compressed"])
            with contextlib.suppress(Exception):
                await status.delete()
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await message.answer(TXT["restart"])
            raise
        except Exception:
            log.exception("photo job failed")
            if status:
                with contextlib.suppress(Exception):
                    await status.edit_text(TXT["fail"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    await worker.run(message.from_user.id, message, job)


async def handle_video(message: Message, bot: Bot, file_id: str, size: int | None, duration: float | None) -> None:
    if size and size > TG_DOWNLOAD_LIMIT:
        await message.reply(TXT["too_big"].format(mb=size / 1048576))
        return
    if duration and duration > MAX_VIDEO_SECONDS + 0.5:
        await message.reply(TXT["too_long"].format(dur=duration, sec=MAX_VIDEO_SECONDS))
        return

    async def job() -> None:
        tmp = Path(tempfile.mkdtemp(prefix="vd_"))
        status, pump, stop = None, None, threading.Event()
        try:
            status = await message.answer("🎬 …")
            src = tmp / "in.mp4"
            await bot.download(file_id, destination=src, timeout=120)
            p = await asyncio.to_thread(video.probe, src)
            if p.duration > MAX_VIDEO_SECONDS + 0.5:
                await status.edit_text(TXT["too_long"].format(dur=p.duration, sec=MAX_VIDEO_SECONDS))
                return
            eta = video.eta_seconds(p, VIDEO_SHORT_SIDE)
            await status.edit_text(TXT["video_work"].format(eta=fmt_eta(eta)))
            prog = Progress(eta)
            pump = asyncio.create_task(prog.pump(status))
            dst = tmp / "enhanced_120fps.mp4"
            info = await asyncio.to_thread(video.enhance_video, src, dst, VIDEO_SHORT_SIDE, 120,
                                           TG_UPLOAD_LIMIT - 4 * 1048576, True, None, prog, MAX_VIDEO_SECONDS, stop)
            await stop_pump(pump)
            pump = None
            cap = TXT["video_done"].format(w=info.width, h=info.height, fps=info.fps, dur=info.duration)
            await send_file(message, dst, dst.name, cap,
                            as_video={"width": info.width, "height": info.height,
                                      "duration": int(round(info.duration))})
            with contextlib.suppress(Exception):
                t = min(info.duration / 2, max(0.0, info.duration - 0.2))
                before, after = await asyncio.gather(asyncio.to_thread(video.frame_at, src, t),
                                                     asyncio.to_thread(video.frame_at, dst, t))
                if before is not None and after is not None:
                    ba = await asyncio.to_thread(_preview, before, after, tmp, 1280)
                    await message.bot(message.answer_photo(FSInputFile(ba), caption=TXT["ba"]),
                                  request_timeout=UPLOAD_TIMEOUT)
            with contextlib.suppress(Exception):
                await status.delete()
        except asyncio.CancelledError:
            stop.set()
            with contextlib.suppress(Exception):
                await message.answer(TXT["restart"])
            raise
        except Exception:
            log.exception("video job failed")
            await stop_pump(pump)
            pump = None
            if status:
                with contextlib.suppress(Exception):
                    await status.edit_text(TXT["fail"])
        finally:
            stop.set()
            await stop_pump(pump)
            shutil.rmtree(tmp, ignore_errors=True)

    await worker.run(message.from_user.id, message, job)


@dp.message(F.photo)
async def on_photo(message: Message, bot: Bot) -> None:
    ph = message.photo[-1]
    await handle_photo(message, bot, ph.file_id, ph.file_size, compressed=True)


@dp.message(F.video | F.animation | F.video_note)
async def on_video(message: Message, bot: Bot) -> None:
    v = message.video or message.animation or message.video_note
    await handle_video(message, bot, v.file_id, v.file_size, getattr(v, "duration", None))


@dp.message(F.document)
async def on_document(message: Message, bot: Bot) -> None:
    d = message.document
    mime = (d.mime_type or "").lower()
    name = (d.file_name or "").lower()
    if (mime.startswith("image/") and "heic" not in mime and "heif" not in mime) or \
            name.endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")):
        await handle_photo(message, bot, d.file_id, d.file_size, compressed=False)
    elif mime.startswith("video/") or name.endswith((".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")):
        await handle_video(message, bot, d.file_id, d.file_size, None)
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
    log.info("loading models…")
    await asyncio.to_thread(models.warm, ("real_esrgan_x4", "clear_reality_x4", "gpen_bfr_512", "yoloface_8n"))
    bot = Bot(token, default=DefaultBotProperties(parse_mode="HTML", allow_sending_without_reply=True))
    await bot.set_my_commands([BotCommand(command="start", description="Бастау / Начать"),
                               BotCommand(command="help", description="Көмек / Помощь")])
    log.info("bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
