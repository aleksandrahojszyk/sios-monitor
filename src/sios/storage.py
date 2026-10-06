from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import CardRecord


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class UpsertResult:
    created: bool
    sios_id: int


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
                raw_fields_json TEXT NOT NULL DEFAULT '{}'
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
                status TEXT NOT NULL,
                error TEXT
            );
            """
        )
        self.conn.commit()

    def start_run(self, keyword: Optional[str]) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO collection_runs (started_at, keyword, status)
            VALUES (?, ?, 'running')
            """,
            (utc_now(), keyword),
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
    ) -> None:
        self.conn.execute(
            """
            UPDATE collection_runs
            SET finished_at = ?, pages_processed = ?, cards_found = ?,
                new_cards = ?, status = ?, error = ?
            WHERE run_id = ?
            """,
            (utc_now(), pages_processed, cards_found, new_cards, status, error, run_id),
        )
        self.conn.commit()

    def has_card(self, sios_id: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM cards WHERE sios_id = ?", (sios_id,)
        ).fetchone()
        return row is not None

    def upsert_card(self, record: CardRecord) -> UpsertResult:
        now = utc_now()
        existing = self.conn.execute(
            "SELECT first_seen_at FROM cards WHERE sios_id = ?",
            (record.sios_id,),
        ).fetchone()
        created = existing is None
        first_seen = now if created else existing["first_seen_at"]
        values = (
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
            first_seen,
            now,
            json.dumps(record.raw_fields, ensure_ascii=False),
        )
        if created:
            self.conn.execute(
                """
                INSERT INTO cards (
                    sios_id, card_number, year, document_name, document_type,
                    case_reference, authority, location, dates_json, source_url,
                    first_seen_at, last_seen_at, raw_fields_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                values,
            )
        else:
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
                    raw_fields_json = ?
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
                    record.sios_id,
                ),
            )
        for keyword in record.matched_keywords:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO keyword_matches (sios_id, keyword)
                VALUES (?, ?)
                """,
                (record.sios_id, keyword),
            )
        self.conn.commit()
        return UpsertResult(created=created, sios_id=record.sios_id)

    def add_keyword_match(self, sios_id: int, keyword: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO keyword_matches (sios_id, keyword)
            VALUES (?, ?)
            """,
            (sios_id, keyword),
        )
        self.conn.commit()

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
