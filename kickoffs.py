"""
Kickoff times from the sportsbooks, used to correct the nflverse schedule.

Added 2026-11-22 (per Trevor: "The Steelers eagles game time is wrong"). On
Nov 9 the NFL swapped two Week 11 games (PIT @ PHI 4:25 -> 1:00 ET, JAX @ NYG
1:00 -> 4:25 ET) and nflverse's games.csv still had the old times 13 days
later, so the board, the weather hour and "last board before kickoff" were
all off for those games.

The Odds API's event list (free, and already pulled on every refresh)
carries each game's start time as the books post it. fetch_odds.py saves
those to <data>/kickoffs.json with save_kickoffs(); anything that reads the
week's schedule passes it through apply_kickoffs(), which replaces
gameday/gametime when the books disagree with nflverse.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

FILE = "kickoffs.json"
ET = ZoneInfo("America/New_York")  # nflverse gameday/gametime are always US Eastern
FMT = "%Y-%m-%d %H:%M"
# A real move is hours (the smallest gap between two NFL windows is 20
# minutes, 4:05 vs 4:25). Anything smaller is a book's clock, not a flex.
MIN_SHIFT_MINUTES = 15
# The same two teams can be listed again weeks later (a rematch); never let
# that game's time land on this week's.
MAX_SHIFT_DAYS = 4


def _parse(commence_time):
    return datetime.fromisoformat(str(commence_time).replace("Z", "+00:00"))


def eastern(start):
    """UTC start -> ('YYYY-MM-DD', 'HH:MM') in US Eastern, to the nearest 5 minutes."""
    local = start.astimezone(ET).replace(second=0, microsecond=0)
    local += timedelta(minutes=(local.minute + 2) // 5 * 5 - local.minute)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


def save_kickoffs(data_dir, week, events, now=None):
    """
    events: [(away_abbr, home_abbr, commence_time ISO string)].
    Entries from earlier pulls of the same week are kept, so a game that has
    finished and dropped off the books' list keeps its corrected time. Once a
    game has started, the time saved before kickoff is left alone (a live
    feed can drift to the actual kick).
    """
    path = Path(data_dir) / FILE
    now = now or datetime.now(timezone.utc)
    old = {}
    try:
        prev = json.loads(path.read_text())
        if prev.get("week") == week:
            old = prev.get("games") or {}
    except (OSError, ValueError):
        pass
    games = dict(old)
    seen = set()
    for away, home, commence in sorted(events, key=lambda e: str(e[2])):
        key = f"{away}@{home}"
        if key in seen:  # the soonest listing of a matchup is this week's
            continue
        try:
            start = _parse(commence)
        except (TypeError, ValueError):
            continue
        seen.add(key)
        if key in old and start <= now:
            continue
        day, tm = eastern(start)
        games[key] = {"gameday": day, "gametime": tm, "commence_time": commence}
    path.write_text(json.dumps({"week": week, "updated_at": now.isoformat(), "games": games}, indent=2))
    return games


def _label(day, tm):
    d = datetime.strptime(f"{day} {tm}", FMT)
    return f"{d:%a} {(d.hour + 11) % 12 + 1}:{d:%M}{'p' if d.hour >= 12 else 'a'} ET"


def apply_kickoffs(games, data_dir, week=None):
    """
    games: schedule rows with away_team / home_team / gameday ('YYYY-MM-DD')
    / gametime ('HH:MM'), changed in place. Returns one line per game whose
    time was replaced, e.g. "PIT @ PHI: Sun 4:25p ET -> Sun 1:00p ET".
    Never raises: with no saved file, or a file from another week, the
    schedule is left as it is.
    """
    try:
        saved = json.loads((Path(data_dir) / FILE).read_text())
    except (OSError, ValueError):
        return []
    if week is not None and saved.get("week") != week:
        return []
    by_game = saved.get("games") or {}
    changes = []
    for g in games:
        k = by_game.get(f"{g.get('away_team')}@{g.get('home_team')}")
        day = g.get("gameday")
        if not k or not isinstance(day, str):
            continue
        tm = g.get("gametime") if isinstance(g.get("gametime"), str) else None
        try:
            new = datetime.strptime(f"{k['gameday']} {k['gametime']}", FMT)
            old = datetime.strptime(f"{day} {tm or '12:00'}", FMT)
        except (KeyError, TypeError, ValueError):
            continue
        gap = abs((new - old).total_seconds())
        if gap > MAX_SHIFT_DAYS * 86400 or (tm and gap < MIN_SHIFT_MINUTES * 60):
            continue
        was = _label(day, tm) if tm else f"{day} (no time yet)"
        changes.append(f"{g['away_team']} @ {g['home_team']}: {was} -> {_label(k['gameday'], k['gametime'])}")
        g["kickoff_was"] = f"{day} {tm}" if tm else day
        g["gameday"], g["gametime"] = k["gameday"], k["gametime"]
    return changes
