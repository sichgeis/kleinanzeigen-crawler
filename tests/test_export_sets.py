from pathlib import Path

from typer.testing import CliRunner

from kleinanzeigen_crawler.cli import app
from kleinanzeigen_crawler.export_sets import (
    NEWBORN_GIRL_56,
    export_set,
    format_money,
    parse_price,
    render_html,
)
from kleinanzeigen_crawler.models import Listing
from kleinanzeigen_crawler.storage import Storage


runner = CliRunner()


def test_price_parsing_and_formatting() -> None:
    assert parse_price("7.5 EUR") == 7.5
    assert parse_price("2,49 €") == 2.49
    assert parse_price("") == 0
    assert format_money(75) == "75 EUR"
    assert format_money(91.49) == "91,49 EUR"


def test_export_reports_missing_ids(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "empty.db")
    storage.init()

    try:
        export_set(storage, "newborn-girl-56", tmp_path / "out.html")
    except ValueError as exc:
        assert "Missing listings" in str(exc)
        assert "vinted:8611457744" in str(exc)
    else:
        raise AssertionError("expected missing listing error")


def test_render_html_contains_gallery_controls_and_escapes() -> None:
    rows = {}
    for item in NEWBORN_GIRL_56.items:
        rows[item.listing_key] = _row(
            item.listing_key,
            title='Body <script>alert("x")</script>',
            price="4 EUR",
            description="Größe 50/56 <b>nice</b> 🛍️ hashtag block",
        )

    output = render_html(NEWBORN_GIRL_56, rows)

    assert "Shortlist" in output
    assert "data-filter=\"Bodies\"" in output
    assert "selected-total" in output
    assert "Hallo Elisa" in output
    assert "https://images.example.test/item.jpg" in output
    assert "<script>alert" not in output
    assert "&lt;script&gt;" in output


def test_export_set_cli_writes_html(tmp_path: Path) -> None:
    db = tmp_path / "items.db"
    storage = Storage(db)
    storage.init()
    for item in NEWBORN_GIRL_56.items:
        storage.upsert_listing(
            Listing(
                platform=item.listing_key.split(":", 1)[0],
                external_id=item.listing_key.split(":", 1)[1],
                url=f"https://example.test/{item.listing_key}",
                title=f"Item {item.listing_key}",
                price="4 EUR",
                size="1-3 Monate / 56",
                brand="Brand",
                condition="Sehr gut",
                description="Beschreibung Größe 56",
                image_url="https://images.example.test/item.jpg",
            )
        )

    output = tmp_path / "gallery.html"
    result = runner.invoke(app, ["export-set", "newborn-girl-56", "--db", str(db), "--output", str(output)])

    assert result.exit_code == 0
    assert output.exists()
    html = output.read_text()
    assert "Erstausstattung Mädchen bis Größe 56" in html
    assert "Item vinted:8611457744" in html


def _row(
    listing_key: str,
    *,
    title: str,
    price: str,
    description: str,
) -> dict[str, str]:
    platform, external_id = listing_key.split(":", 1)
    return {
        "listing_key": listing_key,
        "platform": platform,
        "external_id": external_id,
        "url": f"https://example.test/{listing_key}",
        "title": title,
        "price": price,
        "location": "",
        "posted_date": "",
        "description": description,
        "attributes": "",
        "image_url": "https://images.example.test/item.jpg",
        "source_url": "",
        "seller_name": "elisa150620",
        "brand": "Brand",
        "size": "1-3 Monate / 56",
        "condition": "Sehr gut",
        "detail_status": 200,
        "detail_fetched": 1,
        "created_at": "",
        "updated_at": "",
    }
