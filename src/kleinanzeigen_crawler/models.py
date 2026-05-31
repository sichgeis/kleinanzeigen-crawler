from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Listing:
    external_id: str
    url: str
    title: str
    platform: str = "kleinanzeigen"
    price: str = ""
    location: str = ""
    posted_date: str = ""
    description: str = ""
    attributes: str = ""
    image_url: str = ""
    source_url: str = ""
    seller_name: str = ""
    brand: str = ""
    size: str = ""
    condition: str = ""
    detail_status: int | None = None
    detail_fetched: bool = False

    @property
    def listing_key(self) -> str:
        return f"{self.platform}:{self.external_id}"

    @property
    def listing_id(self) -> str:
        return self.external_id


@dataclass(slots=True)
class CrawlResult:
    status: str
    pages_scanned: int
    listings_found: int
    error_summary: str = ""
