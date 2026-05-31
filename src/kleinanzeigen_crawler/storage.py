from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .models import Listing


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Storage:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            self._migrate_old_schema(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    listing_key TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    price TEXT NOT NULL DEFAULT '',
                    location TEXT NOT NULL DEFAULT '',
                    posted_date TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    attributes TEXT NOT NULL DEFAULT '',
                    image_url TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    seller_name TEXT NOT NULL DEFAULT '',
                    brand TEXT NOT NULL DEFAULT '',
                    size TEXT NOT NULL DEFAULT '',
                    condition TEXT NOT NULL DEFAULT '',
                    detail_status INTEGER,
                    detail_fetched INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS listing_fts USING fts5(
                    listing_key UNINDEXED,
                    title,
                    price,
                    location,
                    posted_date,
                    description,
                    attributes,
                    seller_name,
                    brand,
                    size,
                    condition
                );

                CREATE TABLE IF NOT EXISTS crawl_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    pages_scanned INTEGER NOT NULL DEFAULT 0,
                    listings_found INTEGER NOT NULL DEFAULT 0,
                    error_summary TEXT NOT NULL DEFAULT ''
                );
                """
            )
            self._ensure_crawl_runs_platform(conn)
            self._rebuild_fts(conn)

    def start_crawl(self, source_url: str, platform: str) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO crawl_runs (platform, source_url, started_at, status) VALUES (?, ?, ?, ?)",
                (platform, source_url, now_iso(), "running"),
            )
            return int(cur.lastrowid)

    def finish_crawl(
        self,
        run_id: int,
        status: str,
        pages_scanned: int,
        listings_found: int,
        error_summary: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE crawl_runs
                SET finished_at = ?, status = ?, pages_scanned = ?, listings_found = ?, error_summary = ?
                WHERE id = ?
                """,
                (now_iso(), status, pages_scanned, listings_found, error_summary, run_id),
            )

    def upsert_listing(self, listing: Listing) -> None:
        timestamp = now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO listings (
                    listing_key, platform, external_id, url, title, price, location, posted_date,
                    description, attributes, image_url, source_url, seller_name, brand, size,
                    condition, detail_status, detail_fetched, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(listing_key) DO UPDATE SET
                    url = excluded.url,
                    title = excluded.title,
                    price = excluded.price,
                    location = excluded.location,
                    posted_date = excluded.posted_date,
                    description = excluded.description,
                    attributes = excluded.attributes,
                    image_url = excluded.image_url,
                    source_url = excluded.source_url,
                    seller_name = excluded.seller_name,
                    brand = excluded.brand,
                    size = excluded.size,
                    condition = excluded.condition,
                    detail_status = excluded.detail_status,
                    detail_fetched = excluded.detail_fetched,
                    updated_at = excluded.updated_at
                """,
                (
                    listing.listing_key,
                    listing.platform,
                    listing.external_id,
                    listing.url,
                    listing.title,
                    listing.price,
                    listing.location,
                    listing.posted_date,
                    listing.description,
                    listing.attributes,
                    listing.image_url,
                    listing.source_url,
                    listing.seller_name,
                    listing.brand,
                    listing.size,
                    listing.condition,
                    listing.detail_status,
                    int(listing.detail_fetched),
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute("DELETE FROM listing_fts WHERE listing_key = ?", (listing.listing_key,))
            conn.execute(
                """
                INSERT INTO listing_fts(
                    listing_key, title, price, location, posted_date, description, attributes,
                    seller_name, brand, size, condition
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing.listing_key,
                    listing.title,
                    listing.price,
                    listing.location,
                    listing.posted_date,
                    listing.description,
                    listing.attributes,
                    listing.seller_name,
                    listing.brand,
                    listing.size,
                    listing.condition,
                ),
            )

    def get_listing(self, listing_key: str) -> sqlite3.Row | None:
        normalized = listing_key if ":" in listing_key else f"kleinanzeigen:{listing_key}"
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM listings WHERE listing_key = ?",
                (normalized,),
            ).fetchone()

    def search(self, query: str, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return list(
                conn.execute(
                    """
                    SELECT
                        listings.*,
                        snippet(listing_fts, 5, '[', ']', ' ... ', 18) AS snippet,
                        bm25(listing_fts) AS rank
                    FROM listing_fts
                    JOIN listings ON listings.listing_key = listing_fts.listing_key
                    WHERE listing_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (_fts_query(query), limit),
                )
            )

    def _migrate_old_schema(self, conn: sqlite3.Connection) -> None:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'listings'"
        ).fetchone()
        if table is None:
            return
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(listings)")]
        if "listing_key" in columns:
            self._ensure_crawl_runs_platform(conn)
            return
        if "listing_id" not in columns:
            return

        conn.execute("ALTER TABLE listings RENAME TO listings_old")
        conn.execute("DROP TABLE IF EXISTS listing_fts")
        conn.executescript(
            """
            CREATE TABLE listings (
                listing_key TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                price TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL DEFAULT '',
                posted_date TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                attributes TEXT NOT NULL DEFAULT '',
                image_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                seller_name TEXT NOT NULL DEFAULT '',
                brand TEXT NOT NULL DEFAULT '',
                size TEXT NOT NULL DEFAULT '',
                condition TEXT NOT NULL DEFAULT '',
                detail_status INTEGER,
                detail_fetched INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO listings (
                listing_key, platform, external_id, url, title, price, location, posted_date,
                description, attributes, image_url, source_url, detail_status, detail_fetched,
                created_at, updated_at
            )
            SELECT
                'kleinanzeigen:' || listing_id, 'kleinanzeigen', listing_id, url, title, price,
                location, posted_date, description, attributes, image_url, source_user_url,
                detail_status, detail_fetched, created_at, updated_at
            FROM listings_old
            """
        )
        conn.execute("DROP TABLE listings_old")

    def _ensure_crawl_runs_platform(self, conn: sqlite3.Connection) -> None:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'crawl_runs'"
        ).fetchone()
        if table is None:
            return
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(crawl_runs)")]
        if "platform" not in columns:
            conn.execute("ALTER TABLE crawl_runs ADD COLUMN platform TEXT NOT NULL DEFAULT ''")

    def _rebuild_fts(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM listing_fts")
        conn.execute(
            """
            INSERT INTO listing_fts(
                listing_key, title, price, location, posted_date, description, attributes,
                seller_name, brand, size, condition
            )
            SELECT
                listing_key, title, price, location, posted_date, description, attributes,
                seller_name, brand, size, condition
            FROM listings
            """
        )


def _fts_query(query: str) -> str:
    terms = [term.replace('"', "") for term in query.split() if term.strip()]
    if not terms:
        return '""'
    return " ".join(f'"{term}"' for term in terms)
