from pathlib import Path

from src.ekokarty.detail_parser import parse_detail_page
from src.sios.models import SOURCE_SYSTEM_EKOKARTY

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://ekokarty.pl"


def test_detail_parser_maps_eighteen_field_template() -> None:
    html = (FIXTURES / "ekokarty_detail_77888.html").read_text(encoding="utf-8")
    record = parse_detail_page(
        html,
        slug="rdos-warszawa",
        card_id="77888",
        source_url="https://ekokarty.pl/wykaz/rdos-warszawa/77888/11843/X",
        base_url=BASE,
        authority="Regionalna Dyrekcja Ochrony Środowiska w Warszawie",
    )
    assert record.source_system == SOURCE_SYSTEM_EKOKARTY
    assert record.native_record_id == "rdos-warszawa:77888"
    assert record.canonical_key == "ekokarty:rdos-warszawa:77888"
    assert record.sios_id is None
    assert record.card_number == "4365/2026"
    assert record.year == 2026
    assert record.document_type == "decyzje"
    assert record.case_reference == "WPN-I.6401.389.2026.AJC"
    assert record.authority == "Regionalna Dyrekcja Ochrony Środowiska w Warszawie"
    assert record.location == "woj. mazowieckie, gmina Mszczonów"
    assert record.dates["listing_date"] == "2026-01-20"
    assert record.dates["issued_at"] == "2026-01-18"
    assert "entered_at" not in record.dates
    related = record.raw_fields["_related_cards"]
    assert related[0]["card_id"] == "77887"
    assert related[0]["card_number"] == "4364/2026"
    assert record.raw_fields["Dokument wytworzył"].startswith("Regionalny Dyrektor")


def test_detail_parser_records_attachment_url_without_downloading() -> None:
    html = (FIXTURES / "ekokarty_detail_77887.html").read_text(encoding="utf-8")
    record = parse_detail_page(
        html,
        slug="rdos-warszawa",
        card_id="77887",
        source_url="https://ekokarty.pl/wykaz/rdos-warszawa/77887/11843/X",
        base_url=BASE,
        authority="Regionalna Dyrekcja Ochrony Środowiska w Warszawie",
    )
    assert record.raw_fields["_attachments"][0]["url"].endswith("example.pdf")
    assert record.authority == "Regionalna Dyrekcja Ochrony Środowiska w Warszawie"
    assert record.raw_fields["Dokument wytworzył"] == "Osoba prywatna"
