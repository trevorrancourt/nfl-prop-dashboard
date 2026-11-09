# NFL Player Prop Dashboard: notes for Claude

Read this first in every session. The full build history (every version, decision and backtest) is in `docs/HISTORY.md`. Search it before re-deciding anything.

## Who / what
- Owner: Trevor (trevorrancourt). He bets NFL player props and uses this dashboard to find them. He isn't a developer: explain in plain words, keep steps short, and do the work yourself.
- Live site: https://trevorrancourt.github.io/nfl-prop-dashboard/ (GitHub Pages, public link).
- `.github/workflows/update.yml` rebuilds the site every 3 hours, 8am-8pm Mountain (cron in UTC), on every push to `main` (except docs/Markdown-only pushes), plus "Run workflow" on demand.
- A copy of the project also lives on his Mac (`~/Documents/Gambling Program`), where `python3 run.py` builds `output/dashboard.html` locally. The repo is now the source of truth.

## How it works
`run.py` runs these in order, then builds the page:
1. `fetch_stats.py`: nflverse schedule, weekly stats, snap counts and finished-game results → `data/stats_cache.json`. It picks the current week and backfills zero-stat weeks.
2. `fetch_injuries.py`: nflverse injury report, with a practice-report fallback and snap shares, plus ESPN's public injury feed merged on top (2026-10-16, for speed).
   - The more severe status wins (IR/PUP/suspension → Out). Joined via players.csv `espn_id`, else name + team.
   - ESPN-only entries for players who didn't play in the last 2 weeks are skipped (old absences).
   - If ESPN is unreachable, the build continues with the NFL report alone. The board header says which ("Injuries: ESPN news + NFL report, updated …").
   - The cloud session can't reach ESPN; only GitHub Actions can.
3. `fetch_odds.py`: The Odds API player props from DK/FD/BetMGM.
   - The key comes from the `ODDS_API_KEY` env/secret; on the Mac it falls back to `config/odds_api_key.txt`.
   - About 9 credits per game, about 127 per full run, on a 20k/month plan.
   - `ODDS_MIN_REMAINING` is a quota guard: below that, it skips the pull and keeps the cached lines.
4. `fetch_weather.py`: Open-Meteo forecasts. Optional; it must never block the build.
5. `fetch_coverage.py`: Sharp Football man/zone scrape. Optional.
6. `build_dashboard.py`: odds join to players by `normalize_name`, with a fallback (2026-11-06, per Trevor: "Nate B from Jacksonville has a line and it isn't coming in") on first initial + last name when exactly one odds name fits (`odds_for_player`). A player with a posted line always gets rows, even under `RELEVANCE_FILTER`. Each Actions build posts an "Odds names" notice: how many players with lines matched, and the odds names that didn't make the board.
   `build_dashboard.py` itself: one large `HTML_TEMPLATE` (Python `str.format`) holding all the JS/CSS, writing `output/dashboard.html`.
   - Data is baked in as JS constants: `ROWS`, `DEFENSE_LOGS`, `DEFENSE_GAMES`, `GAMES`, `TEAM_RESULTS`, `INJ_BY_TEAM`, `COVERAGE`, `WEEK`, `SEASON`, `ODDS_TIME`.

**Monday Night board:** when the previous week still has an un-kicked-off game, `run.py` also builds `output/dashboard_mnf.html` from `data_mnf/`, using these env vars:
- `NFL_DATA_DIR`
- `NFL_WEEK_OVERRIDE`
- `NFL_UPCOMING_ONLY`
- `NFL_OUTPUT_NAME`
- `NFL_ALT_LINK`
- `NFL_BOARD_BADGE`

The two boards link to each other.

**Phone alerts:** `scripts/check_must_bets.py` reads a built page headlessly (Playwright) and lists MUST BET / 3-star rows, plus (with `--watch-file`) the current best line/price of given mark keys. `scripts/notify.py` sends one ntfy push when the `NTFY_TOPIC` secret is set, with two sections (2026-10-16, per Trevor):
- **NEW:** picks never sent before and not already marked by him.
- **WATCHING:** every 🌕 row on this week's board, with its line/price and the move since alerts first saw it watched.

It only buzzes on a NEW pick or a watched move (any line change, or 10+ cents of price, measured from the last alert).

**Per person:** anyone signed in can save their own ntfy topic under "🔔 Alerts" next to Sign out, stored in `public.alert_prefs`. Each person gets their own alert from their own marks, with per-user state in `data/last_alert.json` → `users`. Trevor's `NTFY_TOPIC` secret maps to the `ALERT_EMAIL` account. Accounts are read with the `SUPABASE_SERVICE_KEY` secret, which goes in Actions secrets only, never in the page; without it, only `NTFY_TOPIC` gets alerts, NEW section only. The `alert_prefs` SQL:
  ```sql
  create table public.alert_prefs (
    user_id uuid primary key references auth.users on delete cascade,
    ntfy_topic text,
    updated_at timestamptz not null default now()
  );
  alter table public.alert_prefs enable row level security;
  create policy "read own"   on public.alert_prefs for select using (auth.uid() = user_id);
  create policy "insert own" on public.alert_prefs for insert with check (auth.uid() = user_id);
  create policy "update own" on public.alert_prefs for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
  ```

**Refresh lines button (one tap, 2026-10-16):** signed-in users on the allow list see "🔄 Refresh lines" plus "Lines Xm old" (`ODDS_TIME_UTC`). It calls the Supabase Edge Function `refresh-lines` (source in `supabase/functions/refresh-lines/index.ts`, deployed by pasting into the Supabase dashboard editor). The function checks the user's email against its `ALLOWED_EMAILS` secret, then starts `update.yml` with its `GH_TOKEN` secret (fine-grained token: this repo only, Actions read/write). It won't start a second run while one is going, and the page polls until the run finishes. Without the function deployed, the button stays hidden. Each tap costs about 130 Odds API credits.

**Look back on a week (2026-11-03, per Trevor):** `.github/workflows/lookback.yml` is manual only ("Run workflow", optional week; blank = last finished week) and pulls no odds. It downloads the `board-*` artifacts from the last 14 days, and for each game takes the last board built before kickoff. It drops that board's data consts into the current page code (`scripts/lookback.py`), then grades every row against nflverse box scores. Output goes to run annotations titled "Look back N" (readable via the check-runs annotations API) and the step summary: group W-L, would-be 3-star/MUST rows by blocking rule (from `r.lookback` in enrichRow: `raw` level, `capped`, `mismatch`, `priced`, `blowout`, `role`), 💡/❓ by reason, and Win % edge buckets.

## Editing `build_dashboard.py`: gotchas that have bitten before
- `HTML_TEMPLATE` goes through `.format()`, so every JS/CSS brace must be doubled: `{{ }}`. Template literals become `${{x}}`.
- It's a normal (not raw) Python string, so in JS `'\n'` write `'\\n'`, and avoid `\'` (use the other quote style).
- After any change: build, then load the page headlessly and check for `pageerror`. One syntax error blanks the whole page.

## Signal logic: Trevor's rules, don't loosen without asking
- **📜 My rules** (button next to My Bets, `myRulesHtml()`) lists every rule below in plain English, using the live constants. **Whenever a rule is added or changed, update `myRulesHtml()` too.**
- **Default signal mode is "Consistency (hit rates)".** "Average edge" is the old formula, still selectable.
  - The choice is saved in localStorage `nfl_prop_dashboard_signal_mode`.
  - If Trevor says signals "disappeared", check this first.
- **Three groups only (2026-10-16, per Trevor: "bet the must bets, review the three stars and then like have everything else"):** ⭐ MUST BET, 🔥🔥🔥/🧊🧊🧊, and ❓. Rows that compute to 1 or 2 are shown as ❓ with "Would have been 🔥🔥 …" (`demoteWhy` in enrichRow). The underlying tiers:
  - **💡** (2026-10-16, per Trevor) sits between 3-star and ❓: a ❓ that would have been a 2-star, or whose 🎬 game script supports its side (`ideaReason`, `signal_rank` 5). Never for role-change or matchup-mismatch ❓s. "Hide ❓ rows" keeps 💡.
  - 1 = player and defense both ≥75% but player not perfect (→ ❓).
  - 2 = player perfect and defense ≥2/3 (→ ❓).
  - 3 = player perfect, defense ≥75%, and a top-10 matchup (otherwise capped at 2).
  - ⭐ MUST BET (**reworked 2026-11-09**, per Trevor after a 1-4 run: "i basically want to be notified whenever there is a true must bet") = **two separate signals agree on the same side** (`mustWhy` / `r.must_pick` in enrichRow): a streak 3-star, 🎯 line looks low/high (`outlierValue`), and a 🪜 Ladder board pick (Overs). It also needs no role/blowout/mismatch flag and a price of -130 or better. The old "both sides perfect, 4+ games, top-10 matchup" is now just a 3-star (those rows went 13-11 in Weeks 7-9). Alerts use `must_pick`'s side/line/price.
  - Price gate: worse than -130 blocks a signal.
- **Excused misses:**
  - A player's miss doesn't count against a top-10 tough defense (top-10 soft for an Under; `EXCUSE_TOUGH_TOP`, raised from 5 on 2026-10-16 per Trevor).
  - A defense's miss doesn't count against an offense whose usual output is under 0.75× the line.
  - The adjusted rate applies only if enough games remain.
- **Matchup mismatch → ❓, not a pick** (2026-10-16, per Trevor: "atlanta allows a lot of yards to good run offenses and holds bad ones in check. don't tell me to go under when chicago is a huge run offense"). `matchupMismatch()` uses `rankOffenses()` (same ranks as the defense popup, 1 = produces the most).
  - **Under:** if this week's offense is top-10 (`MISMATCH_OFF_TOP`), the defense must have held every top-half offense it faced **at or below that offense's usual output** (raw team numbers, not scaled to the player's share, not vs the line), or it's ❓.
  - **Over:** the mirror, for a bottom-10 offense: the defense must have let every bottom-half offense reach at least its usual.
  - **Untested** (the defense never faced that kind of offense) → ❓.
  - The reason in the ❓ hover lists the games split by top half / weaker.
  - Kept as ❓ rather than tossing games. Tossing "cheap hits" was tested and dropped MUST BETs from 40 to 1 (see HISTORY).
- **Blowout rule → ❓** (2026-10-16, per Trevor: "10+ point favorite as a line to say that I shouldn't be taking a rb rush over"). If the team is favored by `BLOWOUT_FAV` (10)+, the team's lead back (`rb_lead` = biggest share of team RB carries) has no Rush Yds / Rush Attempts Over picks: they become ❓ ("Blowout risk …"), never 💡. Backup RB on a 10+ favorite (same day, per Trevor on Kaelon Black): his rush Unders become ❓ ("Blowout upside …", with his numbers in his team's 17+ wins) and his rush Overs get 💡 ("blowout upside on the Over -- an upside bet, not a consistency pick"), unless already a 3-star/MUST Over. The lead back's Unders and receiving stats are unaffected. In 2026 so far, 7+ favorites won by 17+ only 2 of 19 times (small sample); the lead back's carry share was 58% in 17+ wins vs ~72% in close games.
- **🎯 Outlier defense → 💡** (2026-10-30, per Trevor: "give some significance to defenses that allow statistically significant amounts", he picked "❓ → 💡", not a 3-star boost). `outlierDefense()`: the opponent is top-3 most allowed (Over) or top-3 least (Under) on **full-season** ranks (`OUTLIER_DEF_TOP`), only for `OUTLIER_DEF_STATS` = RB Rush Yds, WR/TE Receptions. 🎯 O / 🎯 U shows next to the player name (`outlierTag`, moved from the narrow Opp Rank cell 2026-10-30 because Trevor could not see it); a ❓ whose lean matches the side becomes 💡. Never for role-change/mismatch/blowout ❓s. Backtest in HISTORY.
  - **🎯 + line looks low → 3-star** (2026-10-30 as 💡; promoted 2026-11-03 per Trevor, "let's try starting with 1", after the Week 7-8 look-back: on the 🎯 side, unflagged rows 22-10, 13-8 at -130 or better). If Anticipated is 20%+ past the line on the 🎯 side (`OUTLIER_VALUE_RATIO`), the row becomes 🔥🔥🔥/🧊🧊🧊 **on the 🎯 side** (`outlierPromo` → `r.outlier_promo` {side, line, price, book, text}, `signal_rank` 6), so it IS alerted (`check_must_bets.py` uses `outlier_promo`'s side/line/price). Not if there's a role change, blowout or mismatch flag, or the best price on that side is worse than -130 (those stay 💡). Never a MUST BET. Re-check with the look-back; roll back if it stops winning.
- **🪜 Ladder board** (2026-11-09, per Trevor: "a projection for who's gonna go off that game based on scheme, performance and projected line vs vegas line"; his ladders are 10-yard rungs, 40+/50+/60+, more stake on low rungs; "going off" = several rungs past the line, 75 → ~120, 30 → ~80). It replaced the old 🪜 badge (season high ≥ 2x line). `ladderInfo()` uses one logistic model (`LADDER_COEF`, fit by `scripts/backtest_ladder_model.py` on 2019-2025) for P(reach T) at any rung.
  - **Features:** form (0.6 last-4 + 0.4 season, over the line), defense ratio (season allowed vs league, shrunk 3 games), usage (last-2 volume vs season), best/line, boom share, vacated teammate volume (Out/Doubtful from `INJ_BY_TEAM`), cv.
  - **Go-off:** reaching line + gap (yards max(40, 0.6L); catches max(3, 0.6L); pass yds max(75, 0.3L)). Rungs 4+ steps up are shaded (`ladderShade`).
  - **Board:** the top `LADDER_BOARD_SIZE` (15), one row per player, ranked by go-off chance ÷ `LADDER_BASE` (backtest rate per prop), so pass yards don't fill it. The "🪜 Ladder board" button opens a modal with each rung's chance and fair price plus the reasons. A 🪜 tag marks board rows, and "Ladder only" shows them. Season-to-date, not the Weeks filter. Context only, never alerted.
  - **Backtest** (2024-25 out of sample): weekly top 10 went off 32% vs 12%; top 10% per prop about 2x the rest. Game total/spread (flat) and man/zone fit (nflverse 2023-25 charting; flat, and 2026 isn't published) were tested and left out.
- **⬆ Alt line idea** (2026-10-30, per Trevor): `altLineInfo()` / `altLineTag()`. Overs only (per Trevor: "you can't bet alt unders"). When Anticipated is 25%+ above the line (`ALT_PROJ_RATIO`), it suggests the furthest alt line (steps of 5 yards / 1 count) short of the projection that he cleared in 75%+ (`ALT_HIT_RATE`) of the selected games (3+ games). "⬆ Alt lines only" filter box (`altOnly`, saved with the other filters; overrides Hide ❓, per Trevor "would be a fun thing to parlay"). A tag by the player name only; no alt odds are pulled (would cost credits), so it doesn't change signals or alerts.
- **Role changes → ❓** (2026-10-16, per Trevor: "lines that are a result of injuries, trade, personnel issues", then "i don't even want that in 3 stars"). A MUST BET or 3-star with a role change becomes ❓ ("Role change -- would have been …"), so it's never alerted. Three sources:
  - **Trade:** the nflverse roster says a player's team changed (`fetch_stats.detect_trades`). It flags him plus same-group teammates on both teams (`TRADE_ROLE_GROUPS`) until 2 games after (`TRADE_SETTLE_GAMES`). The new-team side counts his own games, or ends after 4 team games if he never plays. Only players with a real role count (`trade_had_role`: WR/TE 3+ targets/g, RB 6+ touches/g, QB 100+ pass yds/g). A traded player's rows use his new team and opponent.
  - **Injury:** a strong own-team 🩹 entry, i.e. a QB/RB/WR/TE with a real role (50%+ snaps, or for RBs 25%+ of team RB carries, `RB_CARRY_SHARE_ROLE`) listed Out/Doubtful. Questionable/missed-practice teammates are a faded ⚠️ "heads-up" that never blocks.
  - **Manual:** "⚠️ Flag role change" in the player popup (`MARKS['role|WEEK|player|team'] = 'flux'`, synced). notify.py applies each person's own flags.
- **📅 Full year agrees** (2026-10-31, per Trevor: "if it's also supported by full year stats, it's flagged"). For any row with a signal side (MUST/3-star/💡/❓), `enrichRow` re-runs `consistencyStats(..., seasonWeeks(), ..., side)` on every played week, same side and line; 📅 (`fullYearTag`) shows next to the signal when he and the defense are both at `CONS_TIERS[1]` (75%)+. A flag only; skipped when the selection already is the full season.
- **Win % / Need / Edge column** (2026-10-31, per Trevor: "show ... win percent chance with odds factored in"; he asked for the best method and approved market + model + hit rate). `winChance()` in enrichRow → `r.win` / `win_edge` (sortable), `winCellHtml()`. Per side: market no-vig % at the best line (other books' lines shifted by the model), moved toward a model in log-odds plus the season hit rate, with per-stat `[model, hit]` weights in `WIN_WEIGHTS` (tuned 2026-10-31 by `scripts/backtest_win_model.py` on 66k 2019-2025 predictions, ×0.75; untested stats fall back to `WIN_MODEL_WEIGHT` 0.35 / `WIN_HIT_WEIGHT` 0.5) applied to the season hit rate shrunk toward market (`WIN_HIT_PRIOR` 12 games). Model: mu = 0.6 last-selected + 0.4 season avg, blended 65/35 with Anticipated (clamped to 0.6-1.4× form); Poisson for small counts, normal for attempts/completions/carries, gamma for yards (`WIN_YARD_CV`), averaged over mu ×0.85/1/1.15. Needs 3+ season and 2+ selected games. Shows the better side's Win %, its best price's break-even, and Edge, colored (2026-10-31, per Trevor): green +3 to +10 (`WIN_EDGE_GOOD`..`WIN_EDGE_CHECK`, "if you like it, go"), amber ⚠ over +10 (check news / stale book), gray 0 to +3, red negative. **Context only, unproven: doesn't change signals or alerts.** My Bets has a "Wins vs break-even" card (sum of each settled bet's implied % vs wins). Saved column layouts get the new column inserted instead of being reset (`initColumns`).
- **Weeks filter:** defaults to the last 4 played weeks (`DEFAULT_LAST_WEEKS`, changed 2026-10-16 per Trevor; was 1..WEEK-1). Phone alerts use the same default. Last 2 / Last 4 / All played buttons. Signals follow the selected weeks; MUST BET always needs 4+ games. The player and defense popups list **every game this season**; games in the selected weeks are bold, the rest faded, with both "bold games" and "full season" averages (2026-10-31, per Trevor).
- **Book cells show the signal's side** (2026-11-01, per Trevor: "it's pulling the under number for Evan Engram over receptions"). `show_side` = the signal side (MUST/3-star/❓/💡 via `sigSide`), else the Win % side, else the old `direction`. DK/FD/MGM cells print "4.5 (O -120)" for that side, and the best-line highlight and bet-slip hint use `show_best_book` / `show_best_line` from `pickBestLine(r, show_side)`. Before, they used `direction` (recent avg vs line, an Average-edge leftover), which disagrees whenever one big game drags the average across the line.
- **Context only, not picks:** game script panel/popup (🎬), Second-look checklist, ladder 🪜, injury impact 🩹. In backtests only game script beat a coin flip (58%), on a small sample. Be honest about small samples; the consistency theory is not proven yet.

## Browser storage (per browser; the main thing to build next)
- Marks: `nfl_prop_dashboard_marks_v1`. Picking ❌ Pass opens a one-tap "Why pass?" picker (`PASS_REASONS`: injury, line moved, matchup, script, volume, exposure, gut, other; 2026-11-09, per Trevor: "would it help if there was a place where when i chose to pass, why i did?"). It's saved as `MARKS['why|' + key]`, along with the line the board showed (`MARKS['pline|' + key]` = side|line|price, from `snapshotPassLine`). Picking ✅ Bet opens "Why do you like it?" (`BET_REASONS` → `MARKS['like|' + key]`). Weekly rationale review (2026-11-09, per Trevor: "review my rationale at the end of the week and see if it worked"): Trevor pastes his My Bets backup, and Claude runs `python3 scripts/review_my_week.py <backup.json> --weeks N` locally. It reports bets by reason, passes by reason (would the board's side have won?), and by stat, side and stake. Don't commit his backup or dollar figures.
- Bets: `nfl_prop_dashboard_bets_v1` (key = `WEEK|player|team|stat_col`)
- Columns: `nfl_prop_dashboard_cols_v1`
- Filter checkboxes (Hide ❓, Ladder, Alt lines, Weak/Strong matchup): `nfl_prop_dashboard_filters_v1`. Hide ❌ rows always loads ticked (per Trevor).
- My Bets has Backup/Restore (JSON).
- 🔗 Parlay mark (`MARKS[key]='parlay'`) isn't a single bet; My Bets' "Build a parlay" box turns ticked 🔗 legs + odds into one manual bet with `legs` (looks W/L from the legs).
- **Login so bets sync across devices: live 2026-10-16** (Supabase project `ugyxzhdcmzqhibajtbwa`; URL + anon key at the top of `build_dashboard.py`). Look for "Sign-in + cross-device sync" in the template. The merge is three-way against the last synced copy (`nfl_prop_dashboard_sync_base_v1|<user id>`), and writes are conditional on `updated_at` so two devices can't overwrite each other. Not available on the Mac's file:// copy. The plan Trevor agreed to:
  - **Supabase** (free) handles email magic-link sign-in, plus one table holding each user's marks and bets.
  - The site keeps working logged-out with localStorage. On first login, local marks/bets are merged into the account.
  - After that, every save also upserts to Supabase (debounced), and on load the account copy is merged in.
  - Trevor's setup steps, to walk him through:
    1. Create a free project at supabase.com.
    2. In SQL Editor, run the script below.
    3. Authentication → URL Configuration: set Site URL to https://trevorrancourt.github.io/nfl-prop-dashboard/ and add `https://trevorrancourt.github.io/nfl-prop-dashboard/**` to Redirect URLs (the wildcard covers the Monday Night board too).
    4. Project Settings → API: give Claude the Project URL and the anon public key. Both are safe to put in the page; row-level security protects the data. Never use the service_role key.
  - SQL:
    ```sql
    create table public.user_state (
      user_id uuid primary key references auth.users on delete cascade,
      marks jsonb not null default '{}'::jsonb,
      bets  jsonb not null default '{}'::jsonb,
      updated_at timestamptz not null default now()
    );
    alter table public.user_state enable row level security;
    create policy "read own"   on public.user_state for select using (auth.uid() = user_id);
    create policy "insert own" on public.user_state for insert with check (auth.uid() = user_id);
    create policy "update own" on public.user_state for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
    ```
  - Load supabase-js from a pinned CDN version: `@supabase/supabase-js@2.45.4/dist/umd/supabase.js` on jsDelivr (that version has no `supabase.min.js`).
  - Put a small "Sign in / signed in as …" control next to My Bets.
  - Hook `saveMarks()` / `saveBets()` and the load path. Keep the existing Backup/Restore.

## Deploying changes
- **Every push to `main` rebuilds the site** (`push:` trigger added 2026-10-16; `docs/**` and `*.md` changes are ignored).
- Push changes to `main` (or open a PR and merge it) so the site updates. A branch alone doesn't change the live site.
- The cloud session's network may not reach the Odds API or Open-Meteo. To test a build locally, use `python run.py --skip-odds --skip-weather`; the real data refresh happens in GitHub Actions.

## Working style Trevor wants
- Make the change, test it (build + headless check), push, and confirm in 1-3 short sentences what changed and where to see it.
- Don't add new automation, publish, or change thresholds he didn't ask for. Flag assumptions plainly.
- Never print or commit the Odds API key.
