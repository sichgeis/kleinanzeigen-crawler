from pathlib import Path

import httpx
from typer.testing import CliRunner

from kleinanzeigen_crawler.cli import app
from kleinanzeigen_crawler.crawler import Crawler
from kleinanzeigen_crawler.models import Listing
from kleinanzeigen_crawler.storage import Storage


FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_search_cli(tmp_path) -> None:
    db = tmp_path / "test.db"
    storage = Storage(db)
    storage.init()
    storage.upsert_listing(
        Listing(
            external_id="123",
            url="https://example.test/listing",
            title="Baby Body",
            description="Größe 56",
        )
    )

    result = runner.invoke(app, ["search", "baby 56", "--db", str(db)])

    assert result.exit_code == 0
    assert "Baby Body" in result.output
    assert "https://example.test/listing" in result.output


def test_crawler_stops_on_403_and_records_run(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, request=request, text=(FIXTURES / "blocked.html").read_text())

    storage = Storage(tmp_path / "blocked.db")
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://www.kleinanzeigen.de")
    result = Crawler(storage, client=client, delay=0, sleeper=lambda _: None).crawl(
        "https://www.kleinanzeigen.de/s-bestandsliste.html?userId=15172148"
    )

    assert result.status == "blocked"
    assert result.pages_scanned == 0
    with storage.connect() as conn:
        row = conn.execute("SELECT status, error_summary FROM crawl_runs").fetchone()
    assert row["status"] == "blocked"
    assert "403" in row["error_summary"]
