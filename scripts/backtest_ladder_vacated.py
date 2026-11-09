"""
Part 4 of the Ladder backtest: does a teammate being out help?

"Vacated volume" = targets (receiving rows) or carries (rushing rows) per
game that teammates averaged earlier in the season but who didn't play this
week, as a share of the team's per-game total. On the live board the same
idea uses the injury report (Out / Doubtful) instead of "didn't play".
    python3 scripts/backtest_ladder_vacated.py <bt dir>
"""
import sys

import numpy as np
import pandas as pd

D = sys.argv[1]
cols = ["player_id", "position", "season", "week", "season_type", "team", "targets", "carries"]
w = pd.concat([pd.read_csv(f"{D}/w{y}.csv", usecols=cols) for y in range(2019, 2026)])
w = w[(w.season_type == "REG") & w.position.isin(["WR", "TE", "RB", "QB"])].fillna(0)
df = pd.read_pickle(f"{D}/ladder_bt.pkl")
df = df[df.stat != "passing_yards"].copy()
team_of = w.set_index(["season", "week", "player_id"]).team.to_dict()
vac = []
cache = {}
for r in df.itertuples():
    vol = "carries" if r.stat == "rushing_yards" else "targets"
    team = team_of.get((r.season, r.week, r.player_id))
    key = (r.season, r.week, team, vol)
    if key not in cache:
        tw = w[(w.season == r.season) & (w.team == team)]
        prior = tw[tw.week < r.week]
        played_now = set(tw[tw.week == r.week].player_id)
        per = prior.groupby("player_id")[vol].sum() / max(prior.week.nunique(), 1)
        team_pg = per.sum()
        gone = per[[p not in played_now for p in per.index]]
        gone = gone[gone >= (2 if vol == "carries" else 3)]  # only teammates with a real role
        cache[key] = float(gone.sum() / team_pg) if team_pg else 0.0
    vac.append(cache[key])
df["vacated"] = vac
df["b"] = pd.cut(df.vacated, [-0.01, 0.0, 0.1, 0.2, 1.0], labels=["none", "0-10%", "10-20%", "20%+"])
print(df.groupby(["b"], observed=True).agg(n=("goff", "size"), goff=("goff", "mean")).round(3).to_string())
print(df.groupby(["stat", "b"], observed=True).agg(n=("goff", "size"), goff=("goff", "mean")).round(3).to_string())
df[["season", "week", "player_id", "stat", "vacated"]].to_pickle(f"{D}/ladder_vac.pkl")
