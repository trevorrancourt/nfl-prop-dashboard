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

--- ESPN injury feed (added 2026-10-16) ---
The official report is slow: game designations only exist once a team's
final report is out (Friday for Sunday), and nflverse posts them later
still. Trevor: "jeremiyah love is out this week and tyler allgeier is a
must bet under" -- Love only showed as "Missed practice", so nothing
blocked. "i think we just need faster injury updates."

So after the nflverse report, ESPN's public injury feed (ESPN_URL, same
data behind espn.com/nfl/injuries, updated within hours of team news) is
merged in. Players are joined on ESPN athlete id via nflverse's
players.csv crosswalk (espn_id), falling back to name + team. For each
player the MORE SEVERE status wins (Injured Reserve / PUP / suspension
count as Out), with source "espn" and ESPN's short note. Guard: an
ESPN-only entry for a player who hasn't played in either of the last two
played weeks is skipped -- he's been out a while, so it's already baked
into his teammates' recent numbers (otherwise every long-term IR player
would set off role-change flags forever). If ESPN can't be reached the
build goes on with the official report alone (cache "espn": false).
"""

import io
import json
import os
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
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"

# ESPN status text -> our status. Anything else (e.g. "Active") is ignored.
ESPN_STATUS = {
    "out": "Out", "injured reserve": "Out", "ir": "Out", "physically unable to perform": "Out",
    "pup": "Out", "suspension": "Out", "suspended": "Out", "non-football injury": "Out",
    "doubtful": "Doubtful", "questionable": "Questionable", "day-to-day": "Questionable",
}

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


def load_crosswalk():
    """nflverse players.csv -- gsis/pfr/espn ids, names, positions. None if
    the download fails."""
    try:
        return fetch_csv(PLAYERS_URL, timeout=120)
    except Exception as e:
        print(f"WARNING: couldn't load players.csv ({e}).", file=sys.stderr)
        return None


def load_snap_shares(season, crosswalk=None):
    """{gsis_id: {"offense": avg_pct, "defense": avg_pct}} -- average snap
    share over the games this season where the player took at least one
    snap in that unit. Returns {} (and prints a warning) if either
    download fails, so injuries still get cached; they just won't pass
    the impact filter until snap data is available."""
    try:
        snaps = fetch_csv(SNAP_COUNTS_URL.format(season=season))
        players = (crosswalk if crosswalk is not None else fetch_csv(PLAYERS_URL, timeout=120))[["gsis_id", "pfr_id"]]
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


def norm_name(n):
    import re
    n = re.sub(r"[.'\u2019]", "", str(n).lower())
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", n)
    return " ".join(n.split())


# ESPN's status field can lag its own news note ("X has been ruled out" while
# still listed Questionable), so the note is read too.
NEWS_OUT = ("ruled out", "won't play", "will not play", "will miss", "is out for", "out for sunday",
            "out for monday", "out for thursday", "out for saturday", "not expected to play", "has been placed on")
NEWS_DOUBTFUL = ("doubtful",)


def status_from_news(note):
    n = (note or "").lower()
    if any(k in n for k in NEWS_OUT):
        return "Out"
    if any(k in n for k in NEWS_DOUBTFUL):
        return "Doubtful"
    return None


def fetch_espn_injuries():
    """[{espn_id, name, team (abbr), position, status, injury, note, date}]
    from ESPN's public feed. Raises on network/format trouble."""
    import re
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from team_mapping import FULL_TO_ABBR
    resp = requests.get(ESPN_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    out = []
    for team_block in data.get("injuries", []):
        team_full = team_block.get("displayName") or ""
        for item in team_block.get("injuries", []):
            ath = item.get("athlete") or {}
            status = ESPN_STATUS.get(str(item.get("status") or (item.get("type") or {}).get("description") or "").strip().lower())
            if not status:
                continue
            espn_id = str(ath.get("id") or "")
            if not espn_id:
                for link in ath.get("links") or []:
                    m = re.search(r"/id/(\d+)", link.get("href", ""))
                    if m:
                        espn_id = m.group(1)
                        break
            team = ((ath.get("team") or {}).get("abbreviation")) or FULL_TO_ABBR.get(team_full, "")
            team = {"WSH": "WAS", "LAR": "LA", "JAC": "JAX"}.get(team, team)
            details = item.get("details") or {}
            note = " ".join(x for x in (item.get("shortComment"), item.get("longComment")) if x)
            news = status_from_news(note)
            if news and STATUS_SEVERITY[news] > STATUS_SEVERITY[status]:
                status = news  # the news note is ahead of ESPN's status field
            out.append({
                "espn_id": espn_id,
                "name": ath.get("displayName") or "",
                "team": team,
                "position": ((ath.get("position") or {}).get("abbreviation")) or "",
                "status": status,
                "injury": details.get("type") or None,
                "note": (item.get("shortComment") or "").strip()[:200] or None,
                "date": item.get("date"),
            })
    if not out:
        blocks = data.get("injuries") or []
        first = (blocks[0].get("injuries") or [None])[0] if blocks and isinstance(blocks[0], dict) else None
        raise ValueError(f"no usable entries; top keys={list(data)[:10]}, blocks={len(blocks)}, "
                         f"sample={json.dumps(first)[:600] if first else None}")
    return out


def recently_played(week):
    """{gsis_id} of players with a game in either of the last two played
    weeks, from stats_cache.json."""
    stats = json.loads((DATA_DIR / "stats_cache.json").read_text())
    recent = {int(week) - 1, int(week) - 2}
    return {pid for pid, p in stats.get("players", {}).items()
            if any(g.get("week") in recent for g in p.get("recent_games", []))}


def gh_notice(title, lines):
    """One GitHub Actions annotation (readable on the run page, and by Claude
    through the API when the logs aren't), so the ESPN step can be checked
    from outside. Plain print anywhere else."""
    msg = "; ".join(str(x) for x in lines)[:30000]
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title={title}::" + msg.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))
    else:
        print(f"{title}: {msg}")


def position_of(e, info):
    return (e.get("position") or info.get("position") or "").strip()


def merge_espn(players, by_team, snap_shares, crosswalk, week, espn_entries, log=None):
    """Folds ESPN statuses into players/by_team in place (more severe wins).
    Returns how many players ESPN added or upgraded. `log` (a list) collects
    why each ESPN entry was used or skipped."""
    log = log if log is not None else []
    by_espn, by_name = {}, {}
    if crosswalk is not None:
        cw = crosswalk.dropna(subset=["gsis_id"])
        for _, r in cw.iterrows():
            info = {"gsis_id": str(r["gsis_id"]), "name": str(r.get("display_name", "")),
                    "position": str(r.get("position", "") or "")}
            if pd.notna(r.get("espn_id")):
                by_espn[str(int(float(r["espn_id"])))] = info
            by_name[(norm_name(r.get("display_name", "")), str(r.get("latest_team", "")))] = info
    played = recently_played(week)
    changed = 0
    for e in espn_entries:
        info = by_espn.get(e["espn_id"]) or by_name.get((norm_name(e["name"]), e["team"]))
        if not info or not e["team"]:
            log.append(f"unmatched {e['name']} {e['team']} {e['status']}")
            continue
        gsis = info["gsis_id"]
        sev = STATUS_SEVERITY[e["status"]]
        cur = players.get(gsis)
        if cur and STATUS_SEVERITY.get(cur["status"], 0) >= sev:
            continue  # the official report already says this or worse
        if not cur and gsis not in played:
            continue  # out for a while already -- not a new absence
        log.append(f"{e['name']} {e['team']}: {(cur or {}).get('status', 'none')} -> {e['status']}"
                   + (f" [{(e['note'] or '')[:110]}]" if position_of(e, info) in ("QB", "RB", "WR", "TE") else ""))
        players[gsis] = {
            "status": e["status"], "source": "espn",
            "primary_injury": e["injury"] or (cur or {}).get("primary_injury"),
            "secondary_injury": (cur or {}).get("secondary_injury"),
            "practice_status": (cur or {}).get("practice_status"),
            "team": e["team"], "note": e["note"],
        }
        position = (e["position"] or info["position"]).strip()
        unit = "offense" if position in OFFENSE_POSITIONS else ("defense" if position in DEFENSE_POSITIONS else None)
        lst = by_team.setdefault(e["team"], [])
        old = next((x for x in lst if x["gsis_id"] == gsis), None)
        entry = {
            "gsis_id": gsis, "name": e["name"] or info["name"], "position": position,
            "status": e["status"], "severity": sev, "source": "espn",
            "injury": e["injury"] or (old or {}).get("injury"), "note": e["note"],
            "snap_pct": snap_shares.get(gsis, {}).get(unit) if unit else None,
        }
        if old:
            lst[lst.index(old)] = entry
        elif unit:
            lst.append(entry)
        changed += 1
    return changed


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
    crosswalk = load_crosswalk()
    snap_shares = load_snap_shares(season, crosswalk)

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

    espn_ok, espn_changed = False, 0
    try:
        print(f"Downloading ESPN injury news ({ESPN_URL}) ...")
        entries = fetch_espn_injuries()
        log = []
        espn_changed = merge_espn(players, by_team, snap_shares, crosswalk, week, entries, log)
        espn_ok = True
        from collections import Counter
        counts = Counter(e["status"] for e in entries)
        gh_notice("ESPN injuries", [f"read {len(entries)} ESPN entries {dict(counts)}", f"changed {espn_changed}"] + log[:150])
    except Exception as e:
        print(f"WARNING: ESPN injury feed unavailable ({e}); using the official report only.", file=sys.stderr)
        gh_notice("ESPN injuries FAILED", [repr(e)[:500]])

    for entries in by_team.values():
        entries.sort(key=lambda e: (-e["severity"], -(e["snap_pct"] or 0)))

    from datetime import datetime, timezone
    cache = {
        "season": int(season),
        "week": int(week),
        "source": url,
        "espn": espn_ok,
        "espn_changed": espn_changed,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
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
