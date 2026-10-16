"""
Phone alerts for the hosted dashboard (added 2026-10-15; NEW / WATCHING
sections and per-person alerts added 2026-10-16).

After each GitHub Actions refresh, reads the freshly built board(s) with
check_must_bets.py and pushes one ntfy notification (https://ntfy.sh) per
person, with two sections:

  NEW       MUST BETs and 3-star picks that person hasn't seen yet: never
            sent to them before, and not already marked by them (bet /
            watching / pass).
  WATCHING  Every row they've marked 🌕 Watching that's on this week's board,
            with its current best line/price and how it moved since the
            alerts first saw it on their watch list.

It only buzzes someone when something changed for them: a NEW pick, or one
of their watched lines moving (any line change, or the price moving 10+
cents). State lives in data/last_alert.json (kept by the workflow cache).

Who gets alerts:
  - Anyone signed in on the site who saved a topic under "🔔 Alerts"
    (public.alert_prefs). Needs the SUPABASE_SERVICE_KEY secret
    (Supabase > Project Settings > API Keys > service_role / secret key;
    never put it in the page).
  - The NTFY_TOPIC secret goes to the owner, whose watch list is read from
    the account with the ALERT_EMAIL secret. If the owner also saved a topic
    on the site, the site one wins.
Without SUPABASE_SERVICE_KEY only NTFY_TOPIC gets alerts, NEW section only.

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


def supabase_get(path, key, params):
    h = {"apikey": key}
    if key.startswith("eyJ"):  # legacy service_role JWT; new sb_secret_ keys go in apikey only
        h["Authorization"] = f"Bearer {key}"
    r = requests.get(f"{SUPABASE_URL}{path}", headers=h, params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def recipients():
    """[{id, topic, marks}] -- marks is None when the account can't be read."""
    owner_topic = os.environ.get("NTFY_TOPIC", "").strip()
    owner_email = os.environ.get("ALERT_EMAIL", "").strip().lower()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    owner = [{"id": "owner", "topic": owner_topic, "marks": None}] if owner_topic else []
    if not key:
        print("SUPABASE_SERVICE_KEY not set -- only NTFY_TOPIC gets alerts, without the Watching section.")
        return owner
    try:
        emails = {}
        for page in range(1, 51):
            users = supabase_get("/auth/v1/admin/users", key, {"page": page, "per_page": 200}).get("users", [])
            emails.update({u["id"]: (u.get("email") or "").lower() for u in users})
            if len(users) < 200:
                break
        states = supabase_get("/rest/v1/user_state", key, {"select": "user_id,marks"})
    except Exception as e:
        print("Couldn't read accounts from Supabase:", e)
        return owner
    try:
        prefs = supabase_get("/rest/v1/alert_prefs", key, {"select": "user_id,ntfy_topic", "ntfy_topic": "not.is.null"})
    except Exception as e:
        print("Couldn't read alert_prefs (table not created yet?):", e)
        prefs = []
    marks = {s["user_id"]: s.get("marks") or {} for s in states}
    out = {}
    for p in prefs:
        t = (p.get("ntfy_topic") or "").strip()
        if t and p["user_id"] in emails:
            out[p["user_id"]] = {"id": p["user_id"], "topic": t, "marks": marks.get(p["user_id"], {})}
    if owner_topic:
        owner_id = next((i for i, e in emails.items() if owner_email and e == owner_email), None)
        if not owner_id:
            print("No dashboard account with ALERT_EMAIL -- NTFY_TOPIC gets alerts without the Watching section.")
            out.setdefault("owner", owner[0])
        elif owner_id not in out:
            out[owner_id] = {"id": owner_id, "topic": owner_topic, "marks": marks.get(owner_id, {}), "owner": True}
        else:
            out[owner_id]["owner"] = True
    # Two people on the same topic would get every alert twice; keep the first.
    seen, result = set(), []
    for r in out.values():
        if r["topic"] not in seen:
            seen.add(r["topic"])
            result.append(r)
    return result


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
    warn = " · ⚠️ role change" if p.get("roleChange") else ""
    return (f"{icon} {p['player']} ({p['team']} {p['opp']}) {p['stat']} "
            f"{p['side'].upper()} {p['line']}{price} · Hit {p['hit']} · Opp {p['oppHit']}{warn}")


def apply_own_flags(picks, marks):
    """This person's own ⚠️ role-change flags (set in the player popup) take
    that player off their alert entirely -- a role change makes a pick a ❓
    on the board, not a MUST BET or 3-star (2026-10-16)."""
    out = []
    for p in picks:
        parts = (p.get("key") or "").split("|")
        if len(parts) >= 3 and (marks or {}).get("role|" + "|".join(parts[:3])) == "flux":
            continue
        out.append(p)
    return out


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


def alert_for(rec, picks, watched_all, week, st):
    """This person's notification payload (or None). Updates their state `st`;
    the returned commit() marks everything as sent, once the push went out."""
    marks = rec["marks"]
    picks = apply_own_flags(picks, marks)
    sent = set(st.get("sent", []))
    watch_keys = {k for k, v in (marks or {}).items() if v == "watch"}
    # Forget rows they stopped watching, so re-watching starts fresh.
    watch_base = {k: v for k, v in st.get("watch_base", {}).items() if marks is None or k in watch_keys}
    watch_last = {k: v for k, v in st.get("watch_last", {}).items() if marks is None or k in watch_keys}

    new = [p for p in picks if key(p) not in sent and not (marks or {}).get(p.get("key"))]
    new.sort(key=lambda p: 0 if p["tier"] == "MUST BET" else 1)
    watched = {k: w for k, w in watched_all.items() if k in watch_keys}
    snap = {k: {"line": w["line"], "price": w["price"]} for k, w in watched.items()}
    for k, s in snap.items():
        if k not in watch_base or watch_base[k].get("line") is None:
            watch_base[k] = s
    n_moved = sum(1 for k, s in snap.items() if moved(watch_last.get(k), s))
    st["watch_base"], st["watch_last"], st["sent"] = watch_base, watch_last, sorted(sent)

    if not new and not n_moved:
        # A newly watched row is quiet until it moves: no buzz just for adding it.
        for k, s in snap.items():
            watch_last.setdefault(k, s)
        return None, None

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

    def commit():
        watch_last.update(snap)
        st["sent"] = sorted(sent | {key(p) for p in picks})

    payload = {"topic": rec["topic"], "title": title, "message": "\n".join(lines),
               "tags": ["football"], "priority": 4 if n_must else 3}
    return payload, commit


def main():
    recs = recipients()
    if not recs:
        print("No NTFY_TOPIC and nobody has saved an alert topic -- skipping phone alerts.")
        return
    site = os.environ.get("PAGE_URL", "")

    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except Exception:
            pass
    users = state.get("users")
    if users is None:  # before per-person alerts there was one shared state, and it was the owner's
        users = {"owner": {k: state[k] for k in ("sent", "watch_base", "watch_last") if k in state}}
    owner_id = next((r["id"] for r in recs if r.get("owner")), None)
    if owner_id and "owner" in users and owner_id not in users:
        users[owner_id] = users.pop("owner")

    watch_keys = set()
    for r in recs:
        watch_keys |= {k for k, v in (r["marks"] or {}).items() if v == "watch"}
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

    print(f"Alerts for {len(recs)} {'person' if len(recs) == 1 else 'people'}; {len(picks)} picks on the board.")
    for r in recs:
        st = users.setdefault(r["id"], {})
        payload, commit = alert_for(r, picks, watched, week, st)
        who = "owner" if r.get("owner") or r["id"] == "owner" else r["id"][:8]
        if not payload:
            print(f"[{who}] nothing new and no watched line moved.")
            continue
        if site:
            payload["click"] = site
        try:
            resp = requests.post("https://ntfy.sh/", json=payload, timeout=20)
            print(f"[{who}] ntfy: {resp.status_code} {payload['title']}")
            if resp.ok:
                commit()
        except Exception as e:
            print(f"[{who}] ntfy failed: {e}")

    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"week": week, "users": users}))


if __name__ == "__main__":
    main()
