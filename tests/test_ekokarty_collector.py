from __future__ import annotations

from datetime import date
from pathlib import Path

from src.ekokarty.collector import (
    STOP_EMPTY_WINDOW,
    STOP_RESULT_CAP,
    STOP_WINDOW_COMPLETE,
    EkokartyCollector,
    main,
)
from src.ekokarty.config import EkokartyInstitution, EkokartySettings
from src.sios.collector import NoWatermarkError
from src.sios.models import SOURCE_SYSTEM_EKOKARTY
from src.sios.storage import Storage

FIXTURES = Path(__file__).parent / "fixtures"


def settings_for(tmp_path: Path, result_cap: int = 2000) -> EkokartySettings:
    return EkokartySettings(
        base_url="https://ekokarty.pl",
        user_agent="test",
        timeout_seconds=5,
        request_delay_seconds=0,
        max_retries=0,
        save_raw_html=False,
        sqlite_path=tmp_path / "sios.sqlite",
        raw_search_dir=tmp_path / "search",
        raw_details_dir=tmp_path / "details",
        result_cap=result_cap,
        max_requests=20,
        default_since=date(2010, 1, 1),
        project_root=tmp_path,
    )


INSTITUTION = EkokartyInstitution(
    key="rdos-warszawa",
    name="Regionalna Dyrekcja Ochrony Środowiska w Warszawie",
    slug="rdos-warszawa",
    enabled=True,
)


class FakeEkokartyClient:
    def __init__(self) -> None:
        self.listings = {
            (date(2026, 1, 1), date(2026, 1, 31)): (
                FIXTURES / "ekokarty_listing_two_rows.html"
            ).read_text(encoding="utf-8"),
            (date(2026, 1, 1), date(2026, 1, 15)): (
                FIXTURES / "ekokarty_listing_jan1.html"
            ).read_text(encoding="utf-8"),
            (date(2026, 1, 16), date(2026, 1, 31)): (
                FIXTURES / "ekokarty_listing_jan16.html"
            ).read_text(encoding="utf-8"),
            (date(2026, 1, 1), date(2026, 1, 1)): (
                FIXTURES / "ekokarty_listing_two_rows.html"
            ).read_text(encoding="utf-8"),
            (date(2026, 2, 1), date(2026, 2, 28)): (
                FIXTURES / "ekokarty_listing_empty.html"
            ).read_text(encoding="utf-8"),
        }
        self.details = {
            "/wykaz/rdos-warszawa/77888/11843/X": (
                FIXTURES / "ekokarty_detail_77888.html"
            ).read_text(encoding="utf-8"),
            "/wykaz/rdos-warszawa/77887/11843/X": (
                FIXTURES / "ekokarty_detail_77887.html"
            ).read_text(encoding="utf-8"),
        }
        self.search_calls: list[tuple[date, date]] = []
        self.detail_calls: list[str] = []

    def search(self, slug, keyword, date_from=None, date_to=None):
        self.search_calls.append((date_from, date_to))
        if (date_from, date_to) in self.listings:
            return self.listings[(date_from, date_to)]
        return (FIXTURES / "ekokarty_listing_empty.html").read_text(encoding="utf-8")

    def fetch_card(self, path: str) -> str:
        self.detail_calls.append(path)
        if path.startswith("http"):
            path = "/" + path.split("/", 3)[-1]
        return self.details[path]

    def card_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return "https://ekokarty.pl{}".format(path)

    def close(self) -> None:
        return None


def collector_for(tmp_path: Path, result_cap: int = 2) -> tuple[EkokartyCollector, FakeEkokartyClient, Storage]:
    storage = Storage(tmp_path / "sios.sqlite")
    client = FakeEkokartyClient()
    collector = EkokartyCollector(
        settings_for(tmp_path, result_cap=result_cap),
        storage,
        client,
        INSTITUTION,
    )
    return collector, client, storage


def test_capped_month_is_split_and_not_treated_as_complete(tmp_path: Path) -> None:
    collector, client, storage = collector_for(tmp_path, result_cap=2)
    result = collector.collect_keyword_window(
        "Castor fiber",
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
    )
    assert result.window_splits == 1
    assert result.stop_reason == STOP_WINDOW_COMPLETE
    assert result.status == "ok"
    assert result.unique_cards == 2
    assert result.new_cards == 2
    assert client.search_calls[0] == (date(2026, 1, 1), date(2026, 1, 31))
    assert (date(2026, 1, 1), date(2026, 1, 15)) in client.search_calls
    assert (date(2026, 1, 16), date(2026, 1, 31)) in client.search_calls
    stored = storage.get_record(SOURCE_SYSTEM_EKOKARTY, "rdos-warszawa:77888")
    assert stored["canonical_key"] == "ekokarty:rdos-warszawa:77888"
    assert stored["listing_date"] == "2026-01-20"
    assert stored["source_keys"] == ["rdos-warszawa"]
    assert (
        storage.last_successful_window_end("Castor fiber", "rdos-warszawa")
        == "2026-01-31"
    )


def test_unsplittable_cap_is_logged_as_incomplete(tmp_path: Path) -> None:
    collector, client, storage = collector_for(tmp_path, result_cap=2)
    result = collector.collect_keyword_window(
        "Castor fiber",
        since=date(2026, 1, 1),
        until=date(2026, 1, 1),
    )
    assert result.stop_reason == STOP_RESULT_CAP
    assert result.status == "partial"
    assert result.capped_windows == 1
    assert result.window_splits == 0
    assert result.unique_cards == 2
    assert storage.last_successful_window_end("Castor fiber", "rdos-warszawa") is None
    assert client.search_calls == [(date(2026, 1, 1), date(2026, 1, 1))]


def test_empty_window_is_complete(tmp_path: Path) -> None:
    collector, _client, storage = collector_for(tmp_path, result_cap=2)
    result = collector.collect_keyword_window(
        "bobry",
        since=date(2026, 2, 1),
        until=date(2026, 2, 28),
    )
    assert result.stop_reason == STOP_EMPTY_WINDOW
    assert result.status == "ok"
    assert result.unique_cards == 0
    assert (
        storage.last_successful_window_end("bobry", "rdos-warszawa") == "2026-02-28"
    )


def test_known_cards_skip_detail_and_update_last_seen(tmp_path: Path) -> None:
    collector, client, storage = collector_for(tmp_path, result_cap=2)
    first = collector.collect_keyword_window(
        "Castor fiber",
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
    )
    assert first.detail_pages_fetched == 2
    first_seen = storage.get_record(SOURCE_SYSTEM_EKOKARTY, "rdos-warszawa:77888")[
        "first_seen_at"
    ]
    client.detail_calls.clear()
    second = collector.collect_keyword_window(
        "Castor fiber",
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
    )
    assert second.known_cards_skipped == 2
    assert second.detail_pages_fetched == 0
    assert client.detail_calls == []
    stored = storage.get_record(SOURCE_SYSTEM_EKOKARTY, "rdos-warszawa:77888")
    assert stored["first_seen_at"] == first_seen
    assert stored["last_seen_at"] >= first_seen


def test_incremental_uses_listing_date_watermark(tmp_path: Path) -> None:
    collector, client, _storage = collector_for(tmp_path, result_cap=2)
    collector.collect_keyword_window(
        "Castor fiber",
        since=date(2026, 1, 1),
        until=date(2026, 1, 31),
    )
    client.search_calls.clear()
    result = collector.collect_keyword_incremental(
        "Castor fiber", until=date(2026, 2, 28)
    )
    assert result.window_mode == "AUTOMATIC"
    assert result.watermark_used == "2026-01-31"
    assert result.overlap_days == 1
    assert result.window_start == "2026-01-30"
    assert result.window_end == "2026-02-28"


def test_incremental_requires_complete_baseline(tmp_path: Path) -> None:
    collector, _client, _storage = collector_for(tmp_path, result_cap=2)
    try:
        collector.collect_keyword_incremental("Castor fiber")
        raised = False
    except NoWatermarkError:
        raised = True
    assert raised is True


def test_cli_rejects_keyword_without_since(capsys) -> None:
    try:
        main(["--keyword", "bóbr"])
        raised = None
    except SystemExit as exc:
        raised = exc.code
    assert raised == 2
    err = capsys.readouterr().err
    assert "--since" in err or "incremental" in err
