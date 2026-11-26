"""
Backtest (2026-11-26): is the Adj Rank column (defense rank adjusted for who
it played) a better read than the plain Opp Rank?

Per Trevor: "if they're 32 against running back runs but they've played the
4 best run teams 4 weeks in a row. It's almost like that's expected".

For every week 6-18 of 2019-2025 and every defense, using only earlier weeks:
  raw      = average allowed to the position over its last 4 games (the
             board's default window), ranked 1 = allows the least
  adjusted = total allowed / total "usual" of the offenses it faced, where an
             offense's usual = its average in its OTHER earlier games that
             season; ranked 1 = furthest under usual
Outcome = what the defense allowed THIS week / what this week's offense
usually gets (its earlier games). 1.00 = the offense got its usual.

Prints, per stat and pooled: how well each rank lines up with the outcome
(Spearman), the outcome by rank bucket, and the cases Trevor described --
the two ranks disagree by 8+ spots -- to see which one was right.

    python3 scripts/backtest_adj_rank.py <dir with w2019.csv .. w2025.csv>
(the files are nflverse stats_player_week_<season>.csv)
"""
import sys

import numpy as np
import pandas as pd

D = sys.argv[1]
STATS = [("RB", "rushing_yards"), ("RB", "carries"), ("RB", "receptions"), ("WR", "receiving_yards"),
         ("WR", "receptions"), ("TE", "receiving_yards"), ("TE", "receptions"), ("QB", "passing_yards")]
WINDOW = 4          # the board's default: last 4 played weeks
MIN_GAMES = 3       # games the defense needs in the window
MIN_OFF_GAMES = 3   # earlier games this week's offense needs for its "usual"
GAP = 8             # ranks apart to count as "the two disagree"

cols = ["position", "season", "week", "season_type", "team", "opponent_team"] + sorted({s for _, s in STATS})
w = pd.concat([pd.read_csv(f"{D}/w{y}.csv", usecols=cols) for y in range(2019, 2026)])
w = w[w.season_type == "REG"].fillna(0)

out = []
for pos, st in STATS:
    x = w[w.position == pos]
    games = (x.groupby(["season", "week", "team", "opponent_team"])[st].sum().reset_index()
             .rename(columns={"team": "off", "opponent_team": "de", st: "val"}))
    for season, g in games.groupby("season"):
        for wk in range(6, 19):
            prior, cur = g[g.week < wk], g[g.week == wk]
            if cur.empty:
                continue
            # each offense's usual in its OTHER earlier games (leave the game itself out)
            tot = prior.groupby("off").val.agg(["sum", "count"])
            p = prior.join(tot, on="off")
            p = p[p["count"] >= 2].copy()
            p["usual"] = (p["sum"] - p.val) / (p["count"] - 1)
            win = p[p.week >= wk - WINDOW]
            d = win.groupby("de").agg(n=("val", "size"), allowed=("val", "sum"), usual=("usual", "sum"))
            d = d[(d.n >= MIN_GAMES) & (d.usual > 0)]
            if len(d) < 24:
                continue
            d["raw"] = d.allowed / d.n
            d["adj"] = d.allowed / d.usual
            d["raw_rank"] = d.raw.rank(method="first")
            d["adj_rank"] = d.adj.rank(method="first")
            d["sched"] = (d.usual / d.n) / (d.usual.sum() / d.n.sum())  # >1 = faced stronger offenses
            off_usual = tot[tot["count"] >= MIN_OFF_GAMES].assign(u=lambda t: t["sum"] / t["count"]).u
            for _, c in cur.iterrows():
                if c.de not in d.index or c.off not in off_usual.index or off_usual[c.off] <= 0:
                    continue
                r = d.loc[c.de]
                out.append(dict(stat=f"{pos} {st}", season=season, week=wk, n_def=len(d), raw_rank=r.raw_rank, adj_rank=r.adj_rank,
                                sched=r.sched, outcome=c.val / off_usual[c.off]))

r = pd.DataFrame(out)
# ranks as 0..1 so weeks with fewer ranked defenses line up
r["raw_p"] = (r.raw_rank - 1) / (r.n_def - 1)
r["adj_p"] = (r.adj_rank - 1) / (r.n_def - 1)


def bucket(p):
    return "1 toughest quarter" if p < 0.25 else "2" if p < 0.5 else "3" if p < 0.75 else "4 softest quarter"


def spearman(a, b):
    return np.corrcoef(a.rank(), b.rank())[0, 1]


def report(s, name):
    print(f"\n=== {name}: {len(s)} defense-games ===")
    print(f"  lines up with what happened (Spearman, higher = better): Opp Rank {spearman(s.raw_p, s.outcome):+.3f}   Adj Rank {spearman(s.adj_p, s.outcome):+.3f}")
    a = s.groupby(s.raw_p.map(bucket)).outcome.mean().round(3)
    b = s.groupby(s.adj_p.map(bucket)).outcome.mean().round(3)
    print("  allowed vs the offense's usual, by quarter of the rank:")
    print(pd.DataFrame({"by Opp Rank": a, "by Adj Rank": b}).to_string().replace("\n", "\n    "))
    # both together: which one carries the weight
    X = np.column_stack([np.ones(len(s)), s.raw_p - 0.5, s.adj_p - 0.5])
    beta = np.linalg.lstsq(X, s.outcome.to_numpy(), rcond=None)[0]
    print(f"  both in one fit (effect of going from toughest to softest): Opp Rank {beta[1]:+.3f}   Adj Rank {beta[2]:+.3f}")
    gap = (s.raw_rank - s.adj_rank)
    soft_raw = s[(gap >= GAP) & (s.raw_p >= 0.75)]    # looks soft, but faced strong offenses
    tough_raw = s[(gap <= -GAP) & (s.raw_p < 0.25)]   # looks tough, but faced weak offenses
    agree_soft = s[(gap.abs() < GAP / 2) & (s.raw_p >= 0.75)]
    agree_tough = s[(gap.abs() < GAP / 2) & (s.raw_p < 0.25)]
    for label, t in (("Opp Rank says SOFT (bottom quarter), Adj Rank 8+ spots tougher", soft_raw),
                     ("  ...both say soft", agree_soft),
                     ("Opp Rank says TOUGH (top quarter), Adj Rank 8+ spots softer", tough_raw),
                     ("  ...both say tough", agree_tough)):
        if len(t):
            print(f"  {label}: n={len(t)}, allowed {t.outcome.mean():.3f}x the offense's usual (median {t.outcome.median():.3f})")


report(r, "ALL STATS")
for stat, s in r.groupby("stat"):
    report(s, stat)
print("\nBy era (all stats):")
for label, s in (("2019-2022", r[r.season <= 2022]), ("2023-2025", r[r.season >= 2023])):
    print(f"  {label}: n={len(s)}  Spearman Opp Rank {spearman(s.raw_p, s.outcome):+.3f}  Adj Rank {spearman(s.adj_p, s.outcome):+.3f}")
