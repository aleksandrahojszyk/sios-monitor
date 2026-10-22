from pathlib import Path

from src.ekokarty.models import EKOKARTY_CARD_PARSER_VERSION
from src.sios.models import SOURCE_SYSTEM_EKOKARTY, SOURCE_SYSTEM_SIOS, CardRecord
from src.sios.storage import STATUS_NEW, STATUS_UNCHANGED, Storage


def sios_card(sios_id: int) -> CardRecord:
    return CardRecord(
        sios_id=sios_id,
        card_number="4365/2026",
        year=2026,
        document_name="Decyzja SIOS",
        document_type="decyzje",
        case_reference="WPN-I.6401.389.2026.AJC",
        authority="RDOŚ",
        location="mazowieckie",
        dates={"entered_at": "2026-01-20"},
        matched_keywords=["bóbr"],
        source_url="https://system.sios.pl/documents/details/id/{}".format(sios_id),
        raw_fields={"Nazwa organu": "RDOŚ"},
    )


def ekokarty_card(card_id: str, keyword: str = "Castor fiber") -> CardRecord:
    return CardRecord(
        sios_id=None,
        card_number="4365/2026",
        year=2026,
        document_name="Decyzja zezwalająca na płoszenie",
        document_type="decyzje",
        case_reference="WPN-I.6401.389.2026.AJC",
        authority="Regionalna Dyrekcja Ochrony Środowiska w Warszawie",
        location="woj. mazowieckie, gmina Mszczonów",
        dates={"listing_date": "2026-01-20", "issued_at": "2026-01-18"},
        matched_keywords=[keyword],
        source_url="https://ekokarty.pl/wykaz/rdos-warszawa/{}/11843/X".format(card_id),
        raw_fields={"Numer karty/rok": "4365/2026"},
        parser_version=EKOKARTY_CARD_PARSER_VERSION,
        source_system=SOURCE_SYSTEM_EKOKARTY,
        native_record_id="rdos-warszawa:{}".format(card_id),
    )


def test_ekokarty_and_sios_records_are_never_merged_by_similar_fields(
    tmp_path: Path,
) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    sios = storage.upsert_card(sios_card(77888), source_key="mazowieckie")
    eko = storage.upsert_card(ekokarty_card("77888"), source_key="rdos-warszawa")

    assert sios.status == STATUS_NEW
    assert eko.status == STATUS_NEW
    assert storage.card_count() == 2
    sios_row = storage.get_card(77888)
    eko_row = storage.get_record(SOURCE_SYSTEM_EKOKARTY, "rdos-warszawa:77888")
    assert sios_row["source_system"] == SOURCE_SYSTEM_SIOS
    assert sios_row["canonical_key"] == "sios:77888"
    assert eko_row["source_system"] == SOURCE_SYSTEM_EKOKARTY
    assert eko_row["canonical_key"] == "ekokarty:rdos-warszawa:77888"
    assert eko_row["sios_id"] is None
    assert eko_row["listing_date"] == "2026-01-20"
    assert eko_row["card_number"] == sios_row["card_number"]
    assert eko_row["case_reference"] == sios_row["case_reference"]


def test_card_number_is_not_the_ekokarty_identity(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    first = ekokarty_card("77888")
    second = ekokarty_card("99999")
    second.card_number = first.card_number
    second.case_reference = first.case_reference
    storage.upsert_card(first, source_key="rdos-warszawa")
    storage.upsert_card(second, source_key="rdos-warszawa")
    assert storage.card_count() == 2


def test_ekokarty_keyword_union_keeps_one_card(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    first = storage.upsert_card(ekokarty_card("77888", "bóbr"), source_key="rdos-warszawa")
    second = storage.upsert_card(
        ekokarty_card("77888", "Castor fiber"), source_key="rdos-warszawa"
    )
    assert first.status == STATUS_NEW
    assert second.status == STATUS_UNCHANGED
    stored = storage.get_record(SOURCE_SYSTEM_EKOKARTY, "rdos-warszawa:77888")
    assert stored["matched_keywords"] == ["Castor fiber", "bóbr"]
    assert stored["source_keys"] == ["rdos-warszawa"]


def test_window_complete_advances_ekokarty_watermark(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    run_id = storage.start_run(
        "Castor fiber",
        source_key="rdos-warszawa",
        window_start="2026-01-01",
        window_end="2026-01-31",
        window_mode="EXPLICIT",
    )
    storage.finish_run(
        run_id,
        pages_processed=3,
        cards_found=2,
        new_cards=2,
        status="ok",
        stop_reason="WINDOW_COMPLETE",
        window_splits=1,
    )
    capped = storage.start_run(
        "Castor fiber",
        source_key="rdos-warszawa",
        window_start="2026-01-01",
        window_end="2026-02-01",
        window_mode="EXPLICIT",
    )
    storage.finish_run(
        capped,
        pages_processed=1,
        cards_found=2000,
        new_cards=2000,
        status="partial",
        stop_reason="RESULT_CAP",
    )
    assert (
        storage.last_successful_window_end("Castor fiber", "rdos-warszawa")
        == "2026-01-31"
    )
    assert storage.last_successful_window_end("Castor fiber", "mazowieckie") is None
