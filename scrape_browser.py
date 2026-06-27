#!/usr/bin/env python3
"""
EuroBall Browser Scraper
Uses Playwright (headless Chromium) to directly browse official league sites,
bypassing the IP-blocking that prevents Python requests on GitHub Actions.
Claude Haiku extracts structured transfer data from new articles.

Cost: ~$0.50-1/month  (vs ~$35/month for AI web-search approach)
Coverage: EuroCup, EuroLeague, ABA Liga, BNXT League
"""

import asyncio
import json
import hashlib
import os
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

# ── Config ────────────────────────────────────────────────────────────────────
ARCHIVE_FILE = "transfers_all.json"
NEW_FILE     = "transfers_new.json"
API_KEY      = os.environ.get("ANTHROPIC_API_KEY", "")
TODAY        = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Headline keywords that suggest a transfer / signing article
TRANSFER_KW = [
    "sign", "join", "contract", "extend", "arriv", "depart", "leav",
    "part ways", "recruit", "welcom", "new deal", "hires", "appoint",
    "quintet", " duo ", " trio ", " four ", " five ", "bolster",
    "confirm", "announce", "add to", "brings", "comes to", "coming to",
    "stays", "remains", "renew",
]

def is_transfer(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in TRANSFER_KW)

def make_id(player: str, to: str, date: str) -> str:
    key = f"{player.strip().lower()}-{to.strip().lower()}-{date}"
    return "br-" + hashlib.md5(key.encode()).hexdigest()[:12]

# ── Archive helpers ───────────────────────────────────────────────────────────
def load_archive() -> dict:
    try:
        with open(ARCHIVE_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return {item["id"]: item for item in data.get("items", [])}
    except FileNotFoundError:
        return {}

def save_archive(archive: dict) -> None:
    items = sorted(archive.values(), key=lambda x: x.get("date", ""), reverse=True)
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"generated_at": datetime.now(timezone.utc).isoformat(),
             "count": len(items), "items": items},
            f, ensure_ascii=False, indent=2,
        )

def save_new(new_items: list, archive: dict) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
    recent = [i for i in archive.values() if i.get("date", "") >= cutoff]
    merged = {i["id"]: i for i in recent}
    merged.update({i["id"]: i for i in new_items})
    items = sorted(merged.values(), key=lambda x: x.get("date", ""), reverse=True)
    with open(NEW_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"generated_at": datetime.now(timezone.utc).isoformat(),
             "count": len(items), "items": items},
            f, ensure_ascii=False, indent=2,
        )

# ── Haiku extraction ──────────────────────────────────────────────────────────
def haiku_extract(title: str, body: str, url: str, league_hint: str) -> list[dict]:
    """
    Call Claude Haiku to extract ALL transfers mentioned in one article.
    Returns a list so multi-player articles (e.g. '5 players depart') work.
    """
    if not API_KEY:
        return []

    prompt = (
        f"Today is {TODAY}. Extract ALL European basketball transfer events "
        f"mentioned in this article. One article can mention multiple players.\n\n"
        f"Return a JSON array. Each element:\n"
        f'{{"player":"Full name","pos":"PG|SG|SF|PF|C|coach|?","from":"Previous club or Free Agent or ?","to":"New club or Free Agent or ?","status":"signed|rumor|left|extended","league":"{league_hint} or the correct league","date":"YYYY-MM-DD"}}\n\n'
        f"Article title: {title}\n"
        f"Article text: {body[:900]}\n"
        f"Source URL: {url}\n\n"
        f"Rules:\n"
        f"- Only include entries with a real player or coach name\n"
        f"- date must be YYYY-MM-DD; use {TODAY} if not stated\n"
        f"- Return ONLY the JSON array, no markdown fences, no explanation"
    )

    req_body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 600,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = Request(
        "https://api.anthropic.com/v1/messages",
        data=req_body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )

    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            raw = result["content"][0]["text"].strip()
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            start, end = raw.find("["), raw.rfind("]") + 1
            if start < 0 or end <= start:
                return []
            data = json.loads(raw[start:end])
            if isinstance(data, dict):
                data = [data]
            return [d for d in data if d.get("player", "?") not in ("?", "", None)]
    except Exception as e:
        print(f"    Haiku error: {e}")
        return []


def build_items(extracted: list, article_url: str, source_name: str,
                league_fallback: str, date_fallback: str) -> list[dict]:
    """Turn Haiku output into archive-ready items, skipping already-seen IDs."""
    result = []
    for e in extracted:
        player = e.get("player", "?").strip()
        to     = e.get("to", "?").strip()
        date   = e.get("date", date_fallback) or date_fallback
        if not player or player == "?":
            continue
        item = {
            "id":          make_id(player, to, date),
            "player":      player,
            "pos":         e.get("pos", "?"),
            "from":        e.get("from", "?"),
            "to":          to,
            "status":      e.get("status", "signed"),
            "league":      e.get("league", league_fallback),
            "date":        date,
            "source_url":  article_url,
            "source_name": source_name,
        }
        result.append(item)
    return result


# ── Site scrapers ─────────────────────────────────────────────────────────────

async def scrape_euroleague_site(page, base_url: str, source_name: str,
                                  league: str, archive: dict) -> list[dict]:
    """
    EuroLeague / EuroCup news (Next.js).
    Reads the __NEXT_DATA__ feed for article list, then visits each new
    transfer article and extracts via Haiku.
    """
    new_items = []
    try:
        print(f"  Navigating to {base_url}")
        await page.goto(base_url, wait_until="networkidle", timeout=35000)

        nd = await page.evaluate("""() => {
            const el = document.getElementById('__NEXT_DATA__');
            return el ? JSON.parse(el.textContent) : null;
        }""")

        if not nd:
            print(f"  {source_name}: no __NEXT_DATA__ found")
            return new_items

        articles = (nd.get("props", {}).get("pageProps", {})
                       .get("feed", {}).get("data", []))
        print(f"  {source_name}: {len(articles)} articles in feed")

        for a in articles[:30]:
            gen_url = a.get("generatedUrl", "")
            if not gen_url:
                continue
            title      = a.get("title", "")
            date       = (a.get("publishDate", "") or TODAY)[:10]
            full_url   = "https://www.euroleaguebasketball.net" + gen_url

            # Quick filter: skip non-transfer articles
            if not is_transfer(title):
                continue

            # Use slug-based seen-check so we don't re-fetch visited articles
            slug_id = "el-seen-" + hashlib.md5(gen_url.encode()).hexdigest()[:12]
            if slug_id in archive:
                continue

            print(f"  NEW [{source_name}]: {title[:70]}")
            await page.goto(full_url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(2000)
            body = await page.evaluate("() => document.body.innerText")

            extracted = haiku_extract(title, body, full_url, league)
            items = build_items(extracted, full_url, source_name, league, date)

            for item in items:
                if item["id"] not in archive:
                    archive[item["id"]] = item
                    new_items.append(item)
                    print(f"    ✓ {item['player']} → {item['to']} ({item['status']})")

            # Mark slug as visited even if no structured data extracted
            archive[slug_id] = {"id": slug_id, "_visited": True, "date": date}
            await page.wait_for_timeout(500)

    except Exception as e:
        print(f"  {source_name} error: {e}")

    return new_items


async def scrape_aba_liga(page, archive: dict) -> list[dict]:
    """ABA Liga news page — JS-rendered, blocked for Python HTTP but fine in browser."""
    new_items = []
    try:
        print("  Navigating to aba-liga.com/news")
        await page.goto("https://www.aba-liga.com/news/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        links = await page.evaluate("""() => {
            const seen = new Set();
            return [...document.querySelectorAll('a[href*="/news/"]')]
                .map(a => {
                    const container = a.closest('tr,div,li,article,td');
                    return {
                        url:  a.href,
                        text: (container?.innerText || a.textContent || '').trim().substring(0, 250)
                    };
                })
                .filter(l => /\/news\/\d+\//.test(l.url))
                .filter(l => { if (seen.has(l.url)) return false; seen.add(l.url); return true; });
        }""")

        transfer_links = [l for l in links if is_transfer(l["text"]) or is_transfer(l["url"])]
        print(f"  ABA Liga: {len(transfer_links)} transfer articles on page")

        for link in transfer_links[:25]:
            article_url = link["url"]
            slug_id = "aba-seen-" + hashlib.md5(article_url.encode()).hexdigest()[:12]
            if slug_id in archive:
                continue

            print(f"  NEW [ABA Liga]: {article_url.rstrip('/').split('/')[-2][:55]}")
            await page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2500)

            title = await page.title()
            body  = await page.evaluate("() => document.body.innerText")

            # ABA Liga date format: "Monday, 23. June 2026 at 16:54"
            date_match = None
            import re
            dm = re.search(r'(\d{1,2})\.\s+(\w+)\s+(\d{4})', body)
            MONTHS = {"january":"01","february":"02","march":"03","april":"04",
                      "may":"05","june":"06","july":"07","august":"08",
                      "september":"09","october":"10","november":"11","december":"12"}
            if dm:
                day, mon, yr = dm.group(1).zfill(2), MONTHS.get(dm.group(2).lower(),"01"), dm.group(3)
                date_match = f"{yr}-{mon}-{day}"

            extracted = haiku_extract(title, body, article_url, "ABA League")
            items = build_items(extracted, article_url, "ABA Liga Official",
                                "ABA League", date_match or TODAY)

            for item in items:
                if item["id"] not in archive:
                    archive[item["id"]] = item
                    new_items.append(item)
                    print(f"    ✓ {item['player']} → {item['to']} ({item['status']})")

            archive[slug_id] = {"id": slug_id, "_visited": True, "date": date_match or TODAY}
            await page.wait_for_timeout(400)

    except Exception as e:
        print(f"  ABA Liga error: {e}")

    return new_items


async def scrape_bnxt(page, archive: dict) -> list[dict]:
    """BNXT League news page — JS-rendered, ~3-4s render wait needed."""
    new_items = []
    try:
        print("  Navigating to bnxtleague.com/en/news")
        await page.goto("https://bnxtleague.com/en/news", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)   # BNXT needs longer to render

        links = await page.evaluate("""() => {
            const SKIP = ['format','where-to-watch','youtopia','bnxt-cares'];
            const seen = new Set();
            return [...document.querySelectorAll('a[href*="/newsvideo/"]')]
                .map(a => {
                    const container = a.closest('div,li,article,section');
                    return {
                        url:  a.href,
                        text: (container?.innerText || a.textContent || '').trim().substring(0, 250)
                    };
                })
                .filter(l => !SKIP.some(s => l.url.includes(s)))
                .filter(l => { if (seen.has(l.url)) return false; seen.add(l.url); return true; });
        }""")

        transfer_links = [l for l in links if is_transfer(l["text"]) or is_transfer(l["url"])]
        print(f"  BNXT: {len(transfer_links)} transfer articles on page")

        for link in transfer_links[:25]:
            article_url = link["url"]
            slug_id = "bnxt-seen-" + hashlib.md5(article_url.encode()).hexdigest()[:12]
            if slug_id in archive:
                continue

            print(f"  NEW [BNXT]: {article_url.rstrip('/').split('/')[-1][:55]}")
            await page.goto(article_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(4000)   # BNXT individual pages also slow

            title   = await page.title()
            body    = await page.evaluate("() => document.body.innerText")

            # Get date from <time> element
            date_str = await page.evaluate("""() => {
                const t = document.querySelector('time,[datetime]');
                return t ? (t.getAttribute('datetime') || '').slice(0, 10) : '';
            }""") or TODAY

            extracted = haiku_extract(title, body, article_url, "BNXT")
            items = build_items(extracted, article_url, "BNXT League Official", "BNXT", date_str)

            for item in items:
                if item["id"] not in archive:
                    archive[item["id"]] = item
                    new_items.append(item)
                    print(f"    ✓ {item['player']} → {item['to']} ({item['status']})")

            archive[slug_id] = {"id": slug_id, "_visited": True, "date": date_str}
            await page.wait_for_timeout(400)

    except Exception as e:
        print(f"  BNXT error: {e}")

    return new_items


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    from playwright.async_api import async_playwright

    print(f"EuroBall Browser Scraper — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Sites: EuroCup, EuroLeague, ABA Liga, BNXT\n")

    archive   = load_archive()
    new_items = []
    total     = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        page = await context.new_page()

        sources = [
            ("EuroCup",    lambda: scrape_euroleague_site(
                page, "https://www.euroleaguebasketball.net/eurocup/news/",
                "EuroCup Official", "EuroCup", archive)),
            ("EuroLeague", lambda: scrape_euroleague_site(
                page, "https://www.euroleaguebasketball.net/euroleague/news/",
                "EuroLeague Official", "EuroLeague", archive)),
            ("ABA Liga",   lambda: scrape_aba_liga(page, archive)),
            ("BNXT",       lambda: scrape_bnxt(page, archive)),
        ]

        for name, scrape_fn in sources:
            print(f"\n── {name} " + "─" * (40 - len(name)))
            try:
                items = await scrape_fn()
                new_items.extend(items)
                total += len(items)
                print(f"  → {len(items)} new transfer(s)")
            except Exception as e:
                print(f"  → FAILED: {e}")

        await browser.close()

    print(f"\n{'='*50}")
    print(f"Browser scraper total: {total} new | Archive: {len(archive)}")
    save_archive(archive)
    save_new(new_items, archive)


if __name__ == "__main__":
    asyncio.run(main())
