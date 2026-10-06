from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.sios.models import CardRecord
from src.sios.storage import (
    CHANGE_ORIGIN_PARSER_BASELINE,
    CHANGE_ORIGIN_SOURCE,
    STATUS_CHANGED,
    STATUS_NEW,
    STATUS_UNCHANGED,
    Storage,
)


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
    assert first.status == STATUS_NEW
    row = storage.get_card(449913)
    assert row is not None
    first_seen = row["first_seen_at"]
    second = storage.upsert_card(sample_card(449913, "Castor fiber", "Decyzja zaktualizowana"))
    assert second.created is False
    assert second.status == STATUS_CHANGED
    again = storage.get_card(449913)
    assert again is not None
    assert again["first_seen_at"] == first_seen
    assert again["document_name"] == "Decyzja zaktualizowana"
    assert storage.card_count() == 1
    assert again["matched_keywords"] == ["Castor fiber", "bóbr"]


def test_multiple_keyword_matches(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    storage.upsert_card(sample_card(1, "bóbr"))
    second = storage.upsert_card(sample_card(1, "bobry"))
    third = storage.upsert_card(sample_card(1, "bóbr"))
    assert second.status == STATUS_UNCHANGED
    assert third.status == STATUS_UNCHANGED
    assert storage.keywords_for(1) == ["bobry", "bóbr"]


def _clock(monkeypatch: pytest.MonkeyPatch, stamps: list[str]) -> None:
    pending = iter(stamps)

    def fake_now() -> str:
        return next(pending)

    monkeypatch.setattr("src.sios.storage.utc_now", fake_now)


def test_observations_record_new_unchanged_and_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    _clock(
        monkeypatch,
        [
            "2026-10-06T10:00:00+00:00",
            "2026-10-06T10:00:01+00:00",
            "2026-10-06T10:00:02+00:00",
            "2026-10-06T10:00:03+00:00",
            "2026-10-06T10:00:04+00:00",
            "2026-10-06T10:00:05+00:00",
        ],
    )
    dates = {"issued_at": "2026-10-06", "received_at": "2026-10-01"}
    raw_fields = {"Uwagi": "brak", "Nazwa organu": "RDOŚ"}

    def card(name: str = "Decyzja") -> CardRecord:
        record = sample_card(449913, "bóbr", name=name)
        record.dates = dict(dates)
        record.raw_fields = dict(raw_fields)
        return record

    original = card()

    run_new = storage.start_run("bóbr")
    first = storage.upsert_card(original, run_id=run_new)
    assert first.status == STATUS_NEW
    assert first.changed_fields is None

    stored_json = storage.conn.execute(
        "SELECT dates_json, raw_fields_json, first_seen_at FROM cards WHERE sios_id = 449913"
    ).fetchone()
    assert stored_json["first_seen_at"] == "2026-10-06T10:00:01+00:00"
    # Same objects, different key order and spacing. This must not count as a change.
    storage.conn.execute(
        """
        UPDATE cards
        SET dates_json = ?, raw_fields_json = ?
        WHERE sios_id = 449913
        """,
        (
            '{"received_at":"2026-10-01","issued_at":"2026-10-06"}',
            '{"Nazwa organu":"RDOŚ","Uwagi":"brak"}',
        ),
    )
    storage.conn.commit()

    run_same = storage.start_run("bóbr")
    second = storage.upsert_card(card(), run_id=run_same)
    assert second.status == STATUS_UNCHANGED
    assert second.changed_fields is None
    assert second.content_hash == first.content_hash

    after_same = storage.conn.execute(
        """
        SELECT dates_json, raw_fields_json, document_name, first_seen_at, last_seen_at
        FROM cards WHERE sios_id = 449913
        """
    ).fetchone()
    assert after_same["dates_json"] == '{"received_at":"2026-10-01","issued_at":"2026-10-06"}'
    assert after_same["raw_fields_json"] == '{"Nazwa organu":"RDOŚ","Uwagi":"brak"}'
    assert after_same["document_name"] == "Decyzja"
    assert after_same["first_seen_at"] == "2026-10-06T10:00:01+00:00"
    assert after_same["last_seen_at"] == "2026-10-06T10:00:03+00:00"

    run_changed = storage.start_run("bóbr")
    third = storage.upsert_card(card("Decyzja zaktualizowana"), run_id=run_changed)
    assert third.status == STATUS_CHANGED
    assert third.changed_fields == {
        "document_name": {"old": "Decyzja", "new": "Decyzja zaktualizowana"}
    }
    assert third.content_hash != first.content_hash

    after_change = storage.get_card(449913)
    assert after_change is not None
    assert after_change["first_seen_at"] == "2026-10-06T10:00:01+00:00"
    assert after_change["last_seen_at"] == "2026-10-06T10:00:05+00:00"
    assert after_change["document_name"] == "Decyzja zaktualizowana"

    observations = storage.observations_for(449913)
    assert [item["run_id"] for item in observations] == [run_new, run_same, run_changed]
    assert [item["status"] for item in observations] == [
        STATUS_NEW,
        STATUS_UNCHANGED,
        STATUS_CHANGED,
    ]
    assert [item["observed_at"] for item in observations] == [
        "2026-10-06T10:00:01+00:00",
        "2026-10-06T10:00:03+00:00",
        "2026-10-06T10:00:05+00:00",
    ]
    assert observations[0]["changed_fields"] is None
    assert observations[1]["changed_fields"] is None
    assert observations[2]["changed_fields"]["document_name"] == {
        "old": "Decyzja",
        "new": "Decyzja zaktualizowana",
    }
    assert observations[2]["change_origin"] == CHANGE_ORIGIN_SOURCE


def test_parser_version_change_establishes_baseline_before_source_changes(
    tmp_path: Path,
) -> None:
    storage = Storage(tmp_path / "sios.sqlite")

    original = sample_card(449913, "bóbr", "Decyzja")
    original.parser_version = "1"
    run_new = storage.start_run("bóbr")
    assert storage.upsert_card(original, run_id=run_new).status == STATUS_NEW
    first_seen = storage.get_card(449913)["first_seen_at"]

    parser_evolved = sample_card(449913, "bóbr", "Decyzja po nowym parserze")
    parser_evolved.parser_version = "2"
    parser_evolved.raw_fields["Nowe pole parsera"] = "wartość"
    run_baseline = storage.start_run("bóbr")
    baseline = storage.upsert_card(parser_evolved, run_id=run_baseline)
    assert baseline.status == STATUS_UNCHANGED
    assert baseline.change_origin == CHANGE_ORIGIN_PARSER_BASELINE
    assert "document_name" in baseline.changed_fields
    assert "raw_fields.Nowe pole parsera" in baseline.changed_fields
    after_baseline = storage.get_card(449913)
    assert after_baseline["parser_version"] == "2"
    assert after_baseline["first_seen_at"] == first_seen

    source_changed = sample_card(449913, "bóbr", "Rzeczywista zmiana SIOS")
    source_changed.parser_version = "2"
    source_changed.raw_fields["Nowe pole parsera"] = "wartość"
    run_changed = storage.start_run("bóbr")
    changed = storage.upsert_card(source_changed, run_id=run_changed)
    assert changed.status == STATUS_CHANGED
    assert changed.change_origin == CHANGE_ORIGIN_SOURCE
    assert changed.changed_fields["document_name"] == {
        "old": "Decyzja po nowym parserze",
        "new": "Rzeczywista zmiana SIOS",
    }

    observations = storage.observations_for(449913)
    assert [item["status"] for item in observations] == [
        STATUS_NEW,
        STATUS_UNCHANGED,
        STATUS_CHANGED,
    ]
    assert [item["parser_version"] for item in observations] == ["1", "2", "2"]
    assert [item["change_origin"] for item in observations] == [
        None,
        CHANGE_ORIGIN_PARSER_BASELINE,
        CHANGE_ORIGIN_SOURCE,
    ]


def test_finish_run_stores_change_counts(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    run_id = storage.start_run("bóbr")
    storage.finish_run(
        run_id,
        pages_processed=1,
        cards_found=3,
        new_cards=1,
        changed_cards=1,
        unchanged_cards=1,
        existing_cards=2,
        error_count=0,
        reported_total=3115,
        stop_reason="MAX_PAGES",
        cards_encountered=5,
        cards_in_window=3,
        cards_skipped_too_old=1,
        cards_skipped_too_new=1,
        known_cards_skipped=2,
        detail_pages_fetched=3,
        status="ok",
    )
    row = storage.conn.execute(
        """
        SELECT new_cards, changed_cards, unchanged_cards, existing_cards,
               error_count, reported_total, stop_reason, cards_encountered,
               cards_in_window, cards_skipped_too_old, cards_skipped_too_new,
               known_cards_skipped, detail_pages_fetched
        FROM collection_runs WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    assert tuple(row) == (
        1, 1, 1, 2, 0, 3115, "MAX_PAGES", 5, 3, 1, 1, 2, 3
    )


def test_failed_or_incomplete_run_does_not_advance_watermark(
    tmp_path: Path,
) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    successful = storage.start_run(
        "bóbr",
        window_start="2026-08-01",
        window_end="2026-09-01",
        window_mode="EXPLICIT",
    )
    storage.finish_run(
        successful,
        pages_processed=2,
        cards_found=10,
        new_cards=10,
        status="ok",
        stop_reason="WINDOW_PASSED",
    )
    failed = storage.start_run(
        "bóbr",
        window_start="2026-08-31",
        window_end="2026-10-01",
        window_mode="AUTOMATIC",
        watermark_used="2026-09-01",
        overlap_days=1,
    )
    storage.finish_run(
        failed,
        pages_processed=1,
        cards_found=0,
        new_cards=0,
        status="error",
        error_count=1,
        stop_reason="ORDERING_UNSAFE",
    )
    capped = storage.start_run(
        "bóbr",
        window_start="2026-08-31",
        window_end="2026-10-02",
        window_mode="AUTOMATIC",
        watermark_used="2026-09-01",
        overlap_days=1,
    )
    storage.finish_run(
        capped,
        pages_processed=1,
        cards_found=2,
        new_cards=2,
        status="ok",
        stop_reason="MAX_PAGES",
    )

    assert storage.last_successful_window_end("bóbr") == "2026-09-01"
    assert storage.last_successful_window_end("Castor fiber") is None


def test_existing_database_gains_observation_columns(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        CREATE TABLE collection_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            keyword TEXT,
            pages_processed INTEGER NOT NULL DEFAULT 0,
            cards_found INTEGER NOT NULL DEFAULT 0,
            new_cards INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    storage = Storage(path)
    columns = [
        row["name"] for row in storage.conn.execute("PRAGMA table_info(collection_runs)")
    ]
    assert "changed_cards" in columns
    assert "unchanged_cards" in columns
    assert "existing_cards" in columns
    assert "error_count" in columns
    assert "reported_total" in columns
    assert "stop_reason" in columns
    assert "window_start" in columns
    assert "window_end" in columns
    assert "window_mode" in columns
    assert "watermark_used" in columns
    assert "overlap_days" in columns
    assert "cards_encountered" in columns
    assert "cards_in_window" in columns
    assert "cards_skipped_too_old" in columns
    assert "cards_skipped_too_new" in columns
    assert "known_cards_skipped" in columns
    assert "detail_pages_fetched" in columns
    tables = {
        row["name"]
        for row in storage.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "card_observations" in tables
    assert "cards" in tables
    card_columns = {
        row["name"] for row in storage.conn.execute("PRAGMA table_info(cards)")
    }
    observation_columns = {
        row["name"]
        for row in storage.conn.execute("PRAGMA table_info(card_observations)")
    }
    assert "parser_version" in card_columns
    assert "parser_version" in observation_columns
    assert "change_origin" in observation_columns
