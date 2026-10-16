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
6. `build_dashboard.py`: one large `HTML_TEMPLATE` (Python `str.format`) holding all the JS/CSS, writing `output/dashboard.html`.
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

## Editing `build_dashboard.py`: gotchas that have bitten before
- `HTML_TEMPLATE` goes through `.format()`, so every JS/CSS brace must be doubled: `{{ }}`. Template literals become `${{x}}`.
- It's a normal (not raw) Python string, so in JS `'\n'` write `'\\n'`, and avoid `\'` (use the other quote style).
- After any change: build, then load the page headlessly and check for `pageerror`. One syntax error blanks the whole page.

## Signal logic: Trevor's rules, don't loosen without asking
- **Default signal mode is "Consistency (hit rates)".** "Average edge" is the old formula, still selectable.
  - The choice is saved in localStorage `nfl_prop_dashboard_signal_mode`.
  - If Trevor says signals "disappeared", check this first.
- **Tiers:**
  - 1 = player and defense both ≥75% but player not perfect.
  - 2 = player perfect and defense ≥2/3.
  - 3 = player perfect, defense ≥75%, and a top-10 matchup (otherwise capped at 2).
  - ⭐ MUST BET = both sides perfect, 4+ games each, top-10 matchup (Over: one of the 10 defenses allowing the most; Under: one of the 10 allowing the least).
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
- **Role changes block MUST BET** (2026-10-16, per Trevor: "lines that are a result of injuries, trade, personnel issues"). Such a row is held at 3 with a ⚠️ tag; alerts send it as a 3-star with "⚠️ role change". Three sources:
  - **Trade:** the nflverse roster says a player's team changed (`fetch_stats.detect_trades`). It flags him plus same-group teammates on both teams (`TRADE_ROLE_GROUPS`) until 2 games after (`TRADE_SETTLE_GAMES`). The new-team side counts his own games, or ends after 4 team games if he never plays. Only players with a real role count (`trade_had_role`: WR/TE 3+ targets/g, RB 6+ touches/g, QB 100+ pass yds/g). A traded player's rows use his new team and opponent.
  - **Injury:** a strong own-team 🩹 entry, i.e. a QB/RB/WR/TE with a real role (50%+ snaps, or for RBs 25%+ of team RB carries, `RB_CARRY_SHARE_ROLE`) listed Out/Doubtful. Questionable/missed-practice teammates are a faded ⚠️ "heads-up" that never blocks.
  - **Manual:** "⚠️ Flag role change" in the player popup (`MARKS['role|WEEK|player|team'] = 'flux'`, synced). notify.py applies each person's own flags.
- **Weeks filter:** defaults to the last 4 played weeks (`DEFAULT_LAST_WEEKS`, changed 2026-10-16 per Trevor; was 1..WEEK-1). Phone alerts use the same default. Last 2 / Last 4 / All played buttons. Signals follow the selected weeks; MUST BET always needs 4+ games.
- **Context only, not picks:** game script panel/popup (🎬), Second-look checklist, ladder 🪜, injury impact 🩹. In backtests only game script beat a coin flip (58%), on a small sample. Be honest about small samples; the consistency theory is not proven yet.

## Browser storage (per browser; the main thing to build next)
- Marks: `nfl_prop_dashboard_marks_v1`
- Bets: `nfl_prop_dashboard_bets_v1` (key = `WEEK|player|team|stat_col`)
- Columns: `nfl_prop_dashboard_cols_v1`
- Filter checkboxes (Hide ❓, Ladder, Weak/Strong matchup): `nfl_prop_dashboard_filters_v1`. Hide ❌ rows always loads ticked (per Trevor).
- My Bets has Backup/Restore (JSON).
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
