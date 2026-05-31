from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Row

from .storage import Storage


@dataclass(frozen=True)
class CuratedItem:
    listing_key: str
    category: str
    note: str = ""
    optional: bool = False


@dataclass(frozen=True)
class ExportSet:
    slug: str
    title: str
    subtitle: str
    suggested_offer: float
    upper_range: str
    items: tuple[CuratedItem, ...]


NEWBORN_GIRL_56 = ExportSet(
    slug="newborn-girl-56",
    title="Erstausstattung Mädchen bis Größe 56",
    subtitle="Kuratierte Vinted/Kleinanzeigen-Auswahl von Elisa mit Bildern, Preisen und Paketvorschlag.",
    suggested_offer=75.0,
    upper_range="80-85 EUR",
    items=(
        CuratedItem("vinted:8611457744", "Bodies", "Kurz- und Langarmbody Set für Neugeborene"),
        CuratedItem("vinted:8271674904", "Bodies", "Wickelbody, praktisch für die ersten Wochen"),
        CuratedItem("vinted:8270397339", "Bodies", "Rosa Kurzarmbody Set"),
        CuratedItem("vinted:6447080730", "Bodies", "Rosa Wickellangarmbodys, Größe 50"),
        CuratedItem("vinted:8112366397", "Bodies", "Wickellangarmbody + Hose, 50/56"),
        CuratedItem("vinted:8112472556", "Bodies", "2 Wickellangarmbodys + Stramplerhose"),
        CuratedItem("vinted:8986726704", "Strampler", "Neuer Jumpsuit mit Herzchen"),
        CuratedItem("vinted:8970905038", "Strampler", "Günstiger Strampler mit Füßen"),
        CuratedItem("vinted:8263763524", "Strampler", "Strampler mit Füßen, Flamingo und Spitze"),
        CuratedItem("vinted:4139323575", "Strampler", "Weicher Strampler mit geschlossenen Füßchen"),
        CuratedItem("vinted:3616822449", "Strampler", "Weicher Strampler mit Füßen"),
        CuratedItem("vinted:8089313122", "Strampler", "4-teiliges Set mit Giraffenmotiv"),
        CuratedItem("vinted:9001182448", "Sets", "Set aus Shirt/Tunika und Stramplerhose, 50/56"),
        CuratedItem("vinted:8984694440", "Sets", "Langarmbody + Leggings, 50/56"),
        CuratedItem("vinted:8984658709", "Sets", "Stramplerhose + 2 Langarmshirts"),
        CuratedItem("vinted:8112405480", "Sets", "Langarmshirt + Hose"),
        CuratedItem("vinted:8089827015", "Sets", "Langarmbody + Stramplerhose"),
        CuratedItem("vinted:8270611009", "Warm/Accessoires", "Jacke/Cardigan für drüber"),
        CuratedItem("vinted:7017954755", "Warm/Accessoires", "Anti-Kratz-Handschuhe"),
        CuratedItem("vinted:6227665684", "Warm/Accessoires", "Pinke Strumpfhose 50/56"),
        CuratedItem("vinted:8978205806", "Warm/Accessoires", "Newborn Mützchen Set"),
        CuratedItem("vinted:8978057974", "Warm/Accessoires", "Newborn Mützchen Set mit Teddyohren"),
        CuratedItem("vinted:8068316527", "Optional", "Zusätzliches Newborn Mützchen", True),
        CuratedItem("vinted:8068287584", "Optional", "Zusätzliches Newborn Mützchen Set", True),
        CuratedItem("vinted:9000973880", "Optional", "Mütze/Sonnenhut + Halstuch, 0-3 Monate", True),
        CuratedItem("vinted:8281205521", "Optional", "Handmade Hose, schön aber teuer", True),
    ),
)

EXPORT_SETS = {NEWBORN_GIRL_56.slug: NEWBORN_GIRL_56}


def export_set(storage: Storage, slug: str, output: Path) -> Path:
    if slug not in EXPORT_SETS:
        available = ", ".join(sorted(EXPORT_SETS))
        raise ValueError(f"Unknown export set '{slug}'. Available: {available}")
    storage.init()
    export = EXPORT_SETS[slug]
    rows = _load_rows(storage, export)
    missing = [item.listing_key for item in export.items if item.listing_key not in rows]
    if missing:
        raise ValueError("Missing listings in database: " + ", ".join(missing))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_html(export, rows), encoding="utf-8")
    return output


def render_html(export: ExportSet, rows: dict[str, Row]) -> str:
    cards = []
    core_total = 0.0
    all_total = 0.0
    payload = []
    categories = []
    for item in export.items:
        row = rows[item.listing_key]
        price = parse_price(row["price"])
        all_total += price
        if not item.optional:
            core_total += price
        if item.category not in categories:
            categories.append(item.category)
        payload.append(
            {
                "key": row["listing_key"],
                "title": row["title"],
                "price": price,
                "priceLabel": row["price"],
                "category": item.category,
                "optional": item.optional,
            }
        )
        cards.append(_render_card(item, row, price))

    category_buttons = "\n".join(
        f'<button class="filter" data-filter="{html.escape(category)}">{html.escape(category)}</button>'
        for category in categories
    )
    selected_keys = [item.listing_key for item in export.items if not item.optional]
    data_json = html.escape(json.dumps(payload, ensure_ascii=False), quote=True)
    selected_json = html.escape(json.dumps(selected_keys), quote=True)
    message = _default_message(export, core_total)

    return f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(export.title)}</title>
  <style>
    :root {{
      --ink: #202124;
      --muted: #667085;
      --line: #d9dee7;
      --paper: #fbfaf7;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-soft: #dff5ef;
      --rose: #b4235f;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: var(--ink); background: var(--paper); }}
    header {{ padding: 28px min(5vw, 56px) 18px; border-bottom: 1px solid var(--line); background: var(--panel); }}
    h1 {{ margin: 0 0 8px; font-size: 32px; line-height: 1.1; letter-spacing: 0; }}
    .subtitle {{ margin: 0; max-width: 860px; color: var(--muted); font-size: 16px; line-height: 1.45; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(140px, 1fr)); gap: 12px; margin-top: 22px; max-width: 920px; }}
    .metric {{ border: 1px solid var(--line); background: #fff; border-radius: 8px; padding: 12px; }}
    .metric b {{ display: block; font-size: 20px; margin-bottom: 2px; }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    .layout {{ display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 22px; padding: 22px min(5vw, 56px) 48px; align-items: start; }}
    .toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
    button, .source {{ border: 1px solid var(--line); background: #fff; color: var(--ink); border-radius: 8px; padding: 9px 12px; font: inherit; cursor: pointer; text-decoration: none; }}
    button.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; min-height: 100%; }}
    .card.optional {{ border-style: dashed; }}
    .photo {{ aspect-ratio: 4 / 5; background: #eef1f4; display: block; width: 100%; object-fit: cover; }}
    .card-body {{ padding: 12px; display: flex; flex-direction: column; gap: 9px; flex: 1; }}
    .category {{ color: var(--accent); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }}
    .title {{ margin: 0; font-size: 16px; line-height: 1.25; }}
    .facts {{ display: grid; gap: 4px; color: var(--muted); font-size: 13px; }}
    .price {{ font-weight: 800; font-size: 18px; color: var(--rose); }}
    .note {{ font-size: 13px; line-height: 1.35; }}
    .actions {{ display: flex; gap: 8px; margin-top: auto; align-items: center; justify-content: space-between; }}
    label.pick {{ display: inline-flex; align-items: center; gap: 7px; font-weight: 700; }}
    aside {{ position: sticky; top: 16px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; }}
    aside h2 {{ margin: 0 0 10px; font-size: 19px; }}
    .short-metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 12px 0; }}
    .short-metrics .metric {{ padding: 10px; }}
    textarea {{ width: 100%; min-height: 220px; border: 1px solid var(--line); border-radius: 8px; padding: 10px; font: inherit; resize: vertical; }}
    .ids {{ color: var(--muted); font-size: 12px; line-height: 1.4; overflow-wrap: anywhere; }}
    @media (max-width: 980px) {{
      .layout {{ grid-template-columns: 1fr; }}
      aside {{ position: static; }}
      .summary {{ grid-template-columns: repeat(2, minmax(140px, 1fr)); }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(export.title)}</h1>
    <p class="subtitle">{html.escape(export.subtitle)}</p>
    <div class="summary">
      <div class="metric"><b>{len([i for i in export.items if not i.optional])}</b><span>Kernartikel</span></div>
      <div class="metric"><b>{format_money(core_total)}</b><span>Listenpreis Kernset</span></div>
      <div class="metric"><b>{format_money(export.suggested_offer)}</b><span>Startangebot</span></div>
      <div class="metric"><b>{html.escape(export.upper_range)}</b><span>Oberer Zielbereich</span></div>
    </div>
  </header>
  <main class="layout">
    <section>
      <nav class="toolbar">
        <button class="filter active" data-filter="all">Alle</button>
        {category_buttons}
      </nav>
      <div class="grid">
        {''.join(cards)}
      </div>
    </section>
    <aside>
      <h2>Shortlist</h2>
      <div class="short-metrics">
        <div class="metric"><b id="selected-count">0</b><span>Ausgewählt</span></div>
        <div class="metric"><b id="selected-total">0 EUR</b><span>Summe</span></div>
      </div>
      <div class="metric"><b id="offer">{format_money(export.suggested_offer)}</b><span>Vorschlag fürs Paket</span></div>
      <p class="ids" id="selected-ids"></p>
      <textarea id="message">{html.escape(message)}</textarea>
      <div class="toolbar">
        <button id="select-core">Kernset wählen</button>
        <button id="select-none">Leeren</button>
      </div>
    </aside>
  </main>
  <script data-items="{data_json}" data-selected="{selected_json}">
    const script = document.currentScript;
    const items = JSON.parse(script.dataset.items);
    const initialSelected = new Set(JSON.parse(script.dataset.selected));
    const checks = [...document.querySelectorAll('.pick input')];
    const format = value => `${{value.toFixed(2).replace('.', ',')}} EUR`;
    const update = () => {{
      const selected = checks.filter(c => c.checked).map(c => c.value);
      const selectedItems = items.filter(item => selected.includes(item.key));
      const total = selectedItems.reduce((sum, item) => sum + item.price, 0);
      const offer = Math.max(1, Math.round(total * 0.82));
      document.getElementById('selected-count').textContent = selected.length;
      document.getElementById('selected-total').textContent = format(total);
      document.getElementById('offer').textContent = `${{offer}} EUR`;
      document.getElementById('selected-ids').textContent = selected.join(', ');
      const names = selectedItems.map(item => item.title).join('; ');
      document.getElementById('message').value = `Hallo Elisa,\\n\\nich interessiere mich für ein Erstausstattungs-Paket für ein neugeborenes Mädchen. Ausgewählt hätten wir diese Artikel: ${{names}}.\\n\\nDer Einzelpreis liegt zusammen bei ca. ${{format(total)}}. Würdest du für das Paket ${{offer}} EUR machen, wenn wir es gesammelt nehmen?\\n\\nViele Grüße`;
    }};
    checks.forEach(check => {{
      check.checked = initialSelected.has(check.value);
      check.addEventListener('change', update);
    }});
    document.querySelectorAll('.filter').forEach(button => {{
      button.addEventListener('click', () => {{
        document.querySelectorAll('.filter').forEach(b => b.classList.remove('active'));
        button.classList.add('active');
        const filter = button.dataset.filter;
        document.querySelectorAll('.card').forEach(card => {{
          card.style.display = filter === 'all' || card.dataset.category === filter ? '' : 'none';
        }});
      }});
    }});
    document.getElementById('select-core').addEventListener('click', () => {{
      checks.forEach(check => check.checked = initialSelected.has(check.value));
      update();
    }});
    document.getElementById('select-none').addEventListener('click', () => {{
      checks.forEach(check => check.checked = false);
      update();
    }});
    update();
  </script>
</body>
</html>
"""


def _load_rows(storage: Storage, export: ExportSet) -> dict[str, Row]:
    rows = {}
    for item in export.items:
        row = storage.get_listing(item.listing_key)
        if row is not None:
            rows[item.listing_key] = row
    return rows


def _render_card(item: CuratedItem, row: Row, price: float) -> str:
    description = _short_description(row["description"])
    image = row["image_url"] or ""
    optional = " optional" if item.optional else ""
    return f"""
<article class="card{optional}" data-category="{html.escape(item.category)}">
  <img class="photo" src="{html.escape(image)}" alt="{html.escape(row['title'])}" loading="lazy">
  <div class="card-body">
    <div class="category">{html.escape(item.category)}{" · Optional" if item.optional else ""}</div>
    <h3 class="title">{html.escape(row['title'])}</h3>
    <div class="price">{html.escape(row['price'])}</div>
    <div class="facts">
      <span>{html.escape(row['size'] or 'Größe nicht angegeben')}</span>
      <span>{html.escape(' · '.join(v for v in [row['brand'], row['condition']] if v))}</span>
    </div>
    <div class="note"><b>{html.escape(item.note)}</b>{' — ' + html.escape(description) if description else ''}</div>
    <div class="actions">
      <label class="pick"><input type="checkbox" value="{html.escape(row['listing_key'])}" data-price="{price}"> Auswählen</label>
      <a class="source" href="{html.escape(row['url'])}" target="_blank" rel="noreferrer">Quelle</a>
    </div>
  </div>
</article>
"""


def _short_description(description: str) -> str:
    text = description.split("🛍️", 1)[0].strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > 180:
        return text[:177].rstrip() + "..."
    return text


def _default_message(export: ExportSet, total: float) -> str:
    return (
        "Hallo Elisa,\n\n"
        "ich würde gern ein kleines Erstausstattungs-Paket für ein neugeborenes Mädchen zusammenstellen. "
        "Interessant wären für uns die ausgewählten Teile in Größe 50/56 bzw. 56.\n\n"
        f"Der Einzelpreis liegt zusammen bei ca. {format_money(total)}. "
        f"Würdest du für das Paket {format_money(export.suggested_offer)} machen, wenn wir es gesammelt nehmen?\n\n"
        "Viele Grüße"
    )


def parse_price(value: str) -> float:
    match = re.search(r"\d+(?:[.,]\d+)?", value or "")
    if not match:
        return 0.0
    return float(match.group(0).replace(",", "."))


def format_money(value: float) -> str:
    if value == int(value):
        return f"{int(value)} EUR"
    return f"{value:.2f}".replace(".", ",") + " EUR"
