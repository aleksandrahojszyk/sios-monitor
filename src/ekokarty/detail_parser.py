from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.sios.models import (
    SOURCE_SYSTEM_EKOKARTY,
    CardRecord,
    parse_card_number_year,
)

from .listing_parser import DETAIL_HREF
from .models import EKOKARTY_CARD_PARSER_VERSION, ListingHit, native_record_id

LABEL_ALIASES = {
    "numer karty/rok": "card_number",
    "rodzaj dokumentu": "document_type",
    "temat dokumentu": "topic",
    "nazwa dokumentu": "document_name",
    "zakres przedmiotowy dokumentu - opis dokumentu": "subject",
    "zakres przedmiotowy dokumentu": "subject",
    "obszar, którego dokument dotyczy, zgodnie z podziałem administracyjnym kraju": "location",
    "znak sprawy": "case_reference",
    "dokument wytworzył": "produced_by",
    "data dokumentu": "issued_at",
    "dokument zatwierdził": "approved_by",
    "data zatwierdzenia dokumentu": "approved_at",
    "miejsce przechowywania dokumentu": "storage_place",
    "adres elektroniczny zawierający odnośnik do dokumentu": "electronic_address",
    "czy dokument jest ostateczny tak/nie": "is_final",
    "numery kart innych dokumentów w sprawie": "related_cards",
    "zastrzeżenia dotyczące nieudostępniania informacji": "access_restrictions",
    "uwagi": "notes",
}

LISTING_DATE_PREFIXES = (
    "data zamieszczenie w wykazie",
    "data zamieszczenia w wykazie",
)
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _cell_value(cell: Tag) -> str:
    html = cell.decode_contents()
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    if "<" not in html:
        return _clean(html)
    soup = BeautifulSoup(html, "html.parser")
    lines = [_clean(line) for line in soup.get_text("\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _empty_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"nie dotyczy", "brak"}:
        return text
    return text


def _normalize_label(label: str) -> str:
    text = _clean(label).rstrip(":")
    text = re.sub(r"^\d+\.?\s*", "", text)
    return text.lower()


def _label_key(label: str) -> Optional[str]:
    normalized = _normalize_label(label)
    if normalized in LABEL_ALIASES:
        return LABEL_ALIASES[normalized]
    for prefix in LISTING_DATE_PREFIXES:
        if normalized.startswith(prefix):
            return "listing_date"
    return None


def parse_detail_page(
    html: str,
    *,
    slug: str,
    card_id: str,
    source_url: str,
    base_url: str,
    authority: str,
    listing_hit: Optional[ListingHit] = None,
) -> CardRecord:
    soup = BeautifulSoup(html, "html.parser")
    raw_fields: dict[str, Any] = {}
    mapped: dict[str, str] = {}
    related_cards: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        if len(cells) >= 3 and _clean(cells[0].get_text(" ", strip=True)).rstrip(".").isdigit():
            label_cell, value_cell = cells[1], cells[2]
        else:
            label_cell, value_cell = cells[0], cells[1]
        label = _clean(label_cell.get_text(" ", strip=True)).rstrip(":")
        if not label:
            continue
        value = _cell_value(value_cell)
        raw_fields[label] = value
        key = _label_key(label)
        if key:
            mapped[key] = value
        if key == "related_cards":
            for link in value_cell.find_all("a", href=DETAIL_HREF):
                href = str(link.get("href") or "")
                match = DETAIL_HREF.search(href)
                if match is None:
                    continue
                related_cards.append(
                    {
                        "card_number": _empty_to_none(link.get_text(" ", strip=True)),
                        "slug": match.group("slug"),
                        "card_id": match.group("card_id"),
                        "secondary_id": match.group("secondary_id"),
                        "url": urljoin(base_url.rstrip("/") + "/", href),
                    }
                )
        if key == "electronic_address":
            for match in URL_RE.finditer(value):
                attachments.append(
                    {
                        "url": match.group(0),
                        "source": "electronic_address",
                    }
                )
            for link in value_cell.find_all("a", href=True):
                href = str(link.get("href") or "")
                if href.lower().startswith("http"):
                    attachments.append(
                        {
                            "url": href,
                            "filename": _empty_to_none(link.get_text(" ", strip=True)),
                            "source": "electronic_address",
                        }
                    )

    if related_cards:
        raw_fields["_related_cards"] = related_cards
    if attachments:
        raw_fields["_attachments"] = attachments
    raw_fields["_identity"] = {
        "source_system": SOURCE_SYSTEM_EKOKARTY,
        "institution_slug": slug,
        "card_id": card_id,
        "native_record_id": native_record_id(slug, card_id),
    }
    if listing_hit is not None:
        raw_fields["_search"] = {
            "keyword": listing_hit.keyword,
            "document_name": listing_hit.document_name,
            "document_type": listing_hit.document_type,
            "topic": listing_hit.topic,
            "subject_snippet": listing_hit.subject_snippet,
            "listing_date": listing_hit.listing_date,
            "secondary_id": listing_hit.secondary_id,
        }

    card_number = _empty_to_none(mapped.get("card_number") or "")
    if listing_hit is not None:
        card_number = card_number or listing_hit.card_number
    parsed_number, year = parse_card_number_year(card_number)
    if listing_hit is not None:
        year = year or listing_hit.year

    listing_date = _empty_to_none(mapped.get("listing_date") or "")
    if listing_hit is not None:
        listing_date = listing_date or listing_hit.listing_date
    issued_at = _empty_to_none(mapped.get("issued_at") or "")
    approved_at = _empty_to_none(mapped.get("approved_at") or "")
    dates = {
        "listing_date": listing_date,
        "issued_at": issued_at,
        "approved_at": approved_at,
    }

    location = _empty_to_none(mapped.get("location") or "")
    document_name = _empty_to_none(mapped.get("document_name") or "")
    document_type = _empty_to_none(mapped.get("document_type") or "")
    case_reference = _empty_to_none(mapped.get("case_reference") or "")
    if listing_hit is not None:
        document_name = document_name or listing_hit.document_name
        document_type = document_type or listing_hit.document_type

    return CardRecord(
        sios_id=None,
        card_number=parsed_number,
        year=year,
        document_name=document_name,
        document_type=document_type,
        case_reference=case_reference,
        authority=authority,
        location=location,
        dates=dates,
        matched_keywords=[],
        source_url=source_url,
        raw_fields=raw_fields,
        parser_version=EKOKARTY_CARD_PARSER_VERSION,
        source_system=SOURCE_SYSTEM_EKOKARTY,
        native_record_id=native_record_id(slug, card_id),
    )
