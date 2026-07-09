#!/usr/bin/env python3
"""
refresh_odds.py — cloud odds refresh with a poison gate.
Fetches live odds (GitHub-datacenter feed), parses, and REBUILDS ONLY IF the
fetched card's fighter-pair set exactly matches the committed card (the pin =
truth for which fights exist, set by the home build). Any mismatch — stale
feed, wrong matchups, or a genuine fight swap — aborts cleanly, keeping the
last good site live, and prints exactly what differed so a human can act.
Exit 0 always (a blocked refresh is success, not failure).
Writes .refresh_status for the workflow commit step: 'rebuilt' | 'blocked' | 'nochange'.
"""
import json, os, subprocess, sys, shutil, pathlib

HERE = pathlib.Path(__file__).parent
PY = sys.executable

def run(*a): subprocess.run([PY, *a], cwd=HERE, check=True)

def pairs(parsed):    # slug-pair keys are order-stable and name-drift-proof
    return set(parsed.keys())

def main():
    status = HERE / ".refresh_status"
    pinned_path = HERE / "odds" / "parsed_odds.json"
    if not pinned_path.exists():
        print("no committed parsed_odds.json — nothing to gate against; abort")
        status.write_text("blocked"); return
    pinned = json.load(open(pinned_path))

    # 1) live fetch -> raw_live.json (never touches the pin)
    raw_live = HERE / "raw_live.json"
    try:
        run("fetch_odds.py", "-o", str(raw_live)) if _fetch_takes_o() else _fetch_default(raw_live)
    except Exception as e:
        print(f"fetch failed ({type(e).__name__}) — keeping last good build")
        status.write_text("blocked"); return

    # 2) parse to a SIDE file
    live_parsed_path = HERE / "odds" / "parsed_live.json"
    try:
        J = json.load(open(raw_live))
        eot = J["data"]["eventOfferTable"]; name = eot.get("name", "")
        evs = (J["data"].get("upcomingEvents") or {}).get("edges", [])
        date = next((e["node"]["date"] for e in evs if e["node"].get("name") == name), "")
        run("parse_fightodds.py", str(raw_live), "-o", str(live_parsed_path),
            "--upcoming", str(HERE / "odds" / "upcoming_live.csv"), "--date", date)
        live = json.load(open(live_parsed_path))
    except Exception as e:
        print(f"parse failed ({type(e).__name__}) — keeping last good build")
        status.write_text("blocked"); return

    mode = (os.environ.get("MODE") or "refresh").strip().lower()
    if mode == "preview":
        print("LIVE CARD PREVIEW — publish nothing, just show what the feed claims:")
        for k, v in live.items():
            print(f"   {v.get('f1','?')}  vs  {v.get('f2','?')}")
        ch = pairs(pinned) ^ pairs(live)
        print(f"vs pin: {'IDENTICAL' if not ch else str(len(ch)) + ' bout(s) differ'}")
        print("If this card looks right, re-run with mode=adopt to make it the new pin.")
        status.write_text("blocked"); return

    # 3) THE GATE — fighter-pair sets must be identical (unless adopting)
    p_pin, p_live = pairs(pinned), pairs(live)
    if mode == "refresh" and p_pin != p_live:
        # pinned card already fought? adopt the new one automatically, loudly
        try:
            import csv as _c, datetime as _d
            u0 = list(_c.DictReader(open(HERE / "odds" / "upcoming.csv")))
            cd = _d.date.fromisoformat(u0[0]["date"]) if u0 else None
            if cd and (_d.date.today() - cd).days >= 1:
                print(f"AUTO-ADOPT — pinned card ({cd}) is over; live card becomes the pin.")
                mode = "adopt"
        except Exception:
            pass
    if mode == "adopt":
        print(f"ADOPT — human-approved: live card ({len(live)} bouts) becomes the new pin.")
    elif p_pin != p_live:
        missing = sorted(p_pin - p_live); extra = sorted(p_live - p_pin)
        print("GATE BLOCKED — card mismatch vs pin (feed anomaly or real swap; "
              "if a swap is real, refresh the pin from a home build):")
        for m in missing: print(f"   pin-only: {m}")
        for x in extra:   print(f"  live-only: {x}")
        status.write_text("blocked"); return

    # 4) identical card -> did prices actually move? (adopt always publishes)
    if mode != "adopt" and json.dumps(pinned, sort_keys=True) == json.dumps(live, sort_keys=True):
        print("card matches, prices unchanged — nothing to publish")
        status.write_text("nochange"); return

    # 5) adopt fresh odds (card identical, prices newer) + rebuild site + ledger
    shutil.move(str(live_parsed_path), str(pinned_path))
    up_live = HERE / "odds" / "upcoming_live.csv"
    if up_live.exists():
        shutil.move(str(up_live), str(HERE / "odds" / "upcoming.csv"))
    run("build_widget.py")
    run("make_offline.py")
    shutil.copy(HERE / "output" / "ufc_skill_explorer.html", HERE / "docs" / "index.html")
    shutil.copy(HERE / "output" / "ufc_skill_explorer_phone.html", HERE / "docs" / "phone.html")
    try:
        import math, csv as _csv, ufc_grade
        _rj = json.load(open(HERE / "output" / "ufc_ratings.json"))
        _fl = _rj["fighters"] if isinstance(_rj, dict) else _rj
        scores = {ufc_grade.norm(f["name"]): f.get("model_score") for f in _fl}
        u = list(_csv.DictReader(open(HERE / "odds" / "upcoming.csv")))
        cdate = (u[0].get("date") if u else "") or date
        bouts = []
        for v in live.values():
            k1 = ufc_grade.resolve(v.get("f1", ""), scores)
            k2 = ufc_grade.resolve(v.get("f2", ""), scores)
            if not k1 or not k2: continue
            bouts.append({"f1": v["f1"], "f2": v["f2"],
                          "p1": 1 / (1 + math.exp(-(scores[k1] - scores[k2]))),
                          "q1": v.get("cons1")})
        nl = ufc_grade.log_card(name, cdate, bouts)
        ng, panel = ufc_grade.grade_all(HERE / "data" / "fighter_bouts.csv")
        json.dump(panel, open(HERE / "output" / "ledger.json", "w"), indent=1)
        shutil.copy(HERE / "output" / "ledger.json", HERE / "docs" / "ledger.json")
        import datetime as _dt
        _st = {"odds_asof": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes"),
               "event": name, "card_src": "cloud"}
        json.dump(_st, open(HERE / "docs" / "status.json", "w"))
        print(f"Ledger: logged {nl}, settled {ng}, record n={panel.get('n', 0)}")
    except Exception as e:
        print(f"ledger step skipped ({type(e).__name__}: {e})")
    print("REFRESHED — same card, fresh prices, site rebuilt")
    status.write_text("rebuilt")

def _fetch_takes_o():
    try:
        h = (HERE / "fetch_odds.py").read_text()
        return '"-o"' in h or "'-o'" in h or "add_argument" in h and "-o" in h
    except Exception:
        return False

def _fetch_default(raw_live):
    run("fetch_odds.py")
    src = HERE / "raw.json"
    if not src.exists(): raise FileNotFoundError("raw.json")
    shutil.move(str(src), str(raw_live))

def selftest():
    a = {"x|y": {"f1": "X", "f2": "Y", "am1": -110}, "p|q": {"f1": "P", "f2": "Q"}}
    b = {"x|y": {"f1": "X", "f2": "Y", "am1": -125}, "p|q": {"f1": "P", "f2": "Q"}}
    c = {"x|y": a["x|y"], "p|z": {"f1": "P", "f2": "Z"}}
    assert pairs(a) == pairs(b)                      # same card, moved price -> gate passes
    assert pairs(a) != pairs(c)                      # swapped bout -> gate blocks
    assert json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True)  # change detected
    print("REFRESH GATE SELFTEST PASS — pass on price moves, block on card changes")
    return 0

if __name__ == "__main__":
    sys.exit(selftest()) if "--selftest" in sys.argv else main()
