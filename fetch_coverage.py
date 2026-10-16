"""
Pulls each team's man-coverage vs. zone-coverage rate from Sharp Football
Analysis (https://www.sharpfootballanalysis.com/stats-nfl/nfl-coverage-schemes/)
-- the only source found that publishes this specific stat for free, with no
login. Writes data/coverage_cache.json.

IMPORTANT -- read this before relying on it:
This is NOT an official, versioned data source like nflverse. It's one
public page on a third-party analytics site, scraped by matching column
headers ("Man Rate", "Zone Rate", etc.) rather than exact HTML structure, so
it's more resilient to small page tweaks than a hardcoded scrape -- but if
Sharp Football Analysis redesigns that page or takes it down, this script
will start failing and will need a look. It fails loudly and safely: it
never touches the rest of your data, and if it can't find a usable table it
just leaves your last successful coverage_cache.json alone and tells you so.

Also note this is a TEAM-LEVEL, SEASON-TO-DATE stat (e.g. "the Falcons run
man coverage on 58% of snaps this year"), not a per-game breakdown, and
there is no free source (that I could find) for the other half of this --
whether a specific PLAYER performs better against man or zone coverage
specifically. That's a PFF/SumerSports subscription metric. This script only
covers the defense side: how much a given opponent leans man vs. zone.

No API key needed. Run it directly, or as part of `python3 run.py` (skip it
with `python3 run.py --skip-coverage` if it's ever being a hassle).
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import requests

from team_mapping import FULL_TO_ABBR

ROOT = Path(__file__).resolve().parent
# NFL_DATA_DIR lets run.py build a second board (Monday Night) from its own
# data folder without touching the main one (added 2026-10-12).
DATA_DIR = Path(__import__("os").environ.get("NFL_DATA_DIR") or (ROOT / "data"))
DATA_DIR.mkdir(exist_ok=True)

SOURCE_URL = "https://www.sharpfootballanalysis.com/stats-nfl/nfl-coverage-schemes/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# A few nicknames/short forms in case the page's team names don't exactly
# match team_mapping.py's full names (e.g. "Football Team" eras, "LA Rams"
# vs "Los Angeles Rams", "Washington" vs "Washington Commanders").
NICKNAME_TO_ABBR = {
    "cardinals": "ARI", "falcons": "ATL", "ravens": "BAL", "bills": "BUF",
    "panthers": "CAR", "bears": "CHI", "bengals": "CIN", "browns": "CLE",
    "cowboys": "DAL", "broncos": "DEN", "lions": "DET", "packers": "GB",
    "texans": "HOU", "colts": "IND", "jaguars": "JAX", "chiefs": "KC",
    "raiders": "LV", "chargers": "LAC", "rams": "LA", "dolphins": "MIA",
    "vikings": "MIN", "patriots": "NE", "saints": "NO", "giants": "NYG",
    "jets": "NYJ", "eagles": "PHI", "steelers": "PIT", "49ers": "SF",
    "niners": "SF", "seahawks": "SEA", "buccaneers": "TB", "bucs": "TB",
    "titans": "TEN", "commanders": "WAS", "washington": "WAS",
}


def get_with_retries(url, attempts=4):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                return resp
            last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.RequestException as e:
            last_error = str(e)
        wait = 1.5 * attempt
        print(f"    (attempt {attempt} failed: {last_error}, retrying in {wait:.0f}s)")
        time.sleep(wait)
    raise RuntimeError(f"Couldn't fetch {url} after {attempts} attempts: {last_error}")


def team_to_abbr(raw_name):
    """Best-effort match of whatever team text is in the page's table cell
    to one of our standard abbreviations. Tries a full-name match first,
    then falls back to matching a nickname word anywhere in the text."""
    cleaned = re.sub(r"[^a-zA-Z0-9 ]", " ", raw_name).strip()
    if cleaned in FULL_TO_ABBR:
        return FULL_TO_ABBR[cleaned]
    lowered = cleaned.lower()
    for full, abbr in FULL_TO_ABBR.items():
        if full.lower() == lowered:
            return abbr
    for word in lowered.split():
        if word in NICKNAME_TO_ABBR:
            return NICKNAME_TO_ABBR[word]
    return None


def parse_pct(value):
    if value is None:
        return None
    s = str(value).strip().replace("%", "")
    if s == "" or s.lower() in ("nan", "-", "--"):
        return None
    try:
        return round(float(s), 1)
    except ValueError:
        return None


def find_coverage_table(tables):
    """Out of every <table> pandas found on the page, return the one that
    actually has Man Rate / Zone Rate columns -- rather than assuming it's
    the Nth table on the page, which breaks the moment the site adds or
    removes an unrelated table above it."""
    for df in tables:
        cols = [str(c).strip().lower() for c in df.columns]
        has_man = any("man" in c and "rate" in c for c in cols)
        has_zone = any("zone" in c and "rate" in c for c in cols)
        if has_man and has_zone:
            return df
    return None


def col_matching(df, *keywords):
    for c in df.columns:
        lc = str(c).lower()
        if all(k in lc for k in keywords):
            return c
    return None


def main():
    print(f"Fetching {SOURCE_URL} ...")
    resp = get_with_retries(SOURCE_URL)

    try:
        import pandas as pd
    except ImportError:
        sys.exit("pandas isn't installed. Run: pip3 install pandas lxml")

    try:
        tables = pd.read_html(StringIO(resp.text))
    except ValueError:
        tables = []

    table = find_coverage_table(tables)
    if table is None:
        sys.exit(
            "Couldn't find a Man Rate / Zone Rate table on that page anymore.\n"
            "Sharp Football Analysis likely changed the page layout -- this\n"
            "script needs a look. Your existing coverage_cache.json (if any)\n"
            "was left untouched, so the dashboard just won't show scheme tags\n"
            "until this is fixed."
        )

    team_col = table.columns[0]
    man_col = col_matching(table, "man", "rate")
    zone_col = col_matching(table, "zone", "rate")
    mid_closed_col = col_matching(table, "middle", "closed")
    mid_open_col = col_matching(table, "middle", "open")

    teams = {}
    unmatched = []
    for _, row in table.iterrows():
        raw_team = str(row[team_col])
        abbr = team_to_abbr(raw_team)
        man_rate = parse_pct(row.get(man_col)) if man_col else None
        zone_rate = parse_pct(row.get(zone_col)) if zone_col else None
        if abbr is None:
            unmatched.append(raw_team)
            continue
        if man_rate is None and zone_rate is None:
            continue
        teams[abbr] = {
            "man_rate": man_rate,
            "zone_rate": zone_rate,
            "middle_closed_rate": parse_pct(row.get(mid_closed_col)) if mid_closed_col else None,
            "middle_open_rate": parse_pct(row.get(mid_open_col)) if mid_open_col else None,
        }

    if unmatched:
        print(f"  (couldn't match these row labels to a team, skipped: {unmatched})")

    if len(teams) < 20:
        sys.exit(
            f"Only matched {len(teams)} of 32 teams -- something's off (page\n"
            "format probably changed). Not overwriting the existing cache.\n"
            f"Raw team labels seen: {[str(row[team_col]) for _, row in table.iterrows()]}"
        )

    cache = {
        "teams": teams,
        "source_url": SOURCE_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "Team-level, season-to-date man/zone coverage rates from a "
            "third-party site (not nflverse). Not a per-game stat, and "
            "there is no free source for player-level splits vs. man/zone."
        ),
    }
    out_path = DATA_DIR / "coverage_cache.json"
    out_path.write_text(json.dumps(cache, indent=2))
    print(f"Saved coverage rates for {len(teams)} teams to {out_path}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
