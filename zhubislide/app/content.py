"""Slide text generation with Claude.

Two phases so that long, detailed decks are still fast:
1. outline  — design palette, title, and a plan (layout + title + focus) for every slide;
2. slides   — the full text, written in parallel batches that all see the whole outline.
Both are streamed, so progress shown to the user is real, not simulated.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Awaitable, Callable

import anthropic

from .themes import FONTS

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("CLAUDE_EFFORT", "low")
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


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(max_retries=3)


async def _stream_json(system: str, prompt: str, schema: dict, on_text: Callable[[str], Awaitable[None]] | None,
                       max_tokens: int) -> dict:
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
    batches = [list(range(i, min(n, i + BATCH))) for i in range(0, n, BATCH)]
    started = [0] * len(batches)
    result: list[dict | None] = [None] * n
    sem = asyncio.Semaphore(PARALLEL)
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
