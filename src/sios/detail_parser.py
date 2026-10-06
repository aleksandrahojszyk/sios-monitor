from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .models import CardRecord, parse_card_number_year

DETAILS_HREF = re.compile(r"documents/details/id/(\d+)", re.I)
DOWNLOAD_HREF = re.compile(r"documents/download/id/(\d+)", re.I)

NORMALIZED_LABELS = {
    "numer karty/rok": "card_number",
    "rodzaj dokumentu": "document_type",
    "nazwa dokumentu": "document_name",
    "znak sprawy": "case_reference",
    "nazwa organu": "authority",
}

DATE_LABELS = {
    "data wpływu dokumentu": "received_at",
    "data wydania dokumentu": "issued_at",
    "data zatwierdzenia dokumentu": "approved_at",
    "data zamieszczenia dokumentu": "published_at",
    "data wprowadzenia": "entered_at",
}

LOCATION_LABELS = ("województwo", "powiat", "gmina")


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text


def _cell_value(cell: Tag) -> str:
    html = cell.decode_contents()
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    soup = BeautifulSoup(html, "html.parser")
    lines = [_clean_text(line) for line in soup.get_text("\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _empty_to_none(value: str) -> Optional[str]:
    text = value.strip()
    if not text:
        return None
    return text


def parse_detail_page(html: str, sios_id: int, source_url: str, base_url: str) -> CardRecord:
    soup = BeautifulSoup(html, "html.parser")
    raw_fields: dict[str, Any] = {}
    dates: dict[str, Optional[str]] = {}
    location_parts: dict[str, str] = {}
    related_cards: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []

    for row in soup.select("table.table1 tr"):
        cells = row.find_all("td")
        if len(cells) == 1:
            value = _cell_value(cells[0])
            if "Brak załączników" in value or cells[0].find("a", href=DOWNLOAD_HREF):
                raw_fields["Wersja elektroniczna"] = value or "Brak załączników."
            continue
        if len(cells) < 2:
            continue
        label = _clean_text(cells[0].get_text(" ", strip=True)).rstrip(":")
        value_cell = cells[1]
        value = _cell_value(value_cell)
        if not label:
            continue
        raw_fields[label] = value

        key = label.lower()
        if key in DATE_LABELS:
            dates[DATE_LABELS[key]] = _empty_to_none(value.replace("\n", " "))
        if key in LOCATION_LABELS:
            cleaned = _empty_to_none(value.replace("\n", " "))
            if cleaned:
                location_parts[key] = cleaned
        if key == "numery kart innych dokumentów w sprawie":
            for link in value_cell.find_all("a", href=DETAILS_HREF):
                href = str(link.get("href") or "")
                match = DETAILS_HREF.search(href)
                if match:
                    related_cards.append(
                        {
                            "sios_id": int(match.group(1)),
                            "card_number": _empty_to_none(link.get_text(" ", strip=True)),
                            "url": urljoin(base_url.rstrip("/") + "/", href),
                        }
                    )

    for link in soup.find_all("a", href=DOWNLOAD_HREF):
        href = str(link.get("href") or "")
        match = DOWNLOAD_HREF.search(href)
        if not match:
            continue
        attachments.append(
            {
                "file_id": int(match.group(1)),
                "filename": _empty_to_none(link.get_text(" ", strip=True)),
                "url": urljoin(base_url.rstrip("/") + "/", href),
            }
        )
    if attachments:
        raw_fields["_attachments"] = attachments
    if related_cards:
        raw_fields["_related_cards"] = related_cards

    card_number = _empty_to_none(str(raw_fields.get("Numer karty/rok") or ""))
    parsed_number, year = parse_card_number_year(card_number)

    location = None
    if location_parts:
        location = " / ".join(
            location_parts[key] for key in LOCATION_LABELS if key in location_parts
        )

    return CardRecord(
        sios_id=sios_id,
        card_number=parsed_number,
        year=year,
        document_name=_empty_to_none(str(raw_fields.get("Nazwa dokumentu") or "")),
        document_type=_empty_to_none(str(raw_fields.get("Rodzaj dokumentu") or "")),
        case_reference=_empty_to_none(str(raw_fields.get("Znak sprawy") or "")),
        authority=_empty_to_none(str(raw_fields.get("Nazwa organu") or "")),
        location=location,
        dates=dates,
        matched_keywords=[],
        source_url=source_url,
        raw_fields=raw_fields,
    )
