"""Polite HTTP GET with retries, shared by every ingester."""

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

USER_AGENT = "hackIAthon-whoamisfc/0.1 (+https://github.com/Wcno/hackiaton-whoamisfc)"
MIN_SECONDS_BETWEEN_REQUESTS_PER_HOST = 1.0
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_last_request_at: dict[str, float] = {}


@dataclass(frozen=True)
class Response:
    url: str
    body: bytes
    headers: dict[str, str]


def get(url: str, *, attempts: int = 4, backoff_seconds: float = 3.0, timeout: int = 60) -> Response:
    for attempt in range(1, attempts + 1):
        _wait_for_host(url)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                headers = {key.lower(): value for key, value in response.headers.items()}
                return Response(url=url, body=response.read(), headers=headers)
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_STATUS or attempt == attempts:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts:
                raise
        time.sleep(backoff_seconds * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def _wait_for_host(url: str) -> None:
    host = urlsplit(url).netloc
    elapsed = time.monotonic() - _last_request_at.get(host, float("-inf"))
    if elapsed < MIN_SECONDS_BETWEEN_REQUESTS_PER_HOST:
        time.sleep(MIN_SECONDS_BETWEEN_REQUESTS_PER_HOST - elapsed)
    _last_request_at[host] = time.monotonic()
