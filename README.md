# NFL Player Prop Dashboard

Compares each player's recent stats, their upcoming opponent, what that
opponent allows to their position, and the Vegas line — all in one local
dashboard you run yourself. No server, no login, no ongoing Claude usage.

## One-time setup

1. Make sure you have Python 3 installed (you already do).
2. Open Terminal and go to this folder:
   ```
   cd ~/Documents/Gambling\ Program
   ```
3. Your Odds API key is already saved in `config/odds_api_key.txt`. If it
   ever changes, just replace the contents of that file with the new key.
4. Install the Python packages this uses (only needed once):
   ```
   pip3 install requests pandas lxml
   ```
   (If that errors, try `python3 -m pip install requests pandas lxml`.)

## Running it

Every time you want fresh data:

```
python3 run.py
```

This will:
1. Pull the latest player stats and this week's matchups from nflverse
   (free, no key needed) — `fetch_stats.py`
2. Pull the NFL's official weekly injury report (Questionable/Doubtful/
   Out, body part, practice participation) from nflverse — same free,
   no-key, structured source as the stats — `fetch_injuries.py`. Like
   coverage below, a failure here just skips itself and prints why,
   without blocking the rest of the run.
3. Pull Vegas player prop lines for this week's games from The Odds API
   using your key — `fetch_odds.py`
4. Pull a weather forecast for each outdoor stadium hosting a game this
   week, from Open-Meteo (free, no key needed) — `fetch_weather.py`
5. Pull each team's man/zone coverage-scheme rate from a free public page
   (no key needed) — `fetch_coverage.py`. Unlike the other sources,
   this one scrapes an unofficial third-party site rather than a
   documented data feed, so it's the piece most likely to eventually
   break — if it does, it just skips itself and prints why, without
   touching anything else in the run.
6. Combine everything into `output/dashboard.html` — `build_dashboard.py`

When it finishes, open `output/dashboard.html` in your browser (double-click
it in Finder, or `open output/dashboard.html` from Terminal).

### Other ways to run it

- `python3 run.py --skip-injuries` — skip the official injury-report fetch.
- `python3 run.py --skip-odds` — just refresh stats/matchups, skip the
  Odds API call (useful if you're out of quota or want to check something
  quickly without spending a request).
- `python3 run.py --skip-weather` — skip the weather forecast fetch.
- `python3 run.py --skip-coverage` — skip the man/zone coverage-rate scrape.
- `python3 run.py --only-dashboard` — just rebuild the HTML from
  whatever data you already fetched, instantly, no network calls.
- `python3 fetch_odds.py --bookmakers all` — pull lines from every
  bookmaker Odds API has instead of just DraftKings/FanDuel/BetMGM (uses
  more quota).
- `python3 fetch_odds.py --markets player_pass_yds,player_rush_yds` —
  only fetch specific prop markets to save quota.

## Reading the dashboard

- **⛑️ injury badge (added 2026-09-24, fixed 2026-09-25)**: shows next
  to a player's name when he himself is on this week's injury report.
  Red = Out/Doubtful, amber = Questionable or **Missed practice**. The
  official Out/Doubtful/Questionable designations only come out on each
  team's FINAL report (Friday for a Sunday game), so earlier in the week
  the badge falls back to the practice report: a player who did not
  practice because of an injury shows as "Missed practice" (rest days
  and personal absences are skipped; limited/full practice isn't
  flagged). Once the final report is out, the official designation takes
  over. Hover it for the body part; click the player for his card.
  Sourced from `fetch_injuries.py` (nflverse's copy of the NFL's official
  injury report — free, structured, not a scrape). This is the official
  report only, not narrative injury news. No badge = not on the report.
- **🩹▲ / 🩹▼ impactful-injury badges (added 2026-09-25, replacing the
  old 🛡️ O-line badge)**: injuries to OTHER players that matter for this
  player on this specific stat. Green 🩹▲ = helps him, red 🩹▼ = hurts
  him. Hover for exactly who's hurt and why it matters; the player's card
  has a full "Injury impact" table. The rules, per position:
  - **QB passing**: his O-line, WRs, or TE out hurts. Opponent's CBs,
    safeties, or pass rushers (DE/OLB) out helps.
  - **RB rushing**: his O-line or his QB out hurts; another RB out helps
    (more carries). Opponent's DTs or linebackers out helps.
  - **RB receiving**: another RB out helps. Opponent's linebackers or
    safeties out helps.
  - **WR**: another WR or the TE out helps (vacated targets); his QB out
    hurts. Opponent's CBs out helps.
  - **TE**: a WR or another TE out helps; his QB or O-line out hurts
    (may stay in to block). Opponent's linebackers or safeties out helps.
  - QB rushing, QB TDs, and INTs get no impact badge.

  Only injured players with a real role count: at least **50% snap
  share** this season (a starter-level number, and Claude's own pick,
  not an official definition). Someone who hasn't played at all this
  season doesn't count — his absence is already in everyone's recent
  numbers. A badge is full-strength when at least one of those players is
  Out/Doubtful, and faded when they're only Questionable or missed
  practice (they may well play). Badges are per stat, so in the
  grouped-by-player view they still show on the collapsed ↳ rows.
- **Mark (added 2026-09-22)**: the leftmost column — your own personal
  marker for that specific bet, separate from anything this dashboard
  computes for you. Pick ✅ if you've bet it, 🌕 if you're still
  watching it, ❌ if you're passing, or leave it blank. Use the "Hide ❌
  rows" checkbox above the table to get passed-on rows out of the way
  while you're scanning. Also shows up on each row inside a player's
  detail modal (click their name), so you can mark individual stats for
  that player without going back to the main table.
  - **Recording your bet (added 2026-09-28)**: pick ✅ Bet it and a small
    slip appears under the selector: Over/Under, the line you got, and
    the odds you got (American odds like -110 or +125). The boxes start
    empty; the grey hint inside each is just today's best available
    line/price for the side the numbers favor. It saves as you type, the
    same way marks do (this browser only, kept through `python3 run.py`
    rebuilds, fresh each new week). An odds entry that isn't a real
    American price (anything between -99 and +99) or a non-number line
    gets a red border. Switching the mark away from ✅ hides the slip but
    keeps what you typed.
  - **$ amount (added 2026-09-29)**: the slip also has a $ box for how
    much you bet, and shows "to win $X" once the odds and $ are filled in.
  - **📒 My Bets (added 2026-09-29)**: the button next to the Weeks filter
    opens every ✅ bet from **every week** (it doesn't reset when a new
    week's build comes in), grouped by week. Set each one's Result
    (Win / Loss / Push / Void) and it tracks your record, total profit,
    ROI, what's still pending, and a week-by-week breakdown. The Actual
    column shows the real stat once the game is in the data, with a
    "looks W/L" hint; **Fill in suggested results** applies those hints
    to every pending bet (you can change any after). **+ Add a bet by
    hand** is for parlays, ladders, or anything that isn't one table row.
    × removes a bet (click twice). **Backup / restore** gives you the
    whole thing as text to save, or to paste into the other copy — the
    Mac dashboard and the shared link each keep their own separate list.
    A **Week** dropdown at the top of the popup narrows it to one week
    (record, profit and pending switch to that week too); clicking a row in
    the week-by-week breakdown does the same.
    The **Best line** column shows the best DK/FanDuel/BetMGM line for
    your side (Over = lowest, Under = highest, same line = better price)
    and tags yours green "+1 better" or red "-1 worse". It refreshes every
    rebuild while the prop is listed, then freezes at the last pull once
    the game starts ("last seen" + time) — roughly the closing line if you
    rebuild near kickoff. The **Line value vs market** card counts how many
    of your bets beat the best market number.
  - **Sort by Mark**: click the Mark column header to put ✅ bets on top.
  - **Where it lives, and why a refresh won't erase it**: your marks are
    saved in this browser's local storage, keyed by week + player + team
    + stat — **not** written into `dashboard.html` itself. Every
    `python3 run.py` fully regenerates that file from scratch, so
    anything baked into the file would get wiped every time, but your
    marks live somewhere else entirely and get read back in when the
    page loads. Practically: re-syncing during the same week (to catch
    updated odds/lines) keeps every mark you've set; a new week starts
    with a clean slate, since it's a different set of props.
  - **The catch**: marks are tied to *this specific browser*, opening
    the dashboard from *this specific file location*. Clearing this
    browser's site data, switching to a different browser, or opening a
    moved/renamed copy of the file all start you over with nothing
    marked — there's no backup/export built in (kept deliberately
    simple, per your ask), so if that would bother you, say so and I'll
    add a way to save your marks to a file you can restore from.
- **Recent Avg**: the player's average over whatever weeks you've checked
  in the **Weeks** filter (see below) — current season only.
- **Opp Allows / Opp Rank**: what the upcoming opponent has allowed to
  that position/stat, over the same weeks you've selected — so if you've
  only checked Weeks 1-2, the defense ranking is also based on each
  team's weeks 1-2, not season-to-date. Rank 1 = the toughest matchup for
  that stat, 32 = the easiest. Early in the season, or with only a couple
  weeks checked, this can be noisy (a team may not even have played that
  many games yet, in which case it just uses whatever games are
  available in the selected weeks).
  - **Opp Rank color gradient (added 2026-09-22)**: replaced the old
    "top 10 red / bottom 10 green / everything else plain" cutoff with a
    continuous red-to-green scale across the full range of ranked
    defenses, so a rank fades smoothly the closer it sits to either
    extreme instead of jumping suddenly at a fixed line — rank 1 and
    whatever the toughest matchup that week is are the most saturated
    red, the easiest matchup is the most saturated green, and it fades
    through a neutral gray in the middle. The extreme ~20% on either end
    is also bolded so it stands out beyond just a slightly different
    shade. This scales against however many teams actually have data for
    that position/stat yet (can be under 32 early in the season), not a
    hardcoded 32, so the gradient always spans the real range instead of
    bunching everything toward one end. **Kept red/green rather than
    switching to a different color pair** for consistency with every
    other color-coded column on this page (Edge, wind, weather all use
    the same red/green convention) — worth knowing that red-green is a
    weaker choice for colorblind readers than some other pairing would
    be, but changing just this one column would make it visually
    inconsistent with the rest of the table, so I left it as-is. Say the
    word if you'd rather this column use a different pair.
- **Team Share**: what percentage of the player's own team's total
  production in that stat, over the selected Weeks, this specific
  player was responsible for. Receiving stats (Rec Yds, Receptions) are
  measured against the team's other players at the exact same position
  only (a WR's share is versus other WRs, not RBs/TEs). Rushing yards for
  RBs is measured against RBs only (QB scrambles are excluded). If the
  player was traded mid-window, each game correctly uses the team he was
  actually on that week, not his current team. QBs are always fixed at
  100% -- there's only one starting passer, so splitting credit doesn't
  make sense the way it does for pass-catchers/backs.
- **Anticipated**: Team Share % multiplied by Opp Allows -- a rough
  projection of this stat based on the player's typical cut of his team's
  production, applied to what the upcoming opponent gives up at that
  position. For QBs (100% share) this is just Opp Allows directly. Like
  Opp Allows, this recalculates instantly when you change the sample
  size. Treat it as a starting point, not a prediction -- it doesn't know
  about game script, injuries to other pass-catchers/backs on the team,
  or weather.
- **Edge**: Recent Avg minus the most advantageous line actually available
  (see "Line shopping" below), colored when it's a *big* edge — 20% or
  more of the line by default, in either direction, adjustable with the
  "How picky" slider described below — so small, noisy differences don't
  light up the whole table. Green means recent form is running well above
  the line; red means well below.
- **Anc. Edge**: the same idea, but built off **Anticipated** instead of
  Recent Avg — i.e. how far the matchup-based projection sits from that
  same shopped line, colored the same way.
  - **Line shopping (added 2026-09-24)**: Edge and Anc. Edge used to be
    graded against one flat consensus line (the median across
    DraftKings/FanDuel/BetMGM). Now, once Recent Avg tells us which side
    looks good against that consensus, the dashboard re-grades Edge
    *and* Anc. Edge against whichever actual book offers the best number
    for that side — the **lowest** available line for an Over (least you
    need to clear), the **highest** for an Under (most cushion) — since
    that's the real number you'd get if you placed it there. That book's
    cell in the DraftKings/FanDuel/BetMGM columns gets a green highlight
    so you know exactly where to place it. Only books that actually
    posted a line for that player/stat are considered; a dead-even tie
    against the consensus (no side to shop for) falls back to the old
    flat-consensus behavior. The price gate below was updated to match —
    it now checks the price at *that specific highlighted book*, not the
    blended consensus price, since that's the number you'd actually be
    betting into.
- **🔥 / 🧊 / ⭐**: shows up when Edge *and* Anc. Edge both light up in the
  same direction — recent form and the matchup projection independently
  agree the player is trending well OVER (🔥) or UNDER (🧊) the line. The
  NUMBER of emojis (1-3) says how big that agreed-upon edge is, using
  whichever of the two signals is *weaker* as the limiting factor — a
  huge Edge paired with only a modest Anc. Edge still only earns 1 flame,
  since one signal is only about as strong as its weakest link. Above the
  3-flame/3-ice max there's a 4th, rarer **⭐ MUST BET** tier — see its own
  section below. Recomputes automatically every time you refresh data
  (`python3 run.py`) since it's derived straight from that run's own
  numbers. Sortable (MUST BET sorts highest, then 🔥 rows as +1/+2/+3,
  🧊 as -1/-2/-3, everything else as 0).
  - **"How picky for 🔥/🧊/❓" slider (added 2026-09-22)**: a slider in the
    controls bar, above the table, that raises or lowers the edge % a row
    needs to earn 1/2/3 🔥/🧊 in the first place — added because the
    original fixed 15%/25%/40% thresholds were letting through too many
    3-star rows. Drag it right to demand a bigger edge before anything
    lights up (fewer, more selective 🔥/🧊 rows); drag it left to loosen
    it back up. The label next to it always shows the exact live cutoffs
    (e.g. "1★ ≥20% · 2★ ≥33% · 3★ ≥53%"), so you always know exactly what
    you're requiring. **It moves one shared threshold, not three separate
    ones** — the same bar that decides 1-star also decides when Edge/Anc.
    Edge get colored green/red and when ❓ considers a signal
    "significant," and the 2-star/3-star bars scale off the 1-star value
    at the same ratio as the original fixed thresholds (25/15 ≈ 1.67x,
    40/15 ≈ 2.67x) — so the whole page's sense of "does this edge matter"
    moves together rather than tiers getting pickier while the coloring
    or ❓ stay put underneath. Range is 10%-30% (default 20%, a bit
    pickier than the original fixed 15%, per your ask) — both the range
    and the default are Claude's own reasonable-looking choices, not a
    fixed number worth trusting blindly, so say the word if 30% isn't
    picky enough or 10% is too picky. Doesn't touch the price gate
    (`MAX_JUICE_PRICE`, still fixed at -130) — that's a separate check on
    the bet's price, not on the size of the stat edge. Resets to the 20%
    default on page reload; it isn't saved between visits.
  - **⭐ MUST BET — a 4th tier above 3 flames/ice (added 2026-09-24,
    made a FIXED bar 2026-09-24)**: even with the picky slider in place,
    you said there were still too many 3-star rows. This adds a
    genuinely new, rarer tier ABOVE the old 3-flame/3-ice max: when Edge
    and Anc. Edge both clear an even higher bar in the same direction,
    the row shows a single gold **⭐ MUST BET** badge instead of a 4th
    flame/ice character -- a deliberately different visual so the very
    top of the scale reads as its own callout, not just "one more
    emoji." It sorts above everything else, including 3-flame/3-ice.
    **This bar was first built to scale with the picky slider (80% by
    default), but real data still showed ~20-25 rows earning it, and you
    said even that was too many — "must bet should always be the same
    criteria, just like a line that almost doesn't even make sense."**
    So MUST BET's bar is now a SEPARATE, FIXED 150% threshold that does
    **not** move when you drag the picky slider — 1-star/2-star/3-star
    keep flexing with the slider exactly as before, but MUST BET always
    means the same absurd thing (recent form running at 2.5x the
    sportsbook's own line) no matter where the slider sits. Against a
    fresh `python3 run.py` run, this actually cut the count from ~20-25
    down to **5 MUST BET rows out of 1,382** — genuinely rare now, with
    the 3-star bucket picking up the rows that no longer qualify. 150%
    is, like every other threshold on this page, **Claude's own
    reasonable-looking pick, not a proven cutoff** -- say the word if 5
    still feels like too many (or too few) once you've watched it over a
    few more weeks of real data; it's a one-constant change to retune.
    **Matchup requirement (added 2026-10-05):** a MUST BET Over now also
    needs the opponent to be one of the 10 defenses that allow the MOST
    of that stat to that position (Opp Rank 23-32 of 32); a MUST BET
    Under needs one of the 10 that allow the LEAST (Opp Rank 1-10). A row
    that misses it keeps its 3 flames/ice. On the Week 4 board this cut
    MUST BETs from 13 to 7. One constant (`MUST_BET_MATCHUP_TOP`).
    **3 flames/ice need it too, plus consistency (added 2026-10-05):** any
    row that would reach 3 or MUST BET must also pass that same matchup
    rule AND be consistent -- the standard deviation of his games in the
    selected weeks can be at most **50% of the line** (e.g. line 50.5 with
    games 55/60/58 swings ~5% -> passes; 10/140/30 swings ~139% -> fails;
    one game can't be measured -> fails). Otherwise it's held at 2, shown
    with a small down-arrow; hover the flames/ice for the swing % and the
    reason. On the Week 4 board, 3-plus went from 59 rows to 10. Graded
    against Week 4's results (30 of 32 teams in), the old 3s and MUST BETs
    went 30-23; the new ones went 6-2 -- one week, so treat it as a good
    sign, not proof. Most survivors are unders: big over edges usually
    come from one huge game, which this rule screens out. Constant:
    `MAX_TIER3_REL_SD`.
  - **Price gate (added 2026-09-22, updated 2026-09-24)**: even when the
    stat math agrees, 🔥/🧊 only shows up if the side you'd actually be
    betting isn't priced too steep. 🔥 checks the Over price at whichever
    book is highlighted by the line-shopping logic above; 🧊 checks that
    same book's Under price. (If no single book was pinned — a dead-even
    tie against consensus, or no per-book price data — it falls back to
    the consensus price like before.) A price worse than **-130** (meaning you'd need to hit roughly 56.5%+
    of the time just to break even — noticeably more than a normal
    -110-ish player-prop vig) suppresses the flag entirely, even at 3
    flames' worth of stat edge. When this happens you'll see a small gray
    "price" tag instead of blank — hover it to see the exact price and
    why it got suppressed. **-130 is Claude's own reasonable-looking
    cutoff, not an official number** (same caveat as the picky-slider
    thresholds above) — easy to move via `MAX_JUICE_PRICE` near the top
    of the JS in `build_dashboard.py`. If a side's price hasn't been
    fetched yet (blank book columns), nothing gets suppressed — no data
    to check it against yet, same as everywhere else here.
- **❓ (added 2026-09-22, refined 2026-09-22)**: shows up when exactly one
  of Edge / Anc. Edge is significant (whatever the "How picky" slider is
  currently set to, 20%+ by default) on its own and the other
  *isn't confirming it but also isn't contradicting it* — worth a manual
  look even though it doesn't qualify for 🔥/🧊. The QB-rushing example
  that started this: a QB who's good at rushing but hasn't rushed much
  lately, facing a defense that gives up a lot of QB rushing yards.
  Recent Avg alone wouldn't show an edge (so Edge stays quiet), but Anc.
  Edge (built off the matchup) would — and that's still worth flagging as
  long as Edge isn't actively pointing the *other* way. Originally this
  also fired when both signals were significant but pointed in opposite
  directions; per Trevor, that case was cut — a flat disagreement in sign
  (one clearly positive, one clearly negative) is now treated as noise,
  not a "worth a look" case, so it no longer shows ❓ at all. Concretely:
  the non-significant signal only has to *not* be on the opposite side of
  zero from the significant one — it can be weakly the same direction, or
  exactly zero, or simply missing (no matchup data yet, which doesn't
  count as contradicting anything). Hover the ❓ to see exactly which
  signal triggered it and its value. This is mutually exclusive with
  🔥/🧊 by construction (they require confident agreement; ❓ requires
  the opposite) and is independent of the price gate above — it still
  shows even at a bad price, since reviewing something yourself isn't the
  same as this dashboard recommending a bet on it.
  - **Default sort order (added 2026-09-22, MUST BET added to the top
    2026-09-24)**: the table now opens sorted by signal strength instead
    of alphabetically by player — all ⭐ MUST BET rows first, then all
    3-flame/3-ice rows, then all 2s together, then all 1s together, then
    ❓ rows, then a price-suppressed row (real edge, bad price), then
    everything else. Fire and ice at the same tier are grouped together
    (a 3-flame row and a 3-ice row both count as "tier 3"), not split
    into separate over/under sections. Click any other column header to
    sort by that instead, same as always — clicking the 🔥/🧊/⭐ header
    again toggles between biggest-first and smallest-first.
- **DraftKings / FanDuel / BetMGM**: that specific book's own line for
  this stat, so you can spot when one book is off the market (a
  discrepancy worth shopping). Blank means that book doesn't have this
  prop posted yet.
- **Weather**: the forecast at the home team's stadium for kickoff —
  temperature, wind speed, condition, and chance of precipitation. Shows
  "Dome" for fixed-roof and retractable-roof stadiums (treated as
  weather-neutral, since a retractable roof is closed for the large
  majority of games). Blank means the forecast isn't available yet (the
  game is too far out) or the stadium wasn't recognized.
  - **Red text** flags bad weather worth noticing before you bet: very
    cold (25°F or below), high wind (20mph+), a meaningful rain/snow
    chance (50%+), or a rain/snow/storm condition in the forecast — any
    one of those is enough to flag it. **Amber** is a lighter "worth a
    look" tier for wind that's elevated (15-19mph) but not yet flagged
    red on its own. These thresholds are Claude's own picks, not an
    official standard — easy to change if you want it more or less
    sensitive (`BAD_WEATHER_*` constants near the top of
    `build_dashboard.py`).

**Stat types available**: QB — Pass Yds, Pass TDs, INTs, Rush Yds, TDs,
Completions, Attempts. RB — Rush Yds, Rush Attempts, Rec Yds, Receptions,
TDs, Air Yards. WR/TE — Rec Yds, Receptions, TDs, Air Yards.

**TDs** is the Anytime-TD-Scorer stat: rushing TDs + receiving TDs added
together, i.e. any touchdown the player scored himself. A QB's thrown
touchdowns don't count here (that's the separate Pass TDs stat) — only a
QB rushing one in himself (or, extremely rarely, catching a trick-play
TD) counts toward his own TDs number. Note Team Share can show "-"
instead of a number for TDs/Rush Attempts when nobody at that position
scored/carried at all in the selected window — 0÷0 doesn't have a
meaningful percentage. QB rows are the one exception: Team Share is
always fixed at 100% since there's only one starting passer, so this
never shows blank for QBs.

**Air Yards** (RB/WR/TE only) is how far downfield the ball traveled in
the air on passes thrown to that player, added up for the game — a
measure of downfield/target quality, not just volume. It's a
**context-only stat**: sportsbooks don't post a player-prop line for it,
so it still gets Recent Avg, Opp Allows, Opp Rank, and Team Share like
every other stat, but Edge, Anc. Edge, 🔥/🧊, and the DraftKings/FanDuel/
BetMGM columns are always blank for it — there's no line to compare
against. Useful for spotting who's actually getting downfield targets vs.
just racking up short, easy catches.

**Click a player's name** to open their full stat card. It has two parts:
a summary table with every stat type this dashboard tracks for that
player (not just whichever one you've currently filtered to) — each with
its own Recent Avg, Opp Allows/Rank, Team Share, Anticipated, Edge, Anc.
Edge, 🔥/🧊, and sportsbook lines — and, below that, a game-by-game box
score: one row per game that falls in your selected Weeks, one column per
stat, so you can see exactly what that player did in each individual game
rather than just an average.

**Click a player's Opp** (their upcoming opponent) to open that team's
defense card instead — a section per position (QB/RB/WR/TE) showing every
stat they allow, its average and rank, plus the same kind of game-by-game
breakdown: one row per game in your selected Weeks, one column per stat,
so you can see exactly what that defense gave up each week rather than
just a season average. Each game row also names the
actual opponent they played that week (e.g. "2026 Wk2 vs CAR"), so you
can tell whether a bad number came against a real offense or a bottom
feeder. The position you clicked from shows up first. If you've run
`fetch_coverage.py`, the top of this card also shows that team's man/zone
coverage split for the season (see **Coverage scheme tag** below).

**Coverage scheme tag** (the small badge next to an Opp's name — "High
Man" / "Medium" / "Low Man"): a 3-tier read on how much that defense
leans on man coverage, season-to-date, based on their zone-coverage rate.
Trevor's own thresholds: zone rate 65% or below → **High Man** (playing
man unusually often), 65–90% → **Medium**, above 90% → **Low Man**
(almost always zone). Hover the badge to see the exact Man%/Zone% split.
This comes from `fetch_coverage.py`, which scrapes a free public page
since nflverse doesn't track coverage type at all. **Important
limitation**: this is
strictly a team-level, season-long stat — it tells you a defense *leans*
man or zone, not whether any specific player does better or worse against
that scheme. I looked for a free source that splits individual
players' stats by man vs. zone coverage faced (the actual "does Christian
Watson do better vs. man or zone" question) and came up empty — that
specific stat is a PFF/SumerSports subscription metric everywhere I
checked, including nflverse's own most detailed datasets (FTN charting,
Next Gen Stats), which don't record coverage type for anyone. So treat
the tag as one input for your own read on the matchup, not a full
answer — pair it with what you already know about how that player
profiles (route-runner who wins with separation vs. someone who needs
scheme help, etc.). Blank means `fetch_coverage.py` hasn't been run yet,
or that page changed shape and the scrape needs a look (it'll tell you
in the terminal either way).

Either card closes with the &times; button, clicking outside the card, or
pressing Escape.

**Game filter (added 2026-09-24)**: the "Game" dropdown next to the
Position buttons narrows the table to just one matchup's players (both
teams), listed in kickoff order for the week (e.g. "Thu 9/24 8:15p ATL @
GB"). Handy for focusing on one game at a time instead of scrolling
through the whole slate. **It resets to "All Games" automatically every
Tuesday morning** — practically, that's after that week's Monday Night
game is done and the NFL week turns over — so you never come back to a
stale filter still stuck on a game that's already been played. This
reset is based on your computer's actual clock, not on when you happen
to re-run `python3 run.py`, so it clears even if you reopen an old
`dashboard.html` you haven't rebuilt yet for the new week. (The exact
cutoff — Tuesday 3am — is Claude's own reasonable buffer past even a
very late Monday night finish, not an official league cutoff.)

Click any column header to sort by it. Use the search box, position
buttons, Game filter, or **Stat** buttons (Pass Yds, Receptions, etc.) to
narrow things down — combine Position + Stat to see, say, just RBs'
receiving lines. Since defense-allowed ranks are computed separately for every
individual stat, the Opp Rank column always reflects the specific stat
you're looking at, not a blended position rank. Use the **Weeks** dropdown
to choose exactly which weeks of the current season count — Recent Avg,
Opp Allows, Opp Rank, Team Share, Anticipated, and both Edge columns all
recalculate instantly (no re-fetching) since every week's data is already
pulled down.

**Weeks filter (replaced the old Last 2/3/5/10 buttons, 2026-09-24)**:
Trevor asked for this directly — "make the 'Sample Size' a function where
you can select specific NFL weeks... you check the boxes you want... for
what it defaults to, just have it be all weeks up to this current one."
Click the **Weeks** dropdown to open a panel of checkboxes for every week
of the current regular season (1-18); check or uncheck any combination
and every stat on the page recalculates against exactly those weeks. The
panel has three shortcuts: **All** (every week), **None** (clear
everything), and **Up to current** (back to the default). It opens on
Week 1 through whatever the current/upcoming week is when you load the
page, and does **not** remember your choice between page loads or
rebuilds — every fresh load starts back at the default, same as the old
Last-N buttons did. This is a bigger change than it might look like: the
old "Last N games" sample used to quietly blend in last season's final
games early in the year, specifically so a small early-season sample
wasn't too thin. Weeks checkboxes only make sense for one season, so that
blending is gone — `fetch_stats.py` now only pulls the current season at
all. In practice this means: if it's Week 2 and you leave the default
(Weeks 1-2) checked, Recent Avg and everything downstream of it really is
just those 2 games, full stop — no cushion from last year anymore. That's
a real early-season sample-size trade-off, not a bug: it's what "pick the
weeks you want" has to mean once weeks (not a game count) are the unit,
and it gets less noisy on its own as the season goes on and more weeks
have real data behind them.

**Zero-stat weeks now count as real zeros (fixed 2026-09-24)**: you
caught this directly — Austin Hooper's Week 1 was missing entirely from
his box score even though he'd actually played that game. Turns out
nflverse's own weekly stats file only includes a row for a player-week
when they recorded at least one relevant stat (a target, a carry, etc.)
— a player who was on the field but never touched the ball that week
(e.g. a blocking TE who ran routes but drew zero targets) gets no row at
all for that week, not a row of zeros. That meant every average was
silently computed over fewer games than the player actually played,
which really does skew the projections, especially for low-target
TEs/RBs. Fixed by pulling nflverse's separate snap-count data (a free,
official dataset — confirms who actually played each week) and filling
in an explicit zero-stat row for any week a tracked player took a real
offensive snap but has no stat line. Only applies to players who already
have at least one real game logged this season, so it doesn't pull in
brand-new players who'd never otherwise show up on the dashboard.

One side effect worth knowing about: with these zero weeks now counted
for real, a handful of low-volume players' true averages came out lower
than before (since they were previously averaged only over their "good"
weeks) — a few dropped below the minimum-relevance bar this dashboard
already uses to filter out players who aren't realistic prop candidates
(e.g. under ~1 target/game for a WR/TE), so they quietly stopped
appearing. That's the fix working as intended, not a bug — their real
average genuinely is lower once a quiet week is counted instead of
ignored.

### 🎯 Signals: Consistency mode (added 2026-10-05, now the default)

The 🔥/🧊/⭐/❓ signals can be built two ways, picked with the **Signals**
dropdown next to the matchup filters (your choice is remembered):

- **Consistency (hit rates)** -- the default. Two new columns:
  - **Hit**: how often HE cleared the line on that side over the
    selected weeks, e.g. `O 4/4`. Hover for his games and his worst
    game vs. the line.
  - **Opp Hit**: how often THIS DEFENSE allowed it -- each of the
    opponent's games, scaled to his usual share of his team's production
    at his position, checked against the same line. Hover for the
    per-game numbers.
  - Tiers: **1** = both 75%+ (he missed at least once); **2** = he
    cleared it every game and the defense 2/3+; **3** = every game and
    the defense 75%+, plus the top-10 matchup rule (else held at 2);
    **⭐ MUST BET** = every game on BOTH sides, 4+ games each, plus the
    top-10 matchup rule; **❓** = he cleared it every game but the defense
    usually holds it under. Needs 3+ games on both sides. The price gate
    still applies. The How-picky slider is greyed out in this mode.
  - Why: on the Week 4 board, his own perfect record was the strongest
    pattern -- 67-40 when he'd cleared it every game vs. about 50/50 when
    he'd missed once; perfect on both sides went 29-14. Overall the
    consistency signals went 51-34 vs. 84-65 for the old formula's
    signals. One week -- keep watching it.
- **Average edge** -- the original formula (Edge / Anc. Edge, the picky
  slider, and the standard-deviation consistency check).
- **Weeks filter drives the signals too (added 2026-10-07):** Hit, Opp
  Hit, Opp Rank and every 🔥/🧊/❓ use only the weeks you've checked;
  the lines never change. The game minimums shrink to fit your window
  (e.g. Wk 3-4 grades everyone on 2 games), and the label next to the
  picky slider says how many played weeks the signals are using, with a
  "small sample" warning under 3. **MUST BET always needs 4+ games on both
  sides**, so a short window can give 1-3 flames/ice but never a MUST BET.
- **Opponent-adjusted hit rates (added 2026-10-05):** a miss can be
  "excused" when the opponent explains it, shown in brackets like
  `O 2/4 (2/3)` and marked `~` in the hover. In **Hit**, a miss against one
  of the 10 toughest defenses for that stat (10 softest for an Under; was 5
  until 2026-10-16). In
  **Opp Hit**, a miss against an offense that rarely produces the stat
  itself -- its usual output (from its other games, scaled to his share)
  is under 75% of the line (over ~1.33x the line for an Under). E.g.
  Seattle held Arizona's QBs to 7 rushing yards, but Arizona's QBs only
  average 12, so that game doesn't count against Seattle for Purdy's
  18.5. Hits are never removed, the adjustment only kicks in when 3+
  games remain, and MUST BET still needs a raw perfect player record.
  Constants: `EXCUSE_TOUGH_TOP`, `EXCUSE_OFF_RATIO`.

### 🔍 Second look, ✔/⚠ script, and Hide ❓ (added 2026-10-01)

- **Second look (player card)**: for every stat with a signal (⭐/🔥/🧊/❓)
  the card runs a checklist on the side the signal points to: hit rate vs.
  the line, volume (targets/carries/attempts he gets vs. how many he needs
  at his own rate), game script from the Vegas spread/total, matchup rank,
  injuries, weather and price, plus cautions (thin sample, one game skewing
  the average, low volume). Hover a ❓ in the table for the same list.
  It's context, not a pick: on Week 3's pre-game board the combined count
  didn't predict results (❓ rows went 61-83 on their signal side, and the
  ones the checklist liked did worse).
- **✔ script / ⚠ script** in the 🔥/🧊/⭐ column: the one factor that held
  up in that test. ⚠ means the spread argues against the bet (e.g. an
  underdog QB's rushing under, a big underdog RB's rushing over); flagged
  ❓ rows like that went 7-16 in Week 3, ones it supported went 11-8.
  Needs the spread, which `fetch_stats.py` now saves.
- **Hide ❓ rows** checkbox next to Hide ❌.
- **history/**: every full `python3 run.py` now saves a copy of the
  dashboard there, so each week's pre-game signals can be graded against
  the real results. One week is a small sample; the more weeks saved, the
  better the next test.

## About the data

- **Stats & matchups**: [nflverse](https://github.com/nflverse), a free,
  actively maintained public NFL data project. Usually updated within
  hours of games ending.
- **Vegas lines**: [The Odds API](https://the-odds-api.com), using your
  key. Each player-prop request against a game costs API quota (roughly
  the number of markets requested), and lines can move between when you
  fetch them and game time — treat this as a snapshot, not a live feed.
  `fetch_odds.py` prints your remaining quota after every request.
- **Weather**: [Open-Meteo](https://open-meteo.com), free and no key
  needed. Forecasts are generally only meaningful a week or so out, which
  matches the one-week-ahead window this dashboard already shows.
  Stadium locations and roof types live in `stadium_info.py`.
- **Coverage scheme (Man/Zone rates)**: [Sharp Football
  Analysis](https://www.sharpfootballanalysis.com/stats-nfl/nfl-coverage-schemes/),
  free and no login needed, but unofficial — it's one page on a
  third-party site, not a documented API like the other three sources
  here, so it's the one most likely to need a fix down the road if that
  site changes its layout. Team-level, season-to-date only.

## If something breaks

Both fetch scripts print what they're doing and any errors in plain
English. If you hit an error you can't figure out, copy the full output
and send it over — that's usually enough to fix.

A couple of things that are expected, not bugs:
- Early in the season, with only a week or two checked in the Weeks
  filter, Recent Avg / Opp Allows / everything else is based on a small
  real sample (no more last-season blending — see the Weeks filter
  section above) — that's intentional, not a mistake.
- A handful of players might not get a Vegas Line even when they clearly
  have a prop on the board — this usually means their name is spelled
  slightly differently between the two data sources (e.g. suffixes like
  "Jr." or initials). Let me know which player and I can add a fix.
- Team Share can very rarely show slightly over 100% for a tiny selected
  Weeks window (e.g. just 1-2 weeks checked). That's a quirk in the
  underlying data — a player's official position tag can vary week to
  week (an RB briefly listed as FB, say) — not a math error.

## Columns: drag to move, drag the edge to resize (2026-10-07)

- **Move a column:** grab a header and drop it on another header. A blue bar shows which side it will land on.
- **Resize a column:** drag the thin bar on a header's right edge. Text that no longer fits is cut off with "…".
- Your layout is saved in this browser and survives rebuilds and refreshes. **↺ Reset columns** (next to "Hide ❓ rows") puts everything back.
- Clicking a header still sorts. A drag or resize won't trigger a sort by accident.
- The "How picky" slider is gone. Average-edge mode stays at its default 20% threshold; the legend text is still shown.
- Fixed a bug: clicking My Bets used to also blank out the main table's position filter.

## Weeks: defaults to played weeks, plus Last 2 / Last 4 (2026-10-07)

- The Weeks filter now defaults to every week already played (e.g. "Wk 1-4" on a Week 5 board). The upcoming week has no games yet, so it was only adding confusion to the label.
- **Last 2 / Last 4 / All played** buttons sit right next to the Weeks dropdown; one click sets the window and every stat, rank, hit rate and signal follows it. The active one is highlighted.
- These are week-based: if a team had a bye in that span, its players have one fewer game in the window.
- Inside the dropdown, "Up to current" is renamed "All played".

## 🎬 Game script analysis (2026-10-07)

- **Where:** pick a game in the Game filter and a "🎬 Game script" panel opens under the Stat row (click its title to collapse it; it stays collapsed while you filter). Every row also has a 🎬 next to the opponent that opens the same analysis as a popup, and so do My Bets (current-week bets, with a "Back to My Bets" button) and the player card.
- **What's in it:**
  - Headline: lopsided / lean / coin flip, plus whether the total is high or low versus this season's average closing total.
  - Spread, total, each team's implied points, and win probability (from the moneylines).
  - How the game should flow: who's likely leading or trailing, and what that does to run/pass volume and interception risk. It also flags pass-heavy or run-heavy teams against the league pass rate, and checks each team's points scored versus the opponent's points allowed against the total.
  - Props the script points to (green = Over side, red = Under side), and matchup edges (offense rank versus defense rank, passing and RB rushing).
  - Weather (wind, cold, rain), rest days, and whether it's a divisional game.
  - Injuries for 40%+ snap players, with who absorbs the targets or carries.
  - Team profiles for the selected weeks: record, against the spread, overs/unders, points for/against, pass attempts, pass and rush yards with ranks, pass rate, defense ranks, coverage, and rest.
  - Each team's game results.
  - The dashboard's signalled rows in this game, and your own bets in it.
- **Data:** `fetch_stats.py` now also saves each game's rest days, moneylines and divisional flag, plus every finished game's score and closing spread/total. Re-run it (or `python3 run.py`) to refresh.
- It's context, not a pick. In the Week 3 backtest, game script was the only checklist factor better than a coin flip (58%), on a small sample.
