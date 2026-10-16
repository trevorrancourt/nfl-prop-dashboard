"""
Pulls Vegas player prop lines from The Odds API (https://the-odds-api.com)
for this week's NFL games (as determined by stats_cache.json, which you
should run fetch_stats.py to generate first).

Requires config/odds_api_key.txt to contain your API key.
Writes data/odds_cache.json.

Each call to the per-event odds endpoint costs API request quota
(roughly: number of markets x number of regions per event). This script
prints your remaining quota after every call so you can keep an eye on it.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from statistics import median

import requests

from team_mapping import to_full

ROOT = Path(__file__).resolve().parent
# NFL_DATA_DIR lets run.py build a second board (Monday Night) from its own
# data folder without touching the main one (added 2026-10-12).
DATA_DIR = Path(__import__("os").environ.get("NFL_DATA_DIR") or (ROOT / "data"))
DATA_DIR.mkdir(exist_ok=True)

API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"

DEFAULT_MARKETS = [
    "player_pass_yds",
    "player_pass_tds",
    "player_pass_interceptions",
    "player_pass_completions",
    "player_pass_attempts",
    "player_rush_yds",
    "player_rush_attempts",
    "player_receptions",
    "player_reception_yds",
    "player_tds",  # Anytime-TD-Scorer, Over/Under: rushing + receiving TDs combined
]


def load_api_key():
    # Hosted version (added 2026-10-15): GitHub Actions passes the key as
    # the ODDS_API_KEY secret; on the Mac it still comes from the file.
    env_key = __import__("os").environ.get("ODDS_API_KEY", "").strip()
    if env_key:
        return env_key
    key_path = ROOT / "config" / "odds_api_key.txt"
    if not key_path.exists():
        sys.exit(f"Couldn't find {key_path}. Put your Odds API key in that file first.")
    return key_path.read_text().strip()


def load_target_games():
    """Read this week's games from the stats cache, so odds fetching stays
    in sync with whatever week fetch_stats.py decided is current."""
    stats_path = DATA_DIR / "stats_cache.json"
    if not stats_path.exists():
        sys.exit("data/stats_cache.json not found. Run fetch_stats.py first.")
    stats = json.loads(stats_path.read_text())
    games = stats["schedule_this_week"]
    target = set()
    for g in games:
        target.add((to_full(g["away_team"]), to_full(g["home_team"])))
    return stats["week"], target


LAST_REMAINING = None


def print_quota(resp):
    global LAST_REMAINING
    remaining = resp.headers.get("x-requests-remaining")
    used = resp.headers.get("x-requests-used")
    try:
        LAST_REMAINING = float(remaining) if remaining is not None else LAST_REMAINING
    except ValueError:
        pass
    if remaining is not None:
        print(f"    [quota] used so far: {used}, remaining: {remaining}")


def get_with_retries(url, params, attempts=4):
    """
    GET with retries for transient connection/SSL hiccups (network blips,
    or the occasional flaky handshake some Python versions hit). Only
    retries connection-level failures, not real API errors (those come
    back as a normal response with a non-200 status and aren't retried
    here).
    """
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return requests.get(url, params=params, timeout=20)
        except requests.exceptions.RequestException as e:
            last_error = e
            wait = 1.5 * attempt
            print(f"    (connection hiccup, retrying in {wait:.0f}s: {e})")
            time.sleep(wait)
    raise last_error


def get_events(api_key):
    url = f"{API_BASE}/sports/{SPORT}/events"
    resp = get_with_retries(url, {"apiKey": api_key, "dateFormat": "iso"})
    if resp.status_code != 200:
        sys.exit(f"Failed to list events ({resp.status_code}): {resp.text}")
    print_quota(resp)
    return resp.json()


def get_event_odds(api_key, event_id, markets, regions, bookmakers):
    url = f"{API_BASE}/sports/{SPORT}/events/{event_id}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": ",".join(markets),
        "oddsFormat": "american",
        "dateFormat": "iso",
    }
    if bookmakers:
        params["bookmakers"] = ",".join(bookmakers)
    try:
        resp = get_with_retries(url, params)
    except requests.exceptions.RequestException as e:
        print(f"    ERROR fetching odds for event {event_id} after retries: {e}")
        return None
    if resp.status_code != 200:
        print(f"    ERROR fetching odds for event {event_id} ({resp.status_code}): {resp.text}")
        return None
    print_quota(resp)
    return resp.json()


def parse_event_odds(event_data):
    """Turn one event's raw bookmaker/market/outcome tree into
    {player_name: {market_key: {consensus_point, books: [...]}}}"""
    props = {}
    for bookmaker in event_data.get("bookmakers", []):
        book_key = bookmaker["key"]
        for market in bookmaker.get("markets", []):
            market_key = market["key"]
            for outcome in market.get("outcomes", []):
                player = outcome.get("description")
                if not player:
                    continue
                entry = props.setdefault(player, {}).setdefault(
                    market_key, {"books": []}
                )
                entry["books"].append(
                    {
                        "bookmaker": book_key,
                        "side": outcome.get("name"),
                        "point": outcome.get("point"),
                        "price": outcome.get("price"),
                    }
                )
    # compute a consensus line (median of points across books) per player/market,
    # plus a consensus price for each side (median of the Over prices, and
    # separately the Under prices, across books) -- used to check whether a
    # side's price is worth betting at all, not just whether the stat says
    # it should hit. Median rather than best/worst so one outlier book
    # doesn't skew the read, same approach as the line itself.
    for player, markets in props.items():
        for market_key, entry in markets.items():
            points = [b["point"] for b in entry["books"] if b.get("point") is not None]
            entry["consensus_point"] = round(median(points), 1) if points else None
            over_prices = [b["price"] for b in entry["books"] if b.get("side") in ("Over", "Yes") and b.get("price") is not None]
            under_prices = [b["price"] for b in entry["books"] if b.get("side") in ("Under", "No") and b.get("price") is not None]
            entry["consensus_over_price"] = round(median(over_prices)) if over_prices else None
            entry["consensus_under_price"] = round(median(under_prices)) if under_prices else None
    return props


def main():
    parser = argparse.ArgumentParser(description="Fetch Vegas NFL player prop lines.")
    parser.add_argument("--markets", default=",".join(DEFAULT_MARKETS), help="Comma-separated market keys")
    parser.add_argument("--regions", default="us", help="Odds API regions (default: us)")
    parser.add_argument(
        "--bookmakers",
        default="draftkings,fanduel,betmgm",
        help="Comma-separated bookmaker keys, or 'all' to not filter",
    )
    args = parser.parse_args()

    markets = [m.strip() for m in args.markets.split(",") if m.strip()]
    bookmakers = None if args.bookmakers.lower() == "all" else [b.strip() for b in args.bookmakers.split(",")]

    api_key = load_api_key()
    week, target_games = load_target_games()
    print(f"Looking for week {week} games: {sorted(target_games)}")

    print("Fetching event list...")
    events = get_events(api_key)

    # Quota guard (added 2026-10-15 for the hosted schedule): if the month's
    # Odds API credits are nearly gone, keep the last saved lines instead of
    # running the account dry. ODDS_MIN_REMAINING=0 (the default) disables it.
    floor = float(__import__("os").environ.get("ODDS_MIN_REMAINING") or 0)
    if floor and LAST_REMAINING is not None and LAST_REMAINING < floor:
        print(f"Only {LAST_REMAINING:.0f} Odds API credits left (floor {floor:.0f}) -- "
              "skipping the props pull and keeping the last saved lines.")
        return

    matching = [
        e for e in events if (e["away_team"], e["home_team"]) in target_games
    ]
    print(f"Found {len(matching)} of {len(target_games)} target games on the odds board.")

    all_props = {}
    event_summaries = []
    for i, event in enumerate(matching, 1):
        label = f"{event['away_team']} @ {event['home_team']}"
        print(f"  [{i}/{len(matching)}] Fetching player props: {label}")
        data = get_event_odds(api_key, event["id"], markets, args.regions, bookmakers)
        time.sleep(0.5)
        if not data:
            continue
        props = parse_event_odds(data)
        event_summaries.append(
            {"event_id": event["id"], "matchup": label, "commence_time": event["commence_time"]}
        )
        for player, markets_for_player in props.items():
            all_props.setdefault(player, {}).update(markets_for_player)

    cache = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "week": week,
        "markets_requested": markets,
        "bookmakers_requested": bookmakers,
        "events": event_summaries,
        "player_props": all_props,
    }
    out_path = DATA_DIR / "odds_cache.json"
    out_path.write_text(json.dumps(cache, indent=2))
    print(f"Saved props for {len(all_props)} players to {out_path}")


if __name__ == "__main__":
    main()
