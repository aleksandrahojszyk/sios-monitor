"""Isolated usability-test dataset, sessions, reset, and CSV export.

This is test-harness code. It does not add Inbox product features.
"""
from __future__ import annotations

import csv
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.ekokarty.detail_parser import parse_detail_page
from src.ekokarty.models import EKOKARTY_CARD_PARSER_VERSION
from src.sios.config import PROJECT_ROOT, load_settings, load_yaml
from src.sios.models import SOURCE_SYSTEM_EKOKARTY, SOURCE_SYSTEM_SIOS, CardRecord
from src.sios.storage import Storage, utc_now

DEFAULT_DATASET_CONFIG = PROJECT_ROOT / "config" / "usability_dataset.yaml"
DEFAULT_USABILITY_SQLITE = PROJECT_ROOT / "data" / "usability" / "inbox.sqlite"
USABILITY_EXPORT_DIR = PROJECT_ROOT / "data" / "usability"
PARTICIPANT_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
TRUE_ENV = {"1", "true", "yes", "on"}

SESSION_PLACEHOLDER_SOURCE = "usability"
EVENT_SESSION_STARTED = "session_started"
EVENT_SESSION_FINISHED = "session_finished"


class UsabilitySafetyError(RuntimeError):
    """Refusing to touch the volunteer collector/review database."""


def usability_mode_enabled(environ: Optional[dict[str, str]] = None) -> bool:
    env = environ if environ is not None else os.environ
    return str(env.get("USABILITY_TEST_MODE") or "").strip().lower() in TRUE_ENV


def resolve_participant_id(environ: Optional[dict[str, str]] = None) -> str:
    env = environ if environ is not None else os.environ
    raw = str(env.get("PARTICIPANT_ID") or "P01").strip() or "P01"
    return normalize_participant_id(raw)


def normalize_participant_id(raw: str) -> str:
    text = (raw or "").strip()
    if not PARTICIPANT_RE.fullmatch(text):
        raise ValueError(
            "participant_id must be 1–32 letters, digits, underscores, or hyphens"
        )
    return text


def volunteer_sqlite_path() -> Path:
    return load_settings().sqlite_path.resolve()


def usability_sqlite_path() -> Path:
    return DEFAULT_USABILITY_SQLITE.resolve()


def assert_not_volunteer_db(path: Path) -> None:
    resolved = path.resolve()
    volunteer = volunteer_sqlite_path()
    if resolved == volunteer:
        raise UsabilitySafetyError(
            "Refusing to use the volunteer database {}. "
            "Usability tests must use data/usability/inbox.sqlite.".format(volunteer)
        )


def load_sios_ids(config_path: Optional[Path] = None) -> list[str]:
    data = load_yaml(config_path or DEFAULT_DATASET_CONFIG)
    ids = data.get("sios_native_record_ids") or []
    return [str(item) for item in ids]


def _copy_rows(
    source: sqlite3.Connection,
    dest: sqlite3.Connection,
    table: str,
    where_sql: str,
    params: list[Any],
) -> int:
    source_cols = [
        row["name"] for row in source.execute("PRAGMA table_info({})".format(table))
    ]
    dest_cols = [
        row["name"] for row in dest.execute("PRAGMA table_info({})".format(table))
    ]
    cols = [name for name in source_cols if name in dest_cols]
    if not cols:
        return 0
    select_sql = "SELECT {} FROM {} WHERE {}".format(
        ", ".join(cols), table, where_sql
    )
    rows = source.execute(select_sql, params).fetchall()
    if not rows:
        return 0
    placeholders = ", ".join("?" for _ in cols)
    insert_sql = "INSERT OR REPLACE INTO {} ({}) VALUES ({})".format(
        table, ", ".join(cols), placeholders
    )
    copied = 0
    for row in rows:
        dest.execute(insert_sql, [row[name] for name in cols])
        copied += 1
    return copied


def _mark_fixture(record: CardRecord, kind: str) -> CardRecord:
    raw = dict(record.raw_fields)
    raw["_usability_fixture"] = kind
    record.raw_fields = raw
    return record


def _research_ekokarty_from_html(
    fixture_name: str,
    card_id: str,
    source_url: str,
    keywords: list[str],
) -> CardRecord:
    html_path = PROJECT_ROOT / "tests" / "fixtures" / fixture_name
    html = html_path.read_text(encoding="utf-8")
    record = parse_detail_page(
        html,
        slug="rdos-warszawa",
        card_id=card_id,
        source_url=source_url,
        base_url="https://ekokarty.pl",
        authority="Regionalna Dyrekcja Ochrony Środowiska w Warszawie",
    )
    record.matched_keywords = list(keywords)
    record.parser_version = EKOKARTY_CARD_PARSER_VERSION
    return _mark_fixture(record, "synthetic_from_research_html")


def synthetic_ekokarty_records() -> list[CardRecord]:
    """EkoKarty Warszawa sample. Not copied from a live bounded collect.

    77888/77887 reuse research HTML fixtures and keep adapter identity.
    The other two cards are invented fixtures for IGNORE and missing-location tasks.
    """
    decision = _research_ekokarty_from_html(
        "ekokarty_detail_77888.html",
        "77888",
        "https://ekokarty.pl/wykaz/rdos-warszawa/77888/11843/X",
        ["Castor fiber"],
    )
    application = _research_ekokarty_from_html(
        "ekokarty_detail_77887.html",
        "77887",
        "https://ekokarty.pl/wykaz/rdos-warszawa/77887/11843/X",
        ["Castor fiber"],
    )
    waste = CardRecord(
        sios_id=None,
        card_number="SYN-1/2026",
        year=2026,
        document_name=(
            "Decyzja o środowiskowych uwarunkowaniach dla punktu "
            "zbiórki odpadów komunalnych"
        ),
        document_type="decyzje",
        case_reference="WOOŚ-I.420.12.2026.SYN",
        authority="Regionalna Dyrekcja Ochrony Środowiska w Warszawie",
        location="woj. mazowieckie, gmina Legionowo",
        dates={"listing_date": "2026-02-03", "issued_at": "2026-02-01"},
        matched_keywords=[],
        source_url="",
        raw_fields={
            "Numer karty/rok": "SYN-1/2026",
            "Rodzaj dokumentu": "decyzje",
            "Nazwa dokumentu": (
                "Decyzja o środowiskowych uwarunkowaniach dla punktu "
                "zbiórki odpadów komunalnych"
            ),
            "Znak sprawy": "WOOŚ-I.420.12.2026.SYN",
            "_usability_fixture": "synthetic",
            "_related_cards": [],
        },
        parser_version=EKOKARTY_CARD_PARSER_VERSION,
        source_system=SOURCE_SYSTEM_EKOKARTY,
        native_record_id="rdos-warszawa:usability-waste",
    )
    no_geo = CardRecord(
        sios_id=None,
        card_number="SYN-2/2026",
        year=2026,
        document_name="Zezwolenie na płoszenie bobra europejskiego (Castor fiber)",
        document_type="decyzje",
        case_reference="WPN-I.6401.999.2026.SYN",
        authority="Regionalna Dyrekcja Ochrony Środowiska w Warszawie",
        location=None,
        dates={"listing_date": "2026-03-12", "issued_at": "2026-03-10"},
        matched_keywords=["Castor fiber"],
        source_url="",
        raw_fields={
            "Numer karty/rok": "SYN-2/2026",
            "Rodzaj dokumentu": "decyzje",
            "Nazwa dokumentu": (
                "Zezwolenie na płoszenie bobra europejskiego (Castor fiber)"
            ),
            "Znak sprawy": "WPN-I.6401.999.2026.SYN",
            "_usability_fixture": "synthetic",
            "_attachments": [
                {
                    "url": "",
                    "filename": "uzasadnienie.pdf",
                    "source": "synthetic_usability",
                }
            ],
        },
        parser_version=EKOKARTY_CARD_PARSER_VERSION,
        source_system=SOURCE_SYSTEM_EKOKARTY,
        native_record_id="rdos-warszawa:usability-nogeo",
    )
    return [decision, application, waste, no_geo]


def prepare_usability_dataset(
    *,
    source_sqlite: Optional[Path] = None,
    dest_sqlite: Optional[Path] = None,
    sios_ids: Optional[list[str]] = None,
    include_synthetic_ekokarty: bool = True,
) -> dict[str, Any]:
    source_path = (source_sqlite or volunteer_sqlite_path()).resolve()
    dest_path = (dest_sqlite or usability_sqlite_path()).resolve()
    assert_not_volunteer_db(dest_path)
    if source_path == dest_path:
        raise UsabilitySafetyError(
            "Source and destination SQLite paths must be different"
        )
    if not source_path.exists():
        raise FileNotFoundError(
            "Collector SQLite not found at {}. Collect SIOS cards first.".format(
                source_path
            )
        )
    ids = list(sios_ids or load_sios_ids())
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(source_path))
    source.row_factory = sqlite3.Row
    dest_storage = Storage(dest_path)
    try:
        copied = 0
        missing: list[str] = []
        if ids:
            placeholders = ", ".join("?" for _ in ids)
            dest_storage.conn.execute(
                """
                DELETE FROM keyword_matches
                WHERE source_system = 'sios' AND native_record_id IN ({})
                """.format(placeholders),
                ids,
            )
            dest_storage.conn.execute(
                """
                DELETE FROM record_sources
                WHERE source_system = 'sios' AND native_record_id IN ({})
                """.format(placeholders),
                ids,
            )
            copied = _copy_rows(
                source,
                dest_storage.conn,
                "cards",
                "source_system = 'sios' AND native_record_id IN ({})".format(
                    placeholders
                ),
                ids,
            )
            found = {
                row["native_record_id"]
                for row in dest_storage.conn.execute(
                    """
                    SELECT native_record_id FROM cards
                    WHERE source_system = 'sios' AND native_record_id IN ({})
                    """.format(placeholders),
                    ids,
                )
            }
            missing = [item for item in ids if item not in found]
            _copy_rows(
                source,
                dest_storage.conn,
                "keyword_matches",
                "source_system = 'sios' AND native_record_id IN ({})".format(
                    placeholders
                ),
                ids,
            )
            _copy_rows(
                source,
                dest_storage.conn,
                "record_sources",
                "source_system = 'sios' AND native_record_id IN ({})".format(
                    placeholders
                ),
                ids,
            )
        synthetic = 0
        if include_synthetic_ekokarty:
            for record in synthetic_ekokarty_records():
                dest_storage.upsert_card(record)
                synthetic += 1
        dest_storage.conn.commit()
        total = int(
            dest_storage.conn.execute(
                "SELECT COUNT(*) AS n FROM cards"
            ).fetchone()["n"]
        )
        eko = int(
            dest_storage.conn.execute(
                "SELECT COUNT(*) AS n FROM cards WHERE source_system = ?",
                (SOURCE_SYSTEM_EKOKARTY,),
            ).fetchone()["n"]
        )
        sios = int(
            dest_storage.conn.execute(
                "SELECT COUNT(*) AS n FROM cards WHERE source_system = ?",
                (SOURCE_SYSTEM_SIOS,),
            ).fetchone()["n"]
        )
    finally:
        source.close()
        dest_storage.close()
    return {
        "source": str(source_path),
        "dest": str(dest_path),
        "sios_copied": copied,
        "sios_missing": missing,
        "synthetic_ekokarty": synthetic,
        "total_cards": total,
        "sios_cards": sios,
        "ekokarty_cards": eko,
    }


def start_or_resume_session(
    conn: sqlite3.Connection,
    participant_id: str,
) -> int:
    participant_id = normalize_participant_id(participant_id)
    existing = conn.execute(
        """
        SELECT id FROM usability_sessions
        WHERE participant_id = ? AND finished_at IS NULL
        ORDER BY id DESC LIMIT 1
        """,
        (participant_id,),
    ).fetchone()
    if existing is not None:
        return int(existing["id"])
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO usability_sessions (participant_id, started_at, finished_at)
        VALUES (?, ?, NULL)
        """,
        (participant_id, now),
    )
    session_id = int(cursor.lastrowid)
    conn.execute(
        """
        INSERT INTO review_events (
            source_system, native_record_id, event_type,
            previous_status, new_status, created_at,
            participant_id, session_id
        ) VALUES (?, ?, ?, NULL, NULL, ?, ?, ?)
        """,
        (
            SESSION_PLACEHOLDER_SOURCE,
            participant_id,
            EVENT_SESSION_STARTED,
            now,
            participant_id,
            session_id,
        ),
    )
    conn.commit()
    return session_id


def finish_open_sessions(
    conn: sqlite3.Connection,
    participant_id: Optional[str] = None,
) -> int:
    now = utc_now()
    if participant_id:
        participant_id = normalize_participant_id(participant_id)
        open_rows = conn.execute(
            """
            SELECT id, participant_id FROM usability_sessions
            WHERE participant_id = ? AND finished_at IS NULL
            """,
            (participant_id,),
        ).fetchall()
    else:
        open_rows = conn.execute(
            """
            SELECT id, participant_id FROM usability_sessions
            WHERE finished_at IS NULL
            """
        ).fetchall()
    for row in open_rows:
        conn.execute(
            "UPDATE usability_sessions SET finished_at = ? WHERE id = ?",
            (now, int(row["id"])),
        )
        conn.execute(
            """
            INSERT INTO review_events (
                source_system, native_record_id, event_type,
                previous_status, new_status, created_at,
                participant_id, session_id
            ) VALUES (?, ?, ?, NULL, NULL, ?, ?, ?)
            """,
            (
                SESSION_PLACEHOLDER_SOURCE,
                row["participant_id"],
                EVENT_SESSION_FINISHED,
                now,
                row["participant_id"],
                int(row["id"]),
            ),
        )
    conn.commit()
    return len(open_rows)


def reset_usability_reviews(
    sqlite_path: Path,
    participant_id: str,
) -> dict[str, Any]:
    path = sqlite_path.resolve()
    assert_not_volunteer_db(path)
    if not path.exists():
        raise FileNotFoundError("Usability SQLite not found at {}".format(path))
    storage = Storage(path)
    try:
        participant_id = normalize_participant_id(participant_id)
        finished = finish_open_sessions(storage.conn, participant_id=None)
        reviews = storage.conn.execute(
            "SELECT COUNT(*) AS n FROM card_reviews"
        ).fetchone()["n"]
        storage.conn.execute("DELETE FROM card_reviews")
        storage.conn.commit()
        remaining_cards = storage.conn.execute(
            "SELECT COUNT(*) AS n FROM cards"
        ).fetchone()["n"]
        remaining_events = storage.conn.execute(
            "SELECT COUNT(*) AS n FROM review_events"
        ).fetchone()["n"]
    finally:
        storage.close()
    return {
        "sqlite_path": str(path),
        "participant_id": participant_id,
        "reviews_deleted": int(reviews),
        "sessions_finished": finished,
        "cards_preserved": int(remaining_cards),
        "events_preserved": int(remaining_events),
    }


def _session_rows(
    conn: sqlite3.Connection,
    participant_id: Optional[str],
) -> list[sqlite3.Row]:
    if participant_id:
        return list(
            conn.execute(
                """
                SELECT * FROM usability_sessions
                WHERE participant_id = ?
                ORDER BY id
                """,
                (participant_id,),
            )
        )
    return list(
        conn.execute("SELECT * FROM usability_sessions ORDER BY id")
    )


def _derive_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    viewed: set[str] = set()
    source_opened: set[str] = set()
    status_counts = {
        "IGNORE": 0,
        "RELEVANT": 0,
        "MONITOR": 0,
        "REQUEST_DOCUMENTS": 0,
        "NEW": 0,
    }
    reversals = 0
    notes = 0
    first_ts: Optional[str] = None
    tenth_view_ts: Optional[str] = None
    last_ts: Optional[str] = None
    for event in events:
        created = event.get("created_at")
        if created:
            if first_ts is None:
                first_ts = created
            last_ts = created
        key = "{}:{}".format(
            event.get("source_system") or "",
            event.get("native_record_id") or "",
        )
        etype = event.get("event_type")
        if etype == "card_viewed":
            if key not in viewed:
                viewed.add(key)
                if len(viewed) == 10:
                    tenth_view_ts = created
        elif etype == "source_opened":
            source_opened.add(key)
        elif etype == "note_updated":
            notes += 1
        elif etype == "status_changed":
            new_status = event.get("new_status") or ""
            previous = event.get("previous_status") or ""
            if new_status in status_counts:
                status_counts[new_status] += 1
            if previous and previous != "NEW" and previous != new_status:
                reversals += 1
    seconds_to_10 = None
    avg_per_card = None
    if first_ts and tenth_view_ts:
        seconds_to_10 = _seconds_between(first_ts, tenth_view_ts)
    if first_ts and last_ts and viewed:
        elapsed = _seconds_between(first_ts, last_ts)
        if elapsed is not None and elapsed > 0:
            avg_per_card = round(elapsed / max(len(viewed), 1), 1)
    reviewed_without_source = len(viewed - source_opened)
    return {
        "cards_viewed": len(viewed),
        "source_pages_opened": len(source_opened),
        "cards_reviewed_without_opening_source": reviewed_without_source,
        "notes_added": notes,
        "status_IGNORE": status_counts["IGNORE"],
        "status_RELEVANT": status_counts["RELEVANT"],
        "status_MONITOR": status_counts["MONITOR"],
        "status_REQUEST_DOCUMENTS": status_counts["REQUEST_DOCUMENTS"],
        "status_back_to_NEW": status_counts["NEW"],
        "status_reversals": reversals,
        "seconds_to_view_10_cards": seconds_to_10,
        "average_seconds_per_viewed_card": avg_per_card,
    }


def _seconds_between(start: str, end: str) -> Optional[float]:
    try:
        left = datetime.fromisoformat(start.replace("Z", "+00:00"))
        right = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return None
    if left.tzinfo is None:
        left = left.replace(tzinfo=timezone.utc)
    if right.tzinfo is None:
        right = right.replace(tzinfo=timezone.utc)
    return round((right - left).total_seconds(), 1)


def export_usability_session(
    sqlite_path: Path,
    participant_id: Optional[str] = None,
    out_dir: Optional[Path] = None,
) -> dict[str, Path]:
    path = sqlite_path.resolve()
    if not path.exists():
        raise FileNotFoundError("Usability SQLite not found at {}".format(path))
    storage = Storage(path)
    try:
        sessions = _session_rows(storage.conn, participant_id)
        session_by_id = {int(row["id"]): dict(row) for row in sessions}
        if participant_id:
            event_rows = storage.conn.execute(
                """
                SELECT * FROM review_events
                WHERE participant_id = ?
                ORDER BY id
                """,
                (participant_id,),
            ).fetchall()
            label = normalize_participant_id(participant_id)
        else:
            event_rows = storage.conn.execute(
                "SELECT * FROM review_events ORDER BY id"
            ).fetchall()
            label = "all"
        events = []
        for row in event_rows:
            item = dict(row)
            session = session_by_id.get(int(item["session_id"] or 0), {})
            item["session_started_at"] = session.get("started_at")
            item["session_finished_at"] = session.get("finished_at")
            events.append(item)
        dest_dir = out_dir or USABILITY_EXPORT_DIR
        dest_dir.mkdir(parents=True, exist_ok=True)
        events_path = dest_dir / "{}_events.csv".format(label)
        summary_path = dest_dir / "{}_summary.csv".format(label)
        fieldnames = [
            "participant_id",
            "session_id",
            "session_started_at",
            "session_finished_at",
            "event_id",
            "event_type",
            "source_system",
            "native_record_id",
            "previous_status",
            "new_status",
            "created_at",
        ]
        with events_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for event in events:
                writer.writerow(
                    {
                        "participant_id": event.get("participant_id") or "",
                        "session_id": event.get("session_id") or "",
                        "session_started_at": event.get("session_started_at") or "",
                        "session_finished_at": event.get("session_finished_at") or "",
                        "event_id": event.get("id") or "",
                        "event_type": event.get("event_type") or "",
                        "source_system": event.get("source_system") or "",
                        "native_record_id": event.get("native_record_id") or "",
                        "previous_status": event.get("previous_status") or "",
                        "new_status": event.get("new_status") or "",
                        "created_at": event.get("created_at") or "",
                    }
                )
        by_session: dict[str, list[dict[str, Any]]] = {}
        for event in events:
            sid = str(event.get("session_id") or "none")
            by_session.setdefault(sid, []).append(event)
        summary_fields = [
            "participant_id",
            "session_id",
            "session_started_at",
            "session_finished_at",
            "cards_viewed",
            "source_pages_opened",
            "cards_reviewed_without_opening_source",
            "notes_added",
            "status_IGNORE",
            "status_RELEVANT",
            "status_MONITOR",
            "status_REQUEST_DOCUMENTS",
            "status_back_to_NEW",
            "status_reversals",
            "seconds_to_view_10_cards",
            "average_seconds_per_viewed_card",
        ]
        with summary_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=summary_fields)
            writer.writeheader()
            for sid, session_events in by_session.items():
                session = session_by_id.get(int(sid) if sid.isdigit() else -1, {})
                derived = _derive_summary(session_events)
                writer.writerow(
                    {
                        "participant_id": session.get("participant_id")
                        or participant_id
                        or "",
                        "session_id": sid,
                        "session_started_at": session.get("started_at") or "",
                        "session_finished_at": session.get("finished_at") or "",
                        **derived,
                    }
                )
    finally:
        storage.close()
    return {"events": events_path, "summary": summary_path}
