"""
Part 3 of the Ladder backtest: does man/zone coverage add anything?

nflverse play-by-play + participation data mark each pass play MAN or ZONE
(2023-2025; 2026 isn't published yet). For each receiver, last season's
yards per target vs man and vs zone (shrunk toward league rates, 25
targets of prior) gives his "man lean". Each defense's man rate is taken
from this season's plays before the game. Fit = man lean x (defense man rate
- league man rate). Tested on 2024 and 2025 receiving rows from
ladder_bt.pkl, on top of the Part 2 model (refit on 2019-2023).
    python3 scripts/backtest_ladder_coverage.py <bt dir> <coverage dir>
"""
import sys

import numpy as np
import pandas as pd

BT, CV = sys.argv[1], sys.argv[2]


def plays(y):
    p = pd.read_csv(f"{CV}/pbp{y}.csv.gz", low_memory=False,
                    usecols=["game_id", "play_id", "week", "season_type", "defteam", "receiver_player_id",
                             "pass_attempt", "sack", "two_point_attempt", "receiving_yards"])
    p = p[(p.season_type == "REG") & (p.pass_attempt == 1) & (p.sack != 1) & (p.two_point_attempt != 1)]
    c = pd.read_csv(f"{CV}/part{y}.csv", usecols=["nflverse_game_id", "play_id", "defense_man_zone_type"])
    m = p.merge(c, left_on=["game_id", "play_id"], right_on=["nflverse_game_id", "play_id"], how="inner")
    m = m[m.defense_man_zone_type.isin(["MAN_COVERAGE", "ZONE_COVERAGE"])]
    m["man"] = (m.defense_man_zone_type == "MAN_COVERAGE").astype(int)
    m["receiving_yards"] = m.receiving_yards.fillna(0)
    return m


P = {y: plays(y) for y in (2023, 2024, 2025)}
for y, m in P.items():
    print(f"{y}: {len(m):,} charted pass plays, man rate {m.man.mean():.3f}")


def man_lean(m, K=25):
    t = m.dropna(subset=["receiver_player_id"])
    lg = t.groupby("man").receiving_yards.mean()
    g = t.groupby(["receiver_player_id", "man"]).receiving_yards.agg(["sum", "count"]).unstack(fill_value=0)
    ypt_man = (g[("sum", 1)] + K * lg[1]) / (g[("count", 1)] + K)
    ypt_zone = (g[("sum", 0)] + K * lg[0]) / (g[("count", 0)] + K)
    return (np.log(ypt_man / lg[1]) - np.log(ypt_zone / lg[0])).rename("lean")


df = pd.read_pickle(f"{BT}/ladder_bt.pkl")
rows = []
for y in (2024, 2025):
    lean = man_lean(P[y - 1])
    m = P[y]
    lg_man = m.man.mean()
    sub = df[(df.season == y) & df.stat.isin(["receiving_yards", "receptions"])].copy()
    dm = {}
    for W in sub.week.unique():
        pr = m[m.week < W].groupby("defteam").man.agg(["mean", "count"])
        dm[W] = ((pr["count"] * pr["mean"] + 150 * lg_man) / (pr["count"] + 150)).to_dict()  # shrink: 150 plays of league avg
    sub["lean"] = sub.player_id.map(lean).fillna(0)
    sub["def_man"] = [dm.get(W, {}).get(o, lg_man) for W, o in zip(sub.week, sub.opp)]
    sub["fit"] = sub.lean * (sub.def_man - lg_man) * 10
    rows.append(sub)
t = pd.concat(rows)
print(f"\nReceiving rows 2024-25: {len(t):,}, with a prior-season man/zone split: {(t.lean != 0).mean():.2f}")
t["q"] = pd.qcut(t.fit.rank(method="first"), 5, labels=["Q1 bad fit", "Q2", "Q3", "Q4", "Q5 good fit"])
print(t.groupby("q", observed=True).agg(fit_lo=("fit", "min"), fit_hi=("fit", "max"), n=("goff", "size"), goff=("goff", "mean")).round(3).to_string())
for s, g in t.groupby("stat"):
    c = np.corrcoef(g.fit, g.goff)[0, 1]
    print(f"  {s}: correlation of fit with go-off {c:+.3f}")
