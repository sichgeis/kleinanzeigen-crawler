from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from .errors import CrawlBlockedError
from .models import CrawlResult
from .platforms import adapter_for_url
from .storage import Storage


class Crawler:
    def __init__(
        self,
        storage: Storage,
        *,
        delay: float = 2.0,
        timeout: float = 20.0,
        sleeper: Callable[[float], None] = time.sleep,
        client: httpx.Client | None = None,
    ) -> None:
        self.storage = storage
        self.delay = delay
        self.sleeper = sleeper
        self.client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/json",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            },
        )

    def crawl(
        self,
        source_url: str,
        max_pages: int | None = None,
        details: bool = True,
    ) -> CrawlResult:
        self.storage.init()
        adapter = adapter_for_url(source_url, self.client, self.delay, self.sleeper, details)
        run_id = self.storage.start_crawl(source_url, adapter.platform)
        pages_scanned = 0
        listings_found = 0
        status = "success"
        error_summary = ""

        try:
            for page in adapter.pages(source_url, max_pages=max_pages):
                pages_scanned += 1
                for listing in page.listings:
                    self.storage.upsert_listing(listing)
                    listings_found += 1
        except CrawlBlockedError as exc:
            status = "blocked"
            error_summary = str(exc)
        except httpx.HTTPError as exc:
            status = "error"
            error_summary = f"HTTP error: {exc}"
        except Exception as exc:
            status = "error"
            error_summary = f"{type(exc).__name__}: {exc}"
        finally:
            self.storage.finish_crawl(run_id, status, pages_scanned, listings_found, error_summary)

        return CrawlResult(status, pages_scanned, listings_found, error_summary)
