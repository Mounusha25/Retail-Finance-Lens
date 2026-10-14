from __future__ import annotations

import gzip
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter


@dataclass(frozen=True)
class RawResponse:
    endpoint: str
    url: str
    fetched_at: datetime
    status_code: int
    headers: dict[str, str]
    content: bytes
    sha256: str
    file_path: Path

    def json(self) -> dict[str, Any]:
        return json.loads(self.content)


class SecClient:
    base_url = "https://data.sec.gov"

    def __init__(self, user_agent: str, raw_dir: Path, requests_per_second: float = 5.0) -> None:
        if not user_agent or "@" not in user_agent:
            raise ValueError("A descriptive SEC User-Agent containing a contact email is required")
        self.raw_dir = raw_dir
        self.minimum_interval = 1.0 / requests_per_second
        self.last_request_at = 0.0
        self.client = httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        )

    def __enter__(self) -> "SecClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        if elapsed < self.minimum_interval:
            time.sleep(self.minimum_interval - elapsed)

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        wait=wait_exponential_jitter(initial=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _get(self, url: str) -> httpx.Response:
        self._throttle()
        response = self.client.get(url)
        self.last_request_at = time.monotonic()
        if response.status_code == 429 or response.status_code >= 500:
            raise httpx.NetworkError(f"SEC temporarily returned {response.status_code}")
        response.raise_for_status()
        return response

    def fetch_json(self, endpoint: str, cik: str, ticker: str) -> RawResponse:
        if endpoint == "submissions":
            url = f"{self.base_url}/submissions/CIK{cik}.json"
        elif endpoint == "companyfacts":
            url = f"{self.base_url}/api/xbrl/companyfacts/CIK{cik}.json"
        else:
            raise ValueError(f"Unsupported SEC endpoint: {endpoint}")

        return self._fetch(endpoint, url, ticker, suffix="json")

    def fetch_filing_document(
        self,
        ticker: str,
        accession_number: str,
        source_url: str,
    ) -> RawResponse:
        return self._fetch(
            "filing",
            source_url,
            ticker,
            accession_number=accession_number,
            suffix="html",
        )

    def _fetch(
        self,
        endpoint: str,
        url: str,
        ticker: str,
        *,
        accession_number: str | None = None,
        suffix: str,
    ) -> RawResponse:
        response = self._get(url)
        fetched_at = datetime.now(timezone.utc)
        digest = hashlib.sha256(response.content).hexdigest()
        timestamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
        folder = self.raw_dir / ticker / endpoint
        if accession_number:
            folder = folder / accession_number
        target = folder / f"{timestamp}_{digest[:12]}.{suffix}.gz"
        target.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(target, "wb") as stream:
            stream.write(response.content)
        return RawResponse(
            endpoint=endpoint,
            url=url,
            fetched_at=fetched_at,
            status_code=response.status_code,
            headers={key: value for key, value in response.headers.items()},
            content=response.content,
            sha256=digest,
            file_path=target,
        )


def read_gzip_json(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rb") as stream:
        return json.load(stream)
