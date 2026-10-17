# Backtest (2026-10-17): RB carries vs spread, 2019-2025. Usage: python3 scripts/backtest_rb_spread.py <dir with games.csv + w2019..w2025.csv from nflverse>
import pandas as pd, numpy as np, sys
d = sys.argv[1]
g = pd.read_csv(f"{d}/games.csv")
g = g[(g.season.between(2019,2025)) & (g.game_type=="REG") & g.result.notna() & g.spread_line.notna()]
# team-game rows: favored-by and margin
rows=[]
for _,x in g.iterrows():
    rows.append((x.game_id,x.home_team,x.spread_line,x.result))
    rows.append((x.game_id,x.away_team,-x.spread_line,-x.result))
tg = pd.DataFrame(rows,columns=["game_id","team","fav_by","margin"])
w = pd.concat([pd.read_csv(f"{d}/w{y}.csv",usecols=["player_id","player_display_name","position","season","week","season_type","game_id","team","carries","rushing_yards"]) for y in range(2019,2026)])
w = w[(w.season_type=="REG") & (w.position=="RB")].copy()
w["carries"]=w.carries.fillna(0); w["rushing_yards"]=w.rushing_yards.fillna(0)
w = w.sort_values(["season","week"])
out=[]
for (season,team),grp in w.groupby(["season","team"]):
    weeks = sorted(grp.week.unique())
    for wk in weeks:
        prior = grp[grp.week<wk]
        if prior.week.nunique()<3: continue
        tot = prior.groupby("player_id").carries.sum().sort_values(ascending=False)
        if len(tot)<2: continue
        cur = grp[grp.week==wk]
        gid = cur.game_id.iloc[0]
        for role,pid in (("lead",tot.index[0]),("backup",tot.index[1])):
            pp = prior[prior.player_id==pid]
            if len(pp)<3: continue
            c = cur[cur.player_id==pid]
            if c.empty: continue   # didn't play (injury etc.) -> skip, like a voided prop
            out.append(dict(season=season,team=team,week=wk,game_id=gid,role=role,name=c.player_display_name.iloc[0],
                            avg_c=pp.carries.mean(),avg_y=pp.rushing_yards.mean(),c=c.carries.iloc[0],y=c.rushing_yards.iloc[0]))
o = pd.DataFrame(out).merge(tg,on=["game_id","team"])
o = o[o.avg_c>=2]
def bucket(f):
    if f<=0: return "a) dog/pick"
    if f<4: return "b) fav 0.5-3.5"
    if f<7: return "c) fav 4-6.5"
    if f<10: return "d) fav 7-9.5"
    return "e) fav 10+"
o["b"]=o.fav_by.apply(bucket)
o["blow"]=o.margin>=17
for role in ("backup","lead"):
    s=o[o.role==role]
    print(f"\n=== {role} RB (by carries so far this season), 2019-2025 ===")
    print(f"{'spread':16}{'games':>7}{'won17+':>8}{'carries vs avg':>16}{'Under avg carries':>19}{'Under avg yds':>15}")
    for b,x in s.groupby("b"):
        print(f"{b:16}{len(x):7}{x.blow.mean():8.0%}{(x.c/x.avg_c).mean():16.2f}{(x.c<x.avg_c).mean():19.0%}{(x.y<x.avg_y).mean():15.0%}")
    x=s[s.b.str.startswith("d")]
    print("  7-9.5 split:  blowout games carries-vs-avg %.2f (n=%d) | non-blowout %.2f (n=%d)"%((x[x.blow].c/x[x.blow].avg_c).mean(),x.blow.sum(),(x[~x.blow].c/x[~x.blow].avg_c).mean(),(~x.blow).sum()))
