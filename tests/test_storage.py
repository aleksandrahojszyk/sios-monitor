from __future__ import annotations

from pathlib import Path

from src.sios.models import CardRecord
from src.sios.storage import Storage


def sample_card(sios_id: int, keyword: str, name: str = "Decyzja") -> CardRecord:
    return CardRecord(
        sios_id=sios_id,
        card_number="2047/2026",
        year=2026,
        document_name=name,
        document_type="decyzje",
        case_reference="WOPN.1",
        authority="RDOŚ",
        location="warmińsko-mazurskie / olsztyński / Dywity",
        dates={"issued_at": "2026-10-06"},
        matched_keywords=[keyword],
        source_url=f"https://system.sios.pl/documents/details/id/{sios_id}",
        raw_fields={"Nazwa organu": "RDOŚ"},
    )


def test_duplicate_sios_id_is_updated_not_inserted(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    first = storage.upsert_card(sample_card(449913, "bóbr", "Decyzja"))
    assert first.created is True
    row = storage.get_card(449913)
    assert row is not None
    first_seen = row["first_seen_at"]
    second = storage.upsert_card(sample_card(449913, "Castor fiber", "Decyzja zaktualizowana"))
    assert second.created is False
    again = storage.get_card(449913)
    assert again is not None
    assert again["first_seen_at"] == first_seen
    assert again["document_name"] == "Decyzja zaktualizowana"
    assert storage.card_count() == 1
    assert again["matched_keywords"] == ["Castor fiber", "bóbr"]


def test_multiple_keyword_matches(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    storage.upsert_card(sample_card(1, "bóbr"))
    storage.upsert_card(sample_card(1, "bobry"))
    storage.upsert_card(sample_card(1, "bóbr"))
    assert storage.keywords_for(1) == ["bobry", "bóbr"]
