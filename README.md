# Kleinanzeigen/Vinted Crawler

Local CLI for crawling public Kleinanzeigen and Vinted user listing pages and searching them with SQLite FTS.

```bash
kleinanzeigen-crawler crawl "https://www.kleinanzeigen.de/s-bestandsliste.html?userId=15172148"
kleinanzeigen-crawler crawl "https://www.vinted.de/member/44026682-elisa150620"
kleinanzeigen-crawler search "baby größe 56"
kleinanzeigen-crawler show kleinanzeigen:123456789
kleinanzeigen-crawler show vinted:9001182448
kleinanzeigen-crawler export-set newborn-girl-56 --output exports/newborn-girl-56.html
```

## GitHub Pages

The workflow in `.github/workflows/deploy-pages.yml` publishes `exports/newborn-girl-56.html` as the GitHub Pages `index.html`.

After pushing to GitHub, enable Pages with:

1. Repository `Settings` -> `Pages`
2. `Build and deployment` -> `Source` -> `GitHub Actions`
3. Run or re-run the `Deploy gallery to GitHub Pages` workflow

The crawler uses polite HTTP requests only. It stops cleanly on `403`, CAPTCHA pages, login walls, and similar blocking responses.
