#!/usr/bin/env python3
"""
ufc_results_update.py — keep fight RESULTS current, incrementally, on Actions.

SOURCE CHANGE (2026-07-17): ufcstats.com now serves a JavaScript bot-check
("Checking your browser..."), so urllib gets a challenge page instead of the
event list and every parse returns zero. That source is unusable without a
headless browser. This version reads ESPN's public, keyless UFC endpoint
instead — same family as the soccer feed the World Cup tool already uses.

  calendar : https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard
             -> leagues[0].calendar[] = {label, startDate, event.$ref(id)}
  one card : same URL + ?dates=YYYYMMDD
             -> events[].competitions[].competitors[] {winner, athlete.fullName}

State:   data/results_through.txt   (a date; only events after it are pulled)
Output:  data/results_delta.csv     (event_date,event,winner,loser,method,round)

Fail-loud: if new events exist but zero fights parse, exit 1. A silent empty
append after an upstream change is exactly the failure mode we refuse to have.

  --selftest  parse fixtures, no network
  --probe     print the raw JSON of the first COMPLETED bout it finds, then exit.
              Run this once on a machine that can reach ESPN to confirm how
              method/round are spelled; paste the output back if anything below
              is guessing wrong.
"""
import os, re, csv, sys, json, datetime as dt
import urllib.request

HERE  = os.path.dirname(os.path.abspath(__file__))
DATA  = os.path.join(HERE, "data")
STATE = os.path.join(DATA, "results_through.txt")
DELTA = os.path.join(DATA, "results_delta.csv")
BASE  = "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard"
UA    = {"User-Agent": "Mozilla/5.0 (results updater; github actions)"}
BOOTSTRAP_THROUGH = dt.date(2026, 6, 14)   # ratings baseline date

def fetch_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

# ---------------- calendar ----------------
def parse_calendar(doc):
    """[(date, label, event_id)] for every card in the season, oldest first."""
    out = []
    for lg in (doc.get("leagues") or []):
        for c in (lg.get("calendar") or []):
            sd = c.get("startDate") or ""
            try:
                d = dt.datetime.strptime(sd[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            ref = (((c.get("event") or {}).get("$ref")) or "")
            m = re.search(r"/events/(\d+)", ref)
            out.append((d, (c.get("label") or "").strip(), m.group(1) if m else ""))
    return sorted(out)

# ---------------- one card ----------------
def _status(comp):
    return ((comp.get("status") or {}).get("type") or {})

def is_final(comp):
    st = _status(comp)
    return bool(st.get("completed")) or st.get("state") == "post"

def parse_method_round(comp):
    """ESPN spells the finish inside status.type (detail/description/shortDetail)
    and the round in status.period. Several shapes are tolerated; if none match
    we return ('?', round) rather than inventing a method."""
    st  = _status(comp)
    txt = " ".join(str(st.get(k) or "") for k in ("detail", "shortDetail", "description"))
    low = txt.lower()

    rnd = comp.get("status", {}).get("period") or 0
    m = re.search(r"\bround\s*(\d)\b|\bR(\d)\b", txt, re.I)
    if m:
        rnd = int(m.group(1) or m.group(2))
    try:
        rnd = int(rnd)
    except (TypeError, ValueError):
        rnd = 0

    if "no contest" in low or re.search(r"\bnc\b", low):        return "NC", rnd
    if "draw" in low:                                           return "Draw", rnd
    if "disqualif" in low or re.search(r"\bdq\b", low):         return "DQ", rnd
    if "submission" in low or "sub" == low.strip():             return "SUB", rnd
    if "decision" in low or "dec" in low.split():
        if "split"     in low: return "S-DEC", rnd
        if "majority"  in low: return "M-DEC", rnd
        return "U-DEC", rnd
    if "ko" in low or "tko" in low or "knockout" in low or "stoppage" in low or "doctor" in low:
        return "KO/TKO", rnd
    return "?", rnd

def parse_card(doc):
    """[(event_name, winner, loser, method, round)] for completed bouts."""
    fights = []
    for ev in (doc.get("events") or []):
        name = (ev.get("name") or "").strip()
        for comp in (ev.get("competitions") or []):
            if not is_final(comp):
                continue
            cs = comp.get("competitors") or []
            if len(cs) != 2:
                continue
            names = []
            for c in cs:
                a = c.get("athlete") or {}
                names.append((a.get("fullName") or a.get("displayName") or "").strip())
            if not all(names):
                continue
            win = [c for c in cs if c.get("winner") is True]
            method, rnd = parse_method_round(comp)
            if len(win) == 1:
                w = win[0]
                wn = ((w.get("athlete") or {}).get("fullName") or "").strip()
                ln = [n for n in names if n != wn]
                if not ln:
                    continue
                fights.append((name, wn, ln[0], method, rnd))
            else:
                # draw / NC: no winner flag. record with a non-decisive method.
                if method in ("Draw", "NC"):
                    fights.append((name, names[0], names[1], method, rnd))
    return fights

# ---------------- selftest ----------------
FIX_CAL = {"leagues": [{"calendar": [
    {"label": "UFC 329", "startDate": "2026-07-11T23:00Z",
     "event": {"$ref": "http://sports.core.api.espn.pvt/v2/sports/mma/leagues/ufc/events/600059148?lang=en"}},
    {"label": "UFC Fight Night: Oklahoma City", "startDate": "2026-07-19T01:00Z",
     "event": {"$ref": "http://sports.core.api.espn.pvt/v2/sports/mma/leagues/ufc/events/600059599?lang=en"}},
]}]}
def _bout(w, l, detail, period, winner_first=True, no_winner=False):
    a = {"athlete": {"fullName": w}, "winner": (not no_winner)}
    b = {"athlete": {"fullName": l}, "winner": False}
    return {"competitors": ([a, b] if winner_first else [b, a]),
            "status": {"period": period, "type": {"completed": True, "state": "post", "detail": detail}}}
FIX_CARD = {"events": [{"name": "UFC 329: McGregor vs. Holloway 2", "competitions": [
    _bout("Max Holloway", "Conor McGregor", "KO/TKO - Round 1, 1:09", 1, winner_first=False),
    _bout("Alessandro Costa", "Cody Durden", "Submission - Round 2, 2:19", 2),
    _bout("Mario Bautista", "Cory Sandhagen", "Decision - Unanimous", 3),
    _bout("Farid Basharat", "John Garza", "Decision - Split", 3),
    {"competitors": [{"athlete": {"fullName": "Ode Osbourne"}, "winner": False},
                     {"athlete": {"fullName": "Someone Else"}, "winner": False}],
     "status": {"period": 0, "type": {"completed": False, "state": "pre", "detail": "Scheduled"}}},
]}]}

def selftest():
    cal = parse_calendar(FIX_CAL)
    assert len(cal) == 2, cal
    assert cal[0] == (dt.date(2026, 7, 11), "UFC 329", "600059148"), cal[0]
    assert cal[1][0] == dt.date(2026, 7, 19)

    f = parse_card(FIX_CARD)
    assert len(f) == 4, f"expected 4 completed bouts, got {len(f)}: {f}"
    assert f[0] == ("UFC 329: McGregor vs. Holloway 2", "Max Holloway", "Conor McGregor", "KO/TKO", 1), f[0]
    assert f[1][1:] == ("Alessandro Costa", "Cody Durden", "SUB", 2), f[1]
    assert f[2][4] == 3 and f[2][3] == "U-DEC", f[2]
    assert f[3][3] == "S-DEC", f[3]
    # scheduled bout must be excluded
    assert all("Osbourne" not in r[2] for r in f)
    # method vocabulary
    for txt, want in [("Decision - Majority", "M-DEC"), ("No Contest", "NC"),
                      ("DQ - Round 2", "DQ"), ("Draw - Split", "Draw"),
                      ("Doctor Stoppage - Round 3", "KO/TKO")]:
        got = parse_method_round({"status": {"period": 1, "type": {"detail": txt}}})[0]
        assert got == want, f"{txt!r} -> {got!r}, expected {want!r}"
    # round parsed out of the text, not just period
    assert parse_method_round({"status": {"period": 0, "type": {"detail": "KO/TKO - Round 3, 1:01"}}})[1] == 3
    print("RESULTS-UPDATER SELFTEST PASS — calendar, bouts, methods, rounds all parse")

# ---------------- probe2: what does a CARD look like, and does the core API carry method? ----------------
def probe2():
    """Dump every completed bout on the most recent card (winner/round/clock) plus
    the core-API competition record for one of them. Calibrates decision-vs-finish
    and shows whether the method is available anywhere."""
    cal = parse_calendar(fetch_json(BASE))
    today = dt.date.today()
    past = sorted([c for c in cal if c[0] <= today], reverse=True)
    for d, label, eid in past[:2]:
        doc = fetch_json(f"{BASE}?dates={d.strftime('%Y%m%d')}")
        print(f"\n=== {label}  ({d})  event_id={eid} ===")
        print(f"{'winner':<24}{'loser':<24}{'rnd':>4}{'clock':>8}  {'periods':>7}")
        comp_id = None
        for ev in (doc.get("events") or []):
            for comp in (ev.get("competitions") or []):
                if not is_final(comp): continue
                cs = comp.get("competitors") or []
                if len(cs) != 2: continue
                w = next((c for c in cs if c.get("winner") is True), None)
                l = next((c for c in cs if c.get("winner") is not True), None)
                if not (w and l): continue
                st = comp.get("status") or {}
                fmt = ((comp.get("format") or {}).get("regulation") or {}).get("periods")
                wn = ((w.get("athlete") or {}).get("fullName") or "")[:23]
                ln = ((l.get("athlete") or {}).get("fullName") or "")[:23]
                print(f"{wn:<24}{ln:<24}{st.get('period',''):>4}"
                      f"{str(st.get('displayClock','')):>8}  {str(fmt):>7}")
                comp_id = comp_id or comp.get("id")
        if comp_id and eid:
            url = (f"http://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/"
                   f"events/{eid}/competitions/{comp_id}?lang=en&region=us")
            print(f"\n--- core API competition {comp_id} ---")
            try:
                j = fetch_json(url)
                print("top-level keys:", sorted(j.keys()))
                for k in ("status", "notes", "type", "outcome", "result", "format"):
                    if k in j: print(f"  {k}: {json.dumps(j[k])[:400]}")
            except Exception as e:
                print(f"  core API failed: {type(e).__name__}: {e}")
        return

# ---------------- probe ----------------
def probe():
    cal = parse_calendar(fetch_json(BASE))
    today = dt.date.today()
    for d, label, _ in sorted([c for c in cal if c[0] <= today], reverse=True):
        doc = fetch_json(f"{BASE}?dates={d.strftime('%Y%m%d')}")
        for ev in (doc.get("events") or []):
            for comp in (ev.get("competitions") or []):
                if is_final(comp):
                    print(f"--- first completed bout found: {label} ({d}) ---")
                    print(json.dumps({"status": comp.get("status"),
                                      "competitors": comp.get("competitors")},
                                     indent=2)[:4000])
                    print("--- parsed as:", parse_method_round(comp))
                    return
    print("no completed bouts found in the calendar window")

# ---------------- main ----------------
def main():
    through = BOOTSTRAP_THROUGH
    if os.path.exists(STATE):
        through = dt.date.fromisoformat(open(STATE).read().strip())
    print(f"results through: {through}")

    cal = parse_calendar(fetch_json(BASE))
    if not cal:
        sys.exit("FATAL: calendar parsed to zero events — ESPN shape changed?")
    today = dt.date.today()
    new = [(d, label, eid) for (d, label, eid) in cal if through < d <= today]
    print(f"cards on calendar: {len(cal)} | new since through-date: {len(new)}")
    if not new:
        print("nothing to do — records already current"); return

    rows, newest = [], through
    for d, label, _eid in new:
        doc = fetch_json(f"{BASE}?dates={d.strftime('%Y%m%d')}")
        fights = parse_card(doc)
        print(f"  {d}  {label:44s} {len(fights):2d} bouts")
        for (ev_name, w, l, method, rnd) in fights:
            rows.append([d.isoformat(), ev_name or label, w, l, method, rnd])
        if fights and d > newest:
            newest = d

    if not rows:
        sys.exit(f"FATAL: {len(new)} new card(s) but zero bouts parsed — ESPN shape changed?")

    os.makedirs(DATA, exist_ok=True)
    seen = set()
    if os.path.exists(DELTA):
        with open(DELTA, newline="") as f:
            for r in csv.reader(f):
                if r: seen.add(tuple(r[:4]))
    added = 0
    write_header = not os.path.exists(DELTA)
    with open(DELTA, "a", newline="") as f:
        wtr = csv.writer(f)
        if write_header:
            wtr.writerow(["event_date", "event", "winner", "loser", "method", "round"])
        for r in rows:
            if tuple(str(x) for x in r[:4]) in seen:
                continue
            wtr.writerow(r); added += 1
    open(STATE, "w").write(newest.isoformat())
    print(f"appended {added} new bout(s); results now through {newest}")

if __name__ == "__main__":
    if "--selftest" in sys.argv: selftest()
    elif "--probe2" in sys.argv: probe2()
    elif "--probe"  in sys.argv: probe()
    else: main()
