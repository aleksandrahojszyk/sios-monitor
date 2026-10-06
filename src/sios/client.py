from __future__ import annotations

import logging
import random
import time
from typing import Any, Optional

import httpx

from .logging_utils import log_extra
from .models import SEARCH_PATH, detail_url

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class SiosHttpError(RuntimeError):
    def __init__(self, message: str, url: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class SiosClient:
    def __init__(
        self,
        base_url: str,
        user_agent: str,
        timeout_seconds: float = 30.0,
        request_delay_seconds: float = 1.5,
        max_retries: int = 4,
        iid: int = 0,
        results_per_page: int = 30,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries
        self.iid = iid
        self.results_per_page = results_per_page
        self._last_request_at: Optional[float] = None
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
            timeout=timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SiosClient":
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

    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> str:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self._pace()
            try:
                response = self._client.get(path, params=params)
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
                    f"HTTP {response.status_code} for {response.url}",
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
                    f"HTTP {response.status_code} for {response.url}",
                    url=str(response.url),
                    status_code=response.status_code,
                )
            return response.text

        logger.error("request_failed", extra=log_extra(url=url, error=str(last_error)))
        if isinstance(last_error, SiosHttpError):
            raise last_error
        raise SiosHttpError(f"Failed GET {url}: {last_error}", url=url)

    def _backoff(self, attempt: int, retry_after: Optional[str] = None) -> None:
        if retry_after:
            try:
                time.sleep(float(retry_after))
                return
            except ValueError:
                pass
        delay = min(30.0, 0.5 * (2**attempt)) + random.uniform(0, 0.25)
        time.sleep(delay)

    def search(self, keyword: str, page: int, results: Optional[int] = None) -> str:
        params = {
            "keywords": keyword,
            "iid": self.iid,
            "id_doctype": 0,
            "id_doctopic": 0,
            "page": page,
            "results": results if results is not None else self.results_per_page,
            "submitSearch": "Szukaj",
        }
        return self.get(SEARCH_PATH, params=params)

    def fetch_card(self, sios_id: int) -> str:
        path = f"/documents/details/id/{sios_id}"
        return self.get(path)

    def card_url(self, sios_id: int) -> str:
        return detail_url(self.base_url, sios_id)
