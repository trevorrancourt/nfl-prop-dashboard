"""
Pulls free, public NFL data from nflverse:
  - the full season schedule (to find this week's matchups)
  - week-by-week player stats (to compute each player's recent averages
    and each team's stats allowed by position)

No API key needed. Writes data/stats_cache.json.
"""

import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
# NFL_DATA_DIR lets run.py build a second board (Monday Night) from its own
# data folder without touching the main one (added 2026-10-12).
DATA_DIR = Path(__import__("os").environ.get("NFL_DATA_DIR") or (ROOT / "data"))
DATA_DIR.mkdir(exist_ok=True)

SCHEDULE_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
WEEKLY_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
# Used only to backfill zero-stat weeks (see backfill_zero_stat_weeks below) --
# added 2026-09-24 after Trevor caught a player's Week 1 missing from his
# game-by-game box score even though he'd actually played that week.
SNAP_COUNTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.csv"
PLAYER_IDS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"


def fetch_csv(url):
    """
    Download a CSV over HTTPS and parse it, using requests (which ships its
    own CA bundle via certifi) instead of pandas' built-in URL handling.
    This avoids "certificate verify failed" errors that some Mac Python
    installs hit when relying on the system's SSL certificate store.
    """
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), low_memory=False)

# Positions we care about for player prop comparisons, and the stat
# categories that matter for each. "total_tds" is a derived column (see
# main()) equal to rushing_tds + receiving_tds -- i.e. how a real
# "Anytime TD Scorer" prop counts it: any TD the player himself scores by
# rushing or catching it in, NOT touchdowns he threw (that's the separate
# Pass TDs stat for QBs). "receiving_air_yards" (RB/WR/TE only, straight
# from nflverse -- how far downfield the ball traveled in the air on
# passes thrown to that player, added up for the game) is a context stat
# with no Odds API market of its own -- see STAT_MARKET_MAP in
# build_dashboard.py, where it's given a null market key so it still gets
# Recent Avg / Opp Allows / Rank / Team Share like everything else, just
# never a Vegas line/Edge/🔥 (there's nothing to compare it to).
POSITION_STATS = {
    "QB": ["completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "rushing_yards", "total_tds"],
    "RB": ["carries", "rushing_yards", "receptions", "targets", "receiving_yards", "total_tds", "receiving_air_yards"],
    "WR": ["receptions", "targets", "receiving_yards", "total_tds", "receiving_air_yards"],
    "TE": ["receptions", "targets", "receiving_yards", "total_tds", "receiving_air_yards"],
}

# Regular-season weeks a player can have a game in. Also doubles as the
# cap on how many of each player's games we keep per season -- one entry
# per week is plenty (a bye week just means one fewer game logged, which
# the dashboard already treats as "no data for that week", same as any
# other missing week). Added 2026-09-24: the dashboard's sample control
# used to be "last N games" (a fixed count, blended in prior-season games
# early in the year for a bigger sample); Trevor asked to replace that
# with checkboxes for specific weeks of the CURRENT season instead --
# "just have all weeks of the regular season available for now" -- so
# there's no more need to reach into last season's data at all.
REGULAR_SEASON_WEEKS = 18
MAX_GAMES_WINDOW = REGULAR_SEASON_WEEKS


def current_season(today=None):
    """NFL season is named for the year it starts in (Sept-Feb)."""
    today = today or date.today()
    return today.year - 1 if today.month <= 2 else today.year


def load_schedule(season):
    df = fetch_csv(SCHEDULE_URL)
    df = df[df["season"] == season].copy()
    df["gameday"] = pd.to_datetime(df["gameday"])
    return df


def _not_started(g):
    """True if this schedule row's kickoff (nflverse gameday + gametime,
    always US Eastern) is still in the future."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    day = pd.Timestamp(g["gameday"]).date()
    hh, mm = (str(g.get("gametime") or "23:59") + ":00").split(":")[:2]
    kick = datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=et)
    return kick > datetime.now(et)


def current_week(schedule_df, today=None):
    """
    The week most useful for betting purposes: the earliest week where at
    least half its games are still ahead of today. This skips past a week
    that's basically over (e.g. only Monday Night Football left) and jumps
    to the upcoming slate instead.
    """
    today = pd.Timestamp(today or date.today())
    for week in sorted(schedule_df["week"].unique()):
        week_games = schedule_df[schedule_df["week"] == week]
        upcoming_fraction = (week_games["gameday"] >= today).mean()
        if upcoming_fraction >= 0.5:
            return int(week)
    return int(schedule_df["week"].max())


def load_weekly_stats(seasons):
    frames = []
    for season in seasons:
        url = WEEKLY_STATS_URL.format(season=season)
        try:
            df = fetch_csv(url)
            df["season"] = season
            frames.append(df)
        except Exception as e:
            print(f"  (no weekly stats available yet for {season}: {e})")
    if not frames:
        raise RuntimeError("Could not load any weekly stats data.")
    return pd.concat(frames, ignore_index=True)


def backfill_zero_stat_weeks(weekly_df, season):
    """
    Added 2026-09-24 after Trevor caught this directly: nflverse's weekly
    player-stats file (stats_player_week, the source for everything in this
    dashboard) only includes a row for a player in a given week if they
    recorded at least one relevant stat that week -- a player who was
    active and played real offensive snaps but simply never touched the
    ball (e.g. a blocking TE who ran routes but drew zero targets) gets NO
    row at all for that week, not a row of zeros. Confirmed directly:
    Austin Hooper played 14 offensive snaps in Week 1 2026 (per nflverse's
    own snap-count data) but has zero targets/catches that week, so his
    Week 1 is simply absent from stats_player_week.

    That absence isn't cosmetic -- every downstream average
    (compute_recent_player_stats) silently drops that week entirely rather
    than counting it as a real 0, which quietly inflates "Avg (Wk X-Y)" and
    skews Team Share/Anticipated/Edge, and it's worst for exactly the kind
    of low-target TEs/RBs whose zero weeks are both common and meaningful
    to a projection.

    Fix: pull nflverse's own snap-count data (SNAP_COUNTS_URL -- a
    separate, free, no-key dataset) to find every (player, week) where the
    player actually took an offensive snap, and for any such week missing
    from weekly_df, insert an explicit all-zero stat row. snap_counts keys
    players by `pfr_player_id` (Pro-Football-Reference's own ID scheme),
    not the gsis-style `player_id` used everywhere else in this project, so
    this also pulls nflverse's own player-ID crosswalk (PLAYER_IDS_URL) to
    translate between the two -- confirmed a clean 1:1 mapping exists there
    (gsis_id/pfr_id/display_name columns).

    Two scope decisions, disclosed rather than silently assumed:
    - Only backfills players who ALREADY have at least one real stat row
      this season. This fixes exactly the bug Trevor found (a tracked
      player missing one week) without pulling in brand-new, never-
      targeted players who wouldn't otherwise appear on this dashboard at
      all -- adding those would be a much bigger, unrequested change.
    - The new zero row's POSITION comes from the player's own EXISTING
      real rows in weekly_df, not from snap_counts' own position label --
      snap_counts sometimes tags a running back "HB" instead of "RB",
      which wouldn't match POSITION_STATS' keys and would silently skip a
      real backfill candidate if trusted directly.

    Fails soft: if either nflverse dataset can't be fetched (network
    hiccup, or the current season's snap-count release isn't posted yet
    very early in a new season), this prints a warning and returns
    weekly_df unchanged -- same "don't block the whole pipeline over one
    enhancement" pattern used elsewhere in this project (coverage
    scraping, injury fetching).
    """
    try:
        snaps = fetch_csv(SNAP_COUNTS_URL.format(season=season))
        crosswalk = fetch_csv(PLAYER_IDS_URL)
    except Exception as e:
        print(f"  (skipping zero-stat-week backfill -- snap count data unavailable: {e})")
        return weekly_df

    snaps = snaps[(snaps["season"] == season) & (snaps["game_type"] == "REG") & (snaps["offense_snaps"] > 0)].copy()

    id_map = crosswalk.dropna(subset=["gsis_id", "pfr_id"]).set_index("pfr_id")["gsis_id"].to_dict()
    snaps["player_id"] = snaps["pfr_player_id"].map(id_map)
    snaps = snaps.dropna(subset=["player_id"])

    # Position comes from the player's own existing real rows, not from
    # snap_counts' own position label -- see docstring above for why.
    player_positions = (
        weekly_df.dropna(subset=["player_id", "position"])
        .drop_duplicates("player_id")
        .set_index("player_id")["position"]
        .to_dict()
    )
    existing_weeks = set(zip(weekly_df["player_id"], weekly_df["season"], weekly_df["week"]))

    new_rows = []
    for _, row in snaps.iterrows():
        pid = row["player_id"]
        pos = player_positions.get(pid)
        if pos is None or pos not in POSITION_STATS:
            continue  # not an already-tracked QB/RB/WR/TE -- see docstring
        key = (pid, season, int(row["week"]))
        if key in existing_weeks:
            continue  # already has a real stat row this week
        new_row = {
            "player_id": pid,
            "player_display_name": row["player"],
            "position": pos,
            "team": row["team"],
            "opponent_team": row["opponent"],
            "season": season,
            "week": int(row["week"]),
            "season_type": "REG",
            "rushing_tds": 0.0,
            "receiving_tds": 0.0,
        }
        for col in POSITION_STATS[pos]:
            new_row.setdefault(col, 0.0)
        new_rows.append(new_row)

    if not new_rows:
        print("  No zero-stat weeks needed backfilling.")
        return weekly_df

    print(f"  Backfilled {len(new_rows)} zero-stat week(s) for players who played but recorded no stats.")
    return pd.concat([weekly_df, pd.DataFrame(new_rows)], ignore_index=True)


def compute_recent_player_stats(weekly_df):
    """
    Every game per player this season (weekly_df is already filtered to the
    current season only -- see main()), most recent first, plus the average.
    Grouped by player_id rather than player_display_name -- the NFL has
    real, distinct players who share the same displayed name (e.g. two
    different "A.J. Brown"s), and grouping by name alone would silently
    merge their stat lines into one nonsense row.
    """
    weekly_df = weekly_df.dropna(subset=["player_display_name", "position"]).copy()
    weekly_df = weekly_df.sort_values(["season", "week"], ascending=[False, False])

    id_col = "player_id" if "player_id" in weekly_df.columns else "player_display_name"

    players = {}
    for player_id, group in weekly_df.groupby(id_col):
        pos = group.iloc[0]["position"]
        if pos not in POSITION_STATS:
            continue
        team = group.iloc[0]["team"]
        display_name = group.iloc[0]["player_display_name"]
        recent = group.head(MAX_GAMES_WINDOW)
        stat_cols = POSITION_STATS[pos]
        games = []
        for _, row in recent.iterrows():
            game = {
                "season": int(row["season"]),
                "week": int(row["week"]),
                "opponent": row["opponent_team"],
                "team": row["team"],
            }
            for col in stat_cols:
                if col in row:
                    game[col] = float(row[col]) if pd.notna(row[col]) else 0.0
            games.append(game)
        avg = {}
        for col in stat_cols:
            vals = [g.get(col, 0.0) for g in games]
            avg[col] = round(sum(vals) / len(vals), 2) if vals else 0.0
        players[str(player_id)] = {
            "name": display_name,
            "position": pos,
            "team": team,
            "games_used": len(games),
            "recent_games": games,
            "recent_avg": avg,
        }
    return players


def compute_defense_allowed(weekly_df):
    """
    For each team and position, a most-recent-first list of what that team
    allowed to the position in each game this season (summed across every
    player of that position they faced that game).

    This is raw per-game data, not a single baked average/rank -- the
    dashboard slices it to whatever sample size you've selected (Last 2,
    Last 5, etc.) and ranks teams against each other at that same window,
    so the defense side always matches the same timeframe as the player
    side instead of always being a season-to-date figure.

    Returns (result, games_meta). `games_meta[team][pos]` is a
    most-recent-first list of {"season", "week", "vs"} dicts, same
    order/length as every stat column's value list for that team+position
    (they all come from the same underlying per-game grouping, just
    summed differently per column) -- lets the dashboard show an actual
    game-by-game defense breakdown (which week, and which offense, each
    number came from) instead of just a bare average. "vs" is the actual
    opposing TEAM that game (pulled via the offensive players' own "team"
    column, which is constant within one team's one game that week).
    """
    weekly_df = weekly_df.dropna(subset=["opponent_team", "position"]).copy()

    result = {}
    games_meta = {}
    for pos, stat_cols in POSITION_STATS.items():
        pos_df = weekly_df[weekly_df["position"] == pos]
        if pos_df.empty:
            continue
        # Sum stat production by (opponent, game), most recent game first.
        # "team" is carried along via "first" (not summed) -- it's the
        # offense whose players generated these stats, constant within a
        # single (opponent_team, season, week) group since a team plays
        # only one opponent per week.
        group_cols = ["opponent_team", "season", "week"]
        agg = {col: "sum" for col in stat_cols}
        agg["team"] = "first"
        per_game = pos_df.groupby(group_cols).agg(agg).reset_index()
        per_game = per_game.sort_values(["season", "week"], ascending=[False, False])

        for team, team_games in per_game.groupby("opponent_team"):
            for col in stat_cols:
                values = [round(float(v), 2) for v in team_games[col].tolist()]
                result.setdefault(team, {}).setdefault(pos, {})[col] = values
            games_meta.setdefault(team, {})[pos] = [
                {"season": int(s), "week": int(w), "vs": v}
                for s, w, v in zip(
                    team_games["season"].tolist(),
                    team_games["week"].tolist(),
                    team_games["team"].tolist(),
                )
            ]
    return result, games_meta


def compute_team_position_totals(weekly_df):
    """
    For each team and position, a most-recent-first list of that TEAM's own
    total production in each stat (summed across every player of that exact
    position on that team, each game). Used to work out what share of the
    team's production at a position one specific player is responsible for.

    Grouping is intentionally narrow and position-specific: an RB's share of
    rushing yards is measured against other RBs only (no QB scrambles mixed
    in), and a WR's share of receiving yards/receptions is measured against
    other WRs only (not RBs/TEs). This uses the same current-season-only
    game window as the player-side recent stats, so a player's per-game log
    and their team's per-game total line up game-for-game.

    Returned keyed by "{season}-{week}" strings (not tuples) so it's directly
    JSON-serializable and easy to look up by a specific game.
    """
    weekly_df = weekly_df.dropna(subset=["team", "position"]).copy()

    result = {}
    for pos, stat_cols in POSITION_STATS.items():
        pos_df = weekly_df[weekly_df["position"] == pos]
        if pos_df.empty:
            continue
        group_cols = ["team", "season", "week"]
        per_game = pos_df.groupby(group_cols)[stat_cols].sum().reset_index()

        for _, row in per_game.iterrows():
            team = row["team"]
            game_key = f"{int(row['season'])}-{int(row['week'])}"
            for col in stat_cols:
                result.setdefault(team, {}).setdefault(pos, {}).setdefault(col, {})[game_key] = round(
                    float(row[col]), 2
                )
    return result


def main():
    season = current_season()
    print(f"Season: {season}")

    schedule = load_schedule(season)
    week = current_week(schedule)
    # Monday Night board (added 2026-10-12): run.py can force a week, and
    # keep only that week's games that haven't kicked off yet.
    import os
    override = os.environ.get("NFL_WEEK_OVERRIDE")
    upcoming_only = bool(override) and os.environ.get("NFL_UPCOMING_ONLY") == "1"
    if override:
        week = int(override)
        print(f"Week forced to {week} (Monday Night board)")
    print(f"Current/upcoming week: {week}")

    # spread_line/total_line added 2026-10-01 for the game-script check
    # (positive spread_line = home team favored, per nflverse).
    # rest days / divisional flag / moneylines added 2026-10-07 for the
    # per-game "Game script" panel.
    schedule_cols = ["gameday", "gametime", "away_team", "home_team", "stadium", "roof", "spread_line", "total_line",
                     "away_rest", "home_rest", "div_game", "away_moneyline", "home_moneyline", "surface"]
    schedule_cols = [c for c in schedule_cols if c in schedule.columns]
    this_week_games = schedule[schedule["week"] == week][schedule_cols].to_dict(orient="records")
    if upcoming_only:
        this_week_games = [g for g in this_week_games if _not_started(g)]
        print(f"Keeping {len(this_week_games)} game(s) that haven't kicked off: "
              + ", ".join(f"{g['away_team']}@{g['home_team']}" for g in this_week_games))
    # Previous week's games that haven't kicked off yet (normally just Monday
    # Night Football after the board has rolled to the new week). run.py
    # reads this to decide whether to also build the Monday Night board.
    prev_week_open = None
    if not override and week > 1:
        prev = [g for g in schedule[schedule["week"] == week - 1][["away_team", "home_team", "gameday", "gametime"]].to_dict(orient="records")
                if _not_started(g)]
        if prev:
            prev_week_open = {"week": week - 1, "games": [
                {"away": g["away_team"], "home": g["home_team"], "gameday": str(pd.Timestamp(g["gameday"]).date()), "gametime": g["gametime"]}
                for g in prev]}
    for g in this_week_games:
        g["gameday"] = str(g["gameday"].date())
        for k in ("spread_line", "total_line", "away_rest", "home_rest", "div_game", "away_moneyline", "home_moneyline"):
            v = g.get(k)
            g[k] = None if v is None or v != v else float(v)  # NaN -> None
        for k in ("roof", "surface", "stadium"):
            v = g.get(k)
            g[k] = None if v is None or v != v else str(v)

    # Every finished regular-season game this season (added 2026-10-07):
    # scores plus the pre-game spread/total, so the dashboard's Game script
    # panel can show each team's record, points for/against, and how it has
    # done against the spread and the total.
    def _num(v):
        return None if v is None or v != v else float(v)
    played = schedule[(schedule["week"] < week) & schedule["home_score"].notna()]
    if "game_type" in played.columns:
        played = played[played["game_type"] == "REG"]
    team_results = [
        {
            "week": int(r["week"]),
            "away": r["away_team"],
            "home": r["home_team"],
            "away_score": _num(r["away_score"]),
            "home_score": _num(r["home_score"]),
            "spread_line": _num(r.get("spread_line")),
            "total_line": _num(r.get("total_line")),
            "overtime": bool(_num(r.get("overtime")) or 0),
        }
        for _, r in played.iterrows()
    ]

    # Current season only. This used to also pull last season so an
    # early-season "last N games" sample wasn't too thin -- but the
    # dashboard's sample control is now "pick specific weeks of THIS
    # season" (added 2026-09-24, at Trevor's request), so a prior season's
    # games are never selectable and there's no reason to fetch them.
    print("Downloading weekly player stats (this may take a few seconds)...")
    weekly = load_weekly_stats([season])

    print("Backfilling zero-stat weeks for players who played but recorded no stats...")
    weekly = backfill_zero_stat_weeks(weekly, season)

    # Anytime-TD-scorer definition: any TD the player scored himself, by
    # rushing or receiving. A passing TD is thrown, not scored by the QB,
    # so it's deliberately excluded here (Pass TDs is its own stat).
    weekly["total_tds"] = weekly["rushing_tds"].fillna(0) + weekly["receiving_tds"].fillna(0)

    print("Computing recent player averages...")
    players = compute_recent_player_stats(weekly)

    print("Computing defense allowed by position...")
    # weekly is already current-season-only. Early in the season this can
    # still be a small, noisy sample (as few as 1-2 games per team) -- that's
    # inherent to the data, not something this filter can fix.
    defense, defense_games = compute_defense_allowed(weekly[weekly["season"] == season])

    print("Computing team totals by position (for team-share projections)...")
    # Current season only, same window as player recent stats, so a
    # player's own per-game log lines up game-for-game with their team's total.
    team_totals = compute_team_position_totals(weekly)

    # Attach each player's upcoming opponent (if their team plays this week),
    # and whether they're on the road (so the dashboard can show "@OPP").
    team_opponent = {}
    team_is_away = {}
    for g in this_week_games:
        team_opponent[g["home_team"]] = g["away_team"]
        team_opponent[g["away_team"]] = g["home_team"]
        team_is_away[g["home_team"]] = False
        team_is_away[g["away_team"]] = True

    for name, info in players.items():
        info["upcoming_opponent"] = team_opponent.get(info["team"])
        info["at_opponent"] = team_is_away.get(info["team"], False)

    cache = {
        "generated_at": datetime.now().isoformat(),
        "season": season,
        "week": week,
        "schedule_this_week": this_week_games,
        "team_results": team_results,
        "prev_week_open": prev_week_open,
        "players": players,
        "defense_allowed": defense,
        "defense_allowed_games": defense_games,
        "team_position_totals": team_totals,
    }

    out_path = DATA_DIR / "stats_cache.json"
    out_path.write_text(json.dumps(cache, indent=2))
    print(f"Saved {len(players)} players and defense data for {len(defense)} teams to {out_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
