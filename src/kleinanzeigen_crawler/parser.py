from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import Listing

BASE_URL = "https://www.kleinanzeigen.de"


HARD_BLOCK_PATTERNS = (
    "captcha",
    "zugriff verweigert",
    "access denied",
    "unusual traffic",
    "bitte bestätige",
    "verify you are human",
    "bot detection",
    "automatisierte zugriffe",
)

LOGIN_WALL_PATTERNS = (
    "bitte melde dich an",
    "du musst angemeldet sein",
    "melde dich an, um fortzufahren",
)


def canonicalize_url(url: str, base_url: str = BASE_URL) -> str:
    absolute = urljoin(base_url, url)
    parsed = urlparse(absolute)
    return parsed._replace(fragment="").geturl()


def listing_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    patterns = (
        r"/s-anzeige/[^/]+/(\d+)-",
        r"/s-anzeige/[^/]+/(\d+)$",
        r"[?&]adId=(\d+)",
        r"/(\d+)(?:$|[/?#-])",
    )
    target = parsed.path + ("?" + parsed.query if parsed.query else "")
    for pattern in patterns:
        match = re.search(pattern, target)
        if match:
            return match.group(1)
    safe = re.sub(r"[^a-zA-Z0-9]+", "-", parsed.path).strip("-")
    return safe or url


def is_block_page(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True).lower()
    if any(pattern in text for pattern in HARD_BLOCK_PATTERNS):
        return True
    has_listings = bool(_find_listing_cards(soup))
    return not has_listings and any(pattern in text for pattern in LOGIN_WALL_PATTERNS)


def parse_listing_page(html: str, page_url: str) -> tuple[list[Listing], str | None]:
    soup = BeautifulSoup(html, "lxml")
    cards = _find_listing_cards(soup)
    listings = [_parse_card(card, page_url) for card in cards]
    listings = [listing for listing in listings if listing.url and listing.title]
    return listings, _find_next_page(soup, page_url)


def parse_detail_page(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    description = _text_from_first(
        soup,
        [
            "#viewad-description-text",
            "[data-testid='ad-description']",
            ".aditem-main--middle--description",
            ".boxedarticle--details",
        ],
    )
    attributes = _parse_attributes(soup)
    return description, attributes


def _find_listing_cards(soup: BeautifulSoup) -> list[Tag]:
    selectors = [
        "article.aditem",
        "li.ad-listitem",
        "[data-testid='ad-item']",
        "article[data-adid]",
    ]
    for selector in selectors:
        found = [tag for tag in soup.select(selector) if isinstance(tag, Tag)]
        if found:
            return found
    fallback: list[Tag] = []
    for link in soup.select("a[href*='/s-anzeige/']"):
        card = link.find_parent(["article", "li", "div"])
        if isinstance(card, Tag) and card not in fallback:
            fallback.append(card)
    return fallback


def _parse_card(card: Tag, page_url: str) -> Listing:
    link = card.select_one("a[href*='/s-anzeige/']") or card.find("a", href=True)
    href = link.get("href", "") if isinstance(link, Tag) else ""
    url = canonicalize_url(href, page_url)
    title = _title_from_card(card, link)
    image = card.select_one("img")
    image_url = ""
    if isinstance(image, Tag):
        image_url = image.get("src") or image.get("data-src") or ""
        if image_url:
            image_url = canonicalize_url(image_url, page_url)
    return Listing(
        external_id=listing_id_from_url(url),
        platform="kleinanzeigen",
        url=url,
        title=title,
        price=_text_from_first(card, [".aditem-main--middle--price-shipping--price", ".aditem-price", "[data-testid='ad-price']"]),
        location=_text_from_first(card, [".aditem-main--top--left", ".aditem-location", "[data-testid='ad-location']"]),
        posted_date=_text_from_first(card, [".aditem-main--top--right", ".aditem-date", "time", "[data-testid='ad-date']"]),
        image_url=image_url,
    )


def _title_from_card(card: Tag, link: Tag | None) -> str:
    title = _text_from_first(card, [".ellipsis", ".text-module-begin", "[data-testid='ad-title']", "h2", "h3"])
    if title:
        return title
    if isinstance(link, Tag):
        return link.get_text(" ", strip=True)
    return ""


def _find_next_page(soup: BeautifulSoup, page_url: str) -> str | None:
    link = soup.select_one("a[rel='next'], a.pagination-next, a[aria-label*='Weiter'], a[title*='Weiter']")
    if isinstance(link, Tag) and link.get("href"):
        return canonicalize_url(str(link["href"]), page_url)

    parsed = urlparse(page_url)
    query = parse_qs(parsed.query)
    current_page = int(query.get("pageNum", ["1"])[0] or "1")
    for candidate in soup.select("a[href]"):
        href = candidate.get("href", "")
        parsed_href = urlparse(urljoin(page_url, href))
        candidate_page = parse_qs(parsed_href.query).get("pageNum", [""])[0]
        if candidate_page.isdigit() and int(candidate_page) == current_page + 1:
            return canonicalize_url(href, page_url)
    return None


def _parse_attributes(soup: BeautifulSoup) -> str:
    values: list[str] = []
    for selector in ["#viewad-details li", ".addetailslist--detail", "[data-testid='attribute']"]:
        for item in soup.select(selector):
            text = item.get_text(" ", strip=True)
            if text and text not in values:
                values.append(text)
    for definition in soup.select("dt"):
        dd = definition.find_next_sibling("dd")
        if isinstance(dd, Tag):
            text = f"{definition.get_text(' ', strip=True)}: {dd.get_text(' ', strip=True)}"
            if text and text not in values:
                values.append(text)
    return "\n".join(values)


def _text_from_first(root: Tag | BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        item = root.select_one(selector)
        if isinstance(item, Tag):
            text = item.get_text(" ", strip=True)
            if text:
                return re.sub(r"\s+", " ", text)
    return ""
