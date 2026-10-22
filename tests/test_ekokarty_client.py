import httpx

from src.ekokarty.client import EkokartyClient


def test_search_posts_keyword_and_date_window() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = dict(httpx.QueryParams(request.content.decode("utf-8")))
        return httpx.Response(200, text="<html></html>")

    client = EkokartyClient(
        base_url="https://ekokarty.pl",
        user_agent="test",
        request_delay_seconds=0,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        from datetime import date

        client.search(
            "rdos-warszawa",
            "Castor fiber",
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
        )
    finally:
        client.close()

    assert captured["method"] == "POST"
    assert captured["url"] == "https://ekokarty.pl/wykaz/rdos-warszawa/"
    assert captured["body"]["szukajRodzaj"] == "NEW"
    assert captured["body"]["karty_all"] == "Castor fiber"
    assert captured["body"]["data_od"] == "2026-01-01"
    assert captured["body"]["data_do"] == "2026-01-31"


def test_detail_fetch_is_get() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(200, text="<html>card</html>")

    client = EkokartyClient(
        base_url="https://ekokarty.pl",
        user_agent="test",
        request_delay_seconds=0,
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    try:
        html = client.fetch_card("/wykaz/rdos-warszawa/77888/11843/X")
    finally:
        client.close()

    assert html == "<html>card</html>"
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/wykaz/rdos-warszawa/77888/11843/X")
