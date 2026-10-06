from __future__ import annotations

from pathlib import Path

import pytest

from src.sios.models import pagination_decision
from src.sios.search_parser import parse_search_page, parse_total_count

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://system.sios.pl"


def test_extract_card_ids_from_search_page() -> None:
    html = (FIXTURES / "search_page_1.html").read_text(encoding="utf-8")
    hits = parse_search_page(html, keyword="bóbr", base_url=BASE)
    assert [hit.sios_id for hit in hits] == [449913, 449844, 434045]
    assert parse_total_count(html) == 3


def test_same_card_number_is_not_collapsed() -> None:
    html = (FIXTURES / "search_page_1.html").read_text(encoding="utf-8")
    hits = parse_search_page(html, keyword="bóbr", base_url=BASE)
    numbers = [hit.card_number for hit in hits]
    assert numbers.count("2047/2026") == 2
    assert {hit.sios_id for hit in hits if hit.card_number == "2047/2026"} == {449913, 434045}


def test_search_fields_and_year() -> None:
    html = (FIXTURES / "search_page_1.html").read_text(encoding="utf-8")
    hits = {hit.sios_id: hit for hit in parse_search_page(html, keyword="bóbr", base_url=BASE)}
    first = hits[449913]
    assert first.year == 2026
    assert first.document_type == "decyzje"
    assert first.document_name == "Decyzja"
    assert "ochrona zwierząt oraz roślin" in first.topics
    assert first.case_reference == "WOPN.6401.7.79.2026.ASM.3"
    assert first.date is None
    assert first.voivodeship == "warmińsko-mazurskie"
    assert first.county == "olsztyński"
    assert first.municipality == "Dywity"
    assert first.detail_url.endswith("/documents/details/id/449913")
    assert first.keyword == "bóbr"
    second = hits[449844]
    assert second.date == "2026-09-16"
    empty_geo = hits[434045]
    assert empty_geo.voivodeship == "śląskie"
    assert empty_geo.county is None


def test_empty_search_page() -> None:
    html = (FIXTURES / "search_empty.html").read_text(encoding="utf-8")
    assert parse_search_page(html, keyword="bóbr", base_url=BASE) == []
    assert parse_total_count(html) is None


def test_pagination_repeated_page_stops() -> None:
    page1 = [449913, 449844, 434045]
    decision = pagination_decision(page1, previous_ids=None, seen_ids=set())
    assert decision.stop is False
    seen = set(decision.new_ids)
    repeated = pagination_decision(page1, previous_ids=set(page1), seen_ids=seen)
    assert repeated.stop is True
    assert repeated.reason == "repeated_page"


def test_pagination_empty_and_no_new_ids() -> None:
    empty = pagination_decision([], previous_ids={1}, seen_ids={1})
    assert empty.reason == "empty_page"
    no_new = pagination_decision([1, 2], previous_ids={9, 8}, seen_ids={1, 2, 3})
    assert no_new.reason == "no_new_ids"


def test_within_page_duplicate_hrefs_are_unique() -> None:
    html = (FIXTURES / "search_page_1.html").read_text(encoding="utf-8")
    hits = parse_search_page(html, keyword="bóbr", base_url=BASE)
    assert len(hits) == len({hit.sios_id for hit in hits})
