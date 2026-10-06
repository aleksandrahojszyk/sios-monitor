from __future__ import annotations

from pathlib import Path

from src.sios.client import SiosHttpError
from src.sios.collector import (
    STOP_EMPTY_PAGE,
    STOP_HTTP_ERROR,
    STOP_MAX_PAGES,
    STOP_NO_NEW_IDS,
    STOP_PARTIAL_DETAIL_FAILURE,
    STOP_REPEATED_PAGE,
    Collector,
    combine_keyword_runs,
    main,
    print_summary,
)
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

    def close(self) -> None:
        return None


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
    assert first.changed_cards == 0
    assert first.unchanged_cards == 0
    assert first.existing_cards == 0
    assert storage.card_count() == 3
    second = collector.collect_keyword("bóbr", max_pages=1)
    assert second.new_cards == 0
    assert second.changed_cards == 0
    assert second.unchanged_cards == 3
    assert second.existing_cards == 3
    assert storage.card_count() == 3
    third = collector.collect_keyword("Castor fiber", max_pages=1)
    assert third.new_cards == 0
    assert third.changed_cards == 0
    assert third.unchanged_cards == 3
    assert storage.keywords_for(449913) == ["Castor fiber", "bóbr"]
    observations = storage.observations_for(449913)
    assert [item["status"] for item in observations] == ["NEW", "UNCHANGED", "UNCHANGED"]
    assert observations[0]["changed_fields"] is None
    assert observations[1]["changed_fields"] is None
    runs = storage.conn.execute(
        """
        SELECT new_cards, changed_cards, unchanged_cards
        FROM collection_runs
        ORDER BY run_id
        """
    ).fetchall()
    assert [tuple(row) for row in runs] == [(3, 0, 0), (0, 0, 3), (0, 0, 3)]
    raw_search = list((tmp_path / "raw" / "search").glob("*.html"))
    assert raw_search


def _latest_run(storage: Storage):
    return storage.conn.execute(
        "SELECT * FROM collection_runs ORDER BY run_id DESC LIMIT 1"
    ).fetchone()


def test_max_pages_is_stored_on_the_run(tmp_path: Path) -> None:
    collector, storage, _ = make_collector(tmp_path)
    result = collector.collect_keyword("bóbr", max_pages=1)
    assert result.stop_reason == STOP_MAX_PAGES
    row = _latest_run(storage)
    assert row["stop_reason"] == STOP_MAX_PAGES
    assert row["reported_total"] == 3
    assert row["existing_cards"] == 0
    assert row["error_count"] == 0
    assert row["new_cards"] == 3


def test_repeated_page_stop_is_stored(tmp_path: Path) -> None:
    collector, storage, _ = make_collector(tmp_path)
    result = collector.collect_keyword("bóbr")
    assert result.termination_reason == "repeated_page"
    assert result.stop_reason == STOP_REPEATED_PAGE
    assert _latest_run(storage)["stop_reason"] == STOP_REPEATED_PAGE


def test_empty_page_stop_is_stored(tmp_path: Path) -> None:
    collector, storage, client = make_collector(tmp_path)

    def search(keyword: str, page: int, results: int | None = None) -> str:
        client.search_calls.append(page)
        return (FIXTURES / "search_empty.html").read_text(encoding="utf-8")

    client.search = search  # type: ignore[assignment]
    result = collector.collect_keyword("bóbr")
    assert result.termination_reason == "empty_page"
    assert result.stop_reason == STOP_EMPTY_PAGE
    row = _latest_run(storage)
    assert row["stop_reason"] == STOP_EMPTY_PAGE
    assert row["reported_total"] is None
    assert row["cards_found"] == 0
    assert row["error_count"] == 0


def test_no_new_ids_stop_is_stored(tmp_path: Path) -> None:
    collector, storage, client = make_collector(tmp_path)
    single_id_page = """
    <html><body>
    <table>
      <tr><th>Nr karty</th><th>t</th><th>n</th><th>d</th><th>l</th></tr>
      <tr>
        <td><a href="documents/details/id/449913" class="fancybox">2047/2026</a></td>
        <td>decyzje</td><td>Decyzja</td><td></td><td>warmińsko-mazurskie</td>
      </tr>
    </table>
    </body></html>
    """

    def search(keyword: str, page: int, results: int | None = None) -> str:
        client.search_calls.append(page)
        if page == 1:
            return client.search_pages[1]
        return single_id_page

    client.search = search  # type: ignore[assignment]
    result = collector.collect_keyword("bóbr")
    assert result.termination_reason == "no_new_ids"
    assert result.stop_reason == STOP_NO_NEW_IDS
    assert _latest_run(storage)["stop_reason"] == STOP_NO_NEW_IDS
    assert result.unique_cards == 3


def test_http_error_is_stored_on_the_run(tmp_path: Path) -> None:
    collector, storage, client = make_collector(tmp_path)

    def search(keyword: str, page: int, results: int | None = None) -> str:
        raise SiosHttpError("HTTP 503", url="https://system.sios.pl/search/common", status_code=503)

    client.search = search  # type: ignore[assignment]
    result = collector.collect_keyword("bóbr")
    assert result.status == "error"
    assert result.stop_reason == STOP_HTTP_ERROR
    row = _latest_run(storage)
    assert row["stop_reason"] == STOP_HTTP_ERROR
    assert row["status"] == "error"
    assert row["error_count"] == 1
    assert row["reported_total"] is None


def test_combined_summary_uses_distinct_cards_not_a_sum(tmp_path: Path, capsys) -> None:
    collector, storage, _ = make_collector(tmp_path)
    first = collector.collect_keyword("bóbr", max_pages=1)
    second = collector.collect_keyword("bobry", max_pages=1)
    assert first.unique_cards == 3
    assert second.unique_cards == 3
    combined = combine_keyword_runs(
        [first, second],
        storage.count_distinct_cards([first.run_id, second.run_id]),
    )
    assert combined.unique_cards == 3
    print_summary(combined)
    combined_out = capsys.readouterr().out
    assert "Unique cards found: 3" in combined_out
    assert "Unique cards found: 6" not in combined_out


def _write_config(tmp_path: Path) -> Path:
    config = tmp_path / "collector.yaml"
    config.write_text(
        "\n".join(
            [
                'base_url: "https://system.sios.pl"',
                'user_agent: "test"',
                "timeout_seconds: 5",
                "request_delay_seconds: 0",
                "max_retries: 0",
                "results_per_page: 30",
                "iid: 0",
                "save_raw_html: false",
                'sqlite_path: "{}"'.format(tmp_path / "sios.sqlite"),
                'raw_search_dir: "{}"'.format(tmp_path / "search"),
                'raw_details_dir: "{}"'.format(tmp_path / "details"),
                "max_pages: 2",
            ]
        ),
        encoding="utf-8",
    )
    return config


def test_keyword_cli_error_returns_nonzero(tmp_path: Path, monkeypatch) -> None:
    class FailingClient:
        def __init__(self, **kwargs) -> None:
            pass

        def search(self, keyword: str, page: int, results: int | None = None) -> str:
            raise SiosHttpError("HTTP 503", url="https://system.sios.pl/search/common", status_code=503)

        def close(self) -> None:
            return None

    monkeypatch.setattr("src.sios.collector.SiosClient", FailingClient)
    config = _write_config(tmp_path)
    assert main(["--keyword", "bóbr", "--config", str(config), "--log-level", "ERROR"]) == 1


def test_card_id_cli_failure_returns_nonzero(tmp_path: Path, monkeypatch) -> None:
    class FailingClient:
        def __init__(self, **kwargs) -> None:
            pass

        def fetch_card(self, sios_id: int) -> str:
            raise SiosHttpError("HTTP 404", url="https://system.sios.pl/documents/details/id/1", status_code=404)

        def card_url(self, sios_id: int) -> str:
            return "https://system.sios.pl/documents/details/id/{}".format(sios_id)

        def close(self) -> None:
            return None

    monkeypatch.setattr("src.sios.collector.SiosClient", FailingClient)
    config = _write_config(tmp_path)
    assert main(["--card-id", "1", "--config", str(config), "--log-level", "ERROR"]) == 1
    row = Storage(tmp_path / "sios.sqlite").conn.execute(
        "SELECT status, stop_reason, error_count FROM collection_runs"
    ).fetchone()
    assert row["status"] == "error"
    assert row["stop_reason"] == STOP_PARTIAL_DETAIL_FAILURE
    assert row["error_count"] == 1


def test_keyword_cli_success_returns_zero(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("src.sios.collector.SiosClient", lambda **kwargs: FakeClient())
    config = _write_config(tmp_path)
    assert main(["--keyword", "bóbr", "--config", str(config), "--max-pages", "1", "--log-level", "ERROR"]) == 0


def test_all_keywords_summary_is_distinct_and_failure_stays_nonzero(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    keywords = tmp_path / "keywords.yaml"
    keywords.write_text('species:\n  - "bóbr"\n  - "bobry"\n', encoding="utf-8")
    monkeypatch.setattr("src.sios.collector.SiosClient", lambda **kwargs: FakeClient())
    config = _write_config(tmp_path)
    code = main(
        [
            "--all-keywords",
            "--keywords-file",
            str(keywords),
            "--config",
            str(config),
            "--max-pages",
            "1",
            "--log-level",
            "ERROR",
        ]
    )
    assert code == 0
    combined = capsys.readouterr().out.split("Combined", 1)[1]
    assert "Unique cards found: 3" in combined
    assert "Unique cards found: 6" not in combined

    class FailingClient:
        def __init__(self, **kwargs) -> None:
            pass

        def search(self, keyword: str, page: int, results: int | None = None) -> str:
            raise SiosHttpError("HTTP 503", url="https://system.sios.pl/search/common", status_code=503)

        def close(self) -> None:
            return None

    (tmp_path / "failed").mkdir()
    failed_config = _write_config(tmp_path / "failed")
    monkeypatch.setattr("src.sios.collector.SiosClient", FailingClient)
    assert (
        main(
            [
                "--all-keywords",
                "--keywords-file",
                str(keywords),
                "--config",
                str(failed_config),
                "--log-level",
                "ERROR",
            ]
        )
        == 1
    )
