from __future__ import annotations

from pathlib import Path

from src.ekokarty.models import EKOKARTY_CARD_PARSER_VERSION
from src.inbox.models import (
    REVIEW_IGNORE,
    REVIEW_MONITOR,
    REVIEW_NEW,
    REVIEW_RELEVANT,
    REVIEW_REQUEST_DOCUMENTS,
    InboxQuery,
)
from src.inbox.query import InboxRepository
from src.sios.models import SOURCE_SYSTEM_EKOKARTY, CardRecord
from src.sios.storage import Storage


def sios_card(
    sios_id: int,
    *,
    keyword: str = "bóbr",
    authority: str = "RDOŚ Olsztyn",
    document_type: str = "decyzje",
    document_name: str = "Decyzja o bobrach",
    location: str = "warmińsko-mazurskie / olsztyński / Dywity",
    entered_at: str = "2026-01-20 08:00:00",
    source_url: str = "",
    card_number: str = "100/2026",
    case_reference: str = "WOP.1",
    raw_fields: dict | None = None,
) -> CardRecord:
    return CardRecord(
        sios_id=sios_id,
        card_number=card_number,
        year=2026,
        document_name=document_name,
        document_type=document_type,
        case_reference=case_reference,
        authority=authority,
        location=location,
        dates={"entered_at": entered_at, "published_at": entered_at[:10]},
        matched_keywords=[keyword],
        source_url=source_url
        or "https://system.sios.pl/documents/details/id/{}".format(sios_id),
        raw_fields=raw_fields
        or {
            "Nazwa organu": authority,
            "_related_cards": [{"sios_id": 1, "card_number": "99/2026"}],
            "_attachments": [
                {"file_id": 1, "filename": "wniosek.pdf", "url": "https://example.test/f"}
            ],
        },
    )


def eko_card(card_id: str, keyword: str = "Castor fiber") -> CardRecord:
    return CardRecord(
        sios_id=None,
        card_number="4365/2026",
        year=2026,
        document_name="Decyzja zezwalająca na płoszenie",
        document_type="decyzje",
        case_reference="WPN-I.6401.389.2026.AJC",
        authority="Regionalna Dyrekcja Ochrony Środowiska w Warszawie",
        location="woj. mazowieckie, gmina Mszczonów",
        dates={"listing_date": "2026-01-22", "issued_at": "2026-01-18"},
        matched_keywords=[keyword],
        source_url="https://ekokarty.pl/wykaz/rdos-warszawa/{}/11843/X".format(card_id),
        raw_fields={"Numer karty/rok": "4365/2026", "_related_cards": []},
        parser_version=EKOKARTY_CARD_PARSER_VERSION,
        source_system=SOURCE_SYSTEM_EKOKARTY,
        native_record_id="rdos-warszawa:{}".format(card_id),
    )


def seeded(tmp_path: Path) -> tuple[Storage, InboxRepository]:
    storage = Storage(tmp_path / "sios.sqlite")
    storage.upsert_card(sios_card(1001, keyword="bóbr"))
    storage.upsert_card(
        sios_card(
            1002,
            keyword="odstrzał",
            authority="RDOŚ Katowice",
            document_type="wnioski o wydanie decyzji",
            document_name="Wniosek o odstrzał",
            location="śląskie / cieszyński / Ustroń",
            entered_at="2026-02-01 09:00:00",
            card_number="200/2026",
            case_reference="WOP.2",
        )
    )
    storage.upsert_card(eko_card("77888"))
    return storage, InboxRepository(storage)


def test_unified_query_keeps_source_identities_distinct(tmp_path: Path) -> None:
    _storage, repo = seeded(tmp_path)
    page = repo.search(InboxQuery(status=None, page_size=50))
    keys = [card.external_key for card in page.items]
    assert "sios:1001" in keys
    assert "ekokarty:rdos-warszawa:77888" in keys
    assert page.total == 3
    sios = repo.get_card("sios", "1001")
    eko = repo.get_card("ekokarty", "rdos-warszawa:77888")
    assert sios.card_number != eko.card_number or sios.external_key != eko.external_key
    assert sios.source_system == "sios"
    assert eko.source_system == "ekokarty"
    assert eko.voivodeship is None
    assert eko.county is None
    assert sios.voivodeship == "warmińsko-mazurskie"
    assert sios.display_date_field == "entered_at"
    assert eko.display_date_field == "listing_date"
    assert sios.display_date == "2026-01-20"
    assert eko.display_date == "2026-01-22"


def test_similar_metadata_does_not_merge_sios_and_ekokarty(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    similar = sios_card(
        77888,
        card_number="4365/2026",
        case_reference="WPN-I.6401.389.2026.AJC",
        document_name="Decyzja zezwalająca na płoszenie",
        authority="Regionalna Dyrekcja Ochrony Środowiska w Warszawie",
    )
    storage.upsert_card(similar)
    storage.upsert_card(eko_card("77888"))
    repo = InboxRepository(storage)
    page = repo.search(InboxQuery(status=None))
    assert page.total == 2
    assert {card.external_key for card in page.items} == {
        "sios:77888",
        "ekokarty:rdos-warszawa:77888",
    }


def test_new_is_the_default_review_status(tmp_path: Path) -> None:
    _storage, repo = seeded(tmp_path)
    card = repo.get_card("sios", "1001")
    assert card.review_status == REVIEW_NEW
    assert repo.metrics().total_new == 3
    default = repo.search(InboxQuery())
    assert default.total == 3
    assert all(item.review_status == REVIEW_NEW for item in default.items)


def test_status_change_reverse_and_note(tmp_path: Path) -> None:
    _storage, repo = seeded(tmp_path)
    first = repo.set_status("sios", "1001", REVIEW_IGNORE)
    assert first.review_status == REVIEW_IGNORE
    assert first.reviewed_at
    second = repo.set_status("sios", "1001", REVIEW_RELEVANT)
    assert second.review_status == REVIEW_RELEVANT
    noted = repo.set_note("sios", "1001", "Duża liczba bobrów, sprawdzić dokumentację.")
    assert noted.review_note.startswith("Duża liczba bobrów")
    assert noted.review_status == REVIEW_RELEVANT
    events = list(
        repo.conn.execute(
            "SELECT event_type, previous_status, new_status FROM review_events ORDER BY id"
        )
    )
    assert [row["event_type"] for row in events] == [
        "status_changed",
        "status_changed",
        "note_updated",
    ]
    assert events[0]["previous_status"] == REVIEW_NEW
    assert events[0]["new_status"] == REVIEW_IGNORE
    assert events[1]["previous_status"] == REVIEW_IGNORE
    assert events[1]["new_status"] == REVIEW_RELEVANT
    cards = repo.storage.get_card(1001)
    assert cards["document_name"] == "Decyzja o bobrach"


def test_filters_search_and_pagination(tmp_path: Path) -> None:
    _storage, repo = seeded(tmp_path)
    repo.set_status("sios", "1002", REVIEW_MONITOR)
    by_status = repo.search(InboxQuery(status=REVIEW_MONITOR))
    assert [card.native_record_id for card in by_status.items] == ["1002"]
    by_source = repo.search(InboxQuery(status=None, source="ekokarty"))
    assert [card.external_key for card in by_source.items] == [
        "ekokarty:rdos-warszawa:77888"
    ]
    by_keyword = repo.search(InboxQuery(status=None, keyword="odstrzał"))
    assert [card.native_record_id for card in by_keyword.items] == ["1002"]
    by_authority = repo.search(InboxQuery(status=None, authority="RDOŚ Olsztyn"))
    assert [card.native_record_id for card in by_authority.items] == ["1001"]
    by_date = repo.search(
        InboxQuery(status=None, date_from="2026-01-21", date_to="2026-01-31")
    )
    assert [card.external_key for card in by_date.items] == [
        "ekokarty:rdos-warszawa:77888"
    ]
    by_voiv = repo.search(InboxQuery(status=None, voivodeship="śląskie"))
    assert [card.native_record_id for card in by_voiv.items] == ["1002"]
    searched = repo.search(InboxQuery(status=None, q="WOP.1"))
    assert [card.native_record_id for card in searched.items] == ["1001"]
    storage = _storage
    for index in range(3, 54):
        storage.upsert_card(
            sios_card(
                2000 + index,
                card_number="{}/2026".format(index),
                entered_at="2025-01-01 00:00:00",
            )
        )
    repo = InboxRepository(storage)
    page1 = repo.search(InboxQuery(status=None, page=1, page_size=50))
    page2 = repo.search(InboxQuery(status=None, page=2, page_size=50))
    assert page1.total == 54
    assert len(page1.items) == 50
    assert len(page2.items) == 4
    keys = {card.external_key for card in page1.items} | {
        card.external_key for card in page2.items
    }
    assert len(keys) == 54


def test_missing_optional_metadata_and_source_url(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    record = sios_card(
        9,
        document_name=None,
        location=None,
        case_reference=None,
        source_url="",
        raw_fields={"Uwagi": "brak"},
    )
    record.document_name = None
    record.location = None
    record.case_reference = None
    record.source_url = ""
    storage.upsert_card(record)
    repo = InboxRepository(storage)
    card = repo.get_card("sios", "9")
    assert card.document_name is None
    assert card.location is None
    assert card.voivodeship is None
    assert not card.source_url
    assert card.review_status == REVIEW_NEW
    page = repo.search(InboxQuery())
    assert page.items[0].document_name is None


def test_request_documents_does_not_create_a_case(tmp_path: Path) -> None:
    _storage, repo = seeded(tmp_path)
    repo.set_status("ekokarty", "rdos-warszawa:77888", REVIEW_REQUEST_DOCUMENTS)
    tables = {
        row["name"]
        for row in repo.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "cases" not in tables
    assert repo.metrics().request_documents == 1
    card = repo.get_card("ekokarty", "rdos-warszawa:77888")
    assert card.review_status == REVIEW_REQUEST_DOCUMENTS
    assert card.source_url.endswith("/77888/11843/X")
    assert card.related_cards_count == 0
    assert repo.get_card("sios", "1001").has_attachment is True
    assert repo.get_card("sios", "1001").related_cards_count == 1
