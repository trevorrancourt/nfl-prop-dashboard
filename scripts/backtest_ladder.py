"""
Backtest for the Ladder board (2026-11-09, per Trevor: ladders are 10-yard
rungs -- 40+, 50+, 60+ -- and a player "goes off" when he climbs several
rungs past his line, e.g. a 75.5 line to ~120, a 30.5 line to ~80).

Part 1 (this file): builds a pre-game snapshot for every player/stat/week in
2019-2025 regular seasons (weeks 5-18, 3+ earlier games that season) with
only what was known before kickoff, plus whether he went off.

  line  = his prior season median, on the .5 (no old prop lines exist)
  go-off = actual >= line + GO_OFF_GAP (yards: max(40, 0.6 x line);
           pass yards: max(75, 0.3 x line); receptions: max(3, 0.6 x line))

Features:
  form      0.6 x last-4 avg + 0.4 x season avg, over the line
  def_ratio what this week's opponent allows to his position in that stat
            (season to date) / league average, shrunk toward 1
  total, fav  Vegas total and his team's spread (+ = favored)
  usage     last-2 volume (targets / carries / attempts) over his season avg
  cv        his game-to-game swing (sd / mean); best = season high / line
  boom      share of his games that already went off at today's gap

Writes <dir>/ladder_bt.pkl and prints base rates and how each feature
separates go-off games.
    python3 scripts/backtest_ladder.py <dir with games.csv + w2019..w2025.csv>
"""
import math
import sys

import numpy as np
import pandas as pd

D = sys.argv[1]
SEASONS = range(2019, 2026)
SETS = [  # (stat, positions, volume column)
    ("receiving_yards", ["WR", "TE", "RB"], "targets"),
    ("receptions", ["WR", "TE", "RB"], "targets"),
    ("rushing_yards", ["RB", "QB"], "carries"),
    ("passing_yards", ["QB"], "attempts"),
]


def gap(stat, line):
    if stat == "passing_yards":
        return max(75.0, 0.3 * line)
    if stat == "receptions":
        return max(3.0, 0.6 * line)
    return max(40.0, 0.6 * line)


g = pd.read_csv(f"{D}/games.csv")
g = g[g.season.between(2019, 2025) & (g.game_type == "REG")]
spread = {}
for _, x in g.iterrows():
    spread[(x.season, x.week, x.home_team)] = (x.total_line, x.spread_line)
    spread[(x.season, x.week, x.away_team)] = (x.total_line, -x.spread_line if pd.notna(x.spread_line) else np.nan)

cols = ["player_id", "player_display_name", "position", "season", "week", "season_type", "team", "opponent_team",
        "targets", "receptions", "receiving_yards", "carries", "rushing_yards", "attempts", "passing_yards"]
w = pd.concat([pd.read_csv(f"{D}/w{y}.csv", usecols=cols) for y in SEASONS])
w = w[w.season_type == "REG"].fillna(0)
rng = np.random.default_rng(11)
out = []
for stat, poss, vol in SETS:
    for pos in poss:
        x = w[w.position == pos]
        allowed = x.groupby(["season", "week", "opponent_team"])[stat].sum().reset_index()
        for season in SEASONS:
            xs = x[x.season == season]
            al = allowed[allowed.season == season]
            for W in range(5, 19):
                cur = xs[xs.week == W]
                if cur.empty:
                    continue
                prior = xs[xs.week < W]
                a_prior = al[al.week < W]
                d_avg = a_prior.groupby("opponent_team")[stat].agg(["mean", "count"])
                lg = d_avg["mean"].mean() if len(d_avg) else np.nan
                gp = prior.groupby("player_id")
                for _, row in cur.iterrows():
                    pid = row.player_id
                    if pid not in gp.groups:
                        continue
                    pa = gp.get_group(pid).sort_values("week")
                    if len(pa) < 3:
                        continue
                    vals = pa[stat].to_numpy(dtype=float)
                    savg = vals.mean()
                    if savg < (1.5 if stat == "receptions" else 15):
                        continue
                    med = float(np.median(vals))
                    line = math.floor(med) + (0.5 if rng.random() < 0.5 else -0.5)
                    line = max(line, 0.5)
                    G = gap(stat, line)
                    last4 = vals[-4:].mean()
                    form = 0.6 * last4 + 0.4 * savg
                    v = pa[vol].to_numpy(dtype=float)
                    usage = (v[-2:].mean() / v.mean()) if v.mean() > 0 else 1.0
                    sd = vals.std(ddof=1)
                    opp = row.opponent_team
                    if opp in d_avg.index and lg and lg > 0:
                        m, n = d_avg.loc[opp, "mean"], d_avg.loc[opp, "count"]
                        def_ratio = (n * (m / lg) + 3 * 1.0) / (n + 3)  # shrink toward 1 (3 games of "average")
                    else:
                        def_ratio = 1.0
                    tot, fav = spread.get((season, W, row.team), (np.nan, np.nan))
                    actual = float(row[stat])
                    out.append(dict(
                        stat=stat, pos=pos, season=season, week=W, player=row.player_display_name, player_id=pid, opp=row.opponent_team,
                        line=line, gap=G, form=form / max(line, 0.5), def_ratio=def_ratio,
                        total=tot, fav=fav, usage=usage, cv=sd / savg if savg else 0,
                        best=vals.max() / max(line, 0.5), boom=float((vals >= line + G).mean()), n=len(vals),
                        actual=actual, goff=int(actual >= line + G),
                    ))
df = pd.DataFrame(out)
df.to_pickle(f"{D}/ladder_bt.pkl")
print(f"{len(df):,} player-games; go-off rate {df.goff.mean():.3f}")
print(df.groupby("stat").goff.agg(["count", "mean"]).round(3).to_string())


def lift(col, q=5):
    t = df.dropna(subset=[col]).copy()
    t["b"] = pd.qcut(t[col].rank(method="first"), q, labels=[f"Q{i+1}" for i in range(q)])
    return t.groupby("b", observed=True).agg(lo=(col, "min"), hi=(col, "max"), n=("goff", "size"), rate=("goff", "mean")).round(3)


for col in ["form", "def_ratio", "total", "fav", "usage", "cv", "best", "boom"]:
    print(f"\n{col} (Q1 = lowest) -> go-off rate")
    print(lift(col).to_string())
