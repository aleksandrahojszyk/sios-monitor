from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

from src.sios.storage import utc_now

OUTCOME_CLAIMED = "claimed"
OUTCOME_ALREADY_YOURS = "already_yours"
OUTCOME_TAKEN = "taken"
OUTCOME_RELEASED = "released"
OUTCOME_NOT_ASSIGNED = "not_assigned"
OUTCOME_NOT_YOURS = "not_yours"


@dataclass(frozen=True)
class Assignee:
    user_id: int
    display_name: str
    claimed_at: str


@dataclass(frozen=True)
class ClaimResult:
    outcome: str
    assignee: Optional[Assignee]

    @property
    def ok(self) -> bool:
        return self.outcome in {
            OUTCOME_CLAIMED,
            OUTCOME_ALREADY_YOURS,
            OUTCOME_RELEASED,
            OUTCOME_NOT_ASSIGNED,
        }


class ClaimRepository:
    """Card ownership, kept apart from the triage status in ``card_reviews``.

    ``card_claims`` has one row per card (primary key on the card identity), so
    SQLite itself guarantees a single assignee: of two simultaneous claims the
    second insert is ignored and reports who won.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def get_assignee(
        self, source_system: str, native_record_id: str
    ) -> Optional[Assignee]:
        row = self.conn.execute(
            """
            SELECT card_claims.user_id, users.display_name, card_claims.claimed_at
            FROM card_claims
            JOIN users ON users.id = card_claims.user_id
            WHERE card_claims.source_system = ?
              AND card_claims.native_record_id = ?
            """,
            (source_system, native_record_id),
        ).fetchone()
        if row is None:
            return None
        return Assignee(
            user_id=row["user_id"],
            display_name=row["display_name"],
            claimed_at=row["claimed_at"],
        )

    def claim(
        self, source_system: str, native_record_id: str, user_id: int
    ) -> ClaimResult:
        """Claim an unassigned card. Raises ``KeyError`` for an unknown card."""
        cursor = self.conn.execute(
            """
            INSERT OR IGNORE INTO card_claims (
                source_system, native_record_id, user_id, claimed_at
            )
            SELECT ?, ?, ?, ?
            WHERE EXISTS (
                SELECT 1 FROM cards
                WHERE source_system = ? AND native_record_id = ?
            )
            """,
            (
                source_system,
                native_record_id,
                user_id,
                utc_now(),
                source_system,
                native_record_id,
            ),
        )
        self.conn.commit()
        current = self.get_assignee(source_system, native_record_id)
        if cursor.rowcount == 1:
            return ClaimResult(OUTCOME_CLAIMED, current)
        if current is None:
            raise KeyError("Unknown card")
        if current.user_id == user_id:
            return ClaimResult(OUTCOME_ALREADY_YOURS, current)
        return ClaimResult(OUTCOME_TAKEN, current)

    def release(
        self, source_system: str, native_record_id: str, user_id: int
    ) -> ClaimResult:
        """Release a card, but only for the user who currently holds it."""
        cursor = self.conn.execute(
            """
            DELETE FROM card_claims
            WHERE source_system = ? AND native_record_id = ? AND user_id = ?
            """,
            (source_system, native_record_id, user_id),
        )
        self.conn.commit()
        if cursor.rowcount == 1:
            return ClaimResult(OUTCOME_RELEASED, None)
        current = self.get_assignee(source_system, native_record_id)
        if current is None:
            return ClaimResult(OUTCOME_NOT_ASSIGNED, None)
        return ClaimResult(OUTCOME_NOT_YOURS, current)
