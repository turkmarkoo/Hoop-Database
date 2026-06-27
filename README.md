# HoopDB Scraper

Collects publicly available player statistics from 6 European basketball
leagues for personal, non-commercial research use.

---

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the scraper (takes ~5–15 min)
python scraper.py

# 3. Prepare data for the HoopDB web app
python import_helper.py

# 4. Copy the contents of hoopdb_import_ready.json
#    Open HoopDB → click Import → paste JSON → click Import Players
```

---

## Legal notes (read before running)

| League | Data source | Terms |
|--------|-------------|-------|
| **Euroleague** | `api-live.euroleague.net` (official public Swagger API) | Non-commercial with attribution to www.euroleague.net |
| **Eurocup** | Same API, competition code `U` | Same as Euroleague |
| **FIBA CL** | Public HTML at championsleague.basketball | Public stats pages, no scraping prohibition found |
| **ABA Liga** | Public HTML at aba-liga.com | Public stats pages, no scraping prohibition found |
| **BBL** | Public HTML at easycredit-bbl.de | Public stats pages, no scraping prohibition found |
| **ACB** | Public HTML at acb.com | Public stats pages, no scraping prohibition found |

**This scraper:**
- Only collects **publicly accessible** statistical data (no login bypass)
- Identifies itself with a descriptive User-Agent string
- Adds **1.2–2.5 second delays** between every request
- Checks `robots.txt` before crawling HTML pages
- Is intended for **personal / research use only — NOT commercial redistribution**

You are responsible for reviewing each site's current Terms of Service
before running. Terms can change. If a site's ToS prohibits scraping,
do not run the relevant scraper module.

---

## Configuration (scraper.py)

```python
SEASON = "2025-26"          # target season label
REQUEST_DELAY_MIN = 1.2     # min seconds between requests
REQUEST_DELAY_MAX = 2.5     # max seconds between requests
OUTPUT_FILE = "hoopdb_players.json"
```

---

## How each league is scraped

### Euroleague & Eurocup
Uses the official public Swagger API at `api-live.euroleague.net/v2`.
This is the same API used by the open-source R package `euroleaguer` and
Python package `euroleague-api`, both published on CRAN and PyPI.

Endpoints used:
- `/v2/competitions/{code}/seasons/{season}/statistics` — all player averages
- `/v2/competitions/{code}/seasons/{season}/clubs` — team list (fallback)
- `/v2/competitions/{code}/seasons/{season}/clubs/{clubCode}/people` — player list (fallback)

### FIBA Champions League, ABA Liga, BBL, ACB
HTML scraping of public statistics pages. The scraper:
1. Fetches the teams listing page
2. Iterates each team's stats page
3. Parses HTML tables with BeautifulSoup
4. Handles both English and Spanish column names (ACB)

---

## Output format

`hoopdb_players.json` — array of player objects:

```json
[
  {
    "name": "Vasilije Micic",
    "position": "G",
    "team": "Anadolu Efes",
    "league": "Euroleague",
    "nationality": "Serbian",
    "height": "190cm",
    "age": 30,
    "img": "https://...",
    "gp": 30,
    "min": 28.8,
    "pts": 13.5,
    "reb": 3.8,
    "ast": 7.2,
    "stl": 1.6,
    "blk": 0.2,
    "to": 2.2,
    "fg_pct": 46.2,
    "three_pct": 37.5,
    "ft_pct": 82.0,
    "pir": 16.4,
    "source": "euroleaguebasketball.net API",
    "attribution": "Data from www.euroleague.net / www.eurocupbasketball.com"
  }
]
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| 0 players from a league | Site structure may have changed — check the log file |
| HTTP 429 / rate limited | Increase `REQUEST_DELAY_MIN` and `REQUEST_DELAY_MAX` |
| Euroleague API returns 404 | Season code may be wrong — update `SEASON` and the year in `el_season_code()` |
| ACB / BBL returns empty | These use heavy JS rendering — consider using Playwright for these |

---

## Playwright fallback (for JS-heavy sites)

If BBL or ACB return 0 players, install Playwright:

```bash
pip install playwright
playwright install chromium
```

Then use this snippet for a single team:

```python
from playwright.sync_api import sync_playwright

def fetch_with_playwright(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)
        page.wait_for_load_state("networkidle")
        html = page.content()
        browser.close()
        return html
```

Pass the returned HTML string to BeautifulSoup instead of `requests.get()`.
