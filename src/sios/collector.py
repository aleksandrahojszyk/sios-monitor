from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .client import SiosClient, SiosHttpError
from .config import CollectorSettings, flatten_keywords, load_keyword_groups, load_settings
from .detail_parser import parse_detail_page
from .logging_utils import configure_logging, log_extra
from .models import PaginationDecision, SearchHit, pagination_decision
from .search_parser import parse_search_page, parse_total_count
from .storage import STATUS_CHANGED, STATUS_NEW, STATUS_UNCHANGED, Storage, UpsertResult

logger = logging.getLogger(__name__)

STOP_EMPTY_PAGE = "EMPTY_PAGE"
STOP_REPEATED_PAGE = "REPEATED_PAGE"
STOP_NO_NEW_IDS = "NO_NEW_IDS"
STOP_MAX_PAGES = "MAX_PAGES"
STOP_HTTP_ERROR = "HTTP_ERROR"
STOP_COMPLETED = "COMPLETED"
STOP_PARTIAL_DETAIL_FAILURE = "PARTIAL_DETAIL_FAILURE"

_SEARCH_STOP_REASONS = {
    "empty_page": STOP_EMPTY_PAGE,
    "repeated_page": STOP_REPEATED_PAGE,
    "no_new_ids": STOP_NO_NEW_IDS,
    "max_pages": STOP_MAX_PAGES,
    "http_error": STOP_HTTP_ERROR,
}


def apply_stop_reason(result: KeywordRunResult) -> None:
    """Persist the stop the collector already chose.

    Search stops, including HTTP_ERROR and MAX_PAGES, are kept. Detail-fetch
    failures that happen without a search stop use PARTIAL_DETAIL_FAILURE.
    A card fetch with no search uses COMPLETED.
    """
    mapped = _SEARCH_STOP_REASONS.get(result.termination_reason or "")
    if mapped:
        result.stop_reason = mapped
    elif result.errors:
        result.stop_reason = STOP_PARTIAL_DETAIL_FAILURE
    else:
        result.stop_reason = STOP_COMPLETED


def _count_outcome(result: KeywordRunResult, status: str) -> None:
    if status == STATUS_NEW:
        result.new_cards += 1
    elif status == STATUS_CHANGED:
        result.changed_cards += 1
    elif status == STATUS_UNCHANGED:
        result.unchanged_cards += 1
    result.existing_cards = result.changed_cards + result.unchanged_cards


def keyword_slug(keyword: str) -> str:
    normalized = unicodedata.normalize("NFKD", keyword)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_").lower()
    return slug or "keyword"


def write_raw(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


@dataclass
class KeywordRunResult:
    keyword: str
    pages_processed: int = 0
    unique_cards: int = 0
    new_cards: int = 0
    changed_cards: int = 0
    unchanged_cards: int = 0
    existing_cards: int = 0
    errors: int = 0
    termination_reason: Optional[str] = None
    stop_reason: Optional[str] = None
    reported_total: Optional[int] = None
    run_id: Optional[int] = None
    status: str = "ok"


class Collector:
    def __init__(self, settings: CollectorSettings, storage: Storage, client: SiosClient) -> None:
        self.settings = settings
        self.storage = storage
        self.client = client

    def search(self, keyword: str, max_pages: Optional[int] = None) -> tuple[list[SearchHit], KeywordRunResult]:
        limit = max_pages if max_pages is not None else self.settings.max_pages
        hits_by_id: dict[int, SearchHit] = {}
        seen_ids: set[int] = set()
        previous_ids: Optional[set[int]] = None
        result = KeywordRunResult(keyword=keyword)
        page = 1
        while page <= limit:
            try:
                html = self.client.search(keyword, page=page)
            except SiosHttpError:
                result.errors += 1
                result.termination_reason = "http_error"
                result.status = "error"
                logger.exception(
                    "search_page_failed",
                    extra=log_extra(keyword=keyword, page=page),
                )
                break

            if self.settings.save_raw_html:
                filename = f"search_{keyword_slug(keyword)}_page_{page}.html"
                write_raw(self.settings.raw_search_dir / filename, html)

            if page == 1:
                result.reported_total = parse_total_count(html)

            page_hits = parse_search_page(html, keyword=keyword, base_url=self.settings.base_url)
            page_ids = [hit.sios_id for hit in page_hits]
            decision: PaginationDecision = pagination_decision(page_ids, previous_ids, seen_ids)
            result.pages_processed += 1
            logger.info(
                "search_page",
                extra=log_extra(
                    keyword=keyword,
                    page=page,
                    cards_on_page=len(set(page_ids)),
                    new_ids=len(decision.new_ids),
                    stop=decision.stop,
                    reason=decision.reason,
                ),
            )
            if decision.stop:
                result.termination_reason = decision.reason
                break

            for hit in page_hits:
                if hit.sios_id in decision.new_ids and hit.sios_id not in hits_by_id:
                    hits_by_id[hit.sios_id] = hit
            seen_ids.update(decision.new_ids)
            previous_ids = set(dict.fromkeys(page_ids))
            page += 1
        else:
            result.termination_reason = "max_pages"

        result.unique_cards = len(hits_by_id)
        logger.info(
            "search_finished",
            extra=log_extra(
                keyword=keyword,
                pages_processed=result.pages_processed,
                unique_cards=result.unique_cards,
                termination_reason=result.termination_reason,
                reported_total=result.reported_total,
            ),
        )
        return list(hits_by_id.values()), result

    def _persist_run(
        self,
        run_id: int,
        result: KeywordRunResult,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        apply_stop_reason(result)
        self.storage.finish_run(
            run_id,
            pages_processed=result.pages_processed,
            cards_found=result.unique_cards,
            new_cards=result.new_cards,
            changed_cards=result.changed_cards,
            unchanged_cards=result.unchanged_cards,
            existing_cards=result.existing_cards,
            error_count=result.errors,
            reported_total=result.reported_total,
            stop_reason=result.stop_reason,
            status=status,
            error=error,
        )

    def fetch_card(
        self,
        sios_id: int,
        keywords: Optional[list[str]] = None,
        search_hit: Optional[SearchHit] = None,
        run_id: Optional[int] = None,
    ) -> Optional[UpsertResult]:
        """Fetch, parse, and store one card. Returns the observation outcome."""
        url = self.client.card_url(sios_id)
        try:
            html = self.client.fetch_card(sios_id)
        except SiosHttpError:
            logger.exception("detail_fetch_failed", extra=log_extra(sios_id=sios_id, url=url))
            return None
        if self.settings.save_raw_html:
            write_raw(self.settings.raw_details_dir / f"{sios_id}.html", html)
        try:
            record = parse_detail_page(
                html,
                sios_id=sios_id,
                source_url=url,
                base_url=self.settings.base_url,
            )
        except Exception:
            logger.exception("detail_parse_failed", extra=log_extra(sios_id=sios_id, url=url))
            return None
        if search_hit is not None:
            record.raw_fields["_search"] = {
                "keyword": search_hit.keyword,
                "document_name": search_hit.document_name,
                "document_type": search_hit.document_type,
                "topics": search_hit.topics,
                "subject_snippet": search_hit.subject_snippet,
                "list_date": search_hit.date,
                "case_reference": search_hit.case_reference,
                "location": search_hit.location,
            }
            record.card_number = record.card_number or search_hit.card_number
            record.year = record.year or search_hit.year
            record.document_name = record.document_name or search_hit.document_name
            record.document_type = record.document_type or search_hit.document_type
            record.case_reference = record.case_reference or search_hit.case_reference
            record.location = record.location or search_hit.location
        record.matched_keywords = list(keywords or [])
        return self.storage.upsert_card(record, run_id=run_id)

    def collect_keyword(self, keyword: str, max_pages: Optional[int] = None) -> KeywordRunResult:
        run_id = self.storage.start_run(keyword)
        logger.info("run_start", extra=log_extra(run_id=run_id, keyword=keyword))
        hits, result = self.search(keyword, max_pages=max_pages)
        result.run_id = run_id
        try:
            for hit in hits:
                stored = self.fetch_card(
                    hit.sios_id,
                    keywords=[keyword],
                    search_hit=hit,
                    run_id=run_id,
                )
                if stored is None:
                    result.errors += 1
                    continue
                _count_outcome(result, stored.status)
            result.unique_cards = len(hits)
            status = "ok" if result.errors == 0 else "partial"
            if result.status == "error":
                status = "error"
            result.status = status
            self._persist_run(run_id, result, status=status)
        except Exception as exc:
            result.status = "error"
            result.errors += 1
            logger.exception("collect_keyword_failed", extra=log_extra(keyword=keyword))
            self._persist_run(run_id, result, status="error", error=str(exc))
        logger.info(
            "run_end",
            extra=log_extra(
                run_id=run_id,
                keyword=keyword,
                pages_processed=result.pages_processed,
                unique_cards=result.unique_cards,
                new_cards=result.new_cards,
                changed_cards=result.changed_cards,
                unchanged_cards=result.unchanged_cards,
                existing_cards=result.existing_cards,
                errors=result.errors,
                termination_reason=result.termination_reason,
                stop_reason=result.stop_reason,
                status=result.status,
            ),
        )
        return result

    def collect_card_id(self, sios_id: int) -> KeywordRunResult:
        run_id = self.storage.start_run(keyword=None)
        result = KeywordRunResult(keyword="(card-id)", run_id=run_id)
        stored = self.fetch_card(sios_id, keywords=[], run_id=run_id)
        result.pages_processed = 0
        if stored is None:
            result.errors = 1
            result.status = "error"
            self._persist_run(
                run_id,
                result,
                status="error",
                error=f"failed to fetch card {sios_id}",
            )
        else:
            result.unique_cards = 1
            _count_outcome(result, stored.status)
            result.status = "ok"
            self._persist_run(run_id, result, status="ok")
        return result


def print_summary(result: KeywordRunResult) -> None:
    print(f"Keyword: {result.keyword}")
    print(f"Pages processed: {result.pages_processed}")
    print(f"Unique cards found: {result.unique_cards}")
    print(f"New cards: {result.new_cards}")
    print(f"Changed cards: {result.changed_cards}")
    print(f"Unchanged cards: {result.unchanged_cards}")
    print(f"Existing cards: {result.existing_cards}")
    print(f"Errors: {result.errors}")
    if result.stop_reason:
        print(f"Stop reason: {result.stop_reason}")
    if result.reported_total is not None:
        print(f"SIOS reported total: {result.reported_total}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect public SIOS card metadata.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--keyword", help="Run one public search keyword.")
    source.add_argument(
        "--all-keywords",
        action="store_true",
        help="Run every keyword from config/keywords.yaml.",
    )
    source.add_argument("--card-id", type=int, help="Fetch a single public card by numeric SIOS ID.")
    parser.add_argument("--max-pages", type=int, default=None, help="Safety cap on search pages.")
    parser.add_argument("--config", type=Path, default=None, help="Path to collector.yaml.")
    parser.add_argument("--keywords-file", type=Path, default=None, help="Path to keywords.yaml.")
    parser.add_argument("--delay", type=float, default=None, help="Seconds between HTTP requests.")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Do not store raw HTML (overrides config).",
    )
    return parser


def combine_keyword_runs(parts: list[KeywordRunResult], unique_cards: int) -> KeywordRunResult:
    """Sum run counters. unique_cards is the distinct total, not a sum of parts."""
    totals = KeywordRunResult(keyword="(all)")
    for part in parts:
        totals.pages_processed += part.pages_processed
        totals.new_cards += part.new_cards
        totals.changed_cards += part.changed_cards
        totals.unchanged_cards += part.unchanged_cards
        totals.existing_cards += part.existing_cards
        totals.errors += part.errors
        if part.status != "ok":
            totals.status = "partial"
    totals.unique_cards = unique_cards
    return totals


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)
    settings = load_settings(args.config)
    if args.delay is not None:
        settings.request_delay_seconds = args.delay
    if args.no_raw:
        settings.save_raw_html = False
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    storage = Storage(settings.sqlite_path)
    client = SiosClient(
        base_url=settings.base_url,
        user_agent=settings.user_agent,
        timeout_seconds=settings.timeout_seconds,
        request_delay_seconds=settings.request_delay_seconds,
        max_retries=settings.max_retries,
        iid=settings.iid,
        results_per_page=settings.results_per_page,
    )
    collector = Collector(settings, storage, client)
    try:
        if args.card_id is not None:
            result = collector.collect_card_id(args.card_id)
            print_summary(result)
            return 1 if result.status == "error" else 0
        if args.keyword:
            result = collector.collect_keyword(args.keyword, max_pages=args.max_pages)
            print_summary(result)
            return 1 if result.status == "error" else 0
        keywords = flatten_keywords(load_keyword_groups(args.keywords_file))
        parts = []
        for keyword in keywords:
            part = collector.collect_keyword(keyword, max_pages=args.max_pages)
            print_summary(part)
            print("---")
            parts.append(part)
        run_ids = [part.run_id for part in parts if part.run_id is not None]
        totals = combine_keyword_runs(parts, storage.count_distinct_cards(run_ids))
        print("Combined")
        print_summary(totals)
        return 0 if totals.errors == 0 else 1
    finally:
        client.close()
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
