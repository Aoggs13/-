"""ZhubiSlide web app: FastAPI API + static single-page site."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import builder, content, jobs
from .themes import AUTO, FONTS, THEMES, resolve

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("zhubislide")

STATIC = Path(__file__).resolve().parent.parent / "static"
RATE_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", 12))
DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", 300))

manager = jobs.Manager()
_hits: dict[str, deque] = defaultdict(deque)
_daily: deque = deque()


@asynccontextmanager
async def lifespan(_: FastAPI):
    manager.load()
    log.info("ZhubiSlide started: provider=%s, data=%s", content.provider() or "NONE (no API key)", jobs.DATA_DIR)
    check = asyncio.create_task(content.self_check())
    yield
    check.cancel()


app = FastAPI(title="ZhubiSlide", docs_url=None, redoc_url=None, lifespan=lifespan)


class NewJob(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    pages: int
    lang: str = "kk"
    theme: str = AUTO
    font: str = AUTO
    tone: str = "student"
    density: str = "long"
    photos: bool = True
    notes: bool = True
    author: str = Field("", max_length=80)
    extra: str = Field("", max_length=500)


def client_ip(req: Request) -> str:
    # Railway's edge proxy sets X-Real-IP / appends the real client to X-Forwarded-For
    real = req.headers.get("x-real-ip", "").strip()
    if real:
        return real
    fwd = [p.strip() for p in req.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    return fwd[-1] if fwd else (req.client.host if req.client else "?")


def _allow(q: deque, limit: int, window: float) -> bool:
    now = time.time()
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def rate_ok(ip: str) -> bool:
    """Per-IP hourly limit plus a global daily cap that protects the API bill."""
    if len(_daily) >= DAILY_LIMIT and _daily[0] >= time.time() - 86400:
        return False
    if not _allow(_hits[ip], RATE_PER_HOUR, 3600):
        return False
    return _allow(_daily, DAILY_LIMIT, 86400)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/api/meta")
async def meta():
    return {
        "themes": THEMES,
        "fonts": {name: f["css"] for name, f in FONTS.items()},
        "pages": jobs.PAGES,
        # seconds for every (pages, density, photos) combination, so the page shows the time instantly
        "estimates": {d: {p: {"1": jobs.estimate(p, True, d), "0": jobs.estimate(p, False, d)}
                          for p in jobs.PAGES} for d in content.DENSITY},
        "ready": bool(content.provider()),
        "ai": {k: content.STATUS[k] for k in ("provider", "ok", "error")},
        "learned_from": jobs.STATS["runs"],
    }


@app.get("/api/estimate")
async def estimate(pages: int, photos: bool = True, density: str = "long"):
    if pages not in jobs.PAGES or density not in content.DENSITY:
        raise HTTPException(400, "bad_params")
    return jobs.estimate(pages, photos, density)


@app.post("/api/jobs")
async def create_job(body: NewJob, request: Request):
    if body.pages not in jobs.PAGES or body.lang not in ("kk", "ru") or (body.theme not in THEMES and body.theme != AUTO) \
            or (body.font not in FONTS and body.font != AUTO) \
            or body.tone not in content.TONES or body.density not in content.DENSITY:
        raise HTTPException(400, "bad_params")
    if not content.provider():
        raise HTTPException(503, "not_configured")
    if not rate_ok(client_ip(request)):
        raise HTTPException(429, "rate_limit")
    clean = {k: (re.sub(r"\s+", " ", v).strip() if isinstance(v, str) else v) for k, v in body.model_dump().items()}
    job = manager.submit(**clean)
    return job.public(manager.queue_pos(job.id))


def _job(job_id: str) -> jobs.Job:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "not_found")
    return job


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    job = _job(job_id)
    return job.public(manager.queue_pos(job.id))


@app.get("/api/jobs/{job_id}/deck")
async def job_deck(job_id: str):
    job = _job(job_id)
    f = job.dir / "deck.json"
    if not f.exists():
        raise HTTPException(404, "not_ready")
    imgs = sorted(p.stem for p in (job.dir / "img").glob("*.jpg") if "_" not in p.stem) \
        if (job.dir / "img").exists() else []
    deck = json.loads(f.read_text())
    return {"deck": deck, "images": imgs, "theme": job.theme, "font": job.font, "author": job.author,
            "auto_theme": resolve(AUTO, deck), "auto_font": builder.pick_font(AUTO, deck)}


@app.get("/api/jobs/{job_id}/img/{name}")
async def job_image(job_id: str, name: str):
    job = _job(job_id)
    if not re.fullmatch(r"cover|\d{1,2}", name):
        raise HTTPException(404)
    f = job.dir / "img" / f"{name}.jpg"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/jobs/{job_id}/download")
async def job_download(job_id: str, theme: str | None = None, font: str | None = None):
    job = _job(job_id)
    if job.status != "done":
        raise HTTPException(409, "not_ready")
    path = await asyncio.to_thread(manager.pptx, job, theme or job.theme, font or job.font)
    name = re.sub(r"[\\/:*?\"<>|\n\r]+", " ", job.title or job.topic).strip()[:80] or "ZhubiSlide"
    return FileResponse(
        path, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f"attachment; filename=\"ZhubiSlide.pptx\"; "
                                        f"filename*=UTF-8''{quote(name + '.pptx')}"})


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
