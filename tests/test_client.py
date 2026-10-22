import httpx

from src.sios.client import SiosClient


def test_source_search_params_override_nationwide_defaults() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(200, text="<html></html>")

    client = SiosClient(
        base_url="https://system.sios.pl",
        user_agent="test",
        request_delay_seconds=0,
        max_retries=0,
        iid=999,
        search_params={"iid": 0, "id_provinces": 7},
        transport=httpx.MockTransport(handler),
    )
    try:
        client.search("bóbr", page=2)
    finally:
        client.close()

    assert captured["keywords"] == "bóbr"
    assert captured["page"] == "2"
    assert captured["iid"] == "0"
    assert captured["id_provinces"] == "7"
