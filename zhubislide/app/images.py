"""Topic photos: Pexels / Unsplash (if a key is set) → Openverse → Wikimedia Commons → generated gradient art."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import random
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger("zhubislide.images")
Image.MAX_IMAGE_PIXELS = 60_000_000

UA = {"User-Agent": "ZhubiSlide/1.0 (presentation generator; https://railway.app)"}
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
UNSPLASH_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
MAX_BYTES = 12 * 1024 * 1024


async def _pexels(c: httpx.AsyncClient, q: str) -> list[str]:
    r = await c.get("https://api.pexels.com/v1/search", headers={"Authorization": PEXELS_KEY},
                    params={"query": q, "per_page": 8, "orientation": "landscape"})
    r.raise_for_status()
    return [p["src"]["large2x"] for p in r.json().get("photos", [])]


async def _unsplash(c: httpx.AsyncClient, q: str) -> list[str]:
    r = await c.get("https://api.unsplash.com/search/photos", headers={"Authorization": f"Client-ID {UNSPLASH_KEY}"},
                    params={"query": q, "per_page": 8, "orientation": "landscape"})
    r.raise_for_status()
    return [p["urls"]["regular"] for p in r.json().get("results", [])]


async def _openverse(c: httpx.AsyncClient, q: str) -> list[str]:
    r = await c.get("https://api.openverse.org/v1/images/", headers=UA,
                    params={"q": q, "page_size": 10, "size": "large", "category": "photograph", "mature": "false"})
    r.raise_for_status()
    return [p["url"] for p in r.json().get("results", []) if (p.get("width") or 0) >= 1000]


async def _wikimedia(c: httpx.AsyncClient, q: str) -> list[str]:
    r = await c.get("https://commons.wikimedia.org/w/api.php", headers=UA, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{q} filetype:bitmap", "gsrlimit": 10, "prop": "imageinfo",
        "iiprop": "url|size|mime", "iiurlwidth": 1600})
    r.raise_for_status()
    pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        if ii.get("mime") in ("image/jpeg", "image/png") and ii.get("width", 0) >= 1000 \
                and ii.get("width", 0) >= ii.get("height", 1) * 0.9:
            out.append(ii.get("thumburl") or ii["url"])
    return out


def _providers():
    if PEXELS_KEY:
        yield _pexels
    if UNSPLASH_KEY:
        yield _unsplash
    yield _openverse
    yield _wikimedia


async def _download(c: httpx.AsyncClient, url: str) -> Image.Image | None:
    try:
        r = await c.get(url, headers=UA, follow_redirects=True)
        if r.status_code != 200 or len(r.content) > MAX_BYTES:
            return None
        img = Image.open(io.BytesIO(r.content))
        img.load()
        if min(img.size) < 400:
            return None
        return img.convert("RGB")
    except Exception:
        return None


async def find_photo(c: httpx.AsyncClient, query: str, used: set[str]) -> Image.Image | None:
    """First decent, not-yet-used photo for the query; shortens the query once if nothing is found."""
    queries = [query]
    words = query.split()
    if len(words) > 2:
        queries.append(" ".join(words[:2]))
    for q in queries:
        for provider in _providers():
            try:
                urls = await provider(c, q)
            except Exception as e:  # provider down / rate limited → try the next one
                log.info("image provider %s failed for %r: %s", provider.__name__, q, e)
                continue
            for url in urls[:5]:
                if url in used:
                    continue
                used.add(url)               # reserve before awaiting: parallel slides never share a photo
                img = await _download(c, url)
                if img is not None:
                    return img
    return None


def gradient_art(seed: str, colors: tuple[str, str, str], size=(1600, 1000)) -> Image.Image:
    """Abstract blurred-blob artwork in the theme colours: used when no photo was found."""
    rnd = random.Random(seed)
    w, h = size
    img = Image.new("RGB", size, "#" + colors[0])
    d = ImageDraw.Draw(img)
    for _ in range(7):
        r = rnd.randint(h // 4, h // 2)
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        d.ellipse([x - r, y - r, x + r, y + r], fill="#" + rnd.choice(colors[1:]))
    return img.filter(ImageFilter.GaussianBlur(120))


def fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """Centre-crop to the w:h aspect, then resize (never stretches)."""
    sw, sh = img.size
    target = w / h
    if sw / sh > target:
        nw = int(sh * target)
        img = img.crop(((sw - nw) // 2, 0, (sw - nw) // 2 + nw, sh))
    else:
        nh = int(sw / target)
        top = max(0, int((sh - nh) * 0.35))           # keep a bit more of the top (faces, skylines)
        img = img.crop((0, top, sw, top + nh))
    return img.resize((w, h), Image.LANCZOS)


class Fetcher:
    """Shared client + de-duplication for one deck, so photos can be fetched while text is still being written."""

    def __init__(self, out_dir: Path, concurrency: int = 6) -> None:
        self.out_dir = out_dir
        self.sem = asyncio.Semaphore(concurrency)
        self.used: set[str] = set()
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        out_dir.mkdir(parents=True, exist_ok=True)

    async def get(self, name: str, query: str, colors: tuple[str, str, str]) -> Path:
        """Photo for the query saved as out_dir/{name}.jpg; abstract art in the theme colours if none is found."""
        path = self.out_dir / f"{name}.jpg"
        async with self.sem:
            img = await find_photo(self.client, query, self.used) if query.strip() else None
        if img is None:
            img = gradient_art(query or name, colors)
        img.thumbnail((1920, 1920))
        await asyncio.to_thread(img.save, path, "JPEG", quality=86, optimize=True)
        return path

    async def close(self) -> None:
        await self.client.aclose()
