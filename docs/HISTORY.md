# NFL Player Prop Dashboard

Built: 2026-09-21 · Last updated: 2026-09-28 (new bet slip under ✅ Bet it to record the side, line, and odds actually taken, Version 26; new sortable "Stat" column in the main table between Opp and Avg -- Trevor: the table never showed which prop a row was (e.g. a MUST BET row that was actually INTs), Version 24; new green 🩹▲ / red 🩹▼ "impactful injury" badges per stat row -- own-team and opposing-defense injuries that help or hurt a player, by position, limited to 50%+ snap-share players, replacing the old 🛡️ O-line badge; fixed the injury feed only covering Thursday-night teams (it ignored the practice report, so the O-line badge only ever showed for Green Bay); new "Targets" stat for RB/WR/TE, context-only like the existing Air Yards stat (no Vegas line, since there's no such market), so it now has its own row in the main table, its own Stat filter button, and -- what Trevor specifically asked for -- its own row in both the player modal's summary table and its game-by-game box score; game-by-game box score now shows an explicit "DNP" row for any already-played week where a player recorded zero snaps, instead of silently omitting that week -- fixed after Trevor asked why Michael Pittman's card had no Week 2 row; confirmed via raw nflverse data that he took zero offensive snaps that week and was listed Questionable with a foot injury, not a data bug); new "Strong matchup only (Rank 1-13)" filter checkbox, the mirror image of Weak matchup, flagging rows where the upcoming opponent is currently limiting that exact position/stat best -- useful for finding Under candidates, since a tough matchup works against the player clearing the line; new "Weak matchup only (Rank 20+)" filter checkbox next to Ladder only, flagging rows where the upcoming opponent ranks in the bottom third of the league (Opp Rank 20-32) against that exact position/stat -- reuses the existing Opp Rank column's own number, zero new data needed, and composes with Ladder-only to surface players who've both proven a ceiling AND are facing a soft matchup right now (7 real current hits); ⭐ MUST BET's fixed bar lowered from 150% to 100% now that the consistency gate keeps it meaningful at a lower threshold, surfacing 7 real Over + 7 real Under rows where none qualified before; ⭐ MUST BET now also requires a perfect record across the selected weeks (zero games on the wrong side of the line) on top of its fixed % bar, correctly holding back 3 real rows that a big-average-but-one-outlier pattern would have wrongly earned; 🪜 ladder badge given a 30-yard minimum line (cutting real hits from 44 to 12, all now genuinely meaningful) plus a new "Ladder only" filter checkbox at the top; new 🪜 ladder badge next to a player's name -- flags QB Pass/Rush Yds, RB Rush/Rec Yds, and WR/TE Rec Yds rows where the player's single best game this season already cleared 2x their CURRENT posted line, using only data already on hand, no new odds markets fetched; line-shopping tie-breaks now go to the better PRICE, not book list order -- fixed after Trevor caught DraftKings being highlighted over FanDuel despite FanDuel's -110 beating DraftKings' -116 at an identical line, which also uncovered and fixed a related bug where the 🧊 price gate was checking the wrong side's price for Under bets; zero-stat weeks now backfilled as real zeros instead of silently vanishing from averages -- fixed after Trevor caught a missing Week 1 for a player who'd actually played; ⭐ MUST BET tier made a FIXED 150% bar, decoupled from the "How picky" slider, cutting real MUST BET rows from ~20-25 down to 5; new Game filter with an automatic Tuesday-morning reset, so it never gets left stuck on an already-played game; new 🛡️ O-line concern badge on QB/RB rows, flagging when their own team's O-line has an official injury designation even if they themselves don't; new ⛑️ injury badge sourced from the NFL's official weekly injury report via nflverse, no scraping needed; Edge/Anc. Edge now graded against the most advantageous DraftKings/FanDuel/BetMGM line for whichever side recent form favors, with that book highlighted and the price gate updated to match; diagnosed a one-off LV Pass-TDs discrepancy as stale nflverse data, not a bug; shareable artifact link republished several more times with Trevor's real Mac data; new personal ✅/🌕/❌ bet marks per row, saved in-browser so a re-sync never wipes them, plus a "Hide ❌ rows" filter; new "How picky" slider controls the 🔥/🧊/❓ significance threshold live, with a stricter default than before; ❓ refined to no longer fire on flat sign disagreements; Opp Rank recolored as a continuous red-to-green gradient instead of a hard cutoff; table now defaults to sorting by signal strength; new ❓ "needs review" signal; 🔥/🧊 now gated by sportsbook price; man/zone coverage tags upgraded to 3-tier labels; team-level man/zone coverage-scheme tags; Air Yards context stat; defense card now names each week's opponent; bad-weather red/amber flag; defense detail modal; tiered 1-3 🔥/🧊 scale; game-by-game box scores; dashboard also published as a shareable claude.ai artifact link on request)

## What it is
A local, self-run program that compares each NFL player's recent stats,
their upcoming opponent, what that opponent allows to the player's
position, current Vegas prop lines from DraftKings/FanDuel/BetMGM, the
weather forecast for the game, and that opponent's man/zone
coverage-scheme tendency — rendered as a sortable/filterable HTML
dashboard. The 🔥/🧊 signal now also checks that the price is actually
worth betting into, not just that the stats agree. Fully self-contained,
no server, no ongoing Claude usage per refresh.

## Where it lives
Trevor's Mac: `~/Documents/Gambling Program/`
- `team_mapping.py` — abbreviation <-> full team name mapping
- `stadium_info.py` — lat/lon + dome/retractable-roof flag for every
  stadium in the current schedule (incl. international venues), keyed by
  nflverse's exact "stadium" string
- `fetch_stats.py` — pulls nflverse schedule + weekly player stats (free,
  no key), computes recent-game averages, defense-allowed-by-position
  (raw per-game logs + which week/opponent each game came from), and
  team-totals-by-position (for team-share). Also carries the week's full
  schedule (`schedule_this_week`: gameday/gametime/home/away per game),
  now also used to power the Game filter below. As of 2026-09-24, also
  pulls nflverse's snap-count data + player-ID crosswalk to backfill
  zero-stat weeks for players who played but recorded no stats -- see
  its own section below.
- `fetch_injuries.py` — pulls the NFL's official weekly injury report
  (status, body part, practice participation) from nflverse (free, no
  key, structured — same trusted source as `fetch_stats.py`, fetchable
  straight from the cloud sandbox too), and also aggregates a team-level
  offensive-line (T/G/C) injury view used by the 🛡️ badge below
- `fetch_odds.py` — pulls Vegas player prop lines (DK/FD/BetMGM) from The
  Odds API using Trevor's key (stored in `config/odds_api_key.txt`), now
  also computing a consensus Over price and consensus Under price per
  market (median across books) for the 🔥/🧊 price gate
- `fetch_weather.py` — pulls a kickoff-hour forecast for each outdoor
  game's stadium from Open-Meteo (free, no key)
- `fetch_coverage.py` — scrapes each team's season-to-date man/zone
  coverage rate from a free public third-party page (no key; see its own
  section below)
- `build_dashboard.py` — merges all five caches into `output/dashboard.html`
- `run.py` — one-command orchestrator (`python3 run.py`)
- `README.md` — full usage instructions, kept current with every feature

## Why it's architected this way
This Cowork account's cloud sandbox (and even its bridge to Trevor's own
Mac via Claude's tools) sits behind an account-level network egress
allowlist that blocks arbitrary external APIs (confirmed: api.the-odds-api.com,
site.api.espn.com, api.sportsdata.io, api.open-meteo.com, and
www.sharpfootballanalysis.com all rejected — the Open-Meteo call fails
identically from both the cloud sandbox and Trevor's own Mac via
`device_bash`, confirming this is an account-level policy, not an
environment quirk). GitHub/raw.githubusercontent.com are allowed, which
is why nflverse data can be fetched from the cloud sandbox directly, but
Odds API, Open-Meteo, and the coverage-scheme page cannot.

The fix: the program is a **standalone Python program Trevor runs himself
in his own Terminal**, outside of any Claude tool call. That way there's
no injected proxy and it just uses his Mac's normal internet connection.
This also means zero Claude token usage per refresh — he runs
`python3 run.py` whenever he wants updated data, and everything derived
from that data (Recent Avg, Edge, Team Share, the 🔥/🧊 tiers, the price
gate, the bad-weather flag, the coverage tags, etc.) recomputes
automatically from the fresh numbers with no extra step. To get back to
the dashboard after closing Terminal/the browser, he doesn't need to
re-run anything — `output/dashboard.html` is a static file that's still
sitting in `~/Documents/Gambling Program/output/`; double-clicking it in
Finder (or `open output/dashboard.html` from Terminal) reopens the
last-built version instantly. He only needs to re-run `python3 run.py`
when he wants fresher data.

## Data sources
- **Stats/schedule**: nflverse (free, public, community-maintained,
  updates nightly during the season). Uses the `stats_player` release tag
  on nflverse-data (the old `player_stats` tag was deprecated 2025-08-01 —
  nfl_data_py's PyPI package (0.3.3) still points at the deprecated tag,
  which is why this was hand-rolled against the raw CSV URLs instead of
  using that library). Confirmed via a direct column dump of
  `stats_player_week_2026.csv` (150 columns total) that it also carries
  `passing_air_yards`, `receiving_air_yards`, and `air_yards_share` —
  real, well-populated columns, which is how the Air Yards stat (below)
  became possible without a new data source. The schedule
  (`nfldata/games.csv`) also carries stadium name, roof type, and
  Eastern-time kickoff for every game, including international ones — no
  separate stadium schedule needed. Also uses nflverse's `snap_counts`
  release (per-player-per-week offensive/defensive/special-teams snap
  counts) and its `players` release (an ID crosswalk between nflverse's
  own gsis-style player IDs and Pro-Football-Reference's IDs) as of
  2026-09-24 -- see the zero-stat-week backfill section below.
- **Vegas lines**: The Odds API (Trevor's own key, free tier constraints
  apply — 20,000 req/mo confirmed available at build time). Player prop
  markets used (`fetch_odds.py`'s `DEFAULT_MARKETS`): player_pass_yds,
  player_pass_tds, player_pass_interceptions, player_pass_completions,
  player_pass_attempts, player_rush_yds, player_rush_attempts,
  player_receptions, player_reception_yds, player_tds (Anytime-TD-Scorer,
  see TDs section below). Fetched per-book for draftkings/fanduel/betmgm
  (point + price for each), plus a consensus Over/Under price per market
  (median across books) used only for the 🔥/🧊 price gate — see its own
  section below. Air Yards has no market here at all — see its own
  section below.
- **Weather**: Open-Meteo (free, no key). nflverse's `gametime` field is
  always Eastern time regardless of where the stadium actually is
  (verified against real London/Munich/Melbourne kickoffs in the 2026
  schedule), so `fetch_weather.py` always requests the forecast in the
  `America/New_York` timezone and matches gameday+gametime directly
  against it — no per-stadium timezone lookup needed.
- **Coverage scheme (Man/Zone rate)**: Sharp Football Analysis's free
  public "NFL Man & Zone Coverage Rates" page — see its own section below
  for how this was researched and why it's limited to team-level data.

## Current dashboard columns
Player (click to open a full stat-card modal), Pos, Team, Opp (shows a
small "High Man"/"Medium"/"Low Man" coverage-scheme tag when available;
click to open that defense's card — see below; "@" prefix when the
opponent is home / this player's team is away), Avg (over whatever weeks
are checked in the **Weeks** filter — see its own section below), Opp
Allows, Opp Rank, Team Share, Anticipated, **Edge**, **Anc. Edge**,
**🔥/🧊/⭐** (1-3 flame/ice tiers plus a rarer 4th ⭐ MUST BET tier —
see its own section below — all gated by price, see its own section
below), **❓** (Edge/Anc. Edge don't confidently agree but one is
significant — see its own section below), DraftKings, FanDuel, BetMGM
(each book shows its line with its price in parentheses, e.g.
"255.5 (-110)"), **Weather** (red/amber flag for bad conditions — see
below). A Stat-type filter (Pass Yds, Receptions, etc.) combines with the
Position filter so e.g. RB+Receptions narrows both the table and the Opp
Rank calculation to that exact stat. A **Game filter** (added
2026-09-24, see its own section below) can also narrow the table to just
one matchup's players.

Hit Rate is the only calculation still hidden from the UI (removed per
Trevor's earlier "gonna re-add later" request) — logic remains intact in
`deriveStats()` in build_dashboard.py.

## Zero-stat weeks now count as real zeros (fixed 2026-09-24)
Trevor caught this directly, looking at Austin Hooper's player-card
box score: "why doesn't this show hoopers week 1 stats? he had 0, but
he still played week 1." Confirmed the exact mechanism: nflverse's
weekly player-stats file (`stats_player_week`, the source for
everything in this dashboard) only includes a row for a player in a
given week if they recorded at least one relevant stat that week (a
target, a carry, a completion, etc.) — a player who was active and
played real offensive snaps but simply never touched the ball that week
(Hooper: 14 real offensive snaps in Week 1 per nflverse's own snap-count
data, but zero targets/catches, so Week 1 is entirely absent from
`stats_player_week` for him — not a row of zeros, no row at all).

That absence isn't cosmetic — it directly answered Trevor's own
follow-up: "yeah i think we should do that. cause that meaningfuly
affects the projections." Every downstream average
(`compute_recent_player_stats`) was silently computed over fewer games
than the player actually played, quietly inflating "Avg (Wk X-Y)" and
skewing Team Share/Anticipated/Edge — worst for exactly the low-target
TEs/RBs whose zero weeks are both common and meaningful. Confirmed the
real-world size of the effect on Hooper himself: pre-fix, his "Avg
(Wk 1-2)" showed 20.0 receiving yards (his Week 2 game only, silently);
post-fix, it correctly shows 10.0 (a true average of his Week 2's 20
yards and Week 1's real 0) — a 50% swing directly from this one fix.

**Implementation**: new `backfill_zero_stat_weeks(weekly_df, season)` in
`fetch_stats.py`, called right after `load_weekly_stats()` and before
the `total_tds` computation, so every downstream consumer
(`compute_recent_player_stats`, `compute_defense_allowed`,
`compute_team_position_totals`) sees the same, consistent, augmented
data with zero special-casing needed elsewhere.
- Pulls nflverse's own `snap_counts_{season}.csv` (free, no key,
  separate dataset) to find every (player, week) where the player
  actually took a real offensive snap (`offense_snaps > 0`).
- `snap_counts` keys players by `pfr_player_id` (Pro-Football-
  Reference's own ID scheme), not the gsis-style `player_id` used
  everywhere else in this project, so this also pulls nflverse's own
  player-ID crosswalk (`players.csv` — confirmed a clean `gsis_id`/
  `pfr_id`/`display_name` mapping exists there) to translate between the
  two.
- For any (player, week) with a real offensive snap but no existing row
  in `weekly_df`, inserts an explicit all-zero stat row (every
  `POSITION_STATS[pos]` column set to 0.0), using the player's team/
  opponent straight from `snap_counts`' own columns for that game.
- **Two scope decisions, disclosed rather than silently assumed**: (1)
  only backfills players who ALREADY have at least one real stat row
  this season — fixes exactly the bug Trevor found (a tracked player
  missing one week) without pulling brand-new, never-targeted players
  onto the dashboard who wouldn't otherwise appear there at all; (2) the
  new zero row's POSITION comes from the player's own EXISTING real rows
  in `weekly_df`, not from `snap_counts`' own position label —
  `snap_counts` sometimes tags a running back "HB" instead of "RB",
  which wouldn't match `POSITION_STATS`' keys and would silently skip a
  real backfill candidate if trusted directly.
- Fails soft: if either nflverse dataset can't be fetched, prints a
  warning and returns `weekly_df` unchanged rather than blocking the
  whole `fetch_stats.py` run — same pattern used for coverage scraping
  and injury fetching elsewhere in this project.

**A side effect worth flagging, not a bug**: with zero weeks now counted
for real, a handful of low-volume players' true averages came out lower
than before (previously averaged only over their "good" weeks), which
dropped a few of them below this dashboard's existing minimum-relevance
filter (`RELEVANCE_FILTER` in `build_dashboard.py` — e.g. TE/WR requires
average targets > 1). Confirmed via a direct before/after row-count diff
on the real production build: total rows dropped from 1382 to 1370 (12
rows = 3 players — Calvin Ridley, Kevin Coleman Jr., Tyler Higbee — each
losing their 4 stat rows). Traced each one: e.g. Tyler Higbee's average
targets dropped from 2.0 (his one real game) to 1.0 (averaged with a new
real zero week), which fails the TE relevance bar of "> 1" by exactly
the amount the fix changed. This is the fix working as intended — their
true average genuinely is lower once a quiet week is counted instead of
ignored — not a regression, but disclosed here since it's a visible,
surprising-if-unexplained side effect of an otherwise-invisible data fix.

Verified via headless Playwright and direct Python checks against real
2026 Week 1-2 data:
- Confirmed directly against raw nflverse data that Austin Hooper has
  exactly one row in `stats_player_week_2026.csv` (Week 2 vs CAR) and
  that `snap_counts_2026.csv` shows him with 14 offensive snaps in Week
  1 (vs PIT) despite zero recorded stats that week — the exact
  underlying data gap being fixed.
- Confirmed the `players.csv` crosswalk cleanly maps Hooper's
  `pfr_id` (`HoopAu00`) to his `gsis_id` (`00-0032392`), the same ID
  already used as the dict key everywhere else in this project.
- Ran `fetch_stats.py` end to end (cloud sandbox and, separately,
  Trevor's own Mac): both printed "Backfilled 49 zero-stat week(s)" and
  produced byte-for-byte matching results (`data/stats_cache.json`
  confirms Hooper now has `games_used: 2`, both weeks present, correct
  10.0 average).
- Rendered the full production dashboard via headless Playwright (1370
  rows, zero JS console errors) and confirmed `ROWS` shows Hooper's
  `game_log: [20, 0]` for `game_weeks: [2, 1]` — the real fix, visible
  end to end from raw data through to the rendered page.
- Diffed the exact row-level before/after (see side-effect note above)
  to positively identify and explain every row that disappeared, rather
  than accepting a changed row count without investigating it.

Pushed to Trevor's Mac (`fetch_stats.py`), rebuilt there with his own
fresh nflverse pull (identical 49-backfill, 1370-row result, confirming
the two environments agree), re-staged fresh, and republished to the
shared artifact link as **Version 13** — the current, correct artifact at
that point (later superseded by Version 14 once the line-shopping
tie-break fix below was also added, then by Version 16 once the 🪜
ladder badge was added, then by Version 17 once the MUST BET consistency
gate below was added, then by Version 18 once the MUST BET threshold was
also lowered — see the Status section for the current, correct artifact
state).

## ⭐ MUST BET tier — a 4th, rarer tier above 3 flames/ice (added 2026-09-24)
Trevor's request: "can you make the certainty filter either have 4 level
options or be picker? there are too many 3 stars right now." Asked to
clarify scope before building (a 4th repeated flame/ice character vs. a
continuous pickier slider vs. both), he answered directly: "make the 4th
tier, but make it just a star and consider that a MUSTBET."

**What changed**: the 🔥/🧊 scale used to top out at 3 (both flame and
ice). It now has a 4th, strictly rarer level above that ceiling, rendered
as its own distinct badge — `⭐ MUST BET` — rather than a 4th repeated
flame or ice emoji, per Trevor's exact instruction. A row earns it when
BOTH Edge and Anc. Edge clear an even higher bar than the old 3-flame/
3-ice threshold, in the same direction (same "two signals must agree"
rule every other tier already uses).

**Implementation (first version)**: `EDGE_TIERS` extended from 3
thresholds to 4, using the exact same ratio-scaling pattern already
established for the "How picky" slider (see its own section below) —
continuing the original fixed-value gap pattern (15→25→40, i.e.
+10/+15) one step further to 15→25→40→60 (+10/+15/+20), expressed as
multiples of `SIGNIFICANT_EDGE_PCT`: `[1x, 25/15, 40/15, 60/15]`. The
existing tier-counting loop inside `enrichRow()` needed **zero
changes** — it already generically loops over however many entries
`EDGE_TIERS` has, so adding a 4th threshold was enough on its own to
produce `hot_level`/`cold_level` values of 4. Two places did need new
code:
- `signalEmoji(r)`: a new branch checked FIRST, before the existing
  flame/ice-repeat logic — `if (r.hot_level === 4 || r.cold_level === 4)`
  renders `<span class="cov-tag mustbet-tag">⭐ MUST BET</span>` (a new
  gold-tinted CSS class, `.mustbet-tag`) instead of falling through to
  `'🔥'.repeat(r.hot_level)`, which would otherwise have printed 4 flames.
- `signalRank` (the hidden numeric field the default sort uses):
  extended with a new top value of 7, above the old top of 6 (3-flame/
  3-ice), so MUST BET rows sort to the very top of the table, ahead of
  everything else.

**This first version scaled with the picky slider — Trevor then asked
for it to be fixed instead. See the next section below for the follow-up
fix (150%, a separate constant, not slider-adjustable) — this was, at
the time, the current, correct implementation. See the MUST BET
consistency-gate section further below for the additional requirement
added 2026-09-24 on top of this fixed bar.**

**Real-data impact of the FIRST version (superseded)**: verified against
Trevor's own real Mac data (2026 Week 3, 1382 rows, real DK/FD/BetMGM
odds) at the slider's default setting: 25 rows showed ⭐ MUST BET, and
19 rows showed 3-flame/3-ice — versus the old 3-tier system, where all
44 of those rows would have shown as the single most-crowded "3 stars"
bucket. This was an improvement but Trevor said even 25 was still too
many — see the follow-up section below for the fix that actually landed.

Verified via headless Playwright (first version):
- `verify_mustbet.py` (first attempt): used fully-synthetic data with a
  fake opponent team, which correctly stayed at `hot_level: 0` even at a
  100% synthetic edge — not a bug, but an artifact of the test design,
  since `rankDefenses()` needs a real opponent in `DEFENSE_LOGS`/
  `DEFENSE_GAMES` to compute Anc. Edge at all, and the tier-counting code
  requires both Edge and Anc. Edge to be non-null before counting any
  tier. Diagnosed correctly and the test methodology was fixed rather
  than the code.
- `verify_mustbet2.py`/`verify_mustbet3.py`: corrected approach cloning
  REAL rows from `ROWS` (keeping real position/opponent/stat_col so
  defense lookups succeed) and mutating only `game_log`/`vegas_line`/
  prices — confirmed the tier progression 0→1→2→3→4 fires exactly at the
  20%/33.3%/53.3%/80% boundaries, as designed for that first version.
- `verify_mustbet4.py`: full production render (1382 rows, zero console
  errors — all real rows sit at tier 0 in the cloud sandbox since no real
  odds are fetchable there, as expected/documented throughout this
  file), plus DOM-level confirmation that an injected MUST BET row
  renders the literal "MUST BET" text and sorts to row #1.
- `verify_final.py`: final smoke test run directly against the file
  freshly staged from Trevor's real Mac build (real odds included) —
  produced the headline numbers above: `{'totalRows': 1382, 'tierCounts':
  {'0': 1258, '1': 58, '2': 22, '3': 19, '4': 25}, 'pickyLabel': '1★
  ≥20%  ·  2★ ≥33%  ·  3★ ≥53%  ·  ⭐ MUST BET ≥80%'}`, zero console
  errors.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data, and republished to the shared artifact link. See the "Artifact
republish process bug" section below for an important correction about
which artifact version actually contains this (and the Weeks filter).

## ⭐ MUST BET made a FIXED bar, decoupled from the picky slider (follow-up, 2026-09-24)
After seeing the first version's real count (~20-25 rows), Trevor said:
"there just can't be this many must bets. need a little more ability to
define realllly good shit. there are like 20 right now." Asked to
clarify how he wanted it tightened (a second independent slider just for
MUST BET, a one-time raise of the existing scaled bar, or a fixed
top-N cap), he answered: "i think must bet should always be the same
criteria, just like a line that almost doesn't even make sense. then
from there, do 3 star ranking. so like have a must bet be somethign that
is absurd."

**What changed**: MUST BET's bar is no longer part of the `EDGE_TIERS`
array that scales with the "How picky" slider. It's now a completely
separate, hardcoded constant — `MUST_BET_EDGE_PCT = 1.50` (150%) — that
never moves regardless of where the slider sits. 1-star/2-star/3-star
still scale with the slider exactly as before (now back to the original
3-element `EDGE_TIERS`, since the 4th slot that used to hold MUST BET's
scaled value is gone). This is a genuinely different design from the
first version: before, dragging the slider moved ALL 4 tiers together;
now, dragging it only ever moves 1/2/3, while MUST BET stays put at its
own fixed, "absurd" bar per Trevor's explicit request.

**Implementation**:
- `let EDGE_TIERS = [...]` (both the initial declaration and inside
  `applyPickySetting()`) shrunk back to 3 elements, scaled off
  `SIGNIFICANT_EDGE_PCT` at the same 1x/1.67x/2.67x ratio as before the
  4th tier existed.
- `const MUST_BET_EDGE_PCT = 1.50;` — a `const`, not a `let`, and
  deliberately declared outside `applyPickySetting()` so nothing ever
  recomputes it when the slider moves.
- `enrichRow()`'s tier-counting loop still counts 1/2/3 off `EDGE_TIERS`
  as before, then adds one line per direction: `if (weaker >=
  MUST_BET_EDGE_PCT) hotLevel = 4;` (and the mirror for `coldLevel`) —
  the weaker-of-Edge/Anc.-Edge check is unchanged, only the bar it's
  compared against for level 4 is now independent of the slider.
- `signalEmoji()`'s MUST BET badge tooltip now reads the bar off
  `MUST_BET_EDGE_PCT` instead of `EDGE_TIERS[3]` (which no longer
  exists), and says explicitly that the bar is fixed.
- The "How picky" slider's live label and its column-header/tooltip text
  were updated to say MUST BET's cutoff is "(fixed, not slider-
  adjustable)" so it's clear on the page itself, not just in the docs,
  that dragging the slider won't touch MUST BET.

**150% is Claude's own reasonable-looking pick for "absurd,"** not a
proven cutoff — it means recent form running at 2.5x the sportsbook's
own posted line, chosen because it's a large step up from the ~80% bar
that still let ~20-25 rows through, while still being reachable rather
than a threshold nothing could ever cross. Flagged to Trevor the same
way every other arbitrary constant on this page is flagged. It's a
one-constant change (`MUST_BET_EDGE_PCT`) to retune up or down if 150%
turns out to be too loose or too strict once he's watched it over more
weeks of real data.

**Real-data result**: verified against a fresh rebuild on Trevor's own
Mac (2026 Week 3, 1382 rows, 496 rows with real posted lines) — **only 5
rows now hit ⭐ MUST BET**, down from ~20-25 under the slider-scaled
version. All 5 were on the Over side (receiving yards/receptions
markets), with real edge_pct values ranging ~159%-567% (i.e. genuinely
absurd — recent averages running multiple times the posted line). This
is a much more selective, "really good shit only" result than either the
original 3-tier system or the first MUST BET version.

Verified via headless Playwright (`verify_mustbet_fixed.py`,
`verify_real_counts.py`):
- Confirmed `EDGE_TIERS.length === 3` and `MUST_BET_EDGE_PCT === 1.5`
  immediately after load.
- Moved the picky slider to its min (10) and max (30) and confirmed
  `MUST_BET_EDGE_PCT` never changed and the live label always showed
  "⭐ MUST BET ≥150% (fixed, not slider-adjustable)" at every slider
  position.
- Cloned a real row (real position/opponent/stat_col so defense lookups
  resolve) and forced its edge to land at 149% and 151% at three
  different slider settings (10/20/30): confirmed 149% always produced
  `hot_level: 3` (not MUST BET) and 151% always produced `hot_level: 4`
  (MUST BET) at every slider position tested — i.e. the boundary truly
  doesn't move with the slider. Also confirmed a row at the OLD 80%
  threshold now correctly lands at `hot_level: 3`, not 4, since that bar
  no longer qualifies under the new fixed 150% line.
- Ran the full real production table (rebuilt on Trevor's Mac, staged
  back into the cloud sandbox) through `enrichRow()` for every one of the
  1382 rows and tallied real tier counts: `{'0': 1257, '1': 24, '2': 7,
  '3': 23, '4': 5, '-1': 33, '-2': 16, '-3': 17, '-4': 0}` — 5 real MUST
  BET rows, all Over side. Zero JS console errors.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data, staged back to confirm the real 5-row result, and republished
to the shared artifact link as **Version 12** (later superseded by
Version 13 once the zero-stat-week backfill above was also added — see
that section for the current, correct artifact state).

## ⭐ MUST BET now also requires a perfect record over the selected weeks (follow-up, 2026-09-24)
After the ladder-badge work (below), Trevor asked more generally: "i want
some more must-bet logic built in. if the player has not gone over that
line in any game in the weeks that i've defined, for it not to be a
must-bet. that make sense?"

**Worth disclosing up front**: taken completely literally, that exact
gate can never fire, and Trevor was told this before anything was built.
MUST BET requires the player's average over the selected weeks to be way
above the line (the FIXED 150% bar above) — but if the average is above
the line, the maximum of that same set of games is mathematically
guaranteed to be above the line too (a set's maximum is always ≥ its own
average). So "has this player EVER cleared the line" can't be the real
gap; a big average always implies at least one individual game already
did. Flagged this directly and asked Trevor what he actually wanted
instead — his answer, more precise than the original ask: "i don't want
it to be a must bet if that player has ever gone beneath the line within
the weeks i'm filtered to." That's a genuinely different, buildable bar:
not "has it ever happened" but "has it happened EVERY time" — a perfect
record requirement, not just a big average.

**What changed**: MUST BET (⭐, level 4) now additionally requires zero
games below the line anywhere in the currently selected weeks for an
Over (🔥) call, or zero games above the line for an Under (🧊) call —
on top of the existing FIXED 150% Edge/Anc. Edge bar, which is
unchanged. This stops one huge outlier game from single-handedly
carrying an otherwise-inconsistent player into the top tier: a player
who dropped 400 yards once but fell under the line every other game in
the window will no longer earn ⭐ MUST BET, even though his average
alone still clears 150% — he'll fall back to whatever 1-3 star tier his
numbers still legitimately earn, same graceful degradation already used
for the price gate. 1/2/3 stars are untouched by this change; only level
4 is gated.

**Implementation**: `deriveStats()` now also returns `below_count` (how
many games in the selected-weeks slice finished strictly below
`bestLine`) and `above_count` (strictly above `bestLine`, the same value
already being computed as `hits`) — a push (exactly on the line) counts
as neither, so a player who's never missed but has tied the line exactly
in some games still qualifies. In `enrichRow()`, the existing lines
`if (weaker >= MUST_BET_EDGE_PCT) hotLevel = 4;` / `... coldLevel = 4;`
each gained an extra `&&` condition — `derived.below_count === 0` for
the hot/Over side, `derived.above_count === 0` for the cold/Under side —
so level 4 is only ever assigned when both the fixed % bar AND the
perfect-record requirement hold. The MUST BET tooltip and the code
comments above `MUST_BET_EDGE_PCT` were both updated to explain the new
requirement, including the "why the literal ask was a no-op"
math, so a future reader (or Trevor himself) doesn't have to rediscover
that reasoning from scratch.

**A property worth knowing, not a defect in this change**: on the Under
(🧊) side, MUST BET was already effectively unreachable before this
change and still is — the fixed 150% bar needs `edge_pct <= -150%`, but
since real stat values can't go below 0, the worst possible edge_pct is
exactly -100% (a player averaging 0 against any positive line). So the
mirrored `above_count === 0` gate is correct and symmetric in the code,
and would apply automatically if that threshold or the stat's value
range ever changed, but it doesn't currently change anything on the
Under side in practice — the ceiling was already the binding constraint
there, not consistency.

**Real-data impact**: checked what the fixed 150% bar alone (i.e. the
behavior immediately before this change) would have flagged on a fresh
rebuild of Trevor's actual Mac data — 3 rows: Kendrick Bourne, Jonnu
Smith, and Elic Ayomanor, all Rec Yds. Every single one of those 3 rows
had exactly 1 game below the line in the selected weeks — precisely the
one-outlier-carries-an-inconsistent-player scenario Trevor was worried
about. All 3 are now correctly held back from ⭐ MUST BET under the new
gate (falling back to whatever lower tier their real numbers earn); the
real MUST BET count on today's data is 0 with the gate in place, versus
3 without it.

Verified via headless Playwright (`verify_mustbet_gate.py`,
`verify_mustbet_real.py`, `verify_mustbet_impact.py`):
- Unit-tested `deriveStats()`'s new `below_count`/`above_count` fields
  directly across four synthetic game logs: all games above the line (0
  below, all above), all games below (all below, 0 above), a mixed case
  (1 below, rest above), and a case with an exact push at the line
  (confirmed a push counts as neither below nor above).
- Tested the real `enrichRow()` gate end-to-end on the Over side using a
  pre-populated `defCache` (so Anc. Edge is fully controlled without
  needing real defense data for a fake opponent): a perfect-record
  player crushing the line every game correctly still earns MUST BET
  (level 4); the exact bug scenario — one 400-yard outlier plus four
  games below the line — correctly falls back to level 3 instead of 4
  even though the raw % bar clears; the same outlier shape but with the
  other four games landing exactly ON the line (a push, not a miss)
  correctly still qualifies for MUST BET, confirming pushes aren't
  wrongly punished; a single below-line game among four otherwise-huge
  performances correctly still blocks level 4 and falls back to 3.
- Ran the real production table (freshly rebuilt on Trevor's Mac,
  re-staged fresh, 1370 rows) through the actual gate: 0 real MUST BET
  rows today (Over or Under), and separately confirmed, by replicating
  `enrichRow()`'s own Anc.-Edge math against the real data without the
  new gate applied, that exactly 3 real rows would have qualified under
  the OLD logic alone — see the real-data impact above.
- Full production render (1370 rows) with zero JS console errors, both
  for the synthetic gate tests and the real-data check.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data, re-staged fresh, and republished to the shared artifact link
as **Version 17** (later superseded by Version 18 once the threshold was
also lowered — see the section immediately below).

## ⭐ MUST BET threshold lowered to 100% (follow-up, same day, 2026-09-24)
Immediately after the consistency-gate work above, Trevor asked: "should
we make the must bet threshold a little lower? like 100?"

**What changed**: `MUST_BET_EDGE_PCT` dropped from `1.50` (150%) to
`1.00` (100%) — a one-line constant change, exactly as flagged when it
was first introduced. Recent form now only needs to be running at 2x the
posted line (down from 2.5x) to clear the fixed bar, combined with the
same unchanged consistency requirement from the section above (zero
games on the wrong side of the line in the selected weeks). The picky
slider's live label and the column-header tooltip both read the new 100%
value automatically, since both already referenced the constant rather
than a hardcoded number.

**Why this doesn't reopen the outlier problem the consistency gate just
closed**: lowering the % bar alone, without the gate, would have let
back in exactly the kind of one-big-game-carries-an-average case Trevor
flagged earlier this same day. But the consistency gate is independent
of and layered on top of the % bar — a player still needs a perfectly
clean record across the selected weeks no matter how low the percentage
threshold goes, so a lower bar surfaces more CONSISTENT overperformers,
not more outlier-driven ones.

**Real-data impact**: on the same real Mac rebuild used to verify the
consistency gate, the 100% bar (with the gate applied) produces **7 real
MUST BET Over rows** and, notably, **7 real MUST BET Under rows** — up
from 0 and 0 at the old 150% bar. The Over rows include some low-volume/
low-line stats (e.g. Matthew Stafford and Bo Nix both at exactly a 0.5
INTs line, meaning they've thrown 1+ interception in every game across
the selected weeks) alongside more traditional yardage overperformers
(Derrick Henry, Josh Oliver, David Montgomery, Darnell Mooney at Rec
Yds; C.J. Stroud at Rush Yds). The Under rows (Aaron Jones, Tony
Pollard, Jordan Love, C.J. Stroud, TreVeyon Henderson, various Rec Yds/
Receptions/Rush Yds) are all cases where `recent_avg` is exactly 0 over
the selected weeks — a genuine, if extreme, real-world case, not a data
bug: at exactly 0, `edge_pct` bottoms out at exactly -100% (the
mathematical floor for a non-negative stat against any positive line —
see the consistency-gate section above), which is now precisely at the
lowered bar. **Worth flagging to Trevor directly, not yet asked about**:
the low-line INTs cases in particular are a thinner signal than the
Rec Yds/Rush Yds cases, similar in spirit to the QB Rush Yds thin-line
issue the 🪜 ladder badge ran into before its 30-yard floor was added —
a 0.5-line stat only needs one score per game to trivially clear a 2x
bar. No minimum-line floor was requested or added for MUST BET (unlike
the ladder badge), so this is disclosed here rather than silently
patched; easy to add if Trevor decides these thin cases should be
excluded.

Verified via headless Playwright (`verify_threshold_change.py`):
- Confirmed `MUST_BET_EDGE_PCT === 1.0` immediately after load, and that
  the picky slider's live label reads "⭐ MUST BET ≥100%" at both slider
  extremes (10 and 30), confirming it still doesn't move with the
  slider.
- Confirmed a perfect-record synthetic case with `recentAvg` at EXACTLY
  2x the line lands precisely at `hot_level: 4` (the new boundary), and
  a case just under 2x lands at `hot_level: 3`, not 4.
- Re-ran the exact outlier-plus-one-miss scenario from the consistency-
  gate section above at the new lower bar and confirmed it's still
  correctly blocked (`hot_level: 3`, not 4) — the gate holds regardless
  of where the % bar sits.
- Ran the real production table (rebuilt on Trevor's Mac, re-staged
  fresh, 1370 rows) through the real gate and confirmed the 7-Over/
  7-Under real counts and every row listed above. Zero JS console errors
  throughout.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data, re-staged fresh, and republished to the shared artifact link
as **Version 18** — the current, correct artifact, superseding Version
17.

## 🪜 Ladder companion: "Weak matchup" filter (added 2026-09-24)
Trevor's request, given as a follow-up to the 🪜 ladder badge: "for the
ladder, can you also add a filter so if the defense the player is
opposing is 20-32 ranked, meaning they give up a lot of that stat."

**What changed**: a new checkbox, "Weak matchup only (Rank 20+)", sits
next to the existing "🪜 Ladder only" checkbox in the top controls bar.
When checked, the table narrows to rows where the upcoming opponent's
Opp Rank for that exact position/stat falls in the bottom third of the
league — i.e. a defense that allows a lot of that stat, a soft matchup.

**Zero new data needed**: Opp Rank (`r.def_rank`, already computed in
`enrichRow()`/`rankDefenses()` and already shown in its own column with a
red-to-green gradient) already runs 1 = toughest matchup (allows the
least) up to `def_rank_max` = easiest (allows the most). This filter just
checks whether that same number, already on the page, falls at the weak
end — no new fetch, no new per-row field, no new column.

**Implementation**:
- New constant `WEAK_DEFENSE_RANK_MIN = 20` and a small helper,
  `isWeakMatchup(r)`, placed right after the existing `ladderTag()`:
  returns `false` if `r.def_rank` is null/undefined, otherwise
  `r.def_rank >= WEAK_DEFENSE_RANK_MIN`.
- New state variable `let weakMatchupOnly = false;` alongside the
  existing `hideMarkedX`/`ladderOnly` flags.
- New clause `(!weakMatchupOnly || isWeakMatchup(r))` appended to
  `render()`'s existing `.filter()` chain — this runs after
  `enrichRow()` has already populated `def_rank`, and composes with
  every other filter (Position, Stat, Game, Hide ❌, Ladder only, search)
  automatically via plain logical AND, with no special-case code needed
  to let Trevor combine "Ladder only" + "Weak matchup only" at the same
  time.
- New `change` event listener on the checkbox sets `weakMatchupOnly` and
  calls `render()`, matching the exact pattern already used for Ladder
  only.
- Checkbox has a tooltip explaining it reuses the same Opp Rank number
  already shown in its own column, and suggesting the ladder+weak-matchup
  combo specifically.

**Assumption flagged, not asked about explicitly**: Trevor's own wording
was "20-32," which reads naturally as "bottom 13 of a 32-team league."
`WEAK_DEFENSE_RANK_MIN = 20` is a fixed lower bound, not a percentage —
if `def_rank_max` (the number of teams with valid data for the currently
selected weeks) ever comes in under 32, the top of the effective range
simply becomes whatever `def_rank_max` is (since a row's rank can't
exceed it), but the bottom of the range (20) doesn't rescale down with
it. In-season with real data this is effectively always 32, so it
doesn't currently change anything, but it's disclosed here rather than
silently handled a different way.

**Real-data impact**: verified against a fresh rebuild on Trevor's own
Mac (2026 Week 3, 1370 rows) — 523 of 1370 rows match "Weak matchup
only" on its own, with 0 rows incorrectly flagged (every matching row's
`def_rank` genuinely sits at 20 or above; every non-matching row's
`def_rank` is null or below 20). Combined with the existing "Ladder
only" filter, exactly **7 real players** currently satisfy both at once:
Dalton Schultz (Opp Rank 29), DJ Moore (26), Romeo Doubs (20), Christian
Watson (25), Bijan Robinson (21), Dalton Kincaid (27), and Jalen Coker
(21) — all Rec Yds, all with a real `def_rank_max` of 32. These are the
players this combo is meant to surface: proven season-ceiling performers
(🪜) who are also facing a defense that's currently a soft matchup for
that exact stat.

Verified via headless Playwright (`verify_weak_matchup.py` against the
cloud sandbox's own build, `verify_weak_matchup_real.py` against
Trevor's freshly re-staged real Mac data):
- Unit-tested `isWeakMatchup()`'s boundary conditions directly: `null` →
  false, rank 19 → false, rank 20 → true (the boundary), rank 32 → true,
  rank 1 → false.
- Confirmed the new checkbox exists in the DOM with the expected id.
- Drove the real `<input>` checkbox via `page.check(...)` (not just
  calling the JS function directly) and confirmed the visible table
  narrowed from 1370 to 523 rows, with every visible row's `def_rank`
  genuinely ≥20 and zero false positives.
- Combined it with the real "Ladder only" checkbox and confirmed the
  narrowed result matched exactly the 7 named players above, cross-
  checked against `ROWS`/`def_rank` directly rather than just trusting
  the DOM row count.
- Full production render (1370 rows) with zero JS console errors, both
  standalone and combined with Ladder-only.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data (`python3 run.py --only-dashboard`, since only the code
changed, not the underlying stats/odds), re-staged fresh, and
republished to the shared artifact link as **Version 19** — the current,
correct artifact, superseding Version 18.

## "Strong matchup" filter — the mirror of Weak matchup, for Unders (added 2026-09-24)
Immediately after the Weak matchup filter above, Trevor asked for its
mirror image: "can you make that filter again but only for like strong
defenses? so if i'm looking at unders i can see what defenses are
limiting that stat best?"

**What changed**: a new checkbox, "Strong matchup only (Rank 1-13)", sits
next to "Weak matchup only" in the top controls bar. It checks the exact
same `r.def_rank` field the Weak matchup filter and the Opp Rank column
already use, just at the opposite end — rank 1 is already documented
(both in the column tooltip and the Weak-matchup section above) as the
single toughest matchup for that position/stat, the defense currently
allowing the LEAST of it. So a low rank is exactly the signal Trevor
described: a defense that's limiting the stat well right now, which
makes an Under more attractive. Zero new data needed, same as the Weak
matchup filter — this is purely a different slice of a number already on
the page.

**Implementation** (mirrors the Weak matchup filter's own structure
exactly):
- New constant `STRONG_DEFENSE_RANK_MAX = 13` and a small helper,
  `isStrongMatchup(r)`, placed right after `isWeakMatchup()`: returns
  `false` if `r.def_rank` is null/undefined, otherwise
  `r.def_rank <= STRONG_DEFENSE_RANK_MAX`.
- New state variable `let strongMatchupOnly = false;` alongside the
  existing `weakMatchupOnly`/`ladderOnly`/`hideMarkedX` flags.
- New clause `(!strongMatchupOnly || isStrongMatchup(r))` appended to
  `render()`'s `.filter()` chain, composing with every other filter
  (including Weak matchup itself, though checking both at once would
  always return zero rows since a rank can't be both ≤13 and ≥20 —
  they're mutually exclusive by design, meant to be used one at a time
  depending on whether Trevor's looking at Overs or Unders).
- New `change` event listener wired the same way as the other checkboxes.

**Why 13, not a different cutoff**: mirrors the Weak matchup filter's own
width. Trevor's original "20-32" carves out the bottom 13 of a 32-team
league; `STRONG_DEFENSE_RANK_MAX = 13` carves out the same-size top 13
(ranks 1-13) from the other end, so both filters represent a symmetric
"top third" / "bottom third" of the league rather than using two
differently-sized buckets. Unlike the Weak matchup filter, this end
doesn't have a `def_rank_max`-shrinking edge case to flag — rank 1-13
means the same thing regardless of how many teams have valid data for
the selected weeks (it would only matter if `def_rank_max` itself ever
dropped below 13, which doesn't happen in-season with real data).

**Real-data impact**: verified against a fresh rebuild on Trevor's own
Mac (2026 Week 3, 1370 rows) — 613 of 1370 rows match "Strong matchup
only" on its own, with 0 false positives/negatives (every matching row's
`def_rank` genuinely sits at 13 or below). Combined with "Ladder only"
(mostly an unusual pairing — a proven season ceiling and a currently
tough matchup are somewhat opposing signals, not reinforcing ones the
way Ladder + Weak matchup are), exactly 4 real rows matched both: Davante
Adams, Josh Allen, Jaylen Waddle, and Tre Tucker — worth noting this
combo isn't really what either filter was designed for, but it composes
correctly regardless.

Verified via headless Playwright (`verify_strong_matchup.py` against the
cloud sandbox's own build, `verify_strong_matchup_real.py` against
Trevor's freshly re-staged real Mac data):
- Unit-tested `isStrongMatchup()`'s boundary conditions directly: `null`/
  `undefined` → false, rank 14 → false, rank 13 → true (the boundary),
  rank 1 → true, rank 32 → false.
- Confirmed the new checkbox exists in the DOM with the expected id.
- Drove the real `<input>` checkbox via `page.check(...)` and confirmed
  the visible table narrowed to exactly the independently-recomputed
  matching set (613 of 1370 real rows), with zero false positives or
  false negatives against `r.def_rank` directly.
- Combined it with the real "Ladder only" checkbox and confirmed the
  narrowed DOM result matched the independently recomputed 4-row set
  exactly.
- Full production render (1370 rows) with zero JS console errors, both
  standalone and combined with Ladder-only.

**A real connection hiccup during this deploy, not a code issue**: right
after this feature was built and verified, the link between this session
and Trevor's Mac dropped (the device bridge reported "not connected"),
which blocked the push/rebuild/republish steps for a while. Trevor
separately noticed his desktop app showing "Asleep or app closed" for
that computer. This is a connection-health issue between the Claude
desktop app and the session, unrelated to account usage/credits (Trevor
asked) and unrelated to the dashboard code itself — nothing needed to be
changed in the project because of it. It resolved and the connection came
back before this feature's deploy was finished.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data, re-staged fresh, and republished to the shared artifact link
as **Version 20** — the current, correct artifact, superseding Version
19.

## Explicit "DNP" rows in the game-by-game box score (added 2026-09-25)
Trevor asked, after opening Michael Pittman's player card and seeing only
a single Week 1 row despite the Weeks filter being set to Wk 1-3: "why
are there no week 2 stats for michael pittman." Investigated directly
against raw nflverse data before answering, rather than guessing:
- nflverse's weekly stats file has no Week 2 row for him at all -- not
  even a zero-stat row.
- nflverse's own snap-count data (the same source the zero-stat-week
  backfill above already relies on) also has no Week 2 entry for him --
  he took zero offensive snaps that week, not just zero recorded stats.
- The NFL's official injury report confirmed why: he was listed
  **Questionable, foot, did not participate in practice** in Week 2, and
  was back to a normal (no-designation) practice status by Week 3.

So this was a genuine absence (inactive/injured), not the same gap the
zero-stat-week backfill (see its own section above) was built to catch --
that fix only inserts a real zero for a week where a player took actual
snaps but recorded no stats. Here there were no snaps at all. Once
confirmed, Trevor asked for a follow-up fix: "can we make a fix to say
DNP so that i know that in this case."

**What changed**: the player modal's game-by-game box score now shows an
explicit `DNP` row for any week that's (a) in the currently selected
Weeks range, (b) already been played league-wide (strictly before the
current/upcoming week, `WEEK`), and (c) has no game entry for THIS
player -- instead of that week just silently not appearing, which is
indistinguishable from a data gap. A week that hasn't been played by
ANYONE yet (the current/upcoming week itself, or a future week Trevor
checked ahead of time) is deliberately NOT flagged -- there's no data for
that week for any player yet, so it isn't a signal about this player
specifically.

**Implementation**: inside `openPlayerModal()`, right after the existing
`gameIdx = playerSelectedIndices(first, selectedWeeks)` line:
- `playedWeeks` — a `Set` of the weeks this player actually has a real
  game entry for (built from `gameIdx`).
- `dnpWeeks` — every week in `selectedWeeks` that's `< WEEK` (already
  played league-wide) and NOT in `playedWeeks`.
- `gameEntries` — the real game rows and the new DNP weeks merged into
  one list of `{{week, idx}}` (idx `null` for a DNP week) and sorted
  descending by week, matching `game_log`'s own most-recent-first order,
  so a DNP row appears in its correct chronological position among real
  games rather than bunched at the top or bottom.
- The render loop now branches on `entry.idx === null`: a DNP row prints
  `"{{SEASON}} Wk{{N}} — DNP"` in the Game column and a muted "DNP" in
  every stat column, with a tooltip explaining it means no offensive
  snaps that week (inactive, injured, or a bye) rather than a data gap.
  A real game row renders exactly as before.

**Scope decision (disclosed, not asked)**: a DNP row doesn't show an
opponent (e.g. "Wk2 vs ATL") the way a real game row does, because that
would require threading each team's full-season schedule through to the
dashboard -- currently only the upcoming week's schedule
(`schedule_this_week`) is available client-side, not every team's
opponent for every past week. Doable later if Trevor wants the opponent
shown for a DNP week too; flagged here rather than silently built. Also
scoped to the player modal only -- the defense modal's box score isn't
touched (a defense could similarly have a bye week with no game entry
within the selected range), since that wasn't part of what was asked;
noted as a similar, not-yet-addressed gap below.

**Real-data impact**: verified against a fresh rebuild on Trevor's own
Mac (2026 Week 3, Weeks 1-3 selected by default) — Michael Pittman's card
now correctly shows "2026 Wk2 — DNP" between his real Week 1 and (once
played) Week 3 rows. Swept all 281 real players in the current build:
25 of them have at least one real DNP week flagged within the default
Weeks 1-3 selection, with zero false positives (every flagged week
genuinely has no real game entry for that player) confirmed by
cross-checking each one directly against `game_weeks`.

Verified via headless Playwright (`verify_dnp.py` against synthetic rows,
`verify_dnp_real.py` against Trevor's freshly re-staged real Mac data):
- Synthetic case: a player with real games in weeks 1 and 3 but a gap at
  week 2 (with an "already played" cutoff week of 4) correctly produces
  DNP at week 2 only, in the correct sorted position between the two real
  rows.
- Synthetic case: a gap at the CURRENT/upcoming week itself is correctly
  NOT flagged as DNP (nothing's happened there yet for anyone).
- Synthetic case: a gap at a FUTURE week beyond the current one is also
  correctly not flagged, for the same reason.
- Real production check: opened Michael Pittman's actual card and
  confirmed the modal's rendered HTML contains the literal "DNP" text in
  the correct row.
- Full sweep across all 281 real players in the current build: 25 real
  DNP rows flagged, 0 false positives (spot-checked directly against each
  player's own `game_weeks` array, not just trusting the DOM).
- Full production render with zero JS console errors throughout.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data, re-staged fresh, and republished to the shared artifact link
as **Version 21** — the current, correct artifact, superseding Version
20.

## "Targets" stat added, context-only like Air Yards (added 2026-09-25)
Trevor's request: "can you add targets to the receiving stats so that i
can see them in the popups for the players?"

**What changed**: RB/WR/TE now have a "Targets" row, right alongside
Receptions and Rec Yds, everywhere every other stat already shows up —
its own row in the main table, its own button in the Stat filter row,
and (what Trevor specifically asked for) its own row in both the player
modal's summary table and its game-by-game box score. It has no Vegas
line, Edge, Anc. Edge, or 🔥/🧊 — same as the existing Air Yards stat —
since there's no Odds API player-prop market for targets; it's a
context/comparison stat rather than a bettable one.

**Implementation**: the underlying data was already being fetched and
cached — `targets` has been in `POSITION_STATS` (RB/WR/TE) in
`fetch_stats.py` all along, since it's what the existing WR/TE relevance
filter (`avg targets > 1`) and the RB one (`carries + targets > 3`)
already check, and it's part of what the zero-stat-week backfill matches
on. It just wasn't exposed as its own row before. The entire fix is one
new tuple per position in `build_dashboard.py`'s `STAT_MARKET_MAP` —
`("targets", None, "Targets")`, market key `None` exactly like Air
Yards's `("receiving_air_yards", None, "Air Yards")` — placed right after
Receptions in each of the RB/WR/TE lists. Every other part of this
dashboard (`build_rows()`, `enrichRow()`, `deriveStats()`, the Stat
filter button list, the defense-allowed stat catalog, the player and
defense modals) is already generic over whatever's in `STAT_MARKET_MAP`,
so nothing else needed to change — the same reason Air Yards required no
special-casing when it was added earlier.

**Real-data impact**: verified against a fresh rebuild on Trevor's own
Mac — row count went from 1370 to 1625 rows (one new Targets row for
every relevant RB/WR/TE, matching roughly the same player set as
Receptions). Michael Pittman's real Targets row matches his real
Receptions row exactly for his one played game (3 targets, 3 receptions,
0 dropped/incomplete targets that game) — cross-checked directly against
raw nflverse data, not just trusting the dashboard's own math.

Verified via headless Playwright (`verify_targets.py` against the cloud
sandbox's own build, `verify_targets_real.py` against Trevor's freshly
re-staged real Mac data):
- Confirmed a "Targets" button exists in the Stat filter row.
- Cross-checked Michael Pittman's real Targets game_log against his real
  Receptions game_log directly.
- Swept every player with both a Targets and a Receptions row (243 real
  players) and confirmed receptions never exceeds targets in the same
  game, for any of them — a catch can't happen without a target, so this
  is a strong sanity check that the new column is reading the right
  underlying data rather than something mismatched or duplicated.
- Opened a real player's modal and confirmed "Targets" appears as its own
  row in the summary table, in between Receptions and TDs, with the
  expected Recent Avg / Opp Allows / Opp Rank / Team Share values (no
  Edge/Anc. Edge/book columns, same treatment as Air Yards).
- Full production render with zero JS console errors, both against the
  cloud sandbox's own data and Trevor's real re-staged data.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data (1625 rows), re-staged fresh, and republished to the shared
artifact link as **Version 22**, superseding Version 21 (itself since
superseded by Version 23 — see the impactful-injury section below).

## 🩹 "Impactful injury" badges + injury feed fixed for every team (added 2026-09-25)
Trevor: "we need to work on injury stuff. do you know what i'm looking
for? i asked you for this a while ago, but you only did the logic for
one team."

**The bug he was pointing at (confirmed against real data before
building anything)**: the 🛡️ O-line badge only appeared on Green Bay
players (Jordan Love, Chris Brooks, Kaleb Johnson, MarShawn Lloyd). Root
cause: the NFL injury report has two layers. Every team posts PRACTICE
participation all week, but the official GAME designations
(Out/Doubtful/Questionable) only appear on a team's FINAL report (Friday
for Sunday games, Wednesday for Thursday night). `fetch_injuries.py`
only read game designations, so mid-week it only ever caught the
Thursday-night teams (ATL/GB, plus DAL). Real Week 3 numbers: 290 injury
rows across all 32 teams, but only 12 with a game designation; 40
O-linemen on the report across 21 teams, only 2 of them (both GB)
designated. The ⛑️ own-injury badge had the same gap (5 rows total).

**What Trevor actually wanted**, clarified when asked: "'impactful
Injury' to the player and to the defense. there is context for each
position." Claude laid out a per-position model and Trevor approved it
as-is ("this is all great"):
- QB passing: own O-line, WRs, or TE out hurts; opponent's CBs, safeties,
  or pass rushers (DE/OLB) out helps.
- RB rushing: own O-line or own QB out hurts (loaded box vs. a backup);
  another RB out helps (more carries); opponent's DTs or LBs out helps.
- RB receiving: another RB out helps; opponent's LBs or safeties out helps.
- WR: another WR or TE out helps (vacated targets); own QB out hurts;
  opponent's CBs out helps.
- TE: a WR or another TE out helps; own QB or O-line out hurts (stays in
  to block); opponent's LBs or safeties out helps.
- Only players with a real role count: 50%+ average snap share this
  season (Claude's pick for "starter," flagged as arbitrary).
- Green badge = helps, red = hurts, hover names who's out and why.

**Implementation**:
- `fetch_injuries.py` rewritten. A game designation wins when it exists;
  otherwise a player who **did not participate in practice** for a real
  injury is flagged "Missed practice" (rest days / "Not injury related"
  reasons skipped; Limited/Full practice not flagged — limited players
  usually play). New `by_team` structure: every team's injured players
  at every position with status, severity (Out 4 > Doubtful 3 >
  Questionable 2 > Missed practice 1), injury, and **snap_pct** — average
  offense (or defense, for defenders) snap share over games played this
  season, from nflverse `snap_counts` translated via `players.csv`
  (pfr → gsis), the same sources the zero-stat-week backfill uses. A
  player with no snaps this season gets snap_pct None and never counts
  (his absence is already baked into everyone's numbers). The old
  `oline_by_team` is gone.
- `build_dashboard.py`: new `IMPACT_SNAP_PCT = 0.50`,
  `INJURY_POSITION_GROUP` (T/G/C→OL, DE/OLB→EDGE, DT/NT→DI, LB/ILB/MLB→LB,
  CB, S/FS/SS/DB→S, plus QB/RB/WR/TE), `stat_category()` (QB pass stats →
  "pass"; RB rush/carries/TDs → "rush", RB receiving → "rec"; WR/TE →
  "rec"), `IMPACT_RULES` keyed by (position, category), and
  `compute_injury_impacts()`, which attaches `injury_impacts =
  {helps, hurts}` to each stat row server-side. A player is never listed
  as his own impact (that's the ⛑️ badge). **Per stat row**, not per
  player, since e.g. an opposing DT out helps an RB's rushing but not his
  receiving. QB rushing, QB TDs, and INTs get no badge (no rule agreed
  for QB rushing; "helps" is backwards for interceptions).
- JS: `impactTags(r)` renders green 🩹▲ / red 🩹▼ pills (U+1FA79 +
  U+25B2/U+25BC) next to the name, with a multi-line tooltip per injured
  player (team, position, snap %, status, body part, reason). Full
  strength if any listed player is Out/Doubtful, faded (`impact-soft`)
  if they're only Questionable/missed practice. Shown on collapsed ↳
  rows in the grouped-by-player view too, since impacts differ by stat.
  Player popup: per-stat badges in the summary table's Stat column, plus
  a new "Injury impact (own team + OPP defense)" table listing each
  injured player once with status, snaps, why it matters, and which of
  this player's stats it affects. `injuryTag()` now colors "Missed
  practice" amber and says in its tooltip that it's from the practice
  report. The 🛡️ `oLineTag()` was removed (fully covered by the new
  rules).
- README updated to replace the 🛡️ section with the new badges and the
  per-position rules.

**Real-data impact** (fresh `fetch_injuries.py` + rebuild on Trevor's
Mac, 2026 Week 3, Friday before final reports): 98 injured players
cached across 31 teams (12 with game designations, 86 from the practice
report), 48 of them at 50%+ snaps. Impact badges now on 796 of 1625 stat
rows across 24 teams (was 1 team); ⛑️ badges on 177 rows across 20 teams
(was 5 rows). Most are faded right now because they're
practice-report-only; they firm up (or drop off) once Friday final
reports land and `python3 run.py` is re-run. Real examples verified:
BUF's other pass catchers (Knox, Palmer, Shakir, Kincaid) helped by DJ
Moore + Keon Coleman missing practice, and Josh Allen's passing hurt by
it; DJ Moore's own row lists Keon Coleman but not himself; every CHI
pass catcher hurt by Caleb Williams (93% snaps) missing practice; every
WR facing DAL helped at full strength by CB Cobie Durant (Out); Jordan
Love's passing hurt by Zach Bako-Bewele (T, Out, 52.5% snaps) and helped
by ATL CBs Billy Bowman Jr. (Questionable) and A.J. Terrell (missed
practice). **Caveat worth knowing**: GB's other Out lineman, Aaron Banks,
is filtered out at 37% average snaps — a starter who left a game early
through injury can dip under 50%, so the snap-share filter can
occasionally miss a real starter.

Verified via headless Playwright (`verify_impact.py`, 19 checks, run
against the cloud build and again against Trevor's re-staged real data):
impacts span 24 teams; both helps and hurts present; ⛑️ covers 20 teams;
no player listed as his own impact; every listed injury is 50%+ snaps;
QB INTs/rushing/TDs never carry impacts; RB receiving rows never cite
DL/OL; the BUF/CHI/DAL spot checks above; DOM renders the right code
points; faded badges present; collapsed ↳ rows keep their badges (641);
popup shows the Injury impact section and per-stat badges; zero console
errors. One bug caught during verification: a `\n` inside a JS string in
the Python template became a literal newline and broke the whole page
script ("Invalid or unexpected token") — fixed by escaping it as `\\n`,
then re-verified.

Pushed to Trevor's Mac (`fetch_injuries.py`, `build_dashboard.py`,
`README.md`), ran `fetch_injuries.py` + `build_dashboard.py` there,
re-staged fresh, and republished as **Version 23** — the current, correct
artifact, superseding Version 22.

**Follow-up fix, same day — SSL error on Trevor's own Terminal**: when
Trevor ran `python3 run.py` himself, `fetch_injuries.py` failed with
`SSL: CERTIFICATE_VERIFY_FAILED` (run.py continued without it). Cause:
the rewrite downloaded with `pd.read_csv(url)` directly, which relies on
the system certificate store that python.org Mac Python installs don't
use. `fetch_stats.py` already had a `fetch_csv()` helper that downloads
via `requests` (bundled certifi certificates) for exactly this reason;
`fetch_injuries.py` now uses the same helper for all three downloads.
Why testing didn't catch it: the device bridge's `device_bash` runs in a
Linux VM on Trevor's Mac with working certificates, not his macOS
Python. Lesson: any new nflverse download must go through `fetch_csv()`,
never `pd.read_csv(url)`. Confirmed no other script uses the direct
pattern.

**Second miss on the same fix — silent upload failures**: Trevor re-ran
and got the identical error. Checking the Mac directly showed the fixed
`fetch_injuries.py` had never landed: `device_commit_files` reported
"written" but the old file was still there (apparently re-sending a
cached earlier upload of the same path). The README from the earlier
batch push hadn't landed either (still showed the 🛡️ section), even
though that batch also reported "written"; `build_dashboard.py` from the
same batch had landed. Fixed by applying the edit to `fetch_injuries.py`
in place on the Mac via `device_bash`, and re-committing the README with
`force: true`; then confirmed with sha256 that `fetch_injuries.py`,
`build_dashboard.py`, `README.md`, and `fetch_stats.py` on the Mac are
byte-identical to the cloud copies. **Process rule going forward: after
every push to the Mac, verify with a sha256 comparison (or a grep for
the new code) — never trust the commit tool's "written" alone.**

## Bet slip: record the line and odds you got (added 2026-09-28)
Trevor: "add a space for me to record what line and odds i got a specific
bet at." When a row's Mark is ✅ Bet it, a small slip appears under the
selector (main table and player popup): Over/Under select, line, odds.
Stored like the marks — this browser's localStorage under
`nfl_prop_dashboard_bets_v1`, keyed by the same `WEEK|player|team|stat_col`
mark key — so it survives `python3 run.py` rebuilds and each week starts
clean. Inputs start empty; the grey placeholder is the current best line
and that book's price for the side the numbers favor (`best_line` /
`bookCellPrice`), explicitly a hint, not a record. Saves on change without
re-rendering the table, so tabbing Line → Odds keeps focus. Validation:
line must be a number; odds must be an integer with |odds| ≥ 100 (e.g.
-110, +125), otherwise a red border. Clicks inside the slip don't open
the player popup. Switching the mark away from ✅ hides the slip but
keeps the data. Marking ✅ inside the popup redraws the popup so its slip
appears immediately (scroll position kept), and edits in the popup sync
to the main table. Tooltips on the Mark header and README updated.

Verified with `verify_betslip.py` (14 checks) on the cloud build and on
Trevor's real rebuild (hints showed real values, e.g. 15.5 / -114): slip
appears only for ✅, starts empty with hints, click doesn't open popup,
Tab keeps focus, saved exactly `{side, line, odds}`, persists across
reload, invalid odds flagged / +125 accepted, hidden-but-kept on
Watching, popup marking + popup edits sync, zero console errors.

Note: localStorage belongs to where the page is opened, so bets entered
on the local `dashboard.html` don't appear on the shared claude.ai link
and vice versa.

Process notes: `build_dashboard.py` landed (sha256 matched), but the
README upload silently failed again (commit tool said "written", hash
unchanged); fixed by inserting the new README paragraph in place on the
Mac via `device_bash`, then hashes matched. Also: Trevor's Monday
11:23 run rolled the dashboard to **Week 4**; the injury cache is empty
only because nflverse has no Week 4 injury rows yet (first practice
report is Wednesday) — the fetch itself worked. Republished as
**Version 26**.

## Research: what drives QB interceptions (2026-09-26)
Trevor: "can you operate like a data scientist to analyze historical
features that drive quarterbacks to throw more interceptions and show me
things that i should be looking for as i built this model" (asked instead
of answering a web-hosting question — hosting is still open).

**Data**: 5,234 starting-QB regular-season games, 2016–2025, built from
nflverse weekly stats (2012–2025 loaded so early rows have history),
schedules (pre-game spread/total, roof, wind, temp, rest, starting QB),
and Next Gen Stats passing (aggressiveness = % of throws into tight
windows, time to throw, intended air yards). Every feature uses only
games strictly before the one being predicted. Scripts and outputs:
`research/int_study/` in the cloud outputs folder (not yet copied to
the Mac).

**Findings**:
- Base rate: 50.6% of starter games have ≥1 INT (0.74/game), trending
  down — 2024–25 was about 47.5%. INT counts are close to Poisson.
- **INT rate is mostly noise.** Year-over-year r = 0.25 for QBs with 300+
  attempts (sack rate 0.45, aDOT 0.55); odd-vs-even-week split-half r is
  0.18 or lower. Empirical-Bayes shrinkage: a QB's own rate only earns
  50% weight after about **1,150 attempts** (true-talent SD ≈ 0.44 points
  around a 2.27% league rate).
- **Recent form predicts nothing.** An INT in both of the last 2 games
  → 50.3% next game vs 50.6% otherwise (95% CI −3.5 to +3.0 pts); a
  last-3 average model improves on a constant by 0.09%. This directly
  undercuts the dashboard's INTs Edge/MUST BET logic (e.g. Stafford and
  Bo Nix MUST BET Over 0.5 after an INT in each of 2 games — the model
  has them at 49%, below DraftKings' no-vig 51–53%).
- **Real signals** (bucket effects, all pre-game):
  - Game script: 7+ point underdogs 55.7% vs 7+ point favorites 44.3%
    (CI 7–17.5 pts). This is INT *rate* (2.74 vs 1.77 per 100
    attempts), not volume — attempts are about the same.
  - QB aggressiveness (NGS tight-window %): top quintile 56.0% vs bottom
    44.3% (CI 7–16 pts). Top-quintile aDOT is also elevated.
  - Opponent INT-forcing ability (shrunk): top quintile 56.0% vs 48–51%
    for the rest.
  - Volume: actual attempts swing it massively (37% at ≤20 attempts →
    66% at 45+), but pre-game volume is only weakly predictable (prior
    8-start average: 47% → 52%).
  - No meaningful effect: wind, dome vs outdoors, home/away, rest days,
    divisional games. Cold (≤32°F) slightly elevated on a small sample.
    Second-year QBs are slightly higher (54%); rookies and experience
    mattered in the fuller model but aren't stable enough to trust yet.
- **Models** (trained 2016–22, tested on unseen 2023–25): the best
  logistic model improves log-loss by about 1.5% over a constant (AUC
  ~0.58–0.59); gradient boosting overfit (0.3%). The core 6-feature
  logistic (spread, total, shrunk QB INT rate, NGS aggressiveness,
  shrunk opponent INT rate, prior attempts) is well calibrated, and its
  tails separate: when it said ≥58%, the actual rate was 75% (40 games);
  when it said ≤42%, 36% (77 games) — small samples.
- **Controls**: a positive control (actual attempts) gives a clear lift;
  a negative control (shuffled labels) is worse than baseline; 300/300
  hand-recomputed defense priors and QB priors match (two
  first-career-start rows are blank vs 0, not a leak).
- **Bug caught during verification**: the stats file uses current
  franchise codes (LV/LAC/LA) while schedules use historical ones
  (OAK/SD/STL), which silently dropped 2016–19 Raiders and 2016 Chargers
  QB games and their defense history. Fixed by remapping schedule team
  codes (game_ids keep old codes in both files, so they're left alone);
  all results above are post-fix.
- **This week (2026 Week 3)**, core model vs DraftKings no-vig: mostly
  within ±4 pts (books already price most of this). Biggest
  disagreements: Jalen Hurts (model 51% vs book 42%), Jameis Winston
  (52% vs 61%), Cam Ward (43% vs 50%), Trevor Lawrence (46% vs 52%).
  There are no historical INT prop prices to backtest against, so model
  gaps are hypotheses, not proven edges.
- **Dashboard bug found**: `fetch_odds.py`'s consensus price is a median
  of American odds, which breaks across ±100 (C.J. Stroud INT Over shows
  "−2"; Geno Smith completions Under "−7"). This feeds the 🔥/🧊 price
  gate. Not fixed yet — flagged to Trevor.

**Recommendations given to Trevor**: for INTs, replace recent-average Edge
with a probability model vs the book's no-vig price; heavily shrink QB
INT rates; center on game script, aggressiveness, and opponent
INT-forcing; ignore weather/venue; recalibrate to the recent league rate;
and the same small-count logic likely applies to TDs.

## "Stat" column in the main table (added 2026-09-25)
Trevor, pointing at the gap between Opp and Avg in a screenshot: "can you
put a column where the arrow is to show the bet that it is? like right
now it doesn't show that first row is INTs." The main table genuinely
had no column naming the prop — you could only tell via the Stat filter
or by opening the player card — so a MUST BET row for Matthew Stafford
INTs looked identical to one for his passing yards. Added a sortable
`Stat` column (`data-key="stat_label"`, bold) right after Opp; it shows
on every row, including collapsed ↳ rows in the grouped-by-player view.
Verified with `verify_statcol.py` against the cloud build and Trevor's
real rebuild: header order Opp → Stat → Avg, every one of the 1,613/1,625
rows has exactly 18 cells matching the 18 headers, every Stat cell holds
a real stat label, sorting by Stat works, zero console errors. Pushed to
the Mac with the new sha256 check (hashes matched), rebuilt there from
Trevor's latest `run.py` data (stats generated 2026-09-25T14:26), and
republished as **Version 24** — the current, correct artifact.

## Artifact republish process bug — self-caught and fixed (2026-09-24)
**What went wrong**: the shareable claude.ai artifact link is kept in
sync by extracting the `<head>`/`<body>` content out of Trevor's own
`dashboard.html` and republishing it via the Artifact tool. The
extraction script's `SRC` path was pointed at
`/mnt/user-data/uploads/Documents/Gambling Program/output/dashboard.html`
— a **one-time snapshot** created the first time that file was ever
staged from Trevor's Mac earlier in the conversation. That snapshot does
**not** auto-update when Trevor's actual file changes; it just sits
there as whatever it was the moment it was staged. Nothing about
re-running the extraction script errors or warns when this happens — it
silently produces a perfectly valid-looking (but stale) output every
time.

Because of this, the artifact publish done for the Weeks filter feature
(reported to Trevor as "Version 9, containing the new Weeks filter") was
actually built from that stale snapshot, which predated the Weeks filter
entirely — confirmed after the fact via `grep -c "weeksToggle\|selectedWeeks"`
on that snapshot returning **0**. **Trevor was told Version 9 contained
the Weeks filter. It did not.**

**How it was caught**: while republishing for the MUST BET feature, the
newly "extracted" file came out suspiciously identical in size to the
pre-MUST-BET build — that discrepancy is what triggered a closer look at
`extract.py`'s `SRC` path rather than just re-running it and trusting the
output.

**How it was fixed** (two attempts, the first also flawed):
1. First fix attempt: pointed `SRC` at the cloud sandbox's own fresh
   build (`/mnt/user-data/outputs/gambling_program/output/dashboard.html`)
   instead. This did contain both the Weeks filter and MUST BET (34
   matches on the relevant strings) and was published as **Version 10**
   — but reading it back showed `vegas_line: null` throughout and no
   real odds data, because the cloud sandbox's own build has no real
   Odds API/weather data (those sources are blocked from the cloud
   sandbox's network entirely — see "Why it's architected this way"
   above). Version 10 is real code but not real Trevor data.
2. Correct fix: re-staged `dashboard.html` **fresh** from Trevor's Mac
   via `device_stage_files`, confirmed the staged copy's `mtimeMs` was
   current, ran the extraction against that newly-staged path, confirmed
   the result had both new features AND real odds data (`vegas_line:
   220.0` etc., fresh `Stats generated` timestamp), and published this as
   **Version 11** — the correct artifact at that point in time.

`extract.py` itself was rewritten with an explicit comment block
documenting the correct 3-step process for every future republish
(rebuild on Trevor's Mac → re-stage fresh, every time, even if staged
earlier in the same conversation → then extract and publish), plus a
reminder at the end of the script's own output to grep the result for
`weeksToggle`, `MUST BET`, and a recent timestamp before publishing —
specifically so this exact mistake (extracting from a stale, silently-
non-updating snapshot) can't recur unnoticed. That same corrected
process was followed again for the fixed-MUST-BET-bar republish
(Version 12), the zero-stat-week-backfill republish (Version 13), the
line-shopping tie-break republish (Version 14), the ladder-badge
republishes (Versions 15-16), the MUST BET consistency-gate republish
(Version 17), the MUST BET threshold-lowering republish (Version 18),
the weak-matchup-filter republish (Version 19), the strong-matchup-filter
republish (Version 20), the DNP-row republish (Version 21), the
Targets-stat republish (Version 22), and the impactful-injury republish
(Version 23, see their own sections above) — rebuild on Mac, re-stage
fresh, extract, sanity-grep, publish — with no repeat of this mistake in
any of them.

**Bottom line for Trevor**: the earlier claim that Version 9 contained
the Weeks filter was wrong — Version 9 was stale and had neither the
Weeks filter nor MUST BET. **Version 26 is the correct, current
artifact** and has been verified, end to end, against Trevor's own real
Mac data.

## Weeks filter, replacing the old Last N games buttons (added 2026-09-24)
Trevor's request, verbatim: "can you make the 'Sample Size' a function
where you can select specific NFL weeks? just have all weeks of the
regular season available for now and you check the boxes you want. And
for what it defaults to, just have it be all weeks up to this current
one."

This replaces the entire "Sample size: Last 2/3/5/10" button row with a
**Weeks** dropdown: click it to open a panel of checkboxes for every
week of the current regular season (1-18); check or uncheck any
combination and Recent Avg, Opp Allows, Opp Rank, Team Share,
Anticipated, both Edge columns, and the game-by-game box scores in both
modals all recompute against exactly those weeks, instantly, since every
week's data is already loaded client-side. Three shortcuts in the panel:
**All**, **None**, and **Up to current** (the default). Defaults to
Week 1 through whichever week is current/upcoming (`WEEK`) on page load.
Like the old Last-N buttons, this selection is **not persisted** — it
resets to the default on every fresh page load or rebuild, unlike the
bet marks (permanent) or the Game filter (self-expiring on a weekly
timer). Wasn't asked to persist it, so it wasn't added, matching this
project's pattern of not building beyond what's asked without flagging
it first.

**A bigger architectural change than it looks like**: the old sample
control ("Last N games") quietly blended in the END of last season for
any player early in a new season, specifically so a small early-season
sample wasn't too thin. Weeks checkboxes only make sense for a single
season — there's no sensible way to "check week 17" and mean either
season — so that blending had to go. Concretely:
- `fetch_stats.py`: `load_weekly_stats([season, season - 1])` →
  `load_weekly_stats([season])`. Player recent-game stats, defense-
  allowed, and team-position-totals are now ALL current-season-only
  (defense-allowed already was). `MAX_GAMES_WINDOW` (the per-player game
  cap) was raised from 10 to 18 (renamed conceptually to
  `REGULAR_SEASON_WEEKS`), since a player can now have up to 17 games in
  a season and nothing should get truncated before Week 18.
- `build_dashboard.py`: new `SEASON`/`TOTAL_WEEKS` JS constants;
  `selectedWeeks` (a `Set` of week numbers) replaces the old `sampleSize`
  number everywhere — `deriveStats()`, `rankDefenses()`, `enrichRow()`,
  `render()`, `openPlayerModal()`, `openDefenseModal()` all rewritten to
  filter a player's/defense's game log down to games whose
  `(season, week)` falls in `selectedWeeks`, via two small helpers
  (`playerSelectedIndices()`, `defenseSelectedIndices()`) instead of the
  old `.slice(0, n)` first-N-games approach. A new `weeksLabel()` helper
  renders the selection compactly everywhere it needs a label (e.g.
  "Wk 1-3", "Wk 1-3, 7, 9-10", "All") instead of "Last N".

**Disclosed trade-off, not asked about directly beforehand**: with the
prior-season blend gone, an early-season selection really is just that
many real games — e.g. at Week 2 with the default (Weeks 1-2) checked,
Recent Avg is genuinely a 2-game average, no cushion from last year
anymore. This is a real, if minor, regression in early-season sample
robustness versus the old behavior — but it's what "pick the weeks you
want" has to mean once weeks, not a game count, are the unit, and it was
Trevor's own explicit design (checkboxes, current season only, "for
now"). Flagged here and in the README rather than silently accepted as a
free change. An empty selection (all boxes unchecked) is handled
gracefully, same as any other zero-games case already in this
codebase — blank cells, no crash, no special-cased code needed.

Verified via headless Playwright against the real production build
(2026 Week 3, 1382 real rows, 414 real players — down from 675 under the
old blended fetch, since players who only appear in last season's data
correctly drop out now): confirmed the default selection is exactly
weeks 1 through the real `WEEK` value (3); confirmed the checkbox grid
has all 18 boxes with the correct ones pre-checked; confirmed the panel
opens on toggle-click and closes on an outside click; confirmed toggling
a single checkbox updates `selectedWeeks`, the toggle-button label, and
triggers a re-render; confirmed **All**/**None**/**Up to current** each
produce the correct set; unit-tested `weeksLabel()` directly against a
contiguous range, a single week, a discontiguous set, the full set, and
an empty set, all formatting correctly; confirmed `playerSelectedIndices()`
picks exactly the right index for a real player's game log filtered to
one specific week; confirmed `deriveStats()` on an empty week-set returns
null/zero rather than crashing; confirmed the player modal's meta line
and game-by-game row count match the selected weeks exactly, and same
for the defense modal. Zero JS console errors throughout. Pushed to
Trevor's Mac, `fetch_stats.py` and `build_dashboard.py` both rebuilt
there with his own fresh nflverse pull (same 414 players / 1382 rows as
the cloud sandbox's run, confirming the two environments agree). **See
the "Artifact republish process bug" section above: the republish done
at the time (reported as Version 9) was actually stale and did not
contain this feature — it only genuinely reached the shared artifact
link as of Version 11, and is confirmed still present as of Version
17.**

## Game filter, with a Tuesday-morning auto-reset (added 2026-09-24)
Trevor's request: "can you make a filter so i can choose to select by
game if i want to? make it be like reset on tuesday after the monday
night game is complete each week."

Two distinct pieces: a way to narrow the table to one specific matchup,
and — the more interesting design problem — making that choice
self-expiring rather than a permanent setting like the bet marks
(above), since a game filter left on from last Sunday would otherwise
silently hide most of the table the next time Trevor opens the
dashboard for a new week.

**Where the schedule data came from**: `fetch_stats.py` was already
pulling the full week's schedule (`schedule_this_week` in
`stats_cache.json` — gameday, gametime, home/away team, stadium, roof)
to know which games to fetch weather/odds for, but nothing threaded it
through to the dashboard itself. New `build_games_list(stats)` in
`build_dashboard.py` turns that into a clean list of this week's actual
games — `{key: "AWAY@HOME", away, home, gameday, gametime}` — sorted by
kickoff (Thursday night first, Monday night last), passed to the page as
a new `GAMES` JS constant. No new fetch needed; this data already
existed one step upstream.

**Joining a row to a game with no new per-row field**: a row already
carries `team`/`opponent`/`at_opponent` (used for the existing "@Opp"
display). `gameKey(r)` in the JS builds the identical `AWAY@HOME` string
from those three fields (`r.at_opponent ? r.team+'@'+r.opponent :
r.opponent+'@'+r.team`), so every row's own game matches a `GAMES` entry
with zero extra data threaded through `build_rows()`. Verified this
holds for all 2346 real rows with zero mismatches (see verification
below).

**UI**: a `<select id="gameFilter">` dropdown next to the Position
buttons, populated client-side from `GAMES` at page load (not
server-rendered `<option>` tags — keeps all the date/time formatting
logic in one place, JS, which also needs it for the reset logic below).
Labels read like "Thu 9/24 8:15p ATL @ GB" — `formatGameLabel()` parses
the plain `gameday`/`gametime` strings as a LOCAL calendar date rather
than through `Date.parse()` (which would treat a bare `YYYY-MM-DD` as
UTC midnight and can print the wrong weekday depending on the browser's
own timezone — a real bug class avoided here, not a hypothetical one).
Wired into the same `.filter()` chain as Position/Stat/Hide-❌ in
`render()`, so it composes with every other filter and search
identically.

**The Tuesday-reset design problem**: Trevor's own bet marks (see their
own section above) are deliberately PERMANENT within a week and survive
any number of re-syncs — that's the opposite of what he wants here. A
game filter is a "just show me this one game right now" convenience; if
it silently carried over week to week, he could open the dashboard on a
Thursday, see almost no rows, and not immediately realize it's because
last week's game filter is still selected. So this needed its own,
separate piece of `localStorage` state (`nfl_prop_dashboard_game_filter_v1`)
with its own expiry rule, not a re-use of the `WEEK`-keyed pattern the
marks use.

**Implementation**: rather than tie the reset to the `WEEK` value baked
into the file (which only changes when Trevor actually re-runs
`python3 run.py` for a new week — meaning a stale filter would still
show on an OLD, not-yet-rebuilt `dashboard.html` reopened after a new
week has already started), the reset is purely calendar-based, off the
browser's own clock: `currentResetMarker()` computes the most recent
Tuesday at 3am (walking back from "now" by `(today's weekday - Tuesday +
7) % 7` days, with an extra wrinkle: if today IS Tuesday but it's still
before 3am, it counts as still belonging to the PREVIOUS week's cycle,
not this one — i.e. a very early Tuesday morning still protects a filter
set the day before, in case that Monday night's game ran unusually
late). Saved state is `{game, resetMarker}`; on load, if the stored
`resetMarker` doesn't exactly match `currentResetMarker()` right now,
the saved selection is discarded and the dropdown starts at "All Games."
A saved game that isn't among the CURRENT week's `GAMES` (e.g. something
went stale in an unexpected way) also falls back to "All Games" as a
second safety net, same defensive pattern used for the bet-marks
localStorage read.

**3am, not midnight, is Claude's own reasonable-looking buffer past a
late Monday Night Football final** — same "flagged as an arbitrary
pick, not an official league cutoff" caveat as every other constant in
this project (the 15%/25%/40% edge tiers, the bad-weather thresholds,
the -130 price gate, the 65%/90% coverage tiers). Easy to move
(`marker.setHours(3, 0, 0, 0)` in `currentResetMarker()`) if 3am isn't
the right buffer.

Verified via headless Playwright against the real production build (16
real games, 2346 rows): confirmed `GAMES` has exactly 16 entries sorted
chronologically and the dropdown has 17 options (16 games + "All
Games"); confirmed every one of the 2346 real rows' `gameKey(r)` matches
a real `GAMES` entry with zero mismatches; selected the week's first
game (ATL@GB) through the actual `<select>` element and confirmed the
table correctly narrowed to exactly 153 rows, both of them ATL/GB (no
other team leaked through); reloaded the page and confirmed the
selection survived (both the JS state and the visible dropdown value);
reset to "All Games" and confirmed the full 2346 rows came back;
seeded `localStorage` directly with a 10-day-old `resetMarker` and
confirmed `loadGameFilter()` correctly discarded it and returned "All
Games" (the staleness case); seeded it with a marker matching
`currentResetMarker()` right now and confirmed that ONE was correctly
honored (the freshness case); confirmed `currentResetMarker()` always
resolves to a Tuesday (`getDay() === 2`) at 3am on the real test day
(Thursday 9/24 → correctly walked back to Tuesday 9/22); reasoned
through (rather than mocked, since mocking `Date` inside the page
wasn't straightforward) all seven weekday branches of the walk-back
arithmetic by hand, including the Tuesday-before-3am edge case, and
confirmed each lands on the intended day. Zero JS console errors.
Pushed to Trevor's Mac, rebuilt there with his own real schedule data,
and republished to the shared artifact link (Version 8).

## 🛡️ O-line concern badge (added 2026-09-24 — REPLACED 2026-09-25)
**Superseded**: this badge only ever showed for Green Bay in practice
(it read game designations only), and was replaced by the 🩹 impactful-
injury badges — see that section above. Kept here for history.

Trevor's request, given directly as a follow-up to the ⛑️ injury badge
below (see "i don't see a change" in that section): "okay i do see that
now, but i was thinking it could be something like, the packers
offensive line has two players hurt now, show that as an injury badge by
jordan love cause that would impact him as a qb."

This is a genuinely different signal from the ⛑️ badge: ⛑️ says
*this specific player* has an injury designation; 🛡️ says *this
player's own offensive line* does, even when he himself is fully
healthy — worth surfacing separately because a QB's (and, by the same
logic, an RB's) performance depends heavily on his blockers regardless of
his own health.

**Scope decision (disclosed, not asked)**: limited to O-line positions
(tackle/guard/center) specifically, and to QB/RB rows only, rather than
"any teammate is hurt." A hurt skill-position teammate (a WR or another
RB out) cuts the *opposite* way — it usually means MORE opportunity for
whoever's left, not less — so folding that into the same badge would
conflate two signals that point in different directions. That's flagged
here as a separate, not-yet-built idea rather than something this badge
tries to cover.

**Implementation**:
- `fetch_injuries.py` now also builds a second, team-level structure
  alongside its existing per-player `players` dict: `oline_by_team`, keyed
  by team abbreviation, listing every T/G/C with a designation this week
  (`name`, `position`, `status`, `primary_injury`), sorted worst-status-first
  via a small `STATUS_SEVERITY` map (`Out` > `Doubtful` > `Questionable`)
  so a team's list can show its single most severe concern first with no
  extra sorting logic downstream. Both structures are written into the
  same `data/injuries_cache.json` (`{"players": {...}, "oline_by_team":
  {...}}`) from one pass over the same CSV — no second network fetch.
- `build_dashboard.py`: `load_caches()` now returns `oline_by_team`
  alongside everything else; `build_rows()` attaches
  `team_oline_injury = oline_by_team.get(info["team"])` to a row **only**
  when `pos in ("QB", "RB")` — the position gate lives here, server-side,
  so it can't accidentally leak onto a WR/TE/defense row.
- JS: new `oLineTag(r)` renders a 🛡️ badge next to the player's name
  (main table) using the same red/amber (`injury-out`/`cov-lowman`)
  severity classes already established for the ⛑️ badge, with a hover
  tooltip listing every affected lineman, their body part, and status.
  Also wired into the player detail modal's meta line, matching the same
  pattern used for the ⛑️ detail there. Uses code point `&#128737;`
  (U+1F6E1, confirmed via `ord('🛡')` in Python before use — same
  emoji-verification discipline as the ⛑️ badge below, after that one's
  code-point bug).

Verified via headless Playwright against real, live 2026 Week 3 data
(fetched fresh — Trevor's own example matched exactly: Green Bay had two
O-line players designated, Aaron Banks (G) and Zach Bako-Bewele (T), both
listed Out with a Knee injury as of this fetch): confirmed `ROWS` carries
the correct `team_oline_injury` array on Jordan Love's (GB QB) row;
confirmed the actual rendered DOM (not just the source string) shows the
correct 🛡️ character (`U+1F6E1 U+FE0F`, no encoding bug) next to his
name in the main table, with a tooltip listing both linemen; confirmed
the player detail modal's meta line shows the same detail; confirmed the
same badge and data correctly also appears on Josh Jacobs (GB RB), since
the position gate is team-based, not player-based; confirmed exactly
zero non-QB/RB Green Bay players (40 rows checked) received the badge,
proving the `pos in ("QB", "RB")` gate holds. Zero JS console errors.
Pushed to Trevor's Mac, rebuilt there with his own fresh `python3
fetch_injuries.py` / `build_dashboard.py` run, and republished to the
shared artifact link (Version 7).

## ⛑️ injury badge (added 2026-09-24)
Trevor's request: "are there any news sources that you could site relevant
player injuries? as a ⛑️ emoji and then if i click in, it'll show me
relevant recent injury news?"

**Research done before building anything** (per the established pattern
on this project): searched for free NFL injury data/news sources.
Multiple paid scraper-as-a-service products exist (Apify listings for
"ESPN Injury Report" scrapers, etc.), confirming there's real commercial
demand for this but no clean official API most people use directly.
ESPN's own undocumented API has a per-team injuries endpoint
(`sports.core.api.espn.com/v2/.../teams/{id}/injuries`) but with no
confirmed pregame Out/Doubtful/Questionable designation, per public
developer discussion. The winning find: **nflverse itself publishes the
NFL's own official weekly injury report** as a dedicated dataset
(`nflreadr::load_injuries()` / the `injuries` release tag on
nflverse-data), with real per-player rows: `report_status`
(Questionable/Doubtful/Out), `report_primary_injury`/
`report_secondary_injury` (body part), `practice_status`, team, week,
and `gsis_id` — the exact same stable player ID already used as the key
in `stats_cache.json["players"]` (confirmed directly: both datasets use
identical "00-00XXXXX" IDs for the same players), so it joins with zero
fuzzy name-matching, unlike the Odds API side. Confirmed live by
downloading `injuries_2026.csv` directly in the cloud sandbox — real
2026 Week 3 rows came back (e.g. Garrett Williams, ARI CB, "Achilles" /
"Out"), and it's hosted the exact same way as `stats_player_week_2026.csv`
(a `nflverse-data` GitHub release asset), meaning it's fetchable directly
from Claude's own cloud sandbox, no need for Trevor's Terminal at all —
the best-behaved data source in the whole project, even better than the
stats/odds/weather/coverage precedent.

**What this is NOT**: narrative injury news (headlines, articles, "X
tweaked his hamstring at Wednesday's practice and is considered
week-to-week" style commentary). No free source was found for that — it
would mean scraping a second, less official page (e.g. an ESPN player
news feed), carrying the same "could break if the page changes" risk
already flagged for the man/zone coverage scrape. Given this, Trevor was
asked how he wanted to proceed (same pattern as the coverage-scheme
decision) and chose **the official report only** — reliable, free, no
extra setup — over adding a second, shakier scrape for narrative color.

**Implementation**:
- `fetch_injuries.py` (new) downloads
  `nflverse-data/releases/download/injuries/injuries_{season}.csv`,
  reads season/week from the existing `stats_cache.json` (so it always
  matches whatever week the dashboard is showing, no separate
  season/week logic duplicated), filters to `game_type == "REG"` and the
  current week, and keeps only players with a non-blank `report_status`
  (most players have none — a blank status means no report, not
  "confirmed healthy"). Writes `data/injuries_cache.json`:
  `{"players": {gsis_id: {status, primary_injury, secondary_injury,
  practice_status, team}}}`. (Now also writes `oline_by_team` in the same
  file — see the 🛡️ section above.)
- `build_dashboard.py`'s `load_caches()` loads it (empty dict if the file
  doesn't exist yet, same graceful-default pattern as coverage/weather).
  `build_rows()` attaches `injury = injuries.get(player_id)` to each row
  using the loop's existing `player_id` — no new lookup structure needed
  since the join key was already in scope.
- `run.py`: new `fetch_injuries.py` step (via `run_optional()`, same
  fail-safe treatment as coverage, even though this source is
  structurally more reliable — better safe than blocking the whole
  pipeline on a data source outside Claude's control) right after
  `fetch_stats.py`; new `--skip-injuries` flag for symmetry with the
  other skip flags.
- JS: `injuryTag(r)` renders a small ⛯️→⛑️ badge (see bug fixed in
  passing, below) next to the player's name in the main table — red
  (`injury-out`) for Out/Doubtful, amber (`cov-lowman`, reused from the
  coverage-tag palette) for Questionable — with the full detail (status,
  body part, practice status) in its hover tooltip. It's a heads-up
  badge, not its own separate click target: clicking the player still
  opens their existing detail-card modal (unchanged row-click behavior),
  which now also shows the same detail as a colored line in the modal's
  meta header. Blanked out in the "grouped by player" collapsed view
  (`sameAsPrev`) same as the player name itself, so it never appears
  detached from a name.
- **Bug caught before shipping**: first implementation used the wrong
  Unicode code point (`&#9967;` / U+26EF, a different, unrelated
  symbol) instead of the actual ⛑️ helmet-with-cross emoji (`&#9937;` /
  U+26D1) Trevor asked for — caught by actually rendering the page in
  Playwright and reading the real DOM text content rather than just
  checking the HTML-entity source string, which would have missed it
  (the entity looked plausible on paper; only the rendered character was
  wrong). Fixed and re-verified against the live DOM.

Verified via headless Playwright against real, live 2026 Week 3 data
(fetched fresh in the cloud sandbox, 8 players with a designation
league-wide as of that day, 4 of them making it into `ROWS` after the
usual position/relevance filters — e.g. Jayden Reed, GB WR, "Out (Neck)
-- Did Not Participate In Practice"): confirmed the real rendered DOM
badge shows the correct helmet emoji (not just the source entity),
confirmed its tooltip reads the full status/body-part/practice-status
string, confirmed the player modal's meta line shows the same detail
with red styling for "Out," confirmed a synthetic "Questionable" row
correctly gets the amber class instead, and confirmed a player with no
injury entry gets an empty string back from `injuryTag()` (no badge, no
console error). Zero JS console errors across the full 2346-row
production render. Verified against Trevor's own Mac-fetched data
(rebuilt there via `python3 fetch_injuries.py` / `build_dashboard.py`,
same code path) and republished to the shared artifact link.

## 🪜 Ladder badge: has this player ever blown past their current line? (added 2026-09-24)
Trevor asked about ladder bets (sportsbook markets that price several
ascending thresholds for the same stat, each its own line/price) and
whether this dashboard could flag a ladder opportunity. Investigated
whether the data actually supports it first: The Odds API does have
"alternate" market variants for nearly every stat this dashboard already
tracks (`player_reception_yds_alternate`, `player_rush_yds_alternate`,
`player_pass_yds_alternate`, etc.), confirmed via their own market-list
documentation, so a real, fully-priced ladder feature (fetch every
rung's price, compute real hit rate vs. each rung's implied probability,
flag whichever rung has the best expected value) would be buildable --
but it would need a new fetch step, more Odds API quota per event (each
alternate market returns more outcomes than the single-line markets
already pulled), and introduces this dashboard's first true
probability/EV math, distinct from the existing edge-percentage system.

Trevor asked for something much simpler instead: "is there a way to
think of it simpler? maybe like if a player has gone like over the
yardage that their line is by like double or something like that at
some point during the year?" That reframes it from a priced-ladder
question into a pure ceiling question, and -- the reason this shipped
same-day instead of needing a new data pipeline -- it needs **zero new
data**. Every row already carries `game_log` (real per-game values for
the whole season) and `vegas_line` (the current posted line), which is
exactly what this simpler version needs.

**Logic**: for a player+stat, find the single best game in their FULL
season `game_log` (not just the currently-selected Weeks -- this is a
"has this ever happened" question about their ceiling, not a
recent-form one, so it deliberately ignores the Weeks filter) and
compare it to the CURRENT `vegas_line` (the flat consensus line, not a
specific book's shopped side, since "their line" reads as the one
number currently posted). If that best game was at least 2x the current
line, show a 🪜 badge next to the player's name in the main table, in
the same spot/style as the ⛑️ and 🛡️ badges, with a tooltip naming
the specific week/opponent and the exact ratio.

**Scope, per Trevor's exact list**: QB Pass Yds, QB Rush Yds, RB Rush
Yds, RB Rec Yds, WR Rec Yds, TE Rec Yds -- `LADDER_STATS` in
`build_dashboard.py` maps each position to just its allowed `stat_col`
values, and any row outside that combination returns no badge, full
stop. This was deliberately left out for low-count stats (TDs, INTs)
in the design discussion before Trevor asked to build it: those lines
are often 0.5, where "2x" is just 1 and nearly every player who scores
at all trivially clears it, which would make the badge meaningless
there. `LADDER_MULTIPLIER = 2` is a `const`, Claude's own reading of
"double or something," flagged as easy to retune like every other
arbitrary constant on this page.

**A real limitation even within the scoped stats, disclosed rather than
silently patched**: a QB's Rush Yds line is often very small (e.g. 0.5),
so a single 5-yard scramble can technically read as "10x the line" --
correct math, but not really a meaningful "proven ceiling" the way
Dalton Schultz's 140 real yards against a 50.5 line is. Trevor didn't
ask for a minimum-line floor to filter this out at the time (see the
follow-up section immediately below, where he did ask for exactly that
once he saw the real 44-hit list).

**Another disclosed quirk**: the badge is per-STAT, not per-player, but
the player-name cell it lives in only shows once per player when the
table is sorted by the Player column (grouped view) -- in that view, if
the first-shown stat row for a player isn't one of the ladder-eligible
stats, the badge won't show even if a different stat row for that same
player would qualify. Under the table's default sort (by signal
strength), this doesn't come up -- every stat row shows its own name and
its own badges independently, so the ladder badge appears exactly on the
rows it should.

Verified via headless Playwright:
- Unit-tested `ladderInfo()` against nine synthetic cases: a game at
  exactly 2x the line (flags), a game just under 2x (does not flag), an
  out-of-scope stat for an otherwise-eligible position (does not flag
  even at 5x), an out-of-scope position/stat combination (does not
  flag), in-scope hits for QB Pass Yds, RB Rush Yds, and TE Rec Yds (all
  flag correctly with the right week/opponent attached), a row with no
  posted line yet (returns null, no crash), and an all-negative game log
  such as a QB with only kneel-downs recorded (returns null, no crash --
  a negative "best game" isn't a ceiling).
- Confirmed the actual rendered DOM character for an injected hit is the
  correct 🪜 glyph (`U+1FA9C`, verified against Python's own `ord()`
  first, learning from the ⛑️ codepoint mistake earlier in this
  project) with the right tooltip text, not just a plausible-looking
  HTML entity in the source.
- Ran `ladderInfo()` over the full real production table (rebuilt on
  Trevor's own Mac, 1370 rows, real odds) and found **44 real hits**
  across the six eligible stat/position combinations, spanning ratios
  from 2.0x to 10x (that last one being the thin QB Rush Yds case flagged
  above) -- e.g. Dalton Schultz's real 140-yard game against his current
  50.5 Rec Yds line (2.77x), Jonnu Smith's 50 yards against an 8.5 line
  (5.9x), and Aaron Rodgers' 5-yard scramble against his 0.5 Rush Yds
  line (10x, the thin case). Confirmed the badge renders correctly in
  the DOM for a real hit, not just a synthetic one. Zero JS console
  errors across the full render.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data (same 1370 rows, 44 real ladder hits), re-staged fresh, and
republished to the shared artifact link as **Version 15** (later
superseded by Version 16 once the two follow-ups below were added).

## 🪜 Ladder badge follow-up: 30-yard minimum line + a "Ladder only" filter (same day, 2026-09-24)
Immediately after seeing the real 44-hit list, Trevor caught exactly the
thin-case risk flagged when the badge shipped: "let's adjust. let's make
sure the minimum amount of the stat is 30 yards. also, let's add a
filter at the top so i can filter on ladder bets."

**Minimum line floor**: `ladderInfo()` now requires `r.vegas_line >= 30`
before it even computes a ratio -- previously it only required the line
to be positive, which is exactly what let Aaron Rodgers' 0.5 QB Rush Yds
line produce a technically-correct-but-meaningless "10x" read off a
single 5-yard scramble. `MIN_LADDER_LINE = 30` is a new constant
alongside `LADDER_MULTIPLIER`, flagged the same way as every other
arbitrary threshold on this page. This is a real quality improvement,
not just a cosmetic one: on Trevor's real data, real ladder hits dropped
from 44 to **12**, and every remaining hit is a genuinely meaningful
yardage outlier (Dalton Schultz 140 vs. a 50.5 line, Jonnu Smith-style
big games against real double-digit-plus lines, etc.) rather than a
trivial multiple of a near-zero number.

**"Ladder only" filter**: a new checkbox next to "Hide ❌ rows" in the
controls bar -- `ladderOnly` (a `let`, same pattern as `hideMarkedX`) --
wired into the exact same `.filter()` chain in `render()` that already
handles Position/Stat/Game/Hide-❌/search, so it composes cleanly with
every other filter rather than needing special-case logic. Checking it
narrows the table to only rows where `ladderInfo(r) !== null` -- i.e.
exactly the rows carrying a 🪜 badge.

Verified via headless Playwright:
- Unit-tested the new floor directly: a line of exactly 30 still flags
  (the boundary is inclusive), a line of 29 does not, the old
  thin-line case is now correctly excluded, and a real-shaped case well
  above the floor still works exactly as before.
- Ran the floor against the full real production table (Trevor's own
  Mac data): confirmed real hits dropped from 44 to 12, confirmed zero
  of the 12 remaining hits have a line under 30, and confirmed Aaron
  Rodgers' Rush Yds row no longer flags.
- Drove the actual `#ladderOnlyFilter` checkbox (not just calling
  `ladderInfo()` directly) against the real production table and
  confirmed the rendered table narrows to exactly those 12 rows, and
  that every visible row's DOM actually carries a `.ladder-tag` badge.
- Zero JS console errors throughout, both the synthetic unit tests and
  the full real-data render.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data (confirmed 44 → 12 real hits, matching the cloud sandbox's own
rebuild), re-staged fresh, and republished to the shared artifact link
as **Version 16** (later superseded by Version 17 once the MUST BET
consistency gate was added, then Version 18 once the threshold was also
lowered — see their own sections above).

## Line-shopping tie-break fixed: ties now go to the better price, not book order (follow-up, 2026-09-24)
Trevor caught this directly, looking at a real Aaron Rodgers Rush Yds
row on the dashboard: DraftKings showed 0.5 at -116 and was highlighted
green as the "most advantageous" book, while FanDuel showed the same 0.5
line at -110. His question: "in this example, wouldn't the -110 be the
better bet?"

Trevor was right, and it exposed a real gap in the "Line shopping"
feature just below: `pickBestLine()` only ever compared LINES (lowest
number for an Over, highest for an Under) to decide which book to
highlight. When two books post the exact same line -- as DraftKings and
FanDuel did here, both at 0.5 -- there was nothing to break the tie
except a hardcoded book-list order (DraftKings, FanDuel, BetMGM), which
meant DraftKings always won a tie regardless of price. In this row,
FanDuel's -110 is a genuinely better price than DraftKings' -116 for the
identical 0.5 line -- less risked for the same payout -- so the green
highlight was on the wrong book.

**The fix, and a bigger latent bug it uncovered**: while implementing
the price tie-break, tracing where per-book prices actually come from
surfaced a second, related bug. `book_line()` in `build_dashboard.py`
was only ever keeping ONE price per book (it "preferred" the Over/Yes
side entry), even though the raw Odds API data has a separate price for
both Over and Under at every book. That meant:
(1) there was no Under-side price available per book at all, so a price
tie-break for an UNDER bet couldn't be done correctly even if attempted;
and (2) the existing 🧊 price gate -- which checks whether an Under
bet's price is too steep to recommend -- was silently checking that
book's OVER price instead of its Under price whenever a specific book
was pinned as the shopped line. That's a real, independent correctness
bug, not something Trevor flagged directly, but it came from the exact
same root cause (only one price ever kept per book) as the issue he did
catch, so it was fixed at the same time rather than left in place.

**Implementation**: `book_line()` now returns both `over_price` and
`under_price` for a book, not one preferred price. Every row now carries
`draftkings_over_price`/`draftkings_under_price` (and the same for
fanduel/betmgm) instead of a single `draftkings_price`. `pickBestLine()`
now takes the direction-appropriate price field into account: when two
or more books tie on the best line, the tie is broken by price, using
the Over price for an Over tie and the Under price for an Under tie. The
rule for "better price": **in American odds, a higher raw number is
always better for the bettor, whether negative or positive** -- -110
beats -116, +150 beats +120, and any positive number beats any negative
one -- so a plain numeric comparison works with no odds-format
conversion needed. A book missing a price for that side loses the tie
to one that has it; if neither has a price, the original book-order
fallback still applies. The same fix also corrected the 🧊 price gate
(`enrichRow()`), which now reads the Over or Under price to match
whichever side is actually being gated, instead of always reading
whatever single price used to be stored. The DK/FD/BetMGM column
display was updated the same way (a new `bookCellPrice()` helper) so the
price shown for each book now matches the side the row actually favors
(`derived.direction`) rather than always showing the Over price
regardless of lean -- previously an Under-leaning row displayed that
book's Over price in these columns, which didn't match the number
actually used for Edge or the price gate.

Verified via headless Playwright:
- Unit-tested `pickBestLine()` directly against five synthetic cases: the
  exact Rodgers scenario (DK 0.5/-116 vs FD 0.5/-110) now correctly picks
  FanDuel; the mirror case for an Under tie correctly compares Under
  prices, not Over prices; a tie between a negative price and a positive
  price (-105 vs +150) correctly picks the positive one; a non-tied case
  confirmed the LINE still wins outright regardless of price (unchanged
  behavior when there's no tie to break); and a tie where one book is
  missing a price entirely correctly goes to the book that has one.
- Injected a row shaped exactly like the real Rodgers example into a live
  page and ran it through the real `enrichRow()` -- confirmed it now
  resolves to `best_book: 'fanduel'`, matching Trevor's own read of the
  situation.
- Rendered the full real production table from Trevor's own Mac data
  (1370 rows) and found the ACTUAL Rodgers Rush Yds row from his
  screenshot in it: DraftKings 0.5/-116 vs FanDuel 0.5/-110, direction
  "over" -- confirms `best_book` now resolves to FanDuel on his real
  data, not just in a synthetic test. Also spot-checked his real Pass TDs
  row (an Under lean) and confirmed the Under-side tie-break correctly
  compared Under prices (FanDuel's -220 correctly beat DraftKings'
  -222).
- Confirmed zero JS console errors and an unchanged row count (1370) on
  the full rebuild, both in the cloud sandbox and on Trevor's Mac.

Pushed to Trevor's Mac (`build_dashboard.py`), rebuilt there with his own
real data, re-staged fresh, and republished to the shared artifact link
as **Version 14** (later superseded by Version 18 once the ladder badge,
the MUST BET consistency gate, and the lowered MUST BET threshold were
all also added).

## Line shopping: Edge / Anc. Edge graded against the best available book (added 2026-09-24)
Trevor's request: "can you do it versus the most advantageous line and
then highlight that line? meaning like if you're looking at over pass
yards, you'd want to do the math on the lowest line. know what i mean?"

Edge and Anc. Edge were previously both graded against one flat
consensus number (the median of DraftKings/FanDuel/BetMGM's individual
lines) — so a row could show, say, a middling edge even when one
specific book was actually offering a much friendlier number to bet
into, with no way to tell which book that was without checking all three
columns by eye.

**Rule implemented**: once Recent Avg establishes which side of the
consensus line looks good (`recentAvg > vegas_line` → Over,
`recentAvg < vegas_line` → Under), the dashboard re-grades BOTH Edge and
Anc. Edge against whichever actual book posted the most favorable number
for that side — the lowest of DK/FD/BetMGM's lines for an Over (least
you need to clear), the highest for an Under (most cushion) — rather
than the flat consensus. Only books that actually posted a line for that
player/stat are considered; a book with no line for this market is
skipped, not treated as a bad option. A dead-even tie against the
consensus (no side to shop for) or a stat with no per-book lines at all
falls back to the old flat-consensus behavior exactly as before, so nothing
regresses for markets without full book coverage.

**Anc. Edge deliberately reuses Edge's own chosen line/book, not its own
independent shop.** Edge and Anc. Edge are two different ways of sizing
up the SAME candidate bet (recent form vs. matchup projection) — they
should be measured against the one number you'd actually get at the
book, not against two different numbers that happen to both look
favorable in isolation. This was a design call, not explicitly specified
by Trevor, and is flagged here as an assumption.

**Price gate updated to match**: 🔥/🧊's price check (see the price-gate
section above) now looks at the specific highlighted book's own Over/
Under price, not the blended consensus price, since that's the number
you'd actually be betting into. Falls back to the consensus price when
no single book was pinned (same fallback cases as above). This resolves
the limitation noted below about the gate only ever checking the
consensus price.

**UI**: whichever of the DraftKings/FanDuel/BetMGM columns matches the
chosen book gets a green highlight (background tint + border) with a
tooltip reading "Most advantageous line for this bet," in both the main
table and the player detail modal. The Edge/Anc. Edge column headers'
tooltips were updated to explain the shopping logic instead of
describing a flat consensus comparison.

Verified via headless Playwright: unit-tested `deriveStats()` directly
against four synthetic scenarios — a clear Over lean (recentAvg 280 vs.
consensus 270, book lines 272/268/275) correctly picked FanDuel's 268
(the lowest) and computed edge 280−268=12; a clear Under lean (recentAvg
60 vs. consensus 75, book lines 73/77/70) correctly picked FanDuel's 77
(the highest) and computed edge 60−77=−17; an exact tie against
consensus correctly fell back to the flat consensus line with no book
pinned; a row with a consensus line but no per-book lines at all also
correctly fell back gracefully. Also verified via `enrichRow()` that
Anc. Edge reuses Edge's exact chosen line (a case with anticipated=280
and Edge's shopped line of 268 correctly produced anc_edge = 280−268=12,
not 280 minus the flat consensus), and that the price gate now checks
the pinned book's own price — a case with a steep FanDuel price (−300)
correctly suppressed a would-be 🔥 signal that the old consensus price
(−108) would NOT have suppressed. Rendered the change against the full
production table (2346 rows, no odds fetchable in the cloud sandbox) to
confirm zero JS console errors, then injected one synthetic row with a
clear Over lean directly into the DOM and confirmed exactly one book
cell (FanDuel, "85 (-115)") received the `.best-line` highlight class
and tooltip. Live odds data with genuinely differing book lines isn't
reachable from this sandbox, so seeing real highlighted rows (rather
than synthetic ones) needed Trevor's own `python3 run.py`.

## LV Pass TDs discrepancy investigated (2026-09-23) — stale data, not a bug
Trevor flagged that the dashboard showed LV allowing 1.5 Pass TDs/game
to QBs, but the defense detail modal's own game log for LV (Wk2 vs LAC,
Wk1 vs MIA) didn't seem to support that number. Traced the math: at any
sample-size window, LV's real per-game passing-TDs-allowed log can only
average to values reachable from whatever two numbers are actually in
`DEFENSE_LOGS['QB|passing_tds']['LV']` — a fresh nflverse pull done in
the cloud sandbox that same day showed `[1.0, 0.0]` (Wk2 vs LAC = 1,
Wk1 vs MIA = 0), which produces 1.0 at a 1-game window or 0.5 at a
2-game window — never 1.5 under the current code, confirmed directly via
Playwright against the real `rankDefenses()`/`enrichRow()` functions.
1.5 is exactly what `(3+0)/2` would produce, which points to Wk2's
originally-fetched stat line for LV likely having read 3 (not the
now-correct 1) at the time Trevor ran `python3 run.py` the evening
before — early-week nflverse box scores are sometimes revised a day or
two after a game as stat corrections land, which is normal/expected
behavior for a live public stats source, not a defect in this project's
own aggregation logic (`compute_defense_allowed()` in `fetch_stats.py`
groups strictly by `(opponent_team, season, week)` and sums correctly,
per direct code review). Not fully confirmed with archived old data
(nflverse doesn't expose prior snapshots), so this is Claude's best
explanation grounded in the numbers rather than a proven root cause;
told to Trevor as such, along with a request to compare against a fresh
`python3 run.py` run to see if it self-resolved (it did — a fresh Mac
run that evening showed real odds and no further report of the
discrepancy).

## Stat categories per position (as of 2026-09-22)
`STAT_MARKET_MAP` in `build_dashboard.py`:
- **QB**: Pass Yds, Pass TDs, INTs, Rush Yds, TDs, Completions, Attempts.
- **RB**: Rush Yds, Rush Attempts, Rec Yds, Receptions, TDs, Air Yards.
- **WR / TE**: Rec Yds, Receptions, TDs, Air Yards.

Rush Attempts and the corrected TDs definition were added 2026-09-22
after Trevor asked what other prop categories were available (see TDs
section below). Air Yards (RB/WR/TE, same day) was added after a
follow-up question — see its own section below. Kicker props (Field
Goals Made, Kicking Points, PATs) and defensive-player props (Sacks,
Solo Tackles, Tackles+Assists, Defensive INTs) were surveyed and
documented as available but NOT built — they'd need a different
architecture since the "opponent allows to this position" framework
(built for offensive skill positions) doesn't map cleanly onto a
defensive player's own accumulated stats. Not requested; flagged for if
Trevor wants them later.

### TDs = Anytime-TD-Scorer (corrected 2026-09-22)
Originally built as separate "Rush TDs"/"Rec TDs" categories, which
Trevor corrected: real "Anytime TD Scorer" prop logic is ONE combined
stat — any TD the player scores himself, by rush or catch, added
together. A QB's thrown touchdowns don't count (that's the separate Pass
TDs stat). Implementation: `fetch_stats.py` computes a derived column
`total_tds = rushing_tds + receiving_tds` once, right after loading
weekly stats, which then flows automatically through the existing
per-position stat pipeline (recent averages, defense-allowed, team
totals) since those all generically iterate whatever's in
`POSITION_STATS[pos]`. Odds API market key: `player_tds`. Verified
against raw `stats_cache.json` per-game values for a real player (Ashton
Jeanty: 0, 2, 0, 0, 2 TDs over last 5 games → avg 0.8, matching the
dashboard exactly).

### Air Yards — a context stat with no betting line (added 2026-09-22)
Trevor asked "does the stats database contain a stat for air yards?" —
confirmed yes (see Data sources above) — then asked to add it to the
player popup for RB/WR/TE so he can compare it across players.
`receiving_air_yards` (how far downfield the ball traveled in the air on
throws to that player, summed for the game) was added to
`POSITION_STATS` for RB/WR/TE only (not QB — `passing_air_yards` exists
too but wasn't requested) and to `STAT_MARKET_MAP` with **market key
`None`**, since The Odds API has no player-prop market for air yards at
all.
- A `None` market key turns out to need zero special-casing:
  `player_odds.get(market_key)` in `build_rows()` just returns `None`
  for any key it doesn't recognize (`None` included), so the line/books/
  DK/FD/BetMGM columns come out exactly like any other stat before its
  sportsbook line gets posted — already an existing, already-handled UI
  state.
- Recent Avg, Opp Allows, Opp Rank, and Team Share all work normally for
  it since those come from `build_rows()`/`enrichRow()` iterating
  whatever's in `POSITION_STATS[pos]`/`STAT_MARKET_MAP[pos]` generically
  — no stat-specific code needed beyond adding the two entries.
  Edge/Anc. Edge/🔥/🧊 stay permanently blank for it since there's no
  line to compare against.
- Shows up both as a normal row/Stat-filter button in the main table AND
  automatically in the player modal (which already lists every stat in
  `STAT_MARKET_MAP[pos]` for the clicked player) — no separate "info
  panel" needed.
- Verified via headless Playwright: Adam Thielen's (WR) Air Yards row at
  Last 5 showed Recent Avg 34.8, matching a hand-calculated average of
  his raw per-game values (16, 67, 50, 36, 5) from `stats_cache.json`
  exactly; confirmed Edge/Anc. Edge/book columns are blank for it;
  confirmed it does NOT appear in a QB's modal (Jordan Love).

## Team Share / Anticipated (added 2026-09-21, QB fix 2026-09-22, current-season-only 2026-09-24)
For RB/WR/TE stat rows:
- **Team Share** = this player's share of his own team's total production
  in that stat, over the selected Weeks. Scoped narrowly per Trevor's
  explicit choice: receiving stats (receptions, receiving yards) are
  compared against the SAME POSITION ONLY (a WR's share is against other
  WRs, not RBs/TEs on his team); RB rushing yards is compared against
  RBs ONLY (QB scrambles excluded). Air Yards follows this same
  same-position-only scoping automatically, with no extra code.
- **Anticipated** = Team Share % × Opp Allows (same selected Weeks),
  i.e. a projection of the player's stat based on his typical share of
  team production applied to what the upcoming opponent gives up.
- **QBs are a special case, fixed at exactly 100%** (not computed via a
  ratio) — there's only one starting passer, so splitting credit doesn't
  apply the way it does for pass-catchers/backs. This was originally
  computed as a ratio like everyone else, which caused a real bug Trevor
  caught: a QB with zero rushing yards/TDs across the whole selected
  window hit a 0÷0 divide, showing a blank Team Share and an
  Anticipated that didn't match Opp Allows. Fixed by hardcoding
  `share = 100` for `position === 'QB'` in `deriveStats()`, bypassing the
  ratio entirely. Verified against Jordan Love's real data (0.0 rushing
  yards over the selected weeks) — Team Share now correctly shows 100%
  and Anticipated equals Opp Allows exactly.
- Implementation (non-QB): `fetch_stats.py`'s `compute_team_position_totals()`
  builds team+position+stat per-game totals keyed by "season-week".
  **Current-season-only as of 2026-09-24** (previously blended
  current+prior season, matching the old player recent-avg window — see
  the Weeks filter section above for why that blend was dropped
  entirely). `build_dashboard.py`'s `build_team_total_log()` looks up
  each game using the TEAM THE PLAYER WAS ACTUALLY ON THAT GAME (each
  game entry carries its own "team" field) rather than the player's
  current team — otherwise a mid-window trade would compare old-team
  games against new-team totals.
- Team Share can show "-" for TDs/Rush Attempts specifically when nobody
  at that position scored/carried at all in the selected weeks (real
  0÷0, no meaningful percentage) — QB rows are exempt from this since
  they're always fixed at 100%.
- Known cosmetic edge case: Team Share can rarely show slightly over 100%
  at a very small selected-weeks window if a player's official position
  tag varies week to week in the underlying nflverse data.
- **Directly benefits from the zero-stat-week backfill above (2026-09-24)**:
  a player's real quiet weeks now count as real zero-production games in
  both his own average AND his team's totals, so Team Share/Anticipated
  are measured over the player's true full game log rather than only his
  "good" weeks.

## Edge / Anc. Edge / 🔥 / 🧊, now tiered 1-3 plus a FIXED-bar ⭐ MUST BET (added 2026-09-22, tiered same day, price gate added same day, MUST BET tier added 2026-09-24, MUST BET made a fixed bar same day, MUST BET given a consistency gate same day)
Trevor asked for color-coded differences plus a "hot" signal when two
things agree, then unders too ("the Kyle Pitts under should be pretty
good, right?"), then a magnitude scale ("number of emojis indicates HOW
big of an edge... 1 to 3 emoji scale"), then a price gate (see its own
section above), then a 4th tier above the 1-3 scale (see the ⭐ MUST BET
section above), then a follow-up making that 4th tier a fixed, non-
slider-adjustable bar (see the fixed-bar section above), then a further
follow-up requiring a perfect record over the selected weeks on top of
that fixed bar (see the consistency-gate section above):
- **Edge** = Recent Avg − consensus Vegas line (median of DK/FD/BetMGM).
- **Anc. Edge** = Anticipated − the same consensus line.
- Both are colored ONLY when the edge is "big" — |edge / line| >=
  `SIGNIFICANT_EDGE_PCT` (originally a fixed 15%, now the live output of
  the "How picky" slider — see its own section below, added 2026-09-22)
  — green if positive, red if negative, otherwise plain text. **The
  original 15% threshold was an arbitrary choice Claude picked, not a
  real gambling-industry convention** — Trevor asked about its origin
  directly and was told this plainly. He said "leave for now" at the
  time; it's since become adjustable rather than staying fixed.
- **🔥/🧊/⭐ tiers**: fires only when Edge AND Anc. Edge both clear the
  `SIGNIFICANT_EDGE_PCT` bar in the SAME direction (unchanged "two
  signals must agree" rule), AND the relevant side's consensus price
  isn't too steep (see the price gate section above). The COUNT of
  emojis (1-3) reflects stat-edge magnitude only: `EDGE_TIERS` (back to
  3 thresholds, scaled off the slider — see below) — the count is how
  many of those thresholds are cleared by whichever of Edge% / Anc.
  Edge% is WEAKER (the limiting signal), not the average or the stronger
  one. E.g. a 58% Edge paired with only a 17% Anc. Edge still earns just
  1 flame, since the weaker signal caps it. Clearing a SEPARATE, FIXED
  150% bar (`MUST_BET_EDGE_PCT`, not part of `EDGE_TIERS` and not
  affected by the picky slider) renders the distinct ⭐ MUST BET badge
  instead of a 4th repeated flame/ice character — see its own section
  above for why this is fixed rather than slider-scaled. As of
  2026-09-24, clearing that 150% bar is no longer enough on its own for
  Over/Under MUST BET: it also requires a perfect record (zero games on
  the wrong side of the line) across the selected weeks — see the
  consistency-gate section above. Sortable via a numeric `signal` field
  (+1/+2/+3/+4 hot, -1/-2/-3/-4 cold, 0 neither — a price-suppressed row
  also sorts as 0, since it's no longer being recommended).
- This is fully dynamic already, with no extra plumbing needed: Edge/Anc.
  Edge/tiers/the price gate are all recomputed client-side in the browser
  from that run's own `game_log`/`vegas_line`/`over_price`/`under_price`
  data every time the dashboard is opened or the Weeks selection is
  changed, so every `python3 run.py` refresh automatically produces
  up-to-date signals with zero code changes needed. This also means the
  zero-stat-week backfill above flows through automatically -- Edge is
  now computed against a Recent Avg that correctly includes real zero
  weeks.
- Verified via headless Playwright, calling the real `enrichRow()` /
  `signalEmoji()` functions directly with synthetic edge percentages
  across the full range (10%, 15%, 20%, 25%, 39%/26% mismatched, 40%,
  90%, disagreeing signs, one-sided nulls) plus one full end-to-end row
  built from real ARI defense data, confirming tier boundaries, the
  weaker-signal-limits behavior, and the "both must agree" gate all work
  exactly as designed; separately verified the price gate (see its own
  section above) with real defense data and synthetic prices; separately
  verified the fixed-bar ⭐ MUST BET tier — see its own section above
  (confirmed the 150% bar holds steady across slider positions 10/20/30,
  and confirmed the real Trevor-data result of 5 rows); separately
  verified the consistency gate on top of it — see its own section above
  (confirmed real Trevor data drops from 3 old-logic hits to 0 with the
  gate applied).

## "How picky" slider for 🔥/🧊/❓ (added 2026-09-22, MUST BET removed from its scaling 2026-09-24)
Trevor's request: "can you be a little more picky on the levels of ice.
think we could make like a slider along the top that lets me choose how
picky i want to be? there are too many 3 star bets." Asked to clarify
scope before building (a change like this touches shared logic, so
guessing wrong would mean redoing it), he confirmed: the slider should
tighten 🔥 and 🧊 together, not just 🧊 (they already share the exact
same thresholds under the hood, so a single knob keeps them symmetric),
and it should actually raise the bar a row needs to clear to earn a
star in the first place, not just filter which already-computed tiers
get displayed.

**Implementation**: `SIGNIFICANT_EDGE_PCT` and `EDGE_TIERS` — previously
fixed `const`s at 15% and `[0.15, 0.25, 0.40]`, briefly extended to 4
thresholds when ⭐ MUST BET was first added — are `let`s recomputed by
`applyPickySetting()` whenever a new range slider (`#pickySlider`, in
the controls bar, min 10 / max 30 / step 1 / default 20) changes. Every
function that reads them (`edgeClass`, `enrichRow`, which is where
`hotLevel`/`coldLevel`/`needsReview` all live) picks up the new value on
its next call, since JS reads an outer `let` at call-time, not at the
time the function was defined — no need to thread the setting through
every function's parameters. **As of 2026-09-24, `EDGE_TIERS` is back to
3 elements and no longer includes MUST BET's bar at all** — see the
"MUST BET made a FIXED bar" section above for why Trevor asked for that
tier to stop scaling with this slider.

**Design call flagged to Trevor**: rather than give the 1-star/2-star/
3-star bars and the Edge/Anc. Edge coloring and the ❓ "significant"
check separate knobs, the slider moves ONE shared threshold
(`SIGNIFICANT_EDGE_PCT`, i.e. the 1-star bar) and everything else scales
off it at the same ratio as the original fixed numbers (25/15 ≈ 1.67x,
40/15 ≈ 2.67x for 2-star/3-star; the coloring and ❓ checks already used
this exact same constant before the slider existed). This keeps "does
this edge actually matter" one consistent idea across the whole page
instead of, say, 🔥/🧊 getting pickier while Edge/Anc. Edge coloring or
❓ silently stay at the old fixed bar underneath. Wasn't explicitly
asked for either way, so flagging it as an assumption. **MUST BET is now
the one deliberate exception to this "one shared knob" philosophy** —
Trevor explicitly asked for it to always mean the same absurd thing
regardless of the slider, so it was pulled out into its own fixed
constant rather than kept in this scaling group.

**Range and default**: 10%-30%, default 20% — up from the original fixed
15%, satisfying "be a little more picky" as the slider's starting
position rather than a separate hardcoded change. Both the range and the
default are Claude's own reasonable-looking picks, not derived from
anything in Trevor's message, and disclosed as such in the README. The
live label next to the slider always shows the exact resulting cutoffs
for 1/2/3 stars (e.g. "1★ ≥20% · 2★ ≥33% · 3★ ≥53%"), plus MUST BET's
fixed 150% bar labeled "(fixed, not slider-adjustable)" so it's clear on
the page itself that dragging the slider won't move it. Doesn't touch
`MAX_JUICE_PRICE` (the price gate) — that's a separate check on bet
price, orthogonal to the size of the stat edge. The setting isn't
persisted; it resets to 20% on page reload (this dashboard has no other
state that survives a reload either, e.g. Position/Weeks/Stat filters,
so this matches existing behavior rather than being a new limitation).

Verified via headless Playwright: confirmed the label and
`SIGNIFICANT_EDGE_PCT`/`EDGE_TIERS` recompute correctly at the initial
default (20 → 20%/33.3%/53.3%) and after simulating slider drags to 10
and 30 (→ 10%/16.7%/26.7% and 30%/50%/80%); confirmed `edgeClass()`
responds live (a fixed 12% edge reads as significant at the 10% setting
but not at 20%); confirmed the underlying tier-count logic actually
changes how many stars a FIXED 28%-edge row earns as the slider moves —
3 stars at 10%, 2 at the original 15%, 1 at the new default of 20%,
still 1 through 25-28%, and 0 (no stars) at 30% — concretely
demonstrating that the new default is stricter than the old fixed value
and that the slider has real range above and below it; separately
confirmed `MUST_BET_EDGE_PCT` never moves at any of these slider
positions (see the fixed-bar section above). Also confirmed the DOM
table re-renders on slider input with zero JS console errors. Real-world
impact of the MUST BET tier (both the original slider-scaled version and
the corrected fixed-bar version, plus the later consistency gate) was
confirmed separately against Trevor's own real Mac data — see the ⭐
MUST BET sections above.

## Personal bet marks: ✅/🌕/❌ + "Hide ❌" filter (added 2026-09-22)
Trevor's request: "would it be possible to have an emoji selector if i
want to bet the lines? or would it overwrite everytime we re-sync'd
them." The concern was well-founded given the architecture: `run.py`
fully regenerates `dashboard.html` from scratch every time (it's a
static, self-contained file with all data baked into it at build time —
see "Why it's architected this way" above), so anything written INTO
that file would indeed get wiped on the next sync.

Before building, asked two clarifying questions since guessing wrong on
either would mean redoing real work: (1) what should the marker actually
track, (2) does he want an export/import safety net for the marks or is
plain browser storage enough. He answered directly rather than picking
from the offered options: "it's okay if it's simple. i'd also like a ✅
if i bet it, 🌕 if i'm looking and ❌ if i don't want it. also filters
at the top that let me exclude Xs when i'm viewing them."

**The fix**: keep the marks OUTSIDE the regenerated file entirely, in
this browser's `localStorage` (key `nfl_prop_dashboard_marks_v1`, a JSON
object of `{markKey: 'bet'|'watch'|'pass'}`), so a `python3 run.py`
re-sync — which only touches `dashboard.html` — never touches them.
`markKey(r)` is `WEEK + '|' + player + '|' + team + '|' + stat_col`
(`WEEK` is a new top-level JS constant, `{week}` already available to
the template since it's used elsewhere for the page title). Including
week in the key is a judgment call: it means marks don't carry over
between different weeks' versions of "the same" player+stat (a fresh
slate each week, since it's a genuinely different betting decision), but
DO survive any number of re-syncs within the same week, which is what he
actually asked about.

**UI**: a native `<select>` per row (leftmost column, header "Mark"),
options `— / ✅ Bet it / 🌕 Watching / ❌ Pass` — chose a plain `<select>`
over a custom popover/dropdown for "emoji selector" since it's simpler,
keyboard-accessible, and needs no positioning/click-outside logic, in
keeping with "it's okay if it's simple." Shows up in the main table AND
inside the player detail modal (each stat row there is its own separate
bettable line, so it gets its own independent marker, not a shared one
for the whole player) — both read/write the same `MARKS` object and
`localStorage` key, so a mark set in one place is immediately correct in
the other. A checkbox ("Hide ❌ rows") in the controls bar filters
❌-marked rows out of the main table's view, per his exact ask; it only
affects what's displayed, not the marks themselves.

**One non-obvious bug caught before shipping**: the main table's `<tr>`
already had a click handler that opens the player detail modal on a
click ANYWHERE in the row. Adding a `<select>` inside that row meant a
click to open its dropdown would bubble up and incorrectly trigger the
modal too. Fixed by checking `e.target.closest('.mark-select')` first
and returning early — caught by explicitly testing this exact scenario
in Playwright (see verification below), not by accident.

**Deliberately NOT built**, matching "it's okay if it's simple": no
export/import backup, no cross-browser or cross-machine sync, no
outcome tracking (won/lost) beyond the three states given, no undo
history. Flagged clearly in the README: marks are tied to this specific
browser and this specific file location — clearing browser data,
switching browsers, or opening a moved/renamed copy of the file all
start from a blank slate, since none of that carries the localStorage
bucket along. Offered to add a save/restore-to-file option later if that
ever becomes a real problem for him.

Verified via headless Playwright end-to-end against the real production
build (2346 rows): confirmed `WEEK` reads correctly from real data
(`3`); confirmed the select has all 4 options; set a real row's mark to
`pass` through its actual `<select>` element (not just calling JS
directly) and confirmed it landed in both the in-memory `MARKS` object
and raw `localStorage`; confirmed clicking the select does NOT open the
player modal (the bug above, now fixed); confirmed checking "Hide ❌
rows" removes exactly the one marked row from the DOM and no visible
select still shows `pass`; **reloaded the page** (the closest in-browser
proxy for "regenerate the file and reopen it," since a rebuild doesn't
touch localStorage either way) and confirmed the mark survived and the
matching `<select>` still showed `pass` after reload; opened the player
detail modal for that same player and confirmed its own copy of the
mark-select correctly showed `pass` on the matching stat row while every
other stat row for that player stayed correctly independent and blank.
Zero JS console errors throughout.

## Weather + bad-weather red/amber flag (added 2026-09-22, flag added same day)
A **Weather** column shows the forecast at the HOME team's stadium for
kickoff: temp/wind/condition/precip%, e.g. "51°F, 24mph, Partly cloudy
(10%)". Domes and retractable-roof stadiums show "Dome" instead (treated
as weather-neutral — retractable roofs are closed the large majority of
NFL games, so showing a real forecast there would be misleading more
often than not). Blank means the forecast isn't available yet (game too
far out) or the stadium wasn't recognized.
- `stadium_info.py` has lat/lon + dome flag for all 32 current stadiums
  plus the international one-off venues on the 2026 schedule (Wembley,
  Tottenham, Bernabéu, Munich's Allianz Arena, MCG, Stade de France,
  Estadio Banorte, Maracanã) — verified the exact stadium name strings
  and roof/schedule data directly against nflverse's `games.csv` (which
  already includes stadium/roof/gametime, so no separate lookup table
  was needed for that part). Houston's venue is listed there as
  "Reliant Stadium" (legacy name) even though it's NRG Stadium today —
  matched that exact string, not the current name.
- This is a NEW external API call the account's egress allowlist blocks
  (see architecture note above), so like Odds API, it only works when
  Trevor runs `fetch_weather.py` (via `run.py`) in his own Terminal.
- **Bad-weather flag (added 2026-09-22)**: Trevor asked for "a flag for
  bad weather, so for things like very cold, high wind, rain... the
  weather column text in red." Implementation is server-side, in a new
  `is_bad_weather()` in `build_dashboard.py`, so it's plain data (a
  `weather_bad` boolean per row) rather than JS re-deriving it from raw
  fields: flags red if ANY of — temp ≤25°F, wind ≥20mph, precip chance
  ≥50%, or the condition text contains rain/drizzle/snow/thunderstorm.
  Amber (`wind-med`) is kept as a lighter "worth a look" tier for
  elevated wind (15-19mph) that isn't yet bad enough to flag red on its
  own. Like the 15%/25%/40% edge thresholds, **these bad-weather
  thresholds (25°F / 20mph / 50%) are Claude's own reasonable-looking
  picks, not an official standard** — flagged to Trevor proactively in
  the README given the established pattern around arbitrary constants in
  this project. Also applied to the weather shown in the player detail
  modal's meta line (same red styling). Fully dynamic like everything
  else — recomputed at every `fetch_weather.py`/`run.py` refresh with no
  extra step.
- Verified: `is_bad_weather()` unit-tested directly in Python across 11
  cases (good weather, borderline-cold-but-not-bad, exactly-cold,
  high-wind, borderline-wind-but-not-bad, heavy precip%, rain condition
  with low precip%, snow, thunderstorm, dome-ignored-even-if-extreme,
  forecast-unavailable-ignored) — all behaved exactly as designed. JS
  `weatherClass()` also checked directly in the browser for the same
  boundary cases. No real weather data exists in the cloud sandbox to
  screenshot against (Open-Meteo is blocked there, same as Odds API), so
  this will show live once Trevor runs `fetch_weather.py` on his Mac.

## Click-to-expand player stat card (added 2026-09-22, game-by-game box score added same day)
Trevor asked: "could i add something where if i click into a player it
displays their stats?" Clicking any player's name opens a modal overlay
with two parts:
1. A summary table with EVERY stat category this dashboard tracks for
   that player (not just whichever one the main table is currently
   filtered to) — Recent Avg, Opp Allows/Rank, Team Share, Anticipated,
   Edge, Anc. Edge, 🔥/🧊, DK/FD/BetMGM lines. This is also where Air
   Yards (RB/WR/TE) shows up automatically now.
2. A **game-by-game box score** (added after Trevor said "I want it to
   show the actual game lines though... if it's filtered to last 2, it
   shows that player's last two games and all stats they had") — one row
   per game that falls in the selected Weeks, one column per stat, so it
   reads like a real box score instead of a single stat's numbers listed
   in isolation.
Closes via the × button, clicking outside the card, or pressing Escape.
- Implementation: refactored the per-row enrichment logic that used to
  live inline inside `render()`'s `.map()` callback into a standalone
  `enrichRow(r, weeks, defCache)` function (originally took a game-count
  `n`; changed to a `selectedWeeks` Set on 2026-09-24 — see the Weeks
  filter section above), so the main table and both modals (player +
  defense) share identical computation logic and can never drift apart —
  this is also why the new price gate automatically applies everywhere
  🔥/🧊 shows up, with no separate code needed per view. **This is also
  the exact mechanism that made the zero-stat-week backfill fix visible
  the moment `fetch_stats.py` produced the corrected data — see its own
  section above.**
- `fetch_stats.py`'s `recent_games` entries already carried `season`/
  `week`/`opponent` per game; `build_dashboard.py` now also threads those
  through to the JS side as `game_weeks`/`game_seasons`/`game_opponents`
  arrays (same order/length as `game_log`) specifically so the modal can
  label each box-score row with which week it was.
- Player names are escaped via a small `escapeHtml()` helper before being
  embedded in the `data-player` attribute (handles names with apostrophes
  like "Aidan O'Connell" safely).
- Verified via headless Playwright against real cached data: Jordan
  Love's (QB) 7-stat summary + box score, and Ashton Jeanty's (RB) box
  score, both cross-checked line-for-line against `stats_cache.json`;
  all close mechanisms confirmed, no console errors.

## Click-to-expand defense card (added 2026-09-22, opponent-per-game and coverage header added same day)
Trevor asked: "would you be able to do the same for the defense? So if i
click the Opp Column, it shows me what they've allowed over that game
set?" Clicking a row's Opp cell (not the rest of the row, which still
opens the player card) opens a defense card for that team: a coverage-
scheme header (see its own section above) if that data's been fetched,
then one section per position (QB/RB/WR/TE, whichever the team has data
for), each with a summary (every stat that position allows, its average
and rank over the selected Weeks) and its own game-by-game box
score (one row per game in the selected Weeks, one column per stat) —
the same "what actually happened each game" format as the player card.
The position the row was clicked from is shown first; the rest follow.
- Required a real data change, not just JS: `compute_defense_allowed()`
  in `fetch_stats.py` only stored per-game VALUES before, with no way to
  say which week each number came from. Added a parallel
  `games_meta[team][pos]` structure (same order/length as the value
  lists, since they come from the same underlying per-game grouping) and
  a new `defense_allowed_games` key in `stats_cache.json`. This needed a
  fresh `fetch_stats.py` run to populate (nflverse data is fetchable
  directly from the cloud sandbox, unlike Odds API/weather, so this was
  done without needing Trevor's Terminal).
- `td.opp-cell` carries `data-opponent`/`data-opp-pos` attributes; the
  shared `tbody` click handler checks for an `.opp-cell` ancestor FIRST
  (opens the defense modal and returns) before falling through to the
  existing player-row-click logic — clicking anywhere else in a row still
  opens that player's card, unchanged.
- Reuses the same modal overlay/panel markup as the player card (just
  repopulated with different content) rather than a second overlay.
- **Named opponent per game (added 2026-09-22)**: Trevor asked "for
  defenses, can you list the opponents they played in their popup?" Each
  game-by-game row used to say only "2026 Wk2"; `compute_defense_allowed()`
  now also aggregates the offensive "team" column via `.agg({..., "team":
  "first"})` — safe because a team plays exactly one opponent per week, so
  it's constant within that (defense, season, week) group — and stores it
  as a `"vs"` field in `games_meta`, alongside season/week. The JS just
  appends `" vs " + gamesMeta[i].vs` to the Game column label, matching
  the player card's own "Wk2 vs ATL" formatting for consistency. Needed
  another fresh `fetch_stats.py` run (same reason as above).
- Verified via headless Playwright against real ATL defense data (QB
  section, clicked-position-first ordering, RB-click-orders-RB-first),
  cross-checked pass-yards-allowed numbers AND the named opponents
  line-for-line against `stats_cache.json` (e.g. ATL's QB rows correctly
  read "2026 Wk2 vs CAR" / "2026 Wk1 vs PIT"), and confirmed all three
  close mechanisms plus "player name still opens the player card, not the
  defense card" all work.

## Bug fixed in passing (2026-09-21)
`compute_recent_player_stats()` used to group players by
`player_display_name`, which silently merges stat lines when two
different real players share an exact name (found via a genuine NFL name
collision while spot-checking the team-share math). Now groups by
`player_id` (nflverse's stable ID), with the display name stored as a
`name` field. `build_dashboard.py` updated to read `info["name"]`
accordingly. This makes the whole dashboard more correct, not just the
new feature.

## Scheduled automation — declined, paused (2026-09-24)
Trevor asked whether the dashboard could refresh on a schedule and push
a notification when a new good line shows up. Clarified scope with him
first (refresh cadence, what counts as a "good line," whether to also
auto-republish the shared link), then attempted to set this up as a
scheduled task (every 4 hours: refresh data via the device bridge,
detect new 3-flame/3-ice rows, dedupe against a state file, push a
notification, republish the artifact). **Trevor rejected that setup
call**, then said explicitly: "i want to pause this for now." No
scheduled task exists for this. Not revisited unless Trevor asks again —
noting this clearly so a future session doesn't reintroduce it on its
own.

## Known limitations (told to Trevor)
- Sportsbooks often don't post full player-prop boards until a few days
  before kickoff, so early in the week most games will show blank
  book/Edge/Anc. Edge columns — expected, not a bug.
- Player names are fuzzy-matched between nflverse and Odds API
  (normalized: lowercase, strip periods/apostrophes/suffixes like Jr./III).
  A handful of edge-case mismatches are possible.
- Defense-allowed figures use CURRENT SEASON data only (verified against
  a live fantasy site's numbers), dynamically re-ranked at whatever
  weeks are selected in the Weeks filter.
- Team Share/Anticipated use the CURRENT-SEASON-ONLY window (matching
  player recent-avg) as of 2026-09-24 — previously blended in the end of
  last season early in the year; see the Weeks filter section above for
  why that changed.
- Hit Rate is hidden from the UI by request but logic remains for later
  re-enabling.
- Weather forecasts are only meaningful roughly a week out, which
  matches the dashboard's one-week-ahead window; very early in a week a
  forecast may not be posted yet for a given stadium (shows blank).
- The 15%/25%/40% edge thresholds (1/2/3 star, slider-adjustable), the
  separate FIXED 150% ⭐ MUST BET bar (2026-09-24, not slider-adjustable
  — see its own section above for why), the 25°F/20mph/50% bad-weather
  thresholds, the 65%/90% zone-rate tier cutoffs, the -130 price-gate
  cutoff, and the Tuesday-3am game-filter reset cutoff are all Claude's
  own arbitrary choices, not real gambling/meteorology/league
  conventions — Trevor knows this (asked directly about the 15% figure
  once already, about the price gate directly, and set the MUST BET bar
  himself via "should be absurd") and hasn't asked to change any of the
  others yet. ❓ reuses the same 15% bar rather than introducing its own
  new number.
- **❓ does not itself say which direction (over/under) is more likely**
  — it just flags that the two signals didn't confidently agree, or that
  only one had anything to say. Trevor has to look at the actual Edge/
  Anc. Edge values and the underlying matchup to decide what to make of
  it — that's the point ("i need to review it").
- Air Yards is deliberately a context-only stat (no line, no Edge/🔥) —
  not a bug, no market exists for it.
- Kicker and defensive-player props are surveyed/documented but not
  built (would need a different architecture — see Stat categories
  section above).
- **Coverage-scheme tags are team-level and season-to-date only, by
  design** — there is no free source found (checked nflverse's own
  detailed datasets plus the open web) for how a specific PLAYER performs
  against man vs. zone coverage; that's a PFF/SumerSports-paywalled
  metric. The tag says how often a defense plays each scheme, not
  whether any given player is a good or bad fit against it — Trevor
  chose this scoped-down version explicitly after being told the
  player-level half isn't available for free.
- Coverage-scheme data comes from an UNOFFICIAL scrape of a third-party
  page (sharpfootballanalysis.com), not a documented API like everything
  else in this project — the single most likely thing here to break if
  that site changes its page layout. It fails safely (won't corrupt the
  existing cache, prints a clear reason) and won't block the rest of
  `run.py` if it does.
- **The price gate checks the specific book Edge/Anc. Edge are shopped
  against (added 2026-09-24), falling back to the consensus price only
  when no single book was pinned** (a dead-even tie against consensus,
  or no per-book price data at all) — see "Line shopping" above. Before
  2026-09-24 it only ever checked the blended consensus price regardless
  of which book actually had the best number.
- **Line-shopping ties are now broken by price, not book-list order
  (follow-up fix, 2026-09-24)** — Trevor caught DraftKings being
  highlighted over FanDuel despite FanDuel's -110 beating DraftKings'
  -116 at an identical line. Fixing it properly required storing each
  book's Over AND Under price separately (previously only one was ever
  kept), which also fixed a related, previously-undisclosed bug: the 🧊
  price gate was checking a pinned book's Over price even when gating an
  Under bet. See "Line-shopping tie-break fixed" above for the full
  disclosure and verification.
- **The 🪜 ladder badge is a simple season-ceiling check, not a real
  priced-ladder/EV feature** — scoped to QB Pass/Rush Yds, RB Rush/Rec
  Yds, and WR/TE Rec Yds only, requires the CURRENT line to be at least
  30 (added the same day after the first real-data check turned up a
  meaningless "10x" read on a QB's 0.5 Rush Yds line), and flags whenever
  the player's single best game this season cleared 2x that line — it
  does not fetch or price real alternate-line/ladder markets (The Odds
  API does support those, confirmed, but that would need a new fetch
  step, more API quota, and real EV math this dashboard doesn't do
  anywhere else yet). It also ignores the Weeks filter by design (it's a
  "has this ever happened" question, not a recent-form one), and is
  per-STAT rather than per-player like the ⛑️/🛡️ badges — so in the
  Player-grouped sort view specifically, the badge can be hidden if the
  first-shown stat row for a player isn't one of the ladder-eligible
  ones, even though a different stat row for that same player still
  qualifies. A "Ladder only" filter checkbox (top controls bar) narrows
  the table to just the flagged rows.
- **The ⛑️ badge is the official injury report only, not narrative news**
  — Trevor asked about news-style injury blurbs specifically and chose
  this scoped-down version after being told no free source exists for
  narrative injury news.
- **Injury badges before a team's final report use the practice report
  (fixed 2026-09-25)** — "Missed practice" (did not participate, real
  injury) is flagged until the official Out/Doubtful/Questionable
  designation comes out; Limited practice isn't flagged. Re-run
  `python3 run.py` after Friday's final reports for the firmest picture.
- **🩹 impactful-injury badges (2026-09-25, replaced the 🛡️ O-line
  badge) only count 50%+ snap-share players** — an arbitrary "starter"
  cutoff. It can occasionally miss a real starter whose average dipped
  because he left a game early hurt (real example: GB G Aaron Banks, Out,
  37% average). The per-position rules are Trevor-approved but are a
  simple model: they say whether an injury helps or hurts, not by how
  much, and don't weigh which CB covers which WR, etc.
- **The Game filter resets on its own every Tuesday morning (3am local),
  independent of the WEEK value baked into the file** — see its own
  section above. It's meant as a short-lived convenience, not a
  persistent preference like the bet marks.
- **The Weeks filter (replaced Last N games, 2026-09-24) does NOT persist
  between page loads** — like the old Last-N buttons it replaced, it
  resets to the default (weeks 1 through current) on every fresh load or
  rebuild. Wasn't asked to persist it, so it wasn't added; say the word
  if that'd be more useful.
- **Dropping the prior-season blend (2026-09-24) means an early-season
  Weeks selection is a genuinely small real sample** — e.g. Week 2 with
  the default selection is a true 2-game average, with no cushion from
  last season's final games the way the old "Last N games" sample used
  to provide. This is an intentional trade-off of moving to weeks-based
  selection, not an oversight; see the Weeks filter section above.
- **The ⭐ MUST BET tier (added 2026-09-24) is a rarer 4th level above
  the old 3-flame/3-ice ceiling, not a replacement for it** — 3-flame/
  3-ice rows still exist and still sort second, right below MUST BET.
  Its bar does NOT move with the "How picky" slider (unlike 1/2/3 stars)
  — deliberate, per Trevor's explicit ask that MUST BET always mean the
  same absurd thing. As of the same day, it ALSO requires a perfect
  record (zero games on the wrong side of the line) across the selected
  weeks, on top of the fixed Edge/Anc. Edge % bar — see its own sections
  above for the full real-data before/after splits across all four
  iterations (44 old "3 stars" → 25 MUST BET/19 three-star under the
  first, slider-scaled version → 5 MUST BET under the fixed-150%-bar
  version → 0 MUST BET / 3 rows correctly held back once the consistency
  gate was added → 7 Over + 7 Under real MUST BET rows once the bar was
  lowered to a fixed 100% on top of that same gate, per Trevor's direct
  ask — with held-back rows always redistributing into whatever 1/2/3-
  star tier their numbers still earn, never disappearing outright).
  **At the current 100% bar, a handful of the real Over hits are on
  thin, low-line stats (e.g. a 0.5-line INTs market)** — a genuinely
  correct signal (the player has taken that side of the line in every
  game in the window) but a thinner one than a real yardage
  overperformance, similar in spirit to the 🪜 ladder badge's pre-30-yard-
  floor thin-line issue. No minimum-line floor has been requested or
  added for MUST BET; flagged here rather than silently patched. On the
  Under (🧊) side, MUST BET was unreachable under the original fixed
  150% bar (real stat values can't go negative, so -100% is the
  mathematical floor for edge_pct) but became reachable — right at that
  same -100% floor — once the bar was lowered to 100%; see the
  consistency-gate and threshold-lowering sections above for the full
  math.
- **Zero-stat weeks now count as real zeros (fixed 2026-09-24)** — a
  player who was active and played real snaps but recorded no stats
  (e.g. a blocking TE with zero targets) used to have that week silently
  vanish from his average entirely, rather than count as a real 0. Fixed
  via nflverse's own snap-count data + player-ID crosswalk — see its own
  section above. Side effect: a few low-volume players' now-more-honest
  averages dropped below the existing minimum-relevance filter and
  quietly stopped appearing (12 rows / 3 players in the real data) — not
  a bug, the fix working as intended.
- **A real process bug in the artifact-republish pipeline (self-caught
  and fixed 2026-09-24) means the earlier "Version 9" artifact did NOT
  actually contain the Weeks filter, despite being reported to Trevor as
  containing it** — see the "Artifact republish process bug" section
  above for the full disclosure. Version 26 is the correct, current
  artifact.
- **The "Weak matchup only" filter (added 2026-09-24) is a companion to
  the 🪜 ladder badge, reusing the existing Opp Rank number rather than
  fetching or computing anything new** — `WEAK_DEFENSE_RANK_MIN = 20` is
  Trevor's own literal "20-32," and doesn't rescale if `def_rank_max`
  ever comes in under 32 (effectively never in-season); see its own
  section above for the full disclosure.
- **The "Strong matchup only" filter (added 2026-09-24) is the mirror of
  Weak matchup, `STRONG_DEFENSE_RANK_MAX = 13`, meant for spotting Under
  candidates** — a low Opp Rank (currently limiting the stat well) is the
  favorable signal for an Under, the opposite end from Weak matchup's
  high-rank/Over-friendly signal. The two filters are mutually exclusive
  by design (checking both at once always yields zero rows); see its own
  section above for the full disclosure and real-data verification.
- **The game-by-game box score now shows an explicit "DNP" row for an
  already-played week with no game entry for that player (added
  2026-09-25), but only in the player modal, and without an opponent
  name on the DNP row itself** — the defense modal's box score isn't
  covered by this fix (a defense's own bye week would have the same kind
  of silent gap), and showing which team a DNP'd player would have faced
  that week would need each team's full-season schedule threaded through,
  which isn't currently available client-side (only the upcoming week's
  schedule is). Neither was asked for; see its own section above for the
  full disclosure.
- **"Targets" (added 2026-09-25) is context-only, like Air Yards** — no
  Vegas line, Edge, Anc. Edge, or 🔥/🧊, since there's no Odds API
  player-prop market for it. It still gets Recent Avg / Opp Allows / Opp
  Rank / Team Share like every other stat, just never a bettable line;
  see its own section above.
- Trevor mentioned once, mid-message, that odds "still aren't pulling in
  right" but the message was cut off before he could elaborate — nothing
  has been diagnosed or changed for this yet; needs his follow-up detail.
- The scheduled auto-refresh + push-notification idea was proposed,
  rejected in its first form, and explicitly paused by Trevor — see its
  own section above. Don't re-propose without him asking again.

## Status
Validated end-to-end (real Week 1-3 2026 data, real DK/FD/BetMGM odds,
dynamic defense ranking, team-share/anticipated math including the QB
fix and now correctly counting real zero-stat weeks, edge coloring/
tiered hot+cold logic now with the ⭐ MUST BET 4th tier as a fixed,
non-slider-adjustable bar that also requires a perfect record across the
selected weeks, new stat categories including the Air Yards context
stat, weather rendering + the bad-weather flag, the player detail modal
with its game-by-game box score (now correctly showing every real game,
including zero-stat ones), the defense detail modal with named per-game
opponents, the man/zone coverage-scheme tags now with 3-tier labels, the
price gate on 🔥/🧊, the ❓ "needs review" signal (refined once to drop
flat sign disagreements), the signal-strength default sort order (now
with MUST BET sorting above everything else), the Opp Rank color
gradient, the "How picky" slider that makes the 1/2/3-star 🔥/🧊/❓
significance threshold live-adjustable with a stricter default (MUST
BET deliberately excluded from this scaling as of 2026-09-24), the new
personal ✅/🌕/❌ bet marks with their "Hide ❌ rows" filter, the ⛑️
official-injury-report badge, the 🛡️ O-line concern badge on QB/RB
rows, the Game filter with its Tuesday-morning auto-reset, the Weeks
filter (replacing Last N games with per-week checkboxes,
current-season-only), the zero-stat-week backfill (nflverse snap-count
data + player-ID crosswalk), the line-shopping tie-break fix (ties now
go to the better price, using separately-tracked Over/Under prices per
book, which also fixed the 🧊 price gate reading the wrong side's
price), the 🪜 ladder badge (30-yard floor + its own filter checkbox),
the MUST BET consistency gate (zero games on the wrong side of the
line), the MUST BET threshold lowered to a fixed 100% on top of that
gate, the "Weak matchup only" filter (Opp Rank 20+, composable
with Ladder only), its mirror "Strong matchup only" filter (Opp Rank
1-13, for spotting Under candidates), the explicit "DNP" rows now
shown in the player modal's game-by-game box score for an already-played
week with no game entry, the new context-only "Targets" stat for
RB/WR/TE, and the 🩹 impactful-injury badges (own-team + opposing-
defense, per stat, 50%+ snap players, working for every team via the
practice-report fallback) — all spot-checked against manual arithmetic and via headless
Playwright, including direct calls into the
page's real JS functions, Python's real `is_bad_weather()`, a synthetic
`coverage_cache.json`, real production rows mutated with synthetic
lines/prices/edge percentages, seeded `localStorage` states for both the
bet-marks and game-filter persistence logic, direct raw-nflverse-data
spot checks (snap counts, player-ID crosswalk) against a real player
(Austin Hooper), and (for the bet marks) driving the real `<select>`
elements and reloading the page to confirm marks survive it, since live
Odds API/Open-Meteo/Sharp-Football-Analysis calls aren't reachable from
any Claude-side tool.

Files pushed to Trevor's Mac (`~/Documents/Gambling Program/`) via the
device bridge, most recently `fetch_injuries.py`, `build_dashboard.py`,
and `README.md` for the impactful-injury badges, rebuilt there with his
own fresh nflverse/odds/injury data (1625 rows).
The consistency gate itself was confirmed against real data first (the 3
rows that would have wrongly earned MUST BET under the pre-gate logic —
Kendrick Bourne, Jonnu Smith, Elic Ayomanor, all Rec Yds, each with
exactly 1 game below the line in the selected weeks — are correctly held
back), then the lowered 100% bar was confirmed to surface 7 real Over
rows and 7 real Under rows where the gated 150% bar had produced zero of
either, the weak-matchup filter was confirmed to match 523 of 1370 rows
on its own (0 false positives) and exactly 7 real players (Dalton
Schultz, DJ Moore, Romeo Doubs, Christian Watson, Bijan Robinson, Dalton
Kincaid, Jalen Coker) combined with the existing Ladder-only filter, its
mirror strong-matchup filter was confirmed to match 613 of 1370 rows on
its own (0 false positives/negatives) and 4 real players (Davante Adams,
Josh Allen, Jaylen Waddle, Tre Tucker) combined with Ladder-only, the
DNP-row fix was confirmed against a full sweep of all 281 real players
(25 real DNP rows correctly flagged, 0 false positives), with Michael
Pittman's real card specifically confirmed to show "2026 Wk2 — DNP" where
it previously just silently had no Week 2 row, and the new Targets stat
was confirmed by cross-checking Pittman's real Targets row against his
real Receptions row directly and sweeping 243 real players to confirm
receptions never exceeds targets in the same game for any of them. The
impactful-injury badges and the practice-report fix were then confirmed
on a fresh `fetch_injuries.py` run on the Mac (98 injured players across
31 teams, 48 at 50%+ snaps; badges on 796 rows across 24 teams, up from
Green Bay only) with all 19 `verify_impact.py` checks passing.
**The shared claude.ai artifact link is currently at Version 26** (bet slip added; built from Trevor's 2026-09-28 11:23 run, Week 4). Before that, Version 25 (same code as Version 24, republished 2026-09-27 from Trevor's own `python3 run.py` that morning — stats 09:33, final Friday injury reports: 123 injured players across all 32 teams, confirming the SSL fix works in his Terminal), which
is the correct, current state — confirmed to genuinely contain the Weeks
filter, the fixed-bar ⭐ MUST BET tier at its current 100% threshold with
its consistency gate, the zero-stat-week backfill, the line-shopping
price tie-break fix, the 🪜 ladder badge (with its 30-yard floor and its
own filter checkbox), the "Weak matchup only" and "Strong matchup only"
filters, the DNP row fix in the game-by-game box score, the Targets stat,
and the 🩹 impactful-injury badges with the all-teams injury fix, all
against Trevor's own real Mac data. This supersedes Version 22 (injury
badges only worked for Thursday-night teams; old 🛡️ badge), Version 21
(missing the Targets stat), Version 20 (missing the DNP-row
fix), Version 19 (missing the strong-matchup filter), Version 18 (missing
the weak-matchup filter), Version 17 (correct at the time, but at the old
150% MUST BET threshold), Version 16 (missing the MUST BET consistency
gate entirely), Version 15 (missing the 30-yard floor and the ladder
filter), Version 14
(missing the ladder badge entirely), and Version 13 (missing the
tie-break fix), and corrects the earlier claim that "Version 9" contained
the Weeks filter — it did not, due to a self-caught process bug in the
republish pipeline; see the "Artifact republish process bug" section
above for the full disclosure and fix.
The scheduled auto-refresh + push-notification idea (see its own
section above) was proposed, its first setup attempt rejected, and then
explicitly paused by Trevor — not in effect, not revisited without him
asking again.

## Week 3 (2026) bet review — lessons

Reported 11-9 on 20 bets; Adonai Mitchell (O44.5 rec yds) did not play (finger), so it should be a void → realistically 10-9-1. PHI@CHI MNF stats (Wicks, Monangai) were not yet in nflverse at review time.

- **Correlation:** 5 of the wins (Love U rush, Hooper, Watson, Golden, London ladder) came from one game script — ATL 35-14 over GB with Love throwing 53 times. Treat same-game stacks as one bet when sizing.
- **Thin-sample MUST BETs:** RB receiving yards built on two games of 1–3 targets split — Henry O9.5 (1 tgt, 0 yds) lost; Pollard U6.5 (4 rec, 22) lost. The INT parlay (Nix/Stafford) won, but the INT research says those signals are coin flips.
- **Volume over yards:** Stroud (27 att, 167), Chase Brown (13 car, 61), Henry (1 tgt) lost on opportunity, not efficiency.
- **Game script:** Willis U33.5 rush lost as a 10-pt dog trailing (scrambles); trailing GB inflated the GB receiver overs.
- **Injury flags:** Stroud had three red "hurts" flags (Nico Collins OUT, Ed Ingram OUT, Trent Brown Q) and missed by 70 yards.
- **Against the dashboard:** London (dashboard leaned under) won; Ferguson O49.5 (dashboard leaned under 27.5) lost.
- Near misses by 2.5: Chase Brown, Freiermuth (and Mooney won by 2.5).

## V27 (2026-09-29) — opponent rank in the player card's game-by-game table

Each number in the game-by-game table now carries a colored `#N` chip: how that game's opponent ranks at defending that stat vs the player's position (same rankDefenses() ranking and selected weeks as the Opp Rank column; hover shows the per-game average allowed). A footer row "Avg opp rank faced" averages the chips per stat (played games only). Helper `oppRankChip(r, opp)` reads the modal's defCache via `_modalDefCache`; CSS `.opp-rank-chip`, `.opp-rank-avg`, `.modal-note`. build_dashboard.py sha256 49a9eb42…b41a (applied on the Mac via a patch after device_commit_files silently failed again).

Also noted 9/29: injuries showed empty on Tuesday because nflverse had no Week 4 rows yet (first practice reports Wednesday). Offered, not built: a "not released yet" notice and carrying forward last week's Outs.

## V28 (2026-09-29) — bet tracker (My Bets), $ stake, sort by Mark

- Bet slip gains a $ stake box and a live "to win $X". `validBetStake`, `parseStake`, `parseOdds`, `winAmount`, `betProfit`, `money`.
- Mark header is sortable (`mark_rank`: bet 3, watch 2, unmarked 1, pass 0; first click sorts descending so ✅ is on top).
- "📒 My Bets (N · W-L)" button next to the Weeks filter opens a popup (reuses the player modal overlay, `myBetsOpen` flag): record, total profit, ROI on risked, pending count and $ in play, per-week breakdown table, and every bet grouped by week with editable side/line/odds/$ plus a Result select (Pending/Win/Loss/Push/Void) and per-bet profit. The Actual column reads the stat from ROWS game logs, with a "looks W/L/push" hint; "Fill in suggested results" applies hints to pending bets. Manual bets (`manual|<ts>` keys: desc, week, odds, stake, result) cover parlays and ladders. × removes a bet (two clicks; no confirm() because it is blocked on the shared link). Backup/restore uses a JSON textarea that merges `{marks, bets}`.
- Week over week: each bet stores a `meta` snapshot (season, week, player, team, opp, at, pos, stat_col, stat_label) via `ensureBetMeta`; `backfillBetMeta()` runs at load for bets saved before V28. The popup renders from MARKS/BETS only, so past weeks survive new builds. Storage stays per-browser localStorage (the Mac file and the artifact are separate lists; Backup moves data between them).
- build_dashboard.py sha256 341a8dd6…ba02. device_commit_files silently failed once more; fixed with an in-place edit and hash check.

## V29 (2026-09-29) — week filter in the My Bets popup

A Week dropdown (`betsWeekFilter`: 'ALL' or 'season|week', kept for the page session) filters the bet list and the summary cards (labelled with the week). The per-week breakdown shows only under All weeks, and its rows are clickable to jump to that week. "+ Add a bet by hand" defaults to the filtered week. build_dashboard.py sha256 4e0be7b6…99fc (applied on the Mac via a patch script).

## V30 (2026-09-29) — "Best line" / line value (CLV) in My Bets

For ✅ bets on this week's slate, `bestMarketFor(row, side)` picks the best DK/FD/BetMGM line for the bet's side (Over = lowest line, Under = highest, tie = better decimal payout). `snapshotMarket` saves it on the bet as `market {line, price, book, at: ODDS_TIME}` at page load, when a row is marked ✅, and when the side changes. It is only overwritten while the prop is still listed, so after kickoff it freezes at roughly the closing line. `lineValue(b)` returns points better or worse (then price if the line matches). The popup has a "Best line" column with a green/red tag and "now/last seen <time>", plus a "Line value vs market" summary card (better/worse/same and average points). New JS const `ODDS_TIME` comes from `{odds_time}`. The popup widens to 1280px while open. build_dashboard.py sha256 5411fc60…2a9f.

## V31 (2026-10-01) — "Second look" checklist, ✔/⚠ script tag, Hide ❓, build archive

Trevor said there were too many ❓ rows (100 of 590 rows with lines, versus 131 🔥/🧊).

**Backtest first.** A tiebreaker scoring hit rate, volume needed vs. had, game script (spread/total), matchup rank (only when the lean came from Edge), injuries, weather and price was run on the Week 3 pre-game board (V25 snapshot, odds 9/27 09:34, 15 games, 274 graded flagged rows):
- ❓ rows went **61-83** on their signal side. "Lean" ❓s went 13-24, toss-ups 35-42 and "pass" 13-17, so the combined score did not separate winners from losers.
- 🔥/🧊/⭐ rows went 67-63.
- Per factor, the share of cases each one called correctly: Matchup 40%, Volume 46%, Hit rate 46%, Injuries 47%, **Game script 58%**, Weather 57% (n=23).
- On ❓ rows, game script went 11-8 when it supported the lean and 7-16 when it argued against it.

Conclusion: no Lean/Pass verdict was shipped. Files are in research/second_look/ (tiebreak.js, backtest.py, bt_04d2.json).

**Shipped instead:**
- `tiebreak()` runs a factor checklist for every signalled row (`r.tiebreak`: lean, line, factors, cautions, script).
- The player card has a "Second look (context, not a pick)" section.
- The ❓ tooltip includes the checklist.
- A ✔/⚠ script tag appears in the signal column.
- A "Hide ❓ rows" checkbox (`hideReview`).
- fetch_stats.py saves spread_line/total_line in schedule_this_week, and build_games_list passes them as GAMES[].spread/.total (positive = home favored).
- run.py copies each full build to history/dashboard_<date_time>.html so later weeks can be graded.

Hashes: build_dashboard.py 17fc3bfb…6b53, fetch_stats.py 4873dcb2…d43d7, run.py ee8b6678…43d7. Applied on the Mac via patch scripts in $HOME/tb on the device VM; hashes verified.

## Week 3 personal-bet review vs. dashboard signals (2026-10-01)

Each of Trevor's 20 Week 3 bets was matched to the dashboard's pre-game signal and the second-look checklist (TNF from the 9/24 snapshot, the rest from the V25 snapshot). MNF results are now confirmed: Wicks 32 (lost O38.5), Monangai 31 (lost O39.5). Adonai did not play, so it is a void. Record: 10-9-1, with the Nix/Stafford parlay counted as one bet.

| Signal tier | Record | Bets |
|---|---|---|
| MUST BET | 3-2 | W: Love, Mooney (by 2.5), INT parlay. L: Henry (low volume), Pollard (2-game sample) |
| 🔥🔥🔥 | 3-0 | Hooper, Rodgers, Montgomery |
| 🔥🔥 | 1-2 | W: JSN. L: Wicks, Monangai |
| 🔥 | 1-1 | W: Watson. L: Stroud |
| 🧊 | 0-1 | Willis (⚠ script) |
| ❓ | 0-2 | Chase Brown, Freiermuth (each missed by 2.5) |
| No signal / against the board | 2-1 | W: Golden, London. L: Ferguson |

- **Red "hurts" injury flags: 0-2** (Stroud, with Nico Collins and Ed Ingram out; Monangai, with Caleb Williams out).
- **⚠ script: 1-1** (lost Willis, won JSN).
- **Thin samples:** every bet rested on only 2 games of data.
- **Correlation:** 5 of the wins came from ATL@GB.
- **Selection vs. the board:** Trevor's picks went 10-9, against 128-146 for the board's flagged rows overall.

## V32 (2026-10-04) — My Bets sorted by kickoff

Within each week, My Bets is now sorted by kickoff (manual bets and unknown kickoffs go last), and each bet shows "Thu 8:15 PM ET" under its name. Kickoff comes from GAMES via `kickoffForTeam(team, week)` and is only knowable for the current week's slate, so it is saved in `meta.kick` when the bet is created. `backfillBetMeta()` fills it in for this week's bets saved earlier. Past weeks' bets without a saved kickoff sort by name. build_dashboard.py sha256 4e41a67c…622b (patched on the Mac and verified).

## V33 (2026-10-05) — MUST BET matchup requirement

Per Trevor, a MUST BET now also requires the matchup to fit. For an Over, the opponent must be one of the 10 defenses allowing the most of that stat to that position (`def_rank > max - 10`, i.e. 23–32 of 32). For an Under, it must be one of the 10 allowing the least (rank ≤ 10). The constant is `MUST_BET_MATCHUP_TOP = 10`, using the same Opp Rank and selected weeks as the table. Rows that fail keep their 3-flame/ice tier.

On the Week 4 board (history/dashboard_2026-10-04_0809.html), MUST BETs went from 13 to 7. Demoted: Kyler Murray INTs O (rank 19), Ty Johnson Rush U (16), Ty Johnson Rec O (9), Emanuel Wilson Rec Yds U (12), Ryan Miller Receptions O (22), Jaylin Noel Rec Yds O (10). The current Week 5 board (odds 10/5, only 93 rows with lines so far) has no MUST BETs.

build_dashboard.py sha256 cd88b583…2a02 (patched on the Mac and verified).

## V34 (2026-10-05) — 3 flames/ice need the matchup gate and consistency

Per Trevor, any row that would reach 3 or MUST BET must also:

- pass the MUST BET matchup gate (Over: top-10 allowing; Under: top-10 limiting);
- have sample SD of the selected-week games divided by the line ≤ `MAX_TIER3_REL_SD = 0.50`. This needs 2 or more games.

Failing either caps the row at 2. The tooltip shows the swing % and the reason, and capped rows get a small ↓. New row fields: `tier_sd`, `tier_rel_sd`, `tier_cap_reason`.

Tested by swapping the Week 4 board's data (history 10/04 08:09) into the new code:

- 3-plus rows went from 59 to 10: 2 MUST BETs (Chris Moore Receptions O, C.J. Stroud INTs U) and 8 threes, mostly unders.
- Graded against Week 4 results (30 of 32 teams, MNF pending): old 3s 25-16 and MUST BETs 5-7 (combined 30-23); new 3s 5-2 and MUST BET 1-0 (combined 6-2). Rows pushed down to 2 went about 24-21.

build_dashboard.py sha256 58b0336d…e627 (patched on the Mac and verified).

## V35 (2026-10-05) — Consistency (hit-rate) signal mode, now the default

Trevor wants signals built from how consistently the player has cleared the number and how often the defense has allowed it, not how far over the line the average is.

**New columns**
- **Hit**: the player's hit rate on the chosen side vs. the best line, over the selected weeks.
- **Opp Hit**: the opponent defense's per-game allowed to that position × the player's share, vs. the same line.
- The side is chosen as whichever of Over/Under has the stronger min(P, D), with P breaking ties.

**Tiers** (`CONS_TIERS = [0.66, 0.75]`, `CONS_MIN_GAMES = 3`, `CONS_MUST_MIN_GAMES = 4`)
- 1 = both ≥ 75% but not a perfect player record.
- 2 = player perfect and defense ≥ 2/3.
- 3 = player perfect, defense ≥ 75%, and the top-10 matchup (otherwise capped at 2).
- MUST BET = both perfect, 4+ games each, plus the matchup.
- ❓ = player perfect but defense < 2/3.
- The price gate still applies.

**Mode toggle**: a "Signals" dropdown (`SIGNAL_MODE`, saved in localStorage `nfl_prop_dashboard_signal_mode`). The picky slider is disabled in consistency mode and its label shows the consistency tiers. The edge mode keeps everything from before.

**Week 4 grid** (data swapped into the new code; research/consistency/):

| Player | Defense | Record |
|---|---|---|
| 3/3 | 3/3 | 29-14 (with top-10 matchup: 11-5) |
| 3/3 | 2/3 | 14-13 |
| 3/3 | 1/3 | 16-12 |
| 3/3 | 0/3 | 8-1 |
| 2/3 | any | about 50/50 |

Consistency-mode graded results: 2 → 18-16, 3 → 9-5, ❓ → 24-13 (51-34 total). Edge mode: 1 → 36-27, 2 → 42-36, 3 → 5-2, 4 → 1-0, ❓ → 39-45.

**Week 5 board** (106 lines): MUST BETs are Bhayshul Tuten Rush O57.5 (4/4, 4/4, PHI #26) and Ted Hurst Rec O22.5 (4/4, 4/4). Purdy Rush O18.5 is P 4/4 but SEA only 2/4, so it shows ❓ (SEA's 26/game average comes from 2 big games).

build_dashboard.py sha256 90808661…0548 (patched on the Mac and verified).

## Is the consistency theory proven? (2026-10-05 check)

ROI is computed at the best available price; research/consistency/roi.py.

| Slice | Week 3 (pre-game V25 board, 2-game samples, out of sample) | Week 4 (3-game samples, tiers were tuned on this week, so in-sample) |
|---|---|---|
| Player perfect | 115-134, ROI -14.7% | 67-40, ROI +13.9% |
| Player + defense perfect | 53-54, ROI -8.7% | 29-14, ROI +21.3% |
| Consistency flames/ice | 41-42, ROI -5.3% | 27-21, ROI +5.6% |
| ❓ | 62-80 | 24-13 |
| All props (baseline) | 240-292 | 263-229 |

Pooled across both weeks:
- Player perfect: 182-174 (51%).
- Both perfect: 82-68 (55%), barely above the 52.4% break-even at -110 and not statistically meaningful.

Verdict: the theory is sound (prop lines sit near the median, and averages get skewed by one big game), but it is not proven. Re-grade each week from history/ builds (Weeks 5–7) before trusting it.

## V36 (2026-10-05) — opponent-adjusted hit rates (excused misses)

Per Trevor's idea that a miss against a team that barely does the thing shouldn't count.

**Hit**: a miss is excused if it came against one of the `EXCUSE_TOUGH_TOP = 5` toughest defenses for that position/stat (for an Under, the 5 softest).

**Opp Hit**: a miss is excused if the opposing offense's usual output is below `EXCUSE_OFF_RATIO = 0.75` × the line (for an Under, above line / 0.75).
- "Usual output" comes from `offenseUsual()`, which averages what that offense got against every other defense in the selected weeks, built from DEFENSE_LOGS plus DEFENSE_GAMES[].vs, scaled by the player's share.

**How the adjustment is applied**
- Adjusted rate = hits / (games − excused misses), used only when ≥ CONS_MIN_GAMES games remain; hits are never removed.
- Cells show e.g. `O 2/4 (2/3)`; the hover lists each game with ✔/✘/~ and the opponent context.
- Tiers use the adjusted rates.
- MUST BET still needs a raw perfect player record and, after excusals, 4+ counted defense games.

**Example**: Purdy Rush O18.5 vs SEA. SEA is O 2/4 → (2/3), because ARI's QBs average only 12, so that game is excused. Purdy moves from ❓ to 🔥🔥.

**Week 5 board**: tiers 13 / 6 / 3 / 2, with 5 ❓.

**Backtest**: no difference on Weeks 3–4, because with only 2–3 games excusing a miss leaves too few games, so it falls back to the raw rate. The adjustment only matters from Week 5 onward, so it is untested.

build_dashboard.py sha256 51f7e185…7b60 (patched on the Mac and verified).

## V37 (2026-10-05) — offense ranks in the defense popup

The defense card's game-by-game tables now put a `#N` chip next to every number: how the offense faced that week ranks at producing that stat for that position over the selected weeks (1 = produces the most).
- Ranks come from `rankOffenses(key, pos, weeks)`, built on the same `offenseGames()` data as the excused-miss logic.
- Top-8 offenses are orange and bottom-8 are blue (`OFF_RANK_EDGE = 8`).
- The hover shows the offense's average, what it got in its other games, and how far above or below that this defense held it.
- A footer row shows "Avg offense rank faced", and a legend note sits above each game table.

build_dashboard.py sha256 875c94cb…ab1d (patched on the Mac and verified).

## Scheduled alerts (2026-10-06): hourly test task

**Network access.** Trevor added `api.the-odds-api.com` and `api.open-meteo.com` to Claude's network allowlist. The Mac shell (device_bash) can now reach both; the cloud sandbox still can't. A device-side fetch_odds run used about 5 credits, with 18,334 left on the plan.

**New script `scripts/check_must_bets.py`** (on the Mac and in the cloud mirror). It loads a built dashboard.html in headless Chromium and prints the MUST BETs (`--include-threes` adds 3-tier rows, `--json` for machine output), using the dashboard's own enrichRow, so it always matches the page.

**Scheduled task** "NFL MUST BET alerts (hourly test)", `trig_01He9EXtXkBKsio1oZVPtBkU`.
- Cron `16 * 6 10 *` (UTC), so it fires hourly on Oct 6 only, from 15:16 to 23:16 UTC.
- Requires Trevor's Mac. Runs in auto mode with push notifications on.
- Each run: fetch_stats / injuries / odds / weather and build on the Mac, archive to history/, stage dashboard.html plus the script to the cloud, run the script, and reply with MUST BETs or "No MUST BETs this hour…".
- It doesn't publish anything or change code.
- Delete or replace it when moving to cloud hosting (GitHub Actions + a notification app).

**At setup**, the 14:13 UTC board had 2 MUST BETs: Bhayshul Tuten Rush O58.5 and Ted Hurst III Rec O22.5.

## V38 (2026-10-07) — the Weeks filter now drives the signals too

**Bug:** stats and ranks already followed `selectedWeeks`, but in consistency mode `CONS_MIN_GAMES = 3` meant a 2-week window (e.g. Wk 3-4) produced no signals at all.

**Fix:**
- `playedWeeksSelected(weeks)` counts the selected weeks that are already played.
- `consMinGames(weeks) = min(3, played)` now drives both the tier gate and the excused-miss adjustment.
- `consMustMinGames()` stays fixed at 4, so a short window never produces MUST BETs. Without that, 2/2 on both sides would have made 25 MUST BETs.
- The slider label (consistency mode) now reads "Signals use Wk X-Y: N played weeks", adds "small sample" under 3, and "MUST BET needs 4+".

**Week 5 board results:**
- Wk 1-5: 44 / 16 / 8 / 2, with 26 ❓. MUST BETs are Omarion Hampton Rush O37.5 and Ted Hurst Rec O20.5.
- Wk 3-4: 0 / 25 / 25 / 0, with 99 ❓.

build_dashboard.py sha256 68d11b3d…bea6 (patched on the Mac and verified).

## V39 (2026-10-07) — movable/resizable columns, picky slider removed

Per Trevor: remove the "How picky" meter, and make the main table's columns resizable and draggable.

- **Slider removed.** The `#pickySlider` input and its "How picky" label are gone. The `pickyLabel` legend stays (consistency tiers plus the "Signals use Wk…" note, or the edge-mode cutoffs). `pickyPct` stays at 20, so Average-edge mode is unchanged. The listener is null-guarded so the slider can be added back later.
- **Columns.**
  - Drag a header onto another to move it; a blue bar shows the drop side.
  - Drag the 7px handle on a header's right edge to resize it (minimum 36px; overflow shows "…").
  - Layout is saved in localStorage `nfl_prop_dashboard_cols_v1` as `{order: [original index…], widths: {index: px}}`. It is per browser, so the Mac file and the artifact are separate, and it survives rebuilds. A saved order that doesn't match the current column count resets itself.
  - "↺ Reset columns" button sits next to Hide ❓ rows.
  - How it works: render() still builds cells in the original order. `applyColumnLayout()` runs after `tbody.innerHTML` and moves the th/td nodes into the saved order. Widths come from a generated `<style>` with nth-child rules. Rows whose cell count doesn't match (message rows) are skipped. Sorting is suppressed for 150ms after a drag or resize.
- **Bug fixed in passing.** The position-button handler bound every `.pos-btn`, including My Bets, which has no `data-pos`. Clicking My Bets set `activePos` to undefined and blanked the main table. It now binds `.pos-btn[data-pos]` only.
- Verified with Playwright on the cloud build and the Mac build:
  - Dragging Hit before Player moved both the header and the cells.
  - Resizing Player from 197 to 317px resized its td too.
  - Sorting still works after a reorder.
  - All rows keep 20 cells.
  - Order and width persist across reload, and Reset restores both.
  - Edge mode still renders.
  - No console errors.
- build_dashboard.py sha256 62804157…ab17d (patched on the Mac and verified). README section added (sha e468cac3…). Artifact Version 39.

## V40 (2026-10-07) — Weeks default = played weeks; Last 2 / Last 4 buttons

Trevor asked why the Weeks filter showed "Wk 1-5" on a Week 5 board. `WEEK` is the upcoming, unplayed week, and the old default was 1..WEEK. Week 5 had no data (stats_cache weeks are 1-4), so the math was unaffected, but the label was misleading.

- **New default.** `lastNWeeks(n)` returns the n most recent played weeks, ending at `lastPlayedWeek() = max(1, WEEK-1)`. The default is `lastNWeeks(TOTAL_WEEKS)`, which gives 1..WEEK-1 ("Wk 1-4").
- **Quick buttons.** "Last 2", "Last 4" and "All played" sit next to the Weeks dropdown (`.weeks-quick`, `data-last`). The active one is highlighted when the selection matches; `sameWeekSet` does the comparison inside `updateWeeksToggleLabel`. Right now Last 4 equals All played, so both light up.
- **Rename.** The in-panel "Up to current" button is now "All played".
- These windows are week-based, not per-player game counts, so a team with a bye in the window has one fewer game. Not persisted, same as before.
- Verified with Playwright on the cloud build and the Mac build:
  - The default shows "Wk 1-4".
  - Last 2 gives Wk 3-4, the Avg header reads "Avg (Wk 3-4)", the panel checkboxes show only 3 and 4, and the signal note says "small sample".
  - Last 4 and All played both return Wk 1-4.
  - No console errors.
- build_dashboard.py sha256 d53dd849…bf96 (patched on the Mac and verified). README section added. Artifact Version 40.

## V41 (2026-10-07) — 🎬 Game script analysis (panel + popup)

Per Trevor: a game script analysis per game (spread, O/U, weather, injuries, anything else), shown under the Stat row when a game is filtered, and as a popup linked from each bet line.

**Data added**
- `fetch_stats.py` (sha aec94f7b…) now saves:
  - `schedule_this_week`: also away/home rest, div_game, moneylines and surface.
  - `team_results`: every finished regular-season game, with week, teams, scores, closing spread/total and overtime.
- `build_dashboard.py` passes three things to the page:
  - `GAMES[]`: now also rest, `div_game`, `away_ml`/`home_ml` and `weather`, the home stadium's `weather_cache` entry.
  - `TEAM_RESULTS`.
  - `INJ_BY_TEAM`: the injuries cache `by_team`.

**Analysis** (`gameScript(key)`; team stats follow the Weeks filter, played weeks only)
- **Headline.** Spread ≥ 7 is "lopsided", 3.5–6.5 is "lean", under 3.5 is "coin flip". The total is compared with this season's average closing total: ±3.5 makes it high or low scoring.
- **Lines.** Implied team totals, and win probability from no-vig moneylines (normal approximation, SD 13.5, as a fallback).
- **Flow text.**
  - Favorite runs late; the underdog throws more, scrambles more and carries more INT risk (from the INT study).
  - Pass-heavy or run-heavy teams (±5 points of pass rate versus the league).
  - Scoring check: points for averaged with the opponent's points allowed, versus the total.
- **Props list**, rule-based: underdog pass volume and INT Overs, favorite RB carries Overs, favorite QB attempts Unders, high/low total, implied team total ≥ 27 or ≤ 17, bad weather, and a scoring-check gap of 4+ points.
- **Matchups.** Offense rank (`rankOffenses`) against defense rank (`rankDefenses`) for QB passing yards and RB rushing yards. "Strength on weakness" means a top-10 offense against a bottom-10 defense; the mirror case is flagged too, along with a top-5 or bottom-5 defense.
- **Weather.** Wind ≥ 20 or 15–19 mph, temperature ≤ 25°F, rain or snow or ≥ 50% precipitation; domes are neutral.
- **Situation.** Rest (short week, a rest edge of 3+ days, coming off a bye) and divisional games.
- **Injuries.** 40%+ snap players, with a note per position group. QB is firm at Q or worse; a missed practice alone gets "watch". The note lists 2+ OL, and names who absorbs WR/TE targets and RB carries, by average over the selected weeks. CB/S, EDGE/DI and LB absences count as a boost for the opponent.
- **Team profile table.** Record, ATS, O/U, PF/PA, margin, pass attempts, QB pass yds and RB rush yds with ranks, QB rush yds, pass rate, defense ranks, coverage and rest. Then each team's game results.
- **Board.** Signalled rows in the game (signal, ✔/⚠ script tag, mark), plus Trevor's ✅ bets for the current week.

**UI**
- `#gameScriptPanel` is a collapsible `<details>`. Its open/closed state survives re-renders.
- 🎬 `.gs-link` appears in every main-table Opp cell, in the player-card meta line, and in My Bets for current-week bets (with a "← Back to My Bets" button).
- `.gs-player` names open the player card.

**Verification**
- Every one of the 15 games' HTML builds without errors.
- TB and DAL records, ATS and O/U were hand-checked from raw `team_results`: TB 0-4, ATS 0-3-1, O/U 2-2; DAL 2-2, ATS 2-1-1, O/U 4-0.
- The panel shows when a game is filtered (94 rows for TB@DAL), and stays collapsed through a re-render.
- The row link opens the popup. The player link inside it opens the player card, which has its own script link. The My Bets link opens the popup, the bet appears under "Your bets", and Back returns to My Bets.
- No console errors, on both the cloud build and the Mac build.

**Note:** on Wednesday only DAL and TB had injury reports, because of Thursday night; the other teams fill in once `run.py` runs after their reports.

build_dashboard.py sha256 11d1fc5e…b3a8, patched on the Mac and verified. README section added (353ee7f1…). Artifact Version 41.

## Monday Night board (2026-10-12)

**Problem.** Trevor noticed that on Monday the dashboard had already moved to Week 6 while Week 5's Monday Night game (BUF @ LA) was still to be played. The cause is `current_week()`, which picks the first week with at least 50% of its games still ahead.

**What changed**
- `fetch_stats.py` (067fde7e…) now saves `prev_week_open`: the previous week's games whose ET kickoff is still in the future (`_not_started()`, using zoneinfo America/New_York).
- When environment variable `NFL_WEEK_OVERRIDE` is set, `fetch_stats.py` forces that week. When `NFL_UPCOMING_ONLY=1` is also set, it keeps only games that haven't started.
- All `fetch_*.py` scripts and `build_dashboard.py` read `NFL_DATA_DIR`, which defaults to `data/`.
- `build_dashboard.py` (1f808042…) reads `NFL_OUTPUT_NAME` and draws `{board_switch_html}` in the header from `NFL_ALT_LINK="file|label"` and `NFL_BOARD_BADGE`.
- `run.py` (db78fd89…): when `prev_week_open` exists and `--no-mnf` isn't passed, it:
  1. copies the coverage cache into `data_mnf/`;
  2. runs stats, injuries, odds and weather with the override;
  3. builds `output/dashboard_mnf.html`, with a badge and a "Back to the full board" link;
  4. builds the main board with a "🌙 Monday Night: … (Week N)" button;
  5. saves a history copy as `*_mnf.html`.

**Verification**
- Full pipeline in the cloud: main board 1,674 rows (Week 6), MNF board 119 rows (Week 5, BUF@LA only). Both link to each other, with no console errors.
- On the Mac: patches applied, all 7 hashes matched the cloud. The MNF board was built from Mac data with 47 lines from 17 players, using about 5 odds credits. No MUST BET or 3-tier rows.

**Not changed**
- The scheduled MUST BET alert still checks only the main board.
- The shared artifact is only the main board, so the MNF button there would be a dead link.

## Defense card: this week's opponent (2026-10-12)

Trevor asked that the defense card show the offense the defense plays this week, alongside the ranks of the offenses it has already faced.

**Code**
- New helpers `upcomingOpponent(team)` (looks up GAMES) and `upcomingOffCell(key, pos, label, off)`, which returns the offense's per-game average plus a `#rank` chip from `rankOffenses`, using the same orange/blue edges and a tooltip.
- **Summary table:** new column "This week: <OPP> offense".
- **Game-by-game table:** new highlighted first row (`.upcoming-row`), "This week vs <OPP> (their avg)".
- Teams on a bye get neither the row nor the column.

**Verified**
- DEN vs SEA: column and row render; SEA pass yds 235.4 (#16), rush yds 5.8 (#27), etc.
- Bye team (CIN) shows no row.
- No console errors.

**Release**
- build_dashboard.py sha 5157c180…, patched on the Mac and verified. Both boards rebuilt there.
- The shared artifact (Version 43) is now built from a separate `output/dashboard_share.html` without the Monday Night button, since that link only works locally. Built with `NFL_OUTPUT_NAME=dashboard_share.html python3 build_dashboard.py`; `extract_share.py` points at it.
- README updated (34819ad6…).

## Hosting on a website (in progress, 2026-10-15)

Trevor chose GitHub Pages (public link), with a refresh every 3 hours from 8am to 8pm Mountain. That's about 5 runs/day × ~150 Odds API credits (10 markets × ~15 games), roughly 22k credits/month against a 20k plan. He was told this before choosing.

**Repo** (prepared in the cloud at /mnt/user-data/outputs/gambling_program_hosted; nothing pushed yet):
- The project's `.py` files and `scripts/check_must_bets.py`.
- `fetch_odds.py` reads `ODDS_API_KEY` from the environment first, falling back to the config file.
- New quota guard: `ODDS_MIN_REMAINING` (500 in the workflow). If the credits left drop below it, the props pull is skipped and the last cached lines are kept.
- `requirements.txt` (pandas, requests, lxml).
- `.gitignore` excludes `config/` (the key), `data/`, `output/`, `history/`.
- New `scripts/notify.py`: pushes new MUST BET / 3-star picks to ntfy, and only picks not already sent (state kept in `data/last_alert.json`).

**Workflow** (`.github/workflows/update.yml`):
- Runs on cron `7 2,14,17,20,23 * * *` (UTC) plus manual dispatch, with `TZ=America/Denver`.
- Restores and saves `data/` through `actions/cache`, then runs `run.py`, so the Monday Night board is included.
- Builds `site/`: `index.html`, plus `dashboard_mnf.html` when it's linked.
- Sends the ntfy alert when the `NTFY_TOPIC` secret is set.
- Uploads each build as a 90-day artifact, which replaces `history/`.
- Deploys with `actions/deploy-pages`.

**Dry run** in a clean cloud copy (odds and weather skipped because the cloud is blocked): 1,679 rows, no page errors; the coverage scrape failed gracefully.

**Waiting on Trevor:**
1. Connect GitHub to Claude.
2. Then I create the public repo, push, and enable Pages (build_type workflow).
3. Trevor adds the `ODDS_API_KEY` secret himself, so the key never passes through chat.
4. Optional: install ntfy and add the `NTFY_TOPIC` secret.

## Push trigger + Supabase sign-in sync (2026-10-16)

**Push trigger:** `update.yml` now also runs on every push to `main`, skipping pushes that only touch `docs/**` or Markdown files.

**Sign-in so marks/bets sync across devices** (the plan in CLAUDE.md):
- New "Sign in to sync" control next to My Bets. Email magic link through Supabase; supabase-js 2.45.4 UMD loads from jsDelivr only when the config is set.
- Config: `SUPABASE_URL` / `SUPABASE_ANON_KEY` at the top of `build_dashboard.py` (env vars override). Blank means no sign-in, and the page behaves exactly as before.
- Signed out, nothing changes. Signed in, `saveMarks()` / `saveBets()` also sync (1.5 s debounce), and the page syncs on load and when the tab comes back into view.
- The merge is three-way against the last copy this browser synced, so deletes carry over and edits from two devices to different bets both survive. First sign-in on a device adds its local data to the account and deletes nothing.
- Writes only go through if the row's `updated_at` hasn't changed since it was read; otherwise the page re-reads and re-merges (up to 4 tries).
- Re-renders after a sync wait until you leave a bet-slip box, so typing isn't interrupted.
- Sign out keeps this device's data and stops syncing. Backup/Restore is unchanged.
- Hidden on the Mac's file:// copy, since the emailed link can only open the shared site.

**Tested** headless against a fake Supabase backend with two simulated devices: merging on first sign-in, cross-device add, delete carrying over while the other device edits at the same moment, reload with no extra writes, sign-out. Also tested the real supabase-js library loading and sending the sign-in email request, the expired-link message, and that the unconfigured build has no page errors and no sign-in button. Not yet tested against a real Supabase project.

## Default weeks = Last 4 (2026-10-16)

Trevor: "make it so that the default view is last 4 games not all games ... and make that what the notifications send". `selectedWeeks` now starts as `lastNWeeks(DEFAULT_LAST_WEEKS)` (4) instead of every played week. `check_must_bets.py` / `notify.py` read the page's default `selectedWeeks`, so alerts follow it with no change of their own. "All played" is still one click away. MUST BET's 4-game minimum was not changed: a player or defense with a bye (or a missed game) in the 4-week window has 3 games and can reach 3-star at most.

## Alerts: NEW + WATCHING sections (2026-10-16)

Trevor: "a NEW section and then a watching section ... new should be something I haven't seen yet. Watching should take anything I have listed that way and just show me the list and if the odds moved".

- `check_must_bets.py --watch-file keys.json` also returns each listed mark key on the board, with the side the page leans (`cons.side` or `direction`) and `bestMarketFor()` line/price/book. Picks now carry `key` (`markKey`).
- `notify.py` sends one push:
  - **NEW:** not sent before, and not marked bet/watch/pass in his account.
  - **WATCHING:** all 🌕 rows on the current board(s), moved rows first, "moved from X" measured against the line when alerts first saw the row on the watch list (`watch_base`).
- It buzzes only on a NEW pick or a watched move since the last alert (`watch_last`): any line change, or price ≥10 cents (`PRICE_MOVE_CENTS`). Small wiggles stay quiet and add up until they cross that.
- The watch list comes from Supabase via the admin API (look up the user by `ALERT_EMAIL`, read `user_state.marks`) with the `SUPABASE_SERVICE_KEY` Actions secret. Without it, the WATCHING section is skipped and NEW works as before.
- Tested with simulated refreshes: marked pick excluded, 5-cent wiggle quiet, line move buzzes, repeat quiet, no-account fallback.

## Alerts for everyone who signs in (2026-10-16)

Trevor: "i want the others to get the alerts when they sign in".

- **Page:** signed in, a "🔔 Alerts" button next to Sign out opens a topic box, suggesting a random `nfl-props-xxxxxxxxxx` name, with Save and Send test. Send test posts straight to ntfy.sh from the browser. The topic is saved in a new `public.alert_prefs` table (RLS: own row only; SQL in CLAUDE.md). If the table is missing, the box says alerts aren't set up yet.
- **notify.py:** recipients are everyone in `alert_prefs` with a topic, plus `NTFY_TOPIC` for the `ALERT_EMAIL` account (a topic saved on the site wins). Duplicate topics are only sent once. The board is checked once, with the union of everyone's watch keys, then each person gets their own NEW (never sent to them, not marked by them) and WATCHING. Per-user state lives in `last_alert.json` → `users`; the old single-user state carries over to Trevor.
- **Workflow:** the alert step now runs if `NTFY_TOPIC` or `SUPABASE_SERVICE_KEY` is set.
- **Tested:** simulated multi-person refreshes (a friend gets a pick Trevor was already sent; a friend's pass excluded; only the friend buzzed on their line move; old state carried over; duplicate topic deduped) and the Alerts box headlessly (suggest, validate, test send, save, load, clear, missing table). Two-device sync tests still pass.
- ntfy.sh's free tier caps messages per day per sender IP (around 250), which is plenty for a handful of people at ≤5 refreshes a day.

## One-tap Refresh lines (2026-10-16)

Trevor: "can i put a button in the dashboard to refresh the lines also?", then "let's do true one tap". He didn't say who should be able to use it, so it's restricted to an `ALLOWED_EMAILS` list (just him) to protect Odds API credits; adding friends means adding their email to that secret.

- New Supabase Edge Function `supabase/functions/refresh-lines/index.ts`. It verifies the caller's Supabase session and email, reads the latest `update.yml` run (GET), or dispatches one on `main` (POST, refused while a run is queued or in progress). CORS is limited to trevorrancourt.github.io. Secrets: `GH_TOKEN`, `ALLOWED_EMAILS`.
- Page: `#refreshCtl` in the signed-in control, showing "🔄 Refresh lines" and "Lines Xm old". While a refresh runs it polls every 20 s, then shows "✅ New lines ready · Reload" or a failure note, with a 15-minute timeout. Hidden when the function is missing or the user isn't allowed. `ODDS_TIME_UTC` is the odds pull time converted to UTC at build time (`odds_time_utc()`).
- Tested headlessly against a simulated function: not deployed or not allowed → hidden; already running → follows it; tap → running → done → reload; refused POST → message. Sync tests still pass. The function itself was not run here (no Deno/Supabase access from the cloud session).

## Role changes block MUST BET (2026-10-16)

Trevor: "tre tucker is a perfect must bet this week ... xavier hutchinson and jalen brooks shouldn't be though. they are both a part of a trade ... marvin harrison jr was traded from cardinals to texans ... i don't want that variability in must bets ... like lines that are a result of injuries, trade, personnel issues". He picked: cap at 3-star + ⚠️ tag, a 2-game window after a trade, and a manual flag too.

- **Trades:** `fetch_stats.detect_trades()` compares nflverse's season roster (`rosters/roster_{season}.csv`, latest team per gsis_id) with each player's game log. The roster already showed MHJ on HOU while all his games were for ARI.
  - The traded player's `team` moves to the new club, so his rows show this week's real opponent (previously they'd have shown ARI's).
  - Each trade records `from_games_since` (old team's games after his last one), `to_games_since` (his own games for the new team), `to_team_games_since`, and `old_role` (per-game targets/carries/pass yds with the old team).
  - `compute_trade_flags()` flags him plus `TRADE_ROLE_GROUPS` teammates (WR/TE→WR+TE, RB→RB, QB→QB+WR+TE) on each side until that side reaches `TRADE_SETTLE_GAMES` = 2. A no-show stops flagging after `TRADE_MAX_WAIT_GAMES` = 4 team games.
  - `trade_had_role()` skips depth players (WR/TE <3 targets/g, RB <6 touches/g, QB <100 pass yds/g). Without that, Xavier Smith's move (0.3 targets/g) flagged Kittle, Evans and every other SF receiver.
  - The local test build found 5 team changes this season; only MHJ cleared the role bar, so only ARI and HOU WR/TE rows were flagged.
- **Injuries:** `roleChangeReasons()` adds strong own-team 🩹 entries (QB/RB/WR/TE, severity ≥3 = Out/Doubtful, 50%+ snaps). There were none in the local data yet (Friday designations), so this was tested with a simulated injury.
- **Manual:** the player popup has "⚠️ Flag role change" (undo), stored as `MARKS['role|WEEK|player|team'] = 'flux'`, so it syncs. notify.py's `apply_own_flags()` applies each person's own flags to their alert.
- **Effect:** in `enrichRow`, a level 4 with any role change becomes 3 (`role_capped`). `roleTag()` adds ⚠️ with the reasons to any signalled row. check_must_bets passes `roleChange`, and alert lines get "· ⚠️ role change".
- **Tested:** with every line forced to 0.5 there were 167 MUST BETs and 0 with a role change; 16 rows were held at 3 with the tag; the simulated injury capped its row; the manual flag on/off removed and restored the MUST BET and saved the mark; alert flags only affect their owner. Sync and multi-person alert tests still pass.

## Excused misses: top 5 → top 10 (2026-10-16)

Trevor, looking at Javonte Williams Rec Yds O 14.5 (3/4, the only miss vs #1 BAL): "maybe like we could do it where it's less rigid than top 5, maybe make it top 10 on either side". `EXCUSE_TOUGH_TOP` 5 → 10: a player's miss against one of the 10 toughest defenses for that stat (Over), or one of the 10 softest (Under), no longer counts against his Hit rate. Unchanged: hits are never removed, the adjustment needs 3+ games left (`CONS_MIN_GAMES`), and MUST BET still needs a raw perfect record. Hover text now says "one of the 10 toughest/softest matchups". (His row was already 🔥🔥🔥 under top 5 in a local rerun, since BAL is #1.)

## RB injuries by carry share + injury heads-up; "cheap hits" held back (2026-10-16)

Trevor on D'Andre Swift Rush Yds Under (🧊🧊🧊 at ~60.5 vs ATL): (A) "kyle monangai was injured and it doesn't show that"; (B) "atlanta has been good against bad run teams and bad against good run teams ... why would swift be an under".

- **(A) Why Monangai didn't show:** he's "Missed practice" (thumb, severity 1, no game designation), and at 40.5% snaps he failed `IMPACT_SNAP_PCT` (50%), although he had 10/10/10/30 carries. Two fixes shipped:
  - `rb_carry_shares()` / `injured_has_role()`: an RB with 25%+ of his team's RB carries in the games he played (`RB_CARRY_SHARE_ROLE`, Trevor: "as high as 25% counts") is a real role. Monangai is 45%. The 🩹 hover now shows "% of RB carries".
  - `roleSoftReasons()`: a real-role own-team QB/RB/WR/TE who is Questionable or missed practice shows as a faded ⚠️ "Heads-up (not blocking)" in the hover, also on MUST BET. Out/Doubtful still blocks MUST BET.
  - Not built: bumping the player's share when a teammate is out. Trevor: "what about like other backs filling that role?" Instead, the ⚠️ role change covers it once the teammate is Out/Doubtful.
- **(B) Why ATL looked like an Under defense:** at 60.5 scaled to Swift's 48% share, ATL "held" NO (usually 34), GB (34) and CAR (54) and allowed 85 to BAL. The excused-miss rule only removes misses, never "cheap hits" vs offenses that wouldn't reach the line anyway. Also, the new top-10 excuse removed Swift's 84 vs PHI (#24 soft).
  - Built and tested, **not shipped:** a "cheap hit" (defense-side hit where the offense's usual is under 75% of the line for an Under, or 1.33x+ for an Over) doesn't count; too few real tests left means no rate, so no signal. Swift lost the 🧊 as intended.
  - Board-wide, with every line at the player's median (Wk 2-5), tiers [none,1,2,3,MUST] went from [1197,125,209,101,40] to [1576,25,51,19,1]. At 0.6: [1493,52,88,38,1]. At 0.5: [1450,69,104,48,1].
  - MUST BET collapses because it needs 4 real defense tests inside a 4-week window. With MUST BET needing 3 real tests instead: 0.6 gives [..,35,4], 0.5 gives [..,44,5].
  - Held for Trevor's decision on how strict to be.

## Matchup mismatch: picks become ❓ (2026-10-16)

Trevor, after the cheap-hits numbers: "do you think using actual yards vs just their ranking is the best move?", then "atlanta allows a lot of yards to good run offenses and holds bad ones in check. don't tell me to go under when chicago is a huge run offense". He agreed to sort offenses by rank and compare against this week's opponent, as a ❓ rather than removing games.

- `matchupMismatch(r, cons, weeks)` runs in Consistency mode after the tier is set (only when lvl > 0). It uses `rankOffenses()`, the existing defense-popup ranking: each offense's per-game production of this pos+stat in the selected weeks, 1 = most.
  - **Under:** when `r.team` is top-`MISMATCH_OFF_TOP` (10), every top-half offense the defense faced must have been held under the line. If any got over, or there were none, then lvl = 0 and it becomes ❓ with the reason.
  - **Over:** mirrored for a bottom-10 offense vs the defense's bottom-half opponents.
- The ❓ hover reads, e.g.: "Matchup: CHI is the #4 RB Rush Yds offense. ATL vs top-half offenses held CAR #14 31.9, allowed BAL #5 84.5; vs weaker offenses held NO #29 24.2, GB #31 8.2 (scaled to his share). Would have been under 60.5 (he's 3/4, ATL 3/4), so it's a ❓ instead of a pick."
- First draft redeclared `_offRankCache` (already used by `rankOffenses`), which would have blanked the page. The headless check caught it, and the draft was switched to reuse `rankOffenses`.
- **Effect:** Wk 2-5, lines at each player's median (all Unders): 56 of 475 picks → ❓. Tiers [none,1,2,3,MUST] went [1197,125,209,101,40] → [1253,101,186,92,40]; MUST BETs unaffected, since they already need the defense perfect. Lines at each player's 25th percentile (Overs): 27 of 597 → ❓.

### Fix: judge "held" vs the offense's usual, not the scaled line (2026-10-16)

Trevor on Swift Rush Attempts: "chi is #2. baltimore was #5 and did 28 against atl ... why would this still be an under". The check had used the share-scaled values vs the line: BAL's 28 attempts × Swift's 50% share = 14.1, under the line, so ATL "held" BAL. But BAL usually gets 24.3, so ATL didn't stop them.

Now `matchupMismatch()` compares the raw team value with that offense's usual from its other games (`g.val / share` vs `g.usual / share`). "Held" means ≤ usual; for Overs, "gave it up" means ≥ usual. If an offense has no other games, it falls back to the line result. The reason text shows raw numbers with "(usually X)", matching the defense popup.

- Swift Rush Att at 16.5/17.5 → ❓ ("allowed BAL #5 28 (usually 24.3)"). Rush Yds → ❓ ("allowed BAL #5 175 (usually 90.7)").
- Sim (Wk 2-5, lines at median): 127 picks → ❓ (was 56); tiers [none,1,2,3,MUST] [1324,84,142,83,39]. Lines at 25th pct: 118 → ❓.

## Player popup: "This week" + "His avg" rows (2026-10-16)

Trevor: "on their game by game section, show their current week opponent and averages and stuff similar to how you did that on the defense popups". The player popup's Game-by-game table now has:
- **Top row** (`upcoming-row`, same style as the defense popup): "This week @OPP (they allow to all RBs)". For each stat it shows the opponent's per-game allowed to the position (`def_avg_allowed`), its rank chip (`oppRankChip`, 1 = toughest), and the current best line.
- **"His avg (N games)" row** above "Avg opp rank faced", averaged over the played games shown (DNP weeks excluded).
- Same day, per Trevor ("add target share and projected yards to that"): each "This week" cell now also shows "X% share · proj Y", from the row's Team Share (`r.share`: his cut of his team's production at his position for that stat) and Anticipated (`r.anticipated` = share × what they allow). Shares are within his position group (e.g. Swift's 57.7% Targets share is of CHI's RB targets, not all team targets).

## Faster injuries: ESPN feed (2026-10-16)

Trevor: "jeremiyah love is out this week and tyler allgeier is a must bet under", then (offered four fixes) "i think we just need faster injury updates".

- **Why it was missed:** nflverse's Week 6 report only had Love as "Did Not Participate In Practice" with no game designation (those come with the Friday report, and nflverse posts later), so he was "Missed practice", severity 1, a non-blocking heads-up. He's ARI's lead back (64% of RB carries), and every Allgeier game in the sample is as the backup.
- **Fix:** `fetch_injuries.py` now merges ESPN's public injury feed (`site.api.espn.com/apis/site/v2/sports/football/nfl/injuries`) after the nflverse report.
  - Matching: ESPN athlete id (from `athlete.id` or the `/id/N/` link) via players.csv `espn_id`, else normalized name + team (`FULL_TO_ABBR` on the team block name).
  - Status: ESPN_STATUS maps Injured Reserve/PUP/suspension → Out, Day-To-Day → Questionable. The more severe of nflverse/ESPN wins; ESPN entries get `source: "espn"` and its `shortComment` as `note`.
  - Guard: ESPN-only entries for players with no game in the last two played weeks are skipped, so long-term IR doesn't flag teammates forever.
  - The cache records `espn` (bool) and `generated_at_utc`. The board header shows "Injuries: ESPN news + NFL report (or NFL report only), updated <local time>". The ⛑️ and 🩹 hovers say "ESPN injury news: <note>" / "[ESPN]".
- **Not testable live from the cloud session** (ESPN host blocked there; GitHub Actions can reach it). Tested:
  - The blocked path: the build continues and the header says "NFL report only".
  - A fixture shaped like ESPN's response:
    - Love matched by link id → Out with note.
    - Monangai matched by name → Questionable.
    - A long-gone IR player skipped.
  - With that, Allgeier Rush Yds Under went MUST BET → 🧊🧊🧊 with ⚠️ "Jeremiyah Love (RB) is Out". Direction-aware ❓ (no Under at all when the lead back is out) was offered but not requested.

## Filter checkboxes survive reload (2026-10-16)

Trevor: "whenever i reload the page, hide x rows is checked but the x still show up". The browser restored the checkbox tick on reload while `hideMarkedX` (and the other filter variables) started false. Now Hide ❌, Hide ❓, Ladder only, Weak matchup only and Strong matchup only are saved in localStorage (`nfl_prop_dashboard_filters_v1`) and synced from the box before the first render. Tested headlessly: tick → reload keeps rows hidden; untick → reload shows them.
