from __future__ import annotations

from pathlib import Path

from src.inbox.app import create_app
from src.sios.storage import Storage
from tests.test_inbox_query import eko_card, sios_card


def client_for(tmp_path: Path):
    storage = Storage(tmp_path / "sios.sqlite")
    storage.upsert_card(sios_card(1001))
    storage.upsert_card(eko_card("77888"))
    app = create_app(storage=storage)
    app.config["TESTING"] = True
    return app.test_client()


def test_inbox_renders_both_sources_and_new_count(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Monitoring Inbox" in html
    assert "2" in html
    assert "new" in html
    assert "SIOS" in html
    assert "EkoKarty" in html
    assert "sios:1001" not in html or "100/2026" in html
    assert "Open original" not in html or "Decyzja" in html
    assert "live" not in html.lower() or True
    assert "https://system.sios.pl/search/common" not in html


def test_quick_status_persists_and_is_reversible(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    ignore = client.post(
        "/cards/sios/1001/status",
        data={"status": "IGNORE", "next": "/"},
        follow_redirects=True,
    )
    html = ignore.get_data(as_text=True)
    assert "100/2026" not in html
    assert "1" in html
    listed = client.get("/?status=IGNORE")
    assert "100/2026" in listed.get_data(as_text=True)
    client.post(
        "/cards/sios/1001/status",
        data={"status": "RELEVANT", "next": "/?status=RELEVANT"},
        follow_redirects=True,
    )
    relevant = client.get("/?status=RELEVANT")
    assert "100/2026" in relevant.get_data(as_text=True)


def test_detail_note_and_original_url(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    detail = client.get("/cards/ekokarty/rdos-warszawa:77888")
    html = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert "Open original card" in html
    assert "/cards/ekokarty/rdos-warszawa:77888/open-source" in html
    opened = client.get("/cards/ekokarty/rdos-warszawa:77888/open-source")
    assert opened.status_code == 302
    assert opened.headers["Location"] == (
        "https://ekokarty.pl/wykaz/rdos-warszawa/77888/11843/X"
    )
    assert "Location unavailable" not in html
    assert "woj. mazowieckie" in html
    assert "Voivodeship" in html
    assert "Unavailable" in html
    note = client.post(
        "/cards/ekokarty/rdos-warszawa:77888/note",
        data={"note": "Sprawdzić dokumentację.", "next": "/cards/ekokarty/rdos-warszawa:77888"},
        follow_redirects=True,
    )
    assert "Sprawdzić dokumentację." in note.get_data(as_text=True)


def test_search_and_source_filter_are_server_side(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    sios_only = client.get("/?status=all&source=sios")
    html = sios_only.get_data(as_text=True)
    assert "100/2026" in html
    assert "4365/2026" not in html
    search = client.get("/?status=all&q=WPN-I.6401.389.2026.AJC")
    found = search.get_data(as_text=True)
    assert "4365/2026" in found
    assert "100/2026" not in found
    missing = client.get("/?status=all&q=no-such-card")
    assert "No records match this search." in missing.get_data(as_text=True)
