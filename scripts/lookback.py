"""
Look back on a finished week (2026-11-03, per Trevor: "too many lightbulbs
and question marks and not enough suggested bets ... can you do a look back
on last week").

Takes the boards saved during that week (Actions artifacts, one folder per
build named by its UTC timestamp), and for each game uses the last board
built before kickoff. Each board's data is dropped into the CURRENT page
code (template), so every row carries `lookback` (what each rule took
away). Every row with a side is then graded against the real box score.

Prints, and writes as GitHub annotations when run in Actions:
  - each final group (MUST BET / 3-star / 💡 / ❓) W-L at the board's line
  - "would have been 3-star / MUST" rows by the rule that blocked them
  - the Win % edge buckets

Usage:
    python scripts/lookback.py --template output/dashboard.html \
        --boards boards/ --week 9
"""
import argparse
import io
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

DATA_CONSTS = ["ROWS", "DEFENSE_LOGS", "DEFENSE_GAMES", "STAT_CATALOG", "COVERAGE", "GAMES",
               "TEAM_RESULTS", "INJ_BY_TEAM", "WEEK", "ODDS_TIME", "ODDS_TIME_UTC", "SEASON", "RULE_NUMS"]
CONST_RE = re.compile(r"^const (" + "|".join(DATA_CONSTS) + r") = .*$", re.M)
STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"


def consts(html):
    return {m.group(1): m.group(0) for m in CONST_RE.finditer(html)}


def kickoff_utc(g):
    try:
        d = datetime.strptime(f"{g['gameday']} {g.get('gametime') or '13:00'}", "%Y-%m-%d %H:%M")
    except (KeyError, ValueError):
        return None
    # EDT through the first Sunday of November, EST after.
    edt = d < datetime(d.year, 11, 1) + timedelta(days=(6 - datetime(d.year, 11, 1).weekday()) % 7)
    return d.replace(tzinfo=timezone(timedelta(hours=-4 if edt else -5))).astimezone(timezone.utc)


EVAL_JS = r"""() => {
  const dc = {}; const out = [];
  const tp = (typeof topPicks === 'function') ? topPicks() : { top: [], review: [], more: [] };
  const tier = {};
  tp.top.forEach(c => { tier[markKey(c.e)] = 'top'; });
  tp.review.forEach(c => { tier[markKey(c.e)] = 'review'; });
  (tp.more || []).forEach(c => { tier[markKey(c.e)] = 'more'; });
  for (const r of ROWS) {
    const e = enrichRow(r, selectedWeeks, dc);
    const c = e.cons;
    const lvl = Math.max(e.hot_level || 0, e.cold_level || 0);
    let group = 'none';
    if (lvl === 4) group = 'MUST BET';
    else if (lvl === 3) group = '3-star';
    else if (e.idea_reason) group = '💡';
    else if (e.needs_review) group = '❓';
    out.push({
      player: e.player, team: e.team, opp: e.opponent, game: gameKey(e), stat: e.stat_col, label: e.stat_label,
      group, side: lvl ? (e.hot_level ? 'over' : 'under') : (c ? c.side : null),
      line: e.outlier_promo ? e.outlier_promo.line : (c ? c.line : null),
      price: e.outlier_promo ? e.outlier_promo.price : (c && c.market ? c.market.price : null),
      lb: e.lookback, idea: e.idea_reason || '', why: e.review_reason || '',
      win: e.win ? { side: e.win.side, line: e.win.line, price: e.win.price, edge: e.win.edge, p: e.win.p } : null,
      ov: e.outlier_value ? (() => { const m = bestMarketFor(e, e.outlier_def.side); return m ? { side: e.outlier_def.side, line: m.line, price: m.price } : null; })() : null,
      blocked: (e.lookback.role || e.lookback.blowout || !!e.lookback.mismatch),
      promo: !!e.outlier_promo,
      grp: (typeof pickGroup === 'function') ? pickGroup(e) : null,
      bet: (typeof pickBet === 'function') ? pickBet(e) : null,
      tier: tier[markKey(e)] || null,
      ld: (typeof ladderInfo === 'function') ? (() => { const i = ladderInfo(e); return i ? { goff: i.goff, lift: i.lift, target: i.target, rungs: i.rungs.map(g => [g.t, g.p]), top: !!ladderPick(e) } : null; })() : null,
    });
  }
  return out;
}"""


def blocker(lb, group):
    """First rule (in pipeline order) that kept a would-be 3-star/MUST off the board."""
    if not lb or lb["raw"] < 3 or group in ("MUST BET", "3-star"):
        return None
    if lb["capped"]:
        return "not a top-10 matchup"
    if lb["mismatch"] == "untested":
        return "matchup untested"
    if lb["mismatch"]:
        return "matchup mismatch"
    if lb["priced"]:
        return "price worse than -130"
    if lb["blowout"] or lb["backup"]:
        return "blowout rule"
    if lb["role"]:
        return "role change"
    return "other"


def result(actual, side, line):
    if actual is None or side is None or line is None:
        return None
    if actual == line:
        return "P"
    return "W" if (actual > line) == (side == "over") else "L"


def profit(res, price):
    if res == "W" and price is not None:
        return price / 100 if price > 0 else 100 / abs(price)
    return -1.0 if res == "L" else 0.0


def rec(rs):
    w, l, p = rs.count("W"), rs.count("L"), rs.count("P")
    pct = f"{w / (w + l) * 100:.0f}%" if w + l else "-"
    return f"{w}-{l}" + (f"-{p}" if p else "") + f" ({pct})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--boards", required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--record-file", help="results/track_record.json to update with this week's group records")
    args = ap.parse_args()

    template = Path(args.template).read_text()
    boards = []
    for d in sorted(Path(args.boards).iterdir()):
        f = d / "dashboard.html"
        if not f.exists():
            continue
        html = f.read_text()
        c = consts(html)
        if "WEEK" not in c or int(c["WEEK"].split("=")[1].strip(" ;")) != args.week:
            continue
        built = datetime.strptime(d.name, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=timezone.utc)
        boards.append((built, c))
    if not boards:
        sys.exit(f"No saved boards for week {args.week}.")
    season = int(boards[0][1]["SEASON"].split("=")[1].strip(" ;"))
    games = json.loads(boards[-1][1]["GAMES"].split("=", 1)[1].strip().rstrip(";"))
    pick_for = {}
    for g in games:
        ko = kickoff_utc(g)
        before = [b for b in boards if ko is None or b[0] < ko]
        if before:
            pick_for[g["key"]] = max(before, key=lambda b: b[0])
    print(f"{len(boards)} week-{args.week} boards; using the last one before each kickoff for {len(pick_for)} games.")

    from playwright.sync_api import sync_playwright
    rows = []
    by_board = defaultdict(list)
    for key, b in pick_for.items():
        by_board[b[0]].append(key)
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        for built, keys in sorted(by_board.items()):
            c = dict(next(b for b in boards if b[0] == built)[1])
            page_html = CONST_RE.sub(lambda m: c.get(m.group(1), m.group(0)), template)
            tmp = Path(args.boards) / "_replay.html"
            tmp.write_text(page_html)
            pg = br.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(tmp.resolve().as_uri())
            pg.wait_for_timeout(3000)
            if errs:
                sys.exit(f"Replay page error ({built}): {errs[0]}")
            got = [r for r in pg.evaluate(EVAL_JS) if r["game"] in keys]
            print(f"  board {built:%a %H:%M}Z -> {len(keys)} games, {len(got)} rows")
            rows += got
            pg.close()
        br.close()

    resp = requests.get(STATS_URL.format(season=season), timeout=120)
    resp.raise_for_status()
    st = pd.read_csv(io.BytesIO(resp.content), low_memory=False)
    st = st[(st.week == args.week) & (st.season_type == "REG")].fillna(0)
    st["total_tds"] = st.get("rushing_tds", 0) + st.get("receiving_tds", 0)
    actual = {}
    for _, s in st.iterrows():
        actual[(s.player_display_name, s.team)] = s
    for r in rows:
        s = actual.get((r["player"], r["team"]))
        r["actual"] = float(s[r["stat"]]) if s is not None and r["stat"] in s else None
        r["res"] = result(r["actual"], r["side"], r["line"])
        w = r["win"]
        r["wres"] = result(r["actual"], w["side"], w["line"]) if w else None
        b = r.get("bet")
        r["gres"] = result(r["actual"], b["side"], b["line"]) if b else None
        o = r["ov"]
        r["ores"] = result(r["actual"], o["side"], o["line"]) if o else None

    lines = []
    groups = defaultdict(list)
    for r in rows:
        if r["res"] and r["group"] != "none":
            groups[r["group"]].append(r["res"])
    lines.append(f"WEEK {args.week} -- graded at the board's line, on the side it pointed to (players who didn't play are left out)")
    for gname in ("MUST BET", "3-star", "💡", "❓"):
        lines.append(f"  {gname:9s} {len(groups[gname]):4d} rows  {rec(groups[gname])}")

    tiers = defaultdict(list)
    for r in rows:
        if r.get("tier") and r["gres"]:
            tiers[r["tier"]].append(r)
    if tiers:
        lines.append("\nTop 3 / Review lists (graded on their own bet):")
        for t in ("top", "review", "more"):
            rs = tiers.get(t, [])
            lines.append(f"  {({'top': '⭐ Best 3', 'review': '🔍 Next 10', 'more': '➕ More 17'})[t]:11s} {len(rs):3d}  {rec([r['gres'] for r in rs])}")
            if t == "more" and rs:
                for sd in ("over", "under"):
                    ss = [r['gres'] for r in rs if r['bet']['side'] == sd]
                    lines.append(f"      {sd:5s} {len(ss):3d}  {rec(ss)}")
            if t == "top":
                for r in rs:
                    lines.append(f"    {r['gres']} {r['player']} {r['label']} {r['bet']['side'][0].upper()}{r['bet']['line']} ({r['bet']['price']}) -> {r['actual']:g}  [{r['grp']}]")
    grp = defaultdict(lambda: [0, 0])
    for r in rows:
        if r.get("grp") and r["gres"] in ("W", "L"):
            grp[r["grp"]][0 if r["gres"] == "W" else 1] += 1
    if grp:
        lines.append("\nPick groups (feeds the Top 3 scoring):")
        for g, (w, l) in sorted(grp.items(), key=lambda kv: -(kv[1][0] + kv[1][1])):
            lines.append(f"  {g:16s} {w}-{l}")
    if args.record_file and grp:
        rf = Path(args.record_file)
        data = json.loads(rf.read_text()) if rf.exists() else {"weeks": {}}
        data.setdefault("weeks", {})[str(args.week)] = {g: v for g, v in sorted(grp.items())}
        rf.write_text(json.dumps(data, indent=1) + "\n")
        print(f"Saved week {args.week} group records to {rf}")

    blocked = defaultdict(list)
    for r in rows:
        b = blocker(r["lb"], r["group"])
        if b and r["res"]:
            blocked[b].append(r)
    total_b = sum(len(v) for v in blocked.values())
    lines.append(f"\nWould-have-been 3-star / MUST BET rows blocked by a rule: {total_b}")
    for b, rs in sorted(blocked.items(), key=lambda kv: -len(kv[1])):
        musts = sum(1 for r in rs if r["lb"]["raw"] == 4)
        lines.append(f"  {b:24s} {len(rs):3d} ({musts} MUST)  {rec([r['res'] for r in rs])}")

    ideas = defaultdict(list)
    for r in rows:
        if r["group"] == "💡" and r["res"]:
            i = r["idea"]
            k = ("🎯 line looks low" if "line looks" in i else "🎯 outlier" if "outlier" in i
                 else "blowout upside" if "blowout" in i else "2-star near miss" if "2-star" in i
                 else "game script" if "script" in i else "other")
            ideas[k].append(r["res"])
    lines.append("\n💡 by reason:")
    for k, rs in sorted(ideas.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {k:24s} {len(rs):3d}  {rec(rs)}")

    qs = defaultdict(list)
    for r in rows:
        if r["group"] == "❓" and r["res"]:
            w = r["why"]
            k = ("role change" if w.startswith("Role change") else "below 3-star bar (1-2 star)" if "below the 3-star bar" in w
                 else "matchup" if w.startswith("Matchup") else "blowout" if w.startswith("Blowout") else "other")
            qs[k].append(r["res"])
    lines.append("\n❓ by reason:")
    for k, rs in sorted(qs.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {k:28s} {len(rs):4d}  {rec(rs)}")

    ov = [r for r in rows if r["ores"]]
    lines.append("\n🎯 line looks low/high, graded on the 🎯 side at its best price:")
    for lbl, rs in (("all", ov), ("no role/blowout/mismatch flag", [r for r in ov if not r["blocked"]]),
                    ("price -130 or better", [r for r in ov if not r["blocked"] and r["ov"]["price"] is not None and r["ov"]["price"] >= -130])):
        u = sum(profit(r["ores"], r["ov"]["price"]) for r in rs)
        lines.append(f"  {lbl:32s} {len(rs):3d}  {rec([r['ores'] for r in rs])}  {u:+.1f} units")
    for r in ov[:25]:
        lines.append(f"    {r['ores']} {r['player']} {r['label']} {r['ov']['side'][0].upper()}{r['ov']['line']} ({r['ov']['price']}) -> {r['actual']:g}  [{r['group']}{', flagged' if r['blocked'] else ''}]")

    eb = defaultdict(list)
    for r in rows:
        if r["wres"]:
            e = r["win"]["edge"] * 100
            k = "<0" if e < 0 else "0-3" if e < 3 else "3-10" if e < 10 else "10+"
            eb[k].append((r["wres"], r["win"]["price"]))
    lines.append("\nWin % edge buckets (better side, best price):")
    for k in ("<0", "0-3", "3-10", "10+"):
        rs = eb.get(k, [])
        u = sum(profit(a, pr) for a, pr in rs)
        lines.append(f"  edge {k:5s} {len(rs):4d}  {rec([a for a, _ in rs])}  {u:+.1f} units")

    pr = [r["res"] for r in rows if r.get("promo") and r["res"]]
    if pr:
        lines.append(f"\n🎯 3-stars (promoted 'line looks low'): {rec(pr)}")

    ld = [r for r in rows if r.get("ld") and r["actual"] is not None]
    if ld:
        top = [r for r in ld if r["ld"]["top"]]
        rate = lambda rs: sum(r["actual"] >= r["ld"]["target"] for r in rs) / len(rs) if rs else 0
        lines.append(f"\n🪜 Ladder board: {len(top)} board picks went off {rate(top):.0%} (board said {sum(r['ld']['goff'] for r in top) / max(len(top), 1):.0%}); all {len(ld)} ladder-eligible rows {rate(ld):.0%}")
        for r in sorted(top, key=lambda r: -r["ld"]["lift"]):
            hit = [t for t, _ in r["ld"]["rungs"] if r["actual"] >= t]
            lines.append(f"    {'GO' if r['actual'] >= r['ld']['target'] else '--'} {r['player']} {r['label']} -> {r['actual']:g} (target {r['ld']['target']}+; rungs hit {len(hit)}/{len(r['ld']['rungs'])})")
        bins = defaultdict(lambda: [0, 0.0, 0])
        for r in ld:
            for t, pp in r["ld"]["rungs"]:
                b = min(int(pp * 10), 9)
                bins[b][0] += 1; bins[b][1] += pp; bins[b][2] += int(r["actual"] >= t)
        lines.append("  Rung calibration (all eligible rows): said -> hit")
        for b in sorted(bins):
            n, sp, h = bins[b]
            lines.append(f"    {sp / n:5.0%} -> {h / n:5.0%}  ({n} rungs)")

    lines.append("\nBlocked would-be picks (first 30):")
    allb = sorted((r for rs in blocked.values() for r in rs), key=lambda r: (-r["lb"]["raw"], r["player"]))
    for r in allb[:30]:
        lines.append(f"  {r['res']} {'MUST' if r['lb']['raw'] == 4 else '3★'} {r['player']} {r['label']} {r['side'][0].upper()}{r['line']} -> {r['actual']:g}  [{blocker(r['lb'], r['group'])}]")

    text = "\n".join(lines)
    print("\n" + text)
    if os.environ.get("GITHUB_ACTIONS"):
        chunk = []
        size = 0
        n = 0
        for ln in lines:
            if size + len(ln) > 3500 and chunk:
                n += 1
                print(f"::notice title=Look back {n}::" + "%0A".join(chunk))
                chunk, size = [], 0
            chunk.append(ln.replace("%", "%25").replace("\n", "%0A"))  # a raw newline would end the note
            size += len(ln) + 3
        if chunk:
            n += 1
            print(f"::notice title=Look back {n}::" + "%0A".join(chunk))
        with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as f:
            f.write("```\n" + text + "\n```\n")


if __name__ == "__main__":
    main()
