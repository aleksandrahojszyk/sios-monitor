from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.sios.models import parse_card_number_year

from .models import ListingHit

DETAIL_HREF = re.compile(
    r"/wykaz/(?P<slug>[^/]+)/(?P<card_id>\d+)/(?P<secondary_id>\d+)/(?P<type>[A-Za-z]+)",
    re.I,
)

HEADER_ALIASES = {
    "numer karty": "card_number",
    "rok wydania": "year",
    "rodzaj dokumentu": "document_type",
    "nazwa dokumentu": "document_name",
    "temat dokumentu": "topic",
    "zakres przedmiotowy": "subject_snippet",
    "data karty": "listing_date",
    "data zamieszczenie w wykazie": "listing_date",
}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _cell_text(cell: Tag) -> str:
    raw = cell.decode_contents()
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    if "<" not in raw:
        return _clean(raw)
    soup = BeautifulSoup(raw, "html.parser")
    lines = [_clean(line) for line in soup.get_text("\n").split("\n")]
    return " ".join(line for line in lines if line).strip()


def _header_key(label: str) -> Optional[str]:
    lowered = _clean(label).lower().rstrip(":")
    if lowered in HEADER_ALIASES:
        return HEADER_ALIASES[lowered]
    for prefix, key in HEADER_ALIASES.items():
        if lowered.startswith(prefix):
            return key
    return None


def parse_listing_page(
    html: str,
    *,
    keyword: str,
    slug: str,
    base_url: str,
) -> list[ListingHit]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#tableKarty") or soup.find("table")
    if table is None:
        return []

    headers: list[Optional[str]] = []
    head_row = table.find("tr")
    if head_row is not None:
        for cell in head_row.find_all(["th", "td"]):
            headers.append(_header_key(cell.get_text(" ", strip=True)))

    hits: list[ListingHit] = []
    seen: set[str] = set()
    body_rows = table.select("tbody tr") or [
        row
        for row in table.find_all("tr")
        if row.find("td") is not None and row is not head_row
    ]
    for row in body_rows:
        href = str(row.get("data-href") or "")
        if not href:
            link = row.find("a", href=DETAIL_HREF)
            if link is not None:
                href = str(link.get("href") or "")
        match = DETAIL_HREF.search(href)
        if match is None:
            continue
        card_id = match.group("card_id")
        row_slug = match.group("slug")
        if row_slug != slug:
            continue
        identity = "{}:{}".format(row_slug, card_id)
        if identity in seen:
            continue
        seen.add(identity)

        values: dict[str, str] = {}
        cells = row.find_all("td")
        for index, cell in enumerate(cells):
            key = headers[index] if index < len(headers) else None
            if key:
                values[key] = _cell_text(cell)

        card_number = values.get("card_number") or None
        parsed_number, year_from_number = parse_card_number_year(card_number)
        year_text = values.get("year") or ""
        year = int(year_text) if year_text.isdigit() else year_from_number
        path = href if href.startswith("/") or href.startswith("http") else "/" + href
        hits.append(
            ListingHit(
                card_id=card_id,
                slug=row_slug,
                secondary_id=match.group("secondary_id"),
                card_type=match.group("type"),
                card_number=parsed_number,
                year=year,
                document_name=values.get("document_name") or None,
                document_type=values.get("document_type") or None,
                topic=values.get("topic") or None,
                subject_snippet=values.get("subject_snippet") or None,
                listing_date=values.get("listing_date") or None,
                detail_path=path if path.startswith("/") else path,
                detail_url=urljoin(base_url.rstrip("/") + "/", href),
                keyword=keyword,
            )
        )
    return hits
