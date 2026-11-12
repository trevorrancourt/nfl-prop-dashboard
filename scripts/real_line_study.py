"""
Real-line study (2026-11-09, per Trevor: "reanalyze how we're doing things
... remember my goal is to make 60% here ... make the model sharper").

Every rule so far was judged on the board's own picks (30-80 bets a group).
This looks at EVERY prop that had a real sportsbook line in the saved
boards, for the given weeks, and asks what actually predicts the result
against that line:

  A. The market itself: Over rate, and whether the books' no-vig chance is
     honest (calibration), by stat.
  B. Line movement: the first line the boards saw that week vs the last one
     before kickoff. Do moves predict results (i.e. is early information
     worth money), and how often does each kind of signal get the market
     moving its way (closing line value)?
  C. Each board signal on its own: Over rate against the closing line by
     quintile (form vs line, matchup, usage, teammates out, hit rates,
     projection, ladder chance, spread/total).
  D. All together on top of the market's own number (logistic regression
     with the no-vig chance as the starting point): which signals add
     anything the books don't already know.
  E. The board's pick groups: record and closing line value.

Usage (in lookback.yml, which downloads the boards):
    python scripts/real_line_study.py --template output/dashboard.html --boards boards --weeks 7 8 9
"""
import argparse
import io
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lookback import CONST_RE, STATS_URL, consts, kickoff_utc  # noqa: E402

BOOKS = ("draftkings", "fanduel", "betmgm")

STUDY_JS = r"""(keys) => {
  const dc = {}; const out = [];
  const sw = seasonWeeks();
  const tp = (typeof topPicks === 'function') ? topPicks() : { top: [], review: [], more: [] };
  const tier = {};
  tp.top.forEach(c => { tier[markKey(c.e)] = 'top'; });
  tp.review.forEach(c => { tier[markKey(c.e)] = 'review'; });
  (tp.more || []).forEach(c => { tier[markKey(c.e)] = 'more'; });
  const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : null;
  const byGame = {};
  for (const r of ROWS) {
    if (r.vegas_line === null || r.vegas_line === undefined || !keys.includes(gameKey(r))) continue;
    const e = enrichRow(r, selectedWeeks, dc);
    const key = e.position + '|' + e.stat_col;
    const ranks = (dc[key] || rankDefenses(key, selectedWeeks)).ranks;
    const co = consistencyStats(e, selectedWeeks, e.share, ranks, 'over');
    const sv = playerSelectedIndices(e, sw).map(i => e.game_log[i]);
    const sel = playerSelectedIndices(e, selectedWeeks).map(i => e.game_log[i]);
    let usage = null, vac = null;
    const set = (typeof LADDER_SETS !== 'undefined') ? LADDER_SETS[e.stat_col] : null;
    if (set) {
      const vr = ladderVolRow(e, e.stat_col === 'passing_yards' ? 'attempts' : set.vol);
      const vv = vr ? ladderSeasonVals(vr) : [];
      usage = vv.length >= 3 && mean(vv) > 0 ? mean(vv.slice(0, 2)) / mean(vv) : null;
      vac = e.stat_col === 'passing_yards' ? 0 : ladderVacated(e.team, set.vol).share;
    }
    const lad = (typeof ladderInfo === 'function') ? ladderInfo(e) : null;
    (byGame[gameKey(e)] = byGame[gameKey(e)] || []).push(e);
    const books = {};
    for (const bk of ['draftkings', 'fanduel', 'betmgm']) books[bk] = [e[bk + '_line'], e[bk + '_over_price'], e[bk + '_under_price']];
    out.push({
      mk: markKey(e),
      player: e.player, team: e.team, opp: e.opponent, pos: e.position, stat: e.stat_col, game: gameKey(e),
      line: e.vegas_line, books,
      season_avg: mean(sv), sel_avg: mean(sel), last1: sv.length ? sv[0] : null, n_season: sv.length,
      ant: e.anticipated, share: e.share,
      def_rank: e.def_rank, def_max: e.def_rank_max,
      o_prate: co ? co.pRate : null, o_drate: co ? co.dRate : null, o_pgames: co ? co.pGames : null,
      usage, vac,
      win: e.win ? { side: e.win.side, p: e.win.p, pm: e.win.pModel, mkt: e.win.pMkt } : null,
      lad: lad ? lad.goff / LADDER_BASE[e.stat_col] : null,
      fav: tbTeamSpread(e, tbGame(e)), total: (tbGame(e) || {}).total,
      inj: e.injury ? e.injury.status : null, role: e.lookback ? e.lookback.role : null,
      grp: (typeof pickGroup === 'function') ? pickGroup(e) : null,
      bet: (typeof pickBet === 'function') ? pickBet(e) : null,
      tier: tier[markKey(e)] || null,
    });
  }
  // 👀 game-view look flags (2026-11-12): what the page would flag when each game is selected.
  const lookBy = {};
  if (typeof computeGameLooks === 'function') {
    Object.values(byGame).forEach(list => computeGameLooks(list).forEach((v, k) => { lookBy[k] = v; }));
  }
  out.forEach(o => {
    const l = lookBy[o.mk];
    o.look = l ? { side: l.side, score: l.score, kinds: l.why.map(x => x.kind), bet: l.bet } : null;
  });
  return out;
}"""


def no_vig_over(books, line):
    ps = []
    for ln, po, pu in books.values():
        if ln == line and po and pu:
            io_ = 1 / (1 + po / 100) if po > 0 else abs(po) / (abs(po) + 100)
            iu = 1 / (1 + pu / 100) if pu > 0 else abs(pu) / (abs(pu) + 100)
            ps.append(io_ / (io_ + iu))
    return sum(ps) / len(ps) if ps else None


def rows_of(html):
    for mm in CONST_RE.finditer(html):
        if mm.group(1) == "ROWS":
            return json.loads(mm.group(0).split("=", 1)[1].strip().rstrip(";"))
    return []


def q_table(df, col, target, q=5, extra=None):
    t = df.dropna(subset=[col]).copy()
    if len(t) < 50:
        return f"  {col}: too few ({len(t)})"
    t["b"] = pd.qcut(t[col].rank(method="first"), q, labels=False)
    g = t.groupby("b").agg(lo=(col, "min"), hi=(col, "max"), n=(target, "size"), over=(target, "mean"))
    if extra:
        g = g.join(t.groupby("b")[extra].mean().rename("moved_up"))
    out = [f"  {col}:"]
    for b, r in g.iterrows():
        out.append(f"    Q{b + 1} {r.lo:8.2f}..{r.hi:8.2f}  n={int(r.n):4d}  over {r.over:.3f}" + (f"  line rose {r.moved_up:.2f}" if extra else ""))
    return "\n".join(out)


def logit_offset(X, y, off, l2=1.0, iters=50):
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ b + off)))
        H = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(b))
        b += np.linalg.solve(H, X.T @ (y - p) - l2 * b)
    p = 1 / (1 + np.exp(-(X @ b + off)))
    H = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(b))
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    return b, se, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--boards", required=True)
    ap.add_argument("--weeks", type=int, nargs="+", required=True)
    ap.add_argument("--max-stale-hours", type=float, default=36,
                    help="skip a game when the last board before its kickoff is older than this")
    ap.add_argument("--dump", help="also write every graded row to this JSON file")
    args = ap.parse_args()
    template = Path(args.template).read_text()

    boards = []
    for d in sorted(Path(args.boards).iterdir()):
        f = d / "dashboard.html"
        if not f.exists():
            continue
        c = consts(f.read_text())
        if "WEEK" not in c:
            continue
        wk = int(c["WEEK"].split("=")[1].strip(" ;"))
        built = datetime.strptime(d.name, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=timezone.utc)
        boards.append((built, wk, f, c))
    boards.sort(key=lambda b: b[0])

    from playwright.sync_api import sync_playwright
    allrows = []
    for week in args.weeks:
        wb = [b for b in boards if b[1] == week]
        if not wb:
            print(f"Week {week}: no saved boards, skipped")
            continue
        season = int(wb[0][3]["SEASON"].split("=")[1].strip(" ;"))
        # Every game any board that week listed (a Monday-night-only board can be the last one).
        ko = {}
        for b in wb:
            for g in json.loads(b[3]["GAMES"].split("=", 1)[1].strip().rstrip(";")):
                ko.setdefault(g["key"], kickoff_utc(g))
        # Opening line per prop: the first board that week that had it.
        opening = {}
        for built, _, f, c in wb:
            for r in rows_of(f.read_text()):
                if r.get("vegas_line") is None:
                    continue
                k = (r["player"], r["team"], r["stat_col"])
                if k not in opening:
                    opening[k] = (built, r["vegas_line"], {bk: [r.get(bk + "_line"), r.get(bk + "_over_price"), r.get(bk + "_under_price")] for bk in BOOKS})
        # Closing: last board before each kickoff, replayed with the current code.
        by_board = defaultdict(list)
        for gk, k in ko.items():
            before = [b for b in wb if k is None or b[0] < k]
            if before and k is not None and (k - max(b[0] for b in before)).total_seconds() / 3600 > args.max_stale_hours:
                print(f"  {gk}: last board {(k - max(b[0] for b in before)).total_seconds() / 3600:.0f}h before kickoff -- skipped")
                continue
            if before:
                by_board[max(before, key=lambda b: b[0])[0]].append(gk)
        with sync_playwright() as p:
            br = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
            for built, keys in sorted(by_board.items()):
                c = dict(next(b for b in wb if b[0] == built)[3])
                tmp = Path(args.boards) / "_study.html"
                tmp.write_text(CONST_RE.sub(lambda m: c.get(m.group(1), m.group(0)), template))
                pg = br.new_page()
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(tmp.resolve().as_uri())
                pg.wait_for_timeout(3000)
                if errs:
                    sys.exit(f"Replay page error: {errs[0]}")
                got = pg.evaluate(STUDY_JS, keys)
                for r in got:
                    r["week"] = week
                    o = opening.get((r["player"], r["team"], r["stat"]))
                    r["open_line"] = o[1] if o else None
                    r["open_books"] = o[2] if o else None
                    r["open_lead_h"] = (built - o[0]).total_seconds() / 3600 if o else None
                allrows += got
                pg.close()
            br.close()
        st = pd.read_csv(io.BytesIO(requests.get(STATS_URL.format(season=season), timeout=120).content), low_memory=False)
        st = st[(st.week == week) & (st.season_type == "REG")].fillna(0)
        st["total_tds"] = st.get("rushing_tds", 0) + st.get("receiving_tds", 0)
        act = {(s.player_display_name, s.team): s for _, s in st.iterrows()}
        for r in allrows:
            if r["week"] != week:
                continue
            s = act.get((r["player"], r["team"]))
            r["actual"] = float(s[r["stat"]]) if s is not None and r["stat"] in s else None
        print(f"Week {week}: {len(wb)} boards, {sum(1 for r in allrows if r['week'] == week)} props with lines")

    if args.dump:
        Path(args.dump).write_text(json.dumps(allrows))
    df = pd.DataFrame(allrows)
    df = df[df.actual.notna() & (df.actual != df.line)].copy()
    df["over"] = (df.actual > df.line).astype(int)
    df["mkt"] = [no_vig_over(b, l) for b, l in zip(df.books, df.line)]
    df["L"] = df.line.clip(lower=0.5)
    df["form_gap"] = ((0.6 * df.sel_avg + 0.4 * df.season_avg) - df.line) / df.L
    df["season_gap"] = (df.season_avg - df.line) / df.L
    df["last1_gap"] = (df.last1 - df.line) / df.L
    df["ant_gap"] = (df.ant - df.line) / df.L
    df["soft_def"] = df.def_rank / df.def_max  # 1 = allows the most
    df["move"] = df.line - df.open_line
    df["moved_up"] = np.where(df.move > 0, 1.0, np.where(df.move < 0, 0.0, np.nan))
    df["pmodel_over"] = [(w["pm"] if w["side"] == "over" else 1 - w["pm"]) if isinstance(w, dict) else np.nan for w in df.win]
    df["fav_signed"] = df.fav

    L = []
    L.append(f"REAL-LINE STUDY, weeks {args.weeks}: {len(df):,} props graded against the closing consensus line (pushes and DNPs out)")
    L.append(f"\nA. MARKET: Over hit {df.over.mean():.3f} overall")
    for s, g in df.groupby("stat"):
        if len(g) >= 40:
            L.append(f"  {s:22s} n={len(g):4d}  over {g.over.mean():.3f}")
    m = df.dropna(subset=["mkt"])
    m["mb"] = pd.cut(m.mkt, [0, .4, .45, .5, .55, .6, 1])
    L.append("  Books' no-vig Over chance vs what happened:")
    for b, g in m.groupby("mb", observed=True):
        L.append(f"    said {g.mkt.mean():.3f}  happened {g.over.mean():.3f}  n={len(g)}")

    mv = df.dropna(subset=["open_line"])
    up, dn, same = mv[mv.move > 0], mv[mv.move < 0], mv[mv.move == 0]
    L.append(f"\nB. LINE MOVES (first line seen vs closing): {len(up)} up, {len(dn)} down, {len(same)} unchanged")
    if len(up):
        L.append(f"  Line went UP:   Over at the OPENING line {(up.actual > up.open_line).mean():.3f}, at the closing line {up.over.mean():.3f}")
    if len(dn):
        L.append(f"  Line went DOWN: Under at the OPENING line {(dn.actual < dn.open_line).mean():.3f}, at the closing line {1 - dn.over.mean():.3f}")
    L.append(f"  Unchanged: Over {same.over.mean():.3f}")
    L.append(f"  Hours between first line seen and closing board: median {mv.open_lead_h.median():.0f}")

    L.append("\nC. EACH SIGNAL ALONE -- Over rate vs the closing line by quintile (Q5 = highest), and how often the line rose after opening:")
    for col in ["form_gap", "season_gap", "last1_gap", "ant_gap", "soft_def", "o_prate", "o_drate", "usage", "vac", "pmodel_over", "lad", "fav_signed", "total", "mkt"]:
        L.append(q_table(df, col, "over", extra="moved_up"))

    feats = ["form_gap", "season_gap", "last1_gap", "ant_gap", "soft_def", "o_prate", "o_drate", "usage", "vac", "fav_signed", "total"]
    d = df.dropna(subset=["mkt"]).copy()
    for f in feats:
        d[f] = d[f].astype(float)
        d[f] = d[f].fillna(d[f].median())
        lo, hi = d[f].quantile(0.02), d[f].quantile(0.98)
        d[f] = d[f].clip(lo, hi)
        d[f] = (d[f] - d[f].mean()) / (d[f].std() or 1)
    off = np.log(d.mkt.clip(0.03, 0.97) / (1 - d.mkt.clip(0.03, 0.97))).to_numpy()
    X = np.column_stack([np.ones(len(d))] + [d[f].to_numpy() for f in feats])
    b, se, ph = logit_offset(X, d.over.to_numpy().astype(float), off)
    ll = lambda p, y: -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    p0 = 1 / (1 + np.exp(-off))
    L.append(f"\nD. ON TOP OF THE BOOKS' OWN NUMBER (n={len(d):,}; log loss market {ll(p0, d.over):.4f} -> with signals {ll(ph, d.over):.4f}):")
    L.append("  (coefficient per 1 standard deviation of the signal; |z| >= 2 is real, < 1 is noise)")
    for name, bb, ss in zip(["intercept"] + feats, b, se):
        L.append(f"    {name:12s} {bb:+.3f}  z={bb / ss:+.1f}")
    # How good is the best slice the combined model finds (in-sample, so optimistic)?
    d["ph"] = ph
    d["edge"] = np.maximum(ph - p0, (1 - ph) - (1 - p0))
    d["pick_over"] = ph > p0
    d["win"] = np.where(d.pick_over, d.over, 1 - d.over)
    for top in (0.02, 0.05, 0.10):
        s = d.sort_values("edge", ascending=False).head(max(1, int(len(d) * top)))
        L.append(f"  Top {top:.0%} by model edge (in-sample, optimistic): {s.win.mean():.3f} win, n={len(s)}")

    L.append("\nE. BOARD PICK GROUPS -- record at the closing line on their own bet, and closing line value (line moved toward the bet after opening):")
    for g, x in df[df.grp.notna()].groupby("grp"):
        w = [((r.actual > r.bet["line"]) if r.bet["side"] == "over" else (r.actual < r.bet["line"])) for r in x.itertuples() if isinstance(r.bet, dict) and r.actual != r.bet["line"]]
        toward = [((r.move > 0) if r.bet["side"] == "over" else (r.move < 0)) for r in x.itertuples() if isinstance(r.bet, dict) and r.open_line is not None and not math.isnan(r.move) and r.move != 0]
        dec = lambda o: 1 + o / 100 if o > 0 else 1 + 100 / abs(o)
        pr = [((r.actual > r.bet["line"]) if r.bet["side"] == "over" else (r.actual < r.bet["line"]), r.bet["price"]) for r in x.itertuples()
              if isinstance(r.bet, dict) and r.bet.get("price") is not None and r.actual != r.bet["line"]]
        roi = sum((dec(p) - 1) if ok else -1 for ok, p in pr) / len(pr) if pr else 0
        L.append(f"  {g:16s} {sum(w)}-{len(w) - sum(w)}  ({(sum(w) / len(w) if w else 0):.0%})  ROI {roi:+.0%}   line moved toward it {sum(toward)}/{len(toward)}")
    # The lists themselves, as the page builds them from this board (Top 3 / Review).
    for t in ("top", "review", "more"):
        x = df[df.tier == t] if "tier" in df else df.iloc[0:0]
        pr = [((r.actual > r.bet["line"]) if r.bet["side"] == "over" else (r.actual < r.bet["line"]), r.bet["price"]) for r in x.itertuples()
              if isinstance(r.bet, dict) and r.bet.get("price") is not None and r.actual != r.bet["line"]]
        if pr:
            dec = lambda o: 1 + o / 100 if o > 0 else 1 + 100 / abs(o)
            wins = sum(ok for ok, _ in pr)
            L.append(f"  LIST {({'top': 'Best 3', 'review': 'Next 10', 'more': 'More 17'})[t]}: {wins}-{len(pr) - wins}  ROI {sum((dec(p) - 1) if ok else -1 for ok, p in pr) / len(pr):+.0%}")
            if t == "more":
                for sd in ("over", "under"):
                    ps = [((r.actual > r.bet["line"]) if sd == "over" else (r.actual < r.bet["line"]), r.bet["price"]) for r in x.itertuples()
                          if isinstance(r.bet, dict) and r.bet.get("side") == sd and r.bet.get("price") is not None and r.actual != r.bet["line"]]
                    if ps:
                        L.append(f"      more / {sd}: {sum(ok for ok, _ in ps)}-{len(ps) - sum(ok for ok, _ in ps)}  ROI {sum((dec(p) - 1) if ok else -1 for ok, p in ps) / len(ps):+.0%}")

    # F. Inside the two groups the lists are built from (2026-11-11, per Trevor:
    # "suggestions are all under and the top three are high odds"): by stat, by
    # line size, by price, by week, and how many picks are the same player twice.
    dec = lambda o: 1 + o / 100 if o > 0 else 1 + 100 / abs(o)
    def _sum(items):
        n = len(items)
        if not n:
            return "none"
        w = sum(1 for ok, _ in items if ok)
        return f"{w}-{n - w} ({w / n:.0%}, ROI {sum((dec(pc) - 1) if ok else -1 for ok, pc in items) / n:+.0%})"
    def _graded(g):
        out = []
        for r in df[df.grp == g].itertuples():
            b = r.bet
            if not isinstance(b, dict) or b.get("price") is None or r.actual == b["line"]:
                continue
            ok = (r.actual > b["line"]) if b["side"] == "over" else (r.actual < b["line"])
            out.append((r, b, ok))
        return out
    L.append("\nF. INSIDE THE GROUPS (record / ROI at the closing line):")
    for g in ("proj_under", "proj_over", "must_market", "target3"):
        xs = _graded(g)
        if not xs:
            continue
        L.append(f"  {g}: {_sum([(ok, b['price']) for _, b, ok in xs])}")
        for side in ("over", "under"):
            L.append(f"    side {side}: {_sum([(ok, b['price']) for _, b, ok in xs if b['side'] == side])}")
        stats = sorted({r.stat for r, _, _ in xs})
        L.append("    by stat: " + "; ".join(f"{st} {_sum([(ok, b['price']) for r, b, ok in xs if r.stat == st])}" for st in stats))
        yd = [(r, b, ok) for r, b, ok in xs if r.stat in ("rushing_yards", "receiving_yards")]
        L.append("    yard props by line size: " + "; ".join(
            f"{lo}-{hi} {_sum([(ok, b['price']) for r, b, ok in yd if lo <= b['line'] < hi])}" for lo, hi in ((0, 20), (20, 40), (40, 70), (70, 999))))
        L.append("    by price: " + "; ".join(
            f"{lo}..{hi} {_sum([(ok, b['price']) for r, b, ok in xs if lo <= b['price'] < hi])}" for lo, hi in ((-999, -150), (-150, -125), (-125, -112), (-112, 999))))
        L.append("    by week: " + "; ".join(f"wk{w} {_sum([(ok, b['price']) for r, b, ok in xs if r.week == w])}" for w in sorted({r.week for r, _, _ in xs})))
        seen = {}
        for r, b, ok in xs:
            seen.setdefault((r.player, r.week), []).append((r, b, ok))
        dups = [v for v in seen.values() if len(v) > 1]
        L.append(f"    same player twice in a week: {len(dups)} of {len(seen)} players ({sum(len(v) for v in dups)} of {len(xs)} picks); of those both won {sum(1 for v in dups if all(o for *_, o in v))}, both lost {sum(1 for v in dups if not any(o for *_, o in v))}")
        best = []
        for v in seen.values():
            strength = lambda t: abs((t[0].ant or 0) - t[1]["line"]) / t[1]["line"] if t[1]["line"] else 0
            best.append(max(v, key=strength))
        L.append(f"    one pick per player-week (strongest kept): {_sum([(ok, b['price']) for _, b, ok in best])}")

    # G. The game-view 👀 look flags, graded on the flagged side at its best line and price.
    if "look" in df:
        items = []
        for r in df.itertuples():
            lk = r.look
            if not isinstance(lk, dict) or not lk.get("bet") or lk["bet"].get("price") is None or not lk.get("side"):
                continue
            b = lk["bet"]
            if r.actual == b["line"]:
                continue
            ok = (r.actual > b["line"]) if b["side"] == "over" else (r.actual < b["line"])
            items.append((r, lk, ok, b["price"]))
        L.append("\nG. 👀 GAME-VIEW LOOK FLAGS (flagged side, at its best line and price; flags are for lines NOT on the ranked list):")
        L.append(f"  all graded props for comparison: Over hit {df.over.mean():.1%}, Under hit {1 - df.over.mean():.1%} (n={len(df)})")
        if items:
            L.append(f"  all flags: {_sum([(ok, pc) for _, _, ok, pc in items])}")
            for sd in ("over", "under"):
                L.append(f"    {sd}: {_sum([(ok, pc) for _, lk, ok, pc in items if lk['side'] == sd])}")
            kinds = sorted({k for _, lk, _, _ in items for k in lk["kinds"]})
            L.append("    by reason (a flag can have several): " + "; ".join(
                f"{k} {_sum([(ok, pc) for _, lk, ok, pc in items if k in lk['kinds']])}" for k in kinds))
            L.append("    by score: " + "; ".join(
                f"{lo}-{hi} {_sum([(ok, pc) for _, lk, ok, pc in items if lo <= lk['score'] < hi])}" for lo, hi in ((2, 3), (3, 4), (4, 99))))
            L.append("    by week: " + "; ".join(f"wk{w} {_sum([(ok, pc) for r, _, ok, pc in items if r.week == w])}" for w in sorted({r.week for r, _, _, _ in items})))
        else:
            L.append("  no flags graded")

    text = "\n".join(L)
    print(text)
    if os.environ.get("GITHUB_ACTIONS"):
        chunk, size, n = [], 0, 0
        for ln in text.split("\n"):
            if size + len(ln) > 3500 and chunk:
                n += 1
                print(f"::notice title=Study {n}::" + "%0A".join(chunk))
                chunk, size = [], 0
            chunk.append(ln.replace("%", "%25"))
            size += len(ln) + 3
        if chunk:
            n += 1
            print(f"::notice title=Study {n}::" + "%0A".join(chunk))


if __name__ == "__main__":
    main()
