from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .crawler import Crawler
from .export_sets import EXPORT_SETS, export_set
from .storage import Storage

app = typer.Typer(help="Crawl and search public Kleinanzeigen/Vinted user listings locally.")
console = Console(width=200)


@app.command()
def crawl(
    url: str = typer.Argument(..., help="Kleinanzeigen or Vinted user inventory/profile URL."),
    db: Path = typer.Option(Path("kleinanzeigen.db"), "--db", help="SQLite database path."),
    delay: float = typer.Option(2.0, "--delay", min=0.0, help="Delay between requests in seconds."),
    max_pages: int | None = typer.Option(None, "--max-pages", min=1, help="Maximum listing pages to crawl."),
    details: bool = typer.Option(True, "--details/--no-details", help="Fetch listing detail pages."),
) -> None:
    """Crawl a public user inventory URL into the local database."""
    storage = Storage(db)
    result = Crawler(storage, delay=delay).crawl(url, max_pages=max_pages, details=details)
    if result.status == "success":
        console.print(
            f"[green]Crawl complete[/green]: {result.listings_found} listings from {result.pages_scanned} pages."
        )
        raise typer.Exit(0)
    console.print(f"[red]Crawl {result.status}[/red]: {result.error_summary}")
    console.print(f"Saved partial data: {result.listings_found} listings from {result.pages_scanned} pages.")
    raise typer.Exit(2 if result.status == "blocked" else 1)


@app.command()
def search(
    query: str = typer.Argument(..., help="Full-text query, e.g. 'baby größe 56'."),
    db: Path = typer.Option(Path("kleinanzeigen.db"), "--db", help="SQLite database path."),
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum results."),
) -> None:
    """Search crawled listings."""
    storage = Storage(db)
    storage.init()
    rows = storage.search(query, limit)
    if not rows:
        console.print("[yellow]No matches found.[/yellow]")
        raise typer.Exit(0)
    table = Table(show_lines=False)
    for column in ["ID", "Platform", "Title", "Price", "Size", "Brand", "Location", "Date", "Match", "URL"]:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(
            row["listing_key"],
            row["platform"],
            row["title"],
            row["price"],
            row["size"],
            row["brand"],
            row["location"],
            row["posted_date"],
            row["snippet"] or "",
            row["url"],
        )
    console.print(table)


@app.command()
def show(
    listing_id: str = typer.Argument(..., help="Listing key, e.g. kleinanzeigen:123 or vinted:456."),
    db: Path = typer.Option(Path("kleinanzeigen.db"), "--db", help="SQLite database path."),
) -> None:
    """Show one listing from the local database."""
    storage = Storage(db)
    storage.init()
    row = storage.get_listing(listing_id)
    if row is None:
        console.print(f"[red]Listing not found:[/red] {listing_id}")
        raise typer.Exit(1)
    console.print(f"[bold]{row['title']}[/bold]")
    console.print(f"{row['listing_key']} | {row['platform']}")
    console.print(f"{row['price']} | {row['location']} | {row['posted_date']}")
    if row["brand"] or row["size"] or row["condition"]:
        console.print(f"{row['brand']} | {row['size']} | {row['condition']}")
    console.print(row["url"])
    if row["attributes"]:
        console.print("\n[bold]Attributes[/bold]")
        console.print(row["attributes"])
    if row["description"]:
        console.print("\n[bold]Description[/bold]")
        console.print(row["description"])


@app.command("export-set")
def export_curated_set(
    slug: str = typer.Argument("newborn-girl-56", help="Curated export set slug."),
    output: Path = typer.Option(Path("exports/newborn-girl-56.html"), "--output", "-o", help="HTML output path."),
    db: Path = typer.Option(Path("kleinanzeigen.db"), "--db", help="SQLite database path."),
) -> None:
    """Export a curated local HTML gallery."""
    if slug not in EXPORT_SETS:
        console.print(f"[red]Unknown set:[/red] {slug}")
        console.print("Available: " + ", ".join(sorted(EXPORT_SETS)))
        raise typer.Exit(1)
    try:
        path = export_set(Storage(db), slug, output)
    except ValueError as exc:
        console.print(f"[red]Export failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]Export complete:[/green] {path}")
