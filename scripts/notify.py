"""
Phone alerts for the hosted dashboard (added 2026-10-15; NEW / WATCHING
sections added 2026-10-16).

After each GitHub Actions refresh, reads the freshly built board(s) with
check_must_bets.py and pushes one ntfy notification (https://ntfy.sh) with
two sections:

  NEW       MUST BETs and 3-star picks you haven't seen yet: never sent
            before, and not already marked by you (bet / watching / pass).
  WATCHING  Every row you've marked 🌕 Watching that's on this week's board,
            with its current best line/price and how it moved since the
            alerts first saw it on your watch list.

It only buzzes when something changed: a NEW pick, or a watched line moving
(any line change, or the price moving 10+ cents). Otherwise it stays quiet.
State lives in data/last_alert.json (kept between runs by the workflow cache).

Your watch list comes from your dashboard account (Supabase), which needs
two more secrets: SUPABASE_SERVICE_KEY (Supabase > Project Settings > API >
service_role / secret key; never put it in the page) and ALERT_EMAIL (the
email you sign in with). Without them the WATCHING section is skipped and
NEW works as before (minus the "already marked" filter).

Does nothing unless the NTFY_TOPIC secret is set.

Usage: python scripts/notify.py output/dashboard.html [output/dashboard_mnf.html ...]
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "last_alert.json"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ugyxzhdcmzqhibajtbwa.supabase.co").rstrip("/")
PRICE_MOVE_CENTS = 10  # -110 -> -120, or -105 -> +105
MAX_LINES = 12


def picks_for(html, watch_keys):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(sorted(watch_keys), f)
    try:
        out = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_must_bets.py"), html,
             "--include-threes", "--json", "--watch-file", f.name],
            capture_output=True, text=True, timeout=180,
        )
    finally:
        os.unlink(f.name)
    if out.returncode != 0:
        print(out.stderr[-2000:])
        return None
    return json.loads(out.stdout)


def account_marks():
    """Your marks from the dashboard account, or None if not set up / failed."""
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    email = os.environ.get("ALERT_EMAIL", "").strip().lower()
    if not key or not email:
        print("SUPABASE_SERVICE_KEY / ALERT_EMAIL not set -- skipping the Watching section.")
        return None
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    try:
        uid = None
        for page in range(1, 11):
            r = requests.get(f"{SUPABASE_URL}/auth/v1/admin/users", headers=h,
                             params={"page": page, "per_page": 200}, timeout=20)
            r.raise_for_status()
            users = r.json().get("users", [])
            uid = next((u["id"] for u in users if (u.get("email") or "").lower() == email), None)
            if uid or len(users) < 200:
                break
        if not uid:
            print("No dashboard account with ALERT_EMAIL -- skipping the Watching section.")
            return None
        r = requests.get(f"{SUPABASE_URL}/rest/v1/user_state", headers=h,
                         params={"select": "marks", "user_id": f"eq.{uid}"}, timeout=20)
        r.raise_for_status()
        rows = r.json()
        return (rows[0].get("marks") or {}) if rows else {}
    except Exception as e:
        print("Couldn't read your marks from the account:", e)
        return None


def key(p):
    return f"{p['tier']}|{p['player']}|{p['stat']}|{p['side']}|{p['line']}"


def fmt_price(p):
    if p is None or p == "":
        return ""
    try:
        p = int(p)
    except (TypeError, ValueError):
        return str(p)
    return f"+{p}" if p > 0 else str(p)


def cents(p):
    # American odds on one continuous scale, so -105 -> +105 is 10 cents.
    p = int(p)
    return p + 100 if p < 0 else p - 100


def pick_line(p):
    icon = {"MUST BET": "⭐", "3 fire": "🔥", "3 ice": "🧊"}.get(p["tier"], "")
    price = f" {p['price']} {p['book']}".rstrip() if p.get("price") else ""
    return (f"{icon} {p['player']} ({p['team']} {p['opp']}) {p['stat']} "
            f"{p['side'].upper()} {p['line']}{price} · Hit {p['hit']} · Opp {p['oppHit']}")


def watch_line(w, base):
    head = f"🌕 {w['player']} ({w['team']} {w['opp']}) {w['stat']} {w['side'].upper()}"
    if w["line"] is None:
        return head + " · no line posted right now"
    now = f"{w['line']} {fmt_price(w['price'])} {w['book']}".rstrip()
    sig = {"MUST BET": " ⭐"}.get(w["signal"], (" " + w["signal"]) if w["signal"] else "")
    if not base or base.get("line") is None:
        move = ""
    elif base["line"] != w["line"] or base["price"] != w["price"]:
        move = f" · moved from {base['line']} {fmt_price(base['price'])}"
    else:
        move = " · no change"
    return f"{head} {now}{sig}{move}"


def moved(a, b):
    """True if the watched line moved enough to be worth a buzz."""
    if not a:
        return False
    if (a.get("line") is None) != (b.get("line") is None):
        return True
    if a.get("line") is None:
        return False
    if a["line"] != b["line"]:
        return True
    try:
        return abs(cents(a["price"]) - cents(b["price"])) >= PRICE_MOVE_CENTS
    except (TypeError, ValueError):
        return False


def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print("NTFY_TOPIC not set -- skipping phone alert.")
        return
    site = os.environ.get("PAGE_URL", "")

    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except Exception:
            pass
    sent = set(state.get("sent", []))
    watch_base = state.get("watch_base", {})  # key -> line/price when first seen watched
    watch_last = state.get("watch_last", {})  # key -> line/price at the last alert

    marks = account_marks()
    watch_keys = {k for k, v in (marks or {}).items() if v == "watch"}
    if marks is not None:  # forget rows you stopped watching, so re-watching starts fresh
        watch_base = {k: v for k, v in watch_base.items() if k in watch_keys}
        watch_last = {k: v for k, v in watch_last.items() if k in watch_keys}

    picks, watched, week = [], {}, None
    for html in sys.argv[1:]:
        if not Path(html).exists():
            continue
        res = picks_for(html, watch_keys)
        if not res:
            continue
        week = week or res["week"]
        picks += res["picks"]
        for w in res.get("watched", []):
            watched[w["key"]] = w

    new = [p for p in picks if key(p) not in sent and not (marks or {}).get(p.get("key"))]
    new.sort(key=lambda p: 0 if p["tier"] == "MUST BET" else 1)

    snap = {k: {"line": w["line"], "price": w["price"]} for k, w in watched.items()}
    for k, s in snap.items():
        if k not in watch_base or watch_base[k].get("line") is None:
            watch_base[k] = s
    n_moved = sum(1 for k, s in snap.items() if moved(watch_last.get(k), s))
    # A newly watched row is quiet until it moves: no buzz just for adding it.
    if not new and not n_moved:
        print(f"Nothing new ({len(picks)} picks on the board, all seen) and no watched line moved.")
        STATE.parent.mkdir(exist_ok=True)
        for k, s in snap.items():
            watch_last.setdefault(k, s)
        STATE.write_text(json.dumps({"week": week, "sent": sorted(sent), "watch_base": watch_base, "watch_last": watch_last}))
        return

    n_must = sum(1 for p in new if p["tier"] == "MUST BET")
    parts = []
    if n_must:
        parts.append(f"{n_must} new MUST BET{'s' if n_must != 1 else ''}")
    elif new:
        parts.append(f"{len(new)} new 3-star pick{'s' if len(new) != 1 else ''}")
    if n_moved:
        parts.append(f"{n_moved} watched line{'s' if n_moved != 1 else ''} moved")
    title = " · ".join(parts) + f" (Week {week})"

    lines = ["NEW"]
    lines += [pick_line(p) for p in new[:MAX_LINES]] or ["Nothing new since the last alert."]
    if len(new) > MAX_LINES:
        lines.append(f"+{len(new) - MAX_LINES} more on the board")
    if marks is not None:
        lines += ["", "WATCHING"]
        ws = sorted(watched.values(), key=lambda w: (not moved(watch_last.get(w["key"]), snap[w["key"]]), w["player"]))
        lines += [watch_line(w, watch_base.get(w["key"])) for w in ws[:MAX_LINES]] or ["Nothing marked 🌕 Watching on this week's board."]
        if len(ws) > MAX_LINES:
            lines.append(f"+{len(ws) - MAX_LINES} more on your watch list")

    r = requests.post("https://ntfy.sh/", json={
        "topic": topic, "title": title, "message": "\n".join(lines),
        "tags": ["football"], "click": site or None, "priority": 4 if n_must else 3,
    }, timeout=20)
    print("ntfy:", r.status_code, title)
    if r.ok:
        STATE.parent.mkdir(exist_ok=True)
        watch_last.update(snap)
        STATE.write_text(json.dumps({
            "week": week, "sent": sorted(sent | {key(p) for p in picks}),
            "watch_base": watch_base, "watch_last": watch_last,
        }))


if __name__ == "__main__":
    main()
