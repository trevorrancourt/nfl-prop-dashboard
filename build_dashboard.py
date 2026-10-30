"""
Combines data/stats_cache.json (recent player stats + defense allowed by
position, from fetch_stats.py) with data/odds_cache.json (Vegas player
prop lines, from fetch_odds.py) into one comparison table, and renders it
as a self-contained local HTML dashboard: output/dashboard.html.

Works even if you haven't run fetch_odds.py yet -- it'll just show the
stats/matchup side with the Vegas line column blank.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from team_mapping import to_full

ROOT = Path(__file__).resolve().parent
# NFL_DATA_DIR lets run.py build a second board (Monday Night) from its own
# data folder without touching the main one (added 2026-10-12).
DATA_DIR = Path(__import__("os").environ.get("NFL_DATA_DIR") or (ROOT / "data"))
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Supabase sign-in, so marks/bets sync across devices (added 2026-10-16).
# Both values come from Supabase > Project Settings > API and are meant to
# be public: row-level security on the user_state table is what keeps each
# person's data private. NEVER put the service_role key here. Left blank,
# the page has no sign-in and works exactly as before (localStorage only).
SUPABASE_URL = __import__("os").environ.get("SUPABASE_URL", "https://ugyxzhdcmzqhibajtbwa.supabase.co")
SUPABASE_ANON_KEY = __import__("os").environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVneXh6aGRjbXpxaGliYWp0YndhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTIxMjA0ODAsImV4cCI6MjEwNzY5NjQ4MH0.3isws7QG2gg_5OSCZETKP6gGa2hZ73xmCo3swPBdScw",
)

# (stat column in stats_cache, Odds API market key, display label) per
# position. "total_tds" is the Anytime-TD-Scorer stat: rushing_tds +
# receiving_tds (any TD the player himself scored) -- for a QB that's
# effectively rushing TDs (a QB catching a TD is a rare trick play, but
# it's still counted correctly since the underlying column includes it).
# Passing TDs are a separate, already-existing stat ("Pass TDs") since a
# thrown TD isn't the QB scoring it himself.
#
# "Air Yards" (RB/WR/TE only) has market key None -- there's no Odds API
# player-prop market for it, so it's a context/comparison stat rather
# than a bettable one: it still gets Recent Avg / Opp Allows / Rank /
# Team Share like every other stat (all of that comes from build_rows()
# and enrichRow() alike, position-and-column-generic, no special-casing
# needed), it just never gets a Vegas line, so Edge/Anc. Edge/🔥/🧊 and
# the book columns stay blank for it -- same as any other stat before its
# sportsbook line gets posted.
#
# "Targets" (RB/WR/TE, added 2026-09-25 per Trevor: "add targets to the
# receiving stats so that i can see them in the popups for the players")
# is the same idea -- market key None, context-only, no bettable line.
# The underlying data was already being fetched and cached (it's in
# POSITION_STATS in fetch_stats.py, used for the RELEVANCE_FILTER cutoff
# and the zero-stat-week backfill match), just never surfaced as its own
# row before. Adding the one tuple below is the entire change -- it rides
# the same generic build_rows()/enrichRow() machinery as every other
# stat, so it automatically gets its own row in the main table, its own
# Stat filter button, its own Opp Allows/Opp Rank (defense-allowed data
# for targets was already being computed too, just not displayed), and
# critically -- since Trevor asked specifically for the popups -- its own
# row in both the player modal's summary table and its game-by-game box
# score, with zero extra code needed for either.
STAT_MARKET_MAP = {
    "QB": [
        ("passing_yards", "player_pass_yds", "Pass Yds"),
        ("passing_tds", "player_pass_tds", "Pass TDs"),
        ("passing_interceptions", "player_pass_interceptions", "INTs"),
        ("rushing_yards", "player_rush_yds", "Rush Yds"),
        ("total_tds", "player_tds", "TDs"),
        ("completions", "player_pass_completions", "Completions"),
        ("attempts", "player_pass_attempts", "Attempts"),
    ],
    "RB": [
        ("rushing_yards", "player_rush_yds", "Rush Yds"),
        ("carries", "player_rush_attempts", "Rush Attempts"),
        ("receiving_yards", "player_reception_yds", "Rec Yds"),
        ("receptions", "player_receptions", "Receptions"),
        ("targets", None, "Targets"),
        ("total_tds", "player_tds", "TDs"),
        ("receiving_air_yards", None, "Air Yards"),
    ],
    "WR": [
        ("receiving_yards", "player_reception_yds", "Rec Yds"),
        ("receptions", "player_receptions", "Receptions"),
        ("targets", None, "Targets"),
        ("total_tds", "player_tds", "TDs"),
        ("receiving_air_yards", None, "Air Yards"),
    ],
    "TE": [
        ("receiving_yards", "player_reception_yds", "Rec Yds"),
        ("receptions", "player_receptions", "Receptions"),
        ("targets", None, "Targets"),
        ("total_tds", "player_tds", "TDs"),
        ("receiving_air_yards", None, "Air Yards"),
    ],
}

TRACKED_BOOKS = ["draftkings", "fanduel", "betmgm"]


def book_line(books, bookmaker):
    """The (point, over_price, under_price) a specific bookmaker has
    posted. A prop's point/line is the same number for Over and Under --
    only the price differs per side -- but the two sides DO have separate
    prices, and both are needed: added 2026-09-24 after the old version
    of this function only kept whichever side's entry came first
    (preferring Over/Yes), silently discarding the Under-side price
    entirely. That gap fed two real bugs downstream: (1) line-shopping
    ties (e.g. two books posting the identical line) could only be
    broken by book-list-order, never by which one actually had the
    better price, since only one side's price was ever known; (2) the
    🧊 price gate, when a specific book was pinned as the shopped line,
    was checking that book's Over price even for an Under bet, since no
    Under price was ever kept to check instead. Trevor caught the first
    symptom directly (a real row where DraftKings was highlighted over
    FanDuel despite FanDuel's -110 being a better price than DraftKings'
    -116 at the identical 0.5 line) -- fixing it properly meant keeping
    both sides' prices, not just patching the tie-break in isolation."""
    if not books:
        return None, None, None
    candidates = [b for b in books if b["bookmaker"] == bookmaker]
    if not candidates:
        return None, None, None
    over = next((b for b in candidates if b["side"] in ("Over", "Yes")), None)
    under = next((b for b in candidates if b["side"] in ("Under", "No")), None)
    point = (over or under or candidates[0]).get("point")
    over_price = over.get("price") if over else None
    under_price = under.get("price") if under else None
    return point, over_price, under_price


# Minimum recent-average volume for a player to be worth showing, per position.
# Trims backups/garbage-time stats without hiding real role players.
RELEVANCE_FILTER = {
    "QB": lambda avg: avg.get("attempts", 0) > 5,
    "RB": lambda avg: (avg.get("carries", 0) + avg.get("targets", 0)) > 3,
    "WR": lambda avg: avg.get("targets", 0) > 1,
    "TE": lambda avg: avg.get("targets", 0) > 1,
}


def normalize_name(name):
    name = name.lower()
    name = re.sub(r"[.\']", "", name)
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def load_caches():
    stats_path = DATA_DIR / "stats_cache.json"
    if not stats_path.exists():
        raise SystemExit("data/stats_cache.json not found. Run fetch_stats.py first.")
    stats = json.loads(stats_path.read_text())

    odds_path = DATA_DIR / "odds_cache.json"
    odds = json.loads(odds_path.read_text()) if odds_path.exists() else None

    weather_path = DATA_DIR / "weather_cache.json"
    weather = json.loads(weather_path.read_text()) if weather_path.exists() else {}

    coverage_path = DATA_DIR / "coverage_cache.json"
    coverage = json.loads(coverage_path.read_text()).get("teams", {}) if coverage_path.exists() else {}

    injuries_path = DATA_DIR / "injuries_cache.json"
    injuries_raw = json.loads(injuries_path.read_text()) if injuries_path.exists() else {}
    injuries = injuries_raw.get("players", {})
    injuries_by_team = injuries_raw.get("by_team", {})
    global INJURY_META
    INJURY_META = {"espn": injuries_raw.get("espn"), "at": injuries_raw.get("generated_at_utc")}
    return stats, odds, weather, coverage, injuries, injuries_by_team


INJURY_META = {}


def injuries_meta_html():
    """Header note: where injury statuses came from and when (added
    2026-10-16 with the ESPN feed, so it's visible whether ESPN worked)."""
    if not INJURY_META.get("at"):
        return ""
    src = "ESPN news + NFL report" if INJURY_META.get("espn") else "NFL report only (ESPN feed unavailable)"
    return (f' &middot; Injuries: {src}, updated <span class="local-time" data-utc="{INJURY_META["at"]}">'
            f'{INJURY_META["at"][:16].replace("T", " ")} UTC</span>')


# --- "Impactful injury" badges (added 2026-09-25) ---
# Trevor: "what i want is like 'impactful Injury' to the player and to the
# defense. there is context for each position." Agreed design, per
# position: which OWN-TEAM injuries help or hurt a player, and which
# injuries on the OPPOSING DEFENSE help him. Replaces the old 🛡️ O-line
# badge (which only covered a QB/RB's own line, and in practice only ever
# showed for Green Bay -- see fetch_injuries.py for that bug).
#
# An injured player only counts if he actually plays a real role:
# IMPACT_SNAP_PCT = his average snap share this season (offense snaps for
# offensive players, defense snaps for defenders). 50% is Claude's own
# reasonable-looking pick for "a starter," not an official definition --
# same caveat as every other threshold on this page.
IMPACT_SNAP_PCT = 0.50

# Injury-report position -> the groups the rules below talk about.
INJURY_POSITION_GROUP = {
    "T": "OL", "G": "OL", "C": "OL", "OT": "OL", "OG": "OL", "OL": "OL",
    "QB": "QB", "RB": "RB", "HB": "RB", "WR": "WR", "TE": "TE",
    "DE": "EDGE", "OLB": "EDGE", "EDGE": "EDGE",
    "DT": "DI", "NT": "DI", "DL": "DI",
    "LB": "LB", "ILB": "LB", "MLB": "LB",
    "CB": "CB",
    "S": "S", "FS": "S", "SS": "S", "SAF": "S", "DB": "S",
}

# Which kind of production each stat row measures. The same player can
# be helped on one stat and not another (an opposing DT out helps an RB's
# rushing, not his receiving), so impacts are computed per stat row.
# Stats not listed (QB rushing/TDs, QB INTs) get no impact badge: no rule
# was agreed for QB rushing, and "helps" is backwards for interceptions.
PASS_STATS = {"passing_yards", "passing_tds", "completions", "attempts"}
RB_RUSH_STATS = {"rushing_yards", "carries", "total_tds"}


def stat_category(pos, stat_col):
    if pos == "QB":
        return "pass" if stat_col in PASS_STATS else None
    if pos == "RB":
        return "rush" if stat_col in RB_RUSH_STATS else "rec"
    if pos in ("WR", "TE"):
        return "rec"
    return None


# (player position, stat category) -> list of
# (whose injury: "own" team or "opp" defense, injured position group,
#  +1 helps / -1 hurts, why it matters)
IMPACT_RULES = {
    ("QB", "pass"): [
        ("own", "OL", -1, "his pass protection"),
        ("own", "WR", -1, "one of his top targets"),
        ("own", "TE", -1, "one of his top targets"),
        ("opp", "CB", +1, "weaker pass coverage"),
        ("opp", "S", +1, "weaker pass coverage"),
        ("opp", "EDGE", +1, "weaker pass rush -- more time to throw"),
    ],
    ("RB", "rush"): [
        ("own", "OL", -1, "his run blocking"),
        ("own", "RB", +1, "more carries for him"),
        ("own", "QB", -1, "backup QB -- defenses load the box"),
        ("opp", "DI", +1, "weaker run defense up front"),
        ("opp", "LB", +1, "weaker run defense"),
    ],
    ("RB", "rec"): [
        ("own", "RB", +1, "more targets for him"),
        ("opp", "LB", +1, "weaker coverage on backs"),
        ("opp", "S", +1, "weaker coverage on backs"),
    ],
    ("WR", "rec"): [
        ("own", "WR", +1, "vacated targets"),
        ("own", "TE", +1, "vacated targets"),
        ("own", "QB", -1, "backup QB throwing to him"),
        ("opp", "CB", +1, "weaker cornerback coverage"),
    ],
    ("TE", "rec"): [
        ("own", "WR", +1, "vacated targets"),
        ("own", "TE", +1, "vacated targets"),
        ("own", "QB", -1, "backup QB throwing to him"),
        ("own", "OL", -1, "may stay in to block instead of running routes"),
        ("opp", "LB", +1, "weaker coverage on tight ends"),
        ("opp", "S", +1, "weaker coverage on tight ends"),
    ],
}


# Role changes (added 2026-10-16, per Trevor: "xavier hutchinson and jalen
# brooks shouldn't be [MUST BETs] ... they are both a part of a trade ... i
# don't want that variability in must bets"). A team change (trade or
# signing, see fetch_stats.detect_trades) flags the player himself and his
# teammates in TRADE_ROLE_GROUPS on BOTH teams until that team has played
# TRADE_SETTLE_GAMES games since. Flagged rows can't be MUST BET (capped at
# 3, with a ⚠️ tag); the JS adds key-teammate injuries and Trevor's own
# manual ⚠️ flags to the same list.
TRADE_SETTLE_GAMES = 2
# A player who joins a team but doesn't suit up (hurt, inactive) stops
# flagging his new teammates once that team has played this many games.
TRADE_MAX_WAIT_GAMES = 4
# Only a player with a real role moves anyone else's workload: per game with
# his old team, WR/TE 3+ targets, RB 6+ carries+targets, QB 100+ passing
# yards. A depth player under these still flags only himself.
def trade_had_role(t):
    r = t.get("old_role") or {}
    pos = t["position"]
    if pos in ("WR", "TE"):
        return r.get("targets", 0) >= 3
    if pos == "RB":
        return r.get("carries", 0) + r.get("targets", 0) >= 6
    if pos == "QB":
        return r.get("passing_yards", 0) >= 100
    return False
TRADE_ROLE_GROUPS = {
    "WR": {"WR", "TE"},
    "TE": {"WR", "TE"},
    "RB": {"RB"},
    "QB": {"QB", "WR", "TE"},
}


def compute_trade_flags(player_id, pos, team, trades):
    """Reasons (strings) this player's role may be changing because of a
    recent team change, or [] if none."""
    out = []
    for t in trades or []:
        t = dict(t)
        if t.get("to_team_games_since", 0) >= TRADE_MAX_WAIT_GAMES:
            t["to_games_since"] = max(t["to_games_since"], TRADE_SETTLE_GAMES)
        if t["player_id"] == player_id:
            if t["to_games_since"] < TRADE_SETTLE_GAMES:
                n = t["to_games_since"]
                out.append(f"joined {t['to']} from {t['from']} after Week {t['last_week']} "
                           f"({n} game{'s' if n != 1 else ''} with them so far)")
            continue
        if pos not in TRADE_ROLE_GROUPS.get(t["position"], set()) or not trade_had_role(t):
            continue
        for side, verb in (("from", "left"), ("to", "joined")):
            if team == t[side] and t[side + "_games_since"] < TRADE_SETTLE_GAMES:
                n = t[side + "_games_since"]
                since = (f"he's played {n} game{'s' if n != 1 else ''} for them" if side == "to"
                         else f"{n} game{'s' if n != 1 else ''} since")
                out.append(f"{t['name']} ({t['position']}) {verb} {team} after Week {t['last_week']} ({since})")
    return out


# RBs split snaps in committees, so a back with a real workload can sit
# under IMPACT_SNAP_PCT (Kyle Monangai: 40% of snaps but 10-30 carries a
# game). A back also counts as a real role at RB_CARRY_SHARE_ROLE of his
# team's RB carries in the games he played (2026-10-16, per Trevor: "i'd
# say as high as 25% counts").
RB_CARRY_SHARE_ROLE = 0.25


def rb_carry_shares(stats):
    """{player_id: share of his team's RB carries in the weeks he played}."""
    team_week = {}
    for info in stats.get("players", {}).values():
        if info.get("position") != "RB":
            continue
        for g in info.get("recent_games", []):
            k = (g["team"], g["week"])
            team_week[k] = team_week.get(k, 0) + (g.get("carries") or 0)
    out = {}
    for pid, info in stats.get("players", {}).items():
        if info.get("position") != "RB":
            continue
        mine = sum(g.get("carries") or 0 for g in info.get("recent_games", []))
        total = sum(team_week.get((g["team"], g["week"]), 0) for g in info.get("recent_games", []))
        if total:
            out[pid] = mine / total
    return out


def injured_has_role(e, carry_shares):
    if e.get("snap_pct") is not None and e["snap_pct"] >= IMPACT_SNAP_PCT:
        return True
    return INJURY_POSITION_GROUP.get(e["position"]) == "RB" and (carry_shares or {}).get(e["gsis_id"], 0) >= RB_CARRY_SHARE_ROLE


def compute_injury_impacts(pos, stat_col, player_id, team, opponent, injuries_by_team, carry_shares=None):
    """{"helps": [...], "hurts": [...]} for one stat row, or None if
    nothing applies. Each entry names the injured player, his team,
    position, status, injury, snap share, and why it matters here."""
    rules = IMPACT_RULES.get((pos, stat_category(pos, stat_col)))
    if not rules:
        return None
    helps, hurts = [], []
    for side, group, effect, reason in rules:
        pool = injuries_by_team.get(team if side == "own" else opponent, [])
        for e in pool:
            if e["gsis_id"] == player_id:
                continue  # his own injury is the ⛑️ badge, not this one
            if INJURY_POSITION_GROUP.get(e["position"]) != group:
                continue
            if not injured_has_role(e, carry_shares):
                continue  # not a real starter (snaps, or RB carry share) -- his absence changes little
            item = {
                "name": e["name"],
                "team": team if side == "own" else opponent,
                "position": e["position"],
                "status": e["status"],
                "severity": e["severity"],
                "injury": e.get("injury"),
                "snap_pct": e["snap_pct"],
                "carry_share": round((carry_shares or {}).get(e["gsis_id"], 0), 2) if INJURY_POSITION_GROUP.get(e["position"]) == "RB" else None,
                "source": e.get("source"),
                "reason": reason,
            }
            (helps if effect > 0 else hurts).append(item)
    if not helps and not hurts:
        return None
    return {"helps": helps, "hurts": hurts}


# Thresholds for flagging a game's weather as bad enough to call out in
# red. Like the edge-significance thresholds elsewhere in this dashboard,
# these are Claude's own reasonable-looking picks, not an official
# handicapping standard -- easy to retune here if they're off.
BAD_WEATHER_COLD_F = 25          # "very cold"
BAD_WEATHER_WIND_MPH = 20        # matches the existing high-wind highlight
BAD_WEATHER_PRECIP_PCT = 50      # "meaningful chance of rain/snow"
BAD_WEATHER_CONDITION_KEYWORDS = ("rain", "drizzle", "snow", "thunderstorm")


def is_bad_weather(entry):
    """True if this forecast is bad enough to flag red: very cold, high
    wind, a meaningful precip chance, or a rain/snow/storm condition.
    Domes and unavailable forecasts are never flagged."""
    if not entry or entry.get("dome") or not entry.get("available"):
        return False
    temp = entry.get("temp_f")
    wind = entry.get("wind_mph")
    precip = entry.get("precip_pct")
    condition = (entry.get("condition") or "").lower()
    if temp is not None and temp <= BAD_WEATHER_COLD_F:
        return True
    if wind is not None and wind >= BAD_WEATHER_WIND_MPH:
        return True
    if precip is not None and precip >= BAD_WEATHER_PRECIP_PCT:
        return True
    if any(kw in condition for kw in BAD_WEATHER_CONDITION_KEYWORDS):
        return True
    return False


def format_weather(entry):
    """Turn one weather_cache.json entry into a display string, or None if
    there's nothing worth showing (dome, or forecast unavailable)."""
    if not entry:
        return None, None, False
    if entry.get("dome"):
        return "Dome", None, False
    if not entry.get("available"):
        return None, None, False
    text = f"{entry['temp_f']}°F, {entry['wind_mph']}mph, {entry['condition']} ({entry['precip_pct']}%)"
    return text, entry["wind_mph"], is_bad_weather(entry)


def build_odds_lookup(odds):
    """normalized player name -> {market_key: {...}}"""
    if not odds:
        return {}
    return {normalize_name(name): markets for name, markets in odds["player_props"].items()}


TEAM_SHARE_POSITIONS = ("RB", "WR", "TE")


def build_team_total_log(team_totals, pos, stat_col, recent_games):
    """
    Parallel array to a player's own game_log: for each of the player's
    recent games (by season/week), that game's TEAM's total production in
    that stat/position for that same game. Uses the team the player was
    actually on for THAT specific game (not just their current team) --
    otherwise a player traded mid-window would have his old-team games
    compared against his new team's totals, inflating or deflating his
    "share". Looked up by (team, season, week) rather than by list
    position, since a player can miss a game their team played (bye,
    injury) while teammates at the same position still logged stats.
    """
    log = []
    for g in recent_games:
        team = g.get("team")
        key = f"{g['season']}-{g['week']}"
        by_game = team_totals.get(team, {}).get(pos, {}).get(stat_col, {})
        log.append(by_game.get(key, 0))
    return log


def build_defense_logs(stats):
    """
    {"POS|stat_col": {team: [most-recent-first game log]}} -- every team's
    raw per-game defense data for every (position, stat) pair the
    dashboard shows. The page slices and re-ranks this itself for whatever
    sample size is selected, so Opp Allows / Opp Rank always match the
    same timeframe as the player side.
    """
    defense = stats["defense_allowed"]
    logs = {}
    for pos, entries in STAT_MARKET_MAP.items():
        for stat_col, _, _ in entries:
            key = f"{pos}|{stat_col}"
            team_logs = {}
            for team, by_pos in defense.items():
                log = by_pos.get(pos, {}).get(stat_col)
                if log:
                    team_logs[team] = log
            logs[key] = team_logs
    return logs


def board_switch_html():
    """Monday Night board switch (added 2026-10-12). run.py sets
    NFL_ALT_LINK="<file>|<label>" when both boards exist, and
    NFL_BOARD_BADGE on the Monday Night board itself."""
    import os, html as _h
    out = ""
    badge = os.environ.get("NFL_BOARD_BADGE")
    if badge:
        out += f'<span class="board-badge">{_h.escape(badge)}</span>'
    alt = os.environ.get("NFL_ALT_LINK")
    if alt and "|" in alt:
        href, label = alt.split("|", 1)
        out += f'<a class="board-switch" href="{_h.escape(href)}">{_h.escape(label)}</a>'
    return f'<div class="board-switch-row">{out}</div>' if out else ""


def build_games_list(stats, weather=None):
    """
    This week's actual matchups, for the Game filter dropdown (added
    2026-09-24 per Trevor: "make a filter so i can choose to select by
    game"). Sourced from stats_cache.json's "schedule_this_week" -- the
    same nflverse schedule data fetch_odds.py/fetch_weather.py already use
    to know which games to fetch for, just not previously threaded through
    to the dashboard itself. Each game's "key" (AWAY@HOME) is built the
    same way a row's own game is identified client-side (see gameKey() in
    the JS below), so the two join with no extra lookup needed. Sorted by
    kickoff (gameday, then gametime) so the dropdown reads in the order
    the week is actually played -- Thursday night first, Monday night
    last.
    """
    games = []
    for g in stats.get("schedule_this_week", []):
        away, home = g.get("away_team"), g.get("home_team")
        if not away or not home:
            continue
        games.append(
            {
                "key": f"{away}@{home}",
                "away": away,
                "home": home,
                "gameday": g.get("gameday"),
                "gametime": g.get("gametime"),
                # Vegas spread (positive = home favored) and total, for the
                # game-script check; None until fetch_stats.py has them.
                "spread": g.get("spread_line"),
                "total": g.get("total_line"),
                # Added 2026-10-07 for the Game script panel.
                "away_rest": g.get("away_rest"),
                "home_rest": g.get("home_rest"),
                "div_game": bool(g.get("div_game")),
                "away_ml": g.get("away_moneyline"),
                "home_ml": g.get("home_moneyline"),
                "weather": (weather or {}).get(home),
            }
        )
    games.sort(key=lambda g: (g.get("gameday") or "", g.get("gametime") or ""))
    return games


def build_rows(stats, odds_lookup, weather, injuries, injuries_by_team):
    rows = []
    team_totals = stats.get("team_position_totals", {})

    carry_shares = rb_carry_shares(stats)
    # Each team's lead back = the RB with the biggest share of its RB carries
    # (for the 10+ point favorite rule, see BLOWOUT_FAV in the page script).
    lead_rb = {}
    for pid, inf in stats["players"].items():
        if inf.get("position") == "RB" and pid in carry_shares:
            cur = lead_rb.get(inf["team"])
            if cur is None or carry_shares[pid] > carry_shares[cur]:
                lead_rb[inf["team"]] = pid
    for player_id, info in stats["players"].items():
        player_name = info.get("name", player_id)
        pos = info["position"]
        opp = info.get("upcoming_opponent")
        if not opp or pos not in STAT_MARKET_MAP:
            continue
        if not RELEVANCE_FILTER.get(pos, lambda a: True)(info["recent_avg"]):
            continue

        norm_name = normalize_name(player_name)
        player_odds = odds_lookup.get(norm_name, {})

        # This week's official injury-report designation for this exact
        # player, if any -- joined by nflverse's stable player_id (the same
        # "00-00XXXXX" gsis_id already used as the key here and in the raw
        # injuries CSV), so no fuzzy name-matching is needed the way the
        # Odds API side requires. None for the (large majority of) players
        # with no designation this week.
        injury = injuries.get(player_id)

        # Weather at the game's actual home stadium (same for every stat row
        # this player has, so compute it once per player).
        home_team = opp if info.get("at_opponent") else info["team"]
        weather_text, wind_mph, weather_bad = format_weather(weather.get(home_team))

        for stat_col, market_key, label in STAT_MARKET_MAP[pos]:
            recent_avg = info["recent_avg"].get(stat_col)
            if recent_avg is None:
                continue
            # Most-recent-first list of this stat's value in each of the
            # player's games this season (up to MAX_GAMES_WINDOW from
            # fetch_stats.py, i.e. the full season). The dashboard's Weeks
            # filter picks which of these count at render time, so Recent
            # Avg / Edge / Hit Rate all update instantly without
            # re-fetching anything.
            game_log = [g.get(stat_col, 0) for g in info["recent_games"]]

            # Same-length, index-aligned metadata for each game in game_log
            # above -- lets the player detail modal show an actual
            # game-by-game box score (week/opponent + every stat that game)
            # instead of just a bare list of numbers for one stat at a time.
            game_weeks = [g.get("week") for g in info["recent_games"]]
            game_seasons = [g.get("season") for g in info["recent_games"]]
            game_opponents = [g.get("opponent") for g in info["recent_games"]]

            # Team-share data: this player's stat vs. their team's own total
            # at that exact position (RBs-only for rushing, same-position-only
            # for receiving), game-for-game aligned with game_log above.
            # QBs don't need this at all -- there's only one starting passer,
            # so the dashboard fixes a QB's share at 100% directly (see
            # deriveStats() in the JS below) rather than computing a ratio.
            team_total_log = (
                build_team_total_log(team_totals, pos, stat_col, info["recent_games"])
                if pos in TEAM_SHARE_POSITIONS
                else []
            )

            market = player_odds.get(market_key)
            line = market.get("consensus_point") if market else None
            books = market.get("books") if market else []
            # Consensus price for each side (median across DK/FD/BetMGM) --
            # used to check whether the price is actually worth betting at,
            # separate from whether the stat itself looks good. Over price
            # is what 🔥 would be betting into, Under price is what 🧊
            # would be betting into.
            over_price = market.get("consensus_over_price") if market else None
            under_price = market.get("consensus_under_price") if market else None

            dk_point, dk_over_price, dk_under_price = book_line(books, "draftkings")
            fd_point, fd_over_price, fd_under_price = book_line(books, "fanduel")
            mgm_point, mgm_over_price, mgm_under_price = book_line(books, "betmgm")

            rows.append(
                {
                    "player": player_name,
                    "position": pos,
                    "team": info["team"],
                    "opponent": opp,
                    "at_opponent": info.get("at_opponent", False),
                    "stat_label": label,
                    "stat_col": stat_col,
                    "game_log": game_log,
                    "game_weeks": game_weeks,
                    "game_seasons": game_seasons,
                    "game_opponents": game_opponents,
                    "team_total_log": team_total_log,
                    "vegas_line": line,
                    "over_price": over_price,
                    "under_price": under_price,
                    "draftkings_line": dk_point,
                    "draftkings_over_price": dk_over_price,
                    "draftkings_under_price": dk_under_price,
                    "fanduel_line": fd_point,
                    "fanduel_over_price": fd_over_price,
                    "fanduel_under_price": fd_under_price,
                    "betmgm_line": mgm_point,
                    "betmgm_over_price": mgm_over_price,
                    "betmgm_under_price": mgm_under_price,
                    "weather": weather_text,
                    "wind_mph": wind_mph,
                    "weather_bad": weather_bad,
                    "injury": injury,
                    # Own-team and opposing-defense injuries that help or
                    # hurt THIS stat (see IMPACT_RULES) -- per stat row,
                    # since e.g. an opposing DT out helps an RB's rushing
                    # but not his receiving.
                    "injury_impacts": compute_injury_impacts(
                        pos, stat_col, player_id, info["team"], opp, injuries_by_team, carry_shares
                    ),
                    "trade_flags": compute_trade_flags(player_id, pos, info["team"], stats.get("trades")),
                    "rb_lead": pos == "RB" and lead_rb.get(info["team"]) == player_id,
                }
            )
    return rows


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>NFL Player Prop Dashboard - Week {week}</title>
<style>
  :root {{
    --bg: #0f1115; --panel: #171a21; --border: #2a2e38; --text: #e6e8ec;
    --muted: #9aa1ac; --green: #3fb950; --red: #f85149; --accent: #4f8cff; --amber: #d29922;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }}
  header {{ padding: 20px 24px; border-bottom: 1px solid var(--border); }}
  header h1 {{ margin: 0 0 4px 0; font-size: 20px; }}
  header .meta {{ color: var(--muted); font-size: 13px; }}
  .controls {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; padding: 14px 24px; border-bottom: 1px solid var(--border); }}
  .controls input[type=text] {{ background:var(--panel); border:1px solid var(--border); color:var(--text); padding:7px 10px; border-radius:6px; min-width:220px; }}
  .pos-btn, .stat-btn {{ background:var(--panel); border:1px solid var(--border); color:var(--text); padding:6px 12px; border-radius:6px; cursor:pointer; font-size:13px; }}
  .pos-btn.active, .stat-btn.active {{ background:var(--accent); border-color:var(--accent); }}
  #pickySlider {{ width: 160px; accent-color: var(--accent); vertical-align: middle; }}
  #pickyLabel {{ font-variant-numeric: tabular-nums; }}
  #hideMarkedX {{ accent-color: var(--accent); }}
  .mark-select {{
    background: var(--panel); border: 1px solid var(--border); color: var(--text);
    padding: 3px 4px; border-radius: 5px; font-size: 13px; cursor: pointer; max-width: 110px;
  }}
  .mark-select:hover {{ border-color: var(--accent); }}
  .bet-slip {{ flex-wrap: wrap; width: 196px; align-items: center; row-gap: 3px; }}
  .bet-slip .bet-stake, .bets-table .bet-stake {{ width: 54px; }}
  .bet-towin {{ font-size: 11px; white-space: nowrap; }}
  .bets-table .bet-field {{ background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 2px 4px; border-radius: 4px; font-size: 12px; }}
  .bets-table .bet-line {{ width: 52px; }} .bets-table .bet-odds {{ width: 56px; }} .bets-table .bet-week {{ width: 34px; margin-right: 4px; }}
  .bets-table .bet-desc {{ width: 230px; }}
  .bets-table .bet-bad {{ border-color: var(--red); }}
  .bets-week-row td {{ color: var(--muted); font-weight: 600; font-size: 12px; background: rgba(127,127,127,0.06); }}
  .bet-res-win td:first-child {{ box-shadow: inset 3px 0 0 var(--green); }}
  .bet-res-loss td:first-child {{ box-shadow: inset 3px 0 0 var(--red); }}
  .bet-sug {{ font-size: 10px; padding: 0 4px; border-radius: 4px; margin-left: 4px; }}
  .bet-sug-win {{ background: rgba(63,185,80,0.18); color: #7ee08a; }}
  .bet-sug-loss {{ background: rgba(248,81,73,0.18); color: #ff8f89; }}
  .bet-sug-push {{ background: rgba(154,161,172,0.18); color: #c3c8d1; }}
  .tb-script-good {{ background: rgba(63,185,80,0.16); color: #7ee08a; margin-left: 4px; }}
  .tb-script-bad {{ background: rgba(210,153,34,0.20); color: #e0b84a; margin-left: 4px; }}
  .sl-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }}
  .sl-block {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; }}
  .sl-head {{ font-weight: 600; margin-bottom: 4px; font-size: 13px; }}
  .sl-head .muted {{ font-weight: 400; font-size: 11px; }}
  .sl-list {{ list-style: none; margin: 0; padding: 0; font-size: 12px; }}
  .sl-list li {{ margin: 3px 0; white-space: normal; }}
  .sl-list .sl-text {{ color: var(--text); opacity: 0.85; font-weight: 400; }}
  .bet-lv-better {{ background: rgba(63,185,80,0.18); color: #7ee08a; }}
  .bet-lv-worse {{ background: rgba(248,81,73,0.18); color: #ff8f89; }}
  .bet-lv-same {{ background: rgba(154,161,172,0.18); color: #c3c8d1; }}
  .bets-week-link {{ cursor: pointer; }}
  .bets-week-link:hover td {{ color: var(--accent); }}
  .bets-cards {{ display: flex; gap: 10px; flex-wrap: wrap; }}
  .bets-card {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; min-width: 170px; font-size: 12px; }}
  .bets-big {{ font-size: 22px; font-weight: 700; margin: 2px 0; font-variant-numeric: tabular-nums; }}
  .opp-rank-chip {{ font-size: 11px; margin-left: 4px; padding: 0 4px; border-radius: 4px; background: rgba(127,127,127,0.12); white-space: nowrap; }}
  .opp-rank-chip.off-hi {{ background: rgba(210,153,34,0.20); color: #e0b84a; }}
  .opp-rank-chip.off-lo {{ background: rgba(79,140,255,0.18); color: #8cb4ff; }}
  .opp-rank-avg td {{ border-top: 1px solid rgba(127,127,127,0.35); }}
  .modal-note {{ font-size: 12px; opacity: 0.7; margin: -4px 0 6px; }}
  .bet-slip {{ display: flex; gap: 4px; margin-top: 4px; }}
  .bet-slip .bet-field {{
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 2px 4px; border-radius: 4px; font-size: 12px;
  }}
  .bet-slip .bet-field:focus {{ outline: none; border-color: var(--accent); }}
  .bet-slip .bet-field::placeholder {{ color: #5c6370; }}
  .bet-slip .bet-line {{ width: 50px; }}
  .bet-slip .bet-odds {{ width: 54px; }}
  .bet-slip .bet-bad {{ border-color: var(--red); }}
  #gameFilter {{
    background: var(--panel); border: 1px solid var(--border); color: var(--text);
    padding: 6px 8px; border-radius: 6px; font-size: 13px; cursor: pointer; max-width: 260px;
  }}
  #gameFilter:hover {{ border-color: var(--accent); }}
  .weeks-filter {{ position: relative; display: inline-block; }}
  .weeks-toggle {{
    background:var(--panel); border:1px solid var(--border); color:var(--text);
    padding:6px 12px; border-radius:6px; cursor:pointer; font-size:13px;
  }}
  .weeks-toggle:hover {{ border-color: var(--accent); }}
  .weeks-panel {{
    display:none; position:absolute; top: calc(100% + 6px); left:0; z-index: 20;
    background:var(--panel); border:1px solid var(--border); border-radius:8px;
    padding:10px; box-shadow: 0 6px 20px rgba(0,0,0,0.3); width: 260px;
  }}
  .weeks-panel.open {{ display:block; }}
  .weeks-panel-actions {{ display:flex; gap:6px; margin-bottom:8px; flex-wrap:wrap; }}
  .weeks-mini-btn {{
    background:var(--bg); border:1px solid var(--border); color:var(--text);
    padding:4px 8px; border-radius:5px; cursor:pointer; font-size:12px;
  }}
  .weeks-mini-btn:hover {{ border-color: var(--accent); }}
  .weeks-quick-group {{ display:inline-flex; gap:4px; margin-left:6px; vertical-align:middle; }}
  .weeks-quick {{ padding:5px 9px; }}
  .weeks-quick.active {{ background:var(--accent); border-color:var(--accent); color:#fff; }}
  .weeks-grid {{ display:grid; grid-template-columns: repeat(6, 1fr); gap:4px; }}
  .week-checkbox {{
    display:flex; align-items:center; justify-content:center; gap:3px;
    font-size:12px; padding:4px 0; border-radius:5px; cursor:pointer; user-select:none;
  }}
  .week-checkbox:hover {{ background: var(--bg); }}
  .week-checkbox input {{ accent-color: var(--accent); cursor:pointer; }}
  .no-odds-note {{ padding: 10px 24px; color: var(--muted); font-size: 13px; }}
  table {{ width:100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  th {{ position: sticky; top: 0; background: var(--panel); cursor: pointer; user-select:none; color: var(--muted); font-weight:600; }}
  th:hover {{ color: var(--text); }}
  .modal-table tr.upcoming-row td {{ background: rgba(79,140,255,0.12); border-bottom: 2px solid var(--accent); }}
  .board-switch-row {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; align-items:center; }}
  .board-switch {{ display:inline-block; padding:6px 12px; border-radius:6px; background:var(--accent); color:#fff; font-size:13px; font-weight:600; text-decoration:none; }}
  .board-switch:hover {{ filter:brightness(1.1); }}
  .board-badge {{ display:inline-block; padding:5px 10px; border-radius:6px; border:1px solid var(--accent); color:var(--text); font-size:13px; font-weight:600; }}
  .gs-panel {{ margin: 6px 24px 14px; padding: 10px 16px; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; }}
  .gs-panel > details > summary {{ cursor: pointer; font-weight: 600; font-size: 14px; padding: 2px 0; }}
  .gs-wrap {{ font-size: 13px; }}
  .gs-headline {{ font-size: 18px; font-weight: 700; margin: 8px 0 6px; }}
  .gs-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 4px; }}
  .gs-chip {{ background: var(--bg); border: 1px solid var(--border); border-radius: 12px; padding: 3px 10px; font-size: 12px; }}
  .gs-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0 28px; }}
  @media (max-width: 900px) {{ .gs-grid {{ grid-template-columns: 1fr; }} }}
  .gs-p {{ margin: 4px 0 8px; line-height: 1.45; }}
  .gs-list {{ margin: 4px 0 8px; padding-left: 18px; line-height: 1.45; }}
  .gs-list li {{ margin-bottom: 3px; }}
  .gs-good {{ color: var(--green); }}
  .gs-bad {{ color: var(--red); }}
  .gs-table td, .gs-table th {{ white-space: nowrap; }}
  .gs-results {{ margin-top: 8px; line-height: 1.9; }}
  .gs-res {{ display: inline-block; margin-right: 10px; }}
  .gs-player {{ text-decoration: underline dotted; text-underline-offset: 3px; cursor: pointer; }}
  .gs-link {{ cursor: pointer; text-decoration: none; margin-left: 4px; padding: 0 3px; border-radius: 4px; font-size: 12px; }}
  .gs-link:hover {{ background: rgba(255,255,255,0.12); }}
  #tbl thead th {{ position: sticky; }}
  #tbl thead th .col-resize {{ position:absolute; top:0; right:0; width:7px; height:100%; cursor:col-resize; z-index:2; }}
  #tbl thead th .col-resize:hover, body.col-resizing #tbl thead th .col-resize {{ background: rgba(255,255,255,0.18); }}
  #tbl thead th.col-dragging {{ opacity:0.45; }}
  #tbl thead th.col-drop-before {{ box-shadow: inset 3px 0 0 var(--accent); }}
  #tbl thead th.col-drop-after {{ box-shadow: inset -3px 0 0 var(--accent); }}
  body.col-resizing, body.col-resizing * {{ cursor: col-resize !important; user-select: none !important; }}
  tbody tr:hover {{ background: rgba(255,255,255,0.03); }}
  .edge-pos {{ color: var(--green); font-weight:600; }}
  .edge-neg {{ color: var(--red); font-weight:600; }}
  /* Added 2026-09-24: marks whichever DraftKings/FanDuel/BetMGM cell is
     the most advantageous line for the bet Edge/Anc. Edge are actually
     grading -- lowest line for an Over, highest for an Under. */
  .best-line {{ background: rgba(63, 185, 80, 0.16); box-shadow: inset 0 0 0 1px rgba(63, 185, 80, 0.5); border-radius: 4px; font-weight: 600; }}
  .wind-high {{ color: var(--red); font-weight:600; }}
  .wind-med {{ color: var(--amber); }}
  .weather-bad {{ color: var(--red); font-weight:600; }}
  .muted {{ color: var(--muted); }}
  .grouped-cell {{ color: var(--muted); border-bottom-color: transparent; }}
  tr.group-end td {{ border-bottom: 1px solid #3a3f4c; }}
  .wrap {{ max-width: 1400px; margin: 0 auto; padding-bottom: 40px; }}
  tbody tr[data-player] {{ cursor: pointer; }}
  td.player-cell {{ text-decoration: underline dotted; text-underline-offset: 3px; }}
  .modal-overlay {{
    display:none; position:fixed; inset:0; background:rgba(0,0,0,0.6);
    align-items:flex-start; justify-content:center; padding: 5vh 20px; z-index:100;
  }}
  .modal-panel {{
    background:var(--panel); border:1px solid var(--border); border-radius:10px;
    max-width: 1000px; width:100%; max-height:88vh; overflow-y:auto; padding:20px 24px;
  }}
  .modal-header {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:4px; }}
  .modal-header h2 {{ margin:0; font-size:19px; }}
  .modal-close {{ background:none; border:none; color:var(--muted); font-size:22px; cursor:pointer; line-height:1; padding:4px 8px; }}
  .modal-close:hover {{ color:var(--text); }}
  .modal-meta {{ color:var(--muted); font-size:13px; margin-bottom:16px; }}
  .modal-table {{ font-size:13px; }}
  .modal-table th {{ position:static; }}
  .modal-section-title {{ font-size:14px; color:var(--muted); margin:20px 0 8px; font-weight:600; }}
  .modal-section-title:first-child {{ margin-top:0; }}
  .modal-table-wrap {{ overflow-x:auto; margin-bottom:6px; }}
  td.opp-cell {{ text-decoration: underline dotted; text-underline-offset: 3px; }}
  .cov-tag {{ display:inline-block; font-size:10px; font-weight:700; padding:1px 4px; border-radius:4px; margin-left:5px; text-decoration:none; vertical-align:1px; }}
  .cov-highman {{ background: rgba(79,140,255,0.18); color:#8cb4ff; }}
  .cov-medium {{ background: rgba(154,161,172,0.18); color:#c3c8d1; }}
  .cov-lowman {{ background: rgba(210,153,34,0.18); color:#e0b84a; }}
  .cov-review {{ background: rgba(191,133,255,0.18); color:#c893ff; margin-left:0; }}
  .mustbet-tag {{ background: rgba(255,215,0,0.20); color:#ffd54a; margin-left:0; font-size:11px; letter-spacing:0.02em; }}
  .injury-tag {{ margin-left:5px; cursor: default; }}
  .injury-out {{ background: rgba(248,81,73,0.18); color:#ff8f89; }}
  .impact-tag {{ margin-left:5px; cursor: default; white-space: nowrap; }}
  td.stat-cell {{ font-weight: 600; }}
  .impact-help {{ background: rgba(63,185,80,0.20); color:#7ee08a; }}
  .impact-hurt {{ background: rgba(248,81,73,0.18); color:#ff8f89; }}
  .impact-soft {{ opacity: 0.55; }}
  .ladder-tag {{ background: rgba(63,185,80,0.20); color:#7ee08a; margin-left:5px; cursor: default; }}
  .cov-header {{ padding: 4px 0 14px 0; color: var(--muted); font-size: 13px; }}
  .cov-header strong {{ color: var(--text); }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>NFL Player Prop Dashboard</h1>
    <div class="meta">Season {season}, Week {week} &middot; Stats generated {stats_time} &middot; Odds generated {odds_time}{injuries_meta}</div>
    {board_switch_html}
  </header>
  {no_odds_note}
  <div class="controls">
    <input type="text" id="search" placeholder="Search player, team, or opponent...">
    <button class="pos-btn active" data-pos="ALL">All</button>
    <button class="pos-btn" data-pos="QB">QB</button>
    <button class="pos-btn" data-pos="RB">RB</button>
    <button class="pos-btn" data-pos="WR">WR</button>
    <button class="pos-btn" data-pos="TE">TE</button>
    <span class="muted" style="margin-left:16px;">Game:</span>
    <select id="gameFilter" title="Narrow the table to just one game's players. Resets to 'All Games' automatically every Tuesday morning (after that week's Monday Night game is done), so it never accidentally stays stuck on a game that's already been played -- doesn't require re-running python3 run.py to clear."></select>
    <span class="muted" style="margin-left:16px;">Weeks:</span>
    <div class="weeks-filter" id="weeksFilter">
      <button type="button" id="weeksToggle" class="weeks-toggle" title="Choose which weeks of the current season count toward Avg / Opp Allows / hit rate / signals / everything else on this page. Defaults to the last 4 weeks played (the upcoming week has no games yet, so it isn&#39;t included)."></button>
      <div class="weeks-panel" id="weeksPanel">
        <div class="weeks-panel-actions">
          <button type="button" id="weeksAll" class="weeks-mini-btn">All</button>
          <button type="button" id="weeksNone" class="weeks-mini-btn">None</button>
          <button type="button" id="weeksToDate" class="weeks-mini-btn">All played</button>
        </div>
        <div class="weeks-grid" id="weeksGrid"></div>
      </div>
    </div>
    <span class="weeks-quick-group">
      <button type="button" class="weeks-mini-btn weeks-quick" data-last="2" title="Only the 2 most recent played weeks. Week-based, so a player whose team had a bye in that span shows 1 game.">Last 2</button>
      <button type="button" class="weeks-mini-btn weeks-quick" data-last="4" title="Only the 4 most recent played weeks (the default). Week-based, so a bye in that span means 3 games for that team.">Last 4</button>
      <button type="button" class="weeks-mini-btn weeks-quick" data-last="all" title="Every week played so far.">All played</button>
    </span>
    <button type="button" id="myBetsBtn" class="pos-btn" style="margin-left:16px;" title="Every bet you've marked &#9989; (all weeks, not just this one), with result tracking: record, total staked, and profit.">&#128210; My Bets</button>
    <button type="button" id="myRulesBtn" class="pos-btn" style="margin-left:6px;" title="Every rule the board applies, in plain words.">&#128220; My rules</button>
    <span id="syncCtl" style="display:none; margin-left:10px;"></span>
  </div>
  <div class="controls">
    <span class="muted" id="pickyLabel"></span>
    <label class="muted" style="margin-left:16px; display:inline-flex; align-items:center; gap:5px; cursor:pointer;">
      <input type="checkbox" id="hideMarkedX" checked> Hide &#10060; rows
    </label>
    <label class="muted" style="margin-left:16px; display:inline-flex; align-items:center; gap:5px; cursor:pointer;" title="Hide the &#10067; 'worth a look' rows -- Edge and Anc. Edge didn't agree, and in the Week 3 backtest they went 61-83 as a group.">
      <input type="checkbox" id="hideReview"> Hide &#10067; rows
    </label>
    <button type="button" id="resetColsBtn" class="pos-btn" style="margin-left:16px;" title="Columns: drag a header to move it, drag the thin bar on a header's right edge to resize it. Your layout is saved in this browser. This puts every column back to its original spot and width.">&#8634; Reset columns</button>
    <label class="muted" style="margin-left:16px; display:inline-flex; align-items:center; gap:5px; cursor:pointer;" title="Only show rows with a &#129692; Ladder badge -- QB Pass/Rush Yds, RB Rush/Rec Yds, and WR/TE Rec Yds rows where the player's best game this season already cleared 2x their current line (line must be at least 30 to qualify).">
      <input type="checkbox" id="ladderOnlyFilter"> &#129692; Ladder only
    </label>
    <label class="muted" style="margin-left:16px; display:inline-flex; align-items:center; gap:5px; cursor:pointer;" title="Only show rows with a &#11014;/&#11015; Alt line idea: the projection is 25%+ past the line, and he cleared the suggested alt line in 75%+ of the selected games. Shows them even when Hide &#10067; is ticked. Fun for parlays -- alt odds aren't pulled, so check the price at the book.">
      <input type="checkbox" id="altOnlyFilter"> &#11014; Alt lines only
    </label>
    <label class="muted" style="margin-left:16px; display:inline-flex; align-items:center; gap:5px; cursor:pointer;" title="Only show rows where the upcoming opponent ranks 20th-32nd against this position/stat (bottom third of the league, i.e. they give up a lot of it) -- same Opp Rank number already shown in its own column, just filtered down to the weak end. Combine this with &#129692; Ladder only to find players who've proven they can blow past their line AND are facing a defense that makes it easier to do again.">
      <input type="checkbox" id="weakMatchupFilter"> Weak matchup only (Rank 20+)
    </label>
    <label class="muted" style="margin-left:16px; display:inline-flex; align-items:center; gap:5px; cursor:pointer;" title="Only show rows where the upcoming opponent ranks 1st-13th against this position/stat (top third of the league, i.e. they limit it best) -- same Opp Rank number already shown in its own column, just filtered down to the strong end. Useful for finding UNDER candidates: a tough matchup makes it harder for the player to clear their line.">
      <input type="checkbox" id="strongMatchupFilter"> Strong matchup only (Rank 1-13)
    </label>
    <label class="muted" style="margin-left:16px; display:inline-flex; align-items:center; gap:5px;" title="What the &#128293;/&#129482;/&#11088;/&#10067; signals are built from. Consistency: how often HE has cleared the line and how often THIS DEFENSE has allowed it (Hit / Opp Hit columns). Average edge: the original formula -- how far his average and the matchup projection are past the line (Edge / Anc. Edge), with the How picky slider.">
      Signals: <select id="signalMode" class="mark-select" style="max-width:none;"><option value="consistency">Consistency (hit rates)</option><option value="edge">Average edge</option></select>
    </label>
  </div>
  <div class="controls">
    <span class="muted">Stat:</span>
    <button class="stat-btn active" data-stat="ALL">All</button>
    {stat_buttons}
    <span class="muted" style="margin-left:auto;">Rank: 1 = toughest matchup for this stat, 32 = easiest &middot; Click a player's name for their full stat card &middot; Click their Opp for that defense's card</span>
  </div>
  <div id="gameScriptPanel" class="gs-panel" style="display:none;"></div>
  <table id="tbl">
    <thead>
      <tr>
        <th data-key="mark_rank" title="Click to sort: &#9989; bets first, then &#127765; watching, then unmarked, then &#10060; passes. Your own marker for this bet -- &#9989; if you've bet it, &#127765; if you're still watching it, &#10060; if you're passing. This is separate from &#128293;/&#129482;/&#10067; (which this dashboard computes for you); it's yours, saved in this browser only, and survives a data refresh (python3 run.py) since it isn't part of the regenerated file. Use the 'Hide &#10060; rows' checkbox above to get passed-on rows out of the way. Pick &#9989; Bet it and a slip appears where you can record the side, line, and odds you actually got (the grey hints are just today's best available line/price).">Mark</th>
        <th data-key="player">Player</th>
        <th data-key="position">Pos</th>
        <th data-key="team">Team</th>
        <th data-key="opponent">Opp</th>
        <th data-key="stat_label" title="Which prop this row is -- every other number on the row (Avg, Opp Allows, Edge, the book lines, the signal) is about this stat.">Stat</th>
        <th data-key="recent_avg" id="th-recent-avg">Avg (L5)</th>
        <th data-key="def_avg_allowed">Opp Allows</th>
        <th data-key="def_rank" title="1 = the toughest defense against this position/stat (allows the least), higher = easier. Color is a red-to-green gradient across the full range, so a rank near either end stands out more the closer it gets to 1 or the max.">Opp Rank</th>
        <th data-key="hit_pct" title="How often HE has cleared the line, on the side shown (O/U), over the selected weeks -- e.g. O 4/4 = over in all 4 games. Hover for his games and his worst game vs the line. Green = 75%+, red = under 50%.">Hit</th>
        <th data-key="def_hit_pct" title="How often THIS DEFENSE has allowed it: each of the opponent's games over the selected weeks, scaled to his usual share of his team's production at his position, checked against the same line. Hover for the per-game numbers.">Opp Hit</th>
        <th data-key="share" title="This player's share of their team's own production at this position/stat, over the selected sample size (RB rushing = RBs only, receiving = same position only)">Team Share</th>
        <th data-key="anticipated" title="Team Share % x Opp Allows -- a projection of this player's stat based on their typical share of team production against what the upcoming opponent allows to this position">Anticipated</th>
        <th data-key="edge" title="Recent Avg minus the most advantageous available line for whichever side (Over/Under) Recent Avg favors -- the lowest DK/FanDuel/BetMGM line for an Over, the highest for an Under. That book is highlighted in green below. Falls back to the consensus line if Recent Avg ties it exactly.">Edge</th>
        <th data-key="anc_edge" title="Anticipated minus that same shopped line -- Edge and Anc. Edge are graded against the same book/number, since they're two ways of sizing up one candidate bet.">Anc. Edge</th>
        <th data-key="signal_rank" title="1-3 &#128293; = Edge and Anc. Edge both significantly positive (a good OVER candidate) -- more flames means a bigger agreed-upon edge. 1-3 &#129482; = the mirror image, both significantly negative (a good UNDER candidate). &#11088; MUST BET = a 4th, much rarer tier above 3 -- both Edge and Anc. Edge clear a FIXED, deliberately extreme bar (100% -- recent form running at 2x the sportsbook's own line) in the same direction, AND the player has never landed on the wrong side of that line anywhere in your selected weeks, AND the matchup fits (Over: opponent is one of the 10 defenses allowing the most of this stat; Under: one of the 10 allowing the least), AND his games are consistent (standard deviation no more than 50% of the line). 3 flames/ice need the same matchup and consistency, otherwise they're held at 2 (marked with a small arrow). This bar does NOT move with the &quot;How picky&quot; slider below -- Trevor's ask was that MUST BET always mean the same absurd thing, while 1/2/3 stars keep flexing with the slider. &#10067; = one of Edge/Anc. Edge is significant on its own and the other isn't confirming it, but also isn't contradicting it (not on the opposite side of zero) -- worth a look. This is the table's default sort: MUST BET rows first, then 3-flame/3-ice, then 2s, then 1s, then &#10067;, then everything else.">&#128293;/&#129482;/&#11088;</th>
        <th data-key="draftkings_line">DraftKings</th>
        <th data-key="fanduel_line">FanDuel</th>
        <th data-key="betmgm_line">BetMGM</th>
        <th data-key="wind_mph" title="Forecast at the home team's stadium for kickoff (domes/retractable roofs show 'Dome'). Red = bad weather: very cold, high wind, or a meaningful rain/snow chance. Amber = elevated wind, not yet bad enough to flag red.">Weather</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
</div>
<div class="modal-overlay" id="playerModalOverlay">
  <div class="modal-panel">
    <div class="modal-header">
      <h2 id="modalPlayerName"></h2>
      <button class="modal-close" id="modalClose" aria-label="Close">&times;</button>
    </div>
    <div class="modal-meta" id="modalMeta"></div>
    <div id="modalBody"></div>
  </div>
</div>
<script>
const ROWS = {rows_json};
const DEFENSE_LOGS = {defense_logs_json};
const DEFENSE_GAMES = {defense_games_json};
const STAT_CATALOG = {stat_catalog_json};
const COVERAGE = {coverage_json};
const GAMES = {games_json};
const TEAM_RESULTS = {team_results_json};
const INJ_BY_TEAM = {injuries_by_team_json};
const WEEK = {week};
const ODDS_TIME = "{odds_time}";
const ODDS_TIME_UTC = "{odds_time_utc}"; // same moment, with timezone, for "Lines Xm old"
const SEASON = {season};
const RULE_NUMS = {rule_nums_json}; // Python-side thresholds, for the My rules page
const TOTAL_WEEKS = 18;
let activePos = "ALL";
let activeStat = "ALL";
let activeGame = "ALL";
let hideMarkedX = true; // starts ticked on every load (2026-10-16, per Trevor)
let hideReview = false;
let ladderOnly = false;
let altOnly = false; // ⬆ Alt lines only (2026-10-30, per Trevor: "make a filter for the alts. would be a fun thing to parlay")
let weakMatchupOnly = false;
let strongMatchupOnly = false;

// Game filter (added 2026-09-24 per Trevor: "make a filter so i can
// choose to select by game"). GAMES (this week's real schedule, sourced
// from stats_cache.json's schedule_this_week -- see build_games_list() in
// build_dashboard.py) gives the dropdown's options; a row's own game is
// identified the same way, AWAY@HOME, from data already on every row
// (team/opponent/at_opponent) -- no extra field needed per row.
function gameKey(r) {{
  return r.at_opponent ? (r.team + '@' + r.opponent) : (r.opponent + '@' + r.team);
}}

// "Thu 9/25 8:15p ATL @ GB" -- built from the game's plain gameday
// (YYYY-MM-DD) / gametime (24h HH:MM) strings. Parsed as a local
// calendar date (not through Date.parse, which would treat a bare
// YYYY-MM-DD as UTC midnight and can print the wrong weekday depending
// on the browser's timezone).
function formatGameLabel(g) {{
  let dayLabel = g.gameday || '';
  let month = null, day = null;
  if (g.gameday) {{
    const [y, m, d] = g.gameday.split('-').map(Number);
    month = m; day = d;
    const dt = new Date(y, m - 1, d);
    const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    dayLabel = DAY_NAMES[dt.getDay()] + ' ' + m + '/' + d;
  }}
  let timeLabel = '';
  if (g.gametime) {{
    const [hh, mm] = g.gametime.split(':').map(Number);
    const hour12 = ((hh + 11) % 12) + 1;
    const ampm = hh >= 12 ? 'p' : 'a';
    timeLabel = ' ' + hour12 + (mm ? ':' + String(mm).padStart(2, '0') : '') + ampm;
  }}
  return `${{dayLabel}}${{timeLabel}} ${{g.away}} @ ${{g.home}}`;
}}

// Unlike the bet marks above (meant to persist all week, and even across
// re-syncs within the same week), the Game filter is a short-lived
// "just show me this one game right now" convenience -- so it resets on
// its own rather than sticking around. Trevor's own rule: "reset on
// tuesday after the monday night game is complete." NFL weeks turn over
// on Tuesday in practice (that's when rosters/opponents change), and by
// Tuesday morning even a late Monday Night game has long finished, so
// this resets at the most recent Tuesday 3am (a few hours' buffer past a
// very late MNF final -- Claude's own reasonable-looking buffer, not an
// official cutoff, same caveat as this dashboard's other picked
// constants). Deliberately calendar-based rather than tied to the WEEK
// value baked into this file, so it resets even if you reopen an old
// dashboard.html you haven't re-built yet for the new week.
const GAME_FILTER_STORAGE_KEY = 'nfl_prop_dashboard_game_filter_v1';

function currentResetMarker() {{
  const now = new Date();
  const marker = new Date(now);
  marker.setHours(3, 0, 0, 0);
  const day = marker.getDay(); // 0=Sun .. 2=Tue .. 6=Sat
  let diff = (day - 2 + 7) % 7;
  if (diff === 0 && now < marker) diff = 7; // it's Tuesday but before 3am -- still last week's cycle
  marker.setDate(marker.getDate() - diff);
  return marker.toISOString();
}}

function loadGameFilter() {{
  try {{
    const saved = JSON.parse(localStorage.getItem(GAME_FILTER_STORAGE_KEY) || 'null');
    if (saved && saved.resetMarker === currentResetMarker()) return saved.game;
  }} catch (e) {{ /* private window, blocked storage, corrupted value -- just start at All Games */ }}
  return 'ALL';
}}

function saveGameFilter(game) {{
  try {{
    localStorage.setItem(GAME_FILTER_STORAGE_KEY, JSON.stringify({{ game, resetMarker: currentResetMarker() }}));
  }} catch (e) {{ /* storage full/blocked -- filter still applies for this page load, just won't survive a reload */ }}
}}

// Builds the dropdown's options from this week's real schedule and
// restores whatever was saved (if it's still within the same reset
// cycle AND still one of this week's actual games -- a saved value from
// a week whose teams don't match this build's GAMES falls back to "All
// Games" automatically, same safety net as a stale sample-size setting
// would need).
function populateGameFilter() {{
  const sel = document.getElementById('gameFilter');
  if (!sel) return;
  const options = ['<option value="ALL">All Games</option>'].concat(
    GAMES.map(g => `<option value="${{escapeHtml(g.key)}}">${{escapeHtml(formatGameLabel(g))}}</option>`)
  );
  sel.innerHTML = options.join('');
  activeGame = loadGameFilter();
  if (activeGame !== 'ALL' && !GAMES.some(g => g.key === activeGame)) activeGame = 'ALL';
  sel.value = activeGame;
}}

// Personal bet marks (added 2026-09-22, per Trevor): a per-row ✅ (bet
// it) / 🌕 (watching) / ❌ (pass) marker that's YOURS, not part of the
// fetched data -- separate from the 🔥/🧊/❓ signals this dashboard
// computes for you. Lives in this browser's localStorage, keyed by
// week+player+team+stat, NOT baked into the generated HTML -- so
// re-running `python3 run.py` (which fully regenerates this file from
// scratch every time) does NOT wipe your marks, as long as you keep
// opening the dashboard from this same file location in this same
// browser. Deliberately kept simple, per Trevor -- no export/import
// backup, no cross-browser/cross-machine sync, no undo history: just
// this browser remembering what you clicked. Clearing this browser's
// site data for this file, or opening the dashboard from a different
// browser or a moved/renamed copy of the file, starts you with a blank
// slate again, since none of that carries the localStorage bucket with
// it.
const MARKS_STORAGE_KEY = 'nfl_prop_dashboard_marks_v1';
function loadMarks() {{
  try {{
    return JSON.parse(localStorage.getItem(MARKS_STORAGE_KEY) || '{{}}');
  }} catch (e) {{
    return {{}}; // private window, blocked storage, corrupted value, etc. -- just start blank
  }}
}}
function saveMarks() {{
  try {{
    localStorage.setItem(MARKS_STORAGE_KEY, JSON.stringify(MARKS));
  }} catch (e) {{
    // storage full/blocked -- the mark still shows for this page load via
    // the in-memory MARKS object, it just won't survive a reload
  }}
  scheduleSync(); // no-op unless signed in (see "Sign-in + cross-device sync")
}}
let MARKS = loadMarks();

// Week is included in the key so a mark never leaks onto a DIFFERENT
// week's version of what looks like "the same" player+stat row -- each
// week's slate starts unmarked, while re-syncing WITHIN the same week
// (same WEEK value) keeps every mark you've already set.
function markKey(r) {{
  return WEEK + '|' + r.player + '|' + r.team + '|' + r.stat_col;
}}

// Bet details (added 2026-09-28, per Trevor: "add a space for me to
// record what line and odds i got a specific bet at"). When a row is
// marked ✅ Bet it, a small slip appears under the Mark selector: Over/
// Under, the line you got, and the odds you got. Same storage model as the
// marks above -- this browser's localStorage, keyed by the same
// week+player+team+stat key, so it survives `python3 run.py` rebuilds and
// each new week starts clean. The boxes start EMPTY: the grey placeholder
// is just today's best available line/price for the side the numbers
// favor, as a hint -- nothing is recorded until you type it.
const BETS_STORAGE_KEY = 'nfl_prop_dashboard_bets_v1';
function loadBets() {{
  try {{
    return JSON.parse(localStorage.getItem(BETS_STORAGE_KEY) || '{{}}');
  }} catch (e) {{
    return {{}};
  }}
}}
function saveBets() {{
  try {{
    localStorage.setItem(BETS_STORAGE_KEY, JSON.stringify(BETS));
  }} catch (e) {{
    // storage blocked/full -- kept in memory for this page load only
  }}
  scheduleSync();
}}
let BETS = loadBets();

// ---- Sign-in + cross-device sync (added 2026-10-16, per Trevor: "login so
// my bets sync across devices"). Supabase email magic link, plus one row
// per user in public.user_state holding {{marks, bets}}. Signed out, nothing
// changes: localStorage only, exactly as before. Signed in, every
// saveMarks()/saveBets() also pushes to the account (debounced), and the
// account copy is pulled in on load and whenever the tab comes back into
// view. The merge is three-way against the last copy this browser synced
// (SYNC_BASE), so a bet removed on the phone stays removed on the laptop,
// and different bets edited on two devices both survive. First sign-in on
// a device has an empty base, so everything on this device is ADDED to the
// account and nothing is deleted. Hidden entirely until SUPABASE_URL /
// SUPABASE_ANON_KEY are set in build_dashboard.py, and on the Mac's
// file:// copy (the emailed link can only open the shared site).
const SUPABASE_CFG = {supabase_config_json};
const SUPABASE_JS_URL = 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.45.4/dist/umd/supabase.js';
const LIVE_SITE_URL = 'https://trevorrancourt.github.io/nfl-prop-dashboard/';
let sb = null;            // Supabase client, once the library loads
let syncUser = null;      // signed-in user, or null
let syncTimer = null;
let syncBusy = false;
let syncAgain = false;
let syncSuppress = false; // true while writing synced data back to localStorage
let syncStatus = '';      // '', 'saving', 'ok', 'error', 'offline'

function syncEnabled() {{
  return !!(SUPABASE_CFG && SUPABASE_CFG.url && SUPABASE_CFG.key) && location.protocol.startsWith('http');
}}
function syncBaseKey() {{
  return 'nfl_prop_dashboard_sync_base_v1|' + (syncUser ? syncUser.id : '');
}}
function loadSyncBase() {{
  try {{
    const v = JSON.parse(localStorage.getItem(syncBaseKey()) || 'null');
    if (v && v.marks && v.bets) return v;
  }} catch (e) {{}}
  return {{ marks: {{}}, bets: {{}} }};
}}
function saveSyncBase(b) {{
  try {{ localStorage.setItem(syncBaseKey(), JSON.stringify(b)); }} catch (e) {{}}
}}
function cloneJson(o) {{ return JSON.parse(JSON.stringify(o)); }}
// Key-order-independent JSON: the database stores objects with its own key
// order, so plain JSON.stringify would call every bet "changed".
function stableStr(v) {{
  if (v === null || typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return '[' + v.map(stableStr).join(',') + ']';
  return '{{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + stableStr(v[k])).join(',') + '}}';
}}
// Applies the edits that turned `from` into `to` onto `target` (in place).
function applyDiff(target, from, to) {{
  for (const k of Object.keys(to)) {{
    if (stableStr(to[k]) !== stableStr(from[k])) target[k] = cloneJson(to[k]);
  }}
  for (const k of Object.keys(from)) {{
    if (!(k in to)) delete target[k];
  }}
  return target;
}}
function sameMap(a, b) {{
  const ka = Object.keys(a), kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  return ka.every(k => (k in b) && stableStr(a[k]) === stableStr(b[k]));
}}
function replaceContents(obj, src) {{
  for (const k of Object.keys(obj)) delete obj[k];
  Object.assign(obj, src);
}}

function scheduleSync(delay) {{
  if (!syncUser || syncSuppress) return;
  clearTimeout(syncTimer);
  syncTimer = setTimeout(syncNow, delay === undefined ? 1500 : delay);
  setSyncStatus('saving');
}}

async function syncNow() {{
  if (!syncUser || !sb) return;
  if (syncBusy) {{ syncAgain = true; return; }}
  syncBusy = true;
  const user = syncUser;
  try {{
    const base = loadSyncBase();
    const snap = {{ marks: cloneJson(MARKS), bets: cloneJson(BETS) }};
    let merged = null;
    // Write only if the account row is still the one we read (same
    // updated_at); if another device saved in between, re-read and re-merge
    // so neither device's edits or deletes get overwritten.
    for (let attempt = 0; attempt < 4 && !merged; attempt++) {{
      const res = await sb.from('user_state').select('marks,bets,updated_at').eq('user_id', user.id).maybeSingle();
      if (res.error) throw res.error;
      const remote = {{ marks: (res.data && res.data.marks) || {{}}, bets: (res.data && res.data.bets) || {{}} }};
      const m = {{
        marks: applyDiff(cloneJson(remote.marks), base.marks, snap.marks),
        bets: applyDiff(cloneJson(remote.bets), base.bets, snap.bets),
      }};
      if (res.data && sameMap(m.marks, remote.marks) && sameMap(m.bets, remote.bets)) {{ merged = m; break; }}
      const row = {{ marks: m.marks, bets: m.bets, updated_at: new Date().toISOString() }};
      if (res.data) {{
        const up = await sb.from('user_state').update(row).eq('user_id', user.id).eq('updated_at', res.data.updated_at).select('user_id');
        if (up.error) throw up.error;
        if (up.data && up.data.length) merged = m;
      }} else {{
        row.user_id = user.id;
        const ins = await sb.from('user_state').insert(row);
        if (!ins.error) merged = m;
        else if (ins.error.code !== '23505') throw ins.error; // 23505 = another device created the row first
      }}
    }}
    if (!merged) throw new Error('account kept changing; will retry');
    if (syncUser !== user) return; // signed out while this was running
    saveSyncBase(merged);
    // Anything typed while this was in flight is layered back on top.
    const nextMarks = applyDiff(cloneJson(merged.marks), snap.marks, MARKS);
    const nextBets = applyDiff(cloneJson(merged.bets), snap.bets, BETS);
    if (!sameMap(nextMarks, MARKS) || !sameMap(nextBets, BETS)) {{
      replaceContents(MARKS, nextMarks);
      replaceContents(BETS, nextBets);
      syncSuppress = true;
      try {{ saveMarks(); saveBets(); }} finally {{ syncSuppress = false; }}
      refreshAfterSync();
    }}
    setSyncStatus('ok');
  }} catch (err) {{
    console.warn('Sync failed (your marks/bets are still saved in this browser):', err);
    setSyncStatus('error');
  }} finally {{
    syncBusy = false;
    if (syncAgain) {{ syncAgain = false; scheduleSync(300); }}
  }}
}}

// Redraws with the merged data, but never yanks the cursor out of a bet
// slip you're typing in -- waits until you leave the box.
function refreshAfterSync() {{
  const a = document.activeElement;
  if (a && a !== document.body && (a.tagName === 'INPUT' || a.tagName === 'SELECT' || a.tagName === 'TEXTAREA') && !a.closest('#syncCtl')) {{
    a.addEventListener('blur', () => setTimeout(refreshAfterSync, 0), {{ once: true }});
    return;
  }}
  render();
  updateMyBetsButton();
  if (myBetsOpen) openMyBetsModal();
}}

function syncStatusText() {{
  if (syncStatus === 'saving') return 'Syncing&hellip;';
  if (syncStatus === 'ok') return 'Synced';
  if (syncStatus === 'error') return "Couldn't sync &middot; saved on this device, will retry";
  if (syncStatus === 'offline') return 'Sign-in unavailable right now';
  return '';
}}
function setSyncStatus(s) {{
  syncStatus = s;
  const el = document.getElementById('syncStatus');
  if (el) el.innerHTML = syncStatusText();
}}
function renderSyncCtl() {{
  const ctl = document.getElementById('syncCtl');
  if (!ctl) return;
  if (syncUser) {{
    ctl.innerHTML = `<span class="muted" title="Your marks and bets are saved to your account and show up on any device where you sign in.">&#9729;&#65039; ${{escapeHtml(syncUser.email || 'Signed in')}} &middot; <span id="syncStatus">${{syncStatusText()}}</span></span>
      <button type="button" class="weeks-mini-btn" id="alertsBtn" title="Get your own phone alerts: new MUST BET / 3-star picks, plus your Watching list when lines move.">&#128276; Alerts${{alertTopic ? ' on' : ''}}</button>
      <button type="button" class="weeks-mini-btn" id="syncSignOut">Sign out</button>
      <span id="refreshCtl" style="display:none; margin-left:6px;"></span>
      <span id="alertsForm" style="display:none;">
        <input type="text" id="alertsTopic" placeholder="ntfy topic" autocomplete="off" spellcheck="false" style="background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:5px 8px; font-size:13px; width:200px;">
        <button type="button" class="weeks-mini-btn" id="alertsSave">Save</button>
        <button type="button" class="weeks-mini-btn" id="alertsTest">Send test</button>
        <span id="alertsMsg" class="muted"></span>
      </span>`;
  }} else {{
    ctl.innerHTML = `<button type="button" class="pos-btn" id="syncSignInBtn" title="Sign in with your email to keep your marks and bets in sync across your phone, laptop, etc. Without signing in they stay in this browser only.">&#9729;&#65039; Sign in to sync</button>
      <span id="syncForm" style="display:none;">
        <input type="email" id="syncEmail" placeholder="you@email.com" autocomplete="email" style="background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:5px 8px; font-size:13px; width:190px;">
        <button type="button" class="weeks-mini-btn" id="syncSend">Email me a sign-in link</button>
      </span>
      <span id="syncStatus" class="muted">${{syncStatus === 'offline' ? syncStatusText() : ''}}</span>`;
  }}
}}

// ---- Per-person phone alerts (added 2026-10-16, per Trevor: "i want the
// others to get the alerts when they sign in"). Signed-in users pick their
// own ntfy topic here; it's saved in public.alert_prefs (row-level security:
// only you can read or change yours). scripts/notify.py then sends each
// person their own NEW + WATCHING alert from their own marks.
let alertTopic = null;      // saved topic, '' if none, null until loaded
let alertsAvailable = true; // false if the alert_prefs table isn't set up
function suggestTopic() {{
  const abc = 'abcdefghijkmnpqrstuvwxyz23456789';
  let s = 'nfl-props-';
  for (let i = 0; i < 10; i++) s += abc[Math.floor(Math.random() * abc.length)];
  return s;
}}
function validTopic(t) {{ return /^[-_A-Za-z0-9]{{1,64}}$/.test(t); }}
async function loadAlertPrefs() {{
  if (!sb || !syncUser) return;
  const user = syncUser;
  const res = await sb.from('alert_prefs').select('ntfy_topic').eq('user_id', user.id).maybeSingle();
  if (syncUser !== user) return;
  if (res.error) {{ alertsAvailable = false; alertTopic = ''; }}
  else alertTopic = (res.data && res.data.ntfy_topic) || '';
  renderAlertsBtn();
}}
function renderAlertsBtn() {{
  const b = document.getElementById('alertsBtn');
  if (b) b.innerHTML = '&#128276; Alerts' + (alertTopic ? ' on' : '');
}}
function openAlertsForm() {{
  const f = document.getElementById('alertsForm');
  if (!f) return;
  if (f.style.display !== 'none') {{ f.style.display = 'none'; return; }}
  f.style.display = '';
  const msg = document.getElementById('alertsMsg');
  if (!alertsAvailable) {{
    f.innerHTML = '<span class="muted">Phone alerts aren&#39;t set up on this site yet.</span>';
    return;
  }}
  const input = document.getElementById('alertsTopic');
  input.value = alertTopic || suggestTopic();
  msg.innerHTML = alertTopic
    ? 'Alerts go to this ntfy topic. Clear it and Save to stop them.'
    : 'Get the free <b>ntfy</b> app, tap + and subscribe to this topic name (or type your own), then Save. Anyone who knows the name can read it, so keep it hard to guess.';
}}
async function saveAlertTopic() {{
  const input = document.getElementById('alertsTopic');
  const msg = document.getElementById('alertsMsg');
  const t = (input.value || '').trim();
  if (t && !validTopic(t)) {{ msg.textContent = 'Use only letters, numbers, - and _ (up to 64).'; return; }}
  if (!sb || !syncUser) return;
  msg.textContent = 'Saving...';
  const res = await sb.from('alert_prefs').upsert({{ user_id: syncUser.id, ntfy_topic: t || null, updated_at: new Date().toISOString() }});
  if (res.error) {{ msg.textContent = "Couldn't save: " + res.error.message; return; }}
  alertTopic = t;
  renderAlertsBtn();
  msg.textContent = t
    ? 'Saved. You will get NEW picks and your Watching list after each refresh (about every 3 hours) when something changes.'
    : 'Alerts turned off.';
}}
async function testAlert() {{
  const t = (document.getElementById('alertsTopic').value || '').trim();
  const msg = document.getElementById('alertsMsg');
  if (!validTopic(t)) {{ msg.textContent = 'Type a topic first.'; return; }}
  try {{
    const r = await fetch('https://ntfy.sh/' + t, {{ method: 'POST', body: 'Test alert from the NFL prop dashboard. If you see this, you are subscribed.', headers: {{ Title: 'NFL props: test alert' }} }});
    msg.textContent = r.ok ? 'Test sent. Check the ntfy app (it only shows up if you subscribed to this exact topic).' : 'Test failed (' + r.status + ').';
  }} catch (e) {{
    msg.textContent = "Couldn't reach ntfy.";
  }}
}}

// ---- One-tap "Refresh lines" (added 2026-10-16, per Trevor). Calls the
// refresh-lines Supabase Edge Function (supabase/functions/refresh-lines),
// which holds the GitHub token and starts the Update dashboard workflow.
// Only shown to signed-in users on the function's ALLOWED_EMAILS list, and
// hidden entirely if the function isn't deployed. Each refresh costs ~130
// Odds API credits.
let refreshAllowed = false;
let refreshState = '';    // '', 'running', 'done', 'failed', 'error'
let refreshMsg = '';
let refreshTapAt = 0;
let refreshPoll = null;
function linesAgeText() {{
  const t = Date.parse(ODDS_TIME_UTC);
  if (!ODDS_TIME_UTC || isNaN(t)) return '';
  const m = Math.max(0, Math.round((Date.now() - t) / 60000));
  const age = m < 60 ? m + 'm' : (m < 1440 ? Math.floor(m / 60) + 'h ' + (m % 60) + 'm' : Math.floor(m / 1440) + 'd');
  return 'Lines ' + age + ' old';
}}
function renderRefresh() {{
  const el = document.getElementById('refreshCtl');
  if (!el) return;
  if (!refreshAllowed) {{ el.style.display = 'none'; el.innerHTML = ''; return; }}
  el.style.display = '';
  let html = '';
  if (refreshState === 'running') {{
    html = '<span class="muted">&#128260; ' + escapeHtml(refreshMsg || 'Refreshing lines… usually 3-4 min') + '</span>';
  }} else if (refreshState === 'done') {{
    html = '<button type="button" class="weeks-mini-btn" id="refreshReload">&#9989; New lines ready &middot; Reload</button>';
  }} else {{
    html = `<button type="button" class="weeks-mini-btn" id="refreshBtn" title="Pull fresh odds and rebuild the board now (takes 3-4 minutes, uses about 130 Odds API credits).">&#128260; Refresh lines</button>`;
    if (refreshMsg) html += ' <span class="muted">' + escapeHtml(refreshMsg) + '</span>';
  }}
  html += ' <span class="muted" id="linesAge">' + linesAgeText() + '</span>';
  el.innerHTML = html;
}}
async function callRefresh(method) {{
  const res = await sb.functions.invoke('refresh-lines', {{ method: method }});
  if (res.error) throw res.error;
  return res.data || {{}};
}}
async function loadRefreshStatus() {{
  if (!sb || !syncUser) return;
  const user = syncUser;
  let d;
  try {{ d = await callRefresh('GET'); }} catch (e) {{ return; }} // not deployed -- no button
  if (syncUser !== user) return;
  refreshAllowed = !!d.allowed;
  if (d.allowed && d.running && refreshState !== 'running') {{
    refreshState = 'running';
    refreshMsg = 'A refresh is already running…';
    refreshTapAt = d.run ? Date.parse(d.run.created_at) : Date.now();
    startRefreshPoll();
  }}
  renderRefresh();
}}
function startRefreshPoll() {{
  clearInterval(refreshPoll);
  refreshPoll = setInterval(checkRefresh, 20000);
}}
async function checkRefresh() {{
  let d;
  try {{ d = await callRefresh('GET'); }} catch (e) {{ return; }}
  const run = d.run;
  const ours = run && Date.parse(run.created_at) >= refreshTapAt - 30000;
  if (ours && !d.running) {{
    clearInterval(refreshPoll);
    if (run.conclusion === 'success') {{ refreshState = 'done'; refreshMsg = ''; }}
    else {{ refreshState = 'failed'; refreshMsg = 'Refresh failed (' + (run.conclusion || 'unknown') + '). Try again later.'; }}
  }} else if (Date.now() - refreshTapAt > 15 * 60000) {{
    clearInterval(refreshPoll);
    refreshState = 'failed';
    refreshMsg = 'Still not done after 15 min. Check the Actions tab on GitHub.';
  }} else if (ours) {{
    refreshMsg = 'Refreshing lines… ' + Math.max(1, Math.round((Date.now() - refreshTapAt) / 60000)) + ' min so far (usually 3-4)';
  }}
  renderRefresh();
}}
async function startRefresh() {{
  refreshState = 'running';
  refreshMsg = 'Starting…';
  renderRefresh();
  let d;
  try {{ d = await callRefresh('POST'); }} catch (e) {{ d = {{ error: (e && e.message) || 'request failed' }}; }}
  if (d.error || !d.allowed) {{
    refreshState = 'error';
    refreshMsg = "Couldn't start: " + (d.error || 'not allowed for this account');
  }} else {{
    refreshTapAt = d.started ? Date.now() : (d.run ? Date.parse(d.run.created_at) : Date.now());
    refreshMsg = d.started ? 'Refreshing lines… usually 3-4 min' : 'A refresh is already running…';
    startRefreshPoll();
  }}
  renderRefresh();
}}
setInterval(() => {{
  const el = document.getElementById('linesAge');
  if (el) el.textContent = linesAgeText();
}}, 60000);

async function sendMagicLink() {{
  const input = document.getElementById('syncEmail');
  const msg = document.getElementById('syncStatus');
  const btn = document.getElementById('syncSend');
  const email = (input.value || '').trim();
  if (email.indexOf('@') < 1) {{ msg.textContent = 'Type your email first.'; return; }}
  if (!sb) {{ msg.textContent = 'Still loading, try again in a second.'; return; }}
  btn.disabled = true;
  msg.textContent = 'Sending...';
  const res = await sb.auth.signInWithOtp({{ email: email, options: {{ emailRedirectTo: location.origin + location.pathname }} }});
  btn.disabled = false;
  msg.textContent = res.error
    ? "Couldn't send: " + res.error.message
    : 'Check your email and tap the link. Open it in this same browser.';
}}

function onAuthChange(session) {{
  const u = session ? session.user : null;
  if ((u ? u.id : null) === (syncUser ? syncUser.id : null)) return;
  syncUser = u;
  syncStatus = '';
  alertTopic = null;
  alertsAvailable = true;
  refreshAllowed = false;
  renderSyncCtl();
  if (u) setTimeout(() => {{ syncNow(); loadAlertPrefs(); loadRefreshStatus(); }}, 0); // not inside the auth callback (supabase-js can deadlock)
  if (myBetsOpen) openMyBetsModal();
}}

function initSync() {{
  const ctl = document.getElementById('syncCtl');
  if (!ctl || !syncEnabled()) return;
  ctl.style.display = '';
  renderSyncCtl();
  // A sign-in link that expired or was already used comes back with an error in the URL.
  const hash = new URLSearchParams(location.hash.replace(/^#/, ''));
  const linkError = hash.get('error_description');
  ctl.addEventListener('click', e => {{
    const t = e.target;
    if (t.id === 'syncSignInBtn') {{
      const f = document.getElementById('syncForm');
      f.style.display = f.style.display === 'none' ? '' : 'none';
      if (f.style.display === '') document.getElementById('syncEmail').focus();
    }} else if (t.id === 'syncSend') {{
      sendMagicLink();
    }} else if (t.id === 'refreshBtn') {{
      startRefresh();
    }} else if (t.id === 'refreshReload') {{
      location.reload();
    }} else if (t.id === 'alertsBtn') {{
      openAlertsForm();
    }} else if (t.id === 'alertsSave') {{
      saveAlertTopic();
    }} else if (t.id === 'alertsTest') {{
      testAlert();
    }} else if (t.id === 'syncSignOut') {{
      // Signing out keeps everything on this device; it just stops syncing.
      if (sb) sb.auth.signOut();
    }}
  }});
  ctl.addEventListener('keydown', e => {{
    if (e.key === 'Enter' && e.target.id === 'syncEmail') sendMagicLink();
    if (e.key === 'Enter' && e.target.id === 'alertsTopic') saveAlertTopic();
  }});
  const s = document.createElement('script');
  s.src = SUPABASE_JS_URL;
  s.onload = () => {{
    try {{
      sb = window.supabase.createClient(SUPABASE_CFG.url, SUPABASE_CFG.key);
    }} catch (err) {{
      console.warn('Supabase init failed:', err);
      setSyncStatus('offline');
      return;
    }}
    sb.auth.onAuthStateChange((event, session) => {{
      onAuthChange(session);
      if (session && /access_token|refresh_token/.test(location.hash)) {{
        history.replaceState(null, '', location.pathname + location.search);
      }}
    }});
    if (linkError) {{
      history.replaceState(null, '', location.pathname + location.search);
      const msg = document.getElementById('syncStatus');
      if (msg && !syncUser) msg.textContent = 'That sign-in link didn’t work (' + linkError + '). Send a new one.';
    }}
  }};
  s.onerror = () => setSyncStatus('offline');
  document.head.appendChild(s);
  document.addEventListener('visibilitychange', () => {{
    if (document.visibilityState === 'visible' && syncUser) scheduleSync(0);
  }});
}}

function validBetLine(s) {{
  return s === undefined || s === '' || /^\d+(\.\d+)?$/.test(String(s).trim());
}}
// American odds: -110, +125, 120 (no sign = plus). Anything between -99
// and +99 isn't a real American price, so it's flagged.
// Odds boxes use the normal keyboard, since a phone's number pad has no
// minus key (2026-10-16, per Trevor: "on mobile, i can't add a minus before
// the odds"). Phones can also swap a typed minus for a long dash, so
// those count as a minus too.
function normOdds(s) {{
  return String(s === undefined || s === null ? '' : s).trim().replace(/^[\u2212\u2013\u2014]/, '-');
}}
function validBetOdds(s) {{
  if (s === undefined || s === '') return true;
  const t = normOdds(s);
  return /^[+-]?\d+$/.test(t) && Math.abs(parseInt(t, 10)) >= 100;
}}

function betSlip(r) {{
  const key = markKey(r);
  if (MARKS[key] !== 'bet') return '';
  const b = BETS[key] || {{}};
  const hintLine = (r.best_line !== null && r.best_line !== undefined) ? r.best_line : r.vegas_line;
  const hintOddsRaw = r.best_book
    ? bookCellPrice(r, r.best_book)
    : (r.direction === 'under' ? r.under_price : r.over_price);
  const hintOdds = (hintOddsRaw === null || hintOddsRaw === undefined) ? 'odds' : (hintOddsRaw > 0 ? '+' + hintOddsRaw : String(hintOddsRaw));
  const sideOpt = (v, label) => `<option value="${{v}}" ${{b.side === v ? 'selected' : ''}}>${{label}}</option>`;
  return `<div class="bet-slip" data-bet-key="${{escapeHtml(key)}}" title="What you actually got on this bet -- saved in this browser only.">
    <select class="bet-field" data-field="side">${{sideOpt('', 'O/U')}}${{sideOpt('over', 'Over')}}${{sideOpt('under', 'Under')}}</select>
    <input class="bet-field bet-line${{validBetLine(b.line) ? '' : ' bet-bad'}}" data-field="line" inputmode="decimal" placeholder="${{hintLine === null || hintLine === undefined ? 'line' : hintLine}}" value="${{escapeHtml(b.line || '')}}" aria-label="Line you got">
    <input class="bet-field bet-odds${{validBetOdds(b.odds) ? '' : ' bet-bad'}}" data-field="odds" inputmode="text" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" placeholder="${{hintOdds}}" value="${{escapeHtml(b.odds || '')}}" aria-label="Odds you got">
    <input class="bet-field bet-stake${{validBetStake(b.stake) ? '' : ' bet-bad'}}" data-field="stake" inputmode="decimal" placeholder="$" value="${{escapeHtml(b.stake || '')}}" aria-label="Dollar amount you bet">
    <span class="bet-towin muted">${{toWinLabel(b)}}</span>
  </div>`;
}}

// Saves one edited slip field. Doesn't re-render the table, so tabbing
// from Line to Odds keeps your cursor where it is.
function handleBetField(el) {{
  const slip = el.closest('[data-bet-key]');
  if (!slip) return;
  const key = slip.dataset.betKey;
  const field = el.dataset.field;
  const v = field === 'odds' ? normOdds(el.value) : el.value.trim();
  const b = BETS[key] || {{}};
  if (v) b[field] = v; else delete b[field];
  BETS[key] = b;
  if (!key.startsWith('manual|')) {{ ensureBetMeta(key); if (field === 'side') snapshotMarket(key); }}
  saveBets();
  if (field === 'line') el.classList.toggle('bet-bad', !validBetLine(v));
  if (field === 'odds') el.classList.toggle('bet-bad', !validBetOdds(v));
  if (field === 'stake') el.classList.toggle('bet-bad', !validBetStake(v));
  const tw = slip.querySelector('.bet-towin');
  if (tw) tw.textContent = toWinLabel(b);
  updateMyBetsButton();
}}

// ---- Bet tracking (added 2026-09-29, per Trevor: "a button up top ... to
// see all the bets i've taken in a popup", "dollar value ... next to where
// the line and odds are", "add in win or lose and you track the record and
// total profit", "static week over week"). ----
//
// Week over week: marks/bets were already keyed WEEK|player|team|stat and
// never pruned, so old weeks' entries stay in localStorage. What was
// missing is that once a new week's build drops last week's rows, there was
// nothing left to describe the bet with -- so each bet now also stores a
// small `meta` snapshot (season, week, player, team, opponent, stat) the
// first time it's touched, and the My Bets popup renders purely from
// BETS/MARKS, never from this week's ROWS. Bets saved before this change
// get their meta backfilled on page load (backfillBetMeta below).
//
// Manual bets ("manual|<timestamp>" keys) cover what isn't a single table
// row -- parlays, alt-line ladders, anything else. They carry a free-text
// description and a week instead of meta.
function validBetStake(s) {{
  return s === undefined || s === '' || /^\$?\d+(\.\d{{1,2}})?$/.test(String(s).trim());
}}
function parseStake(s) {{
  if (s === undefined || s === '' || !validBetStake(s)) return null;
  return parseFloat(String(s).replace('$', ''));
}}
function parseOdds(s) {{
  if (s === undefined || s === '' || !validBetOdds(s)) return null;
  return parseInt(normOdds(s), 10);
}}
// Profit if the bet wins (stake not included), from American odds.
function winAmount(stake, odds) {{
  if (stake === null || odds === null) return null;
  return odds > 0 ? stake * odds / 100 : stake * 100 / Math.abs(odds);
}}
function money(v, signed) {{
  if (v === null || v === undefined || isNaN(v)) return '-';
  const abs = Math.abs(v).toFixed(2);
  if (!signed) return '$' + abs;
  return (v > 0 ? '+$' : (v < 0 ? '-$' : '$')) + abs;
}}
function toWinLabel(b) {{
  const w = winAmount(parseStake(b.stake), parseOdds(b.odds));
  return w === null ? '' : 'to win ' + money(w);
}}
// Settled profit for one bet: null when it isn't settled yet, or when a
// win is missing the stake/odds needed to price it.
function betProfit(b) {{
  const stake = parseStake(b.stake);
  if (b.result === 'win') return winAmount(stake, parseOdds(b.odds));
  if (b.result === 'loss') return stake === null ? null : -stake;
  if (b.result === 'push' || b.result === 'void') return 0;
  return null;
}}

function parseBetKey(key) {{
  const parts = key.split('|');
  return {{ week: parseInt(parts[0], 10), player: parts[1], team: parts[2], stat_col: parts[3] }};
}}
function statLabelFor(statCol) {{
  const r = ROWS.find(x => x.stat_col === statCol);
  return r ? r.stat_label : statCol;
}}
// Fills BETS[key].meta once, from the live row when it's this week's
// bet, otherwise from the key itself plus the player's game log (which
// has the opponent for any week already played).
function ensureBetMeta(key) {{
  const b = BETS[key] || (BETS[key] = {{}});
  if (b.meta) return;
  const k = parseBetKey(key);
  const live = ROWS.find(r => markKey(r) === key);
  if (live) {{
    b.meta = {{ season: SEASON, week: k.week, player: live.player, team: live.team, opp: live.opponent,
      at: !!live.at_opponent, pos: live.position, stat_col: live.stat_col, stat_label: live.stat_label,
      kick: kickoffForTeam(live.team, k.week) }};
    return;
  }}
  let opp = null, pos = null;
  const any = ROWS.find(r => r.player === k.player && r.stat_col === k.stat_col);
  if (any) {{
    pos = any.position;
    const i = any.game_weeks.findIndex((w, j) => w === k.week && any.game_seasons[j] === SEASON);
    if (i >= 0) opp = any.game_opponents[i];
  }}
  b.meta = {{ season: SEASON, week: k.week, player: k.player, team: k.team, opp: opp, at: null,
    pos: pos, stat_col: k.stat_col, stat_label: statLabelFor(k.stat_col) }};
}}
// Kickoff ("YYYY-MM-DD HH:MM", ET) for a team's game in the given week --
// only knowable for this week's slate (GAMES), so it's saved onto each bet
// the first time it's seen and kept from then on (added 2026-10-04, per
// Trevor: show My Bets "in order of kickoffs").
function kickoffForTeam(team, week) {{
  if (week !== WEEK || !team) return null;
  const g = GAMES.find(g => g.home === team || g.away === team);
  return g && g.gameday ? g.gameday + ' ' + (g.gametime || '00:00') : null;
}}
function fmtKickoff(k) {{
  if (!k) return '';
  const [d, t] = k.split(' ');
  const day = new Date(d + 'T12:00:00').toLocaleDateString([], {{ weekday: 'short' }});
  let [h, m] = (t || '00:00').split(':').map(Number);
  const ap = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${{day}} ${{h}}:${{String(m).padStart(2, '0')}} ${{ap}} ET`;
}}
function backfillBetMeta() {{
  let changed = false;
  for (const [key, v] of Object.entries(MARKS)) {{
    if (v === 'bet' && !(BETS[key] && BETS[key].meta)) {{ ensureBetMeta(key); changed = true; }}
    const m = BETS[key] && BETS[key].meta;
    if (v === 'bet' && m && !m.kick) {{
      const k = kickoffForTeam(m.team, m.week);
      if (k) {{ m.kick = k; changed = true; }}
    }}
  }}
  if (changed) saveBets();
}}

// Every bet to show in the popup: rows still marked ✅ plus manual bets.
function allBets() {{
  const out = [];
  for (const [key, v] of Object.entries(MARKS)) {{
    if (v !== 'bet') continue;
    out.push({{ key, b: BETS[key] || {{}}, manual: false }});
  }}
  for (const [key, b] of Object.entries(BETS)) {{
    if (key.startsWith('manual|')) out.push({{ key, b, manual: true }});
  }}
  const wk = (x) => x.manual ? (parseInt(x.b.week, 10) || 0) : ((x.b.meta && x.b.meta.week) || parseBetKey(x.key).week);
  const ss = (x) => (x.b.meta && x.b.meta.season) || SEASON;
  const ko = (x) => (!x.manual && x.b.meta && x.b.meta.kick) || '9999';
  out.sort((a, c) => (ss(c) - ss(a)) || (wk(c) - wk(a)) || ko(a).localeCompare(ko(c)) || betTitle(a).localeCompare(betTitle(c)));
  out.forEach(x => {{ x.week = wk(x); x.season = ss(x); x.kick = ko(x) === '9999' ? null : ko(x); }});
  return out;
}}
function betTitle(x) {{
  if (x.manual) return x.b.desc || 'Manual bet';
  const m = x.b.meta || parseBetKey(x.key);
  return m.player + ' ' + (m.stat_label || statLabelFor(m.stat_col));
}}
// What actually happened, when the stat is in the data: this week's
// build carries every played game for players on this week's slate
// (a player on a bye this week won't have it -- enter those by hand).
function betActual(x) {{
  if (x.manual) return null;
  const m = x.b.meta || parseBetKey(x.key);
  const r = ROWS.find(r => r.player === m.player && r.stat_col === m.stat_col);
  if (!r) return null;
  const season = m.season || SEASON;
  const i = r.game_weeks.findIndex((w, j) => w === m.week && r.game_seasons[j] === season);
  return i >= 0 ? r.game_log[i] : null;
}}
function suggestedResult(x, actual) {{
  if (actual === null || actual === undefined) return null;
  const line = parseFloat(x.b.line);
  if (!x.b.side || isNaN(line)) return null;
  if (actual === line) return 'push';
  return (x.b.side === 'over') === (actual > line) ? 'win' : 'loss';
}}

function betStats(list) {{
  const s = {{ w: 0, l: 0, p: 0, v: 0, pending: 0, staked: 0, profit: 0, unpriced: 0, pendingStake: 0 }};
  for (const x of list) {{
    const res = x.b.result || '';
    const stake = parseStake(x.b.stake);
    if (!res) {{ s.pending++; if (stake !== null) s.pendingStake += stake; continue; }}
    if (res === 'win') s.w++; else if (res === 'loss') s.l++; else if (res === 'push') s.p++; else if (res === 'void') s.v++;
    const pr = betProfit(x.b);
    if (pr === null) {{ s.unpriced++; continue; }}
    s.profit += pr;
    if (res === 'win' || res === 'loss') s.staked += stake;
  }}
  return s;
}}

// ---- Line value / CLV (added 2026-09-29, per Trevor: "add the best
// current line i could get on a bet compared to what i took it at"). ----
// For each ✅ bet whose row is on this week's slate, the best DraftKings/
// FanDuel/BetMGM line for YOUR side (Over = lowest line, Under = highest;
// same line -> better payout) is saved onto the bet as `market`, stamped
// with when the odds were pulled. Every rebuild refreshes it while the prop
// is still listed; once the game starts the books pull the prop, so the
// last snapshot stays frozen -- if you rebuild close to kickoff that's
// essentially the closing line, i.e. closing-line value (CLV): beating it
// consistently is the best early sign your picks have a real edge.
const BET_BOOKS = [['draftkings', 'DK'], ['fanduel', 'FD'], ['betmgm', 'MGM']];
function americanToDecimal(o) {{ return o > 0 ? 1 + o / 100 : 1 + 100 / Math.abs(o); }}
function bestMarketFor(r, side) {{
  let best = null;
  for (const [bk, label] of BET_BOOKS) {{
    const line = r[bk + '_line'];
    const price = r[bk + (side === 'under' ? '_under_price' : '_over_price')];
    if (line === null || line === undefined || price === null || price === undefined) continue;
    const better = !best ||
      (side === 'over' ? line < best.line : line > best.line) ||
      (line === best.line && americanToDecimal(price) > americanToDecimal(best.price));
    if (better) best = {{ line: line, price: price, book: label }};
  }}
  return best;
}}
function snapshotMarket(key) {{
  const b = BETS[key];
  if (!b || !b.side) return false;
  const live = ROWS.find(r => markKey(r) === key);
  if (!live) return false; // not on this week's slate anymore -- keep the frozen snapshot
  const m = bestMarketFor(live, b.side);
  if (!m) return false; // prop no longer listed (game started) -- keep the last one
  b.market = Object.assign(m, {{ at: ODDS_TIME }});
  return true;
}}
function snapshotAllMarkets() {{
  let changed = false;
  for (const [key, v] of Object.entries(MARKS)) if (v === 'bet' && snapshotMarket(key)) changed = true;
  if (changed) saveBets();
}}
// Your line/price vs the best market one for your side. pts > 0 = you got
// a better number than the market's best (good); < 0 = worse.
function lineValue(b) {{
  if (!b.market || !b.side) return null;
  const yl = parseFloat(b.line);
  if (isNaN(yl)) return null;
  const pts = Math.round((b.side === 'over' ? b.market.line - yl : yl - b.market.line) * 10) / 10;
  const yo = parseOdds(b.odds);
  if (pts !== 0) return {{ pts, verdict: pts > 0 ? 'better' : 'worse', priceOnly: false }};
  if (yo === null) return {{ pts: 0, verdict: 'same', priceOnly: false }};
  const d = americanToDecimal(yo) - americanToDecimal(b.market.price);
  return {{ pts: 0, verdict: Math.abs(d) < 1e-9 ? 'same' : (d > 0 ? 'better' : 'worse'), priceOnly: true }};
}}
function fmtOddsNum(o) {{ return o > 0 ? '+' + o : String(o); }}
function fmtOddsTime(t) {{
  const d = new Date(t);
  if (isNaN(d)) return '';
  return (d.getMonth() + 1) + '/' + d.getDate() + ' ' + d.toLocaleTimeString([], {{ hour: 'numeric', minute: '2-digit' }});
}}
function marketCellHtml(x) {{
  const b = x.b;
  if (x.manual) return '<span class="muted">-</span>';
  if (!b.side) return '<span class="muted" title="Pick Over/Under first">pick O/U</span>';
  if (!b.market) return '<span class="muted" title="No DK/FanDuel/BetMGM line for this prop in the odds pulls this dashboard has seen">-</span>';
  const m = b.market;
  const live = ROWS.some(r => markKey(r) === x.key) && !!bestMarketFor(ROWS.find(r => markKey(r) === x.key), b.side);
  const lv = lineValue(b);
  let tag = '';
  if (lv) {{
    const txt = lv.verdict === 'same' ? 'same'
      : lv.priceOnly ? (lv.verdict === 'better' ? 'better price' : 'worse price')
      : (lv.pts > 0 ? '+' : '') + lv.pts + ' ' + (lv.verdict === 'better' ? 'better' : 'worse');
    tag = `<span class="bet-sug bet-lv-${{lv.verdict}}">${{txt}}</span>`;
  }}
  const when = (live ? 'now' : 'last seen') + (m.at ? ' ' + fmtOddsTime(m.at) : '');
  const tip = live
    ? 'Best line for your side across DK/FanDuel/BetMGM as of the latest odds pull. Keeps updating each rebuild until kickoff.'
    : 'Frozen at the last odds pull before this prop came off the board -- roughly the closing line if you rebuilt near kickoff.';
  return `<span title="${{escapeHtml(tip)}}">${{b.side === 'over' ? 'O' : 'U'}} ${{m.line}} ${{fmtOddsNum(m.price)}} <span class="muted">${{m.book}}</span></span>${{tag}}<div class="muted" style="font-size:10px;">${{when}}</div>`;
}}

function updateMyBetsButton() {{
  const btn = document.getElementById('myBetsBtn');
  if (!btn) return;
  const list = allBets();
  const st = betStats(list);
  btn.innerHTML = '&#128210; My Bets (' + list.length + ')' + ((st.w + st.l + st.p) ? ' &middot; ' + st.w + '-' + st.l + (st.p ? '-' + st.p : '') : '');
}}

let myBetsOpen = false;
// Week filter inside the popup (added 2026-09-29): 'ALL' or 'season|week'.
// Kept for the page session so reopening the popup stays on the same week.
let betsWeekFilter = 'ALL';
function filterBetsByWeek(list) {{
  if (betsWeekFilter === 'ALL') return list;
  return list.filter(x => (x.season + '|' + x.week) === betsWeekFilter);
}}
function betsWeekOptions(all) {{
  const seen = [];
  for (const x of all) {{ const k = x.season + '|' + x.week; if (!seen.includes(k)) seen.push(k); }}
  if (betsWeekFilter !== 'ALL' && !seen.includes(betsWeekFilter)) betsWeekFilter = 'ALL';
  const opt = (v, label) => `<option value="${{v}}" ${{betsWeekFilter === v ? 'selected' : ''}}>${{label}}</option>`;
  return opt('ALL', 'All weeks') + seen.map(k => {{ const [ss, w] = k.split('|'); return opt(k, ss + ' Week ' + w); }}).join('');
}}
function openMyBetsModal() {{
  myBetsOpen = true;
  document.querySelector('#playerModalOverlay .modal-panel').style.maxWidth = '1280px'; // wider: the bets table has 11 columns
  currentModalPlayer = null;
  currentModalDefenseTeam = null;
  document.getElementById('modalPlayerName').textContent = 'My Bets';
  document.getElementById('modalMeta').innerHTML =
    'Every &#9989; bet from every week, plus bets you add by hand (parlays, ladders). '
    + (syncUser ? 'Synced to your account (' + escapeHtml(syncUser.email || '') + '), so it shows on every device you sign in on.'
       : 'Saved in this browser only' + (syncEnabled() ? ' &middot; sign in (next to My Bets) to sync across devices,' : ' &middot;') + ' use Backup to copy it somewhere safe.');
  const allList = allBets();
  const weekOptionsHtml = betsWeekOptions(allList);
  const list = filterBetsByWeek(allList);
  const resOpt = (cur, v, label) => `<option value="${{v}}" ${{(cur || '') === v ? 'selected' : ''}}>${{label}}</option>`;
  let rowsHtml = '';
  let lastWeek = null;
  for (const x of list) {{
    const b = x.b;
    if (x.week !== lastWeek) {{
      rowsHtml += `<tr class="bets-week-row"><td colspan="11">${{x.season}} Week ${{x.week || '?'}}</td></tr>`;
      lastWeek = x.week;
    }}
    const actual = betActual(x);
    const sug = b.legs ? parlaySuggestion(b) : suggestedResult(x, actual);
    let what;
    if (x.manual) {{
      what = `<input class="bet-field bet-desc" data-field="desc" value="${{escapeHtml(b.desc || '')}}" placeholder="e.g. Nix + Stafford INT parlay">` + (b.legs ? parlayLegsHtml(b) : '');
    }} else {{
      const m = b.meta || parseBetKey(x.key);
      const opp = m.opp ? (m.at === true ? ' @' : (m.at === false ? ' vs ' : ' vs ')) + m.opp : '';
      what = `<strong>${{escapeHtml(m.player)}}</strong> <span class="muted">${{escapeHtml(m.team)}}${{escapeHtml(opp)}}</span> &middot; ${{escapeHtml(m.stat_label || statLabelFor(m.stat_col))}}` +
        (x.kick ? `<div class="muted" style="font-size:10px;">${{fmtKickoff(x.kick)}} ${{gsLinkForTeam(m.team, x.week, 'Game script')}}</div>` : (gsLinkForTeam(m.team, x.week) ? `<div style="font-size:10px;">${{gsLinkForTeam(m.team, x.week, 'Game script')}}</div>` : ''));
    }}
    const sideSel = x.manual ? '<span class="muted">-</span>' :
      `<select class="bet-field" data-field="side">${{resOpt(b.side, '', 'O/U')}}${{resOpt(b.side, 'over', 'Over')}}${{resOpt(b.side, 'under', 'Under')}}</select>`;
    const lineIn = x.manual ? '<span class="muted">-</span>' :
      `<input class="bet-field bet-line${{validBetLine(b.line) ? '' : ' bet-bad'}}" data-field="line" inputmode="decimal" value="${{escapeHtml(b.line || '')}}" placeholder="line">`;
    // Parlays take their week from their legs, so no week box (2026-10-16, per Trevor).
    const weekIn = (x.manual && !b.legs) ? `<input class="bet-field bet-week" data-field="week" inputmode="numeric" value="${{escapeHtml(b.week || '')}}" placeholder="wk" title="Week">` : '';
    const sugHtml = sug ? `<span class="bet-sug bet-sug-${{sug}}" title="From the stat line vs your side/line -- a hint, not auto-filled">${{sug === 'win' ? 'looks W' : sug === 'loss' ? 'looks L' : 'looks push'}}</span>` : '';
    const pr = betProfit(b);
    rowsHtml += `<tr data-bet-key="${{escapeHtml(x.key)}}" class="bet-row bet-res-${{b.result || 'pending'}}">
      <td>${{weekIn}}${{what}}</td>
      <td>${{sideSel}}</td>
      <td>${{lineIn}}</td>
      <td><input class="bet-field bet-odds${{validBetOdds(b.odds) ? '' : ' bet-bad'}}" data-field="odds" inputmode="text" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" value="${{escapeHtml(b.odds || '')}}" placeholder="odds"></td>
      <td><input class="bet-field bet-stake${{validBetStake(b.stake) ? '' : ' bet-bad'}}" data-field="stake" inputmode="decimal" value="${{escapeHtml(b.stake || '')}}" placeholder="$"></td>
      <td class="bet-towin muted">${{toWinLabel(b).replace('to win ', '')}}</td>
      <td class="bet-market">${{marketCellHtml(x)}}</td>
      <td>${{actual === null ? '<span class="muted">-</span>' : fmt(Math.round(actual * 10) / 10)}} ${{sugHtml}}</td>
      <td><select class="bet-field bet-result" data-field="result">${{resOpt(b.result, '', 'Pending')}}${{resOpt(b.result, 'win', '&#9989; Win')}}${{resOpt(b.result, 'loss', '&#10060; Loss')}}${{resOpt(b.result, 'push', '&#8596;&#65039; Push')}}${{resOpt(b.result, 'void', '&#9898; Void')}}</select></td>
      <td class="bet-profit ${{pr > 0 ? 'edge-pos' : (pr < 0 ? 'edge-neg' : '')}}">${{b.result ? money(pr, true) : ''}}</td>
      <td><button type="button" class="weeks-mini-btn bet-remove" title="Remove this bet from the tracker">&times;</button></td>
    </tr>`;
  }}
  if (!list.length) rowsHtml = '<tr><td colspan="10" class="muted">No bets yet. Mark a row &#9989; Bet it, or add one by hand above.</td></tr>';

  document.getElementById('modalBody').innerHTML = `
    <div style="display:flex; gap:8px; align-items:center; margin-bottom:10px;">
      <span class="muted">Week:</span>
      <select id="betsWeekFilter" class="mark-select" style="max-width:none;" title="Show one week's bets -- the record, profit and pending totals switch to that week too.">${{weekOptionsHtml}}</select>
    </div>
    <div id="betsSummary"></div>
    <div style="display:flex; gap:8px; flex-wrap:wrap; margin: 10px 0;">
      <button type="button" class="weeks-mini-btn" id="betsAddManual">+ Add a bet by hand (ladder, anything)</button>
      <button type="button" class="weeks-mini-btn" id="betsFillSuggested" title="Sets Win/Loss/Push on every still-Pending bet that has a 'looks W/L' hint. You can change any of them after.">Fill in suggested results</button>
      <button type="button" class="weeks-mini-btn" id="betsBackup">Backup / restore</button>
    </div>
    ${{parlayBuilderHtml()}}
    <div id="betsBackupPanel" style="display:none; margin-bottom:10px;">
      <div class="modal-note">Copy this text somewhere safe (Notes, email to yourself). To restore -- or to move your bets between the Mac dashboard and the shared link, which keep separate copies -- paste a backup here and click Restore; it merges, it doesn't delete anything.</div>
      <textarea id="betsBackupText" rows="5" style="width:100%; background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:6px; font-size:12px;"></textarea>
      <button type="button" class="weeks-mini-btn" id="betsRestore">Restore from pasted backup</button> <span id="betsRestoreMsg" class="muted"></span>
    </div>
    <div class="modal-table-wrap">
    <table class="modal-table bets-table">
      <thead><tr><th>Bet</th><th>Side</th><th>Line</th><th>Odds</th><th>$ Bet</th><th>To win</th><th title="Best DK/FanDuel/BetMGM line for your side vs the one you got. Green = you beat the market's best number (good sign), red = you could have done better. Once the game starts it freezes at the last pull -- roughly the closing line.">Best line</th><th>Actual</th><th>Result</th><th>Profit</th><th></th></tr></thead>
      <tbody>${{rowsHtml}}</tbody>
    </table>
    </div>`;
  refreshBetsSummary();
  document.getElementById('playerModalOverlay').style.display = 'flex';
}}

function refreshBetsSummary() {{
  const el = document.getElementById('betsSummary');
  if (!el) return;
  const allList = allBets();
  const list = filterBetsByWeek(allList);
  const st = betStats(list);
  const scope = betsWeekFilter === 'ALL' ? '' : ' &middot; ' + betsWeekFilter.replace('|', ' Week ');
  const decided = st.w + st.l;
  const winPct = decided ? Math.round(st.w / decided * 1000) / 10 + '%' : '-';
  const roi = st.staked ? (st.profit / st.staked * 100).toFixed(1) + '%' : '-';
  const cls = st.profit > 0 ? 'edge-pos' : (st.profit < 0 ? 'edge-neg' : '');
  let lvB = 0, lvW = 0, lvS = 0, lvPts = 0, lvN = 0;
  for (const x of list) {{
    if (x.manual) continue;
    const lv = lineValue(x.b);
    if (!lv) continue;
    if (lv.verdict === 'better') lvB++; else if (lv.verdict === 'worse') lvW++; else lvS++;
    lvPts += lv.pts; lvN++;
  }}
  const lvCard = lvN ? `<div class="bets-card" title="How your lines compare to the best DK/FanDuel/BetMGM line for the same side (frozen near kickoff once the game starts). Beating it more often than not is the best early sign of a real edge -- more reliable than win/loss over a small sample."><div class="muted">Line value vs market</div><div class="bets-big"><span class="edge-pos">${{lvB}}</span> / <span class="edge-neg">${{lvW}}</span>${{lvS ? ' / ' + lvS : ''}}</div><div class="muted">better / worse${{lvS ? ' / same' : ''}} &middot; avg ${{(lvPts / lvN > 0 ? '+' : '') + (Math.round(lvPts / lvN * 10) / 10)}} pts</div></div>` : '';
  // Per-week breakdown
  const weeks = new Map();
  for (const x of (betsWeekFilter === 'ALL' ? allList : [])) {{
    const k = x.season + '|' + x.week;
    if (!weeks.has(k)) weeks.set(k, []);
    weeks.get(k).push(x);
  }}
  let wkRows = '';
  for (const [k, xs] of weeks) {{
    const w = betStats(xs);
    const [season, week] = k.split('|');
    wkRows += `<tr class="bets-week-link" data-week-key="${{k}}" title="Show just this week"><td>${{season}} Wk${{week}}</td><td>${{w.w}}-${{w.l}}${{w.p ? '-' + w.p : ''}}${{w.v ? ' (' + w.v + ' void)' : ''}}</td><td>${{w.pending || ''}}</td><td>${{money(w.staked)}}</td><td class="${{w.profit > 0 ? 'edge-pos' : (w.profit < 0 ? 'edge-neg' : '')}}">${{money(w.profit, true)}}</td></tr>`;
  }}
  el.innerHTML = `
    <div class="bets-cards">
      <div class="bets-card"><div class="muted">Record (W-L${{st.p ? '-P' : ''}})${{scope}}</div><div class="bets-big">${{st.w}}-${{st.l}}${{st.p ? '-' + st.p : ''}}</div><div class="muted">${{winPct}} wins${{st.v ? ' &middot; ' + st.v + ' void' : ''}}</div></div>
      <div class="bets-card"><div class="muted">Total profit</div><div class="bets-big ${{cls}}">${{money(st.profit, true)}}</div><div class="muted">ROI ${{roi}} on ${{money(st.staked)}} risked</div></div>
      ${{lvCard}}<div class="bets-card"><div class="muted">Pending</div><div class="bets-big">${{st.pending}}</div><div class="muted">${{money(st.pendingStake)}} in play</div></div>
    </div>
    ${{st.unpriced ? `<div class="modal-note" style="margin-top:8px; color:var(--amber); opacity:1;">${{st.unpriced}} settled bet(s) are missing the $ amount or odds, so they count in the record but not in profit.</div>` : ''}}
    ${{wkRows ? `<table class="modal-table" style="margin-top:10px; width:auto;"><thead><tr><th>Week</th><th>Record</th><th>Pending</th><th>Risked</th><th>Profit</th></tr></thead><tbody>${{wkRows}}</tbody></table>` : ''}}`;
  updateMyBetsButton();
}}

// After a field changes in the popup, update just that row's numbers and
// the summary -- no full redraw, so the cursor stays where it is.
function refreshBetRow(tr) {{
  const key = tr.dataset.betKey;
  const b = BETS[key] || {{}};
  const pr = betProfit(b);
  const pc = tr.querySelector('.bet-profit');
  pc.textContent = b.result ? money(pr, true) : '';
  pc.className = 'bet-profit ' + (pr > 0 ? 'edge-pos' : (pr < 0 ? 'edge-neg' : ''));
  const tw = tr.querySelector('.bet-towin');
  if (tw) tw.textContent = toWinLabel(b).replace('to win ', '');
  const mc = tr.querySelector('.bet-market');
  if (mc) mc.innerHTML = marketCellHtml({{ key, b, manual: key.startsWith('manual|') }});
  tr.className = 'bet-row bet-res-' + (b.result || 'pending');
  refreshBetsSummary();
}}

const MARK_OPTIONS = [
  {{ value: '', label: '—' }},
  {{ value: 'bet', label: '✅ Bet it' }},
  {{ value: 'watch', label: '🌕 Watching' }},
  {{ value: 'pass', label: '❌ Pass' }},
  {{ value: 'parlay', label: '🔗 Parlay' }},
];
const MARK_EMOJI = {{ bet: '✅', watch: '🌕', pass: '❌', parlay: '🔗' }};
// ---- Parlays (added 2026-10-16, per Trevor: "make a new status for
// parlay ... don't add it to my bets ... unless you have a way where i can
// select which parlays i combined in the my bets screen and what odds i
// got"). Rows marked 🔗 Parlay are NOT single bets. My Bets has a "Build a
// parlay" box listing every 🔗 row: tick the legs, enter the odds/stake,
// Add -- it becomes one manual bet with a `legs` list, tracked like any
// other bet, with a looks-W/L hint from the legs' actual stats.
function parlayLegCandidates() {{
  const c = {{}};
  const out = [];
  for (const [key, v] of Object.entries(MARKS)) {{
    if (v !== 'parlay') continue;
    ensureBetMeta(key);
    const m = BETS[key].meta;
    const live = ROWS.find(r => markKey(r) === key);
    let side = 'over', line = '';
    if (live) {{
      const e = enrichRow(live, selectedWeeks, c);
      side = (e.cons && e.cons.side) || e.direction || 'over';
      const mk = bestMarketFor(live, side);
      line = mk ? mk.line : (live.vegas_line === null || live.vegas_line === undefined ? '' : live.vegas_line);
    }}
    const used = Object.entries(BETS).filter(([k, b]) => k.startsWith('manual|') && (b.legs || []).some(l => l.key === key)).length;
    out.push({{ key, m, side, line, used }});
  }}
  out.sort((a, b) => (b.m.week - a.m.week) || String(a.m.kick || '9999').localeCompare(String(b.m.kick || '9999')) || a.m.player.localeCompare(b.m.player));
  return out;
}}
// Legs already in a parlay drop out of the builder (2026-10-16, per Trevor:
// "once they're added to a parlay in there can you take them out of the
// build queue?"); a "show" link brings them back to reuse one.
let parlayShowUsed = false;
function parlayBuilderHtml() {{
  const all = parlayLegCandidates();
  const hidden = parlayShowUsed ? 0 : all.filter(l => l.used).length;
  const legs = parlayShowUsed ? all : all.filter(l => !l.used);
  const usedNote = hidden ? ` <span class="muted">${{hidden}} leg${{hidden > 1 ? 's' : ''}} already in a parlay hidden &middot; <a href="#" id="parlayShowUsed">show</a></span>` : '';
  if (!legs.length && hidden) {{
    return `<div class="modal-note">&#128279; <strong>Build a parlay:</strong> every &#128279; leg is already in a parlay.${{usedNote}}</div>`;
  }}
  if (!legs.length) {{
    return '<div class="modal-note">&#128279; <strong>Build a parlay:</strong> mark rows &#128279; Parlay in the table and they show up here to combine. (Parlay rows aren&#39;t counted as single bets.)</div>';
  }}
  const sideOpt = (cur, v, label) => `<option value="${{v}}" ${{cur === v ? 'selected' : ''}}>${{label}}</option>`;
  const rows = legs.map(l => `<tr data-leg-key="${{escapeHtml(l.key)}}">
      <td><input type="checkbox" class="parlay-pick"></td>
      <td><strong>${{escapeHtml(l.m.player)}}</strong> <span class="muted">${{escapeHtml(l.m.team)}}${{l.m.opp ? (l.m.at ? ' @' : ' vs ') + escapeHtml(l.m.opp) : ''}} &middot; Wk${{l.m.week}}</span> &middot; ${{escapeHtml(l.m.stat_label || statLabelFor(l.m.stat_col))}}</td>
      <td><select class="parlay-side">${{sideOpt(l.side, 'over', 'Over')}}${{sideOpt(l.side, 'under', 'Under')}}</select></td>
      <td><input class="parlay-line" inputmode="decimal" value="${{escapeHtml(String(l.line))}}" placeholder="line" style="width:60px;"></td>
      <td class="muted">${{l.used ? 'in ' + l.used + ' parlay' + (l.used > 1 ? 's' : '') : ''}}</td>
    </tr>`).join('');
  return `<div style="border:1px solid var(--border); border-radius:8px; padding:8px 10px; margin-bottom:10px;">
    <div style="margin-bottom:6px;"><strong>&#128279; Build a parlay</strong> <span class="muted">-- tick the legs you combined, then the odds you got.</span>${{usedNote}}</div>
    <div class="modal-table-wrap"><table class="modal-table"><tbody>${{rows}}</tbody></table></div>
    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:6px;">
      <input id="parlayOdds" class="bet-odds" inputmode="text" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" placeholder="odds e.g. +450" style="width:110px;">
      <input id="parlayStake" class="bet-stake" inputmode="decimal" placeholder="$ stake" style="width:80px;">
      <button type="button" class="weeks-mini-btn" id="parlayAdd">Add parlay</button>
      <span id="parlayMsg" class="muted"></span>
    </div>
  </div>`;
}}
function addParlayFromBuilder() {{
  const msg = document.getElementById('parlayMsg');
  const picked = Array.from(document.querySelectorAll('tr[data-leg-key]')).filter(tr => tr.querySelector('.parlay-pick').checked);
  if (picked.length < 2) {{ msg.textContent = 'Tick at least 2 legs.'; return; }}
  const odds = normOdds(document.getElementById('parlayOdds').value);
  const stake = document.getElementById('parlayStake').value.trim();
  if (!odds || !validBetOdds(odds)) {{ msg.textContent = 'Enter the parlay odds, like +450 or -110.'; return; }}
  if (stake && !validBetStake(stake)) {{ msg.textContent = 'Stake should be a dollar amount.'; return; }}
  const legs = picked.map(tr => {{
    const key = tr.dataset.legKey;
    ensureBetMeta(key);
    const m = BETS[key].meta;
    return {{ key, player: m.player, team: m.team, opp: m.opp, at: m.at, week: m.week, season: m.season || SEASON,
      stat_col: m.stat_col, stat_label: m.stat_label || statLabelFor(m.stat_col),
      side: tr.querySelector('.parlay-side').value, line: tr.querySelector('.parlay-line').value.trim() }};
  }});
  const desc = 'Parlay: ' + legs.map(l => `${{l.player}} ${{l.side === 'over' ? 'O' : 'U'}} ${{l.line}} ${{l.stat_label}}`).join(' + ');
  BETS['manual|' + Date.now()] = {{ week: String(Math.max(...legs.map(l => l.week))), desc, odds, stake: stake || undefined, legs, parlay: true }};
  parlayShowUsed = false;
  saveBets();
  openMyBetsModal();
  updateMyBetsButton();
}}
// Each leg's actual stat and W/L hint; the parlay looks L as soon as one
// leg missed, W once every leg hit.
function parlayLegResults(b) {{
  return (b.legs || []).map(l => {{
    const actual = betActual({{ manual: false, key: l.key, b: {{ meta: l }} }});
    return {{ l, actual, res: suggestedResult({{ b: {{ side: l.side, line: l.line }} }}, actual) }};
  }});
}}
function parlaySuggestion(b) {{
  const rs = parlayLegResults(b);
  if (!rs.length) return null;
  if (rs.some(x => x.res === 'loss')) return 'loss';
  return rs.every(x => x.res === 'win') ? 'win' : null;
}}
function parlayLegsHtml(b) {{
  return '<div style="font-size:11px; margin-top:3px;">' + parlayLegResults(b).map(({{ l, actual, res }}) =>
    `<div>${{res === 'win' ? '&#9989;' : (res === 'loss' ? '&#10060;' : (res === 'push' ? '&#8596;&#65039;' : '&middot;'))}} ${{escapeHtml(l.player)}} ${{l.side === 'over' ? 'O' : 'U'}} ${{escapeHtml(String(l.line))}} ${{escapeHtml(l.stat_label)}}${{actual === null || actual === undefined ? '' : ' <span class="muted">(' + (Math.round(actual * 10) / 10) + ')</span>'}}</div>`
  ).join('') + '</div>';
}}

// Default view: biggest 🔥/🧊/❓ signal first (see signal_rank in
// enrichRow), not alphabetical by player -- Trevor asked for the whole
// table to open this way, not just as a click-to-sort option. sortDir
// -1 means descending, so the highest rank (3-flame/3-ice) is on top.
let sortKey = "signal_rank";
let sortDir = -1;
// Which weeks of the current season count toward every stat on this page.
// Defaults to the last DEFAULT_LAST_WEEKS played weeks (was every played
// week until 2026-10-16) -- see populateWeeksFilter() for the checkboxes.
// WEEK is the upcoming (not yet played) week, so the default is every
// week already played: 1 .. WEEK-1. (Before 2026-10-07 it was 1 .. WEEK,
// which showed "Wk 1-5" on a Week 5 board even though Week 5 has no games
// yet -- harmless to the math, but confusing.)
function lastPlayedWeek() {{ return Math.max(1, WEEK - 1); }}
function lastNWeeks(n) {{
  const end = lastPlayedWeek();
  const start = Math.max(1, end - n + 1);
  return new Set(Array.from({{length: end - start + 1}}, (_, i) => start + i));
}}
// Default = the 4 most recent played weeks (2026-10-16, per Trevor: "make
// it so that the default view is last 4 games"). Phone alerts read this
// same default, so they follow it too. Week-based: a team with a bye in
// that span has 3 games, which is short of MUST BET's 4-game minimum.
const DEFAULT_LAST_WEEKS = 4;
let selectedWeeks = lastNWeeks(DEFAULT_LAST_WEEKS);

function fmt(v, suffix) {{
  if (v === null || v === undefined) return '<span class="muted">-</span>';
  return suffix ? v + suffix : v;
}}

function fmtLine(point, price) {{
  if (point === null || point === undefined) return '<span class="muted">-</span>';
  if (price === null || price === undefined) return point;
  const priceStr = price > 0 ? '+' + price : price;
  return point + ' <span class="muted">(' + priceStr + ')</span>';
}}

// Which of a book's two prices to show in its DK/FD/BetMGM column cell.
// Added 2026-09-24 alongside the line-shopping tie-break fix: each book
// now carries a separate Over and Under price (see book_line() in
// build_dashboard.py), so the column can finally show the side this row
// actually favors (r.direction, set by deriveStats()) instead of always
// showing the Over price regardless of which way the row leans -- e.g.
// an Under-leaning row used to display that book's Over price here,
// which didn't match the price actually being used for Edge/the price
// gate. Defaults to the Over price when there's no lean yet (a dead-even
// tie against consensus, or no line at all), matching the old behavior
// for that case.
function bookCellPrice(r, book) {{
  const suffix = r.direction === 'under' ? '_under_price' : '_over_price';
  return r[book + suffix];
}}

// Opp Rank gradient, added 2026-09-22 per Trevor -- replaces the old hard
// "top 10 red / bottom 10 green / everything else plain" cutoff with a
// continuous scale, so a rank near either end (1 or the toughest/easiest
// defense that week) stands out more the closer it gets to that extreme,
// instead of jumping suddenly at a fixed line and treating rank 11 the
// same as rank 22. Red = toughest matchup (allows the least), green =
// easiest, fading through a neutral gray in the middle -- same red/green
// meaning already used everywhere else on this page (Edge, wind, weather),
// kept for consistency rather than switching this one column to a
// different color pair. Scaled against def_rank_max (how many teams have
// data for that position/stat yet, which can be under 32 early in the
// season) rather than a hardcoded 32, so the gradient always spans the
// full set of ranked defenses rather than compressing early-season ranks
// into one end.
function rankColor(rank, maxRank) {{
  if (rank === null || rank === undefined) return null;
  const total = (maxRank && maxRank > 1) ? maxRank : 32;
  const t = (rank - 1) / (total - 1); // 0 = toughest defense, 1 = easiest
  const RED = [248, 81, 73];     // var(--red)
  const GRAY = [122, 128, 138];  // neutral midpoint
  const GREEN = [63, 185, 80];   // var(--green)
  const mix = (a, b, f) => a.map((v, i) => Math.round(v + (b[i] - v) * f));
  const rgb = t < 0.5 ? mix(RED, GRAY, t / 0.5) : mix(GRAY, GREEN, (t - 0.5) / 0.5);
  return `rgb(${{rgb[0]}}, ${{rgb[1]}}, ${{rgb[2]}})`;
}}

function rankStyle(rank, maxRank) {{
  const color = rankColor(rank, maxRank);
  if (!color) return '';
  const total = (maxRank && maxRank > 1) ? maxRank : 32;
  const t = (rank - 1) / (total - 1);
  // Bold the extreme ~20% on either end so they stand out beyond just a
  // slightly different shade -- the point of "stands out" per Trevor.
  const bold = (t <= 0.2 || t >= 0.8) ? 'font-weight:700;' : '';
  return `style="color:${{color}};${{bold}}"`;
}}

// Pickiness slider (added 2026-09-22 per Trevor: "too many 3 star bets").
// SIGNIFICANT_EDGE_PCT is the % edge needed to earn even 1 star, and it's
// the single shared "does this edge actually matter" bar used everywhere
// on the page: it's also what colors Edge/Anc. Edge green/red, and what
// ❓ checks to decide a signal is worth flagging. The 2-star/3-star bars
// (EDGE_TIERS) scale off it at the SAME ratio as the original fixed
// thresholds (15/25/40, i.e. 1x / ~1.67x / ~2.67x) rather than being a
// separate knob each, so dragging the slider keeps "significant" meaning
// one consistent thing everywhere it's checked, instead of tiers getting
// pickier while the Edge/Anc. Edge coloring or ❓ stay put underneath.
// Both are `let`, not `const`, and recomputed by applyPickySetting()
// below whenever the slider moves -- every function that reads them
// (edgeClass, enrichRow) picks up the new value on its next call, since
// they're read at call time, not captured at page load.
//
// 4th tier -- ⭐ MUST BET (added 2026-09-24, made a FIXED bar 2026-09-24):
// Trevor said there were "too many 3 stars" again even with the slider in
// place, and asked for either a 4th level or a pickier slider; his
// follow-up pick was a 4th tier specifically, rendered as a single star
// rather than a 4th flame/ice, and treated as its own "MUST BET" callout
// rather than just a bigger number -- see signalEmoji() below. It was
// first built scaled off the same picky slider (60% at the original fixed
// scale, i.e. 4x SIGNIFICANT_EDGE_PCT), but real data still showed ~20
// rows earning it and Trevor said even that was too many -- his exact
// ask: "i think must bet should always be the same criteria, just like a
// line that almost doesn't even make sense. then from there, do 3 star
// ranking." So as of this fix, MUST_BET_EDGE_PCT (below) is a SEPARATE,
// FIXED constant, deliberately NOT part of the SIGNIFICANT_EDGE_PCT/
// EDGE_TIERS scaling and NOT affected by the "How picky" slider at all --
// 1/2/3 stars keep flexing with the slider exactly as before, but MUST
// BET is always the same absolute, extreme bar regardless of where the
// slider sits. Originally set to 150% (2.5x the sportsbook's own line) --
// Claude's own reasonable-looking pick for "absurd" -- flagged the same
// way every other arbitrary constant in this project is flagged. Lowered
// to 100% (2x the line) on 2026-09-24 per Trevor's direct ask ("should we
// make the must bet threshold a little lower? like 100?") once the
// consistency gate below was in place to keep the tier meaningful at a
// lower bar -- still a one-line change (`MUST_BET_EDGE_PCT` below) to
// retune further if 100% turns out to be too loose or too strict once he
// watches it over more weeks of real data.
//
// Consistency gate (added 2026-09-24): Trevor asked for the % bar alone
// to not be enough -- his exact ask, after I pointed out that "the player
// has literally never cleared the line" can't happen mathematically (if
// the average is above the line, at least one game must be too -- the max
// of a set is always >= its average), was "I don't want it to be a must
// bet if that player has ever gone beneath the line within the weeks I'm
// filtered to." So level 4 now ALSO requires a perfect record across the
// selected weeks (zero below-the-line games for a MUST BET Over, zero
// above-the-line games for a MUST BET Under) -- see the below_count/
// above_count fields in deriveStats() and the gate in enrichRow(). This
// stops one huge outlier game from carrying an otherwise-inconsistent
// player into the top tier, and is also why lowering the % bar to 100%
// (above) doesn't reopen the door to that same outlier problem -- a
// player still needs a perfectly clean record to qualify, no matter how
// low the bar goes.
let pickyPct = 20; // starts a bit pickier than the original fixed 15%, per Trevor's ask -- adjustable via the slider in the controls bar
let SIGNIFICANT_EDGE_PCT = pickyPct / 100;
let EDGE_TIERS = [SIGNIFICANT_EDGE_PCT, SIGNIFICANT_EDGE_PCT * (25 / 15), SIGNIFICANT_EDGE_PCT * (40 / 15)];
const MUST_BET_EDGE_PCT = 1.00; // FIXED -- always this, never scaled by the picky slider (see comment above). Lowered from 1.50 to 1.00 on 2026-09-24 per Trevor's ask.
// MUST BET matchup gate (added 2026-10-05, per Trevor: "i don't want it to
// be a must-bet unless it's an over and the defense lets up a top 10 amount
// or if it's an under and they let up a least 10 amount"). Over: the
// opponent must be among the 10 defenses ALLOWING THE MOST of this stat to
// this position (Opp Rank in the top 10 from the easy end, e.g. 23-32 of
// 32). Under: among the 10 allowing the LEAST (Opp Rank 1-10). Same Opp
// Rank as the table (selected weeks). Failing it keeps the 3-star tier.
const MUST_BET_MATCHUP_TOP = 10;
// 3-flame/3-ice gates (added 2026-10-05, per Trevor: "i also want that
// factored in so that 3 emojis needs that too" and "i want a 3 or must bet
// to have a low standard deviation over the time duration from what the
// line is"). Any row that would reach 3 (or MUST BET) must ALSO:
//   1. pass the same matchup gate as MUST BET (MUST_BET_MATCHUP_TOP), and
//   2. be consistent: the standard deviation of his games in the selected
//      weeks, as a share of the line, must be at most MAX_TIER3_REL_SD.
//      E.g. line 50.5 with games 55/60/58 -> SD ~2.5 = 5% (passes); games
//      10/140/30 -> SD ~70 = 139% (fails). Needs 2+ games to measure.
// A row that fails either is capped at 2 flames/ice. 50% kept 10 of the
// 59 three-plus rows on the Week 4 board (25 passed the matchup alone).
const MAX_TIER3_REL_SD = 0.50;

function applyPickySetting() {{
  SIGNIFICANT_EDGE_PCT = pickyPct / 100;
  EDGE_TIERS = [SIGNIFICANT_EDGE_PCT, SIGNIFICANT_EDGE_PCT * (25 / 15), SIGNIFICANT_EDGE_PCT * (40 / 15)];
  const label = document.getElementById('pickyLabel');
  if (label) {{
    const pct = (v) => Math.round(v * 100) + '%';
    label.textContent = '1★ ≥' + pct(EDGE_TIERS[0]) + '  ·  2★ ≥' + pct(EDGE_TIERS[1]) + '  ·  3★ ≥' + pct(EDGE_TIERS[2]) + '  ·  ⭐ MUST BET ≥' + pct(MUST_BET_EDGE_PCT) + ' (fixed)';
  }}
}}

// Worst price (American odds) a side is allowed to have and still earn a
// 🔥/🧊 -- Trevor's own read on this: -110ish is normal/expected vig on a
// player prop, and the more negative it gets past that, the more the book
// is charging you for the same bet, so a stat-based edge stops being
// worth much once the price gets too steep. -130 is Claude's own
// reasonable-looking cutoff for "too steep" (needing the bet to hit
// ~56.5% of the time just to break even, noticeably worse than a normal
// -110/-115 prop) -- not an official number, easy to move here. Positive
// prices (plus money) always pass, since they require LESS than 50% to
// break even, which is the best case for a bettor, not the worst.
const MAX_JUICE_PRICE = -130;

// American odds -> implied win probability (what the book's price says
// you'd need to hit at just to break even, before even accounting for
// the vig baked into both sides). Shown in tooltips so the reasoning
// behind a suppressed 🔥/🧊 is visible, not just asserted.
function impliedProb(price) {{
  if (price === null || price === undefined) return null;
  return price < 0 ? (-price) / (-price + 100) : 100 / (price + 100);
}}

function edgeClass(pct) {{
  if (pct === null || pct === undefined) return '';
  if (pct >= SIGNIFICANT_EDGE_PCT) return 'edge-pos';
  if (pct <= -SIGNIFICANT_EDGE_PCT) return 'edge-neg';
  return '';
}}

// Red for anything flagged bad server-side (very cold, high wind, a
// meaningful rain/snow chance, or a rain/snow/storm condition -- see
// is_bad_weather() in build_dashboard.py, which is where the actual
// thresholds live). Amber as a lighter "worth a look" tier for wind
// that's elevated (15-19mph) but not yet bad enough to flag red on its
// own (20mph+ already gets flagged bad).
function weatherClass(r) {{
  if (r.weather_bad) return 'weather-bad';
  if (r.wind_mph !== null && r.wind_mph !== undefined && r.wind_mph >= 15) return 'wind-med';
  return '';
}}

// 1-3 🔥 for an OVER signal, 1-3 🧊 for an UNDER signal, blank for neither.
// More emojis = a bigger agreed-upon edge (see EDGE_TIERS / enrichRow).
// Level 4 (added 2026-09-24, per Trevor) is a separate, rarer tier above
// 3 flames/ice -- shown as a single ⭐ "MUST BET" badge instead of a 4th
// flame/ice character, so the very top of the page's signal scale reads
// as its own distinct callout rather than just "one more emoji." Its bar
// (MUST_BET_EDGE_PCT) is FIXED, not part of EDGE_TIERS and not affected
// by the "How picky" slider -- see the comment above MUST_BET_EDGE_PCT's
// declaration for why.
// Role changes (added 2026-10-16, see TRADE_ROLE_GROUPS in the builder):
// a recent trade (server-side trade_flags), a key own-team skill player
// Out/Doubtful (the strong 🩹 entries), or Trevor's own ⚠️ flag from the
// player popup (MARKS 'role|WEEK|player|team' = 'flux', synced like marks).
// Any of these keeps a row from being a MUST BET (held at 3).
const BLOWOUT_FAV = 10; // team favored by this many or more -> no lead-RB rush Overs
// 🎯 outlier defense (2026-10-30, per Trevor: "give some significance to
// defenses that allow statistically significant amounts"). Top/bottom 3 on
// the full season (season-long ranks predicted better than last 4 in a
// 2019-2025 backtest), only for stats where it held up: top-3 soft defenses
// gave RB rush yds 54% vs 47% (ranks 4-10), WR receptions 48% vs 44%; no
// edge for QB pass yds, RB rec yds or TE yds. A ❓ facing one on its side -> 💡.
const OUTLIER_DEF_TOP = 3;
const OUTLIER_VALUE_RATIO = 1.2; // 🎯 + Anticipated 20%+ past the line -> 💡 even with no signal
const OUTLIER_DEF_STATS = new Set(['RB|rushing_yards', 'WR|receptions', 'TE|receptions']);
const _seasonDefRanks = {{}};
function outlierDefense(r) {{
  const key = r.position + '|' + r.stat_col;
  if (!OUTLIER_DEF_STATS.has(key)) return null;
  if (!_seasonDefRanks[key]) {{
    const all = new Set();
    for (let w = 1; w < WEEK; w++) all.add(w);
    _seasonDefRanks[key] = rankDefenses(key, all);
  }}
  const {{ avgs, ranks }} = _seasonDefRanks[key];
  const rk = ranks[r.opponent];
  if (rk === undefined) return null;
  const n = Object.keys(ranks).length;
  const avg = avgs[r.opponent] === null ? '' : ` (${{avgs[r.opponent].toFixed(1)}}/game)`;
  if (rk > n - OUTLIER_DEF_TOP) return {{ side: 'over', text: `${{r.opponent}} allows the ${{n - rk + 1 === 1 ? 'most' : (n - rk + 1) + (n - rk + 1 === 2 ? 'nd' : 'rd') + ' most'}} this season${{avg}}` }};
  if (rk <= OUTLIER_DEF_TOP) return {{ side: 'under', text: `${{r.opponent}} allows the ${{rk === 1 ? 'least' : rk + (rk === 2 ? 'nd' : 'rd') + ' least'}} this season${{avg}}` }};
  return null;
}}
const ROLE_INJURY_POSITIONS = new Set(['QB', 'RB', 'HB', 'FB', 'WR', 'TE']);
function roleKey(r) {{ return 'role|' + WEEK + '|' + r.player + '|' + r.team; }}
// Heads-up only (2026-10-16): a real-role teammate who is Questionable or
// missed practice. Shown in the ⚠️ hover (faded tag), never blocks.
function roleSoftReasons(r) {{
  const imp = r.injury_impacts;
  if (!imp) return [];
  const out = [], seen = new Set();
  for (const e of [].concat(imp.helps || [], imp.hurts || [])) {{
    if (e.team !== r.team || e.severity >= 3 || !ROLE_INJURY_POSITIONS.has(e.position) || seen.has(e.name)) continue;
    seen.add(e.name);
    out.push(`${{e.name}} (${{e.position}}) ${{e.status}}${{e.injury ? ' (' + e.injury + ')' : ''}} -- may not play: ${{e.reason}}`);
  }}
  return out;
}}
function roleChangeReasons(r) {{
  const out = (r.trade_flags || []).slice();
  const imp = r.injury_impacts;
  if (imp) {{
    const seen = new Set();
    for (const e of [].concat(imp.helps || [], imp.hurts || [])) {{
      if (e.team !== r.team || e.severity < 3 || !ROLE_INJURY_POSITIONS.has(e.position) || seen.has(e.name)) continue;
      seen.add(e.name);
      out.push(`${{e.name}} (${{e.position}}) is ${{e.status}}: ${{e.reason}}`);
    }}
  }}
  if (MARKS[roleKey(r)] === 'flux') out.push('you flagged a role change this week');
  return out;
}}
function roleTag(r) {{
  const hard = r.role_changes || [], soft = r.role_soft || [];
  if (!hard.length && !soft.length) return '';
  const parts = [];
  if (hard.length) parts.push((r.role_capped ? 'Held at 3 instead of MUST BET -- role change:' : 'Role change:') + '\\n- ' + hard.join('\\n- '));
  if (soft.length) parts.push('Heads-up (not blocking):\\n- ' + soft.join('\\n- '));
  return ` <span class="cov-tag impact-hurt${{hard.length ? '' : ' impact-soft'}}" style="margin-left:3px" title="${{escapeHtml(parts.join('\\n'))}}">&#9888;&#65039;</span>`;
}}

function tierEmojiSpan(emo, r) {{
  const parts = [];
  if (SIGNAL_MODE === 'consistency' && r.cons) parts.push(`He cleared ${{r.cons.side}} ${{r.cons.line}} in ${{fmtHit(r.cons.pHits, r.cons.pGames)}} games; ${{r.opponent}} allowed it in ${{fmtHit(r.cons.dHits, r.cons.dGames)}}`);
  else if (r.tier_rel_sd !== null && r.tier_rel_sd !== undefined) parts.push(`Consistency: games swing ${{Math.round(r.tier_sd * 10) / 10}} (${{Math.round(r.tier_rel_sd * 100)}}% of the line; 3+ needs ${{Math.round(MAX_TIER3_REL_SD * 100)}}% or less)`);
  if (r.tier_cap_reason) parts.push(`Held at 2 instead of 3 -- ${{r.tier_cap_reason}}`);
  return (parts.length ? `<span title="${{escapeHtml(parts.join('\\n'))}}">${{emo}}${{r.tier_cap_reason ? '<sup class="muted" style="font-size:9px;">&#8595;</sup>' : ''}}</span>` : emo) + roleTag(r);
}}

function signalEmoji(r) {{
  if (r.hot_level === 4 || r.cold_level === 4) {{
    const side = r.hot_level === 4 ? 'Over' : 'Under';
    const bar = Math.round(MUST_BET_EDGE_PCT * 100);
    const title = SIGNAL_MODE === 'consistency' && r.cons ? `MUST BET (consistency): he cleared ${{r.cons.side}} ${{r.cons.line}} in EVERY game (${{fmtHit(r.cons.pHits, r.cons.pGames)}}), ${{r.opponent}} allowed it in EVERY game (${{fmtHit(r.cons.dHits, r.cons.dGames)}}), and ${{r.opponent}} is one of the 10 defenses allowing the ${{r.cons.side === 'over' ? 'most' : 'least'}} of this stat.` : `Edge AND Anc. Edge both clear a FIXED ${{bar}}% bar on the ${{side}} -- the rarest, highest-conviction tier on this page (above the usual 3-flame/3-ice max). Unlike 1-3 flame/ice, this bar does not move with the "How picky" slider -- it's meant to always mean the same absurd thing. It also requires a perfect record over your selected weeks -- zero games where the player landed on the wrong side of the line -- so a single bad week always blocks it, no matter how big the average edge looks. And the matchup has to fit (an Over needs a defense in the 10 that allow the most of this stat, an Under one of the 10 that allow the least), and his games can't swing more than ${{Math.round(MAX_TIER3_REL_SD * 100)}}% of the line.`;
    return `<span class="cov-tag mustbet-tag" title="${{escapeHtml(title)}}">&#11088; MUST BET</span>` + roleTag(r);
  }}
  if (r.hot_level > 0) return tierEmojiSpan('\U0001F525'.repeat(r.hot_level), r);
  if (r.cold_level > 0) return tierEmojiSpan('\U0001F9CA'.repeat(r.cold_level), r);
  if (r.suppressed_by) {{
    // The stat math agreed, but the price on that side was too steep to
    // bet into (see MAX_JUICE_PRICE) -- shown as a small muted marker
    // rather than silently blank, so it's clear this isn't "no edge",
    // it's "edge, but bad price."
    const p = r.suppressed_by.price;
    const priceStr = p > 0 ? '+' + p : String(p);
    const prob = Math.round(impliedProb(p) * 100);
    const title = `Stat edge agreed on the ${{r.suppressed_by.side}}, but its price (${{priceStr}}, needs to hit ~${{prob}}% of the time just to break even) is worse than the ${{MAX_JUICE_PRICE}} cutoff -- suppressed rather than flagged.`;
    return `<span class="cov-tag cov-medium" title="${{escapeHtml(title)}}">price</span>`;
  }}
  if (r.idea_reason) {{
    const title = `💡 Worth a closer look -- ${{r.idea_reason}}.\n\n${{r.review_reason || ''}}` + (r.tiebreak ? `\n\nSecond look on the ${{r.tiebreak.lean === 'over' ? 'Over' : 'Under'}}:\n` + secondLookText(r.tiebreak) : '');
    return `<span class="cov-tag cov-review" title="${{escapeHtml(title)}}">&#128161;</span>`;
  }}
  if (r.needs_review) {{
    // Edge and Anc. Edge didn't confidently agree, but one of them is
    // significant enough on its own to be worth a manual look -- see
    // enrichRow() for the exact rule and Trevor's original example.
    const title = `Worth a look: ${{r.review_reason}}` + (r.tiebreak ? `\n\nSecond look on the ${{r.tiebreak.lean === 'over' ? 'Over' : 'Under'}}:\n` + secondLookText(r.tiebreak) : '');
    return `<span class="cov-tag cov-review" title="${{escapeHtml(title)}}">❓</span>`;
  }}
  return '';
}}

// Buckets a team's ZONE rate into a 3-tier label describing how much MAN
// they lean on -- Trevor's own thresholds: zone 50-60% counts as "High
// Man" (they're playing man unusually often), 70-90% as "Medium", and
// above 90% as "Low Man" (they almost never play man). He didn't specify
// the 60-70% gap between his first two examples or anything below 50%,
// so those are filled in at the midpoint (65) and by extending "High
// Man" downward (even more zone-averse = even more "High Man") --
// easy to move if 65 isn't where he'd actually draw the line.
const COVERAGE_TIER_CUTOFFS = {{ highManMax: 65, mediumMax: 90 }};

function coverageTier(zoneRate) {{
  if (zoneRate === null || zoneRate === undefined) return null;
  if (zoneRate <= COVERAGE_TIER_CUTOFFS.highManMax) return {{ label: 'High Man', cls: 'cov-highman' }};
  if (zoneRate <= COVERAGE_TIER_CUTOFFS.mediumMax) return {{ label: 'Medium', cls: 'cov-medium' }};
  return {{ label: 'Low Man', cls: 'cov-lowman' }};
}}

// Small tier badge next to an opponent's name showing how much they lean
// on man coverage, straight from data/coverage_cache.json (see
// fetch_coverage.py). Team-level and season-to-date only -- there's no
// free source for how a specific player performs against man vs. zone
// specifically, just how often a defense plays each. Returns '' when
// coverage data hasn't been fetched yet.
function coverageTag(team) {{
  const c = COVERAGE[team];
  if (!c || c.zone_rate === null || c.zone_rate === undefined) return '';
  const tier = coverageTier(c.zone_rate);
  if (!tier) return '';
  const title = `${{team}} coverage (season-to-date): ${{c.man_rate}}% Man / ${{c.zone_rate}}% Zone -- ${{tier.label}}`;
  return ` <span class="cov-tag ${{tier.cls}}" title="${{escapeHtml(title)}}">${{tier.label}}</span>`;
}}

// Added 2026-09-24 per Trevor: a small helmet badge next to a player's
// name when the NFL's own official weekly injury report has them
// designated Questionable/Doubtful/Out this week, sourced from
// data/injuries_cache.json (fetch_injuries.py, straight from nflverse --
// same free, structured, no-scraping source as the stats themselves).
// This is the OFFICIAL report only (status/body part/practice
// participation), not narrative injury news/headlines -- there's no free
// source found for that; Trevor was asked and chose this version. Click
// the player to open their card, where the full detail shows (see
// openPlayerModal below); the badge itself is just a heads-up, not its
// own separate click target, so it doesn't compete with the existing
// row-click-opens-player-card behavior. Returns '' when there's no
// injuries_cache.json yet, or this player has no designation this week
// (true for the large majority of players).
// Red for Out/Doubtful, amber for Questionable or "Missed practice" (the
// practice-report fallback used before a team's final report is out --
// see fetch_injuries.py; added 2026-09-25 so this works for every team
// all week, not just Thursday-night teams).
function injuryTag(r) {{
  const inj = r.injury;
  if (!inj) return '';
  const cls = (inj.status === 'Out' || inj.status === 'Doubtful') ? 'injury-out' : 'cov-lowman';
  const parts = [inj.status];
  if (inj.primary_injury) parts.push(`(${{inj.primary_injury}})`);
  if (inj.practice_status && inj.source !== 'practice') parts.push(`-- ${{inj.practice_status}}`);
  const src = inj.source === 'practice'
    ? 'NFL practice report -- no official game designation yet, final report usually comes out Friday'
    : (inj.source === 'espn' ? 'ESPN injury news' + (inj.note ? ': ' + inj.note : '') : 'NFL official injury report');
  const title = `${{r.player}}: ${{parts.join(' ')}} (${{src}})`;
  return ` <span class="cov-tag ${{cls}} injury-tag" title="${{escapeHtml(title)}}">&#9937;&#65039;</span>`;
}}

// "Impactful injury" badges (added 2026-09-25, replacing the old 🛡️
// O-line badge). Trevor: "what i want is like 'impactful Injury' to the
// player and to the defense." Per stat row, computed server-side in
// compute_injury_impacts() from IMPACT_RULES:
//   green 🩹▲ = injuries that HELP this player on this stat (another WR
//     out = vacated targets; the opposing defense's starting CBs out, etc.)
//   red 🩹▼ = injuries that HURT him (his O-line, his QB, his top
//     targets, etc.)
// Only injured players with a real role count (50%+ snap share this
// season -- IMPACT_SNAP_PCT). Full strength when at least one of them is
// Out/Doubtful; faded when it's only Questionable/missed-practice, since
// those players may well suit up.
function impactItemText(e) {{
  let snaps = e.snap_pct !== null && e.snap_pct !== undefined ? `${{Math.round(e.snap_pct * 100)}}% snaps` : '';
  if (e.carry_share) snaps += (snaps ? ', ' : '') + `${{Math.round(e.carry_share * 100)}}% of RB carries`;
  const inj = e.injury ? ` (${{e.injury}})` : '';
  return `${{e.name}}, ${{e.team}} ${{e.position}}${{snaps ? ', ' + snaps : ''}} -- ${{e.status}}${{inj}}${{e.source === 'espn' ? ' [ESPN]' : ''}}: ${{e.reason}}`;
}}

function impactTags(r) {{
  const imp = r.injury_impacts;
  if (!imp) return '';
  let out = '';
  const build = (list, cls, arrow, heading) => {{
    if (!list || !list.length) return '';
    const strong = list.some(e => e.severity >= 3);
    const title = `${{heading}} ${{r.player}}'s ${{r.stat_label}}:\\n` + list.map(e => '- ' + impactItemText(e)).join('\\n');
    return ` <span class="cov-tag ${{cls}} impact-tag${{strong ? '' : ' impact-soft'}}" title="${{escapeHtml(title)}}">&#129657;${{arrow}}</span>`;
  }};
  out += build(imp.helps, 'impact-help', '&#9650;', 'Injuries that HELP');
  out += build(imp.hurts, 'impact-hurt', '&#9660;', 'Injuries that HURT');
  return out;
}}

// 🪜 Ladder badge -- added 2026-09-24 per Trevor, deliberately kept
// simple rather than pulling real sportsbook ladder/alternate-line
// markets: "if a player has gone like over the yardage that their line
// is by like double or something like that at some point during the
// year." Flags a player+stat whose single BEST game this season already
// cleared a fixed multiple of the CURRENT posted line -- a proven
// ceiling well above what the book is asking right now, using data this
// dashboard already has (game_log, vegas_line), no new fetch needed.
//
// Deliberately scoped to just the volume/yardage stats where "double the
// line" means something real -- QB Pass/Rush Yds, RB Rush/Rec Yds, WR/TE
// Rec Yds, per Trevor's exact list. Left out on purpose: low-count stats
// like TDs/INTs, where a typical 0.5 line makes "2x" trivial (any player
// who scores at all already clears it), which would make the badge
// meaningless there.
//
// Checks the player's FULL season game_log, not the selected Weeks --
// this is a "has this ever happened" question about their ceiling, not
// a recent-form question, so it deliberately ignores the Weeks filter.
// Compared against r.vegas_line (the current consensus line), not the
// line-shopped best_line, since "their line" is naturally read as the
// one flat number currently posted, not a specific book's shopped side.
//
// MIN_LADDER_LINE added 2026-09-24 (same day, follow-up): the very first
// real-data check turned up exactly the thin case flagged when this
// shipped -- Aaron Rodgers' QB Rush Yds line was 0.5, so his one 5-yard
// scramble read as "10x the line," which is correct arithmetic but not
// a real proven ceiling. Trevor's fix: require the CURRENT line itself
// to be at least 30 (yards) before the ratio check even runs, so a tiny
// line can't trivially produce a huge, meaningless ratio. This also
// naturally excludes the low-count stats' worst edge cases even further,
// on top of the position/stat scoping below.
const LADDER_STATS = {{
  QB: ['passing_yards', 'rushing_yards'],
  RB: ['rushing_yards', 'receiving_yards'],
  WR: ['receiving_yards'],
  TE: ['receiving_yards'],
}};
const LADDER_MULTIPLIER = 2; // "double or something" -- Claude's own pick, easy to retune
const MIN_LADDER_LINE = 30; // yards -- per Trevor, added 2026-09-24 so a thin line (e.g. a 0.5 QB Rush Yds line) can't trivially produce a huge ratio

function ladderInfo(r) {{
  const allowed = LADDER_STATS[r.position];
  if (!allowed || !allowed.includes(r.stat_col)) return null;
  if (r.vegas_line === null || r.vegas_line === undefined || r.vegas_line < MIN_LADDER_LINE) return null;
  if (!r.game_log || !r.game_log.length) return null;
  let bestIdx = -1, bestVal = -Infinity;
  for (let i = 0; i < r.game_log.length; i++) {{
    if (r.game_log[i] > bestVal) {{ bestVal = r.game_log[i]; bestIdx = i; }}
  }}
  if (bestVal <= 0) return null; // a negative/zero "best game" (e.g. an all-sack Rush Yds season so far) isn't a ceiling
  const ratio = bestVal / r.vegas_line;
  if (ratio < LADDER_MULTIPLIER) return null;
  return {{
    value: bestVal,
    ratio,
    week: r.game_weeks ? r.game_weeks[bestIdx] : null,
    opponent: r.game_opponents ? r.game_opponents[bestIdx] : null,
  }};
}}

// Alt-line idea (2026-10-30, per Trevor: "if a projection is over and like
// way over the line, you could suggest an alternate line"). No alt-line
// odds are pulled (they'd cost extra Odds API credits), so this only
// suggests a number to look up at the book: Anticipated is 25%+ past the
// line, and the alt line is the furthest step (5 for yards, 1 for counts)
// that stays short of the projection and that he cleared in 75%+ of the
// selected games (3+ games).
const ALT_PROJ_RATIO = 1.25;
const ALT_HIT_RATE = 0.75;
function altLineInfo(r, weeks, proj, line) {{
  if (proj === null || line === null || line === undefined || !r.game_log || !r.game_weeks) return null;
  const vals = [];
  for (let i = 0; i < r.game_log.length; i++) if (weeks.has(r.game_weeks[i]) && r.game_weeks[i] < WEEK) vals.push(r.game_log[i]);
  if (vals.length < 3) return null;
  const step = /yards/.test(r.stat_col) ? 5 : 1;
  // Overs only (2026-10-30, per Trevor: "you can't bet alt unders").
  const over = proj >= line * ALT_PROJ_RATIO && proj - line >= step;
  if (!over) return null;
  let best = null;
  for (let k = 1; k < 20; k++) {{
    const L = over ? line + k * step : line - k * step;
    if (over ? L >= proj : (L <= proj || L <= 0)) break;
    const hits = vals.filter(v => over ? v > L : v < L).length;
    if (hits / vals.length >= ALT_HIT_RATE) best = {{ side: over ? 'over' : 'under', line: L, hits, n: vals.length }};
  }}
  return best ? Object.assign(best, {{ proj }}) : null;
}}
// 🎯 next to the player name (moved from the narrow Opp Rank cell on
// 2026-10-30 -- Trevor couldn't see it there).
function outlierTag(r) {{
  const o = r.outlier_def;
  if (!o) return '';
  const title = `🎯 Outlier defense: ${{o.text}} -- favors the ${{o.side === 'over' ? 'Over' : 'Under'}}` + (r.outlier_value ? `. ${{r.outlier_value}}` : '');
  return ` <span class="cov-tag" title="${{escapeHtml(title)}}">&#127919; ${{o.side === 'over' ? 'O' : 'U'}}</span>`;
}}
function altLineTag(r) {{
  const a = r.alt_line;
  if (!a) return '';
  const sideWord = a.side === 'over' ? 'Over' : 'Under';
  const title = `Alt-line idea: projects ${{a.proj}} vs the ${{r.best_line ?? r.vegas_line}} line, and he went ${{a.side === 'over' ? 'over' : 'under'}} ${{a.line}} in ${{a.hits}} of ${{a.n}} selected games. Look up the ${{sideWord}} ${{a.line}} alt line at the book -- no alt odds are pulled here, so check the price.`;
  return ` <span class="cov-tag" title="${{escapeHtml(title)}}">${{a.side === 'over' ? '&#11014;' : '&#11015;'}} Alt ${{a.side === 'over' ? 'O' : 'U'}} ${{a.line}}</span>`;
}}

function ladderTag(r) {{
  const info = ladderInfo(r);
  if (!info) return '';
  const ratioStr = (Math.round(info.ratio * 10) / 10) + 'x';
  const whenStr = info.week ? `Wk${{info.week}}${{info.opponent ? ' vs ' + info.opponent : ''}}` : 'earlier this season';
  const title = `${{r.stat_label}}: posted ${{info.value}} in ${{whenStr}} -- ${{ratioStr}} the current line (${{r.vegas_line}}). A proven ceiling well above what's being asked right now (fixed ${{LADDER_MULTIPLIER}}x bar).`;
  return ` <span class="cov-tag ladder-tag" title="${{escapeHtml(title)}}">&#129692;</span>`;
}}

// "Weak matchup" filter (added 2026-09-24 per Trevor, as a companion to
// the ladder badge above): "add a filter so if the defense the player is
// opposing is 20-32 ranked, meaning they give up a lot of that stat."
// Opp Rank (r.def_rank, computed in enrichRow()/rankDefenses()) already
// runs 1 = toughest matchup (allows the least) to def_rank_max = easiest
// (allows the most) -- see the column header tooltip. This just checks
// whether that same number falls in the bottom third of the league,
// i.e. a defense that's a soft matchup for this exact position/stat over
// whatever weeks are currently selected. WEAK_DEFENSE_RANK_MIN=20 is
// Trevor's own literal "20-32" -- since the NFL always has 32 teams this
// reads naturally as "ranked in the bottom 13," but if def_rank_max ever
// comes in under 32 (e.g. a team with no games yet in a very narrow
// Weeks selection drops out of the ranking pool entirely) the top of
// that range simply becomes whatever def_rank_max is, and the bottom
// (20) doesn't rescale -- flagged as an assumption, not something
// Trevor asked to handle explicitly.
const WEAK_DEFENSE_RANK_MIN = 20;

function isWeakMatchup(r) {{
  if (r.def_rank === null || r.def_rank === undefined) return false;
  return r.def_rank >= WEAK_DEFENSE_RANK_MIN;
}}

// "Strong matchup" filter (added 2026-09-24 per Trevor, as the mirror
// image of the "Weak matchup" filter above): "can you make that filter
// again but only for like strong defenses? so if i'm looking at unders i
// can see what defenses are limiting that stat best?" Same r.def_rank
// field, just checked at the opposite end -- 1 = the single toughest
// matchup for this position/stat (allows the least), so a LOW number is
// a defense that's currently limiting that stat well, which is exactly
// what makes an Under more attractive. STRONG_DEFENSE_RANK_MAX=13 mirrors
// the weak filter's own bottom-13-of-32 width (20-32) onto the top end
// (1-13) so both filters carve out the same-size top/bottom thirds of a
// 32-team league. Unlike the weak filter, this end doesn't have the
// def_rank_max edge case -- rank 1-13 always means the same thing
// regardless of how many teams have valid data for the selected weeks,
// since a team's rank can only go as high as the pool actually ranked
// (it just means the "strong" bucket could theoretically end up smaller
// than 13 teams if def_rank_max itself drops below 13, which doesn't
// happen in-season with real data).
const STRONG_DEFENSE_RANK_MAX = 13;

function isStrongMatchup(r) {{
  if (r.def_rank === null || r.def_rank === undefined) return false;
  return r.def_rank <= STRONG_DEFENSE_RANK_MAX;
}}

// Added 2026-09-24 per Trevor: once recent form tells us which side of a
// line looks good, don't grade it against one flat consensus number --
// grade it against whichever actual book offers the most favorable price
// for THAT side. An Over wants the lowest available line (least you need
// to clear); an Under wants the highest (most cushion). Only books that
// actually posted a line for this player/stat are considered.
//
// Tie-break added 2026-09-24 (follow-up, same day): Trevor caught a real
// row where DraftKings (0.5 at -116) was highlighted as the "most
// advantageous" book over FanDuel (0.5 at -110), even though -110 is
// objectively the better price for the identical line -- the original
// version only compared lines and broke any tie by book-list-order
// (DraftKings first), never looking at price at all. Fixed: when two or
// more books tie on the best line, the tie is now broken by price, using
// whichever price field matches the side actually being shopped (Over
// price for an Over tie, Under price for an Under tie -- see book_line()
// in build_dashboard.py for why both are now tracked per book). In
// American odds, a HIGHER raw number is always the better price for the
// bettor, whether negative or positive -- -110 beats -116, +150 beats
// +120, and any positive beats any negative -- so a plain numeric
// comparison works regardless of sign, no decimal-odds conversion
// needed. A book missing a price for that side loses the tie-break to
// one that has it; if neither has a price, the original list-order
// fallback still applies.
function pickBestLine(r, direction) {{
  const priceKey = direction === 'over' ? 'over_price' : 'under_price';
  const candidates = [
    {{ book: 'draftkings', line: r.draftkings_line, price: r['draftkings_' + priceKey] }},
    {{ book: 'fanduel', line: r.fanduel_line, price: r['fanduel_' + priceKey] }},
    {{ book: 'betmgm', line: r.betmgm_line, price: r['betmgm_' + priceKey] }},
  ].filter(c => c.line !== null && c.line !== undefined);
  if (!candidates.length) return null;
  const lineIsBetter = direction === 'over'
    ? (a, b) => a.line < b.line
    : (a, b) => a.line > b.line;
  return candidates.reduce((best, c) => {{
    if (lineIsBetter(c, best)) return c;
    if (lineIsBetter(best, c)) return best;
    // Lines tied -- break by price (higher raw number always wins, see
    // comment above).
    const cHas = c.price !== null && c.price !== undefined;
    const bestHas = best.price !== null && best.price !== undefined;
    if (cHas && bestHas) return c.price > best.price ? c : best;
    if (cHas && !bestHas) return c;
    return best;
  }});
}}

// Recompute Recent Avg / Games / Edge / Hit Rate / Team Share from a row's
// raw game log for whatever sample size is currently selected, so the
// filter is instant with no re-fetching.
// Which of a player's logged games fall in the selected weeks, as indices
// into game_log/game_weeks/game_seasons/team_total_log (all four arrays
// are parallel, one entry per game, most-recent-first). game_seasons is
// checked too even though the cache is current-season-only now, as a
// defensive no-op in case that ever changes again.
function playerSelectedIndices(r, weeks) {{
  const idx = [];
  for (let i = 0; i < r.game_log.length; i++) {{
    if (r.game_seasons[i] === SEASON && weeks.has(r.game_weeks[i])) idx.push(i);
  }}
  return idx;
}}

// Same idea for a defense's per-game log (DEFENSE_LOGS), using its
// parallel DEFENSE_GAMES metadata array to know which week each index is.
function defenseSelectedIndices(gamesMeta, weeks) {{
  const idx = [];
  for (let i = 0; i < gamesMeta.length; i++) {{
    const g = gamesMeta[i];
    if (g && g.season === SEASON && weeks.has(g.week)) idx.push(i);
  }}
  return idx;
}}

// Compact label for the Weeks toggle button and every "as of X weeks"
// caption on the page, e.g. {{1,2,3}} -> "Wk 1-3", {{1,2,3,7,9,10}} ->
// "Wk 1-3, 7, 9-10", the full set -> "All", empty -> "none selected".
function weeksLabel(weeks) {{
  const sorted = Array.from(weeks).sort((a, b) => a - b);
  if (!sorted.length) return 'none selected';
  if (sorted.length === TOTAL_WEEKS) return 'All';
  const ranges = [];
  let start = sorted[0], prev = sorted[0];
  for (let i = 1; i <= sorted.length; i++) {{
    const cur = sorted[i];
    if (cur === prev + 1) {{ prev = cur; continue; }}
    ranges.push(start === prev ? `${{start}}` : `${{start}}-${{prev}}`);
    start = cur; prev = cur;
  }}
  return 'Wk ' + ranges.join(', ');
}}

function deriveStats(r, weeks) {{
  const idx = playerSelectedIndices(r, weeks);
  const slice = idx.map(i => r.game_log[i]);
  const gamesUsed = slice.length;
  const avg = gamesUsed ? slice.reduce((a, b) => a + b, 0) / gamesUsed : null;
  const recentAvg = avg === null ? null : Math.round(avg * 100) / 100;
  let edge = null, edgePct = null, hitRate = null, bestLine = null, bestBook = null, direction = null;
  let belowCount = null, aboveCount = null;
  if (recentAvg !== null && r.vegas_line !== null && r.vegas_line !== undefined) {{
    // Which side does recent form favor against the consensus? That
    // decides whether we're line-shopping for the lowest or highest book
    // number. A dead-even tie has no side to shop for, so it falls back
    // to the flat consensus line, same as before this feature existed.
    // Returned below (not just used locally) so downstream code -- the
    // price gate and the DK/FD/BetMGM column display -- knows which
    // side's price to read for the pinned book, instead of guessing.
    direction = recentAvg > r.vegas_line ? 'over' : (recentAvg < r.vegas_line ? 'under' : null);
    const picked = direction ? pickBestLine(r, direction) : null;
    bestLine = picked ? picked.line : r.vegas_line;
    bestBook = picked ? picked.book : null;
    edge = Math.round((recentAvg - bestLine) * 10) / 10;
    edgePct = bestLine ? edge / bestLine : null;
    const hits = slice.filter(v => v > bestLine).length;
    hitRate = gamesUsed ? Math.round(100 * hits / gamesUsed) : null;
    // belowCount/aboveCount: how many individual games (within the SAME
    // selected-weeks window) actually finished on each side of bestLine --
    // added 2026-09-24 as the input to the MUST BET consistency gate below
    // (see enrichRow). aboveCount is the same set as "hits" above, just
    // named for its other use; belowCount is new -- strictly less-than, so
    // a push (exactly on the line) counts as neither "went beneath" nor
    // "went above."
    belowCount = slice.filter(v => v < bestLine).length;
    aboveCount = hits;
  }}
  // Team share: this player's cut of their team's own production at this
  // position/stat, over the same games (RB rushing = RBs only, receiving =
  // same position only). QBs are always 100% by convention -- there's only
  // one starting passer, so this is fixed rather than computed from a
  // ratio, otherwise a low-mobility QB with 0 rush yards over the selected
  // window would divide 0/0 and wrongly show a blank share instead of 100%.
  let share = null;
  if (r.position === 'QB') {{
    share = 100;
  }} else if (r.team_total_log && r.team_total_log.length) {{
    const teamSlice = idx.map(i => r.team_total_log[i]);
    const playerSum = slice.reduce((a, b) => a + b, 0);
    const teamSum = teamSlice.reduce((a, b) => a + b, 0);
    share = teamSum > 0 ? Math.round((playerSum / teamSum) * 1000) / 10 : null;
  }}
  return {{ recent_avg: recentAvg, games_used: gamesUsed, edge, edge_pct: edgePct, hit_rate: hitRate, share, best_line: bestLine, best_book: bestBook, direction, below_count: belowCount, above_count: aboveCount }};
}}

// For a given position+stat, filter every team's defense game log down to
// the selected weeks and rank them against each other over that same set
// (1 = allows the least / toughest, higher = allows more).
function rankDefenses(posStatKey, weeks) {{
  const pos = posStatKey.split('|')[0];
  const teamLogs = DEFENSE_LOGS[posStatKey] || {{}};
  const avgs = {{}};
  for (const [team, log] of Object.entries(teamLogs)) {{
    const meta = (DEFENSE_GAMES[team] && DEFENSE_GAMES[team][pos]) || [];
    const idx = defenseSelectedIndices(meta, weeks);
    const slice = idx.map(i => log[i]);
    avgs[team] = slice.length ? slice.reduce((a, b) => a + b, 0) / slice.length : null;
  }}
  const entries = Object.entries(avgs).filter(([, v]) => v !== null).sort((a, b) => a[1] - b[1]);
  const ranks = {{}};
  for (let i = 0; i < entries.length; i++) {{
    const [team, val] = entries[i];
    ranks[team] = (i > 0 && entries[i - 1][1] === val) ? ranks[entries[i - 1][0]] : i + 1;
  }}
  return {{ avgs, ranks }};
}}

// Adds every derived/computed field (Recent Avg, Opp Allows/Rank, Team
// Share, Anticipated, Edge, Anc. Edge, hot/cold) to one row, for whatever
// set of weeks is passed in. Shared by the main table render() and the
// player detail modal, so the two never drift out of sync with each
// other. defCache is a plain {{}} the caller creates once per pass, so
// rankDefenses() isn't recomputed for every row that shares a position+stat.
// ---- "Second look" checklist (added 2026-10-01, per Trevor: "there are so
// many question mark bets right now, is there any way we could build some
// more analysis in there?"). For every row with a signal (MUST BET, fire,
// ice, ❓) this runs a checklist on the side the signal points to, using
// things Edge/Anc. Edge don't look at: hit rate vs. the line, volume
// (targets/carries/attempts he gets vs. needs at his own rate), game
// script from the spread/total, matchup rank, injuries, weather and price.
//
// Deliberately NOT turned into a "Lean/Pass" verdict: a backtest on Week 3
// (every flagged row from the pre-game dashboard, graded against the real
// box scores) found the combined score didn't separate winners from losers
// -- ❓ rows went 61-83 on their signal side, and "Lean" ❓s did worse, not
// better. The one factor that held up was game script (❓ rows it supported
// 11-8, ones it argued against 7-16), consistent with the INT study -- so
// that's the only one surfaced in the main table (✔/⚠ script tag); the
// rest is context in the player card. One week is a small sample; re-test
// as weeks accumulate (run.py now archives each build in history/).
const TB_VOLUME_STAT = {{
  receiving_yards: 'targets', receptions: 'targets',
  rushing_yards: 'carries',
  passing_yards: 'attempts', completions: 'attempts',
}};
const TB_VOLUME_LABEL = {{ targets: 'targets', carries: 'carries', attempts: 'pass attempts' }};
const TB_PASS_GAME = new Set(['passing_yards', 'attempts', 'completions', 'receiving_yards', 'receptions', 'targets', 'receiving_air_yards']);
const TB_EXPENSIVE = -135;  // a lean-side price at or worse than this counts against

function tbGame(r) {{
  return GAMES.find(g => g.key === gameKey(r)) || null;
}}
// + = this player's team is favored by that many points
function tbTeamSpread(r, g) {{
  if (!g || g.spread === null || g.spread === undefined) return null;
  const homeFav = g.spread; // nflverse spread_line: positive = home team favored
  return r.at_opponent ? -homeFav : homeFav;
}}
function tbMedian(a) {{
  const s = a.slice().sort((x, y) => x - y);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}}
function tiebreak(r, derived, lean, defRank, defRankMax, leanFromAnc, weeks) {{
  const factors = [];
  const add = (name, effect, text) => factors.push({{ name, effect, text }});
  const sideWord = lean === 'over' ? 'Over' : 'Under';
  const mkt = bestMarketFor(r, lean);
  const line = mkt ? mkt.line : r.vegas_line;
  const idx = playerSelectedIndices(r, weeks);
  const vals = idx.map(i => r.game_log[i]);
  const cautions = [];
  if (line === null || line === undefined) return null;

  // Hit rate
  if (vals.length) {{
    const hits = vals.filter(v => lean === 'over' ? v > line : v < line).length;
    const rate = hits / vals.length;
    const eff = rate >= 0.6 ? 1 : (rate <= 0.4 ? -1 : 0);
    add('Hit rate', eff, `${{hits}} of ${{vals.length}} games went ${{sideWord.toLowerCase()}} ${{line}} (${{vals.map(v => Math.round(v * 10) / 10).join(', ')}})`);
  }}
  if (vals.length < 3) cautions.push(`only ${{vals.length}} game${{vals.length === 1 ? '' : 's'}} in the sample`);
  if (vals.length >= 3) {{
    const med = tbMedian(vals);
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    if (mean > 0 && Math.abs(mean - med) / mean > 0.35) cautions.push(`one big/small game skews the average (avg ${{Math.round(mean * 10) / 10}} vs median ${{Math.round(med * 10) / 10}})`);
  }}

  // Volume: opportunities he gets vs. needs at his own rate
  const volCol = (r.position === 'QB' && r.stat_col === 'rushing_yards') ? null : TB_VOLUME_STAT[r.stat_col];
  if (volCol) {{
    const sib = ROWS.find(x => x.player === r.player && x.team === r.team && x.stat_col === volCol);
    if (sib) {{
      const byWeek = {{}};
      sib.game_weeks.forEach((w, i) => {{ byWeek[sib.game_seasons[i] + '|' + w] = sib.game_log[i]; }});
      let sumStat = 0, sumVol = 0, n = 0;
      idx.forEach(i => {{
        const v = byWeek[r.game_seasons[i] + '|' + r.game_weeks[i]];
        if (v === undefined) return;
        sumStat += r.game_log[i]; sumVol += v; n++;
      }});
      if (n && sumVol > 0 && sumStat > 0) {{
        const perOpp = sumStat / sumVol;
        const need = line / perOpp;
        const avgVol = sumVol / n;
        const ratio = avgVol / need;
        const eff = lean === 'over' ? (ratio >= 1.1 ? 1 : (ratio <= 0.9 ? -1 : 0)) : (ratio <= 0.9 ? 1 : (ratio >= 1.1 ? -1 : 0));
        const lbl = TB_VOLUME_LABEL[volCol];
        add('Volume', eff, `averaging ${{Math.round(avgVol * 10) / 10}} ${{lbl}}; at his ${{Math.round(perOpp * 100) / 100}} per ${{lbl.replace(/s$/, '')}} he needs ~${{Math.round(need * 10) / 10}} to reach ${{line}}`);
        if (avgVol < 4 && (volCol === 'targets' || volCol === 'carries')) cautions.push(`low volume (${{Math.round(avgVol * 10) / 10}} ${{lbl}}/game) -- one play swings it`);
      }}
    }}
  }}

  // Game script from the spread/total
  const g = tbGame(r);
  const sp = tbTeamSpread(r, g);
  if (sp !== null) {{
    const favTxt = sp > 0 ? `favored by ${{sp}}` : (sp < 0 ? `a ${{-sp}}-pt underdog` : 'a pick-em');
    let dir = 0, why = '';
    const sc = r.stat_col;
    if (sc === 'passing_tds' || sc === 'total_tds') {{
      if (g.total !== null && g.total !== undefined) {{
        const tt = g.total / 2 + sp / 2;
        dir = tt >= 25 ? 1 : (tt <= 18.5 ? -1 : 0);
        why = `team implied total ${{Math.round(tt * 10) / 10}} (O/U ${{g.total}}, ${{favTxt}})`;
      }}
    }} else if (r.position === 'QB' && sc === 'rushing_yards') {{
      dir = sp <= -4 ? 1 : 0;
      why = `${{favTxt}}${{sp <= -4 ? ' -- trailing QBs scramble more' : ''}}`;
    }} else if (sc === 'passing_interceptions') {{
      dir = sp <= -4 ? 1 : (sp >= 7 ? -1 : 0);
      why = `${{favTxt}}${{sp <= -4 ? ' -- more passes while trailing' : (sp >= 7 ? ' -- big favorites throw less late' : '')}}`;
    }} else if (TB_PASS_GAME.has(sc)) {{
      dir = sp <= -4 ? 1 : (sp >= 7 ? -1 : 0);
      why = `${{favTxt}}${{sp <= -4 ? ' -- likely trailing and throwing' : (sp >= 7 ? ' -- may run out the clock' : '')}}`;
    }} else if (r.position === 'RB' && (sc === 'rushing_yards' || sc === 'carries')) {{
      dir = sp >= 4 ? 1 : (sp <= -7 ? -1 : 0);
      why = `${{favTxt}}${{sp >= 4 ? ' -- favorites lean on the run' : (sp <= -7 ? ' -- big underdogs abandon the run' : '')}}`;
    }}
    if (why) add('Game script', lean === 'over' ? dir : -dir, why);
  }}

  // Matchup (skip when Anc. Edge -- itself matchup-based -- is the reason)
  if (!leanFromAnc && defRank !== null && defRank !== undefined && defRankMax) {{
    const soft = defRank >= Math.round(defRankMax * 0.6);
    const tough = defRank <= Math.round(defRankMax * 0.4);
    const dir = soft ? 1 : (tough ? -1 : 0);
    add('Matchup', lean === 'over' ? dir : -dir, `${{r.opponent}} ranks #${{defRank}} of ${{defRankMax}} vs ${{r.position}} ${{r.stat_label}} (${{soft ? 'soft' : tough ? 'tough' : 'middle'}})`);
  }}

  // Injuries
  const imp = r.injury_impacts;
  if (imp) {{
    const strong = (l) => (l || []).filter(e => (e.severity || 0) >= 3);
    const h = strong(imp.helps), u = strong(imp.hurts);
    if (h.length || u.length) {{
      const dir = h.length && !u.length ? 1 : (u.length && !h.length ? -1 : 0);
      const names = [...h.map(e => '+' + e.name + ' ' + e.status), ...u.map(e => '-' + e.name + ' ' + e.status)].join(', ');
      add('Injuries', lean === 'over' ? dir : -dir, names);
    }}
  }}

  // Weather
  if (r.weather_bad && TB_PASS_GAME.has(r.stat_col)) {{
    add('Weather', lean === 'over' ? -1 : 1, r.weather || 'bad weather');
  }}

  // Price
  if (mkt) {{
    const p = mkt.price;
    add('Price', p <= TB_EXPENSIVE ? -1 : 0, `${{sideWord}} ${{mkt.line}} at ${{p > 0 ? '+' + p : p}} (${{mkt.book}})${{p <= TB_EXPENSIVE ? ' -- expensive' : ''}}`);
  }}

  const net = factors.reduce((a, f) => a + f.effect, 0);
  const pros = factors.filter(f => f.effect > 0).length;
  const cons = factors.filter(f => f.effect < 0).length;
  const script = factors.find(f => f.name === 'Game script') || null;
  return {{ lean, line, net, pros, cons, factors, cautions, script }};
}}

// ✔/⚠ game-script tag for the main table (any row with a signal).
function scriptTag(r) {{
  const t = r.tiebreak;
  if (!t || !t.script || t.script.effect === 0) return '';
  const side = t.lean === 'over' ? 'Over' : 'Under';
  if (t.script.effect > 0) return `<span class="cov-tag tb-script-good" title="${{escapeHtml('Game script supports the ' + side + ': ' + t.script.text)}}">&#10004; script</span>`;
  return `<span class="cov-tag tb-script-bad" title="${{escapeHtml('Game script argues against the ' + side + ': ' + t.script.text + '. In the Week 3 backtest, flagged rows like this went 7-16.')}}">&#9888; script</span>`;
}}
function secondLookText(t) {{
  const lines = t.factors.map(f => `${{f.effect > 0 ? '✔' : f.effect < 0 ? '✘' : '•'}} ${{f.name}}: ${{f.text}}`);
  if (t.cautions.length) lines.push('⚠ ' + t.cautions.join('; '));
  return lines.join('\\n');
}}


// ---- Consistency mode (added 2026-10-05, per Trevor: "i think the way i
// want to bet this is more based on consistency than by how much it
// exceeds the line ... i care more about how consistently the player has
// exceeded the number and how commonly the defense has allowed the
// number"). Two hit rates, on the same side and the same shopped line:
//   Hit     -- share of HIS games (selected weeks) that cleared the line
//   Opp Hit -- share of the OPPONENT's games (selected weeks) where what
//              that defense allowed to this position, times his usual
//              share of his team's production, would have cleared it.
//              (QBs are 100% of their team, so it's simply what the
//              defense allowed to QBs.)
// Tiers (built after testing every hit-rate combination on the Week 4
// board against the real results -- his own perfect record was the
// strongest pattern: 67-40 when he'd cleared it every game, ~50/50 when
// he'd missed even once; perfect on both sides went 29-14):
//   1 flame/ice: he cleared it in 75%+ of games (not all) AND the defense
//      allowed it 75%+ (only possible with 4+ games)
//   2: he cleared it EVERY game and the defense allowed it in 2/3+ of games
//   3: he cleared it EVERY game and the defense 75%+ (so 3/3 or 3/4+), plus
//      the top-10 matchup rule (Over: one of the 10 allowing the most;
//      Under: one of the 10 allowing the least) -- otherwise held at 2
//   MUST BET: he cleared it every game AND the defense allowed it every
//      game, 4+ games on both sides, plus the same matchup rule
//   ❓: he cleared it every game but the defense usually holds it under
//      2/3 -- the two disagree
// Needs at least CONS_MIN_GAMES games on both sides. The old average-edge
// formula is still available from the "Signals" dropdown.
const CONS_TIERS = [0.66, 0.75];
const CONS_MUST_MIN_GAMES = 4;
const CONS_MIN_GAMES = 3;
// Weeks filter drives the recommendations too (added 2026-10-07, per
// Trevor: "if i select only weeks 3 and 4 that should update both the stats
// and recommendations, but keep the lines there"). The game minimums scale
// down to however many already-played weeks are selected, so picking Wk 3-4
// grades everyone on those 2 games instead of showing no signals at all
// (a player with a bye in that window just has fewer games and may drop out).
function signalSampleNote() {{
  const n = playedWeeksSelected(selectedWeeks);
  return `  ·  Signals use ${{weeksLabel(selectedWeeks)}}: ${{n}} played week${{n === 1 ? '' : 's'}}` + (n < 3 ? ' -- small sample, treat signals as rough' : '') + (n < CONS_MUST_MIN_GAMES ? `; MUST BET needs ${{CONS_MUST_MIN_GAMES}}+` : '');
}}
function playedWeeksSelected(weeks) {{
  return Array.from(weeks).filter(w => w < WEEK).length;
}}
function consMinGames(weeks) {{
  return Math.max(1, Math.min(CONS_MIN_GAMES, playedWeeksSelected(weeks)));
}}
// MUST BET does NOT scale down: it always needs 4+ games on both sides, so a
// 2-week window can produce 1-3 flames/ice but never a MUST BET (2-for-2 on
// both sides would otherwise have made 25 MUST BETs on the Week 5 board).
function consMustMinGames(weeks) {{
  return CONS_MUST_MIN_GAMES;
}}
let SIGNAL_MODE = 'consistency';
try {{
  const savedMode = localStorage.getItem('nfl_prop_dashboard_signal_mode');
  if (savedMode === 'edge' || savedMode === 'consistency') SIGNAL_MODE = savedMode;
}} catch (e) {{}}

// Opponent-adjusted hit rates (added 2026-10-05, per Trevor: "if the team
// played a team who never does qb rushes, it would skew the stats ... say
// 3/4 of the games were over and 1/4 was a team that barely runs it").
// A MISS is "excused" when the opponent explains it:
//   Hit (his games): he missed against one of the EXCUSE_TOUGH_TOP toughest
//     defenses for this stat (Over) / softest (Under).
//   Opp Hit (the defense's games): the offense it faced rarely produces this
//     stat at all -- that offense's usual output at his position, scaled to
//     his share, is under 75% of the line (Over) or over 1/0.75 = ~1.33x it
//     (Under) -- i.e. that offense usually doesn't get there on its own.
//     "Usual output" = what that offense got in its OTHER games.
// Adjusted rate = hits / (games - excused misses), used when at least
// CONS_MIN_GAMES games remain; hits are never removed. Shown in brackets,
// e.g. "O 3/4 (3/3)". MUST BET still needs a raw perfect player record.
// Was 5 until 2026-10-16; Trevor: "less rigid than top 5, maybe make it top
// 10 on either side" (prompted by Javonte Williams' only miss coming vs #1 BAL).
const EXCUSE_TOUGH_TOP = 10;
const EXCUSE_OFF_RATIO = 0.75;
const _offenseCache = {{}};
function offenseGames(key, pos, weeks) {{
  const ck = key + '|' + Array.from(weeks).sort((a, b) => a - b).join(',');
  if (_offenseCache[ck]) return _offenseCache[ck];
  const byOff = {{}};
  const logs = DEFENSE_LOGS[key] || {{}};
  for (const [def, log] of Object.entries(logs)) {{
    const meta = (DEFENSE_GAMES[def] && DEFENSE_GAMES[def][pos]) || [];
    for (const i of defenseSelectedIndices(meta, weeks)) {{
      const off = meta[i] && meta[i].vs;
      if (!off) continue;
      (byOff[off] = byOff[off] || []).push({{ def, week: meta[i].week, val: log[i] }});
    }}
  }}
  return (_offenseCache[ck] = byOff);
}}
function offenseUsual(key, pos, weeks, off, exclDef, exclWeek) {{
  const g = (offenseGames(key, pos, weeks)[off] || []).filter(x => !(x.def === exclDef && x.week === exclWeek));
  return g.length ? g.reduce((a, b) => a + b.val, 0) / g.length : null;
}}

// Matchup mismatch (added 2026-10-16, per Trevor: "atlanta allows a lot of
// yards to good run offenses and holds bad ones in check. don't tell me to
// go under when chicago is a huge run offense"). Offenses are ranked by
// what their position group produces of this stat per game (1 = most).
// Under: if this week's offense is top-MISMATCH_OFF_TOP, the defense must
// have held the top-half offenses it faced too -- if a top-half offense got
// over the line, or it hasn't faced one, it's not a pick (shown as ❓ with
// the reason). Over: the mirror, for a bottom-MISMATCH_OFF_TOP offense vs a
// defense that only gave it up to stronger offenses.
const MISMATCH_OFF_TOP = 10;
function matchupMismatch(r, cons, weeks) {{
  if (!cons || !cons.dg || !cons.dg.length) return null;
  // Same ranking the defense popup shows (rankOffenses, 1 = produces the most).
  const {{ ranks }} = rankOffenses(r.position + '|' + r.stat_col, r.position, weeks);
  const n = Object.keys(ranks).length;
  const me = ranks[r.team];
  if (!me || n < 2 * MISMATCH_OFF_TOP) return null;
  const half = n / 2;
  const r1 = v => Math.round(v * 10) / 10;
  const what = `${{r.position}} ${{r.stat_label}}`;
  const tag = t => `${{t}} #${{ranks[t] || '-'}}`;
  // Judged on the team's raw numbers vs what that offense USUALLY gets in
  // its other games -- not scaled to his share and not vs the line (fixed
  // 2026-10-16: Swift Rush Att showed BAL's 28 attempts as 14 "Swift-sized"
  // ones, under the line, so ATL got credit for holding BAL -- but BAL
  // usually gets 24; ATL didn't stop them at all). A defense "held" an
  // offense if it allowed at most its usual; it "gave it up" if at least.
  const sh = cons.share || 0;
  const raw = g => sh ? g.val / sh : g.val;
  const usualRaw = g => (g.usual === null || !sh) ? null : g.usual / sh;
  const heldIt = g => usualRaw(g) === null ? g.hit === (cons.side === 'under') : raw(g) <= usualRaw(g);
  const desc = g => `${{tag(g.vs)}} ${{r1(raw(g))}}` + (usualRaw(g) === null ? '' : ` (usually ${{r1(usualRaw(g))}})`);
  const say = (word, gs) => {{
    const held = gs.filter(heldIt), let_ = gs.filter(g => !heldIt(g));
    return `vs ${{word}} offenses ` + [held.length ? `held ${{held.map(desc).join(', ')}}` : '', let_.length ? `allowed ${{let_.map(desc).join(', ')}}` : ''].filter(Boolean).join('; ');
  }};
  const split = (topWord, bottomWord) => `${{r.opponent}} ` + [top.length ? say(topWord, top) : '', bottom.length ? say(bottomWord, bottom) : ''].filter(Boolean).join(' | ') + ` (team ${{r.stat_label}}).`;
  const top = cons.dg.filter(g => ranks[g.vs] && ranks[g.vs] <= half);
  const bottom = cons.dg.filter(g => !(ranks[g.vs] && ranks[g.vs] <= half));
  if (cons.side === 'under' && me <= MISMATCH_OFF_TOP) {{
    if (top.length && top.every(heldIt)) return null;
    return `Matchup: ${{r.team}} is the #${{me}} ${{what}} offense. ` + (top.length
      ? split('top-half', 'weaker')
      : `${{r.opponent}} hasn't faced a top-half ${{what}} offense in these weeks (${{cons.dg.map(g => tag(g.vs)).join(', ')}}), so its record doesn't say much about this one.`);
  }}
  if (cons.side === 'over' && me > n - MISMATCH_OFF_TOP) {{
    if (bottom.length && bottom.every(g => !heldIt(g) || raw(g) === usualRaw(g))) return null;
    return `Matchup: ${{r.team}} is only the #${{me}} ${{what}} offense. ` + (bottom.length
      ? split('stronger', 'bottom-half')
      : `${{r.opponent}} hasn't faced a bottom-half ${{what}} offense in these weeks (${{cons.dg.map(g => tag(g.vs)).join(', ')}}), so its record doesn't say much about this one.`);
  }}
  return null;
}}

function consistencyStats(r, weeks, sharePct, ranks) {{
  const key = r.position + '|' + r.stat_col;
  const idx = playerSelectedIndices(r, weeks);
  const games = idx.map(i => ({{ val: r.game_log[i], opp: r.game_opponents[i], week: r.game_weeks[i] }}));
  const dlog = (DEFENSE_LOGS[key] || {{}})[r.opponent];
  const dmeta = (DEFENSE_GAMES[r.opponent] && DEFENSE_GAMES[r.opponent][r.position]) || [];
  const didx = dlog ? defenseSelectedIndices(dmeta, weeks) : [];
  const share = (sharePct === null || sharePct === undefined) ? null : sharePct / 100;
  const dgames = share === null ? [] : didx.map(i => {{
    const vs = dmeta[i] && dmeta[i].vs;
    const usual = vs ? offenseUsual(key, r.position, weeks, vs, r.opponent, dmeta[i].week) : null;
    return {{ val: dlog[i] * share, vs, week: dmeta[i] && dmeta[i].week, usual: usual === null ? null : usual * share }};
  }});
  const rk = ranks || {{}};
  const nTeams = Object.keys(rk).length;
  const sides = {{}};
  for (const side of ['over', 'under']) {{
    const m = bestMarketFor(r, side);
    const line = m ? m.line : r.vegas_line;
    if (line === null || line === undefined) continue;
    const ok = v => side === 'over' ? v > line : v < line;
    const pg = games.map(g => {{
      const hit = ok(g.val);
      const orank = rk[g.opp];
      const excused = !hit && orank !== undefined && nTeams > 0 &&
        (side === 'over' ? orank <= EXCUSE_TOUGH_TOP : orank > nTeams - EXCUSE_TOUGH_TOP);
      return Object.assign({{}}, g, {{ hit, excused, orank }});
    }});
    const dg = dgames.map(g => {{
      const hit = ok(g.val);
      const excused = !hit && g.usual !== null && (side === 'over' ? g.usual < line * EXCUSE_OFF_RATIO : g.usual > line / EXCUSE_OFF_RATIO);
      return Object.assign({{}}, g, {{ hit, excused }});
    }});
    const pHits = pg.filter(g => g.hit).length, pEx = pg.filter(g => g.excused).length;
    const dHits = dg.filter(g => g.hit).length, dEx = dg.filter(g => g.excused).length;
    const adj = (h, n, ex) => (n - ex >= consMinGames(weeks)) ? h / (n - ex) : (n ? h / n : null);
    sides[side] = {{
      side, line, market: m, share, pg, dg,
      pHits, pGames: pg.length, pExcused: pEx, pRate: adj(pHits, pg.length, pEx), pRawRate: pg.length ? pHits / pg.length : null,
      dHits, dGames: dg.length, dExcused: dEx, dRate: adj(dHits, dg.length, dEx), dRawRate: dg.length ? dHits / dg.length : null,
      worst: pg.length ? (side === 'over' ? Math.min(...pg.map(g => g.val)) - line : line - Math.max(...pg.map(g => g.val))) : null,
      vals: pg.map(g => g.val), dvals: dg.map(g => g.val),
    }};
  }}
  const o = sides.over, u = sides.under;
  if (!o && !u) return null;
  const score = s => s ? Math.min(s.pRate === null ? 0 : s.pRate, s.dRate === null ? 0 : s.dRate) * 10 + (s.pRate === null ? 0 : s.pRate) : -1;
  return score(o) >= score(u) ? o : u;
}}
function fmtHit(h, g) {{ return g ? `${{h}}/${{g}}` : '-'; }}
function hitCellHtml(r, which) {{
  const c = r.cons;
  if (!c) return '<span class="muted">-</span>';
  const isP = which === 'p';
  const h = isP ? c.pHits : c.dHits, g = isP ? c.pGames : c.dGames, ex = isP ? c.pExcused : c.dExcused, rate = isP ? c.pRate : c.dRate;
  if (!g) return '<span class="muted">-</span>';
  const cls = rate >= CONS_TIERS[1] ? 'edge-pos' : (rate < 0.5 ? 'edge-neg' : '');
  const sideL = c.side === 'over' ? 'O' : 'U';
  const r1 = v => Math.round(v * 10) / 10;
  let lines;
  if (isP) {{
    lines = [`${{r.player}}: ${{c.side}} ${{c.line}} in ${{h}} of ${{g}} games` + (c.worst !== null ? ` (worst game ${{c.worst >= 0 ? '+' : ''}}${{r1(c.worst)}} vs the line)` : '')];
    for (const x of c.pg) lines.push(`${{x.hit ? '✔' : (x.excused ? '~' : '✘')}} Wk${{x.week}} vs ${{x.opp}}: ${{r1(x.val)}}` + (x.orank !== undefined ? ` (${{x.opp}} #${{x.orank}} vs ${{r.position}} ${{r.stat_label}})` : '') + (x.excused ? ` -- excused, one of the ${{EXCUSE_TOUGH_TOP}} ${{c.side === 'over' ? 'toughest' : 'softest'}} matchups` : ''));
  }} else {{
    lines = [`${{r.opponent}}'s games, scaled to his ${{Math.round((c.share || 0) * 100)}}% share: ${{h}} of ${{g}} ${{c.side}} ${{c.line}}`];
    for (const x of c.dg) lines.push(`${{x.hit ? '✔' : (x.excused ? '~' : '✘')}} Wk${{x.week}} vs ${{x.vs}}: ${{r1(x.val)}}` + (x.usual !== null ? ` (${{x.vs}} usually gets ${{r1(x.usual)}})` : '') + (x.excused ? (c.side === 'over' ? ' -- excused, that offense rarely does this' : ' -- excused, that offense always piles this up') : ''));
  }}
  if (ex) lines.push(`Adjusted ${{fmtHit(h, g - ex)}} after excusing ${{ex}} miss${{ex > 1 ? 'es' : ''}} (~). Hits are never removed.`);
  // Every game excused = nothing left to judge (2026-10-16: "O 0/4 (-)" on
  // Bowers vs BUF read like BUF shuts TEs down; really no offense BUF faced
  // gets near his number, so there was no fair test).
  const noTest = ex && g - ex === 0;
  if (noTest) lines.push(isP ? 'Every miss came against a matchup that explains it -- no fair test of him at this line.' : `None of the offenses ${{r.opponent}} faced usually get near this number at his share -- no fair test of this defense at this line.`);
  return `<span class="${{cls}}" title="${{escapeHtml(lines.join('\\n'))}}">${{sideL}} ${{fmtHit(h, g)}}${{ex ? ` <span class="muted">(${{noTest ? 'no fair test' : fmtHit(h, g - ex)}})</span>` : ''}}</span>`;
}}

function enrichRow(r, weeks, defCache) {{
  const key = r.position + '|' + r.stat_col;
  if (!defCache[key]) defCache[key] = rankDefenses(key, weeks);
  const {{ avgs, ranks }} = defCache[key];
  const defAvg = avgs[r.opponent];
  const defAvgRounded = (defAvg === undefined || defAvg === null) ? null : Math.round(defAvg * 100) / 100;
  const derived = deriveStats(r, weeks);
  // Anticipated = this player's typical share of their team's production
  // x what the upcoming opponent allows to this position/stat.
  const anticipated = (derived.share !== null && defAvgRounded !== null)
    ? Math.round((derived.share / 100) * defAvgRounded * 100) / 100
    : null;
  // Anc. Edge = Anticipated vs. the line -- same idea as Edge, but built
  // off the matchup projection instead of recent form. Added 2026-09-24:
  // graded against the SAME shopped line as Edge (derived.best_line) --
  // Edge and Anc. Edge are two different ways of sizing up one candidate
  // bet, so they should both be measured against the actual number you'd
  // get at the book, not a blended consensus. Falls back to the flat
  // consensus line when Edge itself had no side to shop for (a dead-even
  // tie against consensus, or no odds at all).
  const lineForAnc = (derived.best_line !== null && derived.best_line !== undefined) ? derived.best_line : r.vegas_line;
  let ancEdge = null, ancEdgePct = null;
  if (anticipated !== null && lineForAnc !== null && lineForAnc !== undefined) {{
    ancEdge = Math.round((anticipated - lineForAnc) * 10) / 10;
    ancEdgePct = lineForAnc ? ancEdge / lineForAnc : null;
  }}
  // Hot/Cold tier: recent form AND the matchup projection both have to
  // agree on direction (same rule as before), but now the NUMBER of
  // 🔥/🧊 reflects how big that agreed-upon edge is, using whichever of
  // the two signals is weaker as the limiting factor -- so 3 flames means
  // "both Edge and Anc. Edge clear the top bar", not just one of them.
  // Level 4 (⭐ MUST BET) is checked separately against the FIXED
  // MUST_BET_EDGE_PCT bar (not part of EDGE_TIERS), so it never moves
  // when the "How picky" slider does -- see the comment above
  // MUST_BET_EDGE_PCT's declaration.
  let hotLevel = 0, coldLevel = 0;
  const mbRank = ranks[r.opponent] === undefined ? null : ranks[r.opponent];
  const mbMax = Object.keys(ranks).length;
  // Consistency vs. the line (sample standard deviation / line).
  const tierVals = playerSelectedIndices(r, weeks).map(i => r.game_log[i]);
  const tierLine = (derived.best_line !== null && derived.best_line !== undefined) ? derived.best_line : r.vegas_line;
  let tierSd = null, tierRelSd = null;
  if (tierVals.length >= 2 && tierLine) {{
    const m = tierVals.reduce((a, b) => a + b, 0) / tierVals.length;
    tierSd = Math.sqrt(tierVals.reduce((a, b) => a + (b - m) * (b - m), 0) / (tierVals.length - 1));
    tierRelSd = tierSd / Math.abs(tierLine);
  }}
  const tierConsistent = tierRelSd !== null && tierRelSd <= MAX_TIER3_REL_SD;
  let tierCapReason = null;
  const cons = consistencyStats(r, weeks, derived.share, ranks);
  let consReview = false, consReviewReason = null;
  let mismatchFlag = false;
  if (SIGNAL_MODE === 'consistency' && cons && cons.pGames >= consMinGames(weeks) && cons.dGames >= consMinGames(weeks)) {{
    const p = cons.pRate, d = cons.dRate, perfect = p === 1;
    let lvl = 0;
    if (!perfect && p >= CONS_TIERS[1] && d >= CONS_TIERS[1]) lvl = 1;
    if (perfect && d >= CONS_TIERS[0]) lvl = 2;
    if (perfect && d >= CONS_TIERS[1]) lvl = 3;
    if (perfect && d === 1 && cons.pHits === cons.pGames && cons.pGames >= consMustMinGames(weeks) && cons.dGames - cons.dExcused >= consMustMinGames(weeks)) lvl = 4;
    if (lvl >= 3) {{
      const mOk = mbRank !== null && (cons.side === 'over' ? mbRank > mbMax - MUST_BET_MATCHUP_TOP : mbRank <= MUST_BET_MATCHUP_TOP);
      if (!mOk) {{
        tierCapReason = `matchup: ${{r.opponent}} is #${{mbRank === null ? '-' : mbRank}} of ${{mbMax}}, not one of the 10 allowing the ${{cons.side === 'over' ? 'most' : 'least'}}`;
        lvl = 2;
      }}
    }}
    const mismatch = lvl > 0 ? matchupMismatch(r, cons, weeks) : null;
    if (mismatch) mismatchFlag = true;
    if (mismatch) lvl = 0;
    if (cons.side === 'over') hotLevel = lvl; else coldLevel = lvl;
    if (lvl === 0 && perfect) {{
      consReview = true;
      consReviewReason = `He cleared the ${{cons.side}} ${{cons.line}} every game (${{fmtHit(cons.pHits, cons.pGames)}}), but ${{r.opponent}} only allowed it in ${{fmtHit(cons.dHits, cons.dGames)}} of its games.`;
    }}
    if (mismatch) {{
      consReview = true;
      consReviewReason = mismatch + ` Would have been ${{cons.side}} ${{cons.line}} (he's ${{fmtHit(cons.pHits, cons.pGames)}}, ${{r.opponent}} ${{fmtHit(cons.dHits, cons.dGames)}}), so it's a ❓ instead of a pick.`;
    }}
  }}
  if (SIGNAL_MODE !== 'consistency' && derived.edge_pct !== null && ancEdgePct !== null) {{
    if (derived.edge_pct >= SIGNIFICANT_EDGE_PCT && ancEdgePct >= SIGNIFICANT_EDGE_PCT) {{
      const weaker = Math.min(derived.edge_pct, ancEdgePct);
      for (const tier of EDGE_TIERS) {{ if (weaker >= tier) hotLevel++; }}
      // MUST BET consistency gate (added 2026-09-24), Trevor's own bar:
      // "I don't want it to be a must bet if that player has ever gone
      // beneath the line within the weeks I'm filtered to." A big average
      // edge can still hide a game where the player fell short -- e.g. one
      // monster outlier week can drag recentAvg (and therefore edge_pct)
      // way up even though most other games in the window landed under
      // the number. So on top of the existing FIXED % bar, level 4
      // additionally requires a perfect record: zero games below bestLine
      // anywhere in the selected weeks. Falling short of that doesn't lose
      // the pick entirely -- it just keeps whatever 1-3 star tier the loop
      // above already earned, same as failing the price gate below.
      if (weaker >= MUST_BET_EDGE_PCT && derived.below_count === 0 && mbRank !== null && mbRank > mbMax - MUST_BET_MATCHUP_TOP) hotLevel = 4;
      if (hotLevel >= 3) {{
        const mOk = mbRank !== null && mbRank > mbMax - MUST_BET_MATCHUP_TOP;
        if (!mOk || !tierConsistent) {{
          tierCapReason = [!mOk ? `matchup: ${{r.opponent}} is #${{mbRank === null ? '-' : mbRank}} of ${{mbMax}}, not one of the 10 allowing the most` : null,
            !tierConsistent ? (tierRelSd === null ? 'only 1 game -- can\\'t measure consistency' : `inconsistent: games swing ${{Math.round(tierRelSd * 100)}}% of the line (max ${{Math.round(MAX_TIER3_REL_SD * 100)}}%)`) : null].filter(Boolean).join('; ');
          hotLevel = 2;
        }}
      }}
    }} else if (derived.edge_pct <= -SIGNIFICANT_EDGE_PCT && ancEdgePct <= -SIGNIFICANT_EDGE_PCT) {{
      const weaker = Math.min(Math.abs(derived.edge_pct), Math.abs(ancEdgePct));
      for (const tier of EDGE_TIERS) {{ if (weaker >= tier) coldLevel++; }}
      // Mirrored for the Under side: blocked if the player has EVER gone
      // over the line in the selected weeks, same reasoning as above.
      if (weaker >= MUST_BET_EDGE_PCT && derived.above_count === 0 && mbRank !== null && mbRank <= MUST_BET_MATCHUP_TOP) coldLevel = 4;
      if (coldLevel >= 3) {{
        const mOk = mbRank !== null && mbRank <= MUST_BET_MATCHUP_TOP;
        if (!mOk || !tierConsistent) {{
          tierCapReason = [!mOk ? `matchup: ${{r.opponent}} is #${{mbRank === null ? '-' : mbRank}} of ${{mbMax}}, not one of the 10 allowing the least` : null,
            !tierConsistent ? (tierRelSd === null ? 'only 1 game -- can\\'t measure consistency' : `inconsistent: games swing ${{Math.round(tierRelSd * 100)}}% of the line (max ${{Math.round(MAX_TIER3_REL_SD * 100)}}%)`) : null].filter(Boolean).join('; ');
          coldLevel = 2;
        }}
      }}
    }}
  }}
  // Remember whether the two signals confidently agreed BEFORE the price
  // gate below can zero it out -- needsReview (just below) needs to know
  // whether they truly agreed, not just whether a bad price hid it, so a
  // price-suppressed row shows the "price" tag, not a redundant ❓.
  const preGateHot = hotLevel > 0;
  const preGateCold = coldLevel > 0;

  // Price gate: the stat math can agree all it wants, but if the side
  // you'd actually be betting is priced too steep (see MAX_JUICE_PRICE),
  // it's not a good bet, so the flame/ice is suppressed rather than shown
  // anyway. 🔥 bets the Over, so it checks the Over price; 🧊 bets the
  // Under, so it checks the Under price. Added 2026-09-24: checks the
  // price at derived.best_book -- the specific book whose line is being
  // highlighted -- rather than the blended consensus price, since that's
  // the actual number you'd get if you bet it there. Falls back to the
  // consensus price when no single book was pinned (no side to shop for,
  // or no per-book price data at all). A missing price (no odds fetched
  // for that side yet) doesn't suppress anything -- there's just nothing
  // to check it against yet, same as everywhere else in this dashboard
  // that treats "no data" as neutral rather than bad.
  //
  // Bug fixed 2026-09-24 (found while fixing the line-shopping tie-break
  // above): this used to read a single price per book regardless of
  // side, which meant an Under bet at a pinned book was actually having
  // its OVER price checked against MAX_JUICE_PRICE -- the wrong number.
  // Now that book_line() keeps both sides' prices, this reads the price
  // for the side actually being gated (Over price for the hot/Over
  // check, Under price for the cold/Under check), which is also, not
  // coincidentally, the side derived.direction says this row favors.
  const bookOverPrice = (book) => {{
    if (book === 'draftkings') return r.draftkings_over_price;
    if (book === 'fanduel') return r.fanduel_over_price;
    if (book === 'betmgm') return r.betmgm_over_price;
    return null;
  }};
  const bookUnderPrice = (book) => {{
    if (book === 'draftkings') return r.draftkings_under_price;
    if (book === 'fanduel') return r.fanduel_under_price;
    if (book === 'betmgm') return r.betmgm_under_price;
    return null;
  }};
  const overPrice = (SIGNAL_MODE === 'consistency' && cons && cons.side === 'over' && cons.market) ? cons.market.price : (derived.best_book ? bookOverPrice(derived.best_book) : r.over_price);
  const underPrice = (SIGNAL_MODE === 'consistency' && cons && cons.side === 'under' && cons.market) ? cons.market.price : (derived.best_book ? bookUnderPrice(derived.best_book) : r.under_price);
  let suppressedBy = null;
  if (hotLevel > 0 && overPrice !== null && overPrice !== undefined && overPrice < MAX_JUICE_PRICE) {{
    suppressedBy = {{ side: 'Over', price: overPrice }};
    hotLevel = 0;
  }}
  if (coldLevel > 0 && underPrice !== null && underPrice !== undefined && underPrice < MAX_JUICE_PRICE) {{
    suppressedBy = {{ side: 'Under', price: underPrice }};
    coldLevel = 0;
  }}

  // Three groups only (2026-10-16, per Trevor: "must bet, three stars then
  // just question marks ... i want to bet the must bets, review the three
  // stars and then like have everything else"):
  //   ⭐ MUST BET, 🔥🔥🔥/🧊🧊🧊, and ❓ for everything else worth a look.
  // So 1-2 flame/ice rows become ❓ (with what they would have been), and
  // a role change (trade / key teammate out / your flag -- roleChangeReasons)
  // takes a MUST BET or 3-star down to ❓ too ("i don't even want that in 3
  // stars"), instead of holding it at 3.
  const roleChanges = roleChangeReasons(r);
  const roleCapped = false;
  let demoteWhy = null, demotedFrom = 0, blowoutFlag = false, backupBlowout = false;
  {{
    const lvlNow = Math.max(hotLevel, coldLevel);
    const sideNow = hotLevel > coldLevel ? 'over' : 'under';
    const icon = sideNow === 'over' ? '🔥' : '🧊';
    const was = lvlNow === 4 ? 'a MUST BET' : icon.repeat(lvlNow);
    const consLine = (SIGNAL_MODE === 'consistency' && cons) ? ` He cleared ${{cons.side}} ${{cons.line}} in ${{fmtHit(cons.pHits, cons.pGames)}}; ${{r.opponent}} allowed it in ${{fmtHit(cons.dHits, cons.dGames)}}.` : '';
    // Blowout rule (2026-10-16, per Trevor: "10+ point favorite as a line to
    // say that I shouldn't be taking a rb rush over"): a big favorite's lead
    // back often sits late, so his rush yards / rush attempts Overs aren't
    // picks. The backup's Overs are left alone.
    const favBy = tbTeamSpread(r, tbGame(r));
    if (lvlNow >= 1 && r.rb_lead && (r.stat_col === 'rushing_yards' || r.stat_col === 'carries') && sideNow === 'over' && favBy !== null && favBy >= BLOWOUT_FAV) {{
      blowoutFlag = true;
      demoteWhy = `Blowout risk -- ${{r.team}} is favored by ${{favBy}}; lead backs often sit late in blowouts, so no rush Over (would have been ${{was}}).` + consLine;
    }} else if (r.position === 'RB' && !r.rb_lead && (r.stat_col === 'rushing_yards' || r.stat_col === 'carries') && favBy !== null && favBy >= BLOWOUT_FAV && cons && !(lvlNow >= 3 && sideNow === 'over')) {{
      // Backup in a likely blowout (2026-10-16, per Trevor, on Kaelon Black):
      // no rush Unders (he gets the late carries), and his rush Over is a 💡.
      backupBlowout = true;
      demoteWhy = `Blowout upside -- ${{r.team}} is favored by ${{favBy}}, so the backup tends to get the late carries` + (lvlNow >= 1 && sideNow === 'under' ? `; no Under (would have been ${{was}} under)` : '') + '.' + blowoutGamesText(r);
    }} else if (lvlNow >= 1 && roleChanges.length) {{
      demoteWhy = `Role change -- would have been ${{was}} (${{sideNow}}): ${{roleChanges.join('; ')}}.` + consLine;
    }} else if (lvlNow === 1 || lvlNow === 2) {{
      demoteWhy = `Would have been ${{was}} (${{sideNow}}) -- below the 3-star bar.` + consLine + (tierCapReason ? ` Held under 3 by ${{tierCapReason}}.` : '');
    }}
    if (demoteWhy) {{ demotedFrom = backupBlowout ? 0 : lvlNow; hotLevel = 0; coldLevel = 0; }}
  }}

  const hot = hotLevel > 0;
  const cold = coldLevel > 0;
  // Numeric so the column is sortable: +1/+2/+3 hot, -1/-2/-3 cold, 0 neither.
  const signal = hot ? hotLevel : (cold ? -coldLevel : 0);

  // ❓ "worth a review" -- Trevor's example: a QB who's good at rushing
  // but hasn't rushed much lately, facing a defense that gives up a lot
  // of QB rushing yards. Recent Avg alone wouldn't show an edge (so Edge
  // stays quiet), but Anc. Edge (built off the matchup, not recent form)
  // would -- and that's worth knowing even though the two signals didn't
  // confidently agree with each other the way 🔥/🧊 requires.
  //
  // Refined 2026-09-22, per Trevor: only flag it when one signal is
  // significant AND the other isn't actively contradicting it -- e.g.
  // Anc. Edge is strongly positive and Edge is merely "above zero" (weak
  // but same side), or Anc. Edge is strongly negative and Edge is at/near
  // zero on that same side. If the two flatly disagree in sign (one
  // clearly positive, one clearly negative), that's not a "worth a look"
  // case anymore -- it's just noise, so no ❓. Concretely: exactly one of
  // Edge/Anc. Edge must be significant (both significant is already
  // 🔥/🧊 territory when they agree, and is now explicitly excluded when
  // they don't), and if the other one has a value at all, its sign must
  // not oppose the significant one's. A missing value (no data yet, e.g.
  // no matchup projection) doesn't count as opposing -- there's simply
  // nothing there to contradict it, so it still flags. This keeps ❓
  // mutually exclusive with 🔥/🧊 and independent of the price gate
  // (still worth a look regardless of price -- reviewing isn't the same
  // as recommending a bet).
  const edgeSig = derived.edge_pct !== null && Math.abs(derived.edge_pct) >= SIGNIFICANT_EDGE_PCT;
  const ancSig = ancEdgePct !== null && Math.abs(ancEdgePct) >= SIGNIFICANT_EDGE_PCT;
  const signOf = (v) => (v > 0 ? 1 : (v < 0 ? -1 : 0));
  const edgeSign = derived.edge_pct === null ? 0 : signOf(derived.edge_pct);
  const ancSign = ancEdgePct === null ? 0 : signOf(ancEdgePct);
  const opposedSigns = edgeSign !== 0 && ancSign !== 0 && edgeSign !== ancSign;
  const needsReview = !!demoteWhy || (SIGNAL_MODE === 'consistency' ? (consReview && !(preGateHot || preGateCold)) : ((edgeSig !== ancSig) && !(preGateHot || preGateCold) && !opposedSigns));
  let reviewReason = null;
  if (needsReview) {{
    const fmtPct = (v) => (v >= 0 ? '+' : '') + Math.round(v * 100) + '%';
    if (edgeSig) {{
      reviewReason = `Edge is significant (${{fmtPct(derived.edge_pct)}}) but Anc. Edge isn't confirming it` +
        (ancEdgePct === null ? ' (no matchup projection available).' : ` (${{fmtPct(ancEdgePct)}}, though not on the other side of zero).`);
    }} else {{
      reviewReason = `Anc. Edge is significant (${{fmtPct(ancEdgePct)}}) but Edge isn't confirming it` +
        (derived.edge_pct === null ? ' (recent form has no line to compare yet).' : ` (${{fmtPct(derived.edge_pct)}}, though not on the other side of zero).`);
    }}
  }}

  // Default table ordering, per Trevor: biggest signal first regardless
  // of over/under direction -- MUST BET rows (level 4, added 2026-09-24)
  // together at the very top, then 3-flame and 3-ice rows, then
  // 2-flame/2-ice together, then 1-flame/1-ice together, then ❓ rows,
  // then everything else. This groups by MAGNITUDE (using whichever of
  // hot/cold/review applies), unlike the plain numeric `signal` field
  // above, which is signed and would sort all the hot rows above all the
  // cold rows instead of pairing them by tier. A price-suppressed row
  // (see suppressedBy above) ranks just below ❓ and above a plain row --
  // there was a real stat edge, just not one worth betting at that
  // price, so it's still slightly more interesting than a row with
  // nothing going on. Ties within a tier (e.g. two different MUST BET
  // rows) keep whatever order they were in before sorting.
  let signalRank = 0;
  if (hotLevel === 4 || coldLevel === 4) signalRank = 7;
  else if (hotLevel === 3 || coldLevel === 3) signalRank = 6;
  else if (hotLevel === 2 || coldLevel === 2) signalRank = 5;
  else if (hotLevel === 1 || coldLevel === 1) signalRank = 4;
  else if (needsReview) signalRank = 3; // 💡 rows go to 5 in the returned signal_rank
  else if (suppressedBy) signalRank = 2;

  // Second-look checklist on the side the signal points to (see tiebreak()).
  let tbLean = null, tbFromAnc = false;
  if (hotLevel > 0) tbLean = 'over';
  else if (coldLevel > 0) tbLean = 'under';
  else if (needsReview && SIGNAL_MODE === 'consistency' && cons) {{
    tbLean = cons.side;
  }}
  else if (needsReview) {{
    const v = edgeSig ? derived.edge_pct : ancEdgePct;
    tbFromAnc = !edgeSig;
    tbLean = v > 0 ? 'over' : 'under';
  }}
  const tbDefRank = ranks[r.opponent] === undefined ? null : ranks[r.opponent];
  const tb = tbLean ? tiebreak(r, derived, tbLean, tbDefRank, Object.keys(ranks).length, tbFromAnc, weeks) : null;

  // 💡 (added 2026-10-16, per Trevor: "put high end question marks and
  // question marks with positive game scripts as a separate status"): a ❓
  // that would have been a 2-star, or whose game script supports its side.
  // Not for ❓s caused by a role change or a matchup mismatch -- those are
  // the "don't trust it" ones.
  let ideaReason = null;
  const outlierDef = outlierDefense(r);
  // 🎯 + the line looks low (2026-10-30, per Trevor: "outliers should give
  // more of a bump when lines seem low"; he chose 💡 first, 3-star later
  // only if it wins): Anticipated 20%+ past the line on the 🎯 side. Also
  // lifts a row with no signal at all to 💡.
  let outlierValue = null;
  if (outlierDef && anticipated !== null && lineForAnc) {{
    const ok = outlierDef.side === 'over' ? anticipated >= lineForAnc * OUTLIER_VALUE_RATIO : anticipated <= lineForAnc / OUTLIER_VALUE_RATIO;
    if (ok) outlierValue = `🎯 line looks low for this matchup: projects ${{anticipated}} vs ${{lineForAnc}} (${{outlierDef.text}})`.replace('looks low', outlierDef.side === 'over' ? 'looks low' : 'looks high');
  }}
  if (backupBlowout) {{
    ideaReason = `blowout upside on the Over: ${{r.team}} favored by ${{tbTeamSpread(r, tbGame(r))}} -- an upside bet, not a consistency pick`;
  }} else if (needsReview && !roleChanges.length && !mismatchFlag && !blowoutFlag) {{
    const why = [];
    if (demotedFrom === 2) why.push('high end: would have been a 2-star');
    if (tb && tb.script && tb.script.effect > 0) why.push(`game script supports the ${{tb.lean === 'over' ? 'Over' : 'Under'}} (${{tb.script.text}})`);
    if (outlierValue) why.push(outlierValue);
    else if (outlierDef && tb && tb.lean === outlierDef.side) why.push(`🎯 outlier defense: ${{outlierDef.text}}`);
    if (why.length) ideaReason = why.join('; ');
  }} else if (outlierValue && !needsReview && !demoteWhy && hotLevel === 0 && coldLevel === 0 && !roleChanges.length && !mismatchFlag && !blowoutFlag) {{
    ideaReason = outlierValue;
  }}

  return Object.assign({{}}, r, derived, {{
    def_avg_allowed: defAvgRounded,
    def_rank: ranks[r.opponent] === undefined ? null : ranks[r.opponent],
    def_rank_max: Object.keys(ranks).length,
    anticipated: anticipated,
    anc_edge: ancEdge,
    anc_edge_pct: ancEdgePct,
    hot: hot,
    cold: cold,
    needs_review: needsReview,
    idea_reason: ideaReason,
    outlier_def: outlierDef,
    outlier_value: outlierValue,
    alt_line: altLineInfo(r, weeks, anticipated, lineForAnc),
    review_reason: demoteWhy || ((SIGNAL_MODE === 'consistency' && needsReview) ? consReviewReason : reviewReason),
    hot_level: hotLevel,
    cold_level: coldLevel,
    signal: signal,
    signal_rank: ideaReason ? 5 : signalRank, // 💡 sorts between 3-star (6) and ❓ (3)
    tier_sd: tierSd,
    tier_rel_sd: tierRelSd,
    tier_cap_reason: tierCapReason,
    cons: cons,
    hit_pct: cons && cons.pGames ? cons.pRate : null,
    def_hit_pct: cons && cons.dGames ? cons.dRate : null,
    tiebreak: tb,
    suppressed_by: suppressedBy,
    role_changes: roleChanges,
    role_soft: roleSoftReasons(r),
    role_capped: roleCapped,
  }});
}}

function escapeHtml(s) {{
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}}

// Renders the <select> for a row's personal bet mark (see MARKS above).
// Always rendered in full even when a row's Player/Team/Opp cells are
// blanked out by the "grouped by player" visual (sameAsPrev in render()
// below) -- each stat row is still its own separate bettable line, so
// each one keeps its own independent marker rather than inheriting or
// hiding behind the row above it.
function markSelect(r) {{
  const key = markKey(r);
  const current = MARKS[key] || '';
  const opts = MARK_OPTIONS.map(o =>
    `<option value="${{o.value}}" ${{o.value === current ? 'selected' : ''}}>${{o.label}}</option>`
  ).join('');
  return `<select class="mark-select" data-mark-key="${{escapeHtml(key)}}">${{opts}}</select>`;
}}

function render() {{
  document.getElementById('th-recent-avg').textContent = 'Avg (' + weeksLabel(selectedWeeks) + ')';
  // The How-picky slider only drives the Average-edge formula.
  if (SIGNAL_MODE === 'consistency') {{
    document.getElementById('pickyLabel').textContent = '⭐ MUST BET = bet it: every game on both sides (4+ games), top-10 matchup  ·  🔥🔥🔥/🧊🧊🧊 = review: he cleared it every game, defense 75%+, top-10 matchup  ·  💡 = high-end ❓ (would have been 2-star) or the game script backs it  ·  ❓ = everything else worth a look (weaker hit rates, role changes, matchup questions -- hover for why)' + signalSampleNote();
  }} else {{
    applyPickySetting();
  }}
  updateMyBetsButton();

  const q = document.getElementById('search').value.toLowerCase();
  const defCache = {{}}; // one lookup per (position, stat) pair per render, not per row
  let rows = ROWS
    .map(r => {{
      const e = enrichRow(r, selectedWeeks, defCache);
      // Mark column sort (added 2026-09-29): ✅ bets on top, then 🌕, unmarked, ❌.
      e.mark_rank = {{ bet: 3, watch: 2, pass: 0 }}[MARKS[markKey(r)]] ?? 1;
      return e;
    }})
    .filter(r =>
      (activePos === 'ALL' || r.position === activePos) &&
      (activeStat === 'ALL' || r.stat_label === activeStat) &&
      (activeGame === 'ALL' || gameKey(r) === activeGame) &&
      (!hideMarkedX || MARKS[markKey(r)] !== 'pass') &&
      (!hideReview || !r.needs_review || r.idea_reason || altOnly) && // Hide ❓ keeps 💡 (and alt-line rows when that filter is on)
      (!altOnly || r.alt_line) &&
      (!ladderOnly || ladderInfo(r) !== null) &&
      (!weakMatchupOnly || isWeakMatchup(r)) &&
      (!strongMatchupOnly || isStrongMatchup(r)) &&
      (!q || r.player.toLowerCase().includes(q) || r.team.toLowerCase().includes(q) || r.opponent.toLowerCase().includes(q))
    );
  rows.sort((a, b) => {{
    let av = a[sortKey], bv = b[sortKey];
    if (av === null || av === undefined) av = -Infinity;
    if (bv === null || bv === undefined) bv = -Infinity;
    if (typeof av === 'string') return sortDir * av.localeCompare(bv);
    return sortDir * (av - bv);
  }});

  const tbody = document.getElementById('tbody');
  const groupingActive = (sortKey === 'player');
  let html = '';
  for (let i = 0; i < rows.length; i++) {{
    const r = rows[i];
    const prev = rows[i - 1];
    const next = rows[i + 1];
    const sameAsPrev = groupingActive && prev && prev.player === r.player;
    const isLastOfGroup = !(groupingActive && next && next.player === r.player);
    // Impact badges are per STAT, so they still show on the collapsed
    // (↳) rows in the grouped-by-player view -- an RB's rushing row and
    // receiving row can have different impacts.
    const idCell = sameAsPrev
      ? '<span class="muted">&rdsh;</span>' + impactTags(r) + outlierTag(r) + altLineTag(r)
      : r.player + injuryTag(r) + impactTags(r) + ladderTag(r) + outlierTag(r) + altLineTag(r);
    const idClass = sameAsPrev ? 'grouped-cell' : '';
    html += `
    <tr class="${{groupingActive && isLastOfGroup ? 'group-end' : ''}}" data-player="${{escapeHtml(r.player)}}">
      <td>${{markSelect(r)}}${{betSlip(r)}}</td>
      <td class="${{idClass}} player-cell">${{idCell}}</td>
      <td class="${{idClass}}">${{sameAsPrev ? '' : r.position}}</td>
      <td class="${{idClass}}">${{sameAsPrev ? '' : r.team}}</td>
      <td class="${{idClass}} opp-cell" data-opponent="${{r.opponent}}" data-opp-pos="${{r.position}}">${{sameAsPrev ? '' : (r.at_opponent ? '@' : '') + r.opponent + coverageTag(r.opponent)}}${{gsLinkHtml(r)}}</td>
      <td class="stat-cell">${{r.stat_label}}</td>
      <td>${{fmt(r.recent_avg)}}</td>
      <td>${{fmt(r.def_avg_allowed)}}</td>
      <td ${{rankStyle(r.def_rank, r.def_rank_max)}}>${{fmt(r.def_rank)}}</td>
      <td>${{hitCellHtml(r, 'p')}}</td>
      <td>${{hitCellHtml(r, 'd')}}</td>
      <td>${{fmt(r.share, '%')}}</td>
      <td>${{fmt(r.anticipated)}}</td>
      <td class="${{edgeClass(r.edge_pct)}}">${{fmt(r.edge)}}</td>
      <td class="${{edgeClass(r.anc_edge_pct)}}">${{fmt(r.anc_edge)}}</td>
      <td>${{signalEmoji(r)}}${{scriptTag(r)}}</td>
      <td class="${{r.best_book === 'draftkings' ? 'best-line' : ''}}" title="${{r.best_book === 'draftkings' ? 'Most advantageous line for this bet' : ''}}">${{fmtLine(r.draftkings_line, bookCellPrice(r, 'draftkings'))}}</td>
      <td class="${{r.best_book === 'fanduel' ? 'best-line' : ''}}" title="${{r.best_book === 'fanduel' ? 'Most advantageous line for this bet' : ''}}">${{fmtLine(r.fanduel_line, bookCellPrice(r, 'fanduel'))}}</td>
      <td class="${{r.best_book === 'betmgm' ? 'best-line' : ''}}" title="${{r.best_book === 'betmgm' ? 'Most advantageous line for this bet' : ''}}">${{fmtLine(r.betmgm_line, bookCellPrice(r, 'betmgm'))}}</td>
      <td class="${{weatherClass(r)}}">${{r.weather ? r.weather : '<span class="muted">-</span>'}}</td>
    </tr>`;
  }}
  tbody.innerHTML = html;
  applyColumnLayout();
  renderGameScriptPanel();
}}

// --- Player detail modal: click any player's name to see every stat this
// dashboard tracks for them in one place, regardless of the current
// Position/Stat filters (only the sample-size selector still applies,
// since it uses the same selected-weeks filter as the rest of the page). ---
let currentModalPlayer = null;

// Added 2026-09-29 per Trevor: in the player card's game-by-game table,
// show how each PAST opponent ranks at defending that stat (e.g. Wk3 vs
// LA: "41 #17" for RB Rec Yds), so he can tell whether a big or small
// game came against a tough or soft defense. Uses the same
// rankDefenses() ranking as the Opp Rank column (same position+stat,
// same selected weeks, 1 = allows the least), read from the modal's
// defCache -- enrichRow() has already filled it for every stat on the card.
let _modalDefCache = null;
function oppRankChip(r, opp) {{
  const info = _modalDefCache && _modalDefCache[r.position + '|' + r.stat_col];
  if (!info) return '';
  const rank = info.ranks[opp];
  if (rank === undefined || rank === null) return '';
  const max = Object.keys(info.ranks).length;
  const avg = info.avgs[opp];
  const tip = `${{opp}} allows ${{avg === null || avg === undefined ? '-' : Math.round(avg * 10) / 10}} ${{r.stat_label}} per game to ${{r.position}}s -- #${{rank}} of ${{max}} (1 = toughest)`;
  return ` <span class="opp-rank-chip" ${{rankStyle(rank, max)}} title="${{escapeHtml(tip)}}">#${{rank}}</span>`;
}}

function secondLookHtml(playerRows) {{
  const rowsWith = playerRows.filter(r => r.tiebreak);
  if (!rowsWith.length) return '';
  let html = '';
  for (const r of rowsWith) {{
    const t = r.tiebreak;
    const side = t.lean === 'over' ? 'Over' : 'Under';
    const items = t.factors.map(f => `<li class="${{f.effect > 0 ? 'edge-pos' : f.effect < 0 ? 'edge-neg' : 'muted'}}"><span style="display:inline-block;width:14px;">${{f.effect > 0 ? '&#10004;' : f.effect < 0 ? '&#10008;' : '&bull;'}}</span><strong>${{escapeHtml(f.name)}}</strong> <span class="sl-text">${{escapeHtml(f.text)}}</span></li>`).join('');
    const cautions = t.cautions.length ? `<li class="wind-med"><span style="display:inline-block;width:14px;">&#9888;</span>${{escapeHtml(t.cautions.join('; '))}}</li>` : '';
    html += `<div class="sl-block"><div class="sl-head">${{escapeHtml(r.stat_label)}} &middot; ${{side}} ${{t.line}} ${{signalEmoji(r)}} <span class="muted">${{t.pros}} for / ${{t.cons}} against</span></div><ul class="sl-list">${{items}}${{cautions}}</ul></div>`;
  }}
  return `<h3 class="modal-section-title">Second look (context, not a pick)</h3>
    <div class="modal-note">A checklist on the side each signal points to. In the Week 3 backtest the combined count did <em>not</em> predict results; only game script held up (shown as &#10004;/&#9888; script in the table). Use it to spot red flags -- low volume, thin sample, a spread that works against you.</div>
    <div class="sl-grid">${{html}}</div>`;
}}

function openPlayerModal(playerName) {{
  const defCache = {{}};
  _modalDefCache = defCache;
  const playerRows = ROWS.filter(r => r.player === playerName).map(r => enrichRow(r, selectedWeeks, defCache));
  if (!playerRows.length) return;
  currentModalPlayer = playerName;

  const first = playerRows[0];
  document.getElementById('modalPlayerName').textContent = first.player;
  const oppLabel = (first.at_opponent ? '@' : '') + first.opponent;
  const metaParts = [
    escapeHtml(first.position + ' · ' + first.team + ' vs ' + oppLabel) + ' ' + gsLinkHtml(first, 'Game script'),
    'Weeks: ' + weeksLabel(selectedWeeks),
  ];
  if (first.weather) {{
    metaParts.push(first.weather_bad
      ? '<span class="weather-bad">' + escapeHtml(first.weather) + '</span>'
      : escapeHtml(first.weather));
  }}
  if (first.injury) {{
    const inj = first.injury;
    const injParts = [inj.status];
    if (inj.primary_injury) injParts.push('(' + inj.primary_injury + ')');
    if (inj.practice_status && inj.source !== 'practice') injParts.push('-- ' + inj.practice_status);
    const injClass = (inj.status === 'Out' || inj.status === 'Doubtful') ? 'weather-bad' : 'wind-med';
    const injSrc = inj.source === 'practice' ? '(NFL practice report -- no game designation yet)' : (inj.source === 'espn' ? '(ESPN injury news' + (inj.note ? ': ' + escapeHtml(inj.note) : '') + ')' : '(NFL official injury report)');
    metaParts.push('&#9937;&#65039; <span class="' + injClass + '">' + escapeHtml(injParts.join(' ')) + '</span> ' + injSrc);
  }}
  const roleReasons = first.role_changes || [];
  const flagged = MARKS[roleKey(first)] === 'flux';
  metaParts.push((roleReasons.length ? '<span class="weather-bad" title="' + escapeHtml(roleReasons.join('\\n')) + '">&#9888;&#65039; Role change: ' + escapeHtml(roleReasons.join('; ')) + '</span> ' : '')
    + `<button type="button" class="weeks-mini-btn" id="roleFlagBtn" data-role-key="${{escapeHtml(roleKey(first))}}" title="For news the data can't see (coach comments, depth chart, a teammate returning). Keeps this player out of MUST BET this week, on your board and in your alerts.">${{flagged ? '&#9888;&#65039; Flagged: role change (undo)' : '&#9888;&#65039; Flag role change'}}</button>`);
  document.getElementById('modalMeta').innerHTML = metaParts.join('  &middot;  ');

  // Injury impact section: every impactful injury touching any of this
  // player's stats, listed once each with which of his stats it affects
  // (the per-stat badges in the table above show the same thing row by row).
  const impactMap = new Map();
  for (const r of playerRows) {{
    const imp = r.injury_impacts;
    if (!imp) continue;
    for (const [dir, list] of [['helps', imp.helps], ['hurts', imp.hurts]]) {{
      for (const e of (list || [])) {{
        const key = dir + '|' + e.name + '|' + e.team + '|' + e.reason;
        if (!impactMap.has(key)) impactMap.set(key, {{ dir, e, stats: [] }});
        impactMap.get(key).stats.push(r.stat_label);
      }}
    }}
  }}
  const impactEntries = Array.from(impactMap.values())
    .sort((a, b) => (a.dir === b.dir ? b.e.severity - a.e.severity : (a.dir === 'hurts' ? -1 : 1)));
  let impactHtml = '';
  if (impactEntries.length) {{
    const rowsHtml = impactEntries.map(({{ dir, e, stats }}) => {{
      const badge = dir === 'helps'
        ? '<span class="cov-tag impact-help" style="margin-left:0">&#129657;&#9650; Helps</span>'
        : '<span class="cov-tag impact-hurt" style="margin-left:0">&#129657;&#9660; Hurts</span>';
      const statusCls = e.severity >= 3 ? 'weather-bad' : 'wind-med';
      const snaps = e.snap_pct !== null && e.snap_pct !== undefined ? Math.round(e.snap_pct * 100) + '%' : '-';
      return `<tr>
        <td>${{badge}}</td>
        <td>${{escapeHtml(e.name)}} <span class="muted">${{e.team}} ${{e.position}}</span></td>
        <td class="${{statusCls}}">${{escapeHtml(e.status)}}${{e.injury ? ' (' + escapeHtml(e.injury) + ')' : ''}}</td>
        <td>${{snaps}}</td>
        <td>${{escapeHtml(e.reason)}}</td>
        <td class="muted">${{escapeHtml(stats.join(', '))}}</td>
      </tr>`;
    }}).join('');
    impactHtml = `
    <h3 class="modal-section-title">Injury impact (own team + ${{escapeHtml(first.opponent)}} defense)</h3>
    <div class="modal-table-wrap">
    <table class="modal-table">
      <thead><tr><th></th><th>Injured player</th><th>Status</th><th>Snaps</th><th>Why it matters</th><th>Affects</th></tr></thead>
      <tbody>${{rowsHtml}}</tbody>
    </table>
    </div>`;
  }}

  let summaryHtml = '';
  for (const r of playerRows) {{
    summaryHtml += `
    <tr>
      <td>${{markSelect(r)}}${{betSlip(r)}}</td>
      <td>${{r.stat_label}}${{impactTags(r)}}</td>
      <td>${{fmt(r.recent_avg)}}</td>
      <td>${{fmt(r.def_avg_allowed)}}</td>
      <td ${{rankStyle(r.def_rank, r.def_rank_max)}}>${{fmt(r.def_rank)}}</td>
      <td>${{hitCellHtml(r, 'p')}}</td>
      <td>${{hitCellHtml(r, 'd')}}</td>
      <td>${{fmt(r.share, '%')}}</td>
      <td>${{fmt(r.anticipated)}}</td>
      <td class="${{edgeClass(r.edge_pct)}}">${{fmt(r.edge)}}</td>
      <td class="${{edgeClass(r.anc_edge_pct)}}">${{fmt(r.anc_edge)}}</td>
      <td>${{signalEmoji(r)}}${{scriptTag(r)}}</td>
      <td class="${{r.best_book === 'draftkings' ? 'best-line' : ''}}" title="${{r.best_book === 'draftkings' ? 'Most advantageous line for this bet' : ''}}">${{fmtLine(r.draftkings_line, bookCellPrice(r, 'draftkings'))}}</td>
      <td class="${{r.best_book === 'fanduel' ? 'best-line' : ''}}" title="${{r.best_book === 'fanduel' ? 'Most advantageous line for this bet' : ''}}">${{fmtLine(r.fanduel_line, bookCellPrice(r, 'fanduel'))}}</td>
      <td class="${{r.best_book === 'betmgm' ? 'best-line' : ''}}" title="${{r.best_book === 'betmgm' ? 'Most advantageous line for this bet' : ''}}">${{fmtLine(r.betmgm_line, bookCellPrice(r, 'betmgm'))}}</td>
    </tr>`;
  }}

  // Game-by-game box score: one row per game that falls in the selected
  // weeks, one column per stat this player is tracked for -- i.e. exactly
  // what happened in each of those games, not just a single stat's
  // numbers in isolation.
  const gameIdx = playerSelectedIndices(first, selectedWeeks);

  // Explicit "DNP" rows (added 2026-09-24, after Trevor asked why Michael
  // Pittman's card had no Week 2 row): a week strictly before the
  // current/upcoming week (WEEK) has already been played league-wide, so
  // if THIS player has no game row for it, that's a real signal --
  // inactive, injured, on a bye -- not a data gap, and it used to look
  // exactly like one (the week just silently didn't appear). Confirmed
  // via nflverse's own snap-count data (zero offense snaps that week, not
  // just zero stats) and the official injury report (Questionable, foot,
  // did not practice) that Pittman's Week 2 was a real absence. A week
  // that hasn't been played by ANYONE yet (week === WEEK, or a future
  // week Trevor checked ahead of time) is deliberately NOT flagged as
  // DNP -- there's no data for that week for any player yet, so it isn't
  // this player's absence to call out.
  const playedWeeks = new Set(gameIdx.map(i => first.game_weeks[i]));
  const dnpWeeks = Array.from(selectedWeeks).filter(w => w < WEEK && !playedWeeks.has(w));
  const gameEntries = [
    ...gameIdx.map(i => ({{ week: first.game_weeks[i], idx: i }})),
    ...dnpWeeks.map(w => ({{ week: w, idx: null }})),
  ].sort((a, b) => b.week - a.week); // most-recent-first, matching game_log's own order

  let gameRowsHtml = '';
  // "This week" row on top (added 2026-10-16, per Trevor: "show their current
  // week opponent and averages and stuff similar to how you did that on the
  // defense popups"): what this week's defense allows per game to his
  // position for each stat, its rank (same chip as the games below, 1 =
  // toughest), and the current best line.
  if (first.opponent) {{
    let up = `<td><strong>This week ${{first.at_opponent ? '@' : 'vs '}}${{escapeHtml(first.opponent)}}</strong> <span class="muted" title="Per game, to ALL of their opponents' ${{escapeHtml(first.position)}}s combined -- not just one player.">(they allow to all ${{escapeHtml(first.position)}}s)</span></td>`;
    for (const r of playerRows) {{
      const a = r.def_avg_allowed;
      const line = (r.best_line !== null && r.best_line !== undefined) ? r.best_line : r.vegas_line;
      // His share of his team's production at this position/stat (Team
      // Share column) and the projection: share x what they allow
      // (Anticipated column). Added 2026-10-16 per Trevor.
      const sh = r.share, proj = r.anticipated;
      const shareTip = `${{r.player}} gets ${{sh}}% of ${{r.team}}'s ${{r.position}} ${{r.stat_label}} (selected weeks). Projection = that share x the ${{fmt(a === null || a === undefined ? null : Math.round(a * 10) / 10)}} ${{first.opponent}} allows to ${{r.position}}s per game.`;
      up += `<td>${{fmt(a === null || a === undefined ? null : Math.round(a * 10) / 10)}}${{oppRankChip(r, first.opponent)}}`
        + (sh !== null && sh !== undefined ? `<div style="font-size:11px;" title="${{escapeHtml(shareTip)}}"><span class="muted">${{sh}}% share &middot; proj</span> <strong>${{proj === null || proj === undefined ? '-' : Math.round(proj * 10) / 10}}</strong></div>` : '')
        + (line !== null && line !== undefined ? `<div class="muted" style="font-size:11px;">line ${{line}}</div>` : '') + `</td>`;
    }}
    gameRowsHtml += `<tr class="upcoming-row">${{up}}</tr>`;
  }}
  for (const entry of gameEntries) {{
    if (entry.idx === null) {{
      const dnpCells = '<td class="muted">DNP</td>'.repeat(playerRows.length);
      gameRowsHtml += `<tr class="muted" title="No offensive snaps recorded for this player in Week ${{entry.week}} (inactive, injured, or a bye) -- not a missing-data gap.">
        <td>${{SEASON}} Wk${{entry.week}} &mdash; DNP</td>${{dnpCells}}
      </tr>`;
      continue;
    }}
    const i = entry.idx;
    const week = first.game_weeks[i];
    const season = first.game_seasons[i];
    const opp = first.game_opponents[i];
    let cells = `<td>${{season}} Wk${{week}} vs ${{opp}}</td>`;
    for (const r of playerRows) {{
      const v = r.game_log[i];
      cells += `<td>${{fmt(Math.round(v * 10) / 10)}}${{oppRankChip(r, opp)}}</td>`;
    }}
    gameRowsHtml += `<tr>${{cells}}</tr>`;
  }}
  const gameHeaderCells = playerRows.map(r => `<th>${{r.stat_label}}</th>`).join('');

  // "Avg opp rank faced" footer: the average of the #N chips in each
  // column, i.e. did this player's numbers come against tough or soft
  // defenses for that stat. Only games actually played count (not DNP).
  let avgRankCells = '<td class="muted">Avg opp rank faced</td>';
  for (const r of playerRows) {{
    const info = defCache[r.position + '|' + r.stat_col];
    const rs = gameIdx.map(i => info && info.ranks[first.game_opponents[i]]).filter(x => x !== undefined && x !== null);
    if (!rs.length) {{ avgRankCells += '<td class="muted">-</td>'; continue; }}
    const avg = Math.round(rs.reduce((a, b) => a + b, 0) / rs.length * 10) / 10;
    const max = Object.keys(info.ranks).length;
    avgRankCells += `<td><span class="opp-rank-chip" ${{rankStyle(Math.round(avg), max)}}>#${{avg}}</span></td>`;
  }}
  // His average per stat over the games above (DNP weeks don't count).
  let hisAvgCells = `<td class="muted">His avg (${{gameIdx.length}} game${{gameIdx.length === 1 ? '' : 's'}})</td>`;
  for (const r of playerRows) {{
    const vs = gameIdx.map(i => r.game_log[i]).filter(v => v !== null && v !== undefined);
    hisAvgCells += `<td>${{vs.length ? fmt(Math.round(vs.reduce((a, b) => a + b, 0) / vs.length * 10) / 10) : '<span class="muted">-</span>'}}</td>`;
  }}
  const avgRankRow = gameIdx.length ? `<tr class="opp-rank-avg">${{hisAvgCells}}</tr><tr class="opp-rank-avg">${{avgRankCells}}</tr>` : '';

  document.getElementById('modalBody').innerHTML = `
    <div class="modal-table-wrap">
    <table class="modal-table">
      <thead><tr>
        <th>Mark</th><th>Stat</th><th>Avg (${{weeksLabel(selectedWeeks)}})</th><th>Opp Allows</th><th>Opp Rank</th><th>Hit</th><th>Opp Hit</th>
        <th>Team Share</th><th>Anticipated</th><th>Edge</th><th>Anc. Edge</th><th>&#128293;/&#129482;/&#11088;</th>
        <th>DraftKings</th><th>FanDuel</th><th>BetMGM</th>
      </tr></thead>
      <tbody>${{summaryHtml}}</tbody>
    </table>
    </div>${{impactHtml}}${{secondLookHtml(playerRows)}}
    <h3 class="modal-section-title">Game-by-game (${{weeksLabel(selectedWeeks)}})</h3>
    <div class="modal-note">#N next to each number = how that game's opponent ranks at defending that stat against ${{escapeHtml(first.position)}}s (1 = toughest, ${{Object.keys((defCache[first.position + '|' + first.stat_col] || {{ranks: {{}}}}).ranks).length || 32}} = easiest), based on ${{weeksLabel(selectedWeeks)}} -- same ranking as the Opp Rank column.</div>
    <div class="modal-table-wrap">
    <table class="modal-table">
      <thead><tr><th>Game</th>${{gameHeaderCells}}</tr></thead>
      <tbody>${{gameRowsHtml || '<tr><td colspan="' + (playerRows.length + 1) + '" class="muted">No game data available.</td></tr>'}}${{avgRankRow}}</tbody>
    </table>
    </div>`;
  document.getElementById('playerModalOverlay').style.display = 'flex';
}}

// --- Defense detail modal: click a row's Opp team to see everything that
// defense has allowed, broken out by position, over the same selected-
// weeks filter as the rest of the page -- and, like the player modal, an
// actual game-by-game breakdown per position, not just a season average. ---
let currentModalDefenseTeam = null;

// Offense rankings for the defense card (added 2026-10-05, per Trevor:
// "adjust the defense pop up to show how that offense they played ranks").
// For a position+stat, each offense's average production in the selected
// weeks (what every defense allowed when facing it), ranked 1 = produces
// the MOST. Built from the same per-game data as the excused-miss logic
// (offenseGames()), so the two always agree.
const OFF_RANK_EDGE = 8; // top/bottom 8 get a colored chip
const _offRankCache = {{}};
function rankOffenses(key, pos, weeks) {{
  const ck = key + '|' + Array.from(weeks).sort((a, b) => a - b).join(',');
  if (_offRankCache[ck]) return _offRankCache[ck];
  const byOff = offenseGames(key, pos, weeks);
  const avgs = {{}};
  for (const [off, g] of Object.entries(byOff)) avgs[off] = g.reduce((a, b) => a + b.val, 0) / g.length;
  const entries = Object.entries(avgs).sort((a, b) => b[1] - a[1]);
  const ranks = {{}};
  for (let i = 0; i < entries.length; i++) {{
    const [off, v] = entries[i];
    ranks[off] = (i > 0 && entries[i - 1][1] === v) ? ranks[entries[i - 1][0]] : i + 1;
  }}
  return (_offRankCache[ck] = {{ avgs, ranks }});
}}
function offRankChip(key, pos, label, off, defTeam, week, allowed) {{
  if (!off) return '';
  const {{ avgs, ranks }} = rankOffenses(key, pos, selectedWeeks);
  const rank = ranks[off];
  if (rank === undefined) return '';
  const max = Object.keys(ranks).length;
  const usual = offenseUsual(key, pos, selectedWeeks, off, defTeam, week);
  const r1 = v => Math.round(v * 10) / 10;
  const cls = rank <= OFF_RANK_EDGE ? 'off-hi' : (rank > max - OFF_RANK_EDGE ? 'off-lo' : '');
  const tip = `${{off}} offense: #${{rank}} of ${{max}} at ${{pos}} ${{label}} (1 = produces the most), averaging ${{r1(avgs[off])}} per game` +
    (usual !== null ? `; ${{r1(usual)}} in its other games` : '') +
    `. ${{defTeam}} allowed ${{r1(allowed)}} here` +
    (usual !== null ? (allowed < usual ? ` -- ${{r1(usual - allowed)}} below what ${{off}} usually gets.` : ` -- ${{r1(allowed - usual)}} above what ${{off}} usually gets.`) : '.');
  return ` <span class="opp-rank-chip ${{cls}}" title="${{escapeHtml(tip)}}">#${{rank}}</span>`;
}}

// This week's opponent for a team (added 2026-10-12, per Trevor: in the
// defense card, also show the offense this defense is playing THIS week and
// how it ranks, next to the offenses it has already faced).
function upcomingOpponent(team) {{
  const g = GAMES.find(x => x.home === team || x.away === team);
  return g ? (g.home === team ? g.away : g.home) : null;
}}
function upcomingOffCell(key, pos, label, off) {{
  const {{ avgs, ranks }} = rankOffenses(key, pos, selectedWeeks);
  const rank = ranks[off];
  if (rank === undefined) return '<td class="muted">-</td>';
  const max = Object.keys(ranks).length;
  const avg = Math.round(avgs[off] * 10) / 10;
  const cls = rank <= OFF_RANK_EDGE ? 'off-hi' : (rank > max - OFF_RANK_EDGE ? 'off-lo' : '');
  const tip = `${{off}} offense: #${{rank}} of ${{max}} at ${{pos}} ${{label}} (1 = produces the most), averaging ${{avg}} per game over ${{weeksLabel(selectedWeeks)}}.`;
  return `<td>${{fmt(avg)}} <span class="opp-rank-chip ${{cls}}" title="${{escapeHtml(tip)}}">#${{rank}}</span></td>`;
}}

function openDefenseModal(team, clickedPos) {{
  currentModalDefenseTeam = team;
  document.getElementById('modalPlayerName').textContent = team + ' Defense';
  document.getElementById('modalMeta').textContent =
    'What ' + team + ' has allowed, by position · Weeks: ' + weeksLabel(selectedWeeks);

  const cov = COVERAGE[team];
  const covTier = cov ? coverageTier(cov.zone_rate) : null;
  const covHtml = (cov && cov.man_rate !== null && cov.man_rate !== undefined)
    ? `<div class="cov-header">Coverage scheme (season-to-date, all games -- not just the selected Weeks filter): `
      + `<strong>${{cov.man_rate}}% Man</strong> / <strong>${{cov.zone_rate}}% Zone</strong>`
      + (covTier ? ` <span class="cov-tag ${{covTier.cls}}">${{covTier.label}}</span>` : '')
      + (cov.middle_closed_rate !== null && cov.middle_closed_rate !== undefined
          ? ` · Middle Closed ${{cov.middle_closed_rate}}% / Open ${{cov.middle_open_rate}}%` : '')
      + `. Team-level only -- this says how often ${{team}} plays each scheme, not how any specific `
      + `player does against it (no free source exists for that). Source: `
      + `<a href="https://www.sharpfootballanalysis.com/stats-nfl/nfl-coverage-schemes/" target="_blank" rel="noopener">Sharp Football Analysis</a>.</div>`
    : `<div class="cov-header">No coverage-scheme data yet -- run <code>python3 fetch_coverage.py</code> to add it.</div>`;

  // Show the position that was actually clicked first (if it has data),
  // then whatever else this team has, so the relevant section is always
  // right at the top rather than buried alphabetically.
  const positions = Object.keys(STAT_CATALOG);
  const ordered = clickedPos && positions.includes(clickedPos)
    ? [clickedPos, ...positions.filter(p => p !== clickedPos)]
    : positions;

  let sectionsHtml = '';
  for (const pos of ordered) {{
    const statsForPos = STAT_CATALOG[pos];
    const perStatValues = {{}};
    let anyData = false;
    for (const [col] of statsForPos) {{
      const key = pos + '|' + col;
      const teamLog = (DEFENSE_LOGS[key] && DEFENSE_LOGS[key][team]) || [];
      perStatValues[col] = teamLog;
      if (teamLog.length) anyData = true;
    }}
    if (!anyData) continue;

    let summaryRows = '';
    const nextOff = upcomingOpponent(team);
    for (const [col, label] of statsForPos) {{
      const key = pos + '|' + col;
      const {{ avgs, ranks }} = rankDefenses(key, selectedWeeks);
      const avg = avgs[team];
      const rank = ranks[team];
      const rankMax = Object.keys(ranks).length;
      summaryRows += `
      <tr>
        <td>${{label}}</td>
        <td>${{fmt(avg === undefined || avg === null ? null : Math.round(avg * 100) / 100)}}</td>
        <td ${{rankStyle(rank === undefined ? null : rank, rankMax)}}>${{fmt(rank === undefined ? null : rank)}}</td>
        ${{nextOff ? upcomingOffCell(key, pos, label, nextOff) : ''}}
      </tr>`;
    }}

    // Game-by-game: DEFENSE_GAMES[team][pos] is the same order/length as
    // every stat column's value list above for this team+position.
    const gamesMeta = (DEFENSE_GAMES[team] && DEFENSE_GAMES[team][pos]) || [];
    const gameIdx = defenseSelectedIndices(gamesMeta, selectedWeeks);
    let gameRowsHtml = '';
    if (nextOff) {{
      let up = `<td><strong>This week vs ${{nextOff}}</strong> <span class="muted">(their avg)</span></td>`;
      for (const [col, label] of statsForPos) up += upcomingOffCell(pos + '|' + col, pos, label, nextOff);
      gameRowsHtml += `<tr class="upcoming-row">${{up}}</tr>`;
    }}
    for (const i of gameIdx) {{
      const vsLabel = gamesMeta[i].vs ? (' vs ' + gamesMeta[i].vs) : '';
      let cells = `<td>${{gamesMeta[i].season}} Wk${{gamesMeta[i].week}}${{vsLabel}}</td>`;
      for (const [col, label] of statsForPos) {{
        const v = perStatValues[col][i];
        cells += `<td>${{fmt(v === undefined ? null : Math.round(v * 10) / 10)}}${{v === undefined ? '' : offRankChip(pos + '|' + col, pos, label, gamesMeta[i].vs, team, gamesMeta[i].week, v)}}</td>`;
      }}
      gameRowsHtml += `<tr>${{cells}}</tr>`;
    }}
    // Average offense rank faced, per stat -- was this defense's sample
    // against strong or weak offenses for that stat?
    let avgOffCells = '<td class="muted">Avg offense rank faced</td>';
    for (const [col] of statsForPos) {{
      const {{ ranks: oRanks }} = rankOffenses(pos + '|' + col, pos, selectedWeeks);
      const rs = gameIdx.map(i => oRanks[gamesMeta[i].vs]).filter(x => x !== undefined);
      if (!rs.length) {{ avgOffCells += '<td class="muted">-</td>'; continue; }}
      const avg = Math.round(rs.reduce((a, b) => a + b, 0) / rs.length * 10) / 10;
      const oMax = Object.keys(oRanks).length;
      avgOffCells += `<td><span class="opp-rank-chip ${{avg <= OFF_RANK_EDGE ? 'off-hi' : (avg > oMax - OFF_RANK_EDGE ? 'off-lo' : '')}}">#${{avg}}</span></td>`;
    }}
    if (gameIdx.length) gameRowsHtml += `<tr class="opp-rank-avg">${{avgOffCells}}</tr>`;
    if (!gameIdx.length && nextOff) gameRowsHtml += `<tr><td colspan="${{statsForPos.length + 1}}" class="muted">No games in the selected weeks.</td></tr>`;
    const gameHeaderCells = statsForPos.map(([, label]) => `<th>${{label}}</th>`).join('');

    sectionsHtml += `
    <h3 class="modal-section-title">${{pos}} allowed</h3>
    <div class="modal-table-wrap">
    <table class="modal-table">
      <thead><tr><th>Stat</th><th>Avg Allowed (${{weeksLabel(selectedWeeks)}})</th><th>Rank</th>${{nextOff ? `<th title="What the offense ${{team}} plays this week produces per game at this position/stat, and its rank among offenses (1 = produces the most).">This week: ${{nextOff}} offense</th>` : ''}}</tr></thead>
      <tbody>${{summaryRows}}</tbody>
    </table>
    </div>
    <div class="modal-note">${{nextOff ? `Top row (highlighted) = ${{nextOff}}, the offense ${{team}} plays this week: its own per-game average and rank, to compare with the offenses below. ` : ''}}#N next to each number = how the offense ${{team}} faced that week ranks at producing that stat for ${{pos}}s (1 = produces the most). <span class="opp-rank-chip off-hi">orange</span> = one of the ${{OFF_RANK_EDGE}} highest-volume offenses, <span class="opp-rank-chip off-lo">blue</span> = one of the ${{OFF_RANK_EDGE}} lowest -- a small number allowed to a blue offense says little about this defense. Hover for that offense's usual output.</div>
    <div class="modal-table-wrap">
    <table class="modal-table">
      <thead><tr><th>Game</th>${{gameHeaderCells}}</tr></thead>
      <tbody>${{gameRowsHtml || '<tr><td colspan="' + (statsForPos.length + 1) + '" class="muted">No game data available.</td></tr>'}}</tbody>
    </table>
    </div>`;
  }}

  document.getElementById('modalBody').innerHTML =
    covHtml + (sectionsHtml || '<p class="muted">No defense data available for this team yet.</p>');
  document.getElementById('playerModalOverlay').style.display = 'flex';
}}

function closePlayerModal() {{
  myBetsOpen = false;
  document.querySelector('#playerModalOverlay .modal-panel').style.maxWidth = '';
  currentModalPlayer = null;
  currentModalDefenseTeam = null;
  document.getElementById('playerModalOverlay').style.display = 'none';
}}

document.getElementById('tbody').addEventListener('click', (e) => {{
  // Don't let a click on the Mark selector bubble up into "open this
  // row's player modal" -- the whole <tr> is otherwise clickable.
  if (e.target.closest('.mark-select, .bet-slip, .gs-link')) return;
  const oppCell = e.target.closest('td.opp-cell');
  if (oppCell) {{
    openDefenseModal(oppCell.dataset.opponent, oppCell.dataset.oppPos);
    return;
  }}
  const tr = e.target.closest('tr[data-player]');
  if (tr) openPlayerModal(tr.dataset.player);
}});

// Personal bet marks: delegated so it keeps working across every
// render() rebuild of tbody's HTML, same pattern as the click handler
// above. Re-renders after saving so a newly-❌'d row can disappear right
// away when "Hide ❌ rows" is checked.
document.getElementById('tbody').addEventListener('change', (e) => {{
  const betEl = e.target.closest('.bet-field');
  if (betEl) {{ handleBetField(betEl); return; }}
  const sel = e.target.closest('.mark-select');
  if (!sel) return;
  const key = sel.dataset.markKey;
  if (sel.value) MARKS[key] = sel.value; else delete MARKS[key];
  saveMarks();
  if (sel.value === 'bet') {{ ensureBetMeta(key); snapshotMarket(key); saveBets(); }}
  if (sel.value === 'parlay') {{ ensureBetMeta(key); saveBets(); }}
  render();
}});

// Filter checkboxes remember their state (added 2026-10-16, per Trevor:
// "whenever i reload the page, hide x rows is checked but the x still show
// up"). The browser restored the tick on reload while these variables
// started false, so box and table disagreed. Now each box's state is saved
// here and read back before the first render.
const FILTER_STORAGE_KEY = 'nfl_prop_dashboard_filters_v1';
const FILTER_BOXES = {{
  hideMarkedX: v => {{ hideMarkedX = v; }},
  hideReview: v => {{ hideReview = v; }},
  ladderOnlyFilter: v => {{ ladderOnly = v; }},
  altOnlyFilter: v => {{ altOnly = v; }},
  weakMatchupFilter: v => {{ weakMatchupOnly = v; }},
  strongMatchupFilter: v => {{ strongMatchupOnly = v; }},
}};
function saveFilterBoxes() {{
  const st = {{}};
  for (const id of Object.keys(FILTER_BOXES)) {{ const el = document.getElementById(id); if (el) st[id] = el.checked; }}
  try {{ localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(st)); }} catch (e) {{}}
}}
(function restoreFilterBoxes() {{
  let saved = {{}};
  try {{ saved = JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY) || '{{}}') || {{}}; }} catch (e) {{}}
  for (const [id, set] of Object.entries(FILTER_BOXES)) {{
    const el = document.getElementById(id);
    if (!el) continue;
    if (id === 'hideMarkedX') el.checked = true; // always loads ticked, per Trevor: "i want it to load with hide rows checked"
    else if (typeof saved[id] === 'boolean') el.checked = saved[id];
    set(el.checked); // whatever the box shows is what the table uses
    el.addEventListener('change', saveFilterBoxes);
  }}
}})();

document.getElementById('hideReview').addEventListener('change', (e) => {{
  hideReview = e.target.checked;
  render();
}});
document.getElementById('hideMarkedX').addEventListener('change', (e) => {{
  hideMarkedX = e.target.checked;
  render();
}});

document.getElementById('ladderOnlyFilter').addEventListener('change', (e) => {{
  ladderOnly = e.target.checked;
  render();
}});

document.getElementById('altOnlyFilter').addEventListener('change', (e) => {{
  altOnly = e.target.checked;
  render();
}});

document.getElementById('weakMatchupFilter').addEventListener('change', (e) => {{
  weakMatchupOnly = e.target.checked;
  render();
}});

document.getElementById('signalMode').value = SIGNAL_MODE;
document.getElementById('signalMode').addEventListener('change', (e) => {{
  SIGNAL_MODE = e.target.value;
  try {{ localStorage.setItem('nfl_prop_dashboard_signal_mode', SIGNAL_MODE); }} catch (err) {{}}
  render();
}});
document.getElementById('strongMatchupFilter').addEventListener('change', (e) => {{
  strongMatchupOnly = e.target.checked;
  render();
}});

// Same mark-saving logic as the main table's tbody listener above, for
// the copy of the Mark selector shown inside the player detail modal.
document.getElementById('modalBody').addEventListener('change', (e) => {{
  if (e.target.id === 'betsWeekFilter') {{
    betsWeekFilter = e.target.value;
    openMyBetsModal();
    return;
  }}
  const betEl = e.target.closest('.bet-field');
  if (betEl && myBetsOpen) {{
    handleBetField(betEl);
    if (betEl.dataset.field === 'week') {{ openMyBetsModal(); render(); return; }} // re-group under the right week
    const tr = betEl.closest('tr[data-bet-key]');
    if (tr) refreshBetRow(tr);
    render(); // keep the main table's slips in sync
    return;
  }}
  if (betEl) {{
    handleBetField(betEl);
    render(); // keep the main table's copy of the slip in sync (focus stays in the popup)
    return;
  }}
  const sel = e.target.closest('.mark-select');
  if (!sel) return;
  const key = sel.dataset.markKey;
  if (sel.value) MARKS[key] = sel.value; else delete MARKS[key];
  saveMarks();
  if (sel.value === 'bet' || sel.value === 'parlay') {{ ensureBetMeta(key); saveBets(); }}
  render(); // updates the main table underneath so it's current whenever the modal closes
  if (currentModalPlayer) {{
    // redraw the popup so a newly-✅'d stat shows its bet slip right away
    const scroller = document.querySelector('.modal-panel');
    const top = scroller ? scroller.scrollTop : 0;
    openPlayerModal(currentModalPlayer);
    if (scroller) scroller.scrollTop = top;
  }}
}});

document.getElementById('modalClose').addEventListener('click', closePlayerModal);
document.getElementById('playerModalOverlay').addEventListener('click', (e) => {{
  if (e.target.id === 'playerModalOverlay') closePlayerModal();
}});
document.addEventListener('keydown', (e) => {{
  if (e.key === 'Escape') {{
    closePlayerModal();
    document.getElementById('weeksPanel').classList.remove('open');
  }}
}});

document.querySelectorAll('.stat-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.stat-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeStat = btn.dataset.stat;
    render();
  }});
}});

// --- Weeks filter: a dropdown panel of checkboxes (1 per regular-season
// week) instead of the old fixed Last 2/3/5/10-games buttons. Toggle
// button opens/closes the panel; clicks inside the panel don't bubble up
// and close it, so checking several weeks in a row doesn't require
// reopening it each time. ---
function sameWeekSet(a, b) {{ return a.size === b.size && Array.from(a).every(w => b.has(w)); }}
function updateWeeksToggleLabel() {{
  document.getElementById('weeksToggle').textContent = 'Weeks: ' + weeksLabel(selectedWeeks) + ' ▾';
  document.querySelectorAll('.weeks-quick').forEach(btn => {{
    const n = btn.dataset.last === 'all' ? TOTAL_WEEKS : parseInt(btn.dataset.last, 10);
    btn.classList.toggle('active', sameWeekSet(selectedWeeks, lastNWeeks(n)));
  }});
}}

function populateWeeksFilter() {{
  const grid = document.getElementById('weeksGrid');
  let html = '';
  for (let w = 1; w <= TOTAL_WEEKS; w++) {{
    const checked = selectedWeeks.has(w) ? 'checked' : '';
    html += `<label class="week-checkbox"><input type="checkbox" data-week="${{w}}" ${{checked}}> ${{w}}</label>`;
  }}
  grid.innerHTML = html;
  updateWeeksToggleLabel();
}}

document.getElementById('weeksToggle').addEventListener('click', (e) => {{
  e.stopPropagation();
  document.getElementById('weeksPanel').classList.toggle('open');
}});
document.getElementById('weeksPanel').addEventListener('click', (e) => {{
  e.stopPropagation();
}});
document.getElementById('weeksGrid').addEventListener('change', (e) => {{
  const cb = e.target.closest('input[type=checkbox][data-week]');
  if (!cb) return;
  const w = parseInt(cb.dataset.week, 10);
  if (cb.checked) selectedWeeks.add(w); else selectedWeeks.delete(w);
  updateWeeksToggleLabel();
  render();
}});
document.getElementById('weeksAll').addEventListener('click', () => {{
  selectedWeeks = new Set(Array.from({{length: TOTAL_WEEKS}}, (_, i) => i + 1));
  populateWeeksFilter();
  render();
}});
document.getElementById('weeksNone').addEventListener('click', () => {{
  selectedWeeks = new Set();
  populateWeeksFilter();
  render();
}});
document.getElementById('weeksToDate').addEventListener('click', () => {{
  selectedWeeks = lastNWeeks(TOTAL_WEEKS);
  populateWeeksFilter();
  render();
}});
document.querySelectorAll('.weeks-quick').forEach(btn => btn.addEventListener('click', (e) => {{
  e.stopPropagation();
  const n = btn.dataset.last === 'all' ? TOTAL_WEEKS : parseInt(btn.dataset.last, 10);
  selectedWeeks = lastNWeeks(n);
  populateWeeksFilter();
  render();
}}));
document.addEventListener('click', () => {{
  document.getElementById('weeksPanel').classList.remove('open');
}});

document.querySelectorAll('.pos-btn[data-pos]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.pos-btn[data-pos]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activePos = btn.dataset.pos;
    render();
  }});
}});

document.querySelectorAll('th[data-key]').forEach(th => {{
  th.addEventListener('click', () => {{
    if (_suppressSortClick) return;
    const key = th.dataset.key;
    if (sortKey === key) sortDir *= -1; else {{ sortKey = key; sortDir = (key === 'mark_rank') ? -1 : 1; }}
    render();
  }});
}});

// How-picky slider removed 2026-10-07 (Trevor: "get rid of the how picky
// meter for now"). pickyPct stays at its default so Average-edge mode still works.
const _pickySlider = document.getElementById('pickySlider');
if (_pickySlider) _pickySlider.addEventListener('input', (e) => {{
  pickyPct = parseInt(e.target.value, 10);
  applyPickySetting();
  render();
}});

document.getElementById('gameFilter').addEventListener('change', (e) => {{
  activeGame = e.target.value;
  saveGameFilter(activeGame);
  render();
}});

document.getElementById('search').addEventListener('input', render);
applyPickySetting();
populateGameFilter();
populateWeeksFilter();

backfillBetMeta();
snapshotAllMarkets();
document.getElementById('myBetsBtn').addEventListener('click', openMyBetsModal);
document.getElementById('modalBody').addEventListener('click', (e) => {{
  if (!myBetsOpen) return;
  const t = e.target;
  const wkLink = t.closest('.bets-week-link');
  if (wkLink) {{
    betsWeekFilter = wkLink.dataset.weekKey;
    openMyBetsModal();
    return;
  }}
  if (t.id === 'parlayShowUsed') {{
    e.preventDefault();
    parlayShowUsed = true;
    openMyBetsModal();
    return;
  }}
  if (t.id === 'parlayAdd') {{
    addParlayFromBuilder();
    return;
  }}
  if (t.id === 'betsAddManual') {{
    const key = 'manual|' + Date.now();
    BETS[key] = {{ week: betsWeekFilter === 'ALL' ? String(WEEK) : betsWeekFilter.split('|')[1] }};
    saveBets();
    openMyBetsModal();
    const inp = document.querySelector(`tr[data-bet-key="${{key}}"] .bet-desc`);
    if (inp) inp.focus();
    return;
  }}
  if (t.id === 'betsFillSuggested') {{
    for (const x of allBets()) {{
      if (x.b.result) continue;
      const sug = x.b.legs ? parlaySuggestion(x.b) : suggestedResult(x, betActual(x));
      if (sug) {{ BETS[x.key] = Object.assign(BETS[x.key] || {{}}, {{ result: sug }}); }}
    }}
    saveBets();
    openMyBetsModal();
    render();
    return;
  }}
  if (t.id === 'betsBackup') {{
    const p = document.getElementById('betsBackupPanel');
    p.style.display = p.style.display === 'none' ? 'block' : 'none';
    document.getElementById('betsBackupText').value = JSON.stringify({{ marks: MARKS, bets: BETS }});
    return;
  }}
  if (t.id === 'betsRestore') {{
    const msg = document.getElementById('betsRestoreMsg');
    try {{
      const data = JSON.parse(document.getElementById('betsBackupText').value);
      Object.assign(MARKS, data.marks || {{}});
      for (const [k, v] of Object.entries(data.bets || {{}})) BETS[k] = Object.assign(BETS[k] || {{}}, v);
      saveMarks(); saveBets();
      openMyBetsModal();
      render();
    }} catch (err) {{
      msg.textContent = "Couldn't read that -- paste the whole backup text.";
    }}
    return;
  }}
  if (t.classList.contains('bet-remove')) {{
    // Two clicks to delete (no confirm() popups -- they're blocked on the shared link).
    if (!t.dataset.armed) {{ t.dataset.armed = '1'; t.textContent = 'Remove?'; return; }}
    const key = t.closest('tr[data-bet-key]').dataset.betKey;
    delete BETS[key];
    if (MARKS[key] === 'bet') delete MARKS[key];
    saveBets(); saveMarks();
    openMyBetsModal();
    render();
  }}
}});

// ---- Game script analysis (added 2026-10-07, per Trevor: "do a game
// script analysis for each game based on spread, o/u, weather and any
// other factors ... like injuries"). Shown as a panel under the Stat row
// when the Game filter is set, and as a popup from the 🎬 link on every
// row, in My Bets, and in the player card.
//
// Everything here is built from data the page already has, plus three
// small additions: each game's weather/rest/moneylines (GAMES), every
// finished game's score + closing spread/total (TEAM_RESULTS), and each
// team's injury report (INJ_BY_TEAM). Team stats follow the Weeks filter.
// It's context, not a pick: in the Week 3 backtest, game script was the
// only checklist factor that beat a coin flip (called the right side 58%
// of the time) -- still a small sample.
const GS_POS_GROUP = {{ T: 'OL', G: 'OL', C: 'OL', OT: 'OL', OG: 'OL', OL: 'OL', QB: 'QB', RB: 'RB', HB: 'RB', FB: 'RB', WR: 'WR', TE: 'TE',
  DE: 'EDGE', OLB: 'EDGE', EDGE: 'EDGE', DT: 'DI', NT: 'DI', DL: 'DI', LB: 'LB', ILB: 'LB', MLB: 'LB', CB: 'CB', S: 'S', FS: 'S', SS: 'S', SAF: 'S', DB: 'S' }};
const GS_MIN_SNAP = 0.40;   // injured players shown only if they play 40%+ of snaps
const GS_BIG_SPREAD = 7;    // "lopsided"
const GS_MID_SPREAD = 3.5;  // "lean"
const GS_TOTAL_DELTA = 3.5; // total this far above/below the season's average total = high/low scoring
let gsPanelOpen = true;

function gsGame(key) {{ return GAMES.find(g => g.key === key) || null; }}
function gsAvg(a) {{ const v = a.filter(x => x !== null && x !== undefined && !Number.isNaN(x)); return v.length ? v.reduce((x, y) => x + y, 0) / v.length : null; }}
function gsR1(v) {{ return v === null || v === undefined ? '-' : String(Math.round(v * 10) / 10); }}
function gsSigned(v) {{ return v === null || v === undefined ? '-' : (v > 0 ? '+' : '') + gsR1(v); }}
function gsPct(v) {{ return v === null || v === undefined ? '-' : Math.round(v * 100) + '%'; }}
function gsNormCdf(z) {{
  const t = 1 / (1 + 0.2316419 * Math.abs(z));
  const d = 0.3989423 * Math.exp(-z * z / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return z > 0 ? 1 - p : p;
}}
function gsMlProb(ml) {{ return ml > 0 ? 100 / (ml + 100) : -ml / (-ml + 100); }}
function gsPlayedWeeks(weeks) {{
  const w = new Set(Array.from(weeks).filter(x => x < WEEK));
  return w.size ? w : new Set(TEAM_RESULTS.map(g => g.week));
}}

// One team's finished games in the selected weeks, newest first.
function gsTeamResults(team, weeks) {{
  return TEAM_RESULTS.filter(g => (g.home === team || g.away === team) && weeks.has(g.week)
      && g.home_score !== null && g.away_score !== null).map(g => {{
    const home = g.home === team;
    const pf = home ? g.home_score : g.away_score, pa = home ? g.away_score : g.home_score;
    const sp = g.spread_line === null ? null : (home ? g.spread_line : -g.spread_line); // + = this team was favored
    const margin = pf - pa;
    const ats = sp === null ? null : (margin - sp > 0 ? 'W' : margin - sp < 0 ? 'L' : 'P');
    const tot = pf + pa;
    const ou = g.total_line === null ? null : (tot > g.total_line ? 'O' : tot < g.total_line ? 'U' : 'P');
    return {{ week: g.week, opp: home ? g.away : g.home, home, pf, pa, margin, sp, ats, ou, tot, line: g.total_line, ot: g.overtime }};
  }}).sort((a, b) => b.week - a.week);
}}
function gsBaseline(weeks) {{
  const games = TEAM_RESULTS.filter(g => weeks.has(g.week) && g.home_score !== null);
  return {{ totalLine: gsAvg(games.map(g => g.total_line)), points: gsAvg(games.map(g => g.home_score + g.away_score)), n: games.length }};
}}
function gsOffAvg(key, pos, team, weeks) {{
  const g = offenseGames(key, pos, weeks)[team] || [];
  return gsAvg(g.map(x => x.val));
}}
function gsLeaguePassRate(weeks) {{
  const att = offenseGames('QB|attempts', 'QB', weeks), car = offenseGames('RB|carries', 'RB', weeks);
  const rates = Object.keys(att).map(t => {{
    const a = gsAvg((att[t] || []).map(x => x.val)), c = gsAvg((car[t] || []).map(x => x.val));
    return a !== null && c !== null && a + c > 0 ? a / (a + c) : null;
  }});
  return gsAvg(rates);
}}
function gsTeamProfile(team, weeks) {{
  const res = gsTeamResults(team, weeks);
  const cnt = (f) => res.filter(f).length;
  const passAtt = gsOffAvg('QB|attempts', 'QB', team, weeks);
  const rbCar = gsOffAvg('RB|carries', 'RB', team, weeks);
  const dPass = rankDefenses('QB|passing_yards', weeks), dRun = rankDefenses('RB|rushing_yards', weeks);
  const oPass = rankOffenses('QB|passing_yards', 'QB', weeks), oRun = rankOffenses('RB|rushing_yards', 'RB', weeks);
  const oAtt = rankOffenses('QB|attempts', 'QB', weeks);
  return {{
    team, res,
    w: cnt(x => x.margin > 0), l: cnt(x => x.margin < 0), t: cnt(x => x.margin === 0),
    atsW: cnt(x => x.ats === 'W'), atsL: cnt(x => x.ats === 'L'), atsP: cnt(x => x.ats === 'P'),
    ouO: cnt(x => x.ou === 'O'), ouU: cnt(x => x.ou === 'U'), ouP: cnt(x => x.ou === 'P'),
    ppg: gsAvg(res.map(x => x.pf)), papg: gsAvg(res.map(x => x.pa)), margin: gsAvg(res.map(x => x.margin)),
    passAtt, rbCar,
    passYds: gsOffAvg('QB|passing_yards', 'QB', team, weeks),
    rbYds: gsOffAvg('RB|rushing_yards', 'RB', team, weeks),
    qbRush: gsOffAvg('QB|rushing_yards', 'QB', team, weeks),
    passRate: passAtt !== null && rbCar !== null && passAtt + rbCar > 0 ? passAtt / (passAtt + rbCar) : null,
    offPassRank: oPass.ranks[team], offRunRank: oRun.ranks[team], offAttRank: oAtt.ranks[team],
    nOff: Object.keys(oPass.ranks).length || 32,
    defPass: dPass.avgs[team], defPassRank: dPass.ranks[team],
    defRun: dRun.avgs[team], defRunRank: dRun.ranks[team],
    nDef: Object.keys(dPass.ranks).length || 32,
  }};
}}
function gsInjuries(team) {{
  return (INJ_BY_TEAM[team] || [])
    .filter(p => (p.snap_pct || 0) >= GS_MIN_SNAP && (p.severity || 0) >= 1)
    .map(p => Object.assign({{}}, p, {{ group: GS_POS_GROUP[p.position] || p.position }}))
    .sort((a, b) => (b.severity - a.severity) || ((b.snap_pct || 0) - (a.snap_pct || 0)));
}}
// Teammates who'd absorb the work, by their average over the selected weeks.
function gsNextUp(team, positions, statCol, exclude) {{
  return ROWS.filter(r => r.team === team && positions.includes(r.position) && r.stat_col === statCol && !exclude.has(r.player))
    .map(r => ({{ name: r.player, v: gsAvg(playerSelectedIndices(r, selectedWeeks).map(i => r.game_log[i])) }}))
    .filter(x => x.v !== null && x.v > 0).sort((a, b) => b.v - a.v).slice(0, 3);
}}
function gsPlayerLink(name) {{ return `<span class="gs-player" data-player="${{escapeHtml(name)}}">${{escapeHtml(name)}}</span>`; }}
function gsInjNotes(team, opp) {{
  const inj = gsInjuries(team);
  if (!inj.length) return {{ list: [], notes: [] }};
  const names = new Set(inj.map(p => p.name));
  const firm = (p) => p.severity >= 3;
  const by = (grp) => inj.filter(p => p.group === grp);
  const who = (arr) => arr.map(p => `${{escapeHtml(p.name)}} (${{escapeHtml(p.status)}})`).join(', ');
  const notes = [];
  const qb = by('QB');
  if (qb.length) notes.push({{ dir: -1, team, text: qb.some(p => p.severity >= 2)
    ? `QB ${{who(qb)}} -- the whole ${{team}} passing game, and the game script, depend on who starts. Re-check before betting either side's passing props.`
    : `QB ${{who(qb)}} -- only a practice note so far; watch the final injury report before betting ${{team}} passing props.` }});
  const ol = by('OL');
  if (ol.length >= 2) notes.push({{ dir: -1, team, text: `${{ol.length}} starting linemen on the report (${{who(ol)}}) -- more pressure on the ${{team}} QB and a tougher day for the run game.` }});
  else if (ol.length === 1 && firm(ol[0])) notes.push({{ dir: -1, team, text: `Lineman ${{who(ol)}} -- a small downgrade for the ${{team}} QB and run game.` }});
  const rec = by('WR').concat(by('TE'));
  if (rec.length) {{
    const nu = gsNextUp(team, ['WR', 'TE', 'RB'], 'targets', names);
    notes.push({{ dir: 0, team, text: `Receivers ${{who(rec)}} -- targets would shift${{nu.length ? ' to ' + nu.map(x => gsPlayerLink(x.name) + ' (' + gsR1(x.v) + ' tgt/g)').join(', ') : ''}}.` }});
  }}
  const rb = by('RB');
  if (rb.length) {{
    const nu = gsNextUp(team, ['RB'], 'carries', names);
    notes.push({{ dir: 0, team, text: `RB ${{who(rb)}} -- carries would shift${{nu.length ? ' to ' + nu.map(x => gsPlayerLink(x.name) + ' (' + gsR1(x.v) + ' car/g)').join(', ') : ''}}.` }});
  }}
  const sec = by('CB').concat(by('S'));
  if (sec.length) notes.push({{ dir: 1, team: opp, text: `${{team}} secondary: ${{who(sec)}} -- helps the ${{opp}} passing game.` }});
  const front = by('EDGE').concat(by('DI'));
  if (front.length) notes.push({{ dir: 1, team: opp, text: `${{team}} pass rush / D-line: ${{who(front)}} -- more time for the ${{opp}} QB and a softer run front.` }});
  const lb = by('LB');
  if (lb.length) notes.push({{ dir: 1, team: opp, text: `${{team}} linebackers: ${{who(lb)}} -- helps ${{opp}} RBs and TEs.` }});
  return {{ list: inj, notes }};
}}
function gsWeather(g) {{
  const w = g.weather;
  if (!w) return {{ text: 'No forecast in this build.', notes: [], bad: false }};
  if (w.dome) return {{ text: `Indoors (${{escapeHtml(w.stadium || 'dome')}}) -- no weather effect.`, notes: [], bad: false }};
  if (!w.available) return {{ text: 'Outdoors -- forecast not posted yet (usually ~a week out).', notes: [], bad: false }};
  const notes = [];
  if (w.wind_mph >= 20) notes.push({{ dir: -1, text: `Strong wind (${{w.wind_mph}} mph): deep passing, completion rate and kicking all suffer -- leans to passing/receiving Unders and more running.` }});
  else if (w.wind_mph >= 15) notes.push({{ dir: -1, text: `Breezy (${{w.wind_mph}} mph): a mild drag on deep passing and long field goals.` }});
  if (w.temp_f <= 25) notes.push({{ dir: -1, text: `Very cold (${{w.temp_f}}°F): harder to throw and catch, slight lean to Unders.` }});
  const cond = (w.condition || '').toLowerCase();
  if (w.precip_pct >= 50 || /rain|snow|drizzle|thunder/.test(cond)) notes.push({{ dir: -1, text: `Wet (${{escapeHtml(w.condition)}}, ${{w.precip_pct}}% chance): ball security and passing efficiency dip; runs and short throws gain share.` }});
  return {{ text: `${{w.temp_f}}°F, wind ${{w.wind_mph}} mph, ${{escapeHtml(w.condition)}} (${{w.precip_pct}}% precip) at ${{escapeHtml(w.stadium || '')}}.`, notes, bad: notes.length > 0 }};
}}

function gameScript(key, weeksIn) {{
  const g = gsGame(key);
  if (!g) return null;
  const weeks = gsPlayedWeeks(weeksIn || selectedWeeks);
  const base = gsBaseline(weeks);
  const A = gsTeamProfile(g.away, weeks), H = gsTeamProfile(g.home, weeks);
  const sp = g.spread; // + = home favored
  const total = g.total;
  const hasLine = sp !== null && sp !== undefined;
  const fav = !hasLine || sp === 0 ? null : (sp > 0 ? g.home : g.away);
  const dog = !fav ? null : (fav === g.home ? g.away : g.home);
  const mag = hasLine ? Math.abs(sp) : null;
  const implied = hasLine && total !== null && total !== undefined
    ? {{ [g.home]: (total + sp) / 2, [g.away]: (total - sp) / 2 }} : null;
  let pHome = null;
  if (g.home_ml && g.away_ml) {{ const ph = gsMlProb(g.home_ml), pa = gsMlProb(g.away_ml); pHome = ph / (ph + pa); }}
  else if (hasLine) pHome = gsNormCdf(sp / 13.5);
  const totalDelta = total !== null && total !== undefined && base.totalLine !== null ? total - base.totalLine : null;
  const pace = totalDelta === null ? null : (totalDelta >= GS_TOTAL_DELTA ? 'high' : totalDelta <= -GS_TOTAL_DELTA ? 'low' : 'mid');
  const shape = !hasLine ? 'none' : (mag >= GS_BIG_SPREAD ? 'lopsided' : (mag >= GS_MID_SPREAD ? 'lean' : 'close'));
  const headline = (!hasLine ? 'No line posted yet' :
      shape === 'lopsided' ? `Lopsided -- ${{fav}} by ${{mag}}` : shape === 'lean' ? `Lean ${{fav}} by ${{mag}}` : (fav ? `Coin flip -- ${{fav}} by ${{mag}}` : 'Pick-em'))
    + (pace === 'high' ? ', high-scoring' : pace === 'low' ? ', low-scoring' : pace === 'mid' ? ', average total' : '');
  const lgPass = gsLeaguePassRate(weeks);
  const prof = {{ [g.home]: H, [g.away]: A }};

  // How the game should flow
  const flow = [];
  if (shape === 'lopsided') {{
    flow.push(`${{fav}} is expected to lead. Teams protecting a lead run more in the second half, so ${{fav}}'s RB volume tends to go up and its late pass attempts down. ${{dog}} is expected to trail: more dropbacks, more targets for its receivers, more QB scrambles, and more interception risk (7+ point underdogs threw an INT in 56% of starts in 2016-25, vs 44% for 7+ point favorites).`);
  }} else if (shape === 'lean') {{
    flow.push(`A modest lean to ${{fav}}. If it plays to the number, ${{dog}} throws a bit more than usual and ${{fav}} leans on the run late, but a ${{mag}}-point spread flips often -- treat it as a tilt, not a script.`);
  }} else if (shape === 'close') {{
    flow.push(`Close game on paper. Neither side should be forced into an extreme run/pass mix, so volume should look like each team's normal week.`);
  }}
  if (pace === 'high') flow.push(`The ${{total}} total is ${{gsR1(totalDelta)}} points above this season's average total (${{gsR1(base.totalLine)}}): the market expects a shootout -- more plays, more yards, more TDs on both sides.`);
  if (pace === 'low') flow.push(`The ${{total}} total is ${{gsR1(-totalDelta)}} points below this season's average total (${{gsR1(base.totalLine)}}): the market expects a grind -- fewer possessions, fewer yards and TDs.`);
  [A, H].forEach(P => {{
    if (P.passRate === null || lgPass === null) return;
    const d = P.passRate - lgPass;
    if (d >= 0.05) flow.push(`${{P.team}} is pass-heavy (${{gsPct(P.passRate)}} pass vs ${{gsPct(lgPass)}} league${{P.team === dog ? '; trailing should push it higher' : ''}}).`);
    else if (d <= -0.05) flow.push(`${{P.team}} is run-heavy (${{gsPct(P.passRate)}} pass vs ${{gsPct(lgPass)}} league${{P.team === fav ? '; a lead makes that even more likely' : ''}}).`);
  }});
  // Points check: recent scoring vs the market
  let statTotal = null;
  if (A.ppg !== null && H.ppg !== null && A.papg !== null && H.papg !== null) {{
    const pA = (A.ppg + H.papg) / 2, pH = (H.ppg + A.papg) / 2;
    statTotal = {{ [g.away]: pA, [g.home]: pH, sum: pA + pH }};
  }}

  // Matchup edges (rank 1 offense = produces the most; rank 1 defense = allows the least)
  const edges = [];
  const chk = (O, D, kind) => {{
    const oR = kind === 'pass' ? O.offPassRank : O.offRunRank, dR = kind === 'pass' ? D.defPassRank : D.defRunRank;
    if (!oR || !dR) return;
    const n = D.nDef, label = kind === 'pass' ? 'passing' : 'RB run game';
    const stat = kind === 'pass' ? 'QB pass yds' : 'RB rush yds';
    if (oR <= 10 && dR >= n - 9) edges.push({{ dir: 1, team: O.team, text: `${{O.team}} ${{label}} (#${{oR}} offense in ${{stat}}) vs a soft ${{D.team}} defense (#${{dR}} of ${{n}}) -- strength on weakness.` }});
    else if (oR >= O.nOff - 9 && dR <= 10) edges.push({{ dir: -1, team: O.team, text: `${{O.team}} ${{label}} (#${{oR}} offense in ${{stat}}) vs a tough ${{D.team}} defense (#${{dR}} of ${{n}}) -- weakness into strength.` }});
    else if (dR >= n - 5) edges.push({{ dir: 1, team: O.team, text: `${{D.team}} is one of the softest defenses vs ${{stat}} (#${{dR}} of ${{n}}).` }});
    else if (dR <= 5) edges.push({{ dir: -1, team: O.team, text: `${{D.team}} is one of the toughest defenses vs ${{stat}} (#${{dR}} of ${{n}}).` }});
  }};
  chk(A, H, 'pass'); chk(A, H, 'run'); chk(H, A, 'pass'); chk(H, A, 'run');

  const wx = gsWeather(g);
  const situ = [];
  if (g.away_rest !== null && g.home_rest !== null && g.away_rest !== undefined) {{
    const d = g.home_rest - g.away_rest;
    if (g.away_rest <= 4 && g.home_rest <= 4) situ.push(`Short week for both teams (${{g.away_rest}} days' rest).`);
    else if (Math.abs(d) >= 3) {{
      const more = d > 0 ? g.home : g.away, mr = Math.max(g.home_rest, g.away_rest);
      situ.push(`${{more}} has ${{Math.abs(d)}} more days of rest${{mr >= 13 ? ' (coming off a bye)' : ''}}.`);
    }} else situ.push(`Normal rest (${{g.away}}: ${{g.away_rest}} days, ${{g.home}}: ${{g.home_rest}}).`);
  }}
  if (g.div_game) situ.push('Divisional game -- the teams know each other well (our INT study found no measurable effect on its own).');
  const injA = gsInjNotes(g.away, g.home), injH = gsInjNotes(g.home, g.away);

  // Props this script points to
  const props = [];
  if (shape === 'lopsided') {{
    props.push({{ dir: 1, text: `${{dog}} pass volume Overs: QB attempts/completions, WR/TE receptions and targets.` }});
    props.push({{ dir: 1, text: `${{dog}} QB interceptions Over.` }});
    props.push({{ dir: 1, text: `${{fav}} RB carries / rush yards Overs.` }});
    props.push({{ dir: -1, text: `${{fav}} QB pass attempts Under (may not need to throw late); ${{dog}} RB rushing Unders (big underdogs abandon the run).` }});
  }} else if (shape === 'lean') {{
    props.push({{ dir: 1, text: `Mild tilt: ${{dog}} pass volume and ${{fav}} RB carries on the Over side.` }});
  }}
  if (pace === 'high') props.push({{ dir: 1, text: 'High total: passing/receiving yards and anytime-TD Overs on both sides.' }});
  if (pace === 'low') props.push({{ dir: -1, text: 'Low total: yardage and TD Unders on both sides.' }});
  if (implied) [g.away, g.home].forEach(t => {{
    if (implied[t] >= 27) props.push({{ dir: 1, text: `${{t}} implied for ${{gsR1(implied[t])}} points -- ${{t}} TD scorers and passing TDs.` }});
    if (implied[t] <= 17) props.push({{ dir: -1, text: `${{t}} implied for only ${{gsR1(implied[t])}} points -- ${{t}} TD and yardage Unders.` }});
  }});
  if (wx.bad) props.push({{ dir: -1, text: 'Weather: passing/receiving Unders, kicking down.' }});
  if (statTotal && total) {{
    const d = statTotal.sum - total;
    if (Math.abs(d) >= 4) props.push({{ dir: d > 0 ? 1 : -1, text: `Scoring so far points ${{d > 0 ? 'Over' : 'Under'}}: each offense's points vs the other defense's points allowed averages to ~${{gsR1(statTotal.sum)}} vs the ${{total}} total (small sample).` }});
  }}
  return {{ g, weeks, base, A, H, fav, dog, mag, sp, total, implied, pHome, totalDelta, pace, shape, headline, flow, statTotal, edges, wx, situ, injA, injH, props, lgPass, prof }};
}}

function gsBoardRows(key) {{
  const defCache = {{}};
  return ROWS.filter(r => gameKey(r) === key).map(r => enrichRow(r, selectedWeeks, defCache))
    .filter(e => e.hot_level > 0 || e.cold_level > 0 || e.needs_review)
    .sort((a, b) => (b.signal_rank || 0) - (a.signal_rank || 0)).slice(0, 18);
}}
function gsDirClass(d) {{ return d > 0 ? 'gs-good' : d < 0 ? 'gs-bad' : ''; }}
function gsList(items) {{
  if (!items.length) return '<div class="muted">Nothing notable.</div>';
  return '<ul class="gs-list">' + items.map(x => `<li class="${{gsDirClass(x.dir)}}">${{x.text}}</li>`).join('') + '</ul>';
}}
function gsRank(r, n) {{ return r ? `<span class="muted">#${{r}}</span>` : ''; }}

function gameScriptHtml(key) {{
  const s = gameScript(key);
  if (!s) return '<div class="muted">No game data for this matchup.</div>';
  const g = s.g, A = s.A, H = s.H;
  const chips = [];
  chips.push(`<span class="gs-chip">${{escapeHtml(formatGameLabel(g))}}</span>`);
  if (s.sp !== null && s.sp !== undefined) chips.push(`<span class="gs-chip">Spread: ${{s.fav ? s.fav + ' -' + s.mag : 'pick-em'}}</span>`);
  if (s.total !== null && s.total !== undefined) chips.push(`<span class="gs-chip">Total ${{s.total}}${{s.totalDelta !== null ? ` <span class="muted">(${{gsSigned(s.totalDelta)}} vs avg)</span>` : ''}}</span>`);
  if (s.implied) chips.push(`<span class="gs-chip">Implied: ${{g.away}} ${{gsR1(s.implied[g.away])}} &middot; ${{g.home}} ${{gsR1(s.implied[g.home])}}</span>`);
  if (s.pHome !== null) chips.push(`<span class="gs-chip">Win prob: ${{g.away}} ${{gsPct(1 - s.pHome)}} &middot; ${{g.home}} ${{gsPct(s.pHome)}}</span>`);

  const row = (label, fa, fh, title) => `<tr${{title ? ` title="${{escapeHtml(title)}}"` : ''}}><td class="muted">${{label}}</td><td>${{fa}}</td><td>${{fh}}</td></tr>`;
  const rec = (P) => P.res.length ? `${{P.w}}-${{P.l}}${{P.t ? '-' + P.t : ''}}` : '-';
  const ats = (P) => P.res.length ? `${{P.atsW}}-${{P.atsL}}${{P.atsP ? '-' + P.atsP : ''}}` : '-';
  const ou = (P) => P.res.length ? `${{P.ouO}}-${{P.ouU}}${{P.ouP ? '-' + P.ouP : ''}}` : '-';
  const cov = (t) => {{ const c = COVERAGE[t]; if (!c || c.man_rate === null || c.man_rate === undefined) return '-'; const tier = coverageTier(c.zone_rate); return `${{c.man_rate}}% man${{tier ? ' <span class="cov-tag ' + tier.cls + '">' + tier.label + '</span>' : ''}}`; }};
  const rest = (t) => {{ const v = t === g.home ? g.home_rest : g.away_rest; return v === null || v === undefined ? '-' : v + ' days'; }};
  const tbl = `<table class="modal-table gs-table"><thead><tr><th>${{escapeHtml(weeksLabel(s.weeks))}}</th><th>${{g.away}} (away)</th><th>${{g.home}} (home)</th></tr></thead><tbody>`
    + row('Record', rec(A), rec(H))
    + row('Against the spread', ats(A), ats(H), "Covered-lost(-push) vs each game's closing spread")
    + row('Overs-Unders', ou(A), ou(H), 'Games that went over-under the closing total')
    + row('Points for / against', `${{gsR1(A.ppg)}} / ${{gsR1(A.papg)}}`, `${{gsR1(H.ppg)}} / ${{gsR1(H.papg)}}`)
    + row('Avg margin', gsSigned(A.margin), gsSigned(H.margin))
    + row('Pass attempts / game', `${{gsR1(A.passAtt)}} ${{gsRank(A.offAttRank)}}`, `${{gsR1(H.passAtt)}} ${{gsRank(H.offAttRank)}}`, '#N = rank among offenses, 1 = most')
    + row('QB pass yds / game', `${{gsR1(A.passYds)}} ${{gsRank(A.offPassRank)}}`, `${{gsR1(H.passYds)}} ${{gsRank(H.offPassRank)}}`, '#N = rank among offenses, 1 = most')
    + row('RB carries / game', gsR1(A.rbCar), gsR1(H.rbCar))
    + row('RB rush yds / game', `${{gsR1(A.rbYds)}} ${{gsRank(A.offRunRank)}}`, `${{gsR1(H.rbYds)}} ${{gsRank(H.offRunRank)}}`, '#N = rank among offenses, 1 = most')
    + row('QB rush yds / game', gsR1(A.qbRush), gsR1(H.qbRush))
    + row('Pass rate', gsPct(A.passRate), gsPct(H.passRate), 'QB pass attempts / (attempts + RB carries); QB scrambles not counted. League: ' + gsPct(s.lgPass))
    + row('Defense: QB pass yds allowed', `${{gsR1(A.defPass)}} ${{gsRank(A.defPassRank)}}`, `${{gsR1(H.defPass)}} ${{gsRank(H.defPassRank)}}`, '#N = rank among defenses, 1 = allows the least')
    + row('Defense: RB rush yds allowed', `${{gsR1(A.defRun)}} ${{gsRank(A.defRunRank)}}`, `${{gsR1(H.defRun)}} ${{gsRank(H.defRunRank)}}`, '#N = rank among defenses, 1 = allows the least')
    + row('Coverage (season)', cov(g.away), cov(g.home))
    + row('Rest', rest(g.away), rest(g.home))
    + '</tbody></table>';

  const injBlock = (team, I) => {{
    if (!I.list.length) return `<div class="muted">${{team}}: no 40%+ snap players on the report${{INJ_BY_TEAM[team] ? '' : ' (report not out yet)'}}.</div>`;
    return `<div><strong>${{team}}</strong>: ` + I.list.map(p => `<span class="cov-tag ${{p.severity >= 3 ? 'injury-out' : 'cov-lowman'}}" title="${{escapeHtml((p.injury || '') + ' · ' + Math.round((p.snap_pct || 0) * 100) + '% snaps · ' + (p.source || ''))}}">${{escapeHtml(p.position + ' ' + p.name + ' · ' + p.status)}}</span>`).join(' ') + '</div>';
  }};
  const injNotes = s.injA.notes.concat(s.injH.notes);

  const board = gsBoardRows(key);
  const boardHtml = board.length ? `<table class="modal-table gs-table"><thead><tr><th>Player</th><th>Stat</th><th>Side</th><th>Signal</th><th>Script</th><th>Mark</th></tr></thead><tbody>`
    + board.map(e => {{
      const side = e.hot_level > 0 ? 'Over' : e.cold_level > 0 ? 'Under' : (e.tiebreak ? (e.tiebreak.lean === 'over' ? 'Over' : 'Under') : '-');
      const line = e.tiebreak && e.tiebreak.line !== undefined ? e.tiebreak.line : e.vegas_line;
      return `<tr><td>${{gsPlayerLink(e.player)}} <span class="muted">${{e.team}}</span></td><td>${{escapeHtml(e.stat_label)}}</td><td>${{side}} ${{line === null || line === undefined ? '' : line}}</td><td>${{signalEmoji(e)}}</td><td>${{scriptTag(e) || '<span class="muted">-</span>'}}</td><td>${{MARK_EMOJI[MARKS[markKey(e)]] || ''}}</td></tr>`;
    }}).join('') + '</tbody></table>' : '<div class="muted">No signalled rows in this game for the selected weeks.</div>';

  const myBets = allBets().filter(x => !x.manual && x.week === WEEK && x.b.meta && (x.b.meta.team === g.home || x.b.meta.team === g.away));
  const betsHtml = myBets.length ? '<ul class="gs-list">' + myBets.map(x => {{
    const b = x.b;
    return `<li>${{escapeHtml(betTitle(x))}} -- ${{b.side ? (b.side === 'over' ? 'Over' : 'Under') : '?'}} ${{escapeHtml(b.line || '')}}${{b.odds ? ' (' + escapeHtml(b.odds) + ')' : ''}}${{b.stake ? ' · $' + escapeHtml(b.stake) : ''}}</li>`;
  }}).join('') + '</ul>' : '<div class="muted">None yet.</div>';

  const resLine = (P) => P.res.length ? P.res.map(x => `<span class="gs-res ${{x.margin > 0 ? 'gs-good' : x.margin < 0 ? 'gs-bad' : ''}}" title="${{escapeHtml(`Closing line: ${{x.sp === null ? '-' : (x.sp > 0 ? P.team + ' -' + x.sp : x.sp < 0 ? P.team + ' +' + (-x.sp) : 'pick-em')}}, total ${{x.line === null ? '-' : x.line}}${{x.ot ? ' · OT' : ''}}`)}}">Wk${{x.week}} ${{x.home ? 'vs' : '@'}} ${{x.opp}} ${{x.margin > 0 ? 'W' : x.margin < 0 ? 'L' : 'T'}} ${{x.pf}}-${{x.pa}} <span class="muted">${{x.ats ? 'ATS ' + x.ats : ''}}${{x.ou ? ' · ' + x.ou : ''}}</span></span>`).join(' ') : '<span class="muted">No games in the selected weeks.</span>';

  return `<div class="gs-wrap">
    <div class="gs-headline">${{escapeHtml(s.headline)}}</div>
    <div class="gs-chips">${{chips.join('')}}</div>
    <div class="gs-grid">
      <div>
        <div class="modal-section-title">How the game should flow</div>
        ${{s.flow.length ? s.flow.map(t => `<p class="gs-p">${{t}}</p>`).join('') : '<p class="gs-p muted">No spread/total posted yet.</p>'}}
        ${{s.statTotal ? `<p class="gs-p muted">Scoring check (${{escapeHtml(weeksLabel(s.weeks))}}): ${{g.away}} ~${{gsR1(s.statTotal[g.away])}}, ${{g.home}} ~${{gsR1(s.statTotal[g.home])}} = ~${{gsR1(s.statTotal.sum)}} vs the ${{s.total}} total. Each team's points scored averaged with the other's points allowed -- a rough, small-sample check on the market.</p>` : ''}}
        <div class="modal-section-title">Props this script points to</div>
        ${{gsList(s.props)}}
        <div class="modal-section-title">Matchups</div>
        ${{gsList(s.edges)}}
      </div>
      <div>
        <div class="modal-section-title">Weather &amp; situation</div>
        <p class="gs-p">${{s.wx.text}}</p>
        ${{s.wx.notes.length ? gsList(s.wx.notes) : ''}}
        ${{s.situ.map(t => `<p class="gs-p">${{t}}</p>`).join('')}}
        <div class="modal-section-title">Injuries (40%+ snap players)</div>
        ${{injBlock(g.away, s.injA)}}
        ${{injBlock(g.home, s.injH)}}
        ${{injNotes.length ? gsList(injNotes) : ''}}
      </div>
    </div>
    <div class="modal-section-title">Team profiles</div>
    <div class="modal-table-wrap">${{tbl}}</div>
    <div class="gs-results"><div><strong>${{g.away}}</strong>: ${{resLine(A)}}</div><div><strong>${{g.home}}</strong>: ${{resLine(H)}}</div></div>
    <div class="modal-section-title">On the board in this game</div>
    <div class="modal-table-wrap">${{boardHtml}}</div>
    <div class="modal-section-title">Your bets in this game</div>
    ${{betsHtml}}
    <div class="modal-note" style="margin-top:12px;">Context, not a pick. Green = favors the Over / that offense, red = favors the Under / against it. Lines from nflverse's schedule (refreshed with fetch_stats.py); team stats use ${{escapeHtml(weeksLabel(s.weeks))}}. In the Week 3 backtest, game script was the only checklist factor that beat a coin flip (58%), on a small sample.</div>
  </div>`;
}}

function renderGameScriptPanel() {{
  const panel = document.getElementById('gameScriptPanel');
  if (!panel) return;
  if (activeGame === 'ALL' || !gsGame(activeGame)) {{ panel.style.display = 'none'; panel.innerHTML = ''; return; }}
  const g = gsGame(activeGame);
  panel.innerHTML = `<details id="gsDetails"${{gsPanelOpen ? ' open' : ''}}><summary>&#127916; Game script: ${{g.away}} @ ${{g.home}}</summary>${{gameScriptHtml(activeGame)}}</details>`;
  panel.style.display = 'block';
}}

let gsFromBets = false;
function openGameScriptModal(key) {{
  const g = gsGame(key);
  if (!g) return;
  gsFromBets = myBetsOpen;
  myBetsOpen = false;
  currentModalPlayer = null;
  currentModalDefenseTeam = null;
  document.querySelector('#playerModalOverlay .modal-panel').style.maxWidth = '1180px';
  document.getElementById('modalPlayerName').textContent = 'Game script: ' + g.away + ' @ ' + g.home;
  document.getElementById('modalMeta').innerHTML = (gsFromBets ? '<button type="button" class="weeks-mini-btn gs-back">&larr; Back to My Bets</button>  ' : '')
    + escapeHtml(formatGameLabel(g)) + '  &middot;  Team stats: ' + escapeHtml(weeksLabel(gsPlayedWeeks(selectedWeeks)));
  document.getElementById('modalBody').innerHTML = gameScriptHtml(key);
  document.getElementById('playerModalOverlay').style.display = 'flex';
  const sc = document.querySelector('#playerModalOverlay .modal-panel');
  if (sc) sc.scrollTop = 0;
}}
function gsLinkForTeam(team, week, text) {{
  if (week !== WEEK) return '';
  const g = GAMES.find(x => x.home === team || x.away === team);
  return g ? `<a class="gs-link" data-game="${{g.key}}" title="Game script: ${{g.away}} @ ${{g.home}}">&#127916;${{text ? ' ' + text : ''}}</a>` : '';
}}
function gsLinkHtml(r, text) {{
  const k = gameKey(r);
  if (!gsGame(k)) return '';
  return `<a class="gs-link" data-game="${{k}}" title="Game script: ${{k.replace('@', ' @ ')}}">&#127916;${{text ? ' ' + text : ''}}</a>`;
}}
document.addEventListener('click', (e) => {{
  const a = e.target.closest('.gs-link');
  if (a) {{ e.preventDefault(); e.stopPropagation(); openGameScriptModal(a.dataset.game); return; }}
  if (e.target.closest('.gs-back')) {{ openMyBetsModal(); return; }}
  const p = e.target.closest('.gs-player');
  if (p) {{ openPlayerModal(p.dataset.player); }}
}});
document.getElementById('gameScriptPanel').addEventListener('toggle', (e) => {{
  if (e.target.id === 'gsDetails') gsPanelOpen = e.target.open;
}}, true);

// ---- Resizable + draggable columns (added 2026-10-07, per Trevor: "can you
// make the columns resizeable width as well as draggable to move them
// around?"). Drag a header to move the column; drag the thin handle on a
// header's right edge to resize it. Both are remembered in this browser
// (localStorage) and survive rebuilds; "Reset columns" puts them back.
// Rows are rendered in the original column order and re-arranged after
// every render(), so nothing else in the page needs to know the order.
var COLS_KEY = 'nfl_prop_dashboard_cols_v1';
var colState = {{ order: null, widths: {{}} }};
try {{
  const saved = JSON.parse(localStorage.getItem(COLS_KEY) || 'null');
  if (saved && typeof saved === 'object') colState = Object.assign(colState, saved);
}} catch (e) {{}}
var _colStyle = document.createElement('style');
document.head.appendChild(_colStyle);
var _suppressSortClick = false;
var _dragCol = null;
function colHeaderRow() {{ return document.querySelector('#tbl thead tr'); }}
function saveCols() {{ try {{ localStorage.setItem(COLS_KEY, JSON.stringify(colState)); }} catch (e) {{}} }}
function suppressSortBriefly() {{ _suppressSortClick = true; setTimeout(() => {{ _suppressSortClick = false; }}, 150); }}
function applyColumnWidths() {{
  const order = colState.order || [];
  let css = '';
  order.forEach((c, pos) => {{
    const w = colState.widths[c];
    if (!w) return;
    const n = pos + 1;
    css += `#tbl thead th:nth-child(${{n}}), #tbl tbody td:nth-child(${{n}}) {{ width:${{w}}px; min-width:${{w}}px; max-width:${{w}}px; overflow:hidden; text-overflow:ellipsis; }} `;
  }});
  _colStyle.textContent = css;
}}
function applyColumnLayout() {{
  const headTr = colHeaderRow();
  if (!headTr || !colState.order) return;
  const byCol = {{}};
  for (const th of headTr.children) byCol[th.dataset.col] = th;
  colState.order.forEach(c => {{ if (byCol[c]) headTr.appendChild(byCol[c]); }});
  const n = colState.order.length;
  for (const tr of document.querySelectorAll('#tbody tr')) {{
    const cells = Array.from(tr.children);
    if (cells.length !== n) continue; // e.g. a "no rows" message row
    colState.order.forEach(c => tr.appendChild(cells[c]));
  }}
  applyColumnWidths();
}}
function startColResize(e) {{
  e.preventDefault();
  e.stopPropagation();
  const th = e.target.closest('th');
  const startX = e.clientX;
  const startW = th.getBoundingClientRect().width;
  const col = th.dataset.col;
  document.body.classList.add('col-resizing');
  const move = (ev) => {{
    colState.widths[col] = Math.max(36, Math.round(startW + ev.clientX - startX));
    applyColumnWidths();
  }};
  const up = () => {{
    document.removeEventListener('mousemove', move);
    document.removeEventListener('mouseup', up);
    document.body.classList.remove('col-resizing');
    saveCols();
    suppressSortBriefly();
  }};
  document.addEventListener('mousemove', move);
  document.addEventListener('mouseup', up);
}}
function initColumns() {{
  const headTr = colHeaderRow();
  if (!headTr) return;
  const ths = Array.from(headTr.children);
  ths.forEach((th, i) => {{ th.dataset.col = String(i); }});
  const n = ths.length;
  const ok = Array.isArray(colState.order) && colState.order.length === n &&
    new Set(colState.order).size === n && colState.order.every(c => c >= 0 && c < n);
  if (!ok) {{ colState.order = ths.map((_, i) => i); colState.widths = {{}}; }}
  for (const th of ths) {{
    th.draggable = true;
    const h = document.createElement('span');
    h.className = 'col-resize';
    h.title = 'Drag to resize';
    h.addEventListener('mousedown', startColResize);
    h.addEventListener('click', (e) => e.stopPropagation());
    th.appendChild(h);
    th.addEventListener('dragstart', (e) => {{
      if (document.body.classList.contains('col-resizing')) {{ e.preventDefault(); return; }}
      _dragCol = parseInt(th.dataset.col, 10);
      th.classList.add('col-dragging');
      try {{ e.dataTransfer.setData('text/plain', th.dataset.col); e.dataTransfer.effectAllowed = 'move'; }} catch (err) {{}}
    }});
    th.addEventListener('dragover', (e) => {{
      if (_dragCol === null) return;
      e.preventDefault();
      const r = th.getBoundingClientRect();
      const before = e.clientX < r.left + r.width / 2;
      th.classList.toggle('col-drop-before', before);
      th.classList.toggle('col-drop-after', !before);
    }});
    th.addEventListener('dragleave', () => th.classList.remove('col-drop-before', 'col-drop-after'));
    th.addEventListener('drop', (e) => {{
      e.preventDefault();
      const target = parseInt(th.dataset.col, 10);
      const before = th.classList.contains('col-drop-before');
      th.classList.remove('col-drop-before', 'col-drop-after');
      if (_dragCol === null || _dragCol === target) return;
      const order = colState.order.filter(c => c !== _dragCol);
      let idx = order.indexOf(target);
      if (!before) idx += 1;
      order.splice(idx, 0, _dragCol);
      colState.order = order;
      saveCols();
      suppressSortBriefly();
      render();
    }});
    th.addEventListener('dragend', () => {{
      _dragCol = null;
      document.querySelectorAll('#tbl thead th').forEach(x => x.classList.remove('col-dragging', 'col-drop-before', 'col-drop-after'));
      suppressSortBriefly();
    }});
  }}
  const reset = document.getElementById('resetColsBtn');
  if (reset) reset.addEventListener('click', () => {{
    colState = {{ order: ths.map((_, i) => i), widths: {{}} }};
    saveCols();
    render();
  }});
}}

initColumns();
document.addEventListener('click', (e) => {{
  const b = e.target.closest && e.target.closest('#roleFlagBtn');
  if (!b) return;
  const k = b.dataset.roleKey;
  if (MARKS[k] === 'flux') delete MARKS[k]; else MARKS[k] = 'flux';
  saveMarks();
  render();
  if (currentModalPlayer) openPlayerModal(currentModalPlayer);
}});

// Show UTC timestamps (e.g. the injuries note) in the viewer's own time.
document.querySelectorAll('.local-time[data-utc]').forEach(el => {{
  const t = new Date(el.dataset.utc);
  if (!isNaN(t)) el.textContent = t.toLocaleString([], {{ weekday: 'short', hour: 'numeric', minute: '2-digit' }});
}});

// ---- 📜 My rules (added 2026-10-16, per Trevor: "make a 'my rules' section
// so I can see specific things we've programmed"). Plain-English list of
// every rule the board applies; numbers come from the live constants, so
// this can't drift from what the page actually does.
function myRulesHtml() {{
  const n = RULE_NUMS;
  const li = s => `<li style="margin:3px 0;">${{s}}</li>`;
  const sec = (title, items) => `<h3 class="modal-section-title">${{title}}</h3><ul style="margin:4px 0 10px 18px; padding:0;">${{items.map(li).join('')}}</ul>`;
  return sec('The groups', [
      '<b>&#11088; MUST BET</b> -- bet it. He cleared the line in every game and the defense allowed it in every game (' + CONS_MUST_MIN_GAMES + '+ games each), against one of the ' + MUST_BET_MATCHUP_TOP + ' defenses allowing the most (Over) / least (Under) of that stat.',
      '<b>&#128293;&#128293;&#128293; / &#129482;&#129482;&#129482;</b> -- review it. He cleared it every game, the defense allowed it ' + Math.round(CONS_TIERS[1] * 100) + '%+ of the time, top-' + MUST_BET_MATCHUP_TOP + ' matchup.',
      '<b>&#128161;</b> -- worth a closer look: would have been a 2-star (defense ' + Math.round(CONS_TIERS[0] * 100) + '%+), the 🎬 game script backs it, it faces a 🎯 outlier defense on its side, or a backup RB with blowout upside.',
      '<b>🎯 Outlier defense:</b> one of the ' + OUTLIER_DEF_TOP + ' defenses allowing the most (or least) for the whole season, for RB Rush Yds and WR/TE Receptions only (where it held up in 2019-2025 tests). Shown as 🎯 O / 🎯 U next to the player name; turns a ❓ on that side into 💡, never a 3-star. If the line also looks off for that matchup (Anticipated ' + Math.round((OUTLIER_VALUE_RATIO - 1) * 100) + '%+ past it), even a row with no signal becomes 💡.',
      '<b>⬆ Alt line idea (Overs only -- books don\u2019t offer alt Unders):</b> when Anticipated is ' + Math.round((ALT_PROJ_RATIO - 1) * 100) + '%+ past the line, the furthest alt line (steps of 5 yards or 1 catch/carry) short of the projection that he cleared in ' + Math.round(ALT_HIT_RATE * 100) + '%+ of the selected games. A number to look up -- alt odds aren\u2019t pulled, so check the price. The \u2b06 Alt lines only box shows just these.',
      '<b>&#10067;</b> -- everything else worth a glance. Hover any ❓ for exactly why it isn’t a pick.',
    ])
    + sec('What counts', [
      'Weeks: the last ' + DEFAULT_LAST_WEEKS + ' played weeks by default (Last 2 / Last 4 / All played buttons). Signals follow whatever weeks are selected; MUST BET always needs ' + CONS_MUST_MIN_GAMES + '+ games.',
      'Price: a price worse than ' + MAX_JUICE_PRICE + ' blocks a pick.',
      'His misses don’t count against one of the ' + EXCUSE_TOUGH_TOP + ' toughest defenses for that stat (softest, for an Under).',
      'A defense’s miss doesn’t count against an offense that usually gets under ' + Math.round(EXCUSE_OFF_RATIO * 100) + '% of the line (Over) -- "no fair test" when every game is excused.',
      'Excusing only kicks in when enough games are left; MUST BET still needs a clean record with nothing excused.',
    ])
    + sec('Turns a pick into a ❓', [
      '<b>Matchup mismatch:</b> an Under against a top-' + MISMATCH_OFF_TOP + ' offense needs the defense to have held every top-half offense it faced at or below their usual (an Over against a bottom-' + MISMATCH_OFF_TOP + ' offense: the mirror). Untested also counts.',
      '<b>Role change:</b> a teammate with a real role (' + Math.round(n.impact_snap * 100) + '%+ snaps, or ' + Math.round(n.rb_carry_share * 100) + '%+ of team RB carries) at QB/RB/WR/TE is Out or Doubtful (NFL report + ESPN news); a trade involving a real-role player at his position (until ' + n.trade_settle + ' games after); or your own ⚠️ flag.',
      '<b>Blowout, lead back:</b> his team favored by ' + BLOWOUT_FAV + '+ -- no Rush Yds / Rush Attempts Overs for the team’s lead RB.',
      '<b>Blowout, backup:</b> his team favored by ' + BLOWOUT_FAV + '+ -- no rush Unders on the backup RB (he gets the late carries); his rush Overs get a 💡 instead.',
      '<b>Heads-up only (doesn’t block):</b> a real-role teammate Questionable or who missed practice -- faded ⚠️.',
    ])
    + sec('Alerts', [
      'NEW: MUST BETs and 3-stars you haven’t been sent and haven’t marked.',
      'WATCHING: every 🌕 row, buzzing only when a line moves or the price moves 10+ cents.',
      '💡 and ❓ rows are never alerted.',
    ])
    + '<div class="modal-note">Rules change only when you ask. The full history of every decision is in the repo’s docs/HISTORY.md.</div>';
}}
function openMyRulesModal() {{
  closePlayerModal();
  document.querySelector('#playerModalOverlay .modal-panel').style.maxWidth = '820px';
  document.getElementById('modalPlayerName').textContent = '📜 My rules';
  document.getElementById('modalMeta').innerHTML = 'Everything the board applies when it picks, in plain words.';
  document.getElementById('modalBody').innerHTML = myRulesHtml();
  document.getElementById('playerModalOverlay').style.display = 'flex';
}}
document.getElementById('myRulesBtn').addEventListener('click', openMyRulesModal);
// Backup RB's carries in his team's blowout wins (17+), for the 💡 hover.
function blowoutGamesText(r) {{
  const out = [];
  (r.game_weeks || []).forEach((w, i) => {{
    const g = TEAM_RESULTS.find(t => t.week === w && (t.home === r.team || t.away === r.team));
    if (!g || g.home_score === null) return;
    const team = r.team;
    const m = team === g.home ? g.home_score - g.away_score : g.away_score - g.home_score;
    if (m >= 17) out.push(`${{Math.round(r.game_log[i] * 10) / 10}} in Wk${{w}} (won by ${{m}})`);
  }});
  return out.length ? ` His ${{r.stat_label}} in his team’s blowout wins: ${{out.join(', ')}}.` : '';
}}

render();
initSync();
</script>
</body>
</html>
"""


def ordered_stat_labels():
    """Unique stat labels in a sensible display order (QB stats first, etc.),
    de-duplicated across positions (e.g. "Receptions" is shared by RB/WR/TE)."""
    seen = []
    for pos in ("QB", "RB", "WR", "TE"):
        for _, _, label in STAT_MARKET_MAP.get(pos, []):
            if label not in seen:
                seen.append(label)
    return seen


def odds_time_utc(odds):
    """The odds pull time as UTC ISO. generated_at is naive local time (the
    workflow runs with TZ=America/Denver), so it's read as this machine's zone."""
    try:
        from datetime import timezone
        return datetime.fromisoformat(odds["generated_at"]).astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def main():
    stats, odds, weather, coverage, injuries, injuries_by_team = load_caches()
    odds_lookup = build_odds_lookup(odds)
    rows = build_rows(stats, odds_lookup, weather, injuries, injuries_by_team)

    no_odds_note = ""
    if odds is None:
        no_odds_note = (
            '<div class="no-odds-note">No odds data found yet - run fetch_odds.py '
            "to add Vegas lines, edge, and hit-rate columns.</div>"
        )

    stat_buttons = "".join(
        f'<button class="stat-btn" data-stat="{label}">{label}</button>'
        for label in ordered_stat_labels()
    )
    defense_logs = build_defense_logs(stats)
    defense_games = stats.get("defense_allowed_games", {})
    games_list = build_games_list(stats, weather)
    # {pos: [[stat_col, display_label], ...]} -- lets the JS-side defense
    # modal iterate every stat category for a position without needing the
    # Odds API market key (irrelevant there), just the raw column + label.
    stat_catalog = {
        pos: [[col, label] for col, _, label in entries]
        for pos, entries in STAT_MARKET_MAP.items()
    }

    html = HTML_TEMPLATE.format(
        season=stats["season"],
        week=stats["week"],
        stats_time=stats["generated_at"],
        injuries_meta=injuries_meta_html(),
        odds_time=odds["generated_at"] if odds else "not fetched",
        odds_time_utc=odds_time_utc(odds),
        no_odds_note=no_odds_note,
        stat_buttons=stat_buttons,
        rows_json=json.dumps(rows),
        defense_logs_json=json.dumps(defense_logs),
        defense_games_json=json.dumps(defense_games),
        stat_catalog_json=json.dumps(stat_catalog),
        coverage_json=json.dumps(coverage),
        games_json=json.dumps(games_list),
        team_results_json=json.dumps(stats.get("team_results", [])),
        injuries_by_team_json=json.dumps(injuries_by_team),
        board_switch_html=board_switch_html(),
        rule_nums_json=json.dumps({"impact_snap": IMPACT_SNAP_PCT, "rb_carry_share": RB_CARRY_SHARE_ROLE, "trade_settle": TRADE_SETTLE_GAMES}),
        supabase_config_json=json.dumps(
            {"url": SUPABASE_URL, "key": SUPABASE_ANON_KEY} if SUPABASE_URL and SUPABASE_ANON_KEY else None
        ),
    )

    import os
    out_path = OUTPUT_DIR / (os.environ.get("NFL_OUTPUT_NAME") or "dashboard.html")
    out_path.write_text(html)
    print(f"Built dashboard with {len(rows)} rows: {out_path}")
    print("Open it in your browser to view.")


if __name__ == "__main__":
    main()
