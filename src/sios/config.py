from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COLLECTOR_CONFIG = PROJECT_ROOT / "config" / "collector.yaml"
DEFAULT_KEYWORDS_CONFIG = PROJECT_ROOT / "config" / "keywords.yaml"


@dataclass
class CollectorSettings:
    base_url: str
    user_agent: str
    timeout_seconds: float
    request_delay_seconds: float
    max_retries: int
    results_per_page: int
    iid: int
    save_raw_html: bool
    sqlite_path: Path
    raw_search_dir: Path
    raw_details_dir: Path
    max_pages: int
    project_root: Path

    @classmethod
    def from_mapping(cls, data: dict[str, Any], project_root: Path) -> "CollectorSettings":
        def resolve(path_value: str) -> Path:
            path = Path(path_value)
            if not path.is_absolute():
                path = project_root / path
            return path

        return cls(
            base_url=str(data.get("base_url", "https://system.sios.pl")).rstrip("/"),
            user_agent=str(
                data.get(
                    "user_agent",
                    "sios-monitor/0.1 (public SIOS metadata collector; conservative pacing)",
                )
            ),
            timeout_seconds=float(data.get("timeout_seconds", 30)),
            request_delay_seconds=float(data.get("request_delay_seconds", 1.5)),
            max_retries=int(data.get("max_retries", 4)),
            results_per_page=int(data.get("results_per_page", 30)),
            iid=int(data.get("iid", 0)),
            save_raw_html=bool(data.get("save_raw_html", True)),
            sqlite_path=resolve(str(data.get("sqlite_path", "data/normalized/sios.sqlite"))),
            raw_search_dir=resolve(str(data.get("raw_search_dir", "data/raw/search"))),
            raw_details_dir=resolve(str(data.get("raw_details_dir", "data/raw/details"))),
            max_pages=int(data.get("max_pages", 1000)),
            project_root=project_root,
        )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data


def load_settings(path: Path | None = None) -> CollectorSettings:
    config_path = path or DEFAULT_COLLECTOR_CONFIG
    return CollectorSettings.from_mapping(load_yaml(config_path), PROJECT_ROOT)


def load_keyword_groups(path: Path | None = None) -> dict[str, list[str]]:
    config_path = path or DEFAULT_KEYWORDS_CONFIG
    raw = load_yaml(config_path)
    groups: dict[str, list[str]] = {}
    for group, values in raw.items():
        if not isinstance(values, list):
            continue
        keywords = [str(item).strip() for item in values if str(item).strip()]
        if keywords:
            groups[str(group)] = keywords
    return groups


def flatten_keywords(groups: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for values in groups.values():
        for keyword in values:
            if keyword not in seen:
                seen.add(keyword)
                ordered.append(keyword)
    return ordered


def iter_keywords(groups: dict[str, list[str]]) -> Iterable[str]:
    yield from flatten_keywords(groups)
