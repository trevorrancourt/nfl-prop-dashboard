"""
Pulls a weather forecast for each of this week's outdoor NFL games from
Open-Meteo (https://open-meteo.com) -- free, no API key needed.

Reads data/stats_cache.json (for this week's schedule + stadiums; run
fetch_stats.py first). Writes data/weather_cache.json.

Domed / retractable-roof stadiums are skipped -- weather doesn't reach the
field there, so the dashboard just shows "Dome" for those games.

nflverse's schedule "gametime" is always Eastern time, no matter where the
stadium actually is (confirmed against real games: London kickoffs listed
as "09:30" are 2:30pm local UK time, etc.), so this always requests the
forecast in the America/New_York timezone and matches the game's own
gameday/gametime directly against it -- no per-stadium timezone lookup
needed.
"""

import json
import sys
import time
from pathlib import Path

import requests

from stadium_info import lookup

ROOT = Path(__file__).resolve().parent
# NFL_DATA_DIR lets run.py build a second board (Monday Night) from its own
# data folder without touching the main one (added 2026-10-12).
DATA_DIR = Path(__import__("os").environ.get("NFL_DATA_DIR") or (ROOT / "data"))
DATA_DIR.mkdir(exist_ok=True)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Simplified from Open-Meteo's WMO weather code table.
WEATHER_CODES = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow",
    80: "Rain showers", 81: "Rain showers", 82: "Violent rain showers",
    95: "Thunderstorms", 96: "Thunderstorms", 99: "Thunderstorms",
}


def get_with_retries(url, params, attempts=4):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return requests.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException as e:
            last_error = e
            wait = 1.5 * attempt
            print(f"    (connection hiccup, retrying in {wait:.0f}s: {e})")
            time.sleep(wait)
    raise last_error


def load_schedule():
    stats_path = DATA_DIR / "stats_cache.json"
    if not stats_path.exists():
        sys.exit("data/stats_cache.json not found. Run fetch_stats.py first.")
    stats = json.loads(stats_path.read_text())
    return stats["schedule_this_week"]


def nearest_hour(gametime_str):
    """'20:15' -> 20, '20:35' -> 21 (rounds to the nearest hour)."""
    h, m = gametime_str.split(":")
    h, m = int(h), int(m)
    return h + 1 if m >= 30 else h


def fetch_forecast(lat, lon, gameday, gametime):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,precipitation_probability,wind_speed_10m,weathercode",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "America/New_York",
        "start_date": gameday,
        "end_date": gameday,
    }
    resp = get_with_retries(FORECAST_URL, params)
    if resp.status_code != 200:
        print(f"    ERROR fetching forecast ({resp.status_code}): {resp.text[:200]}")
        return None
    data = resp.json()
    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    target = f"{gameday}T{nearest_hour(gametime):02d}:00"
    if target not in times:
        # Game is likely too far out for this stadium's forecast window yet.
        return None
    idx = times.index(target)
    return {
        "temp_f": round(hourly["temperature_2m"][idx]),
        "wind_mph": round(hourly["wind_speed_10m"][idx]),
        "precip_pct": hourly["precipitation_probability"][idx],
        "condition": WEATHER_CODES.get(hourly["weathercode"][idx], "—"),
    }


def main():
    games = load_schedule()
    weather = {}
    for g in games:
        home = g["home_team"]
        stadium = g.get("stadium")
        label = f"{g['away_team']} @ {home}"
        info = lookup(stadium) if stadium else None

        if info is None:
            print(f"  {label}: unknown stadium ({stadium!r}), skipping weather")
            weather[home] = {"available": False, "stadium": stadium}
            continue

        if info["dome"]:
            print(f"  {label}: {stadium} is a dome/retractable roof, skipping weather")
            weather[home] = {"available": False, "dome": True, "stadium": stadium}
            continue

        gametime = g.get("gametime")
        if not gametime:
            weather[home] = {"available": False, "stadium": stadium}
            continue

        print(f"  {label}: fetching forecast for {stadium}...")
        # One slow/unreachable forecast shouldn't sink the whole refresh
        # (added 2026-10-15 after Open-Meteo timed out on a GitHub run).
        try:
            forecast = fetch_forecast(info["lat"], info["lon"], g["gameday"], gametime)
        except Exception as e:
            print(f"    (couldn't reach the weather service for this game, skipping: {e})")
            forecast = None
        time.sleep(0.3)
        if forecast is None:
            print("    (no forecast available yet for this game -- probably too far out)")
            weather[home] = {"available": False, "stadium": stadium}
            continue
        weather[home] = {"available": True, "dome": False, "stadium": stadium, **forecast}

    out_path = DATA_DIR / "weather_cache.json"
    out_path.write_text(json.dumps(weather, indent=2))
    print(f"Saved weather for {len(weather)} games to {out_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
