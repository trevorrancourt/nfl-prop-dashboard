"""
Pulls the NFL's official weekly injury report (Questionable/Doubtful/Out,
body part, and practice participation) from nflverse -- the same free,
public, no-API-key source already used for player/defense stats in
fetch_stats.py, hosted the same way (a CSV release asset on
github.com/nflverse/nflverse-data). Unlike fetch_odds.py/fetch_weather.py/
fetch_coverage.py, this one is fetchable directly from Claude's own cloud
sandbox too -- there's no need to run this specifically from your own
Terminal for it to work, though it's included in the normal run.py
pipeline for one-command convenience and so it always matches whatever
season/week fetch_stats.py just fetched.

Writes data/injuries_cache.json with two views:

1. "players" -- each player's OWN injury status this week, keyed by
   nflverse's stable gsis_id (the same "00-00XXXXX" id used as the key in
   stats_cache.json), for the ⛑️ badge next to his name.

2. "by_team" -- every team's injured players this week, at EVERY
   position, each tagged with how big a role that player actually plays
   (his average snap share this season). build_dashboard.py uses this for
   the "impactful injury" badges: own-team injuries that help or hurt a
   player (e.g. his O-line or his QB out hurts him; another WR out helps
   him via vacated targets) and injuries on the OPPOSING defense that
   help him (e.g. their starting CBs out helps a WR).

--- Why the practice-report fallback exists (fixed 2026-09-25) ---
The injury report has two layers. Every team posts PRACTICE
participation all week (Did Not Participate / Limited / Full), but the
official GAME designations (Out/Doubtful/Questionable) only appear on a
team's FINAL report -- Friday for a Sunday game, Wednesday for Thursday
night. The first version of this file only read game designations, so
mid-week it only ever caught the Thursday-night teams: the O-line badge
only ever showed on Green Bay players even though 21 teams had O-linemen
on the practice report that same week. Trevor caught this: "i asked you
for this a while ago, but you only did the logic for one team."

So now: a game designation always wins when it exists. When a team's
final report isn't out yet, a player who DID NOT PARTICIPATE in practice
(for an actual injury -- rest days and personal-matter absences are
skipped) is flagged as "Missed practice." "Limited" and "Full"
participation are NOT flagged -- a limited player usually plays, so
counting him would mostly add noise.

--- Snap share ("is this injury actually impactful?") ---
A backup who barely plays shouldn't set off a badge. Each injured player
gets his average offensive (or defensive, for defenders) snap share over
the games he's played this season, from nflverse's own snap-count data
(pfr ids, translated to gsis ids with nflverse's players.csv crosswalk --
the same sources fetch_stats.py already uses for the zero-stat-week
backfill). A player with no snaps this season at all gets snap_pct None:
he hasn't been contributing, so his absence is already baked into
everyone's recent numbers and isn't a new change. The actual 50% cutoff
lives in build_dashboard.py (IMPACT_SNAP_PCT) so it's one easy-to-find
constant.

Note: this is the OFFICIAL injury report -- structured designations, not
narrative news/headlines. No free source was found for injury-news
blurbs; Trevor chose the official-report-only version.
"""

import io
import json
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
# NFL_DATA_DIR lets run.py build a second board (Monday Night) from its own
# data folder without touching the main one (added 2026-10-12).
DATA_DIR = Path(__import__("os").environ.get("NFL_DATA_DIR") or (ROOT / "data"))

INJURIES_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"
SNAP_COUNTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.csv"
PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"

# Worst-first severity, used for sorting and for deciding whether an
# impact badge shows at full strength (Out/Doubtful) or faded
# (Questionable / missed practice -- a real concern, but he may well play).
STATUS_SEVERITY = {"Out": 4, "Doubtful": 3, "Questionable": 2, "Missed practice": 1}

DID_NOT_PRACTICE = "Did Not Participate In Practice"

# Which snap-count column measures a player's role, by his injury-report
# position. Anything not listed (K, P, LS, FB) is ignored for impact.
OFFENSE_POSITIONS = {"QB", "RB", "HB", "WR", "TE", "T", "G", "C", "OT", "OG", "OL"}
DEFENSE_POSITIONS = {"DE", "DT", "NT", "DL", "LB", "ILB", "MLB", "OLB", "EDGE", "CB", "S", "FS", "SS", "SAF", "DB"}


def fetch_csv(url, timeout=60):
    """Download a CSV over HTTPS with requests (which ships its own CA
    bundle via certifi) instead of pandas' built-in URL handling -- same
    helper as fetch_stats.py. Fixed 2026-09-25: this file used
    pd.read_csv(url) directly, which failed on Trevor's Mac Terminal with
    "SSL: CERTIFICATE_VERIFY_FAILED" (python.org Mac Python installs don't
    use the system certificate store)."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), low_memory=False)


def load_season_and_week():
    """Reads season/week from stats_cache.json (fetch_stats.py must run
    first) rather than recomputing it, so this always matches whatever
    week the dashboard is actually showing."""
    stats_path = DATA_DIR / "stats_cache.json"
    if not stats_path.exists():
        sys.exit("data/stats_cache.json not found -- run fetch_stats.py first.")
    stats = json.loads(stats_path.read_text())
    return stats["season"], stats["week"]


def is_non_injury(reason):
    """nflverse's practice report lists rest days and personal absences
    with reasons like 'Not injury related - resting player' -- those
    aren't injuries, and a veteran rest day on Wednesday means nothing
    for Sunday."""
    return reason.lower().startswith("not injury related")


def load_snap_shares(season):
    """{gsis_id: {"offense": avg_pct, "defense": avg_pct}} -- average snap
    share over the games this season where the player took at least one
    snap in that unit. Returns {} (and prints a warning) if either
    download fails, so injuries still get cached; they just won't pass
    the impact filter until snap data is available."""
    try:
        snaps = fetch_csv(SNAP_COUNTS_URL.format(season=season))
        players = fetch_csv(PLAYERS_URL, timeout=120)[["gsis_id", "pfr_id"]]
    except Exception as e:
        print(f"WARNING: couldn't load snap counts ({e}); impact badges will be empty.", file=sys.stderr)
        return {}

    if "game_type" in snaps.columns:
        snaps = snaps[snaps["game_type"] == "REG"]
    players = players.dropna(subset=["pfr_id", "gsis_id"])
    pfr_to_gsis = dict(zip(players["pfr_id"], players["gsis_id"]))

    shares = {}
    for pfr_id, grp in snaps.groupby("pfr_player_id"):
        gsis = pfr_to_gsis.get(pfr_id)
        if not gsis:
            continue
        entry = {}
        off = grp.loc[grp["offense_snaps"] > 0, "offense_pct"]
        dfn = grp.loc[grp["defense_snaps"] > 0, "defense_pct"]
        if len(off):
            entry["offense"] = round(float(off.mean()), 3)
        if len(dfn):
            entry["defense"] = round(float(dfn.mean()), 3)
        if entry:
            shares[str(gsis)] = entry
    return shares


def main():
    season, week = load_season_and_week()
    url = INJURIES_URL.format(season=season)
    print(f"Downloading {url} ...")
    df = fetch_csv(url)
    df = df.fillna("")

    # REG-season rows only, and only this exact week -- the file covers
    # the whole season to date.
    df = df[(df["game_type"] == "REG") & (df["week"].astype(int) == int(week))]

    print("Downloading snap counts + player-ID crosswalk for snap shares ...")
    snap_shares = load_snap_shares(season)

    players = {}
    by_team = {}
    from_game_report = 0
    from_practice = 0
    for _, row in df.iterrows():
        report_status = str(row.get("report_status", "")).strip()
        practice_status = str(row.get("practice_status", "")).strip()
        practice_injury = str(row.get("practice_primary_injury", "")).strip()

        if report_status in STATUS_SEVERITY:
            # Final report is out for this team -- the official game
            # designation is the most authoritative thing we have.
            status = report_status
            source = "game"
            primary = str(row.get("report_primary_injury", "")).strip() or practice_injury or None
            secondary = str(row.get("report_secondary_injury", "")).strip() or None
        elif practice_status == DID_NOT_PRACTICE and not is_non_injury(practice_injury):
            # No game designation yet (final report not out) -- a real
            # injury kept him out of practice.
            status = "Missed practice"
            source = "practice"
            primary = practice_injury or None
            secondary = str(row.get("practice_secondary_injury", "")).strip() or None
        else:
            continue  # Full/Limited practice, rest day, or no report at all

        if source == "game":
            from_game_report += 1
        else:
            from_practice += 1

        gsis_id = str(row["gsis_id"])
        team = row.get("team")
        position = str(row.get("position", "")).strip()

        players[gsis_id] = {
            "status": status,
            "source": source,
            "primary_injury": primary,
            "secondary_injury": secondary,
            "practice_status": practice_status or None,
            "team": team,
        }

        if position in OFFENSE_POSITIONS:
            unit = "offense"
        elif position in DEFENSE_POSITIONS:
            unit = "defense"
        else:
            continue  # K/P/LS/FB -- not part of any impact rule
        snap_pct = snap_shares.get(gsis_id, {}).get(unit)

        by_team.setdefault(team, []).append(
            {
                "gsis_id": gsis_id,
                "name": str(row.get("full_name", "")).strip(),
                "position": position,
                "status": status,
                "severity": STATUS_SEVERITY[status],
                "source": source,
                "injury": primary,
                "snap_pct": snap_pct,
            }
        )

    for entries in by_team.values():
        entries.sort(key=lambda e: (-e["severity"], -(e["snap_pct"] or 0)))

    cache = {
        "season": int(season),
        "week": int(week),
        "source": url,
        "players": players,
        "by_team": by_team,
    }
    out_path = DATA_DIR / "injuries_cache.json"
    out_path.write_text(json.dumps(cache, indent=2))
    print(
        f"Saved {len(players)} injured players for {season} Week {week} "
        f"({from_game_report} with an official game designation, "
        f"{from_practice} from the practice report) across {len(by_team)} teams "
        f"to {out_path}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
