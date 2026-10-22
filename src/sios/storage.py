from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import SOURCE_SYSTEM_SIOS, CardRecord

STATUS_NEW = "NEW"
STATUS_CHANGED = "CHANGED"
STATUS_UNCHANGED = "UNCHANGED"
CHANGE_ORIGIN_SOURCE = "SOURCE"
CHANGE_ORIGIN_PARSER_BASELINE = "PARSER_BASELINE"

WATERMARK_STOP_REASONS = (
    "WINDOW_PASSED",
    "EMPTY_PAGE",
    "REPEATED_PAGE",
    "NO_NEW_IDS",
    "WINDOW_COMPLETE",
    "EMPTY_WINDOW",
)

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
    source_system: str
    native_record_id: str
    status: str
    content_hash: str
    sios_id: Optional[int] = None
    changed_fields: Optional[dict[str, Any]] = None
    change_origin: Optional[str] = None


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        # Migrations rebuild parent tables. Keep FK checks off until the
        # namespaced identity exists, otherwise SQLite reports a mismatch.
        self.conn.execute("PRAGMA foreign_keys = OFF")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cards (
                source_system TEXT NOT NULL,
                native_record_id TEXT NOT NULL,
                sios_id INTEGER UNIQUE,
                card_number TEXT,
                year INTEGER,
                document_name TEXT,
                document_type TEXT,
                case_reference TEXT,
                authority TEXT,
                location TEXT,
                listing_date TEXT,
                dates_json TEXT NOT NULL DEFAULT '{}',
                source_url TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                raw_fields_json TEXT NOT NULL DEFAULT '{}',
                parser_version TEXT NOT NULL,
                PRIMARY KEY (source_system, native_record_id)
            );

            CREATE TABLE IF NOT EXISTS keyword_matches (
                source_system TEXT NOT NULL,
                native_record_id TEXT NOT NULL,
                keyword TEXT NOT NULL,
                sios_id INTEGER,
                PRIMARY KEY (source_system, native_record_id, keyword),
                FOREIGN KEY (source_system, native_record_id)
                    REFERENCES cards(source_system, native_record_id)
            );

            CREATE TABLE IF NOT EXISTS collection_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                keyword TEXT,
                source_key TEXT,
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
                window_mode TEXT,
                watermark_used TEXT,
                overlap_days INTEGER NOT NULL DEFAULT 0,
                cards_encountered INTEGER NOT NULL DEFAULT 0,
                cards_in_window INTEGER NOT NULL DEFAULT 0,
                cards_skipped_too_old INTEGER NOT NULL DEFAULT 0,
                cards_skipped_too_new INTEGER NOT NULL DEFAULT 0,
                known_cards_skipped INTEGER NOT NULL DEFAULT 0,
                detail_pages_fetched INTEGER NOT NULL DEFAULT 0,
                window_splits INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS card_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                source_system TEXT NOT NULL,
                native_record_id TEXT NOT NULL,
                sios_id INTEGER,
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
                FOREIGN KEY (source_system, native_record_id)
                    REFERENCES cards(source_system, native_record_id)
            );

            CREATE INDEX IF NOT EXISTS idx_card_observations_sios_id
                ON card_observations(sios_id);
            CREATE INDEX IF NOT EXISTS idx_card_observations_run_id
                ON card_observations(run_id);
            """
        )
        self._migrate_collection_runs()
        self._migrate_parser_versions()
        self._migrate_record_identities()
        self._migrate_namespaced_primary_key()
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_card_observations_identity
            ON card_observations(source_system, native_record_id)
            """
        )
        self._init_record_sources()
        from src.inbox.schema import init_review_schema

        init_review_schema(self.conn)
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
        if "source_key" not in columns:
            self.conn.execute("ALTER TABLE collection_runs ADD COLUMN source_key TEXT")
        if "window_start" not in columns:
            self.conn.execute("ALTER TABLE collection_runs ADD COLUMN window_start TEXT")
        if "window_end" not in columns:
            self.conn.execute("ALTER TABLE collection_runs ADD COLUMN window_end TEXT")
        if "window_mode" not in columns:
            self.conn.execute("ALTER TABLE collection_runs ADD COLUMN window_mode TEXT")
        if "watermark_used" not in columns:
            self.conn.execute("ALTER TABLE collection_runs ADD COLUMN watermark_used TEXT")
        if "overlap_days" not in columns:
            self.conn.execute(
                "ALTER TABLE collection_runs ADD COLUMN overlap_days "
                "INTEGER NOT NULL DEFAULT 0"
            )
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
        if "window_splits" not in columns:
            self.conn.execute(
                "ALTER TABLE collection_runs ADD COLUMN window_splits "
                "INTEGER NOT NULL DEFAULT 0"
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

    def _migrate_record_identities(self) -> None:
        columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(cards)")
        }
        if "source_system" not in columns:
            self.conn.execute(
                "ALTER TABLE cards ADD COLUMN source_system "
                "TEXT NOT NULL DEFAULT 'sios'"
            )
        if "native_record_id" not in columns:
            self.conn.execute(
                "ALTER TABLE cards ADD COLUMN native_record_id TEXT"
            )
        self.conn.execute(
            """
            UPDATE cards
            SET source_system = ?, native_record_id = CAST(sios_id AS TEXT)
            WHERE native_record_id IS NULL OR native_record_id = ''
            """,
            (SOURCE_SYSTEM_SIOS,),
        )
        self.conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_source_identity
            ON cards(source_system, native_record_id)
            """
        )

    def _table_columns(self, table: str) -> list[str]:
        return [
            str(row["name"])
            for row in self.conn.execute("PRAGMA table_info({})".format(table))
        ]

    def _primary_key_columns(self, table: str) -> list[str]:
        rows = list(self.conn.execute("PRAGMA table_info({})".format(table)))
        ordered = sorted((row for row in rows if row["pk"] > 0), key=lambda row: row["pk"])
        return [str(row["name"]) for row in ordered]

    def _migrate_namespaced_primary_key(self) -> None:
        """Move identity off sios_id so EkoKarty rows cannot collide with SIOS IDs."""
        self.conn.execute("PRAGMA foreign_keys = OFF")
        try:
            if self._primary_key_columns("cards") == ["sios_id"]:
                self._rebuild_cards_table()
            keyword_columns = set(self._table_columns("keyword_matches"))
            if "sios_id" in keyword_columns and "source_system" not in keyword_columns:
                self._rebuild_keyword_matches()
            observation_columns = set(self._table_columns("card_observations"))
            if observation_columns and "source_system" not in observation_columns:
                self._rebuild_observations()
            card_columns = set(self._table_columns("cards"))
            if "listing_date" not in card_columns:
                self.conn.execute("ALTER TABLE cards ADD COLUMN listing_date TEXT")
        finally:
            self.conn.execute("PRAGMA foreign_keys = ON")

    def _rebuild_cards_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE cards_new (
                source_system TEXT NOT NULL,
                native_record_id TEXT NOT NULL,
                sios_id INTEGER UNIQUE,
                card_number TEXT,
                year INTEGER,
                document_name TEXT,
                document_type TEXT,
                case_reference TEXT,
                authority TEXT,
                location TEXT,
                listing_date TEXT,
                dates_json TEXT NOT NULL DEFAULT '{}',
                source_url TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                raw_fields_json TEXT NOT NULL DEFAULT '{}',
                parser_version TEXT NOT NULL,
                PRIMARY KEY (source_system, native_record_id)
            )
            """
        )
        old_columns = set(self._table_columns("cards"))
        select_listing = (
            "listing_date" if "listing_date" in old_columns else "NULL"
        )
        self.conn.execute(
            """
            INSERT INTO cards_new (
                source_system, native_record_id, sios_id, card_number, year,
                document_name, document_type, case_reference, authority,
                location, listing_date, dates_json, source_url, first_seen_at,
                last_seen_at, raw_fields_json, parser_version
            )
            SELECT
                source_system,
                native_record_id,
                sios_id,
                card_number,
                year,
                document_name,
                document_type,
                case_reference,
                authority,
                location,
                {},
                dates_json,
                source_url,
                first_seen_at,
                last_seen_at,
                raw_fields_json,
                parser_version
            FROM cards
            """.format(select_listing)
        )
        self.conn.execute("DROP TABLE cards")
        self.conn.execute("ALTER TABLE cards_new RENAME TO cards")

    def _rebuild_keyword_matches(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE keyword_matches_new (
                source_system TEXT NOT NULL,
                native_record_id TEXT NOT NULL,
                keyword TEXT NOT NULL,
                sios_id INTEGER,
                PRIMARY KEY (source_system, native_record_id, keyword),
                FOREIGN KEY (source_system, native_record_id)
                    REFERENCES cards(source_system, native_record_id)
            )
            """
        )
        self.conn.execute(
            """
            INSERT INTO keyword_matches_new (
                source_system, native_record_id, keyword, sios_id
            )
            SELECT ?, CAST(sios_id AS TEXT), keyword, sios_id
            FROM keyword_matches
            """,
            (SOURCE_SYSTEM_SIOS,),
        )
        self.conn.execute("DROP TABLE keyword_matches")
        self.conn.execute("ALTER TABLE keyword_matches_new RENAME TO keyword_matches")

    def _rebuild_observations(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE card_observations_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                source_system TEXT NOT NULL,
                native_record_id TEXT NOT NULL,
                sios_id INTEGER,
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
                FOREIGN KEY (source_system, native_record_id)
                    REFERENCES cards(source_system, native_record_id)
            )
            """
        )
        columns = set(self._table_columns("card_observations"))
        parser_select = (
            "COALESCE(parser_version, '')" if "parser_version" in columns else "''"
        )
        origin_select = "change_origin" if "change_origin" in columns else "NULL"
        self.conn.execute(
            """
            INSERT INTO card_observations_new (
                id, run_id, source_system, native_record_id, sios_id,
                observed_at, status, content_hash, changed_fields_json,
                parser_version, change_origin
            )
            SELECT
                id, run_id, ?, CAST(sios_id AS TEXT), sios_id,
                observed_at, status, content_hash, changed_fields_json,
                {}, {}
            FROM card_observations
            """.format(parser_select, origin_select),
            (SOURCE_SYSTEM_SIOS,),
        )
        self.conn.execute("DROP TABLE card_observations")
        self.conn.execute("ALTER TABLE card_observations_new RENAME TO card_observations")
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_card_observations_identity
            ON card_observations(source_system, native_record_id)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_card_observations_sios_id
            ON card_observations(sios_id)
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_card_observations_run_id
            ON card_observations(run_id)
            """
        )

    def _init_record_sources(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS record_sources (
                source_system TEXT NOT NULL,
                native_record_id TEXT NOT NULL,
                source_key TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (source_system, native_record_id, source_key),
                FOREIGN KEY (source_system, native_record_id)
                    REFERENCES cards(source_system, native_record_id)
            );

            CREATE INDEX IF NOT EXISTS idx_record_sources_source_key
                ON record_sources(source_key);
            """
        )

    def start_run(
        self,
        keyword: Optional[str],
        *,
        window_start: Optional[str] = None,
        window_end: Optional[str] = None,
        window_mode: Optional[str] = None,
        watermark_used: Optional[str] = None,
        overlap_days: int = 0,
        source_key: Optional[str] = None,
    ) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO collection_runs (
                started_at, keyword, window_start, window_end, window_mode,
                watermark_used, overlap_days, source_key, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running')
            """,
            (
                utc_now(),
                keyword,
                window_start,
                window_end,
                window_mode,
                watermark_used,
                overlap_days,
                source_key,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def last_successful_window_end(
        self, keyword: str, source_key: Optional[str] = None
    ) -> Optional[str]:
        """Return the latest safe end date for one keyword and source.

        Incomplete caps and failed/partial runs must never advance the
        incremental watermark. A NULL source is the legacy/manual nationwide
        scope and never advances a named source's watermark.
        """
        row = self.conn.execute(
            """
            SELECT window_end
            FROM collection_runs
            WHERE keyword = ?
              AND (
                  (? IS NULL AND source_key IS NULL)
                  OR source_key = ?
              )
              AND status = 'ok'
              AND window_end IS NOT NULL
              AND stop_reason IN (
                  'WINDOW_PASSED', 'EMPTY_PAGE',
                  'REPEATED_PAGE', 'NO_NEW_IDS',
                  'WINDOW_COMPLETE', 'EMPTY_WINDOW'
              )
            ORDER BY finished_at DESC, run_id DESC
            LIMIT 1
            """,
            (keyword, source_key, source_key),
        ).fetchone()
        return str(row["window_end"]) if row is not None else None

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
        window_splits: int = 0,
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
                window_splits = ?, status = ?, error = ?
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
                window_splits,
                status,
                error,
                run_id,
            ),
        )
        self.conn.commit()

    def has_card(self, sios_id: int) -> bool:
        return self.has_record(SOURCE_SYSTEM_SIOS, str(sios_id))

    def has_record(self, source_system: str, native_record_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM cards
            WHERE source_system = ? AND native_record_id = ?
            """,
            (source_system, native_record_id),
        ).fetchone()
        return row is not None

    def upsert_card(
        self,
        record: CardRecord,
        run_id: Optional[int] = None,
        source_key: Optional[str] = None,
    ) -> UpsertResult:
        now = utc_now()
        listing_date = record.dates.get("listing_date") if record.dates else None
        existing = self.conn.execute(
            """
            SELECT * FROM cards
            WHERE source_system = ? AND native_record_id = ?
            """,
            (record.source_system, record.native_record_id),
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
                    source_system, native_record_id, sios_id, card_number, year,
                    document_name, document_type, case_reference, authority,
                    location, listing_date, dates_json, source_url,
                    first_seen_at, last_seen_at, raw_fields_json, parser_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.source_system,
                    record.native_record_id,
                    record.sios_id,
                    record.card_number,
                    record.year,
                    record.document_name,
                    record.document_type,
                    record.case_reference,
                    record.authority,
                    record.location,
                    listing_date,
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
                # the refreshed payload as a baseline without claiming the
                # source changed. The diff remains available for audit.
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
                        listing_date = ?,
                        dates_json = ?,
                        source_url = ?,
                        last_seen_at = ?,
                        raw_fields_json = ?,
                        parser_version = ?
                    WHERE source_system = ? AND native_record_id = ?
                    """,
                    (
                        record.card_number,
                        record.year,
                        record.document_name,
                        record.document_type,
                        record.case_reference,
                        record.authority,
                        record.location,
                        listing_date,
                        json.dumps(record.dates, ensure_ascii=False),
                        record.source_url,
                        now,
                        json.dumps(record.raw_fields, ensure_ascii=False),
                        record.parser_version,
                        record.source_system,
                        record.native_record_id,
                    ),
                )
            else:
                self.conn.execute(
                    """
                    UPDATE cards SET last_seen_at = ?
                    WHERE source_system = ? AND native_record_id = ?
                    """,
                    (now, record.source_system, record.native_record_id),
                )
        for keyword in record.matched_keywords:
            self.add_record_keyword_match(
                record.source_system,
                record.native_record_id,
                keyword,
                sios_id=record.sios_id,
                commit=False,
            )
        if source_key is not None:
            self._link_record_source(
                record.source_system,
                record.native_record_id,
                source_key,
                observed_at=now,
            )
        if run_id is not None:
            self.conn.execute(
                """
                INSERT INTO card_observations (
                    run_id, source_system, native_record_id, sios_id,
                    observed_at, status, content_hash, changed_fields_json,
                    parser_version, change_origin
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    record.source_system,
                    record.native_record_id,
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
            source_system=record.source_system,
            native_record_id=record.native_record_id,
            sios_id=record.sios_id,
            status=status,
            content_hash=digest,
            changed_fields=changed_fields,
            change_origin=change_origin,
        )

    def _link_record_source(
        self,
        source_system: str,
        native_record_id: str,
        source_key: str,
        *,
        observed_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO record_sources (
                source_system, native_record_id, source_key,
                first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                source_system,
                native_record_id,
                source_key,
                observed_at,
                observed_at,
            ),
        )
        self.conn.execute(
            """
            UPDATE record_sources
            SET last_seen_at = ?
            WHERE source_system = ?
              AND native_record_id = ?
              AND source_key = ?
            """,
            (observed_at, source_system, native_record_id, source_key),
        )

    def link_sios_record_source(self, sios_id: int, source_key: str) -> None:
        self._link_record_source(
            SOURCE_SYSTEM_SIOS,
            str(sios_id),
            source_key,
            observed_at=utc_now(),
        )
        self.conn.commit()

    def sources_for(self, sios_id: int) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT source_key
            FROM record_sources
            WHERE source_system = ? AND native_record_id = ?
            ORDER BY source_key
            """,
            (SOURCE_SYSTEM_SIOS, str(sios_id)),
        ).fetchall()
        return [str(row["source_key"]) for row in rows]

    def add_keyword_match(self, sios_id: int, keyword: str) -> None:
        self.add_record_keyword_match(
            SOURCE_SYSTEM_SIOS, str(sios_id), keyword, sios_id=sios_id
        )

    def add_record_keyword_match(
        self,
        source_system: str,
        native_record_id: str,
        keyword: str,
        *,
        sios_id: Optional[int] = None,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO keyword_matches (
                source_system, native_record_id, keyword, sios_id
            ) VALUES (?, ?, ?, ?)
            """,
            (source_system, native_record_id, keyword, sios_id),
        )
        if commit:
            self.conn.commit()

    def mark_record_seen(
        self,
        source_system: str,
        native_record_id: str,
        *,
        keyword: Optional[str] = None,
        source_key: Optional[str] = None,
        sios_id: Optional[int] = None,
    ) -> None:
        now = utc_now()
        self.conn.execute(
            """
            UPDATE cards SET last_seen_at = ?
            WHERE source_system = ? AND native_record_id = ?
            """,
            (now, source_system, native_record_id),
        )
        if keyword:
            self.add_record_keyword_match(
                source_system,
                native_record_id,
                keyword,
                sios_id=sios_id,
                commit=False,
            )
        if source_key is not None:
            self._link_record_source(
                source_system,
                native_record_id,
                source_key,
                observed_at=now,
            )
        self.conn.commit()

    def observations_for(self, sios_id: int) -> list[dict[str, Any]]:
        return self.observations_for_record(SOURCE_SYSTEM_SIOS, str(sios_id))

    def observations_for_record(
        self, source_system: str, native_record_id: str
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, run_id, source_system, native_record_id, sios_id,
                   observed_at, status, content_hash, changed_fields_json,
                   parser_version, change_origin
            FROM card_observations
            WHERE source_system = ? AND native_record_id = ?
            ORDER BY id
            """,
            (source_system, native_record_id),
        ).fetchall()
        observations: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw_changes = item.pop("changed_fields_json")
            item["changed_fields"] = json.loads(raw_changes) if raw_changes else None
            observations.append(item)
        return observations

    def keywords_for(self, sios_id: int) -> list[str]:
        return self.keywords_for_record(SOURCE_SYSTEM_SIOS, str(sios_id))

    def keywords_for_record(self, source_system: str, native_record_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT keyword FROM keyword_matches
            WHERE source_system = ? AND native_record_id = ?
            ORDER BY keyword
            """,
            (source_system, native_record_id),
        ).fetchall()
        return [row["keyword"] for row in rows]

    def get_card(self, sios_id: int) -> Optional[dict[str, Any]]:
        return self.get_record(SOURCE_SYSTEM_SIOS, str(sios_id))

    def get_record(
        self, source_system: str, native_record_id: str
    ) -> Optional[dict[str, Any]]:
        row = self.conn.execute(
            """
            SELECT * FROM cards
            WHERE source_system = ? AND native_record_id = ?
            """,
            (source_system, native_record_id),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["dates"] = json.loads(data.pop("dates_json") or "{}")
        data["raw_fields"] = json.loads(data.pop("raw_fields_json") or "{}")
        data["matched_keywords"] = self.keywords_for_record(
            source_system, native_record_id
        )
        data["source_keys"] = self.sources_for_record(source_system, native_record_id)
        data["canonical_key"] = "{}:{}".format(source_system, native_record_id)
        return data

    def sources_for_record(self, source_system: str, native_record_id: str) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT source_key
            FROM record_sources
            WHERE source_system = ? AND native_record_id = ?
            ORDER BY source_key
            """,
            (source_system, native_record_id),
        ).fetchall()
        return [str(row["source_key"]) for row in rows]

    def card_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()
        return int(row["n"])

    def count_distinct_cards(self, run_ids: list[int]) -> int:
        if not run_ids:
            return 0
        placeholders = ",".join("?" for _ in run_ids)
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS n FROM (
                SELECT DISTINCT source_system, native_record_id
                FROM card_observations
                WHERE run_id IN ({})
            )
            """.format(placeholders),
            tuple(run_ids),
        ).fetchone()
        return int(row["n"])
