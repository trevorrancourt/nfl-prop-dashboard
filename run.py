"""
One-command entry point: pulls fresh stats + odds + weather and rebuilds
the dashboard.

Usage:
    python3 run.py                  # stats + injuries + odds + weather + coverage + dashboard
    python3 run.py --skip-injuries  # skip the official injury-report fetch
    python3 run.py --skip-odds      # skip the Odds API call
    python3 run.py --skip-weather   # skip the weather forecast fetch
    python3 run.py --skip-coverage  # skip the man/zone coverage-rate scrape
    python3 run.py --only-dashboard # just rebuild the HTML from existing data
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(script_name, env=None):
    print(f"\n=== {script_name} ===")
    result = subprocess.run([sys.executable, str(ROOT / script_name)], env=env)
    if result.returncode != 0:
        sys.exit(f"{script_name} failed, stopping.")


def run_optional(script_name, env=None):
    """Like run(), but a failure here doesn't stop the rest of the pipeline
    -- used for the coverage-rate scrape, which pulls from an unofficial
    third-party page and is the most likely thing here to ever break."""
    print(f"\n=== {script_name} ===")
    result = subprocess.run([sys.executable, str(ROOT / script_name)], env=env)
    if result.returncode != 0:
        print(f"({script_name} failed -- continuing without it. See its output above.)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-injuries", action="store_true", help="Don't fetch the official injury report")
    parser.add_argument("--skip-odds", action="store_true", help="Don't call the Odds API")
    parser.add_argument("--skip-weather", action="store_true", help="Don't fetch weather forecasts")
    parser.add_argument("--skip-coverage", action="store_true", help="Don't fetch man/zone coverage rates")
    parser.add_argument("--only-dashboard", action="store_true", help="Just rebuild the HTML")
    parser.add_argument("--no-mnf", action="store_true", help="Don't build the Monday Night board")
    args = parser.parse_args()

    if not args.only_dashboard:
        run("fetch_stats.py")
        if not args.skip_injuries:
            run_optional("fetch_injuries.py")
        if not args.skip_odds:
            run("fetch_odds.py")
        if not args.skip_weather:
            run("fetch_weather.py")
        if not args.skip_coverage:
            run_optional("fetch_coverage.py")

    # Monday Night board (added 2026-10-12). Once most of a week is played,
    # fetch_stats.py rolls the main board to the next week -- but Monday
    # Night Football from the old week is still ahead. When that happens,
    # build a second board just for those games (own data folder, own
    # output file) and link the two boards to each other.
    import json, os, shutil
    from datetime import datetime
    mnf = None
    try:
        mnf = json.loads((ROOT / "data" / "stats_cache.json").read_text()).get("prev_week_open")
    except Exception:
        pass
    main_env = None
    if mnf and not args.no_mnf:
        wk = mnf["week"]
        games = ", ".join(f"{g['away']} @ {g['home']}" for g in mnf["games"])
        mnf_dir = ROOT / "data_mnf"
        mnf_dir.mkdir(exist_ok=True)
        env = dict(os.environ, NFL_DATA_DIR=str(mnf_dir), NFL_WEEK_OVERRIDE=str(wk), NFL_UPCOMING_ONLY="1",
                   NFL_OUTPUT_NAME="dashboard_mnf.html", NFL_BOARD_BADGE=f"Monday Night board: Week {wk}, {games}",
                   NFL_ALT_LINK="dashboard.html|Back to the full board")
        print(f"\n##### Monday Night board: Week {wk} ({games}) #####")
        cov = ROOT / "data" / "coverage_cache.json"
        if cov.exists():
            shutil.copy2(cov, mnf_dir / "coverage_cache.json")
        if not args.only_dashboard:
            run("fetch_stats.py", env)
            if not args.skip_injuries:
                run_optional("fetch_injuries.py", env)
            if not args.skip_odds:
                run("fetch_odds.py", env)
            if not args.skip_weather:
                run_optional("fetch_weather.py", env)
        if (mnf_dir / "stats_cache.json").exists():
            run("build_dashboard.py", env)
            main_env = dict(os.environ, NFL_ALT_LINK=f"dashboard_mnf.html|\U0001F319 Monday Night: {games} (Week {wk})")
            if not args.only_dashboard:
                hist = ROOT / "history"
                hist.mkdir(exist_ok=True)
                shutil.copy2(ROOT / "output" / "dashboard_mnf.html", hist / f"dashboard_{datetime.now():%Y-%m-%d_%H%M}_mnf.html")
        print("\n##### Main board #####")

    run("build_dashboard.py", main_env)

    dashboard = ROOT / "output" / "dashboard.html"
    # Keep a copy of every full build (added 2026-10-01) so each week's
    # pre-game signals can be graded against the real results later --
    # that's how the Week 3 backtest of the ❓ rows was done.
    if not args.only_dashboard and dashboard.exists():
        hist = ROOT / "history"
        hist.mkdir(exist_ok=True)
        shutil.copy2(dashboard, hist / f"dashboard_{datetime.now():%Y-%m-%d_%H%M}.html")
    print(f"\nDone. Open this in your browser:\n{dashboard}")
    if main_env:
        print(f"Monday Night board: {ROOT / 'output' / 'dashboard_mnf.html'} (linked from the top of the main board)")


if __name__ == "__main__":
    main()
