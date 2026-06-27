"""
HoopDB Basketball Statistics Scraper
=====================================
Collects publicly available player statistics from 6 European basketball leagues
for personal, non-commercial research purposes.

LEGAL NOTES (read before running):
  - Euroleague/Eurocup: Uses their public Swagger API (api-live.euroleague.net).
    Stats may only be used for non-commercial purposes with attribution to euroleague.net
    per their Terms & Conditions (https://id.euroleague.net/terms).
  - FIBA Champions League: Scrapes public HTML pages. No robots.txt restriction found.
  - ABA Liga: Scrapes public HTML pages. No robots.txt restriction found.
  - BBL (EasyCredit): Scrapes public HTML pages. No robots.txt restriction found.
  - ACB (Spain): Scrapes public HTML pages. No robots.txt restriction found.

  All data collected is:
    * Publicly accessible (no login bypass, no paywall circumvention)
    * Statistical/factual (not copyrighted creative content)
    * For personal/research use only — NOT for commercial redistribution
    * Rate-limited to avoid server impact (1-2s delays between requests)

  You are responsible for reviewing each site's current ToS before running.
  This scraper does NOT bypass any technical access controls.
"""

import requests
import json
import time
import random
import re
import sys
import os
from datetime import datetime
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Installing required packages...")
    os.system(f"{sys.executable} -m pip install beautifulsoup4 requests lxml --quiet")
    from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

OUTPUT_FILE = "hoopdb_players.json"
LOG_FILE = "scraper_log.txt"
SEASON = "2025-26"  # Change to target a different season

HEADERS = {
    "User-Agent": "HoopDB-Scraper/1.0 (personal basketball stats research; non-commercial)",
    "Accept": "application/json, text/html,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

REQUEST_DELAY_MIN = 1.2   # seconds between requests
REQUEST_DELAY_MAX = 2.5   # seconds between requests (randomised)

# ─────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def sleep():
    t = random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)
    time.sleep(t)

def get(url: str, params=None, headers=None, timeout=15) -> requests.Response | None:
    h = {**HEADERS, **(headers or {})}
    try:
        resp = requests.get(url, params=params, headers=h, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.HTTPError as e:
        log(f"  HTTP {e.response.status_code} for {url}")
        return None
    except Exception as e:
        log(f"  Request failed for {url}: {e}")
        return None

def robots_allows(url: str) -> bool:
    """Check robots.txt for the given URL. Returns True if allowed or robots.txt unavailable."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        allowed = rp.can_fetch(HEADERS["User-Agent"], url)
        if not allowed:
            log(f"  robots.txt DISALLOWS {url} — skipping")
        return allowed
    except Exception:
        return True  # If robots.txt unreachable, proceed with caution

def safe_float(val) -> float | None:
    try:
        return float(str(val).replace(",", ".").strip()) if val not in (None, "", "-", "—") else None
    except (ValueError, TypeError):
        return None

def safe_int(val) -> int | None:
    try:
        return int(str(val).strip()) if val not in (None, "", "-", "—") else None
    except (ValueError, TypeError):
        return None

# ─────────────────────────────────────────────
# 1. Euroleague & Eurocup — Public API
# ─────────────────────────────────────────────
# Uses the official Euroleague Swagger API (api-live.euroleague.net).
# This is a documented public API used by the R package 'euroleaguer' and the
# Python package 'euroleague-api'. No authentication required for stats endpoints.
# Attribution required per ToS: www.euroleague.net / www.eurocupbasketball.com
# ─────────────────────────────────────────────

EL_API_BASE = "https://api-live.euroleague.net/v2"
EL_COMPETITIONS = {
    "Euroleague": "E",   # competition_code E = Euroleague
    "Eurocup":    "U",   # competition_code U = Eurocup
}

def el_season_code(league_code: str, year: int = 2025) -> str:
    """E.g. 'E2025' for Euroleague 2025-26 season."""
    return f"{league_code}{year}"

def fetch_el_teams(competition_code: str, season_code: str) -> list[dict]:
    """Fetch all teams for a Euroleague/Eurocup season."""
    url = f"{EL_API_BASE}/competitions/{competition_code}/seasons/{season_code}/clubs"
    resp = get(url)
    if not resp:
        return []
    try:
        data = resp.json()
        return data.get("data", data) if isinstance(data, dict) else data
    except Exception as e:
        log(f"  Could not parse teams: {e}")
        return []

def fetch_el_team_players(competition_code: str, season_code: str, club_code: str) -> list[dict]:
    """Fetch player statistics for a specific team."""
    url = f"{EL_API_BASE}/competitions/{competition_code}/seasons/{season_code}/clubs/{club_code}/people"
    resp = get(url)
    sleep()
    if not resp:
        return []
    try:
        data = resp.json()
        return data.get("data", data) if isinstance(data, dict) else data
    except Exception as e:
        log(f"  Could not parse players for {club_code}: {e}")
        return []

def fetch_el_player_stats(competition_code: str, season_code: str) -> list[dict]:
    """Fetch season averages for all players. Returns normalised player dicts."""
    url = f"{EL_API_BASE}/competitions/{competition_code}/seasons/{season_code}/statistics"
    params = {"statisticMode": "averages", "limit": 400, "offset": 0}
    resp = get(url, params=params)
    sleep()
    if not resp:
        return []
    try:
        raw = resp.json()
        rows = raw.get("data", raw) if isinstance(raw, dict) else raw
        return rows
    except Exception as e:
        log(f"  Could not parse stats: {e}")
        return []

def map_el_player(row: dict, league: str) -> dict:
    """Normalise Euroleague API player stat row to HoopDB schema."""
    p = row.get("player", row)
    s = row.get("stats", row)
    return {
        "name":        f"{p.get('name', '')} {p.get('surname', '')}".strip() or p.get('fullName', ''),
        "position":    p.get("positionName", p.get("position", "")),
        "team":        row.get("club", {}).get("name", row.get("clubName", "")),
        "team_code":   row.get("club", {}).get("code", row.get("clubCode", "")),
        "league":      league,
        "nationality": p.get("country", {}).get("name", ""),
        "height":      str(p.get("height", "")) + "cm" if p.get("height") else "",
        "age":         safe_int(p.get("age")),
        "img":         p.get("images", {}).get("headshot", p.get("imageUrl", "")),
        "gp":          safe_int(s.get("gamesPlayed", s.get("gp"))),
        "min":         safe_float(s.get("minutesPerGame", s.get("min"))),
        "pts":         safe_float(s.get("pointsPerGame", s.get("pts"))),
        "reb":         safe_float(s.get("totalReboundsPerGame", s.get("reb"))),
        "ast":         safe_float(s.get("assistsPerGame", s.get("ast"))),
        "stl":         safe_float(s.get("stealsPerGame", s.get("stl"))),
        "blk":         safe_float(s.get("blocksPerGame", s.get("blk"))),
        "to":          safe_float(s.get("turnoversPerGame", s.get("to"))),
        "fg_pct":      safe_float(s.get("fieldGoalsPercentage", s.get("fg_pct"))),
        "three_pct":   safe_float(s.get("threePointersPercentage", s.get("three_pct"))),
        "ft_pct":      safe_float(s.get("freeThrowsPercentage", s.get("ft_pct"))),
        "pir":         safe_float(s.get("performanceIndexRating", s.get("pir"))),
        "source":      "euroleaguebasketball.net API",
        "attribution": "Data from www.euroleague.net / www.eurocupbasketball.com",
    }

def scrape_euroleague(league_name: str, competition_code: str) -> list[dict]:
    log(f"\n{'='*50}")
    log(f"Fetching {league_name} via public API...")
    season_code = el_season_code(competition_code, 2025)

    # Try /statistics endpoint first (all players at once)
    stats = fetch_el_player_stats(competition_code, season_code)
    if stats:
        players = [map_el_player(r, league_name) for r in stats if r]
        players = [p for p in players if p["name"]]
        log(f"  ✓ {len(players)} players via statistics endpoint")
        return players

    # Fallback: enumerate teams then players
    log("  Falling back to team-by-team fetch...")
    teams = fetch_el_teams(competition_code, season_code)
    log(f"  Found {len(teams)} teams")
    all_players = []
    for team in teams:
        club_code = team.get("code", team.get("clubCode", ""))
        club_name = team.get("name", team.get("clubName", ""))
        if not club_code:
            continue
        log(f"    Fetching {club_name}...")
        rows = fetch_el_team_players(competition_code, season_code, club_code)
        for r in rows:
            r.setdefault("club", {"name": club_name, "code": club_code})
            all_players.append(map_el_player(r, league_name))
    log(f"  ✓ {len(all_players)} players via team endpoint")
    return all_players

# ─────────────────────────────────────────────
# 2. FIBA Champions League — HTML scraping
# ─────────────────────────────────────────────

FIBA_CL_BASE = "https://www.championsleague.basketball"
FIBA_CL_TEAMS_URL = f"{FIBA_CL_BASE}/en/teams"

def fetch_fiba_teams() -> list[dict]:
    resp = get(FIBA_CL_TEAMS_URL)
    sleep()
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    teams = []
    # Team links are typically in /en/teams/<slug>
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/en/teams/" in href and href not in [t.get("url") for t in teams]:
            name = a.get_text(strip=True)
            if name and len(name) > 2:
                teams.append({"name": name, "url": FIBA_CL_BASE + href if href.startswith("/") else href})
    # Deduplicate
    seen = set()
    unique = []
    for t in teams:
        if t["url"] not in seen:
            seen.add(t["url"])
            unique.append(t)
    return unique

def fetch_fiba_team_stats(team: dict) -> list[dict]:
    stats_url = team["url"].rstrip("/") + "#statistics"
    resp = get(stats_url.replace("#statistics", ""))
    sleep()
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    players = []

    # Look for statistics tables
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th","td"])]
        if not any(h in headers for h in ["pts", "points", "reb", "rebounds", "ast"]):
            continue

        col = {h: i for i, h in enumerate(headers)}
        for row in rows[1:]:
            cells = row.find_all(["td","th"])
            if len(cells) < 3:
                continue
            try:
                name_cell = cells[col.get("player", col.get("name", 0))]
                name = name_cell.get_text(strip=True)
                img_tag = name_cell.find("img")
                img = img_tag["src"] if img_tag and img_tag.get("src") else ""
                players.append({
                    "name":        name,
                    "team":        team["name"],
                    "league":      "FIBA CL",
                    "position":    cells[col["pos"]].get_text(strip=True) if "pos" in col else "",
                    "img":         img,
                    "gp":          safe_int(cells[col["gp"]].get_text(strip=True)) if "gp" in col else None,
                    "min":         safe_float(cells[col.get("min", col.get("minutes", -1))].get_text(strip=True)) if col.get("min") is not None else None,
                    "pts":         safe_float(cells[col.get("pts", col.get("points", -1))].get_text(strip=True)) if "pts" in col or "points" in col else None,
                    "reb":         safe_float(cells[col.get("reb", col.get("rebounds", -1))].get_text(strip=True)) if "reb" in col or "rebounds" in col else None,
                    "ast":         safe_float(cells[col.get("ast", col.get("assists", -1))].get_text(strip=True)) if "ast" in col or "assists" in col else None,
                    "stl":         safe_float(cells[col.get("stl", col.get("steals", -1))].get_text(strip=True)) if "stl" in col or "steals" in col else None,
                    "blk":         safe_float(cells[col.get("blk", col.get("blocks", -1))].get_text(strip=True)) if "blk" in col or "blocks" in col else None,
                    "fg_pct":      safe_float(cells[col.get("fg%", col.get("fg_pct", -1))].get_text(strip=True)) if "fg%" in col or "fg_pct" in col else None,
                    "three_pct":   safe_float(cells[col.get("3p%", col.get("three_pct", -1))].get_text(strip=True)) if "3p%" in col or "three_pct" in col else None,
                    "ft_pct":      safe_float(cells[col.get("ft%", col.get("ft_pct", -1))].get_text(strip=True)) if "ft%" in col or "ft_pct" in col else None,
                    "source":      stats_url,
                })
            except (IndexError, KeyError):
                continue
    return players

def scrape_fiba_cl() -> list[dict]:
    log(f"\n{'='*50}")
    log("Fetching FIBA Champions League...")
    if not robots_allows(FIBA_CL_TEAMS_URL):
        return []
    teams = fetch_fiba_teams()
    log(f"  Found {len(teams)} teams")
    all_players = []
    for i, team in enumerate(teams):
        log(f"  [{i+1}/{len(teams)}] {team['name']}...")
        players = fetch_fiba_team_stats(team)
        all_players.extend(players)
    log(f"  ✓ {len(all_players)} players")
    return all_players

# ─────────────────────────────────────────────
# 3. ABA Liga — HTML scraping
# ─────────────────────────────────────────────

ABA_BASE = "https://www.aba-liga.com"
ABA_TEAMS_URL = f"{ABA_BASE}/teams"

def fetch_aba_teams() -> list[dict]:
    resp = get(ABA_TEAMS_URL)
    sleep()
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    teams = []
    # ABA team URLs pattern: /team/<id>/<season>/<round>/<home_away>/<name>/
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r".*/team/\d+/", href):
            full = ABA_BASE + href if href.startswith("/") else href
            if full not in seen:
                seen.add(full)
                name = a.get_text(strip=True)
                if name:
                    teams.append({"name": name, "url": full})
    return teams

def fetch_aba_team_stats(team: dict) -> list[dict]:
    resp = get(team["url"])
    sleep()
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    players = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [th.get_text(strip=True).upper() for th in rows[0].find_all(["th","td"])]
        if not any(h in headers for h in ["PTS", "REB", "AST", "MIN"]):
            continue

        col = {h: i for i, h in enumerate(headers)}
        for row in rows[1:]:
            cells = row.find_all(["td","th"])
            if len(cells) < 4:
                continue
            try:
                # Try first few cells for name
                name = ""
                img = ""
                for c in cells[:3]:
                    txt = c.get_text(strip=True)
                    img_tag = c.find("img")
                    if img_tag:
                        img = img_tag.get("src", "")
                    if txt and len(txt) > 3 and not txt.isdigit():
                        name = txt
                        break

                if not name:
                    continue

                def gcell(key, aliases=[]):
                    for k in [key] + aliases:
                        if k in col:
                            return cells[col[k]].get_text(strip=True) if col[k] < len(cells) else None
                    return None

                players.append({
                    "name":      name,
                    "team":      team["name"],
                    "league":    "ABA",
                    "position":  gcell("POS") or "",
                    "img":       img,
                    "gp":        safe_int(gcell("GP", ["G"])),
                    "min":       safe_float(gcell("MIN", ["MPG"])),
                    "pts":       safe_float(gcell("PTS", ["PPG"])),
                    "reb":       safe_float(gcell("REB", ["RPG"])),
                    "ast":       safe_float(gcell("AST", ["APG"])),
                    "stl":       safe_float(gcell("STL", ["SPG"])),
                    "blk":       safe_float(gcell("BLK", ["BPG"])),
                    "to":        safe_float(gcell("TO", ["TPG"])),
                    "fg_pct":    safe_float(gcell("FG%")),
                    "three_pct": safe_float(gcell("3P%", ["3PT%"])),
                    "ft_pct":    safe_float(gcell("FT%")),
                    "source":    team["url"],
                })
            except (IndexError, KeyError):
                continue
    return players

def scrape_aba() -> list[dict]:
    log(f"\n{'='*50}")
    log("Fetching ABA Liga...")
    if not robots_allows(ABA_TEAMS_URL):
        return []
    teams = fetch_aba_teams()
    log(f"  Found {len(teams)} teams")
    all_players = []
    for i, team in enumerate(teams):
        log(f"  [{i+1}/{len(teams)}] {team['name']}...")
        players = fetch_aba_team_stats(team)
        all_players.extend(players)
    log(f"  ✓ {len(all_players)} players")
    return all_players

# ─────────────────────────────────────────────
# 4. Germany EasyCredit BBL — HTML scraping
# ─────────────────────────────────────────────

BBL_BASE = "https://www.easycredit-bbl.de"
BBL_TEAMS_URL = f"{BBL_BASE}/teams"

def fetch_bbl_teams() -> list[dict]:
    resp = get(BBL_TEAMS_URL)
    sleep()
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    teams = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.match(r".*/teams/\d+", href):
            full = BBL_BASE + href if href.startswith("/") else href
            if full not in seen:
                seen.add(full)
                name = a.get_text(strip=True) or href.split("/")[-1]
                teams.append({"name": name, "url": full})
    return teams

def fetch_bbl_team_stats(team: dict) -> list[dict]:
    resp = get(team["url"])
    sleep()
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    players = []

    # BBL uses data-driven tables or JSON embedded in page
    # Try embedded JSON first
    scripts = soup.find_all("script")
    for script in scripts:
        txt = script.string or ""
        if "playerStats" in txt or '"pts"' in txt or '"points"' in txt:
            try:
                # Extract JSON-like data
                m = re.search(r'\{.*"players".*\}', txt, re.DOTALL)
                if m:
                    data = json.loads(m.group())
                    for p in data.get("players", []):
                        players.append({
                            "name":    p.get("name", ""),
                            "team":    team["name"],
                            "league":  "BBL",
                            "position": p.get("position", ""),
                            "img":     p.get("image", p.get("img", "")),
                            "gp":      safe_int(p.get("gamesPlayed", p.get("gp"))),
                            "pts":     safe_float(p.get("pointsPerGame", p.get("pts"))),
                            "reb":     safe_float(p.get("reboundsPerGame", p.get("reb"))),
                            "ast":     safe_float(p.get("assistsPerGame", p.get("ast"))),
                            "min":     safe_float(p.get("minutesPerGame", p.get("min"))),
                            "fg_pct":  safe_float(p.get("fieldGoalPct", p.get("fg_pct"))),
                            "source":  team["url"],
                        })
                    if players:
                        return players
            except Exception:
                pass

    # Fallback: HTML table parse
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [th.get_text(strip=True).upper() for th in rows[0].find_all(["th","td"])]
        if not any(h in headers for h in ["PTS", "REB", "MIN"]):
            continue
        col = {h: i for i, h in enumerate(headers)}
        for row in rows[1:]:
            cells = row.find_all(["td","th"])
            if len(cells) < 3:
                continue
            try:
                name = ""
                img = ""
                for c in cells[:4]:
                    t = c.get_text(strip=True)
                    ig = c.find("img")
                    if ig:
                        img = ig.get("src", "")
                    if t and len(t) > 3 and not t.isdigit():
                        name = t
                        break
                if not name:
                    continue
                def g(k, a=[]):
                    for key in [k]+a:
                        if key in col and col[key] < len(cells):
                            return cells[col[key]].get_text(strip=True)
                    return None
                players.append({
                    "name": name, "team": team["name"], "league": "BBL",
                    "img": img, "source": team["url"],
                    "gp": safe_int(g("GP")), "min": safe_float(g("MIN")),
                    "pts": safe_float(g("PTS")), "reb": safe_float(g("REB")),
                    "ast": safe_float(g("AST")), "stl": safe_float(g("STL")),
                    "blk": safe_float(g("BLK")), "fg_pct": safe_float(g("FG%")),
                    "three_pct": safe_float(g("3P%")), "ft_pct": safe_float(g("FT%")),
                })
            except (IndexError, KeyError):
                continue
    return players

def scrape_bbl() -> list[dict]:
    log(f"\n{'='*50}")
    log("Fetching BBL (EasyCredit)...")
    if not robots_allows(BBL_TEAMS_URL):
        return []
    teams = fetch_bbl_teams()
    log(f"  Found {len(teams)} teams")
    all_players = []
    for i, team in enumerate(teams):
        log(f"  [{i+1}/{len(teams)}] {team['name']}...")
        players = fetch_bbl_team_stats(team)
        all_players.extend(players)
    log(f"  ✓ {len(all_players)} players")
    return all_players

# ─────────────────────────────────────────────
# 5. Spain ACB — HTML scraping
# ─────────────────────────────────────────────

ACB_BASE = "https://www.acb.com"
ACB_TEAMS_URL = f"{ACB_BASE}/es/liga/equipos"

def fetch_acb_teams() -> list[dict]:
    resp = get(ACB_TEAMS_URL)
    sleep()
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    teams = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/liga/equipos/" in href or "/es/liga/equipos/" in href:
            full = ACB_BASE + href if href.startswith("/") else href
            if "estadisticas" not in full and full not in seen:
                seen.add(full)
                name = a.get_text(strip=True)
                if name and len(name) > 2:
                    teams.append({"name": name, "url": full + "/estadisticas" if not full.endswith("estadisticas") else full})
    return teams

def fetch_acb_team_stats(team: dict) -> list[dict]:
    resp = get(team["url"])
    sleep()
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    players = []

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [th.get_text(strip=True).upper() for th in rows[0].find_all(["th","td"])]
        if not any(h in headers for h in ["PTS", "REB", "MIN", "P.MARC", "PUNTOS"]):
            continue
        col = {h: i for i, h in enumerate(headers)}

        # ACB uses Spanish column names
        pts_key  = next((k for k in col if k in ["PTS","P.MARC","PUNTOS"]), None)
        reb_key  = next((k for k in col if k in ["REB","REB.TOT","REBOTES"]), None)
        ast_key  = next((k for k in col if k in ["AST","ASIS","ASISTENCIAS"]), None)
        min_key  = next((k for k in col if k in ["MIN","MINUTOS"]), None)
        gp_key   = next((k for k in col if k in ["PJ","GP","PARTIDOS"]), None)
        stl_key  = next((k for k in col if k in ["REC","STL","ROBOS"]), None)
        blk_key  = next((k for k in col if k in ["TAP","BLK","TAPONES"]), None)
        fg_key   = next((k for k in col if k in ["TC%","FG%","% TC"]), None)
        t3_key   = next((k for k in col if k in ["T3%","3P%","% T3"]), None)
        ft_key   = next((k for k in col if k in ["TL%","FT%","% TL"]), None)

        for row in rows[1:]:
            cells = row.find_all(["td","th"])
            if len(cells) < 4:
                continue
            try:
                name = ""
                img = ""
                for c in cells[:4]:
                    t = c.get_text(strip=True)
                    ig = c.find("img")
                    if ig:
                        img = ig.get("src", "")
                    if t and len(t) > 3 and not t.isdigit() and "." not in t:
                        name = t
                        break
                if not name:
                    continue
                def gv(key):
                    if key and key in col and col[key] < len(cells):
                        return cells[col[key]].get_text(strip=True)
                    return None
                players.append({
                    "name": name, "team": team["name"], "league": "ACB",
                    "img": img, "source": team["url"],
                    "gp":        safe_int(gv(gp_key)),
                    "min":       safe_float(gv(min_key)),
                    "pts":       safe_float(gv(pts_key)),
                    "reb":       safe_float(gv(reb_key)),
                    "ast":       safe_float(gv(ast_key)),
                    "stl":       safe_float(gv(stl_key)),
                    "blk":       safe_float(gv(blk_key)),
                    "fg_pct":    safe_float(gv(fg_key)),
                    "three_pct": safe_float(gv(t3_key)),
                    "ft_pct":    safe_float(gv(ft_key)),
                    "position":  gv("POS") or gv("POSICION") or "",
                })
            except (IndexError, KeyError):
                continue
    return players

def scrape_acb() -> list[dict]:
    log(f"\n{'='*50}")
    log("Fetching ACB (Spain)...")
    if not robots_allows(ACB_TEAMS_URL):
        return []
    teams = fetch_acb_teams()
    log(f"  Found {len(teams)} teams")
    all_players = []
    for i, team in enumerate(teams):
        log(f"  [{i+1}/{len(teams)}] {team['name']}...")
        players = fetch_acb_team_stats(team)
        all_players.extend(players)
    log(f"  ✓ {len(all_players)} players")
    return all_players

# ─────────────────────────────────────────────
# Merge & deduplicate
# ─────────────────────────────────────────────

def merge_and_save(all_players: list[dict]) -> None:
    seen = {}
    for p in all_players:
        key = f"{p.get('name','').lower().strip()}|{p.get('league','')}"
        if key not in seen:
            seen[key] = p
        else:
            # Prefer record with more filled fields
            existing = seen[key]
            filled_new = sum(1 for v in p.values() if v is not None and v != "")
            filled_old = sum(1 for v in existing.values() if v is not None and v != "")
            if filled_new > filled_old:
                seen[key] = p

    result = list(seen.values())
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    log(f"\n✓ Saved {len(result)} unique players to {OUTPUT_FILE}")
    return result

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    log("="*60)
    log("HoopDB Scraper — personal/research use only, non-commercial")
    log(f"Season: {SEASON}")
    log("="*60)

    all_players = []

    # 1. Euroleague (public API)
    try:
        el_players = scrape_euroleague("Euroleague", "E")
        all_players.extend(el_players)
    except Exception as e:
        log(f"Euroleague failed: {e}")

    # 2. Eurocup (public API)
    try:
        ec_players = scrape_euroleague("Eurocup", "U")
        all_players.extend(ec_players)
    except Exception as e:
        log(f"Eurocup failed: {e}")

    # 3. FIBA Champions League (HTML)
    try:
        fiba_players = scrape_fiba_cl()
        all_players.extend(fiba_players)
    except Exception as e:
        log(f"FIBA CL failed: {e}")

    # 4. ABA Liga (HTML)
    try:
        aba_players = scrape_aba()
        all_players.extend(aba_players)
    except Exception as e:
        log(f"ABA failed: {e}")

    # 5. BBL Germany (HTML)
    try:
        bbl_players = scrape_bbl()
        all_players.extend(bbl_players)
    except Exception as e:
        log(f"BBL failed: {e}")

    # 6. ACB Spain (HTML)
    try:
        acb_players = scrape_acb()
        all_players.extend(acb_players)
    except Exception as e:
        log(f"ACB failed: {e}")

    # Save
    merge_and_save(all_players)

    # Summary
    by_league = {}
    for p in all_players:
        l = p.get("league", "Unknown")
        by_league[l] = by_league.get(l, 0) + 1
    log("\n--- Summary ---")
    for league, count in sorted(by_league.items()):
        log(f"  {league:15s}: {count} players")
    log(f"  {'TOTAL':15s}: {len(all_players)}")
    log(f"\nOutput: {os.path.abspath(OUTPUT_FILE)}")
    log(f"Log:    {os.path.abspath(LOG_FILE)}")

if __name__ == "__main__":
    main()
