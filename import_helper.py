"""
HoopDB — Import Helper
========================
After running scraper.py, run this script to:
  1. Load hoopdb_players.json
  2. Print a summary
  3. Generate a ready-to-paste import snippet for the HoopDB web app

Usage:
    python import_helper.py
    python import_helper.py --file my_data.json
    python import_helper.py --league Euroleague   # filter one league
"""

import json
import sys
import argparse
import os

def load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def summary(players: list[dict]):
    by_league = {}
    for p in players:
        l = p.get("league", "Unknown")
        by_league[l] = by_league.get(l, 0) + 1

    teams = len({p.get("team","") for p in players})
    nations = len({p.get("nationality","") for p in players if p.get("nationality")})
    filled_pts = sum(1 for p in players if p.get("pts") is not None)
    avg_pts = round(sum(p.get("pts",0) or 0 for p in players) / max(filled_pts,1), 1)

    print("\n" + "="*55)
    print("  HoopDB Import Summary")
    print("="*55)
    print(f"  Total players : {len(players)}")
    print(f"  Teams         : {teams}")
    print(f"  Nationalities : {nations}")
    print(f"  Avg PPG       : {avg_pts}")
    print()
    print("  By league:")
    for league, count in sorted(by_league.items()):
        bar = "█" * (count // 5)
        print(f"    {league:15s} {count:4d}  {bar}")
    print("="*55)

def validate(players: list[dict]) -> list[dict]:
    """Remove players with no name or no meaningful stats."""
    valid = []
    for p in players:
        if not p.get("name") or len(p["name"]) < 2:
            continue
        if all(p.get(k) is None for k in ["pts","reb","ast","min"]):
            continue
        valid.append(p)
    return valid

def export_for_app(players: list[dict], out_path: str):
    """Write a clean JSON file ready for copy-paste import into the HoopDB web app."""
    export = []
    for p in players:
        export.append({k: v for k, v in p.items() if k not in ["source","attribution"]})
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    print(f"\n✓ App-ready file written: {out_path}")
    print("  → Open HoopDB, click Import, paste the contents of this file.")

def main():
    parser = argparse.ArgumentParser(description="HoopDB import helper")
    parser.add_argument("--file", default="hoopdb_players.json")
    parser.add_argument("--league", default=None, help="Filter to one league")
    parser.add_argument("--out", default="hoopdb_import_ready.json")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: {args.file} not found. Run scraper.py first.")
        sys.exit(1)

    players = load(args.file)
    print(f"Loaded {len(players)} players from {args.file}")

    if args.league:
        players = [p for p in players if p.get("league","").lower() == args.league.lower()]
        print(f"Filtered to {len(players)} players in {args.league}")

    players = validate(players)
    print(f"Valid players: {len(players)}")

    summary(players)
    export_for_app(players, args.out)

if __name__ == "__main__":
    main()
