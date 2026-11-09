"""
Part 2 of the Ladder backtest (run scripts/backtest_ladder.py first).

One logistic model for "does he reach threshold T?", trained on every rung
(T = line + k x step, k = 0..6; step 10 yards, 25 pass yards, 1 catch), so
the same model prices every rung of a ladder. Fit on 2019-2023, tested on
2024-2025. Prints:
  - the fitted weights (to copy into the page as LADDER_COEF)
  - calibration by rung (predicted vs actual hit rate)
  - top-decile lift on the go-off event vs everyone else
    python3 scripts/backtest_ladder_model.py <dir>
"""
import json
import sys

import numpy as np
import pandas as pd

D = sys.argv[1]
df = pd.read_pickle(f"{D}/ladder_bt.pkl")
# Vacated teammate volume (Part 4, scripts/backtest_ladder_vacated.py); 0 for passing rows.
vac = pd.read_pickle(f"{D}/ladder_vac.pkl")
df = df.merge(vac, on=["season", "week", "player_id", "stat"], how="left")
df["vacated"] = df.vacated.fillna(0)
STEP = {"receiving_yards": 10, "rushing_yards": 10, "passing_yards": 25, "receptions": 1}
C = {"receiving_yards": 10, "rushing_yards": 10, "passing_yards": 25, "receptions": 1}  # log offset
STATS = list(STEP)
FEATS = ["dist", "dist2", "dist3", "form", "defr", "usage", "best", "boom", "dist_cv", "dist_boom"]


def features(d, k):
    t = d.line + k * d.stat.map(STEP)
    c = d.stat.map(C)
    dist = np.log((t + c) / (d.line + c))
    X = pd.DataFrame({
        "dist": dist, "dist2": dist ** 2, "dist3": dist ** 3,
        "dist_form": dist * np.log(d.form.clip(0.2, 5)),
        "form": np.log(d.form.clip(0.2, 5)), "defr": np.log(d.def_ratio.clip(0.5, 2)),
        "usage": np.log(d.usage.clip(0.3, 3)), "best": np.log(d.best.clip(0.5, 20)),
        "boom": d.boom, "vac": d.vacated.clip(0, 0.6), "dist_vac": dist * d.vacated.clip(0, 0.6), "dist_cv": dist * d.cv.clip(0, 2), "dist_boom": dist * d.boom,
    })
    for s in STATS:
        X["is_" + s] = (d.stat == s).astype(float)
        X["dist_" + s] = dist * X["is_" + s]
    return X, (d.actual >= t).astype(float)


def stack(d):
    Xs, ys, ks = [], [], []
    for k in range(0, 7):
        X, y = features(d, k)
        Xs.append(X); ys.append(y); ks.append(np.full(len(X), k))
    return pd.concat(Xs, ignore_index=True), pd.concat(ys, ignore_index=True), np.concatenate(ks)


def fit(X, y, l2=1.0, iters=60):
    A = X.to_numpy(); yy = y.to_numpy()
    b = np.zeros(A.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-A @ b))
        H = (A * (p * (1 - p))[:, None]).T @ A + l2 * np.eye(len(b))
        b += np.linalg.solve(H, A.T @ (yy - p) - l2 * b)
    return b


tr, te = df[df.season <= 2023], df[df.season >= 2024]
Xtr, ytr, _ = stack(tr)
b = fit(Xtr, ytr)
coef = dict(zip(Xtr.columns, b.round(4)))
print("LADDER_COEF =", json.dumps(coef))

Xte, yte, kte = stack(te)
p = 1 / (1 + np.exp(-Xte.to_numpy() @ b))
ll = -np.mean(yte * np.log(p) + (1 - yte) * np.log(1 - p))
base = pd.Series(yte).groupby(kte).transform("mean").to_numpy()
llb = -np.mean(yte * np.log(base) + (1 - yte) * np.log(1 - base))
print(f"\nTest 2024-25: log loss {ll:.4f} vs rung base rates {llb:.4f}")
t = pd.DataFrame({"k": kte, "p": p, "y": yte})
print("\nBy rung (k steps above the line): predicted vs actual")
print(t.groupby("k").agg(pred=("p", "mean"), actual=("y", "mean"), n=("y", "size")).round(3).to_string())
t["b"] = pd.cut(t.p, [0, .05, .1, .2, .3, .5, .7, .9, 1])
print("\nCalibration (all rungs):")
print(t.groupby("b", observed=True).agg(n=("y", "size"), said=("p", "mean"), won=("y", "mean")).round(3).to_string())

# Go-off event = the rung at line + gap, i.e. the model's chance at that threshold.
te = te.copy()
Xg, _ = features(te.assign(), 0)
c = te.stat.map(C)
distg = np.log((te.line + te.gap + c) / (te.line + c))
Xg["dist"] = distg; Xg["dist2"] = distg ** 2; Xg["dist3"] = distg ** 3; Xg["dist_form"] = distg * Xg["form"]; Xg["dist_vac"] = distg * Xg["vac"]; Xg["dist_cv"] = distg * te.cv.clip(0, 2); Xg["dist_boom"] = distg * te.boom
for s in STATS:
    Xg["dist_" + s] = distg * Xg["is_" + s]
te["p_goff"] = 1 / (1 + np.exp(-Xg[Xtr.columns].to_numpy() @ b))
te["dec"] = te.groupby("stat").p_goff.transform(lambda s: pd.qcut(s.rank(method="first"), 10, labels=False))
print("\nGo-off rate by model decile (test seasons, within each stat; 9 = top 10%):")
print(te.groupby("dec").agg(said=("p_goff", "mean"), actual=("goff", "mean"), n=("goff", "size")).round(3).to_string())
for s, g in te.groupby("stat"):
    top = g[g.dec == 9].goff.mean(); rest = g[g.dec < 9].goff.mean()
    print(f"  {s:16s} top 10% {top:.3f} vs rest {rest:.3f}  (x{top / rest:.2f})")
# Per week: the top 10 on a weekly "Ladder board" across all stats
wk = te.sort_values("p_goff", ascending=False).groupby(["season", "week"]).head(10)
print(f"\nWeekly top-10 ladder board, 2024-25: {wk.goff.mean():.3f} went off (base {te.goff.mean():.3f}), {len(wk)} picks")

# Production weights: refit on every season (2019-2025) for the page.
Xall, yall, _ = stack(df)
print("\nLADDER_COEF_ALL =", json.dumps(dict(zip(Xall.columns, fit(Xall, yall).round(4)))))
