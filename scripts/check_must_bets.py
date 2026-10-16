"""
Reads a built output/dashboard.html in a headless browser and prints the
current MUST BETs (and 3-flame/3-ice rows with --include-threes) exactly as
the dashboard computes them, in its default Consistency mode.

Used by the scheduled alert task (added 2026-10-06): the task refreshes the
data on Trevor's Mac, stages dashboard.html to the cloud session, and runs
this there (Playwright + Chromium are preinstalled in the cloud session).

Usage:
    python3 check_must_bets.py /path/to/dashboard.html [--include-threes] [--json]
"""
import argparse
import asyncio
import json
import os

from playwright.async_api import async_playwright

JS = r"""
(includeThrees) => {
  const c = {};
  const rows = ROWS.map(r => enrichRow(r, selectedWeeks, c));
  const lvl = x => x.hot_level || x.cold_level;
  const pick = rows.filter(x => lvl(x) === 4 || (includeThrees && lvl(x) === 3));
  const fmtP = p => p === null || p === undefined ? '' : (p > 0 ? '+' + p : String(p));
  return {
    week: WEEK, oddsTime: ODDS_TIME, mode: SIGNAL_MODE,
    linesPosted: rows.filter(x => x.vegas_line !== null && x.vegas_line !== undefined).length,
    picks: pick.map(x => {
      const cn = x.cons || {};
      const m = cn.market || null;
      return {
        tier: lvl(x) === 4 ? 'MUST BET' : (x.hot_level ? '3 fire' : '3 ice'),
        player: x.player, team: x.team, opp: (x.at_opponent ? '@' : 'vs ') + x.opponent,
        stat: x.stat_label, side: cn.side || (x.hot_level ? 'over' : 'under'),
        line: cn.line !== undefined ? cn.line : x.vegas_line,
        price: m ? fmtP(m.price) : '', book: m ? m.book : '',
        hit: cn.pGames ? `${cn.pHits}/${cn.pGames}` : '', oppHit: cn.dGames ? `${cn.dHits}/${cn.dGames}` : '',
        oppRank: x.def_rank, injury: x.injury ? x.injury.status : null,
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
    a = ap.parse_args()
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=exe, headless=True)
        pg = await b.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + os.path.abspath(a.html))
        await pg.wait_for_timeout(1500)
        res = await pg.evaluate(JS, a.include_threes)
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
