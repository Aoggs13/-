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
    "gemini": ["models/gemini-3.8-flash", "models/gemini-3.5-flash", "models/gemini-3.5-pro",
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
    state = {"broke": set(), "calls": [], "unserved": {"gemini-3.8-flash"}, "cut": 0, "down": set()}

    def handler(request: httpx2.Request) -> httpx2.Response:
        p = "gemini" if "generativelanguage" in request.url.host else "openai"
        if request.url.path.endswith("/models"):
            return httpx2.Response(200, json={"object": "list", "data": [
                {"id": i, "object": "model", "created": 1, "owned_by": p} for i in MODELS[p]]})
        body = json.loads(request.content)
        state["calls"].append((p, request.url.path, body))
        if body.get("stream") and body["model"] in state["down"]:
            return httpx2.Response(503, json={"error": {"message": "The model is overloaded.", "code": 503}})
        if body["model"] in state["unserved"]:
            return httpx2.Response(503, json={"error": {"message": "The model is overloaded.", "code": 503}})
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
        data = sse(json.dumps(payload, ensure_ascii=False), body["model"])
        if state["cut"]:                      # stream that just stops: no finish reason, broken JSON
            state["cut"] -= 1
            data = data[:300] + b"\n\n"
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=data)

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
    tried = [b["model"] for _, _, b in api["calls"]]
    assert tried == ["gemini-3.8-flash", "gemini-3.5-flash"]       # newest is listed but not served → next
    p, path, body = api["calls"][-1]
    assert p == "gemini" and path.endswith("/v1beta/openai/chat/completions")
    assert body["reasoning_effort"] == "low" and "max_tokens" in body
    assert "additionalProperties" not in json.dumps(body["response_format"])

    api["calls"].clear()                                         # the failed model is remembered
    asyncio.run(content.write_slides("Ғарыш", "kk", "student", "long", "", False, OUTLINE, on_progress))
    assert [b["model"] for _, _, b in api["calls"]] == ["gemini-3.5-flash"]


def test_cut_stream_is_retried_and_used_up_models_are_skipped(api, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    api["cut"] = 1
    plan = asyncio.run(content.outline("Ғарыш", 7, "kk", "student", ""))
    assert plan["title"] == "Ғарыш"
    assert [b["model"] for _, _, b in api["calls"]][-2:] == ["gemini-3.5-flash", "gemini-3.5-flash"]

    api["calls"].clear()
    api["broke"].add("gemini")                                    # every model: daily limit reached
    with pytest.raises(content.DailyLimit) as e:
        asyncio.run(content.outline("Ғарыш", 7, "kk", "student", ""))
    assert content.error_code(e.value) == "daily_limit"
    assert {b["model"] for _, _, b in api["calls"]} == {"gemini-3.5-flash", "gemini-3.5-flash-lite"}


def test_self_check_skips_a_key_without_balance_and_spends_no_gemini_quota(api, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    api["broke"].add("openai")
    asyncio.run(content.self_check())
    assert content.provider() == "gemini" and content.STATUS["ok"] is True
    assert [p for p, _, _ in api["calls"]] == ["openai"]          # Gemini was only listed, not asked

    monkeypatch.delenv("GEMINI_API_KEY")
    asyncio.run(content.self_check())
    assert content.STATUS == {"provider": "openai", "model": "", "ok": False, "error": "quota"}


def test_time_estimates_are_kept_per_provider(monkeypatch, tmp_path):
    from app import jobs
    monkeypatch.setattr(jobs, "_ALL_STATS", {})
    monkeypatch.setattr(jobs, "STATS_FILE", tmp_path / "stats.json")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    gemini = jobs.estimate(10, True)["parts"]["text"]
    assert gemini == round(9.0 + 5.0 + 3.5 * 8)                   # 8 content slides in one batch
    jobs.learn("outline_s", 30.0)                                  # a slow run moves the average
    assert jobs.STATS["outline_s"] == round(0.7 * 9 + 0.3 * 30, 3)
    jobs.save_stats()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")                   # another provider: its own numbers
    assert jobs.STATS["outline_s"] == 14.0
    assert set(jobs.load_stats()) == {"gemini"}
