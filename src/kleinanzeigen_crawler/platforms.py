from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from bs4 import BeautifulSoup

from .errors import CrawlBlockedError
from .models import Listing
from .parser import is_block_page, parse_detail_page, parse_listing_page


@dataclass(slots=True)
class PageResult:
    listings: list[Listing]
    next_url: str | None = None


class PlatformAdapter(ABC):
    platform: str

    def __init__(
        self,
        client: httpx.Client,
        delay: float,
        sleeper: Callable[[float], None],
        details: bool = True,
    ) -> None:
        self.client = client
        self.delay = delay
        self.sleeper = sleeper
        self.details = details

    @abstractmethod
    def pages(self, source_url: str, max_pages: int | None = None) -> Iterator[PageResult]:
        pass

    def _get(self, url: str, **kwargs) -> httpx.Response:
        last_error: httpx.HTTPError | None = None
        for attempt in range(3):
            try:
                response = self.client.get(url, **kwargs)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                    self.sleeper(self.delay * (attempt + 1))
                    continue
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < 2:
                    self.sleeper(self.delay * (attempt + 1))
        assert last_error is not None
        raise last_error

    def _ensure_allowed(self, response: httpx.Response, *, html: bool = True) -> None:
        if response.status_code == 403:
            raise CrawlBlockedError(f"Blocked with HTTP 403 at {response.url}")
        if response.status_code >= 400:
            response.raise_for_status()
        if html and is_block_page(response.text):
            raise CrawlBlockedError(f"Blocked by CAPTCHA/login/access page at {response.url}")


class KleinanzeigenAdapter(PlatformAdapter):
    platform = "kleinanzeigen"

    def pages(self, source_url: str, max_pages: int | None = None) -> Iterator[PageResult]:
        next_url: str | None = source_url
        seen_pages: set[str] = set()
        pages_scanned = 0
        while next_url and next_url not in seen_pages:
            if max_pages is not None and pages_scanned >= max_pages:
                break
            seen_pages.add(next_url)
            response = self._get(next_url)
            self._ensure_allowed(response)
            listings, next_url = parse_listing_page(response.text, str(response.url))
            for listing in listings:
                listing.platform = self.platform
                listing.source_url = source_url
                if self.details:
                    self._fetch_detail(listing)
                    self.sleeper(self.delay)
            pages_scanned += 1
            yield PageResult(listings=listings, next_url=next_url)
            if next_url:
                self.sleeper(self.delay)

    def _fetch_detail(self, listing: Listing) -> None:
        try:
            response = self._get(listing.url)
            listing.detail_status = response.status_code
            self._ensure_allowed(response)
            description, attributes = parse_detail_page(response.text)
            listing.description = description
            listing.attributes = attributes
            listing.detail_fetched = True
        except CrawlBlockedError:
            raise
        except httpx.HTTPError:
            listing.detail_fetched = False


class VintedAdapter(PlatformAdapter):
    platform = "vinted"
    per_page = 96

    def pages(self, source_url: str, max_pages: int | None = None) -> Iterator[PageResult]:
        member_id = vinted_member_id(source_url)
        self._warm_session(source_url)
        page = 1
        total_pages: int | None = None
        while total_pages is None or page <= total_pages:
            if max_pages is not None and page > max_pages:
                break
            response = self._get(
                self._catalog_url(member_id, page),
                headers={"Accept": "application/json", "Referer": source_url},
            )
            self._ensure_allowed(response, html=False)
            data = response.json()
            items = data.get("items", [])
            listings = [self._listing_from_item(item, source_url) for item in items]
            if self.details:
                for listing in listings:
                    self._fetch_detail(listing)
                    self.sleeper(self.delay)
            pagination = data.get("pagination") or {}
            total_pages = int(pagination.get("total_pages") or page)
            next_url = self._catalog_url(member_id, page + 1) if page < total_pages else None
            yield PageResult(listings=listings, next_url=next_url)
            page += 1
            if page <= total_pages:
                self.sleeper(self.delay)

    def _warm_session(self, source_url: str) -> None:
        response = self._get(source_url, headers={"Accept": "text/html,application/xhtml+xml"})
        self._ensure_vinted_allowed(response)

    def _catalog_url(self, member_id: str, page: int) -> str:
        query = urlencode(
            {
                "user_ids[]": member_id,
                "page": page,
                "per_page": self.per_page,
                "order": "newest_first",
            }
        )
        return f"https://www.vinted.de/api/v2/catalog/items?{query}"

    def _listing_from_item(self, item: dict, source_url: str) -> Listing:
        external_id = str(item["id"])
        price = ""
        raw_price = item.get("price") or {}
        if raw_price.get("amount"):
            amount = str(raw_price["amount"]).rstrip("0").rstrip(".")
            price = f"{amount} {raw_price.get('currency_code', '').strip()}".strip()
        photo = item.get("photo") or {}
        user = item.get("user") or {}
        attrs = {
            "brand": item.get("brand_title") or "",
            "size": item.get("size_title") or "",
            "condition": item.get("status") or "",
        }
        attributes = "\n".join(f"{k}: {v}" for k, v in attrs.items() if v)
        return Listing(
            platform=self.platform,
            external_id=external_id,
            url=item.get("url") or f"https://www.vinted.de{item.get('path', '')}",
            title=item.get("title") or "",
            price=price,
            description="",
            attributes=attributes,
            image_url=photo.get("url") or "",
            source_url=source_url,
            seller_name=user.get("login") or "",
            brand=attrs["brand"],
            size=attrs["size"],
            condition=attrs["condition"],
            detail_status=None,
            detail_fetched=False,
        )

    def _fetch_detail(self, listing: Listing) -> None:
        try:
            response = self._get(listing.url, headers={"Accept": "text/html,application/xhtml+xml"})
            listing.detail_status = response.status_code
            self._ensure_vinted_allowed(response)
            description = parse_vinted_detail_description(response.text)
            if description:
                listing.description = description
            listing.detail_fetched = True
        except CrawlBlockedError:
            raise
        except httpx.HTTPError:
            listing.detail_fetched = False

    def _ensure_vinted_allowed(self, response: httpx.Response) -> None:
        if response.status_code == 403:
            raise CrawlBlockedError(f"Blocked with HTTP 403 at {response.url}")
        if response.status_code >= 400:
            response.raise_for_status()
        text = response.text.lower()
        if "datadome" in text and ("captcha-delivery" in text or "geo.captcha" in text):
            raise CrawlBlockedError(f"Blocked by Vinted DataDome page at {response.url}")


def adapter_for_url(
    url: str,
    client: httpx.Client,
    delay: float,
    sleeper: Callable[[float], None],
    details: bool,
) -> PlatformAdapter:
    host = urlparse(url).netloc.lower()
    if "kleinanzeigen.de" in host:
        return KleinanzeigenAdapter(client, delay, sleeper, details)
    if "vinted." in host:
        return VintedAdapter(client, delay, sleeper, details)
    raise ValueError(f"Unsupported URL host: {host}")


def vinted_member_id(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "member":
        return parts[1].split("-", 1)[0]
    query_id = parse_qs(parsed.query).get("user_id", [""])[0]
    if query_id:
        return query_id
    raise ValueError(f"Could not extract Vinted member ID from URL: {url}")


def parse_vinted_detail_description(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    meta = soup.select_one("meta[name='description']")
    if meta and meta.get("content"):
        return str(meta["content"]).strip()
    return ""
