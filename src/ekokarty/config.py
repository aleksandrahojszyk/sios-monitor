from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from src.sios.config import flatten_keywords, load_keyword_groups, load_yaml

# Re-export for the EkoKarty CLI.
__all__ = [
    "EkokartyInstitution",
    "EkokartySettings",
    "flatten_keywords",
    "iter_keywords",
    "load_ekokarty_keywords",
    "load_institutions",
    "load_settings",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EKOKARTY_CONFIG = PROJECT_ROOT / "config" / "ekokarty.yaml"
DEFAULT_EKOKARTY_SOURCES = PROJECT_ROOT / "config" / "ekokarty_sources.yaml"
DEFAULT_EKOKARTY_KEYWORDS = PROJECT_ROOT / "config" / "ekokarty_keywords.yaml"


@dataclass(frozen=True)
class EkokartyInstitution:
    key: str
    name: str
    slug: str
    enabled: bool


@dataclass
class EkokartySettings:
    base_url: str
    user_agent: str
    timeout_seconds: float
    request_delay_seconds: float
    max_retries: int
    save_raw_html: bool
    sqlite_path: Path
    raw_search_dir: Path
    raw_details_dir: Path
    result_cap: int
    max_requests: int
    default_since: date
    project_root: Path

    @classmethod
    def from_mapping(cls, data: dict[str, Any], project_root: Path) -> "EkokartySettings":
        def resolve(path_value: str) -> Path:
            path = Path(path_value)
            if not path.is_absolute():
                path = project_root / path
            return path

        return cls(
            base_url=str(data.get("base_url", "https://ekokarty.pl")).rstrip("/"),
            user_agent=str(
                data.get(
                    "user_agent",
                    "sios-monitor/0.1 (public EkoKarty metadata collector; conservative pacing)",
                )
            ),
            timeout_seconds=float(data.get("timeout_seconds", 30)),
            request_delay_seconds=float(data.get("request_delay_seconds", 1.5)),
            max_retries=int(data.get("max_retries", 4)),
            save_raw_html=bool(data.get("save_raw_html", True)),
            sqlite_path=resolve(str(data.get("sqlite_path", "data/normalized/sios.sqlite"))),
            raw_search_dir=resolve(
                str(data.get("raw_search_dir", "data/raw/ekokarty/search"))
            ),
            raw_details_dir=resolve(
                str(data.get("raw_details_dir", "data/raw/ekokarty/details"))
            ),
            result_cap=int(data.get("result_cap", 2000)),
            max_requests=int(data.get("max_requests", 1000)),
            default_since=date.fromisoformat(
                str(data.get("default_since", "2010-01-01"))
            ),
            project_root=project_root,
        )


def load_settings(path: Path | None = None) -> EkokartySettings:
    config_path = path or DEFAULT_EKOKARTY_CONFIG
    return EkokartySettings.from_mapping(load_yaml(config_path), PROJECT_ROOT)


def load_institutions(path: Path | None = None) -> dict[str, EkokartyInstitution]:
    config_path = path or DEFAULT_EKOKARTY_SOURCES
    raw = load_yaml(config_path)
    institutions: dict[str, EkokartyInstitution] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            raise ValueError("Expected mapping for EkoKarty institution {!r}".format(key))
        slug = str(value.get("slug") or key).strip()
        if not slug:
            raise ValueError("EkoKarty institution {!r} is missing a slug".format(key))
        institutions[str(key)] = EkokartyInstitution(
            key=str(key),
            name=str(value.get("name") or key),
            slug=slug,
            enabled=bool(value.get("enabled", False)),
        )
    return institutions


def load_ekokarty_keywords(path: Path | None = None) -> dict[str, list[str]]:
    return load_keyword_groups(path or DEFAULT_EKOKARTY_KEYWORDS)


def iter_keywords(groups: dict[str, list[str]]) -> Iterable[str]:
    yield from flatten_keywords(groups)
