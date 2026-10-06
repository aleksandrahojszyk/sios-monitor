from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


DETAIL_PATH = "/documents/details/id/{sios_id}"
SEARCH_PATH = "/search/common"
# Increment when normalized fields or parser semantics change. Existing cards
# then establish a new baseline instead of emitting source-data CHANGED events.
CARD_PARSER_VERSION = "2"


def detail_url(base_url: str, sios_id: int) -> str:
    return f"{base_url.rstrip('/')}{DETAIL_PATH.format(sios_id=sios_id)}"


def parse_card_number_year(card_number: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    if not card_number:
        return None, None
    text = card_number.strip()
    if "/" not in text:
        return text or None, None
    left, right = text.rsplit("/", 1)
    year: Optional[int] = None
    if right.isdigit():
        year = int(right)
    return (left + "/" + right) if left else text, year


@dataclass
class SearchHit:
    sios_id: int
    card_number: Optional[str]
    year: Optional[int]
    document_name: Optional[str]
    document_type: Optional[str]
    topics: list[str]
    subject_snippet: Optional[str]
    date: Optional[str]
    case_reference: Optional[str]
    location: Optional[str]
    voivodeship: Optional[str]
    county: Optional[str]
    municipality: Optional[str]
    detail_url: str
    keyword: str


@dataclass
class CardRecord:
    sios_id: int
    card_number: Optional[str]
    year: Optional[int]
    document_name: Optional[str]
    document_type: Optional[str]
    case_reference: Optional[str]
    authority: Optional[str]
    location: Optional[str]
    dates: dict[str, Optional[str]]
    matched_keywords: list[str]
    source_url: str
    raw_fields: dict[str, Any]
    parser_version: str = CARD_PARSER_VERSION
    search_metadata: dict[str, Any] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "sios_id": self.sios_id,
            "card_number": self.card_number,
            "year": self.year,
            "document_name": self.document_name,
            "document_type": self.document_type,
            "case_reference": self.case_reference,
            "authority": self.authority,
            "location": self.location,
            "dates": self.dates,
            "matched_keywords": list(self.matched_keywords),
            "source_url": self.source_url,
            "raw_fields": self.raw_fields,
            "parser_version": self.parser_version,
            "search_metadata": self.search_metadata,
        }


@dataclass
class PaginationDecision:
    stop: bool
    reason: Optional[str]
    new_ids: list[int]


def pagination_decision(
    page_ids: list[int],
    previous_ids: Optional[set[int]],
    seen_ids: set[int],
) -> PaginationDecision:
    """Decide whether to stop walking search pages.

    Overflow pages on SIOS may repeat the last page instead of returning empty.
    """
    ordered_unique: list[int] = []
    seen_page: set[int] = set()
    for item in page_ids:
        if item not in seen_page:
            seen_page.add(item)
            ordered_unique.append(item)

    if not ordered_unique:
        return PaginationDecision(stop=True, reason="empty_page", new_ids=[])

    page_set = set(ordered_unique)
    if previous_ids is not None and page_set == previous_ids:
        return PaginationDecision(stop=True, reason="repeated_page", new_ids=[])

    new_ids = [item for item in ordered_unique if item not in seen_ids]
    if not new_ids:
        return PaginationDecision(stop=True, reason="no_new_ids", new_ids=[])

    return PaginationDecision(stop=False, reason=None, new_ids=new_ids)
