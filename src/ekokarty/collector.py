from __future__ import annotations

import argparse
import logging
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from src.sios.client import SiosHttpError
from src.sios.collector import NoWatermarkError, parse_cli_date, write_raw
from src.sios.logging_utils import configure_logging, log_extra
from src.sios.models import SOURCE_SYSTEM_EKOKARTY, CardRecord
from src.sios.storage import STATUS_CHANGED, STATUS_NEW, STATUS_UNCHANGED, Storage, UpsertResult

from .client import EkokartyClient
from .config import (
    EkokartyInstitution,
    EkokartySettings,
    flatten_keywords,
    load_ekokarty_keywords,
    load_institutions,
    load_settings,
)
from .detail_parser import parse_detail_page
from .listing_parser import parse_listing_page
from .models import DateWindow, KeywordRunResult, ListingHit
from .windows import WindowSplitError, can_split, split_window

logger = logging.getLogger(__name__)

STOP_WINDOW_COMPLETE = "WINDOW_COMPLETE"
STOP_EMPTY_WINDOW = "EMPTY_WINDOW"
STOP_RESULT_CAP = "RESULT_CAP"
STOP_HTTP_ERROR = "HTTP_ERROR"
STOP_MAX_REQUESTS = "MAX_REQUESTS"
STOP_PARTIAL_DETAIL_FAILURE = "PARTIAL_DETAIL_FAILURE"
STOP_COMPLETED = "COMPLETED"
WINDOW_MODE_EXPLICIT = "EXPLICIT"
WINDOW_MODE_AUTOMATIC = "AUTOMATIC"


def _count_outcome(result: KeywordRunResult, status: str) -> None:
    if status == STATUS_NEW:
        result.new_cards += 1
    elif status == STATUS_CHANGED:
        result.changed_cards += 1
        result.existing_cards += 1
    elif status == STATUS_UNCHANGED:
        result.unchanged_cards += 1
        result.existing_cards += 1


def keyword_slug(keyword: str) -> str:
    normalized = unicodedata.normalize("NFKD", keyword)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_text).strip("_").lower()
    return slug or "keyword"


class EkokartyCollector:
    def __init__(
        self,
        settings: EkokartySettings,
        storage: Storage,
        client: EkokartyClient,
        institution: EkokartyInstitution,
    ) -> None:
        self.settings = settings
        self.storage = storage
        self.client = client
        self.institution = institution

    @property
    def source_key(self) -> str:
        return self.institution.key

    def _persist_run(
        self,
        run_id: int,
        result: KeywordRunResult,
        status: str,
        error: Optional[str] = None,
    ) -> None:
        self.storage.finish_run(
            run_id,
            pages_processed=result.pages_processed,
            cards_found=result.unique_cards,
            new_cards=result.new_cards,
            changed_cards=result.changed_cards,
            unchanged_cards=result.unchanged_cards,
            existing_cards=result.existing_cards,
            error_count=result.errors,
            stop_reason=result.stop_reason,
            cards_encountered=result.cards_encountered,
            cards_in_window=result.cards_in_window,
            known_cards_skipped=result.known_cards_skipped,
            detail_pages_fetched=result.detail_pages_fetched,
            window_splits=result.window_splits,
            status=status,
            error=error,
        )

    def fetch_card_record(self, hit: ListingHit) -> Optional[CardRecord]:
        url = hit.detail_url
        try:
            html = self.client.fetch_card(hit.detail_path)
        except SiosHttpError:
            logger.exception(
                "ekokarty_detail_fetch_failed",
                extra=log_extra(canonical_key=hit.canonical_key, url=url),
            )
            return None
        if self.settings.save_raw_html:
            filename = "{}_{}.html".format(hit.slug, hit.card_id)
            write_raw(self.settings.raw_details_dir / filename, html)
        try:
            return parse_detail_page(
                html,
                slug=hit.slug,
                card_id=hit.card_id,
                source_url=url,
                base_url=self.settings.base_url,
                authority=self.institution.name,
                listing_hit=hit,
            )
        except Exception:
            logger.exception(
                "ekokarty_detail_parse_failed",
                extra=log_extra(canonical_key=hit.canonical_key, url=url),
            )
            return None

    def _store_hit(
        self,
        hit: ListingHit,
        keyword: str,
        run_id: int,
        result: KeywordRunResult,
    ) -> None:
        if hit.canonical_key in result.seen_keys:
            return
        result.seen_keys.add(hit.canonical_key)
        result.cards_in_window += 1
        existing = self.storage.get_record(SOURCE_SYSTEM_EKOKARTY, hit.native_record_id)
        if existing is not None:
            result.known_cards_skipped += 1
            result.existing_cards += 1
            self.storage.mark_record_seen(
                SOURCE_SYSTEM_EKOKARTY,
                hit.native_record_id,
                keyword=keyword,
                source_key=self.source_key,
            )
            return
        record = self.fetch_card_record(hit)
        result.detail_pages_fetched += 1
        if record is None:
            result.errors += 1
            return
        record.matched_keywords = [keyword]
        stored: UpsertResult = self.storage.upsert_card(
            record,
            run_id=run_id,
            source_key=self.source_key,
        )
        _count_outcome(result, stored.status)

    def _collect_window(
        self,
        keyword: str,
        window: DateWindow,
        result: KeywordRunResult,
        run_id: int,
        max_requests: int,
    ) -> None:
        if result.status == "error":
            return
        if result.pages_processed >= max_requests:
            result.stop_reason = STOP_MAX_REQUESTS
            result.status = "partial"
            logger.error(
                "ekokarty_max_requests",
                extra=log_extra(
                    keyword=keyword,
                    institution=self.institution.slug,
                    date_from=window.iso_start(),
                    date_to=window.iso_end(),
                    max_requests=max_requests,
                    complete=False,
                ),
            )
            return

        try:
            html = self.client.search(
                self.institution.slug,
                keyword,
                date_from=window.start,
                date_to=window.end,
            )
        except SiosHttpError as exc:
            result.errors += 1
            result.status = "error"
            result.stop_reason = STOP_HTTP_ERROR
            logger.exception(
                "ekokarty_search_failed",
                extra=log_extra(
                    keyword=keyword,
                    institution=self.institution.slug,
                    date_from=window.iso_start(),
                    date_to=window.iso_end(),
                    error=str(exc),
                ),
            )
            return

        result.pages_processed += 1
        if self.settings.save_raw_html:
            filename = "search_{}_{}_{}_{}.html".format(
                self.institution.slug,
                keyword_slug(keyword),
                window.iso_start(),
                window.iso_end(),
            )
            write_raw(self.settings.raw_search_dir / filename, html)

        hits = parse_listing_page(
            html,
            keyword=keyword,
            slug=self.institution.slug,
            base_url=self.settings.base_url,
        )
        result.cards_encountered += len(hits)
        logger.info(
            "ekokarty_window_result",
            extra=log_extra(
                keyword=keyword,
                institution=self.institution.slug,
                date_from=window.iso_start(),
                date_to=window.iso_end(),
                row_count=len(hits),
                result_cap=self.settings.result_cap,
                capped=len(hits) >= self.settings.result_cap,
            ),
        )

        if len(hits) >= self.settings.result_cap:
            if not can_split(window):
                result.capped_windows += 1
                result.stop_reason = STOP_RESULT_CAP
                result.status = "partial"
                logger.error(
                    "ekokarty_result_cap",
                    extra=log_extra(
                        keyword=keyword,
                        institution=self.institution.slug,
                        date_from=window.iso_start(),
                        date_to=window.iso_end(),
                        row_count=len(hits),
                        result_cap=self.settings.result_cap,
                        complete=False,
                    ),
                )
                for hit in hits:
                    self._store_hit(hit, keyword, run_id, result)
                return
            try:
                left, right = split_window(window)
            except WindowSplitError:
                result.capped_windows += 1
                result.stop_reason = STOP_RESULT_CAP
                result.status = "partial"
                for hit in hits:
                    self._store_hit(hit, keyword, run_id, result)
                return
            result.window_splits += 1
            logger.warning(
                "ekokarty_window_split",
                extra=log_extra(
                    keyword=keyword,
                    institution=self.institution.slug,
                    date_from=window.iso_start(),
                    date_to=window.iso_end(),
                    row_count=len(hits),
                    result_cap=self.settings.result_cap,
                    left_from=left.iso_start(),
                    left_to=left.iso_end(),
                    right_from=right.iso_start(),
                    right_to=right.iso_end(),
                    complete=False,
                ),
            )
            self._collect_window(keyword, left, result, run_id, max_requests)
            self._collect_window(keyword, right, result, run_id, max_requests)
            return

        for hit in hits:
            self._store_hit(hit, keyword, run_id, result)

    def collect_keyword_window(
        self,
        keyword: str,
        *,
        since: date,
        until: date,
        max_requests: Optional[int] = None,
        window_mode: str = WINDOW_MODE_EXPLICIT,
        watermark_used: Optional[str] = None,
        overlap_days: int = 0,
    ) -> KeywordRunResult:
        if until < since:
            raise ValueError("until must be on or after since")
        run_id = self.storage.start_run(
            keyword,
            window_start=since.isoformat(),
            window_end=until.isoformat(),
            window_mode=window_mode,
            watermark_used=watermark_used,
            overlap_days=overlap_days,
            source_key=self.source_key,
        )
        result = KeywordRunResult(
            keyword=keyword,
            source_key=self.source_key,
            run_id=run_id,
            window_start=since.isoformat(),
            window_end=until.isoformat(),
            window_mode=window_mode,
            watermark_used=watermark_used,
            overlap_days=overlap_days,
        )
        logger.info(
            "run_start",
            extra=log_extra(
                run_id=run_id,
                keyword=keyword,
                source=self.source_key,
                adapter="ekokarty",
                window_start=result.window_start,
                window_end=result.window_end,
                window_mode=result.window_mode,
                date_basis="listing_date",
            ),
        )
        error_message: Optional[str] = None
        try:
            self._collect_window(
                keyword,
                DateWindow(since, until),
                result,
                run_id,
                max_requests if max_requests is not None else self.settings.max_requests,
            )
            result.unique_cards = len(result.seen_keys)
            if result.status == "error":
                pass
            elif result.capped_windows or result.stop_reason == STOP_RESULT_CAP:
                result.status = "partial"
                result.stop_reason = STOP_RESULT_CAP
            elif result.stop_reason == STOP_MAX_REQUESTS:
                result.status = "partial"
            elif result.errors:
                result.status = "partial"
                result.stop_reason = STOP_PARTIAL_DETAIL_FAILURE
            elif result.unique_cards == 0:
                result.status = "ok"
                result.stop_reason = STOP_EMPTY_WINDOW
            else:
                result.status = "ok"
                result.stop_reason = STOP_WINDOW_COMPLETE
            self._persist_run(run_id, result, status=result.status, error=error_message)
        except Exception as exc:
            result.status = "error"
            result.errors += 1
            error_message = str(exc)
            logger.exception(
                "ekokarty_collect_failed", extra=log_extra(keyword=keyword)
            )
            self._persist_run(run_id, result, status="error", error=error_message)

        logger.info(
            "run_end",
            extra=log_extra(
                run_id=run_id,
                keyword=keyword,
                source=self.source_key,
                unique_cards=result.unique_cards,
                new_cards=result.new_cards,
                window_splits=result.window_splits,
                capped_windows=result.capped_windows,
                stop_reason=result.stop_reason,
                status=result.status,
                complete=result.status == "ok",
            ),
        )
        return result

    def collect_keyword_incremental(
        self,
        keyword: str,
        *,
        until: Optional[date] = None,
        max_requests: Optional[int] = None,
    ) -> KeywordRunResult:
        watermark = self.storage.last_successful_window_end(
            keyword, source_key=self.source_key
        )
        if watermark is None:
            raise NoWatermarkError(
                "No successful bounded EkoKarty run exists for keyword {!r} "
                "and institution {!r}; provide --since".format(
                    keyword, self.source_key
                )
            )
        try:
            watermark_date = date.fromisoformat(watermark)
        except ValueError:
            raise NoWatermarkError(
                "Stored watermark for {!r} is invalid: {}".format(keyword, watermark)
            )
        return self.collect_keyword_window(
            keyword,
            since=watermark_date - timedelta(days=1),
            until=until or date.today(),
            max_requests=max_requests,
            window_mode=WINDOW_MODE_AUTOMATIC,
            watermark_used=watermark,
            overlap_days=1,
        )

    def collect_card_url(self, url: str) -> KeywordRunResult:
        from .listing_parser import DETAIL_HREF

        match = DETAIL_HREF.search(url)
        if match is None:
            raise ValueError("Not an EkoKarty card URL: {}".format(url))
        slug = match.group("slug")
        if slug != self.institution.slug:
            raise ValueError(
                "Card slug {!r} does not match configured institution {!r}".format(
                    slug, self.institution.slug
                )
            )
        hit = ListingHit(
            card_id=match.group("card_id"),
            slug=slug,
            secondary_id=match.group("secondary_id"),
            card_type=match.group("type"),
            card_number=None,
            year=None,
            document_name=None,
            document_type=None,
            topic=None,
            subject_snippet=None,
            listing_date=None,
            detail_path=url if url.startswith("/") else url,
            detail_url=self.client.card_url(url),
            keyword="(card-url)",
        )
        run_id = self.storage.start_run(keyword=None, source_key=self.source_key)
        result = KeywordRunResult(
            keyword="(card-url)", run_id=run_id, source_key=self.source_key
        )
        record = self.fetch_card_record(hit)
        result.detail_pages_fetched = 1
        if record is None:
            result.errors = 1
            result.status = "error"
            result.stop_reason = STOP_PARTIAL_DETAIL_FAILURE
            self._persist_run(
                run_id, result, status="error", error="failed to fetch {}".format(url)
            )
            return result
        stored = self.storage.upsert_card(
            record, run_id=run_id, source_key=self.source_key
        )
        result.unique_cards = 1
        result.cards_in_window = 1
        _count_outcome(result, stored.status)
        result.status = "ok"
        result.stop_reason = STOP_COMPLETED
        self._persist_run(run_id, result, status="ok")
        return result


def print_summary(result: KeywordRunResult) -> None:
    print("Keyword: {}".format(result.keyword))
    if result.source_key is not None:
        print("Source: {}".format(result.source_key))
    print("Adapter: ekokarty")
    print("Search requests: {}".format(result.pages_processed))
    print("Unique cards found: {}".format(result.unique_cards))
    print("New cards: {}".format(result.new_cards))
    print("Changed cards: {}".format(result.changed_cards))
    print("Unchanged cards: {}".format(result.unchanged_cards))
    print("Existing cards: {}".format(result.existing_cards))
    print("Errors: {}".format(result.errors))
    if result.stop_reason:
        print("Stop reason: {}".format(result.stop_reason))
    if result.window_start is not None:
        print("Window: {} through {}".format(result.window_start, result.window_end))
        print("Window mode: {}".format(result.window_mode))
        print("Date basis: listing_date")
        if result.watermark_used is not None:
            print("Watermark used: {}".format(result.watermark_used))
            print("Overlap days: {}".format(result.overlap_days))
        print("Cards encountered: {}".format(result.cards_encountered))
        print("Cards inside window: {}".format(result.cards_in_window))
        print("Known cards skipped: {}".format(result.known_cards_skipped))
        print("Detail pages fetched: {}".format(result.detail_pages_fetched))
        print("Window splits: {}".format(result.window_splits))
        if result.capped_windows:
            print("Capped unsplittable windows: {}".format(result.capped_windows))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect public EkoKarty card metadata for one institution."
    )
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--keyword", help="Run one public keyword search.")
    operation.add_argument(
        "--all-keywords",
        action="store_true",
        help="Run every keyword from config/ekokarty_keywords.yaml.",
    )
    operation.add_argument(
        "--card-url",
        help="Fetch a single public card by its /wykaz/{slug}/{cardId}/... URL.",
    )
    parser.add_argument(
        "--institution",
        default="rdos-warszawa",
        help="Institution key from config/ekokarty_sources.yaml.",
    )
    parser.add_argument(
        "--sources-file",
        type=Path,
        default=None,
        help="Path to ekokarty_sources.yaml.",
    )
    parser.add_argument(
        "--since",
        type=parse_cli_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="Inclusive listing-date window start (Data zamieszczenie w wykazie).",
    )
    parser.add_argument(
        "--until",
        type=parse_cli_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="Inclusive listing-date window end (defaults to today in bounded modes).",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Derive --since from the last complete bounded run minus one day.",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="Safety cap on listing POST requests, including window splits.",
    )
    parser.add_argument("--config", type=Path, default=None, help="Path to ekokarty.yaml.")
    parser.add_argument(
        "--keywords-file",
        type=Path,
        default=None,
        help="Path to ekokarty_keywords.yaml.",
    )
    parser.add_argument("--delay", type=float, default=None, help="Seconds between HTTP requests.")
    parser.add_argument("--log-level", default="INFO")
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Do not store raw HTML (overrides config).",
    )
    return parser


def combine_keyword_runs(parts: list[KeywordRunResult], unique_cards: int) -> KeywordRunResult:
    totals = KeywordRunResult(keyword="(all)")
    for part in parts:
        totals.pages_processed += part.pages_processed
        totals.new_cards += part.new_cards
        totals.changed_cards += part.changed_cards
        totals.unchanged_cards += part.unchanged_cards
        totals.existing_cards += part.existing_cards
        totals.errors += part.errors
        totals.window_splits += part.window_splits
        totals.capped_windows += part.capped_windows
        if part.status != "ok":
            totals.status = "partial"
        if part.stop_reason == STOP_RESULT_CAP:
            totals.stop_reason = STOP_RESULT_CAP
    totals.unique_cards = unique_cards
    return totals


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.until is not None and args.since is None and not args.incremental:
        parser.error("--until requires --since")
    if args.card_url is None and args.since is None and not args.incremental:
        parser.error("EkoKarty keyword collection requires --since or --incremental")
    if (
        args.since is not None
        and args.until is not None
        and args.until < args.since
    ):
        parser.error("--until must be on or after --since")
    configure_logging(args.log_level)
    settings = load_settings(args.config)
    institutions = load_institutions(args.sources_file)
    institution = institutions.get(args.institution)
    if institution is None:
        parser.error("Unknown EkoKarty institution: {}".format(args.institution))
    if not institution.enabled:
        parser.error("EkoKarty institution is disabled: {}".format(args.institution))
    if args.delay is not None:
        settings.request_delay_seconds = args.delay
    if args.no_raw:
        settings.save_raw_html = False
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    storage = Storage(settings.sqlite_path)
    client = EkokartyClient(
        base_url=settings.base_url,
        user_agent=settings.user_agent,
        timeout_seconds=settings.timeout_seconds,
        request_delay_seconds=settings.request_delay_seconds,
        max_retries=settings.max_retries,
    )
    collector = EkokartyCollector(settings, storage, client, institution)
    try:
        if args.card_url is not None:
            result = collector.collect_card_url(args.card_url)
            print_summary(result)
            return 1 if result.status == "error" else 0
        if args.keyword:
            if args.since is not None:
                result = collector.collect_keyword_window(
                    args.keyword,
                    since=args.since,
                    until=args.until or date.today(),
                    max_requests=args.max_requests,
                )
            else:
                try:
                    result = collector.collect_keyword_incremental(
                        args.keyword,
                        until=args.until,
                        max_requests=args.max_requests,
                    )
                except NoWatermarkError as exc:
                    logger.error(
                        "incremental_watermark_missing",
                        extra=log_extra(keyword=args.keyword, error=str(exc)),
                    )
                    return 2
            print_summary(result)
            if result.stop_reason == STOP_RESULT_CAP:
                return 1
            return 1 if result.status == "error" else 0
        keywords = flatten_keywords(load_ekokarty_keywords(args.keywords_file))
        parts = []
        for keyword in keywords:
            if args.since is not None:
                part = collector.collect_keyword_window(
                    keyword,
                    since=args.since,
                    until=args.until or date.today(),
                    max_requests=args.max_requests,
                )
            else:
                try:
                    part = collector.collect_keyword_incremental(
                        keyword,
                        until=args.until,
                        max_requests=args.max_requests,
                    )
                except NoWatermarkError as exc:
                    logger.error(
                        "incremental_watermark_missing",
                        extra=log_extra(keyword=keyword, error=str(exc)),
                    )
                    return 2
            print_summary(part)
            print("---")
            parts.append(part)
        run_ids = [part.run_id for part in parts if part.run_id is not None]
        totals = combine_keyword_runs(parts, storage.count_distinct_cards(run_ids))
        print("Combined")
        print_summary(totals)
        if totals.stop_reason == STOP_RESULT_CAP or totals.errors:
            return 1
        return 0
    finally:
        client.close()
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
