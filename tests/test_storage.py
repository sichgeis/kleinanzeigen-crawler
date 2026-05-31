from kleinanzeigen_crawler.models import Listing
from kleinanzeigen_crawler.storage import Storage


def test_upsert_and_search(tmp_path) -> None:
    storage = Storage(tmp_path / "test.db")
    storage.init()
    storage.upsert_listing(
        Listing(
            external_id="123",
            url="https://www.kleinanzeigen.de/s-anzeige/foo/123-1",
            title="Baby Body",
            price="5 €",
            location="Berlin",
            posted_date="Heute",
            description="Babysachen in Größe 56 und sehr gutem Zustand",
            attributes="Größe: 56",
        )
    )

    results = storage.search("baby größe 56")

    assert len(results) == 1
    assert results[0]["listing_key"] == "kleinanzeigen:123"
    assert "Größe" in results[0]["snippet"]


def test_migrates_old_kleinanzeigen_schema(tmp_path) -> None:
    db = tmp_path / "old.db"
    conn = __import__("sqlite3").connect(db)
    conn.executescript(
        """
        CREATE TABLE listings (
            listing_id TEXT PRIMARY KEY,
            url TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            price TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            posted_date TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            attributes TEXT NOT NULL DEFAULT '',
            image_url TEXT NOT NULL DEFAULT '',
            source_user_url TEXT NOT NULL DEFAULT '',
            detail_status INTEGER,
            detail_fetched INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO listings (
            listing_id, url, title, description, created_at, updated_at
        )
        VALUES ('123', 'https://example.test/123', 'Old Baby Body', 'Größe 50', 'now', 'now');
        """
    )
    conn.commit()
    conn.close()

    storage = Storage(db)
    storage.init()

    row = storage.get_listing("kleinanzeigen:123")
    assert row is not None
    assert row["platform"] == "kleinanzeigen"
    assert row["external_id"] == "123"
    assert storage.search("Größe 50", 10)[0]["listing_key"] == "kleinanzeigen:123"
