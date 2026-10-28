"""Generation jobs: queue, real progress, time estimates learned from finished jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import builder, content, images
from .themes import AUTO, FONTS, THEMES, resolve

log = logging.getLogger("zhubislide.jobs")

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
JOBS_DIR = DATA_DIR / "jobs"
STATS_FILE = DATA_DIR / "stats.json"
MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL", 3))
KEEP_DAYS = float(os.environ.get("KEEP_DAYS", 14))
MAX_VARIANTS = 4           # design/font variants of one deck kept on disk
PAGES = [5, 8, 10, 15, 20, 25]
BATCH_FIRST = 5.0          # seconds until a slide batch starts streaming

# starting guesses (measured once per AI provider: their speeds differ a lot), replaced by moving averages of
# real runs that are persisted on the volume
DEFAULT_STATS = {"outline_s": 14.0, "per_slide_medium": 5.0, "per_slide_long": 8.0, "per_slide_full": 12.0,
                 "img_tail": 3.0, "build_per_slide": 0.3, "runs": 0}
PROVIDER_DEFAULTS = {
    # gemini-3.6-flash, reasoning "low": outline ~7 s, a batch of 6 "long" slides ~18 s
    "gemini": {"outline_s": 9.0, "per_slide_medium": 2.5, "per_slide_long": 3.5, "per_slide_full": 5.0},
}

ID_RE = re.compile(r"^[a-f0-9]{32}$")


def load_stats() -> dict[str, dict]:
    try:
        data = json.loads(STATS_FILE.read_text())
        return {p: v for p, v in data.items() if isinstance(v, dict)}
    except Exception:
        return {}


_ALL_STATS = load_stats()


class _ProviderStats:
    """Timing stats of the AI provider currently in use."""

    @staticmethod
    def _d() -> dict:
        p = content.provider() or "none"
        d = _ALL_STATS.setdefault(p, {})
        for k, v in {**DEFAULT_STATS, **PROVIDER_DEFAULTS.get(p, {})}.items():
            d.setdefault(k, v)
        return d

    def __getitem__(self, k: str) -> float:
        return self._d()[k]

    def __setitem__(self, k: str, v: float) -> None:
        self._d()[k] = v

    def get(self, k: str, default=None):
        return self._d().get(k, default)


STATS = _ProviderStats()


def save_stats() -> None:
    try:
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATS_FILE.write_text(json.dumps(_ALL_STATS))
    except OSError:
        pass


def learn(key: str, value: float) -> None:
    if value > 0:
        STATS[key] = round(0.7 * STATS[key] + 0.3 * value, 3)


def _rounds(n: int) -> tuple[int, int]:
    """(parallel rounds, slides per batch) for n content slides."""
    size = content.batch_size()
    k = min(size, n)
    return math.ceil(math.ceil(n / size) / content.parallel()), k


def writing_estimate(n: int, density: str) -> float:
    rounds, k = _rounds(n)
    return rounds * (BATCH_FIRST + STATS.get(f"per_slide_{density}", STATS["per_slide_long"]) * k)


def estimate(pages: int, photos: bool, density: str = "long") -> dict:
    n = pages - 2
    text = STATS["outline_s"] + writing_estimate(n, density)
    img = STATS["img_tail"] if photos else 0.5
    design = STATS["build_per_slide"] * pages + 1
    return {"seconds": round(text + img + design),
            "parts": {"text": round(text), "images": round(img), "design": round(design)},
            "learned_from": STATS["runs"]}


@dataclass
class Job:
    id: str
    topic: str
    pages: int
    lang: str
    theme: str
    font: str
    tone: str
    density: str
    photos: bool
    notes: bool
    author: str
    extra: str
    created: float = field(default_factory=time.time)
    status: str = "queued"          # queued → outline → writing → images → design → done | error
    progress: float = 0.0
    slides_done: int = 0
    titles: list[str] = field(default_factory=list)
    images_done: int = 0
    images_total: int = 0
    started: float = 0.0
    finished: float = 0.0
    est_total: float = 0.0
    error: str = ""
    title: str = ""
    palette: dict = field(default_factory=dict)
    font_used: str = ""
    t_stage: float = 0.0

    @property
    def dir(self) -> Path:
        return JOBS_DIR / self.id

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "meta.json").write_text(json.dumps(asdict(self), ensure_ascii=False))

    def remaining(self) -> float:
        """Seconds left, re-estimated from the speed observed so far in this very job."""
        now = time.time()
        n = self.pages - 2
        stage_t = now - self.t_stage
        tail = STATS["img_tail"] if self.photos else 0.5
        design = STATS["build_per_slide"] * self.pages + 1
        writing = writing_estimate(n, self.density)
        if self.status == "queued":
            return self.est_total
        if self.status == "outline":
            return max(2.0, STATS["outline_s"] - stage_t) + writing + tail + design
        if self.status == "writing":
            planned = max(1.0, writing - stage_t)
            if self.slides_done:
                observed = stage_t * (n - self.slides_done) / self.slides_done
                w = min(1.0, self.slides_done / max(1.0, n * 0.5))
                planned = w * observed + (1 - w) * planned
            return max(1.0, planned) + tail + design
        if self.status == "images":
            return max(1.0, tail - stage_t) + design
        if self.status == "design":
            return max(1.0, design - stage_t)
        return 0.0

    def public(self, queue_pos: int = 0) -> dict:
        now = time.time()
        d = {k: getattr(self, k) for k in ("id", "topic", "pages", "lang", "theme", "font", "font_used", "status",
                                           "slides_done", "titles", "images_done", "images_total", "error",
                                           "title", "created", "photos", "tone", "density", "palette")}
        d["progress"] = round(self.progress, 1)
        d["elapsed"] = round((self.finished or now) - self.started, 1) if self.started else 0
        d["remaining"] = round(self.remaining())
        d["estimate"] = round(self.est_total)
        d["queue_pos"] = queue_pos
        return d


class Manager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.waiting: list[str] = []
        self.sem = asyncio.Semaphore(MAX_PARALLEL)
        self.tasks: set[asyncio.Task] = set()

    # ── persistence ──
    def load(self) -> None:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - KEEP_DAYS * 86400
        for d in JOBS_DIR.iterdir():
            try:
                job = Job(**json.loads((d / "meta.json").read_text()))
            except Exception:
                shutil.rmtree(d, ignore_errors=True)
                continue
            if job.created < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                continue
            if job.status not in ("done", "error"):      # interrupted by a restart
                job.status, job.error = "error", "restart"
                job.save()
            self.jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id) if ID_RE.match(job_id or "") else None

    def queue_pos(self, job_id: str) -> int:
        return self.waiting.index(job_id) + 1 if job_id in self.waiting else 0

    # ── lifecycle ──
    def submit(self, **params) -> Job:
        self.prune()
        job = Job(id=uuid.uuid4().hex, **params)
        job.est_total = estimate(job.pages, job.photos, job.density)["seconds"]
        job.started = time.time()
        job.save()
        self.jobs[job.id] = job
        self.waiting.append(job.id)
        task = asyncio.create_task(self._run(job))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    async def _run(self, job: Job) -> None:
        async with self.sem:
            self.waiting.remove(job.id)
            job.started = time.time()              # the countdown starts when the work starts
            try:
                await self._generate(job)
                job.status, job.progress = "done", 100.0
            except Exception as e:
                log.exception("job %s failed", job.id)
                job.status, job.error = "error", content.error_code(e)
            job.finished = time.time()
            job.save()

    async def _generate(self, job: Job) -> None:
        n = job.pages - 2

        # 1) outline: design + plan of every slide
        job.status, job.t_stage, job.progress = "outline", time.time(), 2
        plan = await content.outline(job.topic, job.pages, job.lang, job.tone, job.extra)
        plan["plan"] = plan["plan"][:n]
        n = len(plan["plan"])
        if not n:
            raise RuntimeError("empty outline")
        learn("outline_s", time.time() - job.t_stage)
        theme = resolve(job.theme, plan)
        job.title = plan["title"]
        job.titles = [p["title"] for p in plan["plan"]]
        job.palette = {k: theme[k] for k in ("bg", "accent", "accent2", "dark", "surface", "text", "muted")}
        job.font_used = builder.pick_font(job.font, plan)
        colors = (theme["bg"][0], theme["accent"], theme["accent2"])

        # 2) full text in parallel batches; photos start downloading as soon as their slide is written
        fetcher = images.Fetcher(job.dir / "img")
        img_tasks: dict[str, asyncio.Task] = {}
        job.images_total = 1 + sum(1 for p in plan["plan"] if p["layout"] in builder.IMAGE_LAYOUTS)

        def fetch(name: str, query: str) -> None:
            async def go() -> Path:
                path = await fetcher.get(name, query if job.photos else "", colors)
                job.images_done += 1
                return path
            img_tasks[name] = asyncio.create_task(go())

        fetch("cover", plan.get("cover_image_query") or job.topic)
        job.status, job.t_stage, job.progress = "writing", time.time(), 10

        async def on_progress(done: int) -> None:
            job.slides_done = min(done, n)
            job.progress = 10 + 75 * job.slides_done / n

        async def on_batch(idxs: list[int], slides: list[dict]) -> None:
            for i, s in zip(idxs, slides):
                if builder.needs_image(s):
                    fetch(str(i), s.get("image_query") or s["title"])

        try:
            slides = await content.write_slides(job.topic, job.lang, job.tone, job.density, job.extra, job.notes,
                                                plan, on_progress, on_batch)
            rounds, k = _rounds(n)
            learn(f"per_slide_{job.density}", ((time.time() - job.t_stage) / rounds - BATCH_FIRST) / k)
            deck = {key: plan[key] for key in ("design", "title", "subtitle", "cover_image_query", "thanks")}
            deck["slides"] = slides
            (job.dir / "deck.json").write_text(json.dumps(deck, ensure_ascii=False))

            # 3) wait for the photos that are still downloading
            job.status, job.t_stage, job.progress = "images", time.time(), 85
            job.images_total = len(img_tasks)
            paths = dict(zip(img_tasks.keys(), await asyncio.gather(*img_tasks.values())))
            if job.photos:
                learn("img_tail", time.time() - job.t_stage)
        finally:
            for task in img_tasks.values():
                task.cancel()
            await fetcher.close()

        # 4) design
        job.status, job.t_stage, job.progress = "design", time.time(), 93
        out = self.pptx_path(job, job.theme, job.font)
        await asyncio.to_thread(builder.build, deck, job.theme, paths, out, job.author, job.font)
        learn("build_per_slide", (time.time() - job.t_stage) / job.pages)
        STATS["runs"] += 1
        save_stats()

    @staticmethod
    def pptx_path(job: Job, theme: str, font: str) -> Path:
        return job.dir / f"deck_{theme}_{font.replace(' ', '_')}.pptx"

    def pptx(self, job: Job, theme: str, font: str) -> Path:
        """PPTX in any theme/font: the text and photos are reused, only the design is rebuilt."""
        theme = theme if (theme in THEMES or theme == AUTO) else job.theme
        font = font if (font in FONTS or font == AUTO) else job.font
        out = self.pptx_path(job, theme, font)
        if not out.exists():
            deck = json.loads((job.dir / "deck.json").read_text())
            paths = {p.stem: p for p in (job.dir / "img").glob("*.jpg") if "_" not in p.stem}
            tmp = out.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
            builder.build(deck, theme, paths, tmp, job.author, font)
            tmp.replace(out)
            # keep the disk bounded: only the most recent design variants of a deck are kept
            variants = sorted(job.dir.glob("deck_*.pptx"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in variants[MAX_VARIANTS:]:
                if old != out:
                    old.unlink(missing_ok=True)
        return out

    def prune(self) -> None:
        """Forget and delete decks older than KEEP_DAYS."""
        cutoff = time.time() - KEEP_DAYS * 86400
        for job_id, job in list(self.jobs.items()):
            if job.created < cutoff and job.status in ("done", "error"):
                self.jobs.pop(job_id, None)
                shutil.rmtree(job.dir, ignore_errors=True)
