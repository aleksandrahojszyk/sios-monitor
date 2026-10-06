from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .models import SearchHit, parse_card_number_year

DETAILS_HREF = re.compile(r"documents/details/id/(\d+)", re.I)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
TOTAL_RE = re.compile(r"Liczba wyświetlanych pozycji:\s*(\d+)", re.I)


def parse_total_count(html: str) -> Optional[int]:
    match = TOTAL_RE.search(html)
    if not match:
        return None
    return int(match.group(1))


def _cell_text_lines(cell: Tag) -> list[str]:
    raw = cell.decode_contents()
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text("\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return [line for line in lines if line]


def _parse_topics(type_cell: Tag) -> tuple[Optional[str], list[str]]:
    lines = _cell_text_lines(type_cell)
    document_type = None
    topics: list[str] = []
    in_topics = False
    for line in lines:
        lowered = line.lower().rstrip(":")
        if lowered.startswith("temat"):
            in_topics = True
            continue
        if in_topics:
            topics.append(line.lstrip("- ").strip())
        elif document_type is None:
            document_type = line
    return document_type, topics


def _parse_name_scope(name_cell: Tag) -> tuple[Optional[str], Optional[str]]:
    lines = _cell_text_lines(name_cell)
    if not lines:
        return None, None
    if len(lines) == 1:
        return lines[0], None
    return lines[0], " ".join(lines[1:])


def _parse_date_case(cell: Tag) -> tuple[Optional[str], Optional[str]]:
    lines = _cell_text_lines(cell)
    date = None
    leftovers: list[str] = []
    for line in lines:
        if date is None and DATE_RE.fullmatch(line):
            date = line
        else:
            leftovers.append(line)
    case_reference = " ".join(leftovers).strip() or None
    return date, case_reference


def _parse_location(cell: Tag) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    lines = _cell_text_lines(cell)
    if not lines:
        return None, None, None, None
    joined = " / ".join(lines)
    # Prefer the first slash-separated location line.
    location_line = lines[0]
    parts = [part.strip() for part in location_line.split("/")]
    voivodeship = parts[0] or None if parts else None
    county = parts[1] or None if len(parts) > 1 else None
    municipality = parts[2] or None if len(parts) > 2 else None
    location = location_line.strip() or joined
    return location or None, voivodeship, county, municipality


def parse_search_page(html: str, keyword: str, base_url: str) -> list[SearchHit]:
    soup = BeautifulSoup(html, "html.parser")
    hits: list[SearchHit] = []
    seen: set[int] = set()

    result_table = None
    for table in soup.find_all("table"):
        header = table.find("th")
        if header and "Nr karty" in header.get_text():
            result_table = table
            break

    rows = result_table.find_all("tr") if result_table else soup.find_all("tr")
    for row in rows:
        if row.find("th"):
            continue
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        link = row.find("a", href=DETAILS_HREF, class_=re.compile(r"fancybox"))
        if link is None:
            link = row.find("a", href=DETAILS_HREF)
        if link is None:
            continue
        href = str(link.get("href") or "")
        match = DETAILS_HREF.search(href)
        if not match:
            continue
        sios_id = int(match.group(1))
        if sios_id in seen:
            continue
        seen.add(sios_id)

        card_number_text = link.get_text(" ", strip=True) or None
        card_number, year = parse_card_number_year(card_number_text)
        document_type, topics = _parse_topics(cells[1])
        document_name, subject_snippet = _parse_name_scope(cells[2])
        date, case_reference = _parse_date_case(cells[3])
        location, voivodeship, county, municipality = _parse_location(cells[4])
        hits.append(
            SearchHit(
                sios_id=sios_id,
                card_number=card_number,
                year=year,
                document_name=document_name,
                document_type=document_type,
                topics=topics,
                subject_snippet=subject_snippet,
                date=date,
                case_reference=case_reference,
                location=location,
                voivodeship=voivodeship,
                county=county,
                municipality=municipality,
                detail_url=urljoin(base_url.rstrip("/") + "/", href),
                keyword=keyword,
            )
        )
    return hits
