"""Photo search against mocked Wikipedia / Commons / Openverse (no network)."""
import asyncio
import io
from urllib.parse import parse_qs, urlparse

import httpx
from PIL import Image

from app import images


def jpeg(w, h, color="#886644") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "JPEG")
    return buf.getvalue()


PORTRAIT = "https://upload.wikimedia.org/a/Akhmet_Baitursynuly.jpg"
MONUMENT = "https://upload.wikimedia.org/b/Baitursynuly_monument.jpg"
STRANGER = "https://cdn.openverse.example/random_man.jpg"


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    host = request.url.host
    if host == "en.wikipedia.org":
        if q.get("titles") == "Akhmet Baitursynuly":
            return httpx.Response(200, json={"query": {"pages": [{"title": "Akhmet Baitursynuly",
                                                                  "thumbnail": {"source": PORTRAIT}}]}})
        return httpx.Response(200, json={"query": {"pages": [{"title": q.get("titles", ""), "missing": True}]}})
    if host.endswith("wikipedia.org"):
        return httpx.Response(200, json={"query": {"pages": [{"title": "x", "missing": True}]}})
    if host == "commons.wikimedia.org":
        if "Baitursynuly" in q.get("gsrsearch", "") or "Байтұрсынұлы" in q.get("gsrsearch", ""):
            return httpx.Response(200, json={"query": {"pages": {"1": {"index": 1, "imageinfo": [
                {"url": MONUMENT, "thumburl": MONUMENT, "width": 900, "height": 1200, "mime": "image/jpeg"}]}}}})
        return httpx.Response(200, json={"query": {"pages": {}}})
    if host == "api.openverse.org":
        return httpx.Response(200, json={"results": [{"url": STRANGER, "width": 1600, "height": 1000}]})
    if url == PORTRAIT:
        return httpx.Response(200, content=jpeg(300, 420))          # old portraits are small
    if url == MONUMENT:
        return httpx.Response(200, content=jpeg(900, 1200, "#445566"))
    if url == STRANGER:
        return httpx.Response(200, content=jpeg(1600, 1000, "#000000"))
    return httpx.Response(404)


def run(query, subject, used):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await images.find_photo(c, query, used, subject, "kk", "t")
    return asyncio.run(go())


def test_subject_photo_comes_from_its_wikipedia_article_then_commons():
    used = set()
    subject = "Akhmet Baitursynuly | Ахмет Байтұрсынұлы"
    first = run("kazakh scholar", subject, used)
    assert first.size == (300, 420) and images.file_key(PORTRAIT) in used     # the real portrait, even if small
    second = run("kazakh scholar", subject, used)
    assert second.size == (900, 1200) and images.file_key(MONUMENT) in used   # then other photos of him
    assert images.file_key(STRANGER) not in used


def test_without_a_subject_stock_search_is_used():
    used = set()
    img = run("steppe horses", "", used)
    assert img.size == (1600, 1000) and used == {images.file_key(STRANGER)}


def test_split_subject():
    assert images.split_subject("Abai Qunanbaiuly | Абай Құнанбайұлы") == ("Abai Qunanbaiuly", "Абай Құнанбайұлы")
    assert images.split_subject("Burabay") == ("Burabay", "Burabay")
    assert images.split_subject("") == ("", "")


def test_thumbnail_and_original_are_the_same_photo():
    a = "https://upload.wikimedia.org/wikipedia/commons/4/4c/%D0%90%D1%85%D0%BC%D0%B5%D1%82_(1913).jpg?utm=x"
    b = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4c/%D0%90%D1%85%D0%BC%D0%B5%D1%82_(1913).jpg/800px-x.jpg"
    assert images.file_key(a) == images.file_key(b) == "ахмет_(1913).jpg"
