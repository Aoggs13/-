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


VEGETABLES = "https://upload.wikimedia.org/thumb/c/cc/Vegetables.jpg/1600px-Vegetables.jpg"
CARROTS = "https://upload.wikimedia.org/e/Fresh_carrots_for_a_healthy_meal.jpg"


def stock(commons_files: list[str], calls: list[str]):
    """Openverse times out; Commons has the given files; Wikipedia search finds a city that mentions every word,
    an article with a city photo, a diagram and finally the right article."""
    hits = [("Atlanta", "https://upload.wikimedia.org/thumb/a/aa/Atlanta.jpg/1600px-Atlanta.jpg"),
            ("Food desert", "https://upload.wikimedia.org/thumb/b/bb/Skyline.jpg/1600px-Skyline.jpg"),
            ("Healthy diet", "https://upload.wikimedia.org/thumb/d/dd/Pyramid.svg/1600px-Pyramid.svg.png"),
            ("Vegetable", VEGETABLES)]

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        calls.append(host)
        if host == "api.openverse.org":
            raise httpx.ReadTimeout("slow", request=request)
        if host == "en.wikipedia.org":
            return httpx.Response(200, json={"query": {"pages": [
                {"index": i, "title": t, "thumbnail": {"source": u}} for i, (t, u) in enumerate(hits, 1)]}})
        if host == "commons.wikimedia.org":
            return httpx.Response(200, json={"query": {"pages": {str(i): {"index": i, "imageinfo": [
                {"url": u, "width": 1600, "height": 1000, "mime": "image/jpeg"}]} for i, u in enumerate(commons_files)}}})
        return httpx.Response(200, content=jpeg(1600, 1000))
    return handler


def find(handler, used):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await images.find_photo(c, "healthy fresh food vegetables", used, "", "kk", "t")
    return asyncio.run(go())


def test_commons_file_comes_before_wikipedia_and_openverse_is_not_waited_for_twice():
    calls, used = [], set()
    handler = stock([CARROTS], calls)
    assert find(handler, used) is not None and used == {images.file_key(CARROTS)}
    assert find(handler, used) is not None and images.file_key(VEGETABLES) in used   # next slide
    assert calls.count("api.openverse.org") == 1           # timed out once, then skipped for a while


def test_only_an_article_about_the_thing_gives_a_photo():
    used = set()
    assert find(stock([], []), used) is not None
    assert used == {images.file_key(VEGETABLES)}           # not the city, the skyline or the diagram
    assert find(stock([], []), used) is None               # nothing else on topic → theme-coloured art


def test_on_topic_article_titles():
    assert images._on_topic("Optical fiber", "telecommunication network fiber optics")
    assert images._on_topic("Eurasian Steppe", "kazakh steppe horses")
    assert images._on_topic("Vegetable", "healthy fresh food vegetables")
    assert images._on_topic("Library of Congress", "old books library")
    assert images._on_topic("Solar panel", "solar panels field")
    assert not images._on_topic("Food desert", "healthy fresh food vegetables")
    assert not images._on_topic("Atlanta", "healthy fresh food vegetables")
    assert not images._on_topic("Art", "artificial intelligence robot")


def test_commons_stock_photos_are_jpeg_only():
    logo = "https://upload.wikimedia.org/f/Telecom_company_logo.png"
    photo = "https://upload.wikimedia.org/g/Fiber_cables.jpg"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": {"pages": {
            "1": {"index": 1, "imageinfo": [{"url": logo, "width": 1437, "height": 1400, "mime": "image/png"}]},
            "2": {"index": 2, "imageinfo": [{"url": photo, "width": 1600, "height": 1000, "mime": "image/jpeg"}]}}}})

    async def go(subject):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await images._commons(c, "telecommunication network", subject=subject)
    assert asyncio.run(go(False)) == [photo]               # a logo is not a stock photo
    assert asyncio.run(go(True)) == [logo, photo]          # an old scanned portrait may be a PNG


def test_split_subject():
    assert images.split_subject("Abai Qunanbaiuly | Абай Құнанбайұлы") == ("Abai Qunanbaiuly", "Абай Құнанбайұлы")
    assert images.split_subject("Burabay") == ("Burabay", "Burabay")
    assert images.split_subject("") == ("", "")


def test_thumbnail_and_original_are_the_same_photo():
    a = "https://upload.wikimedia.org/wikipedia/commons/4/4c/%D0%90%D1%85%D0%BC%D0%B5%D1%82_(1913).jpg?utm=x"
    b = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4c/%D0%90%D1%85%D0%BC%D0%B5%D1%82_(1913).jpg/800px-x.jpg"
    assert images.file_key(a) == images.file_key(b) == "ахмет_(1913).jpg"
