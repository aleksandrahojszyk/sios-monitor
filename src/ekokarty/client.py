from __future__ import annotations

import logging
import random
import time
from datetime import date
from typing import Any, Optional

import httpx

from src.sios.client import RETRYABLE_STATUS, SiosHttpError
from src.sios.logging_utils import log_extra

logger = logging.getLogger(__name__)

SEARCH_FIELDS = (
    "karty_numer",
    "sprawy_znak",
    "rok_dokumentu",
    "rodzaj_dokumentu",
    "karty_nazwa",
    "temat_dokumentu",
    "karty_miejsce_wyd",
    "karty_wyt_name",
    "karty_zat_name",
)


class EkokartyClient:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout_seconds: float = 30.0,
        request_delay_seconds: float = 1.5,
        max_retries: int = 4,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries
        self._last_request_at: Optional[float] = None
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EkokartyClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _pace(self) -> None:
        if self.request_delay_seconds <= 0:
            return
        if self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.request_delay_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _backoff(self, attempt: int, retry_after: Optional[str] = None) -> None:
        if retry_after:
            try:
                time.sleep(float(retry_after))
                return
            except ValueError:
                pass
        delay = min(30.0, 0.5 * (2**attempt)) + random.uniform(0, 0.25)
        time.sleep(delay)

    def _request(self, method: str, path: str, **kwargs: Any) -> str:
        url = path if path.startswith("http") else "{}{}".format(self.base_url, path)
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                response = self._client.request(method, path, **kwargs)
                self._last_request_at = time.monotonic()
            except httpx.RequestError as exc:
                last_error = exc
                logger.warning(
                    "request_error",
                    extra=log_extra(url=url, attempt=attempt, error=str(exc)),
                )
                self._backoff(attempt)
                continue

            if response.status_code in RETRYABLE_STATUS:
                logger.warning(
                    "retryable_http_status",
                    extra=log_extra(
                        url=str(response.url),
                        status_code=response.status_code,
                        attempt=attempt,
                    ),
                )
                retry_after = response.headers.get("Retry-After")
                self._backoff(attempt, retry_after=retry_after)
                last_error = SiosHttpError(
                    "HTTP {} for {}".format(response.status_code, response.url),
                    url=str(response.url),
                    status_code=response.status_code,
                )
                continue

            if response.status_code >= 400:
                logger.error(
                    "http_error",
                    extra=log_extra(url=str(response.url), status_code=response.status_code),
                )
                raise SiosHttpError(
                    "HTTP {} for {}".format(response.status_code, response.url),
                    url=str(response.url),
                    status_code=response.status_code,
                )
            return response.text

        logger.error("request_failed", extra=log_extra(url=url, error=str(last_error)))
        if isinstance(last_error, SiosHttpError):
            raise last_error
        raise SiosHttpError("Failed {} {}: {}".format(method, url, last_error), url=url)

    def search(
        self,
        slug: str,
        keyword: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> str:
        data = {
            "szukajRodzaj": "NEW",
            "karty_all": keyword,
            "data_od": date_from.isoformat() if date_from else "",
            "data_do": date_to.isoformat() if date_to else "",
        }
        for field in SEARCH_FIELDS:
            data[field] = ""
        path = "/wykaz/{}/".format(slug)
        return self._request("POST", path, data=data)

    def fetch_card(self, path: str) -> str:
        if not path.startswith("/") and not path.startswith("http"):
            path = "/" + path
        return self._request("GET", path)

    def card_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return "{}{}".format(self.base_url, path)
