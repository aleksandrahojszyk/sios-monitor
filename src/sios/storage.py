from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import CardRecord

STATUS_NEW = "NEW"
STATUS_CHANGED = "CHANGED"
STATUS_UNCHANGED = "UNCHANGED"
CHANGE_ORIGIN_SOURCE = "SOURCE"
CHANGE_ORIGIN_PARSER_BASELINE = "PARSER_BASELINE"

# Search-hit context, not the public card. Keyword overlap lives in keyword_matches.
_IGNORED_RAW_KEYS = {"_search"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _public_raw_fields(raw_fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in raw_fields.items() if key not in _IGNORED_RAW_KEYS}


def content_payload_from_record(record: CardRecord) -> dict[str, Any]:
    return {
        "card_number": record.card_number,
        "year": record.year,
        "document_name": record.document_name,
        "document_type": record.document_type,
        "case_reference": record.case_reference,
        "authority": record.authority,
        "location": record.location,
        "dates": record.dates,
        "source_url": record.source_url,
        "raw_fields": _public_raw_fields(record.raw_fields),
    }


def content_payload_from_row(row: sqlite3.Row) -> dict[str, Any]:
    raw_fields = json.loads(row["raw_fields_json"] or "{}")
    return {
        "card_number": row["card_number"],
        "year": row["year"],
        "document_name": row["document_name"],
        "document_type": row["document_type"],
        "case_reference": row["case_reference"],
        "authority": row["authority"],
        "location": row["location"],
        "dates": json.loads(row["dates_json"] or "{}"),
        "source_url": row["source_url"],
        "raw_fields": _public_raw_fields(raw_fields),
    }


def diff_content(old: dict[str, Any], new: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Field paths whose canonical JSON differs. Object key order is not a change."""
    changes: dict[str, dict[str, Any]] = {}

    def walk(left: Any, right: Any, path: str) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right), key=str):
                child = "{}.{}".format(path, key) if path else str(key)
                walk(left.get(key), right.get(key), child)
            return
        if _stable_json(left) != _stable_json(right):
            changes[path] = {"old": left, "new": right}

    walk(old, new, "")
    return changes


@dataclass
class UpsertResult:
    created: bool
    sios_id: int
    status: str
    content_hash: str
    changed_fields: Optional[dict[str, Any]] = None
    change_origin: Optional[str] = None


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cards (
                sios_id INTEGER PRIMARY KEY,
                card_number TEXT,
                year INTEGER,
                document_name TEXT,
                document_type TEXT,
                case_reference TEXT,
                authority TEXT,
                location TEXT,
                dates_json TEXT NOT NULL DEFAULT '{}',
                source_url TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                raw_fields_json TEXT NOT NULL DEFAULT '{}',
                parser_version TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS keyword_matches (
                sios_id INTEGER NOT NULL,
                keyword TEXT NOT NULL,
                PRIMARY KEY (sios_id, keyword),
                FOREIGN KEY (sios_id) REFERENCES cards(sios_id)
            );

            CREATE TABLE IF NOT EXISTS collection_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                keyword TEXT,
                pages_processed INTEGER NOT NULL DEFAULT 0,
                cards_found INTEGER NOT NULL DEFAULT 0,
                new_cards INTEGER NOT NULL DEFAULT 0,
                changed_cards INTEGER NOT NULL DEFAULT 0,
                unchanged_cards INTEGER NOT NULL DEFAULT 0,
                existing_cards INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                reported_total INTEGER,
                stop_reason TEXT,
                window_start TEXT,
                window_end TEXT,
                cards_encountered INTEGER NOT NULL DEFAULT 0,
                cards_in_window INTEGER NOT NULL DEFAULT 0,
                cards_skipped_too_old INTEGER NOT NULL DEFAULT 0,
                cards_skipped_too_new INTEGER NOT NULL DEFAULT 0,
                known_cards_skipped INTEGER NOT NULL DEFAULT 0,
                detail_pages_fetched INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS card_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                sios_id INTEGER NOT NULL,
                observed_at TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('NEW', 'CHANGED', 'UNCHANGED')),
                content_hash TEXT NOT NULL,
                changed_fields_json TEXT,
                parser_version TEXT NOT NULL,
                change_origin TEXT CHECK (
                    change_origin IS NULL OR
                    change_origin IN ('SOURCE', 'PARSER_BASELINE')
                ),
                FOREIGN KEY (run_id) REFERENCES collection_runs(run_id),
                FOREIGN KEY (sios_id) REFERENCES cards(sios_id)
            );

            CREATE INDEX IF NOT EXISTS idx_card_observations_sios_id
                ON card_observations(sios_id);
            CREATE INDEX IF NOT EXISTS idx_card_observations_run_id
                ON card_observations(run_id);
            """
        )
        self._migrate_collection_runs()
        self._migrate_parser_versions()
        self.conn.commit()

    def _migrate_collection_runs(self) -> None:
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(collection_runs)")
        }
        if "changed_cards" not in columns:
            self.conn.execute(
                "ALTER TABLE collection_runs ADD COLUMN changed_cards INTEGER NOT NULL DEFAULT 0"
            )
        if "unchanged_cards" not in columns:
            self.conn.execute(
                "ALTER TABLE collection_runs ADD COLUMN unchanged_cards INTEGER NOT NULL DEFAULT 0"
            )
        if "existing_cards" not in columns:
            self.conn.execute(
                "ALTER TABLE collection_runs ADD COLUMN existing_cards INTEGER NOT NULL DEFAULT 0"
            )
        if "error_count" not in columns:
            self.conn.execute(
                "ALTER TABLE collection_runs ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0"
            )
        if "reported_total" not in columns:
            self.conn.execute("ALTER TABLE collection_runs ADD COLUMN reported_total INTEGER")
        if "stop_reason" not in columns:
            self.conn.execute("ALTER TABLE collection_runs ADD COLUMN stop_reason TEXT")
        if "window_start" not in columns:
            self.conn.execute("ALTER TABLE collection_runs ADD COLUMN window_start TEXT")
        if "window_end" not in columns:
            self.conn.execute("ALTER TABLE collection_runs ADD COLUMN window_end TEXT")
        for column in (
            "cards_encountered",
            "cards_in_window",
            "cards_skipped_too_old",
            "cards_skipped_too_new",
            "known_cards_skipped",
            "detail_pages_fetched",
        ):
            if column not in columns:
                self.conn.execute(
                    "ALTER TABLE collection_runs ADD COLUMN {} "
                    "INTEGER NOT NULL DEFAULT 0".format(column)
                )

    def _migrate_parser_versions(self) -> None:
        card_columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(cards)")
        }
        if "parser_version" not in card_columns:
            # NULL means this current state predates explicit parser versioning.
            # Its next fetch becomes a parser baseline, not a source change.
            self.conn.execute("ALTER TABLE cards ADD COLUMN parser_version TEXT")

        observation_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(card_observations)")
        }
        if "parser_version" not in observation_columns:
            # Historical observations remain NULL and are not rewritten.
            self.conn.execute(
                "ALTER TABLE card_observations ADD COLUMN parser_version TEXT"
            )
        if "change_origin" not in observation_columns:
            self.conn.execute(
                "ALTER TABLE card_observations ADD COLUMN change_origin TEXT"
            )

    def start_run(
        self,
        keyword: Optional[str],
        *,
        window_start: Optional[str] = None,
        window_end: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO collection_runs (
                started_at, keyword, window_start, window_end, status
            )
            VALUES (?, ?, ?, ?, 'running')
            """,
            (utc_now(), keyword, window_start, window_end),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        *,
        pages_processed: int,
        cards_found: int,
        new_cards: int,
        status: str,
        error: Optional[str] = None,
        changed_cards: int = 0,
        unchanged_cards: int = 0,
        existing_cards: int = 0,
        error_count: int = 0,
        reported_total: Optional[int] = None,
        stop_reason: Optional[str] = None,
        cards_encountered: int = 0,
        cards_in_window: int = 0,
        cards_skipped_too_old: int = 0,
        cards_skipped_too_new: int = 0,
        known_cards_skipped: int = 0,
        detail_pages_fetched: int = 0,
    ) -> None:
        self.conn.execute(
            """
            UPDATE collection_runs
            SET finished_at = ?, pages_processed = ?, cards_found = ?,
                new_cards = ?, changed_cards = ?, unchanged_cards = ?,
                existing_cards = ?, error_count = ?, reported_total = ?,
                stop_reason = ?, cards_encountered = ?, cards_in_window = ?,
                cards_skipped_too_old = ?, cards_skipped_too_new = ?,
                known_cards_skipped = ?, detail_pages_fetched = ?,
                status = ?, error = ?
            WHERE run_id = ?
            """,
            (
                utc_now(),
                pages_processed,
                cards_found,
                new_cards,
                changed_cards,
                unchanged_cards,
                existing_cards,
                error_count,
                reported_total,
                stop_reason,
                cards_encountered,
                cards_in_window,
                cards_skipped_too_old,
                cards_skipped_too_new,
                known_cards_skipped,
                detail_pages_fetched,
                status,
                error,
                run_id,
            ),
        )
        self.conn.commit()

    def has_card(self, sios_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM cards WHERE sios_id = ?", (sios_id,)
        ).fetchone()
        return row is not None

    def upsert_card(self, record: CardRecord, run_id: Optional[int] = None) -> UpsertResult:
        now = utc_now()
        existing = self.conn.execute(
            "SELECT * FROM cards WHERE sios_id = ?",
            (record.sios_id,),
        ).fetchone()
        payload = content_payload_from_record(record)
        digest = content_hash(payload)
        changed_fields: Optional[dict[str, Any]] = None
        change_origin: Optional[str] = None
        if existing is None:
            status = STATUS_NEW
            self.conn.execute(
                """
                INSERT INTO cards (
                    sios_id, card_number, year, document_name, document_type,
                    case_reference, authority, location, dates_json, source_url,
                    first_seen_at, last_seen_at, raw_fields_json, parser_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.sios_id,
                    record.card_number,
                    record.year,
                    record.document_name,
                    record.document_type,
                    record.case_reference,
                    record.authority,
                    record.location,
                    json.dumps(record.dates, ensure_ascii=False),
                    record.source_url,
                    now,
                    now,
                    json.dumps(record.raw_fields, ensure_ascii=False),
                    record.parser_version,
                ),
            )
        else:
            changed_fields = diff_content(content_payload_from_row(existing), payload) or None
            parser_changed = existing["parser_version"] != record.parser_version
            if parser_changed:
                # Parser evolution may add, remove, or reinterpret fields. Store
                # the refreshed payload as a baseline without claiming SIOS
                # changed. The diff remains available for audit.
                status = STATUS_UNCHANGED
                change_origin = CHANGE_ORIGIN_PARSER_BASELINE
            elif changed_fields:
                status = STATUS_CHANGED
                change_origin = CHANGE_ORIGIN_SOURCE
            else:
                status = STATUS_UNCHANGED

            if parser_changed or changed_fields:
                self.conn.execute(
                    """
                    UPDATE cards SET
                        card_number = ?,
                        year = ?,
                        document_name = ?,
                        document_type = ?,
                        case_reference = ?,
                        authority = ?,
                        location = ?,
                        dates_json = ?,
                        source_url = ?,
                        last_seen_at = ?,
                        raw_fields_json = ?,
                        parser_version = ?
                    WHERE sios_id = ?
                    """,
                    (
                        record.card_number,
                        record.year,
                        record.document_name,
                        record.document_type,
                        record.case_reference,
                        record.authority,
                        record.location,
                        json.dumps(record.dates, ensure_ascii=False),
                        record.source_url,
                        now,
                        json.dumps(record.raw_fields, ensure_ascii=False),
                        record.parser_version,
                        record.sios_id,
                    ),
                )
            else:
                self.conn.execute(
                    "UPDATE cards SET last_seen_at = ? WHERE sios_id = ?",
                    (now, record.sios_id),
                )
        for keyword in record.matched_keywords:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO keyword_matches (sios_id, keyword)
                VALUES (?, ?)
                """,
                (record.sios_id, keyword),
            )
        if run_id is not None:
            self.conn.execute(
                """
                INSERT INTO card_observations (
                    run_id, sios_id, observed_at, status, content_hash,
                    changed_fields_json, parser_version, change_origin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    record.sios_id,
                    now,
                    status,
                    digest,
                    json.dumps(changed_fields, ensure_ascii=False, sort_keys=True)
                    if changed_fields
                    else None,
                    record.parser_version,
                    change_origin,
                ),
            )
        self.conn.commit()
        return UpsertResult(
            created=status == STATUS_NEW,
            sios_id=record.sios_id,
            status=status,
            content_hash=digest,
            changed_fields=changed_fields,
            change_origin=change_origin,
        )

    def add_keyword_match(self, sios_id: int, keyword: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO keyword_matches (sios_id, keyword)
            VALUES (?, ?)
            """,
            (sios_id, keyword),
        )
        self.conn.commit()

    def observations_for(self, sios_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, run_id, sios_id, observed_at, status, content_hash,
                   changed_fields_json, parser_version, change_origin
            FROM card_observations
            WHERE sios_id = ?
            ORDER BY id
            """,
            (sios_id,),
        ).fetchall()
        observations: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw_changes = item.pop("changed_fields_json")
            item["changed_fields"] = json.loads(raw_changes) if raw_changes else None
            observations.append(item)
        return observations

    def keywords_for(self, sios_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT keyword FROM keyword_matches WHERE sios_id = ? ORDER BY keyword",
            (sios_id,),
        ).fetchall()
        return [row["keyword"] for row in rows]

    def get_card(self, sios_id: int) -> Optional[dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM cards WHERE sios_id = ?", (sios_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["dates"] = json.loads(data.pop("dates_json") or "{}")
        data["raw_fields"] = json.loads(data.pop("raw_fields_json") or "{}")
        data["matched_keywords"] = self.keywords_for(sios_id)
        return data

    def card_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()
        return int(row["n"])

    def count_distinct_cards(self, run_ids: list[int]) -> int:
        if not run_ids:
            return 0
        placeholders = ",".join("?" for _ in run_ids)
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT sios_id) AS n FROM card_observations WHERE run_id IN ({})".format(
                placeholders
            ),
            tuple(run_ids),
        ).fetchone()
        return int(row["n"])
