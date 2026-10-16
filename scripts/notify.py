"""
Phone alerts for the hosted dashboard (added 2026-10-15).

After each GitHub Actions refresh, reads the freshly built board(s) with
check_must_bets.py and pushes NEW MUST BETs and 3-star picks to the free
ntfy app (https://ntfy.sh). Picks already sent are remembered in
data/last_alert.json (kept between runs by the workflow's cache), so the
same list doesn't buzz your phone every three hours.

Does nothing unless the NTFY_TOPIC secret is set.

Usage: python scripts/notify.py output/dashboard.html [output/dashboard_mnf.html ...]
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "last_alert.json"


def picks_for(html):
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_must_bets.py"), html, "--include-threes", "--json"],
        capture_output=True, text=True, timeout=180,
    )
    if out.returncode != 0:
        print(out.stderr[-2000:])
        return None
    return json.loads(out.stdout)


def key(p):
    return f"{p['tier']}|{p['player']}|{p['stat']}|{p['side']}|{p['line']}"


def line(p):
    icon = {"MUST BET": "⭐", "3 fire": "🔥", "3 ice": "🧊"}.get(p["tier"], "")
    price = f" {p['price']} {p['book']}".rstrip() if p.get("price") else ""
    return (f"{icon} {p['player']} ({p['team']} {p['opp']}) {p['stat']} "
            f"{p['side'].upper()} {p['line']}{price} · Hit {p['hit']} · Opp {p['oppHit']}")


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print("NTFY_TOPIC not set -- skipping phone alert.")
        return
    site = os.environ.get("PAGE_URL", "")
    picks, week = [], None
    for html in sys.argv[1:]:
        if not Path(html).exists():
            continue
        res = picks_for(html)
        if not res:
            continue
        week = week or res["week"]
        picks += res["picks"]
    sent = set()
    if STATE.exists():
        try:
            sent = set(json.loads(STATE.read_text()).get("sent", []))
        except Exception:
            pass
    new = [p for p in picks if key(p) not in sent]
    if not new:
        print(f"No new picks to alert ({len(picks)} on the board, all sent before).")
        return
    new.sort(key=lambda p: 0 if p["tier"] == "MUST BET" else 1)
    n_must = sum(1 for p in new if p["tier"] == "MUST BET")
    title = (f"{n_must} new MUST BET{'s' if n_must != 1 else ''}" if n_must else f"{len(new)} new 3-star pick{'s' if len(new) != 1 else ''}") + f" (Week {week})"
    body = "\n".join(line(p) for p in new[:12])
    if len(new) > 12:
        body += f"\n+{len(new) - 12} more on the board"
    r = requests.post("https://ntfy.sh/", json={
        "topic": topic, "title": title, "message": body,
        "tags": ["football"], "click": site or None, "priority": 4 if n_must else 3,
    }, timeout=20)
    print("ntfy:", r.status_code, title)
    if r.ok:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps({"week": week, "sent": sorted(sent | {key(p) for p in picks})}))


if __name__ == "__main__":
    main()
