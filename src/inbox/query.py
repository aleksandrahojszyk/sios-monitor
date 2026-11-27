from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional

from src.sios.models import canonical_record_key
from src.sios.storage import Storage, utc_now

from .geography import parse_location
from .models import (
    DATE_FIELD_LABELS,
    DEFAULT_PAGE_SIZE,
    EVENT_CARD_VIEWED,
    EVENT_NOTE_UPDATED,
    EVENT_SOURCE_OPENED,
    EVENT_STATUS_CHANGED,
    MAX_PAGE_SIZE,
    REVIEW_MONITOR,
    REVIEW_NEW,
    REVIEW_REQUEST_DOCUMENTS,
    REVIEW_STATUSES,
    InboxCard,
    InboxFacets,
    InboxMetrics,
    InboxPage,
    InboxQuery,
)

# Per-source display date. SIOS uses entered_at (collection basis);
# EkoKarty uses listing_date. These are not the same event.
DISPLAY_DATE_SQL = """
CASE cards.source_system
    WHEN 'ekokarty' THEN COALESCE(
        cards.listing_date,
        substr(json_extract(cards.dates_json, '$.listing_date'), 1, 10)
    )
    ELSE COALESCE(
        substr(json_extract(cards.dates_json, '$.entered_at'), 1, 10),
        substr(json_extract(cards.dates_json, '$.published_at'), 1, 10)
    )
END
"""

KEYWORDS_SQL = """
COALESCE((
    SELECT GROUP_CONCAT(keyword, ' | ')
    FROM keyword_matches
    WHERE keyword_matches.source_system = cards.source_system
      AND keyword_matches.native_record_id = cards.native_record_id
), '')
"""

RELATED_COUNT_SQL = """
COALESCE(json_array_length(json_extract(cards.raw_fields_json, '$._related_cards')), 0)
"""

HAS_ATTACHMENT_SQL = """
CASE
    WHEN json_array_length(json_extract(cards.raw_fields_json, '$._attachments')) > 0
    THEN 1 ELSE 0
END
"""


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _like_term(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )
    return "%{}%".format(escaped)


class InboxRepository:
    def __init__(
        self,
        storage: Storage,
        participant_id: Optional[str] = None,
        session_id: Optional[int] = None,
    ) -> None:
        self.storage = storage
        self.conn = storage.conn
        self.participant_id = participant_id
        self.session_id = session_id

    def _filters(self, query: InboxQuery) -> tuple[str, list[Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if query.status:
            if query.status == REVIEW_NEW:
                clauses.append(
                    "(card_reviews.status IS NULL OR card_reviews.status = ?)"
                )
                params.append(REVIEW_NEW)
            else:
                clauses.append("card_reviews.status = ?")
                params.append(query.status)
        if query.source:
            clauses.append("cards.source_system = ?")
            params.append(query.source)
        if query.authority:
            clauses.append("cards.authority = ?")
            params.append(query.authority)
        if query.document_type:
            clauses.append("cards.document_type = ?")
            params.append(query.document_type)
        if query.keyword:
            clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM keyword_matches
                    WHERE keyword_matches.source_system = cards.source_system
                      AND keyword_matches.native_record_id = cards.native_record_id
                      AND keyword_matches.keyword = ?
                )
                """
            )
            params.append(query.keyword)
        if query.voivodeship:
            clauses.append("cards.source_system = 'sios'")
            clauses.append(
                "(cards.location = ? OR cards.location LIKE ? ESCAPE '\\')"
            )
            voiv = (
                query.voivodeship.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            params.extend([voiv, "{} /%".format(voiv)])
        if query.county:
            clauses.append("cards.source_system = 'sios'")
            clauses.append("cards.location LIKE ? ESCAPE '\\'")
            county = (
                query.county.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            if query.voivodeship:
                voiv = (
                    query.voivodeship.replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                params.append("{} / {} /%".format(voiv, county))
            else:
                params.append("% / {} /%".format(county))
        display_date = "({})".format(DISPLAY_DATE_SQL.strip())
        if query.date_from:
            clauses.append("{} >= ?".format(display_date))
            params.append(query.date_from)
        if query.date_to:
            clauses.append("{} <= ?".format(display_date))
            params.append(query.date_to)
        if query.q:
            term = _like_term(query.q.strip())
            clauses.append(
                """
                (
                    cards.card_number LIKE ? ESCAPE '\\'
                    OR cards.case_reference LIKE ? ESCAPE '\\'
                    OR cards.document_name LIKE ? ESCAPE '\\'
                    OR cards.authority LIKE ? ESCAPE '\\'
                    OR cards.location LIKE ? ESCAPE '\\'
                )
                """
            )
            params.extend([term, term, term, term, term])
        return " AND ".join(clauses), params

    def _card_from_row(self, row: Any, *, include_raw: bool = False) -> InboxCard:
        data = dict(row)
        dates = json.loads(data.get("dates_json") or "{}")
        raw_fields: dict[str, Any] = {}
        related: list[dict[str, Any]] = []
        attachments: list[dict[str, Any]] = []
        if include_raw:
            raw_fields = json.loads(data.get("raw_fields_json") or "{}")
            related = list(raw_fields.get("_related_cards") or [])
            attachments = list(raw_fields.get("_attachments") or [])
        keywords_raw = data.get("matched_keywords") or ""
        keywords = [item.strip() for item in keywords_raw.split(" | ") if item.strip()]
        voivodeship, county, municipality = parse_location(
            data["source_system"], data.get("location")
        )
        display_date = data.get("display_date")
        if display_date:
            display_date = str(display_date)[:10]
        return InboxCard(
            source_system=data["source_system"],
            native_record_id=data["native_record_id"],
            external_key=canonical_record_key(
                data["source_system"], data["native_record_id"]
            ),
            card_number=data.get("card_number"),
            year=data.get("year"),
            authority=data.get("authority"),
            document_type=data.get("document_type"),
            document_name=data.get("document_name"),
            case_reference=data.get("case_reference"),
            location=data.get("location"),
            voivodeship=voivodeship,
            county=county,
            municipality=municipality,
            display_date=display_date,
            display_date_field=DATE_FIELD_LABELS.get(
                data["source_system"], "display_date"
            ),
            dates=dates,
            matched_keywords=keywords,
            related_cards_count=int(data.get("related_cards_count") or 0),
            has_attachment=bool(data.get("has_attachment")),
            source_url=data.get("source_url") or None,
            review_status=data.get("review_status") or REVIEW_NEW,
            review_note=data.get("review_note"),
            reviewed_at=data.get("reviewed_at"),
            first_seen_at=data.get("first_seen_at"),
            raw_fields=raw_fields,
            related_cards=related,
            attachments=attachments,
            assignee_user_id=data.get("assignee_user_id"),
            assignee_name=data.get("assignee_name"),
            claimed_at=data.get("claimed_at"),
        )

    def search(self, query: InboxQuery) -> InboxPage:
        query = replace(
            query,
            page=max(1, query.page),
            page_size=min(MAX_PAGE_SIZE, max(1, query.page_size or DEFAULT_PAGE_SIZE)),
        )
        if query.status == "":
            query = replace(query, status=None)
        where, params = self._filters(query)
        from_sql = """
            FROM cards
            LEFT JOIN card_reviews
                ON card_reviews.source_system = cards.source_system
               AND card_reviews.native_record_id = cards.native_record_id
            LEFT JOIN card_claims
                ON card_claims.source_system = cards.source_system
               AND card_claims.native_record_id = cards.native_record_id
            LEFT JOIN users AS claim_users
                ON claim_users.id = card_claims.user_id
            WHERE {where}
        """.format(where=where)
        total = int(
            self.conn.execute(
                "SELECT COUNT(*) AS n " + from_sql, params
            ).fetchone()["n"]
        )
        offset = (query.page - 1) * query.page_size
        rows = self.conn.execute(
            """
            SELECT
                cards.source_system,
                cards.native_record_id,
                cards.card_number,
                cards.year,
                cards.authority,
                cards.document_type,
                cards.document_name,
                cards.case_reference,
                cards.location,
                cards.dates_json,
                cards.source_url,
                cards.first_seen_at,
                COALESCE(card_reviews.status, ?) AS review_status,
                card_reviews.note AS review_note,
                card_reviews.reviewed_at,
                card_claims.user_id AS assignee_user_id,
                claim_users.display_name AS assignee_name,
                card_claims.claimed_at AS claimed_at,
                {display_date} AS display_date,
                {keywords} AS matched_keywords,
                {related} AS related_cards_count,
                {attachments} AS has_attachment
            {from_sql}
            ORDER BY display_date DESC, cards.first_seen_at DESC,
                     cards.source_system, cards.native_record_id
            LIMIT ? OFFSET ?
            """.format(
                display_date=DISPLAY_DATE_SQL,
                keywords=KEYWORDS_SQL,
                related=RELATED_COUNT_SQL,
                attachments=HAS_ATTACHMENT_SQL,
                from_sql=from_sql,
            ),
            [REVIEW_NEW] + params + [query.page_size, offset],
        ).fetchall()
        items = [self._card_from_row(row) for row in rows]
        return InboxPage(
            items=items,
            total=total,
            page=query.page,
            page_size=query.page_size,
            query=query,
        )

    def get_card(self, source_system: str, native_record_id: str) -> Optional[InboxCard]:
        row = self.conn.execute(
            """
            SELECT
                cards.source_system,
                cards.native_record_id,
                cards.card_number,
                cards.year,
                cards.authority,
                cards.document_type,
                cards.document_name,
                cards.case_reference,
                cards.location,
                cards.dates_json,
                cards.raw_fields_json,
                cards.source_url,
                cards.first_seen_at,
                COALESCE(card_reviews.status, ?) AS review_status,
                card_reviews.note AS review_note,
                card_reviews.reviewed_at,
                card_claims.user_id AS assignee_user_id,
                claim_users.display_name AS assignee_name,
                card_claims.claimed_at AS claimed_at,
                {display_date} AS display_date,
                {keywords} AS matched_keywords,
                {related} AS related_cards_count,
                {attachments} AS has_attachment
            FROM cards
            LEFT JOIN card_reviews
                ON card_reviews.source_system = cards.source_system
               AND card_reviews.native_record_id = cards.native_record_id
            LEFT JOIN card_claims
                ON card_claims.source_system = cards.source_system
               AND card_claims.native_record_id = cards.native_record_id
            LEFT JOIN users AS claim_users
                ON claim_users.id = card_claims.user_id
            WHERE cards.source_system = ? AND cards.native_record_id = ?
            """.format(
                display_date=DISPLAY_DATE_SQL,
                keywords=KEYWORDS_SQL,
                related=RELATED_COUNT_SQL,
                attachments=HAS_ATTACHMENT_SQL,
            ),
            (REVIEW_NEW, source_system, native_record_id),
        ).fetchone()
        if row is None:
            return None
        return self._card_from_row(row, include_raw=True)

    def metrics(self) -> InboxMetrics:
        total_cards = int(
            self.conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"]
        )
        reviewed = int(
            self.conn.execute(
                "SELECT COUNT(*) AS n FROM card_reviews WHERE status != ?",
                (REVIEW_NEW,),
            ).fetchone()["n"]
        )
        total_new = total_cards - reviewed
        reviewed_today = int(
            self.conn.execute(
                """
                SELECT COUNT(*) AS n FROM card_reviews
                WHERE reviewed_at IS NOT NULL
                  AND substr(reviewed_at, 1, 10) = ?
                """,
                (_today_utc(),),
            ).fetchone()["n"]
        )
        request_documents = int(
            self.conn.execute(
                "SELECT COUNT(*) AS n FROM card_reviews WHERE status = ?",
                (REVIEW_REQUEST_DOCUMENTS,),
            ).fetchone()["n"]
        )
        monitor = int(
            self.conn.execute(
                "SELECT COUNT(*) AS n FROM card_reviews WHERE status = ?",
                (REVIEW_MONITOR,),
            ).fetchone()["n"]
        )
        return InboxMetrics(
            total_new=total_new,
            reviewed_today=reviewed_today,
            request_documents=request_documents,
            monitor=monitor,
            total_cards=total_cards,
        )

    def facets(self) -> InboxFacets:
        sources = [
            str(row["source_system"])
            for row in self.conn.execute(
                "SELECT DISTINCT source_system FROM cards ORDER BY source_system"
            )
        ]
        authorities = [
            str(row["authority"])
            for row in self.conn.execute(
                """
                SELECT DISTINCT authority FROM cards
                WHERE authority IS NOT NULL AND authority != ''
                ORDER BY authority
                """
            )
        ]
        document_types = [
            str(row["document_type"])
            for row in self.conn.execute(
                """
                SELECT DISTINCT document_type FROM cards
                WHERE document_type IS NOT NULL AND document_type != ''
                ORDER BY document_type
                """
            )
        ]
        keywords = [
            str(row["keyword"])
            for row in self.conn.execute(
                "SELECT DISTINCT keyword FROM keyword_matches ORDER BY keyword"
            )
        ]
        voivodeships: list[str] = []
        counties: list[str] = []
        seen_voiv: set[str] = set()
        seen_county: set[str] = set()
        for row in self.conn.execute(
            """
            SELECT DISTINCT location FROM cards
            WHERE source_system = 'sios' AND location IS NOT NULL
            """
        ):
            voiv, county, _muni = parse_location("sios", row["location"])
            if voiv and voiv not in seen_voiv:
                seen_voiv.add(voiv)
                voivodeships.append(voiv)
            if county and county not in seen_county:
                seen_county.add(county)
                counties.append(county)
        voivodeships.sort()
        counties.sort()
        return InboxFacets(
            sources=sources,
            authorities=authorities,
            document_types=document_types,
            keywords=keywords,
            voivodeships=voivodeships,
            counties=counties,
        )

    def _log_event(
        self,
        source_system: str,
        native_record_id: str,
        event_type: str,
        previous_status: Optional[str] = None,
        new_status: Optional[str] = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO review_events (
                source_system, native_record_id, event_type,
                previous_status, new_status, created_at,
                participant_id, session_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_system,
                native_record_id,
                event_type,
                previous_status,
                new_status,
                utc_now(),
                self.participant_id,
                self.session_id,
            ),
        )

    def mark_viewed(self, source_system: str, native_record_id: str) -> None:
        self._log_event(source_system, native_record_id, EVENT_CARD_VIEWED)
        self.conn.commit()

    def mark_source_opened(
        self,
        source_system: str,
        native_record_id: str,
        *,
        previous_status: Optional[str] = None,
    ) -> None:
        self._log_event(
            source_system,
            native_record_id,
            EVENT_SOURCE_OPENED,
            previous_status=previous_status,
        )
        self.conn.commit()

    def set_status(
        self,
        source_system: str,
        native_record_id: str,
        status: str,
        note: Optional[str] = None,
    ) -> InboxCard:
        if status not in REVIEW_STATUSES:
            raise ValueError("Unsupported review status: {}".format(status))
        card = self.get_card(source_system, native_record_id)
        if card is None:
            raise KeyError("Unknown card")
        previous = card.review_status
        now = utc_now()
        existing = self.conn.execute(
            """
            SELECT id, note FROM card_reviews
            WHERE source_system = ? AND native_record_id = ?
            """,
            (source_system, native_record_id),
        ).fetchone()
        kept_note = card.review_note if note is None else note
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO card_reviews (
                    source_system, native_record_id, external_key, status,
                    note, reviewed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_system,
                    native_record_id,
                    card.external_key,
                    status,
                    kept_note,
                    now,
                    now,
                    now,
                ),
            )
        else:
            self.conn.execute(
                """
                UPDATE card_reviews
                SET status = ?, note = ?, reviewed_at = ?, updated_at = ?
                WHERE source_system = ? AND native_record_id = ?
                """,
                (
                    status,
                    kept_note if note is not None else existing["note"],
                    now,
                    now,
                    source_system,
                    native_record_id,
                ),
            )
        if previous != status:
            self._log_event(
                source_system,
                native_record_id,
                EVENT_STATUS_CHANGED,
                previous_status=previous,
                new_status=status,
            )
        self.conn.commit()
        updated = self.get_card(source_system, native_record_id)
        assert updated is not None
        return updated

    def set_note(
        self,
        source_system: str,
        native_record_id: str,
        note: str,
    ) -> InboxCard:
        card = self.get_card(source_system, native_record_id)
        if card is None:
            raise KeyError("Unknown card")
        now = utc_now()
        existing = self.conn.execute(
            """
            SELECT id FROM card_reviews
            WHERE source_system = ? AND native_record_id = ?
            """,
            (source_system, native_record_id),
        ).fetchone()
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO card_reviews (
                    source_system, native_record_id, external_key, status,
                    note, reviewed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
                """,
                (
                    source_system,
                    native_record_id,
                    card.external_key,
                    REVIEW_NEW,
                    note,
                    now,
                    now,
                ),
            )
        else:
            self.conn.execute(
                """
                UPDATE card_reviews
                SET note = ?, updated_at = ?
                WHERE source_system = ? AND native_record_id = ?
                """,
                (note, now, source_system, native_record_id),
            )
        self._log_event(source_system, native_record_id, EVENT_NOTE_UPDATED)
        self.conn.commit()
        updated = self.get_card(source_system, native_record_id)
        assert updated is not None
        return updated
