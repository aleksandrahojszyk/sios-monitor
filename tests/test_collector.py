from __future__ import annotations

from pathlib import Path

from src.sios.collector import Collector
from src.sios.config import CollectorSettings
from src.sios.storage import Storage

FIXTURES = Path(__file__).parent / "fixtures"


class FakeClient:
    def __init__(self) -> None:
        self.search_pages = {
            1: (FIXTURES / "search_page_1.html").read_text(encoding="utf-8"),
            2: (FIXTURES / "search_page_2.html").read_text(encoding="utf-8"),
        }
        self.details = {
            449913: (FIXTURES / "detail_449913.html").read_text(encoding="utf-8"),
            449844: (FIXTURES / "detail_minimal.html").read_text(encoding="utf-8"),
            434045: (FIXTURES / "detail_minimal.html").read_text(encoding="utf-8"),
            449168: (FIXTURES / "detail_minimal.html").read_text(encoding="utf-8"),
            449160: (FIXTURES / "detail_minimal.html").read_text(encoding="utf-8"),
        }
        self.search_calls: list[int] = []

    def search(self, keyword: str, page: int, results: int | None = None) -> str:
        self.search_calls.append(page)
        if page >= 3:
            return self.search_pages[2]
        return self.search_pages[page]

    def fetch_card(self, sios_id: int) -> str:
        return self.details[sios_id]

    def card_url(self, sios_id: int) -> str:
        return f"https://system.sios.pl/documents/details/id/{sios_id}"


def make_collector(tmp_path: Path) -> tuple[Collector, Storage, FakeClient]:
    storage = Storage(tmp_path / "sios.sqlite")
    settings = CollectorSettings(
        base_url="https://system.sios.pl",
        user_agent="test",
        timeout_seconds=5,
        request_delay_seconds=0,
        max_retries=0,
        results_per_page=30,
        iid=0,
        save_raw_html=True,
        sqlite_path=tmp_path / "sios.sqlite",
        raw_search_dir=tmp_path / "raw" / "search",
        raw_details_dir=tmp_path / "raw" / "details",
        max_pages=50,
        project_root=tmp_path,
    )
    client = FakeClient()
    return Collector(settings, storage, client), storage, client  # type: ignore[arg-type]


def test_repeated_final_page_does_not_loop(tmp_path: Path) -> None:
    collector, storage, client = make_collector(tmp_path)
    hits, result = collector.search("bóbr")
    assert result.termination_reason == "repeated_page"
    assert client.search_calls == [1, 2, 3]
    assert [hit.sios_id for hit in hits] == [449913, 449844, 434045, 449168, 449160]


def test_max_pages_safety_limit(tmp_path: Path) -> None:
    collector, _, client = make_collector(tmp_path)
    _, result = collector.search("bóbr", max_pages=1)
    assert result.termination_reason == "max_pages"
    assert result.pages_processed == 1
    assert client.search_calls == [1]


def test_collect_keyword_and_rerun_does_not_duplicate(tmp_path: Path) -> None:
    collector, storage, _ = make_collector(tmp_path)
    first = collector.collect_keyword("bóbr", max_pages=1)
    assert first.new_cards == 3
    assert first.existing_cards == 0
    assert storage.card_count() == 3
    second = collector.collect_keyword("bóbr", max_pages=1)
    assert second.new_cards == 0
    assert second.existing_cards == 3
    assert storage.card_count() == 3
    third = collector.collect_keyword("Castor fiber", max_pages=1)
    assert third.new_cards == 0
    assert storage.keywords_for(449913) == ["Castor fiber", "bóbr"]
    raw_search = list((tmp_path / "raw" / "search").glob("*.html"))
    assert raw_search
