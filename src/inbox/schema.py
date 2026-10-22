from __future__ import annotations

import sqlite3


def init_review_schema(conn: sqlite3.Connection) -> None:
    """Create the human-review tables. No foreign key onto collected cards."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS card_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_system TEXT NOT NULL,
            native_record_id TEXT NOT NULL,
            external_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'NEW'
                CHECK (status IN (
                    'NEW', 'RELEVANT', 'IGNORE', 'MONITOR', 'REQUEST_DOCUMENTS'
                )),
            note TEXT,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (source_system, native_record_id)
        );

        CREATE INDEX IF NOT EXISTS idx_card_reviews_status
            ON card_reviews(status);
        CREATE INDEX IF NOT EXISTS idx_card_reviews_reviewed_at
            ON card_reviews(reviewed_at);
        CREATE INDEX IF NOT EXISTS idx_card_reviews_external_key
            ON card_reviews(external_key);

        CREATE TABLE IF NOT EXISTS review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_system TEXT NOT NULL,
            native_record_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            previous_status TEXT,
            new_status TEXT,
            created_at TEXT NOT NULL,
            participant_id TEXT,
            session_id INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_review_events_identity
            ON review_events(source_system, native_record_id);
        CREATE INDEX IF NOT EXISTS idx_review_events_created
            ON review_events(created_at);

        CREATE TABLE IF NOT EXISTS usability_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_usability_sessions_participant
            ON usability_sessions(participant_id, finished_at);

        CREATE INDEX IF NOT EXISTS idx_cards_authority ON cards(authority);
        CREATE INDEX IF NOT EXISTS idx_cards_document_type ON cards(document_type);
        CREATE INDEX IF NOT EXISTS idx_cards_listing_date ON cards(listing_date);
        CREATE INDEX IF NOT EXISTS idx_cards_card_number ON cards(card_number);
        """
    )
    _ensure_column(conn, "review_events", "participant_id", "TEXT")
    _ensure_column(conn, "review_events", "session_id", "INTEGER")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_review_events_participant
            ON review_events(participant_id, session_id)
        """
    )


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    name: str,
    sql_type: str,
) -> None:
    existing = {
        row[1] for row in conn.execute("PRAGMA table_info({})".format(table))
    }
    if name not in existing:
        conn.execute(
            "ALTER TABLE {} ADD COLUMN {} {}".format(table, name, sql_type)
        )
