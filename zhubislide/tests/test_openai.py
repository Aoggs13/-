"""The OpenAI path, against a mocked HTTP transport (no network, no real key)."""
import asyncio
import json

import httpx2
import openai
import pytest

from app import content

OUTLINE = {
    "design": {"mood": "космос", "dark": True, "bg1": "0B1D3A", "bg2": "1A0B3A", "accent": "22D3EE",
               "accent2": "A855F7", "pattern": "geometric", "font": "Segoe UI"},
    "title": "Ғарыш", "subtitle": "Шолу", "cover_image_query": "space rocket", "thanks": "Рахмет!",
    "plan": [{"layout": "cards", "title": f"Слайд {i}", "focus": "-"} for i in range(5)],
}


def sse(text: str, model: str, finish: str = "stop") -> bytes:
    chunks = [text[i:i + 30] for i in range(0, len(text), 30)]
    out = []
    for i, c in enumerate(chunks):
        out.append({"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": model,
                    "choices": [{"index": 0, "delta": ({"role": "assistant"} if i == 0 else {}) | {"content": c},
                                 "finish_reason": None}]})
    out.append({"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
    return b"".join(f"data: {json.dumps(o, ensure_ascii=False)}\n\n".encode() for o in out) + b"data: [DONE]\n\n"


@pytest.fixture()
def oa(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setattr(content, "_openai_model", "")
    monkeypatch.setattr(content, "OPENAI_MODEL", "")
    seen = {"chat": []}
    state = {"quota": False}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/models"):
            data = [{"id": i, "object": "model", "created": 1, "owned_by": "openai"}
                    for i in ("gpt-4o", "gpt-5", "gpt-5.1", "gpt-4.1", "gpt-5-mini", "gpt-5.1-codex", "dall-e-3")]
            return httpx2.Response(200, json={"object": "list", "data": data})
        body = json.loads(request.content)
        seen["chat"].append(body)
        if state["quota"]:
            return httpx2.Response(429, json={"error": {"message": "You exceeded your current quota.",
                                                        "type": "insufficient_quota", "code": "insufficient_quota"}})
        if not body.get("stream"):
            return httpx2.Response(200, json={"id": "c", "object": "chat.completion", "created": 1, "model": body["model"],
                                              "choices": [{"index": 0, "finish_reason": "stop",
                                                           "message": {"role": "assistant", "content": "OK"}}]})
        props = body["response_format"]["json_schema"]["schema"]["properties"]
        if "plan" in props:
            payload = OUTLINE
        else:
            n = body["messages"][1]["content"].count("- slide ")
            payload = {"slides": [{"title": f"T{i}", "lead": "Кіріспе.", "bullets": ["Бір: екі."], "left_title": "",
                                   "right_title": "", "right_bullets": [], "quote": "", "quote_author": "",
                                   "stats": [], "image_query": "", "notes": ""} for i in range(n)]}
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               content=sse(json.dumps(payload, ensure_ascii=False), body["model"]))

    monkeypatch.setattr(content, "_openai_client", lambda: openai.AsyncOpenAI(
        api_key="test", max_retries=0, http_client=openai.DefaultAsyncHttpx2Client(transport=httpx2.MockTransport(handler))))
    seen["state"] = state
    return seen


def test_provider_follows_the_key(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert content.provider() == ""
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert content.provider() == "openai"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
    assert content.provider() == "anthropic"
    monkeypatch.setenv("AI_PROVIDER", "openai")
    assert content.provider() == "openai"


def test_openai_outline_and_slides(oa):
    plan = asyncio.run(content.outline("Ғарыш", 7, "kk", "student", ""))
    assert plan["design"]["font"] == "Segoe UI"
    body = oa["chat"][0]
    assert body["model"] == "gpt-5.1"                       # newest flagship, not codex/mini/dall-e
    assert body["reasoning_effort"] == "low"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["messages"][0]["role"] == "system" and body["stream"] is True

    done = []

    async def on_progress(n):
        done.append(n)

    slides = asyncio.run(content.write_slides("Ғарыш", "kk", "student", "long", "", False, OUTLINE, on_progress))
    assert len(slides) == 5 and done[-1] == 5
    assert all(s["layout"] == "cards" for s in slides)


def test_self_check_reports_empty_balance(oa):
    oa["state"]["quota"] = True
    asyncio.run(content.self_check())
    assert content.STATUS["ok"] is False and content.STATUS["error"] == "quota"
    oa["state"]["quota"] = False
    asyncio.run(content.self_check())
    assert content.STATUS["ok"] is True and content.STATUS["provider"] == "openai"
