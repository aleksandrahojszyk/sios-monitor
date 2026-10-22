from __future__ import annotations

import csv
from pathlib import Path

import pytest

from src.inbox.app import create_app
from src.inbox.query import InboxRepository
from src.inbox.reset_usability_test import main as reset_main
from src.inbox.usability import (
    UsabilitySafetyError,
    export_usability_session,
    prepare_usability_dataset,
    reset_usability_reviews,
    volunteer_sqlite_path,
)
from src.sios.storage import Storage
from tests.test_inbox_query import eko_card, sios_card


def _source_db(tmp_path: Path) -> Path:
    path = tmp_path / "volunteer" / "sios.sqlite"
    storage = Storage(path)
    storage.upsert_card(
        sios_card(
            438450,
            document_name="Zezwolenie na zniszczenie tam",
            case_reference="ST-I.6401.52.2026.RDu",
            location="małopolskie / brzeski / Czchów",
        )
    )
    storage.upsert_card(
        sios_card(
            439543,
            document_name="Wniosek o wydanie decyzji",
            location="warmińsko-mazurskie",
            document_type="wnioski o wydanie decyzji",
            card_number="1693/2026",
        )
    )
    storage.close()
    return path


def test_prepare_copies_sios_identity_and_marks_synthetic_ekokarty(
    tmp_path: Path,
) -> None:
    source = _source_db(tmp_path)
    dest = tmp_path / "usability" / "inbox.sqlite"
    result = prepare_usability_dataset(
        source_sqlite=source,
        dest_sqlite=dest,
        sios_ids=["438450", "439543", "999999"],
    )
    assert dest.resolve() != source.resolve()
    assert dest.resolve() != volunteer_sqlite_path()
    assert result["sios_copied"] == 2
    assert "999999" in result["sios_missing"]
    assert result["synthetic_ekokarty"] == 4
    assert result["total_cards"] == 6
    dest_storage = Storage(dest)
    copied = dest_storage.get_record("sios", "438450")
    assert copied["source_system"] == "sios"
    assert copied["native_record_id"] == "438450"
    assert copied["case_reference"] == "ST-I.6401.52.2026.RDu"
    assert copied["source_url"] == (
        "https://system.sios.pl/documents/details/id/438450"
    )
    eko = dest_storage.get_record("ekokarty", "rdos-warszawa:77888")
    assert eko["raw_fields"]["_usability_fixture"] == "synthetic_from_research_html"
    waste = dest_storage.get_record("ekokarty", "rdos-warszawa:usability-waste")
    assert waste["raw_fields"]["_usability_fixture"] == "synthetic"
    dest_storage.close()
    volunteer = Storage(source)
    volunteer.upsert_card(eko_card("should-not-copy"))
    volunteer.close()
    dest_after = Storage(dest)
    assert dest_after.get_record("ekokarty", "rdos-warszawa:should-not-copy") is None
    dest_after.close()


def test_reset_clears_test_reviews_only(tmp_path: Path) -> None:
    volunteer_path = tmp_path / "volunteer" / "sios.sqlite"
    volunteer = Storage(volunteer_path)
    volunteer.upsert_card(sios_card(1001))
    volunteer_repo = InboxRepository(volunteer)
    volunteer_repo.set_status("sios", "1001", "IGNORE")
    volunteer_repo.set_note("sios", "1001", "keep me")
    dest = tmp_path / "usability" / "inbox.sqlite"
    prepare_usability_dataset(
        source_sqlite=_source_db(tmp_path / "src"),
        dest_sqlite=dest,
        sios_ids=["438450"],
    )
    test_storage = Storage(dest)
    test_repo = InboxRepository(test_storage, participant_id="P01", session_id=1)
    test_repo.set_status("sios", "438450", "IGNORE")
    test_repo.set_note("sios", "438450", "test note")
    test_storage.close()
    result = reset_usability_reviews(dest, "P01")
    assert result["reviews_deleted"] == 1
    assert result["cards_preserved"] >= 1
    assert result["events_preserved"] >= 1
    reset_db = Storage(dest)
    remaining = reset_db.conn.execute(
        "SELECT COUNT(*) AS n FROM card_reviews"
    ).fetchone()["n"]
    assert remaining == 0
    events = reset_db.conn.execute(
        "SELECT COUNT(*) AS n FROM review_events"
    ).fetchone()["n"]
    assert events >= 1
    assert reset_db.get_record("sios", "438450") is not None
    reset_db.close()
    volunteer_card = volunteer_repo.get_card("sios", "1001")
    assert volunteer_card.review_status == "IGNORE"
    assert volunteer_card.review_note == "keep me"


def test_reset_refuses_volunteer_database() -> None:
    with pytest.raises(UsabilitySafetyError):
        reset_usability_reviews(volunteer_sqlite_path(), "P01")


def test_reset_cli_refuses_volunteer_path(capsys: pytest.CaptureFixture[str]) -> None:
    code = reset_main(
        ["--participant", "P01", "--sqlite", str(volunteer_sqlite_path())]
    )
    assert code == 2
    assert "volunteer" in capsys.readouterr().err.lower()


def test_session_logging_and_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "usability" / "inbox.sqlite"
    prepare_usability_dataset(
        source_sqlite=_source_db(tmp_path),
        dest_sqlite=dest,
        sios_ids=["438450"],
    )
    monkeypatch.setenv("USABILITY_TEST_MODE", "1")
    monkeypatch.setenv("PARTICIPANT_ID", "P01")
    app = create_app(sqlite_path=dest)
    app.config["TESTING"] = True
    client = app.test_client()
    listed = client.get("/")
    html = listed.get_data(as_text=True)
    assert listed.status_code == 200
    assert "Usability test" in html
    assert "P01" in html
    assert "isolated dataset" in html
    client.get("/cards/sios/438450")
    client.post(
        "/cards/sios/438450/status",
        data={"status": "IGNORE", "next": "/"},
    )
    client.post(
        "/cards/sios/438450/note",
        data={"note": "nie dotyczy bobrów", "next": "/cards/sios/438450"},
    )
    opened = client.get("/cards/sios/438450/open-source")
    assert opened.status_code == 302
    finish = client.post("/usability/finish")
    assert finish.status_code == 200
    assert "Session ended" in finish.get_data(as_text=True)
    storage = Storage(dest)
    rows = storage.conn.execute(
        """
        SELECT event_type, participant_id, session_id, previous_status, new_status
        FROM review_events ORDER BY id
        """
    ).fetchall()
    types = [row["event_type"] for row in rows]
    assert "session_started" in types
    assert "card_viewed" in types
    assert "status_changed" in types
    assert "note_updated" in types
    assert "source_opened" in types
    assert "session_finished" in types
    assert all(row["participant_id"] == "P01" for row in rows)
    assert all(row["session_id"] is not None for row in rows)
    storage.close()
    paths = export_usability_session(dest, participant_id="P01", out_dir=tmp_path)
    with paths["events"].open(encoding="utf-8") as handle:
        exported = list(csv.DictReader(handle))
    assert any(row["event_type"] == "source_opened" for row in exported)
    with paths["summary"].open(encoding="utf-8") as handle:
        summary = list(csv.DictReader(handle))
    assert summary
    assert int(summary[0]["cards_viewed"]) >= 1
    assert int(summary[0]["status_IGNORE"]) >= 1


def test_usability_mode_refuses_volunteer_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("USABILITY_TEST_MODE", "1")
    monkeypatch.setenv("PARTICIPANT_ID", "P01")
    with pytest.raises(SystemExit):
        create_app(sqlite_path=volunteer_sqlite_path())


def test_normal_inbox_does_not_show_usability_banner(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "sios.sqlite")
    storage.upsert_card(sios_card(1001))
    app = create_app(storage=storage)
    app.config["TESTING"] = True
    html = app.test_client().get("/").get_data(as_text=True)
    assert "Usability test" not in html
    assert "End session" not in html
