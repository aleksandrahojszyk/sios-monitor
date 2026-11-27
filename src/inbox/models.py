from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

REVIEW_NEW = "NEW"
REVIEW_RELEVANT = "RELEVANT"
REVIEW_IGNORE = "IGNORE"
REVIEW_MONITOR = "MONITOR"
REVIEW_REQUEST_DOCUMENTS = "REQUEST_DOCUMENTS"

REVIEW_STATUSES = (
    REVIEW_NEW,
    REVIEW_RELEVANT,
    REVIEW_IGNORE,
    REVIEW_MONITOR,
    REVIEW_REQUEST_DOCUMENTS,
)

REVIEW_LABELS = {
    REVIEW_NEW: "New",
    REVIEW_RELEVANT: "Relevant",
    REVIEW_IGNORE: "Ignore",
    REVIEW_MONITOR: "Monitor",
    REVIEW_REQUEST_DOCUMENTS: "Request documents",
}

QUICK_ACTIONS = (
    REVIEW_RELEVANT,
    REVIEW_IGNORE,
    REVIEW_MONITOR,
    REVIEW_REQUEST_DOCUMENTS,
)

EVENT_CARD_VIEWED = "card_viewed"
EVENT_STATUS_CHANGED = "status_changed"
EVENT_NOTE_UPDATED = "note_updated"
EVENT_SOURCE_OPENED = "source_opened"

SOURCE_LABELS = {
    "sios": "SIOS",
    "ekokarty": "EkoKarty",
}

DATE_FIELD_LABELS = {
    "sios": "entered_at",
    "ekokarty": "listing_date",
}

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100


@dataclass
class InboxQuery:
    status: Optional[str] = REVIEW_NEW
    source: Optional[str] = None
    authority: Optional[str] = None
    document_type: Optional[str] = None
    keyword: Optional[str] = None
    voivodeship: Optional[str] = None
    county: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    q: Optional[str] = None
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass
class InboxCard:
    source_system: str
    native_record_id: str
    external_key: str
    card_number: Optional[str]
    year: Optional[int]
    authority: Optional[str]
    document_type: Optional[str]
    document_name: Optional[str]
    case_reference: Optional[str]
    location: Optional[str]
    voivodeship: Optional[str]
    county: Optional[str]
    municipality: Optional[str]
    display_date: Optional[str]
    display_date_field: str
    dates: dict[str, Optional[str]]
    matched_keywords: list[str]
    related_cards_count: int
    has_attachment: bool
    source_url: Optional[str]
    review_status: str
    review_note: Optional[str]
    reviewed_at: Optional[str]
    first_seen_at: Optional[str] = None
    raw_fields: dict[str, Any] = field(default_factory=dict)
    related_cards: list[dict[str, Any]] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    assignee_user_id: Optional[int] = None
    assignee_name: Optional[str] = None
    claimed_at: Optional[str] = None

    @property
    def source_label(self) -> str:
        return SOURCE_LABELS.get(self.source_system, self.source_system)

    @property
    def review_label(self) -> str:
        return REVIEW_LABELS.get(self.review_status, self.review_status)


@dataclass
class InboxPage:
    items: list[InboxCard]
    total: int
    page: int
    page_size: int
    query: InboxQuery

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 1
        return max(1, (self.total + self.page_size - 1) // self.page_size)


@dataclass
class InboxMetrics:
    total_new: int
    reviewed_today: int
    request_documents: int
    monitor: int
    total_cards: int


@dataclass
class InboxFacets:
    sources: list[str]
    authorities: list[str]
    document_types: list[str]
    keywords: list[str]
    voivodeships: list[str]
    counties: list[str]
