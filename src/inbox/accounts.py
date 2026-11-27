from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash

from src.sios.storage import utc_now

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,39}$")
MIN_PASSWORD_LENGTH = 8
MAX_DISPLAY_NAME_LENGTH = 60

# Used to keep failed sign-ins for unknown usernames as slow as known ones.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


class AccountError(ValueError):
    """A user-account request that cannot be honoured (safe to show)."""


@dataclass(frozen=True)
class User:
    id: int
    username: str
    display_name: str
    is_active: bool
    created_at: str


def _user(row: sqlite3.Row) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
    )


def normalize_username(value: str) -> str:
    username = (value or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise AccountError(
            "Username must be 2-40 characters: lowercase letters, digits, "
            "'.', '_' or '-', starting with a letter or digit."
        )
    return username


def normalize_display_name(value: str) -> str:
    name = " ".join((value or "").split())
    if not name:
        raise AccountError("Display name is required.")
    if len(name) > MAX_DISPLAY_NAME_LENGTH:
        raise AccountError(
            "Display name must be at most {} characters.".format(
                MAX_DISPLAY_NAME_LENGTH
            )
        )
    if any(ord(char) < 32 for char in name):
        raise AccountError("Display name contains control characters.")
    return name


def _check_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AccountError(
            "Password must be at least {} characters.".format(MIN_PASSWORD_LENGTH)
        )


class AccountRepository:
    """Individual team accounts stored in the same SQLite file as the inbox."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_user(self, username: str, display_name: str, password: str) -> User:
        username = normalize_username(username)
        display_name = normalize_display_name(display_name)
        _check_password(password)
        try:
            cursor = self.conn.execute(
                """
                INSERT INTO users (
                    username, display_name, password_hash, is_active, created_at
                ) VALUES (?, ?, ?, 1, ?)
                """,
                (username, display_name, generate_password_hash(password), utc_now()),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            self.conn.rollback()
            raise AccountError(
                "That username or display name is already in use."
            ) from None
        user = self.get_user(cursor.lastrowid)
        assert user is not None
        return user

    def get_user(self, user_id: int) -> Optional[User]:
        row = self.conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return _user(row) if row else None

    def get_by_username(self, username: str) -> Optional[User]:
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", ((username or "").strip(),)
        ).fetchone()
        return _user(row) if row else None

    def list_users(self) -> list[User]:
        rows = self.conn.execute(
            "SELECT * FROM users ORDER BY display_name COLLATE NOCASE"
        ).fetchall()
        return [_user(row) for row in rows]

    def authenticate(self, username: str, password: str) -> Optional[User]:
        row = self.conn.execute(
            "SELECT * FROM users WHERE username = ?", ((username or "").strip(),)
        ).fetchone()
        if row is None:
            check_password_hash(_DUMMY_HASH, password or "")
            return None
        if not check_password_hash(row["password_hash"], password or ""):
            return None
        if not row["is_active"]:
            return None
        return _user(row)

    def set_password(self, username: str, password: str) -> None:
        _check_password(password)
        cursor = self.conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (generate_password_hash(password), (username or "").strip()),
        )
        self.conn.commit()
        if cursor.rowcount == 0:
            raise AccountError("Unknown user: {}".format(username))

    def set_active(self, username: str, active: bool) -> None:
        """Deactivating also frees the user's claims so cards are not stuck."""
        user = self.get_by_username(username)
        if user is None:
            raise AccountError("Unknown user: {}".format(username))
        self.conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if active else 0, user.id),
        )
        if not active:
            self.conn.execute(
                "DELETE FROM card_claims WHERE user_id = ?", (user.id,)
            )
        self.conn.commit()
