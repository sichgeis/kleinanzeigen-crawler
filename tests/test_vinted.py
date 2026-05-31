from pathlib import Path

import httpx
from typer.testing import CliRunner

from kleinanzeigen_crawler.cli import app
from kleinanzeigen_crawler.crawler import Crawler
from kleinanzeigen_crawler.platforms import (
    adapter_for_url,
    parse_vinted_detail_description,
    vinted_member_id,
)
from kleinanzeigen_crawler.storage import Storage


FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_platform_auto_detection() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200)))

    assert adapter_for_url("https://www.kleinanzeigen.de/s-bestandsliste.html?userId=1", client, 0, lambda _: None, True).platform == "kleinanzeigen"
    assert adapter_for_url("https://www.vinted.de/member/44026682-elisa150620", client, 0, lambda _: None, True).platform == "vinted"


def test_vinted_member_id() -> None:
    assert vinted_member_id("https://www.vinted.de/member/44026682-elisa150620") == "44026682"


def test_parse_vinted_detail_description() -> None:
    html = (FIXTURES / "vinted_item.html").read_text()

    assert "Größe 50/56" in parse_vinted_detail_description(html)


def test_crawl_vinted_with_details(tmp_path) -> None:
    seen_item_pages: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/member/44026682" in url:
            return httpx.Response(200, request=request, text="<html><title>elisa150620</title></html>")
        if "page=1" in url:
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "application/json"},
                text=(FIXTURES / "vinted_catalog_page1.json").read_text(),
            )
        if "page=2" in url:
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "application/json"},
                text=(FIXTURES / "vinted_catalog_page2.json").read_text(),
            )
        if "/items/" in url:
            seen_item_pages.append(url)
            if "9001202823" in url:
                return httpx.Response(
                    200,
                    request=request,
                    text='<html><head><meta name="description" content="Set aus Jeanslatzhose Größe 80" /></head></html>',
                )
            return httpx.Response(200, request=request, text=(FIXTURES / "vinted_item.html").read_text())
        raise AssertionError(url)

    storage = Storage(tmp_path / "vinted.db")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    result = Crawler(storage, client=client, delay=0, sleeper=lambda _: None).crawl(
        "https://www.vinted.de/member/44026682-elisa150620"
    )

    assert result.status == "success"
    assert result.pages_scanned == 2
    assert result.listings_found == 2
    assert len(seen_item_pages) == 2
    rows = storage.search("Größe56", 10)
    assert rows[0]["listing_key"] == "vinted:9001182448"
    assert rows[0]["size"] == "Bis zu 1 Monat / 50"


def test_crawl_vinted_no_details_skips_item_pages(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/member/44026682" in url:
            return httpx.Response(200, request=request, text="<html><title>elisa150620</title></html>")
        if "catalog/items" in url:
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "application/json"},
                text=(FIXTURES / "vinted_catalog_page1.json").read_text().replace('"total_pages": 2', '"total_pages": 1'),
            )
        if "/items/" in url:
            raise AssertionError("item page should not be fetched")
        raise AssertionError(url)

    storage = Storage(tmp_path / "vinted.db")
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    result = Crawler(storage, client=client, delay=0, sleeper=lambda _: None).crawl(
        "https://www.vinted.de/member/44026682-elisa150620",
        details=False,
    )

    assert result.status == "success"
    assert result.listings_found == 1


def test_cli_search_shows_platform_column(tmp_path) -> None:
    storage = Storage(tmp_path / "mixed.db")
    storage.init()
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                headers={"content-type": "application/json"} if "catalog/items" in str(request.url) else {},
                text=(
                    (FIXTURES / "vinted_catalog_page1.json").read_text().replace('"total_pages": 2', '"total_pages": 1')
                    if "catalog/items" in str(request.url)
                    else "<html><title>profile</title></html>"
                ),
            )
        ),
        follow_redirects=True,
    )
    Crawler(storage, client=client, delay=0, sleeper=lambda _: None).crawl(
        "https://www.vinted.de/member/44026682-elisa150620",
        details=False,
    )

    result = runner.invoke(app, ["search", "Zara", "--db", str(tmp_path / "mixed.db")])

    assert result.exit_code == 0
    assert "Platform" in result.output
    assert "vinted" in result.output
