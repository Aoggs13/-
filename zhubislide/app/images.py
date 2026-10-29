"""Topic photos.

A slide about a specific person, place or event gets a photo of exactly that subject: its Wikipedia page
image (English, deck-language and Russian Wikipedia), then more photos of it from Wikimedia Commons.
Other slides get a stock-style photo: Pexels / Unsplash (if a key is set) → Openverse → the lead photo of the
best-matching English Wikipedia articles → Wikimedia Commons. When nothing is found, abstract art in the theme
colours is used.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import random
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from PIL import Image, ImageDraw, ImageFilter

log = logging.getLogger("zhubislide.images")
Image.MAX_IMAGE_PIXELS = 60_000_000

UA = {"User-Agent": "ZhubaiSlide/1.0 (presentation generator; https://zhubislide-production.up.railway.app)"}
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
UNSPLASH_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
MAX_BYTES = 12 * 1024 * 1024
MIN_SIDE = 400            # stock photos
MIN_SIDE_SUBJECT = 220    # a real photo of the subject is worth more than resolution (old portraits are small)


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


async def _commons(c: httpx.AsyncClient, q: str, subject: bool = False) -> list[str]:
    """Wikimedia Commons file search. For a subject any orientation and smaller files are fine."""
    r = await c.get("https://commons.wikimedia.org/w/api.php", headers=UA, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f"{q} filetype:bitmap", "gsrlimit": 10, "prop": "imageinfo",
        "iiprop": "url|size|mime", "iiurlwidth": 1600})
    r.raise_for_status()
    pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        w, h = ii.get("width", 0), ii.get("height", 1)
        if ii.get("mime") not in ("image/jpeg", "image/png"):
            continue
        if subject and min(w, h) >= MIN_SIDE_SUBJECT or not subject and w >= 1000 and w >= h * 0.9:
            out.append(ii.get("thumburl") or ii["url"])
    return out


async def _wiki_image(c: httpx.AsyncClient, lang: str, title: str) -> list[str]:
    """The main image of a Wikipedia article (exact title, else the best search hit)."""
    base = {"action": "query", "format": "json", "formatversion": 2, "redirects": 1, "prop": "pageimages",
            "piprop": "original|thumbnail", "pithumbsize": 1600}
    url = f"https://{lang}.wikipedia.org/w/api.php"
    r = await c.get(url, headers=UA, params={**base, "titles": title})
    r.raise_for_status()
    pages = r.json().get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing"):
        r = await c.get(url, headers=UA, params={**base, "generator": "search", "gsrsearch": title,
                                                 "gsrlimit": 1, "gsrnamespace": 0})
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", [])
    for p in pages[:1]:
        for u in ((p.get("thumbnail") or {}).get("source"), (p.get("original") or {}).get("source")):
            if u and ".svg" not in u.lower():
                return [u]                      # one picture per article: the thumbnail is the same file
    return []


async def _wiki_search(c: httpx.AsyncClient, q: str) -> list[str]:
    """Lead photos of the English Wikipedia articles that best match a stock query: always on topic, unlike a
    free-text file search. JPEG only — PNG/SVG lead images are maps, diagrams, flags and logos."""
    r = await c.get("https://en.wikipedia.org/w/api.php", headers=UA, params={
        "action": "query", "format": "json", "formatversion": 2, "generator": "search", "gsrsearch": q,
        "gsrlimit": 3, "gsrnamespace": 0, "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 1600})
    r.raise_for_status()
    pages = sorted(r.json().get("query", {}).get("pages", []), key=lambda p: p.get("index", 99))
    urls = [(p.get("thumbnail") or {}).get("source", "") for p in pages]
    return [u for u in urls if urlparse(u).path.lower().endswith((".jpg", ".jpeg"))]


def split_subject(subject: str) -> tuple[str, str]:
    """"English title | local title" → (english, local); a single name is used for both."""
    parts = [p.strip() for p in (subject or "").split("|")]
    en = parts[0] if parts else ""
    local = parts[1] if len(parts) > 1 and parts[1] else en
    return en, local


def _subject_sources(subject: str, lang: str):
    en, local = split_subject(subject)
    langs = [("en", en), (lang, local), ("ru", local)]
    for wl, title in dict.fromkeys((wl, t) for wl, t in langs if t):
        yield f"wikipedia:{wl}", (lambda c, wl=wl, title=title: _wiki_image(c, wl, title))
    for q in dict.fromkeys(q for q in (en, local) if q):
        yield "commons", (lambda c, q=q: _commons(c, q, subject=True))


def _stock_sources():
    if PEXELS_KEY:
        yield "pexels", _pexels
    if UNSPLASH_KEY:
        yield "unsplash", _unsplash
    yield "openverse", _openverse
    yield "wikipedia", _wiki_search
    yield "commons", _commons


def file_key(url: str) -> str:
    """Same picture, different URL (thumbnail sizes, original, tracking query) → one key, so no photo repeats."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if "thumb" in parts and len(parts) >= parts.index("thumb") + 4:
        name = parts[parts.index("thumb") + 3]
    else:
        name = parts[-1] if parts else url
    return unquote(name).lower()


async def _download(c: httpx.AsyncClient, url: str, min_side: int) -> Image.Image | None:
    try:
        r = await c.get(url, headers=UA, follow_redirects=True)
        if r.status_code != 200 or len(r.content) > MAX_BYTES:
            return None
        img = Image.open(io.BytesIO(r.content))
        img.load()
        if min(img.size) < min_side:
            return None
        return img.convert("RGB")
    except Exception:
        return None


async def find_photo(c: httpx.AsyncClient, query: str, used: set[str], subject: str = "",
                     lang: str = "kk", name: str = "") -> Image.Image | None:
    """First decent, not-yet-used photo: of the subject if one is named, else for the stock query."""
    attempts = []
    if subject.strip():
        attempts += [(src, fn, "", MIN_SIDE_SUBJECT) for src, fn in _subject_sources(subject, lang)]
    if query.strip():
        queries = [query] + ([" ".join(query.split()[:2])] if len(query.split()) > 2 else [])
        attempts += [(src, fn, q, MIN_SIDE) for q in queries for src, fn in _stock_sources()]
    for src, fn, q, min_side in attempts:
        try:
            urls = await (fn(c, q) if q else fn(c))
        except Exception as e:  # source down / rate limited → try the next one
            log.info("photo source %s failed for %r: %s %s", src, q or subject, type(e).__name__, e)
            continue
        for url in urls[:5]:
            key = file_key(url)
            if key in used:
                continue
            used.add(key)               # reserve before awaiting: parallel slides never share a photo
            img = await _download(c, url, min_side)
            if img is not None:
                log.info("photo %s from %s (%s): %s %dx%d", name, src, subject or q, url, *img.size)
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
        top = max(0, int((sh - nh) * 0.2))            # keep more of the top: faces, skylines
        img = img.crop((0, top, sw, top + nh))
    return img.resize((w, h), Image.LANCZOS)


class Fetcher:
    """Shared client + de-duplication for one deck, so photos can be fetched while text is still being written."""

    def __init__(self, out_dir: Path, lang: str = "kk", concurrency: int = 6) -> None:
        self.out_dir = out_dir
        self.lang = lang
        self.sem = asyncio.Semaphore(concurrency)
        self.used: set[str] = set()
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
        out_dir.mkdir(parents=True, exist_ok=True)

    async def get(self, name: str, query: str, colors: tuple[str, str, str], subject: str = "") -> Path:
        """Photo saved as out_dir/{name}.jpg; abstract art in the theme colours if none is found."""
        path = self.out_dir / f"{name}.jpg"
        img = None
        if query.strip() or subject.strip():
            async with self.sem:
                img = await find_photo(self.client, query, self.used, subject, self.lang, name)
        if img is None:
            img = gradient_art(query or subject or name, colors)
        img.thumbnail((1920, 1920))
        await asyncio.to_thread(img.save, path, "JPEG", quality=86, optimize=True)
        return path

    async def close(self) -> None:
        await self.client.aclose()
