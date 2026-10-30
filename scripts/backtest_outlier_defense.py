# Backtest (2026-10-30): do the softest/toughest defenses keep allowing more? Part 1 writes <dir>/defz.pkl.
import pandas as pd, numpy as np, sys
d=sys.argv[1]
cols=["player_id","position","season","week","season_type","team","opponent_team","passing_yards","rushing_yards","carries","receiving_yards","receptions","targets"]
w=pd.concat([pd.read_csv(f"{d}/w{y}.csv",usecols=cols) for y in range(2019,2026)])
w=w[(w.season_type=="REG")].fillna(0)
STATS=[("QB","passing_yards"),("RB","rushing_yards"),("RB","receiving_yards"),("WR","receiving_yards"),("WR","receptions"),("TE","receiving_yards"),("TE","receptions")]
res=[]; pres=[]
for pos,st in STATS:
    x=w[w.position==pos]
    # defense allowed per game (sum over position)
    da=x.groupby(["season","week","opponent_team"])[st].sum().reset_index().rename(columns={"opponent_team":"def"})
    for season,g in da.groupby("season"):
        for wk in range(6,19):
            prior=g[g.week<wk]; cur=g[g.week==wk]
            if cur.empty: continue
            for label,pr in (("season",prior),("last4",prior[prior.week>=wk-4])):
                m=pr.groupby("def")[st].agg(["mean","count"])
                m=m[m["count"]>=3]
                if len(m)<28: continue
                mu,sd=m["mean"].mean(),m["mean"].std()
                m["z"]=(m["mean"]-mu)/sd
                m["rank"]=m["mean"].rank(ascending=False,method="first")
                lg=cur[st].mean()
                for de,row in m.iterrows():
                    c=cur[cur["def"]==de]
                    if c.empty: continue
                    res.append(dict(stat=f"{pos} {st}",window=label,z=row.z,rank=row["rank"],ratio=c[st].iloc[0]/lg if lg else np.nan,season=season,week=wk,de=de))
r=pd.DataFrame(res)
def zb(z):
    return "z>=2" if z>=2 else "1.5-2" if z>=1.5 else "1-1.5" if z>=1 else "0-1" if z>=0 else "<0"
r["zb"]=r.z.apply(zb)
def rb(k):
    return "rank 1-3" if k<=3 else "4-10" if k<=10 else "11-22" if k<=22 else "23-32"
r["rb"]=r["rank"].apply(rb)
for win in ("season","last4"):
    s=r[r.window==win]
    print(f"\n==== defense ranked on {win} games (weeks 6-18, 2019-2025) -> what it allowed THIS week vs league avg ====")
    print(s.groupby("rb").ratio.agg(["count","mean"]).round(3).to_string())
    print(s.groupby("zb").ratio.agg(["count","mean"]).round(3).to_string())
r.to_pickle(f"{d}/defz.pkl")
