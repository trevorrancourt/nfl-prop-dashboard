"""
"Review my week" (2026-11-09, per Trevor: "review my rationale at the end
of the week and see if it worked").

Takes the My Bets backup text (My Bets -> Backup / restore -> copy) and
grades, for the given week(s):
  - your bets, grouped by the "why I like it" reason (MARKS['like|' + key]),
    using the result you set or, if it's still pending, the box score;
  - your passes, grouped by the "why pass?" reason (MARKS['why|' + key]),
    against the line the board showed when you passed (MARKS['pline|' + key]).
    A pass was "right" when that bet would have lost.
Also breaks your bets down by stat, Over/Under and stake size.

    python3 scripts/review_my_week.py backup.json --weeks 10
"""
import argparse
import io
import json
from collections import defaultdict

import pandas as pd
import requests

STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
LABELS = {
    "matchup": "Matchup", "volume": "Usage / volume", "line_off": "Line looks off", "script": "Game script",
    "news": "Injury / news", "board": "The board's signal", "gut": "Gut", "other": "Other",
    "injury": "Injury / role news", "line_moved": "Line moved / bad number", "exposure": "Enough on this game",
}


def dec(o):
    o = float(o)
    return 1 + o / 100 if o > 0 else 1 + 100 / abs(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("backup")
    ap.add_argument("--weeks", type=int, nargs="+", required=True)
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args()
    raw = open(a.backup).read()
    data = json.loads(raw[raw.index("{"):])
    marks, bets = data.get("marks", {}), data.get("bets", {})
    st = pd.read_csv(io.BytesIO(requests.get(STATS_URL.format(season=a.season), timeout=120).content), low_memory=False)
    st = st[st.season_type == "REG"].fillna(0).copy()
    st["total_tds"] = st.get("rushing_tds", 0) + st.get("receiving_tds", 0)
    actual = {(int(s.week), s.player_display_name, s.team): s for _, s in st.iterrows()}

    def stat(week, player, team, col):
        s = actual.get((week, player, team))
        return float(s[col]) if s is not None and col in s else None

    def grade(v, side, line):
        if v is None or v == line:
            return None
        return "W" if (v > line) == (side == "over") else "L"

    by_reason, by_stat, by_side, by_stake = (defaultdict(list) for _ in range(4))
    money = []
    for key, b in bets.items():
        if key.startswith("manual|"):
            continue
        week, player, team, col = key.split("|")
        week = int(week)
        if week not in a.weeks:
            continue
        res = {"win": "W", "loss": "L"}.get(b.get("result"))
        if res is None and b.get("line") and b.get("side"):
            res = grade(stat(week, player, team, col), b["side"], float(b["line"]))
        if res is None:
            continue
        reason = LABELS.get(marks.get("like|" + key), "no reason saved")
        by_reason[reason].append(res)
        by_stat[col].append(res)
        by_side[b.get("side") or "?"].append(res)
        stake = float(b["stake"]) if b.get("stake") else None
        if stake and b.get("odds"):
            p = stake * (dec(b["odds"]) - 1) if res == "W" else -stake
            money.append(p)
            by_stake["over $100" if stake > 100 else "$100 or less"].append(res)

    passes = defaultdict(list)
    for key, v in marks.items():
        if v != "pass" or "|" not in key or key.split("|")[0] in ("why", "pline", "like", "role"):
            continue
        week, player, team, col = key.split("|")
        if int(week) not in a.weeks or ("pline|" + key) not in marks:
            continue
        side, line, _price = marks["pline|" + key].split("|")
        res = grade(stat(int(week), player, team, col), side, float(line))
        if res:
            passes[LABELS.get(marks.get("why|" + key), "no reason saved")].append(res)

    rec = lambda rs: f"{rs.count('W')}-{rs.count('L')}"
    out = [f"REVIEW, week(s) {a.weeks}"]
    allb = [r for rs in by_reason.values() for r in rs]
    out.append(f"Your bets: {rec(allb)}" + (f", ${sum(money):+.0f}" if money else ""))
    out.append("\nBets by why you liked them:")
    for k, rs in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        out.append(f"  {k:24s} {rec(rs)}")
    for title, d in (("By stat", by_stat), ("Over / Under", by_side), ("By stake", by_stake)):
        out.append(f"\n{title}:")
        for k, rs in sorted(d.items(), key=lambda kv: -len(kv[1])):
            out.append(f"  {k:24s} {rec(rs)}")
    out.append("\nPasses -- what the board's side would have done (L = you were right to pass):")
    if passes:
        for k, rs in sorted(passes.items(), key=lambda kv: -len(kv[1])):
            out.append(f"  {k:24s} would have gone {rec(rs)}  -> right to pass {rs.count('L')} of {len(rs)}")
    else:
        out.append("  none with a saved line yet (lines are saved on passes from Nov 9 on)")
    print("\n".join(out))


if __name__ == "__main__":
    main()
