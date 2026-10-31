"""
Backtest (2026-10-31): is the Win % model's projection honest?

Replays 2019-2025 regular seasons week by week. For every player/stat with
3+ earlier games this season (2+ in the last 4 weeks), it builds the same
projection the board's winChance() uses -- 60% last-4 / 40% season form,
blended 65/35 with share x what this opponent allowed over its last 4
(clamped to 0.6-1.4x form), Poisson / normal / gamma by stat with the
0.85/1/1.15 smear -- and the season hit-rate estimate. There are no old
prop lines, so the "line" is the player's prior season median, put on the
.5 above or below it at random (no built-in Over/Under lean).

Prints calibration tables (predicted vs actual Over rate) and fits how much
weight the model and hit rate deserve (logistic regression on their
log-odds). Usage:
    python3 scripts/backtest_win_model.py <dir with w2019.csv..w2025.csv>
"""
import math
import sys

import numpy as np
import pandas as pd

D = sys.argv[1]
SEASONS = range(2019, 2026)
STATS = {  # stat -> positions
    "receptions": ["WR", "TE", "RB"], "receiving_yards": ["WR", "TE", "RB"],
    "rushing_yards": ["RB", "QB"], "carries": ["RB"],
    "passing_yards": ["QB"], "completions": ["QB"], "attempts": ["QB"],
}
POISSON = {"receptions", "targets"}
NORMAL = {"attempts", "completions", "carries"}
CV = {"passing_yards": 0.28, "rushing_yards": 0.55, "receiving_yards": 0.65}
HIT_PRIOR = 12


def gammaln(x):
    return math.lgamma(x)


def gammap(a, x):
    if x <= 0:
        return 0.0
    gln = gammaln(a)
    if x < a + 1:
        ap, s, d = a, 1 / a, 1 / a
        for _ in range(300):
            ap += 1; d *= x / ap; s += d
            if abs(d) < abs(s) * 1e-10:
                break
        return s * math.exp(-x + a * math.log(x) - gln)
    b, c, dd = x + 1 - a, 1e300, 1 / (x + 1 - a)
    h = dd
    for i in range(1, 300):
        an = -i * (i - a); b += 2
        dd = an * dd + b; dd = dd if abs(dd) > 1e-300 else 1e-300
        c = b + an / c; c = c if abs(c) > 1e-300 else 1e-300
        dd = 1 / dd; de = dd * c; h *= de
        if abs(de - 1) < 1e-10:
            break
    return 1 - math.exp(-x + a * math.log(x) - gln) * h


def ncdf(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def p_over1(stat, mu, sd, line):
    if mu <= 0:
        return None
    if stat in POISSON:
        term, below, cdf = math.exp(-mu), 0.0, 0.0
        for k in range(0, int(max(60, line * 3)) + 1):
            if k > 0:
                term *= mu / k
            if k < line:
                below += term
            cdf += term
        return max(0.0, cdf - below) / cdf
    if stat in NORMAL:
        s = max(sd, math.sqrt(mu), 0.5)
        return 1 - ncdf((line - mu) / s)
    s = max(sd, mu * 0.15)
    k, th = (mu / s) ** 2, s * s / mu
    return 1 - gammap(k, max(line, 0) / th)


def p_over(stat, mu, sd, line):
    tot = 0.0
    for f, w in ((0.85, 0.25), (1, 0.5), (1.15, 0.25)):
        x = p_over1(stat, mu * f, sd, line)
        if x is None:
            return None
        tot += w * x
    return tot


clip = lambda p: min(0.97, max(0.03, p))
logit = lambda p: math.log(p / (1 - p))

cols = ["player_id", "position", "season", "week", "season_type", "team", "opponent_team"] + sorted({s for s in STATS} | {"targets"})
w = pd.concat([pd.read_csv(f"{D}/w{y}.csv", usecols=cols) for y in SEASONS])
w = w[w.season_type == "REG"].fillna(0)
rng = np.random.default_rng(7)
out = []
for stat, poss in STATS.items():
    for pos in poss:
        x = w[w.position == pos][["player_id", "season", "week", "team", "opponent_team", stat]]
        team_tot = x.groupby(["season", "week", "team"])[stat].sum().rename("team_tot")
        def_tot = x.groupby(["season", "week", "opponent_team"])[stat].sum().rename("allowed")
        x = x.join(team_tot, on=["season", "week", "team"])
        for season in SEASONS:
            xs = x[x.season == season]
            ds = def_tot.loc[season] if season in def_tot.index.get_level_values(0) else None
            if ds is None:
                continue
            ds = ds.reset_index()
            for W in range(5, 19):
                cur = xs[xs.week == W]
                if cur.empty:
                    continue
                prior = xs[xs.week < W]
                last4 = prior[prior.week >= W - 4]
                dl4 = ds[(ds.week < W) & (ds.week >= W - 4)].groupby("opponent_team").allowed.mean()
                g_all = prior.groupby("player_id")
                g_l4 = last4.groupby("player_id")
                for _, row in cur.iterrows():
                    pid = row.player_id
                    if pid not in g_all.groups or pid not in g_l4.groups:
                        continue
                    pa = g_all.get_group(pid)
                    pl = g_l4.get_group(pid)
                    if len(pa) < 3 or len(pl) < 2:
                        continue
                    vals = pa[stat].to_numpy()
                    savg, ravg = vals.mean(), pl[stat].mean()
                    if savg <= 0:
                        continue
                    form = 0.6 * ravg + 0.4 * savg
                    tt = pl.team_tot.sum()
                    share = pl[stat].sum() / tt if tt > 0 else None
                    allowed = dl4.get(row.opponent_team)
                    ant = share * allowed if (share is not None and allowed is not None and not math.isnan(allowed)) else None
                    if ant is not None and ant > 0:
                        ant = min(1.4 * form, max(0.6 * form, ant))
                        mu = 0.65 * form + 0.35 * ant
                    else:
                        mu = form
                    sd = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
                    if stat in CV:
                        sd = math.sqrt(0.5 * sd * sd + 0.5 * (CV[stat] * mu) ** 2)
                    med = float(np.median(vals))
                    base = math.floor(med)
                    line = base + 0.5 if rng.random() < 0.5 else base - 0.5
                    if line < 0.5:
                        line = 0.5
                    pm = p_over(stat, mu, sd, line)
                    if pm is None:
                        continue
                    hits = int((vals > line).sum())
                    ph = (hits + HIT_PRIOR * 0.5) / (len(vals) + HIT_PRIOR)
                    out.append((stat, pos, season, W, line, mu, clip(pm), clip(ph), int(row[stat] > line)))
df = pd.DataFrame(out, columns=["stat", "pos", "season", "week", "line", "mu", "p_model", "p_hit", "over"])
df.to_pickle(f"{D}/winbt.pkl")
print(f"{len(df):,} predictions, base Over rate {df.over.mean():.3f}")


def calib(p, y, label):
    b = pd.cut(p, [0, .3, .4, .45, .5, .55, .6, .7, 1])
    t = pd.DataFrame({"p": p, "y": y, "b": b}).groupby("b", observed=True).agg(n=("y", "size"), said=("p", "mean"), won=("y", "mean"))
    ll = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
    print(f"\n{label}: log loss {ll:.4f} (coin flip 0.6931)")
    print(t.round(3).to_string())


def fit(X, y, iters=50):
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-X @ beta))
        g = X.T @ (y - p)
        H = (X * (p * (1 - p))[:, None]).T @ X
        beta += np.linalg.solve(H + 1e-6 * np.eye(len(beta)), g)
    return beta


y = df.over.to_numpy()
lm = df.p_model.apply(logit).to_numpy()
lh = df.p_hit.apply(logit).to_numpy()
cur = 1 / (1 + np.exp(-(0.35 * lm + 0.5 * lh)))
calib(df.p_model.to_numpy(), y, "Model alone")
calib(df.p_hit.to_numpy(), y, "Hit rate alone")
calib(cur, y, "Board's current blend (0.35 model + 0.5 hit, market = 50%)")
print("\nBest weights (fit on all, then by stat): intercept, model, hit")
b = fit(np.column_stack([np.ones_like(lm), lm, lh]), y)
print(f"  ALL: {b.round(3)}")
for s, g in df.groupby("stat"):
    yy = g.over.to_numpy(); X = np.column_stack([np.ones(len(g)), g.p_model.apply(logit), g.p_hit.apply(logit)])
    print(f"  {s:16s} n={len(g):6,d}  {fit(X, yy).round(3)}")
# out-of-sample check: fit 2019-2023, test 2024-2025
tr, te = df.season <= 2023, df.season >= 2024
Xa = np.column_stack([np.ones(len(df)), lm, lh])
bt = fit(Xa[tr.to_numpy()], y[tr.to_numpy()])
pt = 1 / (1 + np.exp(-(Xa[te.to_numpy()] @ bt)))
calib(pt, y[te.to_numpy()], f"Fitted on 2019-23 {bt.round(3)}, tested on 2024-25")
