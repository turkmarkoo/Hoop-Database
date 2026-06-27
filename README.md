# 🏀 Hoop Database

A multi-league European basketball statistics platform — web app + scraper.

## What's in this repo

| File | Description |
|------|-------------|
| `index.html` | HoopDB web app — open in any browser, no server needed |
| `scraper.py` | Main scraper for all 6 leagues |
| `scrape_browser.py` | Playwright-based browser scraper for JS-heavy sites |
| `import_helper.py` | Validates & formats scraped data for import into the app |
| `requirements.txt` | Python dependencies |
| `scrape.yml` | GitHub Actions workflow for scheduled scraping |

## Leagues covered

| League | Country | Data source |
|--------|---------|-------------|
| Euroleague | Pan-European | Official public API (api-live.euroleague.net) |
| Eurocup | Pan-European | Official public API |
| FIBA Champions League | Pan-European | Public HTML scraping |
| ABA Liga | Balkans | Public HTML scraping |
| EasyCredit BBL | Germany | Public HTML scraping |
| ACB Liga Endesa | Spain | Public HTML scraping |

## Quick start

### Web app
Open `index.html` in your browser. No server or install needed.
Use **Import** to load scraped data, or **Load Sample Data** to explore with example players.

### Scraper
```bash
pip install -r requirements.txt
python scraper.py         # scrapes all leagues (~5-15 min)
python import_helper.py   # prepares hoopdb_import_ready.json
```
Then paste `hoopdb_import_ready.json` into the web app via the Import button.

## Features

- Player profiles with stats across all 6 leagues
- Sortable/filterable player table (PTS, REB, AST, FG%, 3P%, and more)
- Head-to-head player comparison
- Advanced metrics: Efficiency Rating, True Shooting %, AST/TO ratio
- JSON + CSV import
- Persistent local storage (data survives page refresh)

## Legal

All data collected is publicly accessible statistical data for personal/research use only.
Euroleague/Eurocup data requires attribution to www.euroleague.net per their Terms & Conditions.
Not for commercial redistribution.
