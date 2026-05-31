from pathlib import Path

from kleinanzeigen_crawler.parser import (
    is_block_page,
    listing_id_from_url,
    parse_detail_page,
    parse_listing_page,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_listing_page_cards_and_next_page() -> None:
    html = (FIXTURES / "list_page.html").read_text()
    listings, next_page = parse_listing_page(
        html,
        "https://www.kleinanzeigen.de/s-bestandsliste.html?userId=15172148",
    )

    assert len(listings) == 2
    assert listings[0].listing_id == "123456789"
    assert listings[0].title == "Baby Body Größe 56"
    assert listings[0].price == "5 €"
    assert listings[0].location == "10115 Mitte"
    assert listings[0].posted_date == "Heute"
    assert listings[0].image_url == "https://www.kleinanzeigen.de/img/body.jpg"
    assert next_page == "https://www.kleinanzeigen.de/s-bestandsliste.html?userId=15172148&pageNum=2"


def test_parse_detail_page_description_and_attributes() -> None:
    html = (FIXTURES / "detail_page.html").read_text()
    description, attributes = parse_detail_page(html)

    assert "Babysachen in Größe 56" in description
    assert "Größe: 56" in attributes
    assert "Typ: Babybody" in attributes


def test_listing_id_from_url() -> None:
    assert (
        listing_id_from_url("https://www.kleinanzeigen.de/s-anzeige/foo/123456789-258-1234")
        == "123456789"
    )


def test_normal_listing_page_with_login_link_is_not_blocked() -> None:
    html = (FIXTURES / "list_page.html").read_text() + "<a>Einloggen</a>"

    assert is_block_page(html) is False
