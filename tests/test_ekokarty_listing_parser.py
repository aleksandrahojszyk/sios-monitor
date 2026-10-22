from pathlib import Path

from src.ekokarty.listing_parser import parse_listing_page

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://ekokarty.pl"


def test_listing_parser_uses_card_id_not_card_number() -> None:
    html = (FIXTURES / "ekokarty_listing_two_rows.html").read_text(encoding="utf-8")
    hits = parse_listing_page(
        html, keyword="Castor fiber", slug="rdos-warszawa", base_url=BASE
    )
    assert [hit.card_id for hit in hits] == ["77888", "77887"]
    assert [hit.native_record_id for hit in hits] == [
        "rdos-warszawa:77888",
        "rdos-warszawa:77887",
    ]
    assert [hit.canonical_key for hit in hits] == [
        "ekokarty:rdos-warszawa:77888",
        "ekokarty:rdos-warszawa:77887",
    ]
    assert hits[0].card_number == "4365/2026"
    assert hits[0].listing_date == "2026-01-20"
    assert hits[0].secondary_id == "11843"
    assert hits[0].detail_url.endswith("/wykaz/rdos-warszawa/77888/11843/X")


def test_listing_parser_ignores_rows_from_other_institutions() -> None:
    html = """
    <table id="tableKarty">
      <tr><th>Numer karty</th><th>Data karty</th></tr>
      <tr data-href="/wykaz/other-slug/1/2/X"><td>1/2026</td><td>2026-01-01</td></tr>
      <tr data-href="/wykaz/rdos-warszawa/9/8/X"><td>2/2026</td><td>2026-01-02</td></tr>
    </table>
    """
    hits = parse_listing_page(
        html, keyword="bóbr", slug="rdos-warszawa", base_url=BASE
    )
    assert [hit.card_id for hit in hits] == ["9"]


def test_empty_listing_is_complete_zero() -> None:
    html = (FIXTURES / "ekokarty_listing_empty.html").read_text(encoding="utf-8")
    hits = parse_listing_page(
        html, keyword="bobry", slug="rdos-warszawa", base_url=BASE
    )
    assert hits == []
