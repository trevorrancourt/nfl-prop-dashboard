# Part 2 of scripts/backtest_win_model.py (run that first): per-stat weights fit on 2019-23, tested on 2024-25.
import pandas as pd, numpy as np, math, sys
df=pd.read_pickle(sys.argv[1]+"/winbt.pkl")
lg=lambda p: np.log(p/(1-p))
df["lm"]=lg(df.p_model); df["lh"]=lg(df.p_hit)
def fit(X,y):
    b=np.zeros(X.shape[1])
    for _ in range(50):
        p=1/(1+np.exp(-X@b)); b+=np.linalg.solve((X*(p*(1-p))[:,None]).T@X+1e-6*np.eye(len(b)), X.T@(y-p))
    return b
ll=lambda p,y: -np.mean(y*np.log(p)+(1-y)*np.log(1-p))
tr=df[df.season<=2023]; te=df[df.season>=2024]
cur=1/(1+np.exp(-(0.35*te.lm+0.5*te.lh)))
print("test 2024-25 log loss: coin 0.6931 | current", round(ll(cur,te.over),4))
for shrink in (1.0,0.75):
    ps=np.zeros(len(te)); W={}
    for s,g in tr.groupby("stat"):
        b=fit(np.column_stack([g.lm,g.lh]),g.over.to_numpy())  # no intercept: the market sets the base
        b=np.clip(b,0,None)*shrink; W[s]=b.round(2)
        m=(te.stat==s).to_numpy(); t=te[m]; ps[m]=1/(1+np.exp(-(b[0]*t.lm+b[1]*t.lh)))
    print(f"per-stat x{shrink}:", round(ll(ps,te.over),4), {k:list(v) for k,v in W.items()})
    if shrink==1.0:
        t=pd.DataFrame({"p":ps,"y":te.over.to_numpy()}); t["b"]=pd.cut(t.p,[0,.3,.4,.45,.5,.55,.6,.7,1])
        print(t.groupby("b",observed=True).agg(n=("y","size"),said=("p","mean"),won=("y","mean")).round(3).to_string())
