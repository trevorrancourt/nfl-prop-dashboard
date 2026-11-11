"""
Reads a built output/dashboard.html in a headless browser and prints the
current MUST BETs (and 3-flame/3-ice rows with --include-threes) exactly as
the dashboard computes them, in its default Consistency mode.

Used by the scheduled alert task (added 2026-10-06): the task refreshes the
data on Trevor's Mac, stages dashboard.html to the cloud session, and runs
this there (Playwright + Chromium are preinstalled in the cloud session).

--watch-file takes a JSON list of mark keys (WEEK|player|team|stat_col) and
also returns each one that's on this board with its current best line and
price (used by notify.py's Watching section, added 2026-10-16).

Usage:
    python3 check_must_bets.py /path/to/dashboard.html [--include-threes] [--json] [--watch-file keys.json]
"""
import argparse
import asyncio
import json
import os

from playwright.async_api import async_playwright

JS = r"""
(arg) => {
  const includeThrees = arg.includeThrees;
  const watch = new Set(arg.watch || []);
  const c = {};
  const rows = ROWS.map(r => enrichRow(r, selectedWeeks, c));
  const lvl = x => x.hot_level || x.cold_level;
  // Since 2026-11-09 alerts are the board's Top 3 (topPicks), per Trevor.
  const pick = (typeof topPicks === 'function')
    ? topPicks().top.map(c => Object.assign({}, c.e, { _bet: c.bet, _p: c.p }))
    : rows.filter(x => lvl(x) === 4 || (includeThrees && lvl(x) === 3));
  const fmtP = p => p === null || p === undefined ? '' : (p > 0 ? '+' + p : String(p));
  return {
    week: WEEK, oddsTime: ODDS_TIME, mode: SIGNAL_MODE,
    linesPosted: rows.filter(x => x.vegas_line !== null && x.vegas_line !== undefined).length,
    // How full the Review list is (2026-11-10): picks shown, and how many rows
    // were in a Review group with a price at all (before the value check).
    reviewList: (typeof topPicks === 'function') ? (() => {
      const tp = topPicks();
      const inGroup = rows.filter(x => REVIEW_GROUPS.includes(pickGroup(x)) && pickBet(x) && pickBet(x).price != null).length;
      // 2026-11-11 (per Trevor: "suggestions are all under and the top three are high odds"):
      // list the picks themselves, and count every candidate by group and side.
      const fp = v => v === null || v === undefined ? '' : (v > 0 ? '+' + v : String(v));
      const items = tp.top.concat(tp.review).map((c, i) =>
        `#${i + 1} ${c.e.player} ${c.e.team} ${c.e.stat_label} ${c.bet.side === 'over' ? 'O' : 'U'} ${c.bet.line} ${fp(c.bet.price)} ${c.bet.book || ''} [${c.g} p${Math.round(c.p * 100)} need${Math.round(c.need * 100)}]`);
      const tally = {};
      for (const x of rows) {
        const g = pickGroup(x), b = g ? pickBet(x) : null;
        if (!g || !b || b.price == null) continue;
        const k = g + ' ' + (b.side === 'over' ? 'O' : 'U');
        tally[k] = (tally[k] || 0) + 1;
      }
      return { shown: tp.top.length + tp.review.length, top: tp.top.length, inGroup, size: (typeof LIST_SIZE !== 'undefined' ? LIST_SIZE : null), items, tally };
    })() : null,
    picks: pick.map(x => {
      // 🎯 3-stars (2026-11-03) aren't streak picks: use their own side/line/price.
      const op = x._bet || x.must_pick || x.outlier_promo; // Top 3 / MUST BET / 🎯 3-star: their own side/line/price
      const cn = op ? { side: op.side, line: op.line, market: { price: op.price, book: op.book } } : (x.cons || {});
      const m = cn.market || null;
      return {
        key: markKey(x),
        tier: x._bet ? `TOP 3 (${Math.round(x._p * 100)}%)` : (lvl(x) === 4 ? 'MUST BET' : (x.hot_level ? '3 fire' : '3 ice')),
        player: x.player, team: x.team, opp: (x.at_opponent ? '@' : 'vs ') + x.opponent,
        stat: x.stat_label, side: cn.side || (x.hot_level ? 'over' : 'under'),
        line: cn.line !== undefined ? cn.line : x.vegas_line,
        price: m ? fmtP(m.price) : '', book: m ? m.book : '',
        hit: cn.pGames ? `${cn.pHits}/${cn.pGames}` : '', oppHit: cn.dGames ? `${cn.dHits}/${cn.dGames}` : '',
        oppRank: x.def_rank, injury: x.injury ? x.injury.status : null,
        roleChange: x.role_changes || [],
      };
    }),
    watched: rows.filter(x => watch.has(markKey(x))).map(x => {
      const cn = x.cons || {};
      const side = cn.side || x.direction || (x.cold_level ? 'under' : 'over');
      const m = bestMarketFor(x, side);
      return {
        key: markKey(x), player: x.player, team: x.team, opp: (x.at_opponent ? '@' : 'vs ') + x.opponent,
        stat: x.stat_label, side: side,
        line: m ? m.line : null, price: m ? m.price : null, book: m ? m.book : '',
        signal: lvl(x) === 4 ? 'MUST BET' : (lvl(x) ? lvl(x) + (x.hot_level ? ' fire' : ' ice') : ''),
      };
    }),
  };
}
"""


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--include-threes", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--watch-file")
    a = ap.parse_args()
    watch = json.loads(open(a.watch_file).read()) if a.watch_file else []
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=exe, headless=True)
        pg = await b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + os.path.abspath(a.html))
        await pg.wait_for_timeout(1500)
        res = await pg.evaluate(JS, {"includeThrees": a.include_threes, "watch": watch})
        await b.close()
    res["page_errors"] = errs
    if a.json:
        print(json.dumps(res, indent=1))
        return
    print(f"Week {res['week']} · odds pulled {res['oddsTime']} · {res['linesPosted']} props with lines · mode {res['mode']}")
    if errs:
        print("PAGE ERRORS:", errs)
    if not res["picks"]:
        print("No MUST BETs right now.")
    for x in res["picks"]:
        inj = f" · {x['injury']}" if x["injury"] else ""
        print(f"{x['tier']}: {x['player']} ({x['team']} {x['opp']}) {x['stat']} {x['side'].upper()} {x['line']} {x['price']} {x['book']} · Hit {x['hit']} · Opp Hit {x['oppHit']} · Opp Rank #{x['oppRank']}{inj}")


asyncio.run(main())
