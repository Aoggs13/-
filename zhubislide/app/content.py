"""Slide text generation with Claude or OpenAI (whichever key is configured).

Two phases so that long, detailed decks are still fast:
1. outline  — design palette, title, and a plan (layout + title + focus) for every slide;
2. slides   — the full text, written in parallel batches that all see the whole outline.
Both are streamed, so progress shown to the user is real, not simulated.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Awaitable, Callable

import anthropic
import openai

from .themes import FONTS

log = logging.getLogger("zhubislide.content")

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("CLAUDE_EFFORT", "low")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "")      # empty: best model the key can use, picked at runtime
OPENAI_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "low")
BATCH = int(os.environ.get("SLIDES_PER_BATCH", 4))
PARALLEL = int(os.environ.get("BATCHES_PARALLEL", 4))

LAYOUTS = ["image_right", "image_left", "article", "cards", "stats", "quote", "two_column", "timeline"]

_STR = {"type": "string"}
_STRS = {"type": "array", "items": _STR}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


DESIGN = _obj({
    "mood": _STR,
    "dark": {"type": "boolean"},
    "bg1": _STR, "bg2": _STR, "accent": _STR, "accent2": _STR,
    "pattern": {"type": "string", "enum": ["blobs", "geometric", "lines", "dots"]},
    "font": {"type": "string", "enum": list(FONTS)},
})

OUTLINE_SCHEMA = _obj({
    "design": DESIGN,
    "title": _STR,
    "subtitle": _STR,
    "cover_image_query": _STR,
    "thanks": _STR,
    "plan": {"type": "array", "items": _obj({
        "layout": {"type": "string", "enum": LAYOUTS},
        "title": _STR,
        "focus": _STR,
    })},
})

SLIDE = _obj({
    "title": _STR,
    "lead": _STR,
    "bullets": _STRS,
    "left_title": _STR,
    "right_title": _STR,
    "right_bullets": _STRS,
    "quote": _STR,
    "quote_author": _STR,
    "stats": {"type": "array", "items": _obj({"value": _STR, "label": _STR})},
    "image_query": _STR,
    "notes": _STR,
})
SLIDES_SCHEMA = _obj({"slides": {"type": "array", "items": SLIDE}})

LANG_NAME = {"kk": "Kazakh (Cyrillic script, literary қазақ тілі)", "ru": "Russian"}
TONES = {
    "school": "for school students: simple words, vivid everyday examples, every term explained",
    "student": "for university students: clear structure, terms explained, examples and facts",
    "business": "business style: precise, practical, numbers and results",
    "science": "academic style: precise terminology, mechanisms, causes and consequences",
    "creative": "creative and inspiring: storytelling, vivid images, still informative",
}
DENSITY = {
    "medium": "lead: 1 sentence (12-20 words). bullets: 4, each one complete sentence of 10-16 words.",
    "long": ("lead: 1-2 sentences (20-30 words) that explain the main idea of the slide. bullets: 4, each 1-2 "
             "complete sentences (15-25 words) — a statement plus an explanation, example or fact."),
    "full": ("lead: 2 sentences (30-45 words). bullets: 5, each 2 complete sentences (20-30 words): what it "
             "is and why it matters, with a concrete example or fact. The slide must be full and "
             "self-explanatory, like a page of a good textbook."),
}

SYSTEM = """You are a top presentation author and subject expert. You write decks that a person can read and
understand without a speaker: complete, clear sentences (never telegraphic fragments of 2-3 words), logical
storyline, accurate facts, concrete examples. Never invent statistics, dates or quotes: use only
well-established facts; if unsure, write a qualitative statement instead. All visible text is in the requested
language. image_query fields are short ENGLISH stock-photo search phrases (2-4 concrete nouns, e.g.
"kazakh steppe horses", "solar panels field") that match the slide and the overall topic."""

LAYOUT_GUIDE = """Layouts:
- image_right / image_left: text + a photo. Use for about half of the slides, alternate sides.
- article: a text-rich slide without a photo (lead + detailed bullets) — for explanations and definitions.
- cards: 3-4 parallel ideas (types, reasons, principles).
- stats: 3-4 key numbers that are well-established facts.
- quote: one real, well-known quote related to the topic (at most once per deck).
- two_column: comparison (pros/cons, before/after, two kinds).
- timeline: 4-5 stages or dates in order.
Use at least 3 different layouts when there are 5+ slides; never the same layout 3 times in a row."""


PROVIDERS = ("anthropic", "openai", "gemini")
_KEYS = {"anthropic": ("ANTHROPIC_API_KEY",), "openai": ("OPENAI_API_KEY",),
         "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"   # Gemini's OpenAI-compatible API
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "")


def _key(p: str) -> str:
    return next((os.environ[k] for k in _KEYS[p] if os.environ.get(k)), "")


def configured() -> list[str]:
    """Providers that have an API key, AI_PROVIDER first."""
    order = list(PROVIDERS)
    pref = os.environ.get("AI_PROVIDER", "").strip().lower()
    if pref in order:
        order.remove(pref)
        order.insert(0, pref)
    return [p for p in order if _key(p)]


_active = ""   # set by self_check(): the first provider whose key and balance actually work


def provider() -> str:
    """Provider used for generation ("" when no key is set)."""
    if _active:
        return _active
    found = configured()
    return found[0] if found else ""


def batch_size() -> int:
    # Gemini's free tier allows few requests per minute: fewer, bigger requests
    return max(BATCH, 6) if provider() == "gemini" else BATCH


def parallel() -> int:
    return min(PARALLEL, 2) if provider() == "gemini" else PARALLEL


# result of the startup check, shown by /api/meta so the page can explain a missing key or empty balance
STATUS: dict = {"provider": "", "model": "", "ok": None, "error": ""}


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(max_retries=3)


def _openai_client(p: str = "openai") -> openai.AsyncOpenAI:
    if p == "gemini":
        return openai.AsyncOpenAI(api_key=_key("gemini"), base_url=GEMINI_BASE, max_retries=3)
    return openai.AsyncOpenAI(max_retries=3)


_GPT = re.compile(r"^gpt-(\d+)(?:\.(\d+))?$")
_GEMINI_FLASH = re.compile(r"^gemini-(\d+)(?:\.(\d+))?-flash$")
_models: dict[str, str] = {}
_model_lock = asyncio.Lock()


def _newest(ids: set[str], pattern: re.Pattern) -> list[str]:
    return sorted((m for m in ids if pattern.match(m)),
                  key=lambda m: tuple(int(x or 0) for x in pattern.match(m).groups()), reverse=True)


async def model_for(p: str) -> str:
    """Env override, or the newest suitable model the key can use: flagship gpt-N.M / gemini-N.M-flash."""
    override = OPENAI_MODEL if p == "openai" else GEMINI_MODEL
    if override:
        return override
    async with _model_lock:
        if p not in _models:
            ids = {m.id.removeprefix("models/") async for m in _openai_client(p).models.list()}
            if p == "openai":
                found = _newest(ids, _GPT) + [m for m in ("gpt-4o", "gpt-4o-mini") if m in ids] + ["gpt-4o-mini"]
            else:
                found = _newest(ids, _GEMINI_FLASH) + ["gemini-2.5-flash"]
            _models[p] = found[0]
            log.info("%s model: %s", p, _models[p])
    return _models[p]


def _reasoning(model: str) -> bool:
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


def _plain_schema(schema):
    """Gemini's JSON-schema support is narrower: drop additionalProperties (every field is required anyway)."""
    if isinstance(schema, dict):
        return {k: _plain_schema(v) for k, v in schema.items() if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_plain_schema(v) for v in schema]
    return schema


def _oa_params(p: str, model: str, max_tokens: int) -> dict:
    if p == "gemini":
        return {"max_tokens": max_tokens}
    extra = {"reasoning_effort": OPENAI_EFFORT} if _reasoning(model) else {}
    return {"max_completion_tokens": max_tokens, **extra}


async def _stream_openai(p: str, system: str, prompt: str, schema: dict,
                         on_text: Callable[[str], Awaitable[None]] | None, max_tokens: int) -> dict:
    model = await model_for(p)
    fmt = {"name": "deck", "schema": _plain_schema(schema) if p == "gemini" else schema, "strict": True}
    stream = await _openai_client(p).chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        response_format={"type": "json_schema", "json_schema": fmt},
        stream=True,
        **_oa_params(p, model, max_tokens),
    )
    text, finish = "", None
    async for chunk in stream:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        if getattr(choice.delta, "refusal", None):
            raise RuntimeError("refusal")
        if choice.delta.content:
            text += choice.delta.content
            if on_text:
                await on_text(text)
        finish = choice.finish_reason or finish
    if finish == "content_filter":
        raise RuntimeError("refusal")
    if finish == "length":
        raise RuntimeError("too long")
    return json.loads(text)


async def _stream_json(system: str, prompt: str, schema: dict, on_text: Callable[[str], Awaitable[None]] | None,
                       max_tokens: int) -> dict:
    p = provider()
    if p in ("openai", "gemini"):
        return await _stream_openai(p, system, prompt, schema, on_text, max_tokens)
    text = ""
    async with _client().beta.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        async for chunk in stream.text_stream:
            text += chunk
            if on_text:
                await on_text(text)
        final = await stream.get_final_message()
    if final.stop_reason == "refusal":
        raise RuntimeError("refusal")
    if final.stop_reason == "max_tokens":
        raise RuntimeError("too long")
    # after a server-side fallback the declined attempt may precede the answer: the last text block is it
    return json.loads([b.text for b in final.content if b.type == "text"][-1])


def error_code(e: Exception) -> str:
    """Short code for the page; the same codes for both providers."""
    msg = f"{e} {getattr(e, 'code', '')} {getattr(e, 'body', '')}".lower()
    if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError,
                      openai.AuthenticationError, openai.PermissionDeniedError)):
        return "auth"
    if any(k in msg for k in ("insufficient_quota", "exceeded your current quota", "credit balance")):
        return "quota"
    if isinstance(e, (anthropic.RateLimitError, openai.RateLimitError)):
        return "busy"
    if isinstance(e, (anthropic.APIConnectionError, anthropic.InternalServerError,
                      openai.APIConnectionError, openai.InternalServerError)):
        return "network"
    if isinstance(e, (anthropic.BadRequestError, openai.BadRequestError, openai.NotFoundError)):
        return "bad_request"
    if str(e) == "refusal":
        return "refusal"
    return "failed"


async def _check(p: str) -> str:
    """A tiny request without retries; returns the model name or raises the provider's error."""
    if p == "anthropic":
        await _client().with_options(max_retries=0).messages.create(
            model=MODEL, max_tokens=64, output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Reply with: OK"}])
        return MODEL
    model = await model_for(p)
    await _openai_client(p).with_options(max_retries=0).chat.completions.create(
        model=model, messages=[{"role": "user", "content": "Reply with: OK"}], **_oa_params(p, model, 64))
    return model


async def self_check() -> None:
    """At startup: use the first provider whose key and balance work; report the problem if none does."""
    global _active
    _active = ""
    failures = []
    for p in configured():
        try:
            model = await _check(p)
        except Exception as e:  # noqa: BLE001 - reported, never fatal
            failures.append((p, error_code(e)))
            log.error("AI check failed: provider=%s error=%s (%s)", p, failures[-1][1], type(e).__name__)
            continue
        _active = p
        STATUS.update(provider=p, model=model, ok=True, error="")
        log.info("AI check ok: provider=%s model=%s", p, model)
        return
    if not failures:
        STATUS.update(provider="", model="", ok=False, error="not_configured")
    else:
        STATUS.update(provider=failures[0][0], model="", ok=False, error=failures[0][1])


async def outline(topic: str, pages: int, lang: str, tone: str, extra: str) -> dict:
    n = pages - 2
    prompt = f"""Topic: {topic}
Language of all visible text: {LANG_NAME[lang]}
Audience/tone: {TONES.get(tone, TONES['student'])}

Plan a deck of exactly {n} content slides in "plan" (the cover and the final thank-you slide are separate:
they use "title", "subtitle" and "thanks"). Storyline: introduction → main parts → the last slide is the
conclusion. For each slide give layout, a clear title (max ~8 words) and "focus": one sentence on exactly what
this slide explains, so that slides never repeat each other.

{LAYOUT_GUIDE}

"design" — the visual identity of THIS topic. Pick colours the audience instantly associates with the subject:
space → deep navy/black + neon cyan/violet; nature/ecology → dark forest green + lime; Nauryz/Kazakh culture →
turquoise and gold of the flag and ornaments; medicine → clean white + teal; history → dark sepia/burgundy +
gold; finance → navy + emerald; sport → black + energetic orange; children/school → light, bright, friendly.
mood: 3-5 words; dark: dark or light background; bg1/bg2: background gradient (hex like "0B1D3A");
accent/accent2: vivid highlight colours (hex) that contrast with the background; pattern: blobs
(soft/organic), geometric (tech/business/science), lines (strict/academic/history), dots (playful/school).
font: Times New Roman or Cambria for history, literature, law, classic/academic topics; Segoe UI or Calibri for
tech, business, modern topics; Verdana or Tahoma for school/children; Arial when neutral.
"subtitle": one sentence. "thanks": a short closing phrase (e.g. "Назарларыңызға рахмет!").
{("Wishes from the author: " + extra) if extra else ""}"""
    return await _stream_json(SYSTEM, prompt, OUTLINE_SCHEMA, None, 16000)


def _slides_prompt(topic: str, lang: str, tone: str, density: str, extra: str, notes: bool, plan: dict,
                   idxs: list[int]) -> str:
    whole = "\n".join(f"{i + 1}. [{p['layout']}] {p['title']} — {p['focus']}" for i, p in enumerate(plan["plan"]))
    mine = "\n".join(f"- slide {i + 1}: layout={plan['plan'][i]['layout']}; title=\"{plan['plan'][i]['title']}\"; "
                     f"focus: {plan['plan'][i]['focus']}" for i in idxs)
    return f"""Topic: {topic}
Deck title: {plan['title']}
Language of all visible text: {LANG_NAME[lang]}
Audience/tone: {TONES.get(tone, TONES['student'])}

Whole deck (for context, so you do not repeat other slides):
{whole}

Write the full text of ONLY these {len(idxs)} slides, in this order, in "slides":
{mine}

Text amount: {DENSITY.get(density, DENSITY['long'])}
Write complete, understandable sentences with explanations and examples — no 2-3 word fragments.
Per layout (fill unused fields with "" or []):
- image_right / image_left / article: title, lead, bullets, image_query (article: image_query "").
- cards: title, lead (1 sentence), bullets = 3-4 items written as "Short heading: 1-2 explanatory sentences".
- stats: title, lead, stats = 3-4 items (value is short: "1991", "70%", "2,7 млн км²"; label 3-8 words),
  bullets = 1-2 sentences explaining what the numbers mean.
- quote: quote (real, exact), quote_author, lead = 1-2 sentences on what it means for the topic, image_query.
- two_column: title, lead (1 sentence), left_title + bullets vs right_title + right_bullets (3-4 sentences each).
- timeline: title, lead (1 sentence), bullets = 4-5 items "Year or stage: 1-2 sentences about it".
Keep each slide's given title. "notes": {"3-4 sentences the speaker can say, adding details not on the slide" if notes else "always \"\""}.
{("Wishes from the author: " + extra) if extra else ""}"""


_SLIDE_START = re.compile(r'"title"\s*:\s*"')


async def write_slides(topic: str, lang: str, tone: str, density: str, extra: str, notes: bool, plan: dict,
                       on_progress: Callable[[int], Awaitable[None]],
                       on_batch: Callable[[list[int], list[dict]], Awaitable[None]] | None = None) -> list[dict]:
    """All content slides; batches run in parallel. on_progress(total slides finished so far)."""
    n = len(plan["plan"])
    size = batch_size()
    batches = [list(range(i, min(n, i + size))) for i in range(0, n, size)]
    started = [0] * len(batches)
    result: list[dict | None] = [None] * n
    sem = asyncio.Semaphore(parallel())
    max_tokens = {"medium": 8000, "long": 12000, "full": 16000}.get(density, 12000)

    async def run(b: int, idxs: list[int]) -> None:
        async def on_text(text: str) -> None:
            # a slide is finished once the next one has started
            k = max(0, min(len(idxs), len(_SLIDE_START.findall(text))) - 1)
            if k != started[b]:
                started[b] = k
                await on_progress(sum(started))

        async with sem:
            data = await _stream_json(SYSTEM, _slides_prompt(topic, lang, tone, density, extra, notes, plan, idxs),
                                      SLIDES_SCHEMA, on_text, max_tokens)
        got = data.get("slides", [])
        for j, i in enumerate(idxs):
            s = got[j] if j < len(got) else {"title": plan["plan"][i]["title"], "lead": plan["plan"][i]["focus"]}
            s["layout"] = plan["plan"][i]["layout"]
            s["title"] = s.get("title") or plan["plan"][i]["title"]
            result[i] = s
        started[b] = len(idxs)
        await on_progress(sum(started))
        if on_batch:
            await on_batch(idxs, [result[i] for i in idxs])

    await asyncio.gather(*(run(b, idxs) for b, idxs in enumerate(batches)))
    return [s for s in result if s is not None]
