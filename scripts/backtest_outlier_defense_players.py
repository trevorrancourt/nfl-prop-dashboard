# Backtest part 2 (2026-10-30): player beats his own season average, by opponent season rank. Run backtest_outlier_defense.py first.
import pandas as pd, numpy as np, sys
d=sys.argv[1]
r=pd.read_pickle(f"{d}/defz.pkl"); r=r[r.window=="season"]
cols=["player_id","position","season","week","season_type","team","opponent_team","passing_yards","rushing_yards","receiving_yards","receptions"]
w=pd.concat([pd.read_csv(f"{d}/w{y}.csv",usecols=cols) for y in range(2019,2026)])
w=w[w.season_type=="REG"].fillna(0).sort_values(["season","week"])
STATS=[("QB","passing_yards"),("RB","rushing_yards"),("RB","receiving_yards"),("WR","receiving_yards"),("WR","receptions"),("TE","receiving_yards"),("TE","receptions")]
out=[]
for pos,st in STATS:
    x=w[w.position==pos].copy()
    x["prior_avg"]=x.groupby(["season","player_id"])[st].transform(lambda s:s.shift().expanding().mean())
    x["n"]=x.groupby(["season","player_id"]).cumcount()
    x=x[(x.n>=3)&(x.prior_avg>=(150 if pos=="QB" else 3 if st=="receptions" else 20))]
    rr=r[r.stat==f"{pos} {st}"][["season","week","de","rank","z"]]
    m=x.merge(rr,left_on=["season","week","opponent_team"],right_on=["season","week","de"])
    m["over"]=m[st]>m.prior_avg
    m["stat"]=f"{pos} {st}"
    out.append(m[["stat","rank","z","over"]])
o=pd.concat(out)
o["b"]=pd.cut(o["rank"],[0,3,5,10,22,32],labels=["1-3","4-5","6-10","11-22","23-32"])
print("Player beats his own season average, by opponent's season rank (1 = allows the most):")
t=o.groupby("b",observed=True).over.agg(["count","mean"]); print(t.round(3).to_string())
o["zb"]=pd.cut(o.z,[-9,0,1,1.5,2,9],labels=["<0","0-1","1-1.5","1.5-2","2+"])
print(o.groupby("zb",observed=True).over.agg(["count","mean"]).round(3).to_string())
print("\nBy stat, rank 1-3 vs 4-10:")
o["g"]=np.where(o["rank"]<=3,"1-3",np.where(o["rank"]<=10,"4-10","other"))
print(o.groupby(["stat","g"]).over.mean().unstack().round(3).to_string())
