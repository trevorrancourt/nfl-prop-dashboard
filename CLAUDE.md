# NFL Player Prop Dashboard: notes for Claude

Read this first in every session. The full build history (every version, decision and backtest) is in `docs/HISTORY.md`. Search it before re-deciding anything.

## Who / what
- Owner: Trevor (trevorrancourt). He bets NFL player props and uses this dashboard to find them. He isn't a developer: explain in plain words, keep steps short, and do the work yourself.
- Live site: https://trevorrancourt.github.io/nfl-prop-dashboard/ (GitHub Pages, public link).
- `.github/workflows/update.yml` rebuilds the site every 3 hours, 8am-8pm Mountain (cron in UTC), plus "Run workflow" on demand.
- A copy of the project also lives on his Mac (`~/Documents/Gambling Program`), where `python3 run.py` builds `output/dashboard.html` locally. The repo is now the source of truth.

## How it works
`run.py` runs these in order, then builds the page:
1. `fetch_stats.py`: nflverse schedule, weekly stats, snap counts and finished-game results → `data/stats_cache.json`. It picks the current week and backfills zero-stat weeks.
2. `fetch_injuries.py`: nflverse injury report, with a practice-report fallback and snap shares.
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

**Phone alerts:** `scripts/check_must_bets.py` reads a built page headlessly (Playwright) and lists MUST BET / 3-star rows. `scripts/notify.py` pushes new ones to ntfy, but only when the `NTFY_TOPIC` secret is set.

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
  - A player's miss doesn't count against a top-5 tough defense.
  - A defense's miss doesn't count against an offense whose usual output is under 0.75× the line.
  - The adjusted rate applies only if enough games remain.
- **Weeks filter:** defaults to played weeks (1..WEEK-1). Last 2 / Last 4 / All played buttons. Signals follow the selected weeks; MUST BET always needs 4+ games.
- **Context only, not picks:** game script panel/popup (🎬), Second-look checklist, ladder 🪜, injury impact 🩹. In backtests only game script beat a coin flip (58%), on a small sample. Be honest about small samples; the consistency theory is not proven yet.

## Browser storage (per browser; the main thing to build next)
- Marks: `nfl_prop_dashboard_marks_v1`
- Bets: `nfl_prop_dashboard_bets_v1` (key = `WEEK|player|team|stat_col`)
- Columns: `nfl_prop_dashboard_cols_v1`
- My Bets has Backup/Restore (JSON).
- **Next up: login so bets sync across devices.** The plan Trevor agreed to:
  - **Supabase** (free) handles email magic-link sign-in, plus one table holding each user's marks and bets.
  - The site keeps working logged-out with localStorage. On first login, local marks/bets are merged into the account.
  - After that, every save also upserts to Supabase (debounced), and on load the account copy is merged in.
  - Trevor's setup steps, to walk him through:
    1. Create a free project at supabase.com.
    2. In SQL Editor, run the script below.
    3. Authentication → URL Configuration: set Site URL to https://trevorrancourt.github.io/nfl-prop-dashboard/ and add it to Redirect URLs.
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
  - Load supabase-js from a pinned CDN version (e.g. `@supabase/supabase-js@2.45.4` UMD on jsDelivr).
  - Put a small "Sign in / signed in as …" control next to My Bets.
  - Hook `saveMarks()` / `saveBets()` and the load path. Keep the existing Backup/Restore.

## Deploying changes
- **Every push to `main` should rebuild the site.** If `update.yml` has no `push:` trigger yet, add `push: branches: [main]` (ignore `docs/**` and `*.md` paths) as the first task.
- Push changes to `main` (or open a PR and merge it) so the site updates. A branch alone doesn't change the live site.
- The cloud session's network may not reach the Odds API or Open-Meteo. To test a build locally, use `python run.py --skip-odds --skip-weather`; the real data refresh happens in GitHub Actions.

## Working style Trevor wants
- Make the change, test it (build + headless check), push, and confirm in 1-3 short sentences what changed and where to see it.
- Don't add new automation, publish, or change thresholds he didn't ask for. Flag assumptions plainly.
- Never print or commit the Odds API key.
