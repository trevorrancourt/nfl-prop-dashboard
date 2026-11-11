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

Your own words (2026-11-11, per Trevor: "when i react to a bet i tell you in
words why i didn't like it ... build that into the model"): the picker's text
box is saved as MARKS['note|' + key] = 'n:' + text, with MARKS['ctx|' + key] =
"group|Review #|projection" (what the board said at that moment). This prints
each note next to what happened, and tallies them by theme. It never changes
the model: the themes that keep being right over several weeks are what get
turned into rules, and the weekly output is for a person to read.

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


# Rough themes found by keyword in your own words -- a first sort, not a model.
THEMES = [
    ("injury / news", ("injur", "hurt", "questionable", "doubtful", "limited", "concussion", "news", "status", "dnp", "inactive")),
    ("role / usage", ("role", "snap", "target", "touch", "carries", "committee", "backup", "depth", "usage", "volume", "replac", "returns", "back from", "workload", "rotation")),
    ("matchup", ("matchup", "defense", "corner", "coverage", "shadow", "pass rush", "front seven", "tough")),
    ("game script", ("script", "blowout", "garbage", "trailing", "pace", "spread", "total", "favorite", "underdog")),
    ("line / price", ("line", "price", "juice", "number", "moved", "stale", "odds", "vig", "steam")),
    ("weather", ("wind", "rain", "snow", "weather", "cold")),
    ("small sample / fluke", ("sample", "fluke", "one game", "lucky", "regress", "outlier")),
    ("gut", ("gut", "feel", "vibe", "don't like", "dont like")),
]


def themes_of(text):
    t = text.lower()
    return [name for name, words in THEMES if any(w in t for w in words)] or ["(no theme matched)"]


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
    # Your own words, next to what happened.
    notes = []
    for key, v in marks.items():
        if not key.startswith("note|") or not isinstance(v, str) or not v.startswith("n:"):
            continue
        bkey = key[5:]
        try:
            week, player, team, col = bkey.split("|")
            week = int(week)
        except ValueError:
            continue
        if week not in a.weeks:
            continue
        kind = marks.get(bkey)
        if kind not in ("pass", "bet"):
            continue
        ctx = (marks.get("ctx|" + bkey) or "||").split("|") + ["", "", ""]
        group, rank, ant = ctx[0], ctx[1], ctx[2]
        if kind == "pass":
            side = line = None
            if ("pline|" + bkey) in marks:
                side, line, _price = marks["pline|" + bkey].split("|")
            res = grade(stat(week, player, team, col), side, float(line)) if side else None
            shown = f"board: {side[0].upper()} {line}" if side else "board line not saved"
            verdict = {"W": "board's side WON (passing cost you)", "L": "board's side LOST (right to pass)", None: "no result yet"}[res]
        else:
            b = bets.get(bkey, {})
            res = {"win": "W", "loss": "L"}.get(b.get("result"))
            if res is None and b.get("line") and b.get("side"):
                res = grade(stat(week, player, team, col), b["side"], float(b["line"]))
            shown = f"your bet: {b.get('side', '?')[:1].upper()} {b.get('line', '?')}"
            verdict = {"W": "won", "L": "lost", None: "no result yet"}[res]
        notes.append(dict(kind=kind, player=player, col=col, shown=shown, verdict=verdict, res=res,
                          group=group or "?", rank=rank, ant=ant, text=v[2:]))
    out.append(f"\nYOUR WORDS ({len(notes)} notes):")
    for n in notes:
        tag = f"{n['group']}{' #' + n['rank'] if n['rank'] else ''}"
        proj = f", projection {n['ant']}" if n["ant"] else ""
        out.append(f"  {n['kind'].upper():4s} {n['player']} {n['col']} -- {n['shown']} ({tag}{proj}) -> {n['verdict']}")
        out.append(f"       \"{n['text']}\"")
    if not notes:
        out.append("  none yet (the box in the Pass / Bet picker saves them)")
    else:
        by_theme = defaultdict(list)
        for n in notes:
            for t in themes_of(n["text"]):
                by_theme[t].append(n)
        out.append("\nBy theme in your words (passes: L = the board's side lost, so passing was right):")
        for t, ns in sorted(by_theme.items(), key=lambda kv: -len(kv[1])):
            ps = [x["res"] for x in ns if x["kind"] == "pass" and x["res"]]
            bs = [x["res"] for x in ns if x["kind"] == "bet" and x["res"]]
            bits = []
            if ps:
                bits.append(f"passes: board's side went {rec(ps)} -> right to pass {ps.count('L')} of {len(ps)}")
            if bs:
                bits.append(f"your bets: {rec(bs)}")
            out.append(f"  {t:24s} {len(ns)} note(s)  " + ("; ".join(bits) or "no results yet"))
        out.append("  (A theme needs several weeks of results before it becomes a rule.)")
    print("\n".join(out))


if __name__ == "__main__":
    main()
