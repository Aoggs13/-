"""OpenAI and Gemini (OpenAI-compatible) paths and provider selection, against mocked HTTP (no network)."""
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
MODELS = {
    "openai": ["gpt-4o", "gpt-5", "gpt-5.1", "gpt-4.1", "gpt-5-mini", "gpt-5.1-codex", "dall-e-3"],
    "gemini": ["models/gemini-2.5-flash", "models/gemini-3.5-flash", "models/gemini-3.5-pro",
               "models/gemini-3.5-flash-lite", "models/text-embedding-004"],
}


def sse(text: str, model: str) -> bytes:
    out = [{"id": "c", "object": "chat.completion.chunk", "created": 1, "model": model,
            "choices": [{"index": 0, "delta": {"content": text[i:i + 30]}, "finish_reason": None}]}
           for i in range(0, len(text), 30)]
    out.append({"id": "c", "object": "chat.completion.chunk", "created": 1, "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
    return b"".join(f"data: {json.dumps(o, ensure_ascii=False)}\n\n".encode() for o in out) + b"data: [DONE]\n\n"


@pytest.fixture()
def api(monkeypatch):
    """Fake OpenAI + Gemini endpoints; state["broke"] holds providers whose balance is empty."""
    state = {"broke": set(), "calls": []}

    def handler(request: httpx2.Request) -> httpx2.Response:
        p = "gemini" if "generativelanguage" in request.url.host else "openai"
        if request.url.path.endswith("/models"):
            return httpx2.Response(200, json={"object": "list", "data": [
                {"id": i, "object": "model", "created": 1, "owned_by": p} for i in MODELS[p]]})
        body = json.loads(request.content)
        state["calls"].append((p, request.url.path, body))
        if p in state["broke"]:
            return httpx2.Response(429, json={"error": {"message": "You exceeded your current quota.",
                                                        "type": "insufficient_quota", "code": "insufficient_quota"}})
        if not body.get("stream"):
            return httpx2.Response(200, json={"id": "c", "object": "chat.completion", "created": 1,
                                              "model": body["model"], "choices": [{"index": 0, "finish_reason": "stop",
                                              "message": {"role": "assistant", "content": "OK"}}]})
        if "plan" in body["response_format"]["json_schema"]["schema"]["properties"]:
            payload = OUTLINE
        else:
            n = body["messages"][1]["content"].count("- slide ")
            payload = {"slides": [{"title": f"T{i}", "lead": "Кіріспе.", "bullets": ["Бір: екі."], "left_title": "",
                                   "right_title": "", "right_bullets": [], "quote": "", "quote_author": "",
                                   "stats": [], "image_query": "", "notes": ""} for i in range(n)]}
        return httpx2.Response(200, headers={"content-type": "text/event-stream"},
                               content=sse(json.dumps(payload, ensure_ascii=False), body["model"]))

    real = content._openai_client

    def client(p="openai"):
        c = real(p)
        return c.with_options(http_client=openai.DefaultAsyncHttpx2Client(transport=httpx2.MockTransport(handler)),
                              max_retries=0)

    monkeypatch.setattr(content, "_openai_client", client)
    return state


def test_provider_follows_the_keys(monkeypatch):
    assert content.provider() == "" and content.configured() == []
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert content.provider() == "gemini"
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert content.configured() == ["openai", "gemini"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert content.provider() == "anthropic"
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    assert content.configured() == ["gemini", "anthropic", "openai"]


def test_openai_requests(api, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    plan = asyncio.run(content.outline("Ғарыш", 7, "kk", "student", ""))
    assert plan["design"]["font"] == "Segoe UI"
    p, path, body = api["calls"][0]
    assert p == "openai" and body["model"] == "gpt-5.1"        # newest flagship, not codex/mini/dall-e
    assert body["reasoning_effort"] == "low" and "max_completion_tokens" in body
    assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False


def test_gemini_requests(api, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    done = []

    async def on_progress(n):
        done.append(n)

    slides = asyncio.run(content.write_slides("Ғарыш", "kk", "student", "long", "", False, OUTLINE, on_progress))
    assert len(slides) == 5 and done[-1] == 5
    p, path, body = api["calls"][0]
    assert p == "gemini" and path.endswith("/v1beta/openai/chat/completions")
    assert body["model"] == "gemini-3.5-flash"                  # newest Flash: free tier, not pro / lite
    assert "reasoning_effort" not in body and "max_tokens" in body
    assert "additionalProperties" not in json.dumps(body["response_format"])
    assert len(api["calls"]) == 1                                # 5 slides fit one bigger batch


def test_self_check_skips_a_key_without_balance(api, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    api["broke"].add("openai")
    asyncio.run(content.self_check())
    assert content.provider() == "gemini" and content.STATUS["ok"] is True

    api["broke"].add("gemini")
    asyncio.run(content.self_check())
    assert content.STATUS == {"provider": "openai", "model": "", "ok": False, "error": "quota"}
