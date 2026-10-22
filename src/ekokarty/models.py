from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.sios.models import SOURCE_SYSTEM_EKOKARTY, canonical_record_key

EKOKARTY_CARD_PARSER_VERSION = "1"
RESULT_CAP = 2000
SOURCE_SYSTEM = SOURCE_SYSTEM_EKOKARTY


def native_record_id(slug: str, card_id: str) -> str:
    return "{}:{}".format(slug, card_id)


def canonical_key(slug: str, card_id: str) -> str:
    return canonical_record_key(SOURCE_SYSTEM, native_record_id(slug, card_id))


@dataclass
class ListingHit:
    card_id: str
    slug: str
    secondary_id: Optional[str]
    card_type: Optional[str]
    card_number: Optional[str]
    year: Optional[int]
    document_name: Optional[str]
    document_type: Optional[str]
    topic: Optional[str]
    subject_snippet: Optional[str]
    listing_date: Optional[str]
    detail_path: str
    detail_url: str
    keyword: str

    @property
    def native_record_id(self) -> str:
        return native_record_id(self.slug, self.card_id)

    @property
    def canonical_key(self) -> str:
        return canonical_key(self.slug, self.card_id)


@dataclass
class DateWindow:
    start: date
    end: date

    def iso_start(self) -> str:
        return self.start.isoformat()

    def iso_end(self) -> str:
        return self.end.isoformat()


@dataclass
class KeywordRunResult:
    keyword: str
    source_key: Optional[str] = None
    pages_processed: int = 0
    unique_cards: int = 0
    new_cards: int = 0
    changed_cards: int = 0
    unchanged_cards: int = 0
    existing_cards: int = 0
    errors: int = 0
    stop_reason: Optional[str] = None
    run_id: Optional[int] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    window_mode: Optional[str] = None
    watermark_used: Optional[str] = None
    overlap_days: int = 0
    cards_encountered: int = 0
    cards_in_window: int = 0
    known_cards_skipped: int = 0
    detail_pages_fetched: int = 0
    window_splits: int = 0
    capped_windows: int = 0
    status: str = "ok"
    seen_keys: set[str] = field(default_factory=set)
