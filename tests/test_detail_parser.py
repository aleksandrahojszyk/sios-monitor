from __future__ import annotations

from pathlib import Path

from src.sios.detail_parser import parse_detail_page

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://system.sios.pl"


def test_parse_card_metadata() -> None:
    html = (FIXTURES / "detail_449913.html").read_text(encoding="utf-8")
    record = parse_detail_page(
        html,
        sios_id=449913,
        source_url="https://system.sios.pl/documents/details/id/449913",
        base_url=BASE,
    )
    assert record.sios_id == 449913
    assert record.card_number == "2047/2026"
    assert record.year == 2026
    assert record.document_name == "Decyzja"
    assert record.document_type == "decyzje"
    assert record.case_reference == "WOPN.6401.7.79.2026.ASM.3"
    assert record.authority == "Regionalna Dyrekcja Ochrony Środowiska w Olsztynie"
    assert record.location == "warmińsko-mazurskie / olsztyński / Dywity"
    assert record.dates["issued_at"] == "2026-10-06"
    assert record.dates["received_at"] is None
    assert record.raw_fields["Informacja może być udostępniona"] == "TAK"
    assert record.raw_fields["Imię i nazwisko"] == "Kamila Kutryb"
    related = record.raw_fields["_related_cards"]
    assert related[0]["sios_id"] == 449844


def test_missing_optional_fields_are_null() -> None:
    html = (FIXTURES / "detail_minimal.html").read_text(encoding="utf-8")
    record = parse_detail_page(
        html,
        sios_id=12,
        source_url="https://system.sios.pl/documents/details/id/12",
        base_url=BASE,
    )
    assert record.card_number == "12/2018"
    assert record.year == 2018
    assert record.document_name is None
    assert record.document_type is None
    assert record.case_reference is None
    assert record.authority is None
    assert record.location is None
    assert record.raw_fields["Informacja może być udostępniona"] == "TAK"


def test_attachment_links_preserved_in_raw_fields() -> None:
    html = (FIXTURES / "detail_with_attachment.html").read_text(encoding="utf-8")
    record = parse_detail_page(
        html,
        sios_id=449707,
        source_url="https://system.sios.pl/documents/details/id/449707",
        base_url=BASE,
    )
    attachments = record.raw_fields["_attachments"]
    assert attachments[0]["file_id"] == 27565
    assert attachments[0]["filename"] == "wop.6401.2.116.2026.dwa_wniosek.pdf"
    assert "wop.6401.2.116.2026.dwa_wniosek.pdf" in record.raw_fields["Wersja elektroniczna"]
