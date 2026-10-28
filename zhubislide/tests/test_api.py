"""End-to-end through the HTTP API with the Claude calls and photo search replaced by fakes."""
import asyncio
import copy
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from sample_deck import DECK


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    from app import content, images, jobs, main

    monkeypatch.setattr(jobs, "DATA_DIR", tmp_path)
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "STATS_FILE", tmp_path / "stats.json")
    seen = {}

    async def outline(topic, pages, lang, tone, extra):
        seen["outline"] = (topic, pages, lang)
        src = (DECK["slides"] * 4)[:pages - 2]
        return {**{k: DECK[k] for k in ("design", "title", "subtitle", "cover_image_query", "thanks")},
                "plan": [{"layout": s["layout"], "title": s["title"], "focus": "-"} for s in src]}

    async def write(topic, lang, tone, density, extra, notes, plan, on_progress, on_batch=None):
        src = (DECK["slides"] * 4)[:len(plan["plan"])]
        out = []
        for i, s in enumerate(src):
            out.append(copy.deepcopy(s))
            await on_progress(i + 1)
            if on_batch:
                await on_batch([i], [out[-1]])
        return out

    async def find_photo(c, q, used):
        return Image.new("RGB", (1200, 800), "#336699")

    monkeypatch.setattr(content, "outline", outline)
    monkeypatch.setattr(content, "write_slides", write)
    monkeypatch.setattr(images, "find_photo", find_photo)
    main.manager.__init__()
    with TestClient(main.app) as c:
        c.seen = seen
        yield c


def wait_done(client, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        st = client.get(f"/api/jobs/{job_id}").json()
        if st["status"] in ("done", "error"):
            return st
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_meta_has_estimates_for_every_option(client):
    m = client.get("/api/meta").json()
    assert m["pages"] == [5, 8, 10, 15, 20, 25]
    assert "Times New Roman" in m["fonts"]
    for d in ("medium", "long", "full"):
        secs = [m["estimates"][d][str(p)]["1"]["seconds"] for p in m["pages"]]
        assert secs == sorted(secs) and secs[0] > 0       # more slides never take less time


def test_full_generation_and_retheme(client):
    r = client.post("/api/jobs", json={"topic": "Ұлттық парктер", "pages": 10, "lang": "kk", "font": "Calibri"})
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["estimate"] > 0
    st = wait_done(client, job["id"])
    assert st["status"] == "done", st
    assert st["slides_done"] == 8 and st["font_used"] == "Calibri"
    assert client.seen["outline"] == ("Ұлттық парктер", 10, "kk")

    deck = client.get(f"/api/jobs/{job['id']}/deck").json()
    assert len(deck["deck"]["slides"]) == 8 and "cover" in deck["images"]
    assert client.get(f"/api/jobs/{job['id']}/img/cover").status_code == 200

    for q in ("", "?theme=minimal&font=Times%20New%20Roman"):
        d = client.get(f"/api/jobs/{job['id']}/download{q}")
        assert d.status_code == 200 and d.content[:2] == b"PK"
        assert "filename*=UTF-8''" in d.headers["content-disposition"]


@pytest.mark.parametrize("body", [
    {"topic": "ab", "pages": 10},
    {"topic": "Тақырып", "pages": 7},
    {"topic": "Тақырып", "pages": 10, "lang": "en"},
    {"topic": "Тақырып", "pages": 10, "font": "Comic Sans"},
    {"topic": "Тақырып", "pages": 10, "theme": "nope"},
])
def test_bad_requests_are_rejected(client, body):
    assert client.post("/api/jobs", json=body).status_code in (400, 422)


def test_unknown_or_malformed_job_ids(client):
    assert client.get("/api/jobs/" + "0" * 32).status_code == 404
    assert client.get("/api/jobs/../../etc/passwd").status_code == 404
    assert client.get("/api/jobs/" + "0" * 32 + "/img/..%2Fmeta").status_code == 404
