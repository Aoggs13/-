"""The real Claude request path, against a mocked HTTP transport (no network, no key)."""
import asyncio
import json

import anthropic
import httpx2
import pytest

from app import content

OUTLINE = {
    "design": {"mood": "космос", "dark": True, "bg1": "0B1D3A", "bg2": "1A0B3A", "accent": "22D3EE",
               "accent2": "A855F7", "pattern": "geometric", "font": "Segoe UI"},
    "title": "Ғарыш", "subtitle": "Шолу", "cover_image_query": "space rocket", "thanks": "Рахмет!",
    "plan": [{"layout": "image_right", "title": f"Слайд {i}", "focus": "-"} for i in range(6)],
}


def sse(obj: dict) -> bytes:
    text = json.dumps(obj, ensure_ascii=False)
    chunks = [text[i:i + 40] for i in range(0, len(text), 40)]
    events = [
        ("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": content.MODEL, "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        *[("content_block_delta", {"type": "content_block_delta", "index": 0,
                                   "delta": {"type": "text_delta", "text": c}}) for c in chunks],
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 50}}),
        ("message_stop", {"type": "message_stop"}),
    ]
    return b"".join(f"event: {e}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n".encode() for e, d in events)


@pytest.fixture()
def calls(monkeypatch):
    seen = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        seen.append((request, body))
        schema_props = body["output_config"]["format"]["schema"]["properties"]
        if "plan" in schema_props:
            payload = OUTLINE
        else:
            n = body["messages"][0]["content"].count("- slide ")
            payload = {"slides": [{"title": f"T{i}", "lead": "Кіріспе сөйлем.", "bullets": ["Бір: екі үш."],
                                   "left_title": "", "right_title": "", "right_bullets": [], "quote": "",
                                   "quote_author": "", "stats": [], "image_query": "rocket", "notes": ""}
                                  for i in range(n)]}
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=sse(payload))

    def client():
        return anthropic.AsyncAnthropic(api_key="test", max_retries=0, http_client=anthropic.DefaultAsyncHttpxClient(
            transport=httpx2.MockTransport(handler)))

    monkeypatch.setattr(content, "_client", client)
    return seen


def test_outline_request_shape(calls):
    plan = asyncio.run(content.outline("Ғарышты игеру", 8, "kk", "student", ""))
    assert plan["design"]["font"] == "Segoe UI"
    req, body = calls[0]
    assert body["model"] == content.MODEL
    assert body["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in req.headers["anthropic-beta"]
    assert body["output_config"]["effort"] == content.EFFORT
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["stream"] is True
    assert "exactly 6 content slides" in body["messages"][0]["content"]


def test_slides_are_written_in_parallel_batches(calls, monkeypatch):
    monkeypatch.setattr(content, "BATCH", 4)
    progress, batches = [], []

    async def on_progress(n):
        progress.append(n)

    async def on_batch(idxs, slides):
        batches.append(idxs)

    slides = asyncio.run(content.write_slides("Ғарыш", "kk", "student", "long", "", True, OUTLINE,
                                              on_progress, on_batch))
    assert len(slides) == 6 and len(calls) == 2                    # 6 slides → batches of 4 + 2
    assert sorted(i for b in batches for i in b) == list(range(6))
    assert progress[-1] == 6
    assert all(s["layout"] == "image_right" for s in slides)       # layout always comes from the plan
    assert "Whole deck" in calls[0][1]["messages"][0]["content"]
