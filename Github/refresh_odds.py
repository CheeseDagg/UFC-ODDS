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
    auto_adopted = False
    if mode == "refresh" and p_pin != p_live:
        # pinned card already fought? adopt the new one automatically, loudly
        try:
            import csv as _c, datetime as _d
            u0 = list(_c.DictReader(open(HERE / "odds" / "upcoming.csv")))
            cd = _d.date.fromisoformat(u0[0]["date"]) if u0 else None
            if cd and (_d.date.today() - cd).days >= 1:
                print(f"AUTO-ADOPT — pinned card ({cd}) is over; live card becomes the pin.")
                mode = "adopt"; auto_adopted = True
        except Exception as _e:
            # This was `except Exception: pass`. A malformed or missing
            # upcoming.csv left mode at "refresh" with no message at all, so a
            # blocked build looked like a card mismatch rather than a broken file.
            print(f"  ! auto-adopt check skipped ({type(_e).__name__}: {_e}) — "
                  f"card-date unknown, staying in refresh mode")
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
    #
    # PRICES ARE NOT THE ONLY BUILD INPUT. On 2026-08-13 a template change
    # (the method-split/durability panel) sat unpublished behind this check:
    # odds were byte-identical, so the rebuild was skipped and the new panel
    # could not reach readers until the market happened to move -- the
    # 259-hours bug mirrored, with the template in the odds' role. So the
    # decision now hashes the RENDER INPUTS too: a build ships when prices
    # moved OR when the code that turns prices into the page did.
    import hashlib as _hl
    _tpl = _hl.sha256()
    for _f in ("ufc_skill_explorer_template.html", "build_widget.py",
               "build_site.py", "make_offline.py"):
        try:
            _tpl.update((HERE / _f).read_bytes())
        except Exception:
            _tpl.update(b"absent")
    _tpl = _tpl.hexdigest()[:16]
    _tpl_path = HERE / "odds" / ".template_hash"
    _tpl_old = _tpl_path.read_text().strip() if _tpl_path.exists() else ""
    if mode != "adopt" and json.dumps(pinned, sort_keys=True) == json.dumps(live, sort_keys=True):
        if _tpl == _tpl_old:
            print("card matches, prices unchanged, template unchanged — nothing to publish")
            status.write_text("nochange"); return
        print(f"card matches and prices are unchanged, but the RENDER INPUTS "
              f"changed ({_tpl_old or 'none'} -> {_tpl}) — rebuilding so the "
              f"template reaches readers without waiting for the market to move")
    _tpl_path.write_text(_tpl)

    # 5) adopt fresh odds (card identical, prices newer) + rebuild site + ledger
    shutil.move(str(live_parsed_path), str(pinned_path))
    up_live = HERE / "odds" / "upcoming_live.csv"
    if up_live.exists():
        shutil.move(str(up_live), str(HERE / "odds" / "upcoming.csv"))
    # Stamp the fetch time BEFORE the build. build_widget now reads odds_asof out
    # of this file for the "Odds imported <date>" line; it used to read the odds
    # file's mtime, which under actions/checkout is always the build time, so the
    # label could never say anything but "today" no matter how old the prices were.
    # Written here rather than in the ledger block below because the ledger block
    # runs AFTER the build and is wrapped in a try -- a ledger failure must not
    # cost the site its freshness stamp.
    import datetime as _dt0
    _stp = HERE / "docs" / "status.json"
    _prev = {}
    try:
        _prev = json.loads(_stp.read_text())
    except Exception:
        pass
    _prev["odds_asof"] = _dt0.datetime.now(_dt0.timezone.utc).isoformat(timespec="minutes")
    # "auto" is the value the site's freshness pill warns on. Nothing ever wrote
    # it before, so the auto-adopt warning in the template was dead code and an
    # unreviewed card swap published looking exactly like a routine price refresh.
    _prev["card_src"] = "auto" if auto_adopted else "cloud"
    json.dump(_prev, open(_stp, "w"))
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
        # Same temperature the site and build_site.py use. Before this, the
        # refresh path logged bouts on a bare sigmoid (T=1) while the ledger it
        # wrote into was being compared against a market that prices real gaps.
        import ufc_temperature
        _T, _ = ufc_temperature.load_T(HERE / "output" / "temperature.json")
        # THE SLUG GUARD. build_site.py has had this since 2026-08-01; this path
        # did not -- and this path is the one on cron (0 11,17,23 * * *) plus the
        # Friday burst, so it is the DOMINANT ledger writer. Without the guard it
        # resolved the odds feed's free-text display name straight to a rating:
        # the Aug 8 card shipped f2='Cezar Ferreira' beside slug
        # 'carlos-diego-ferreira-3134' and logged Quarantillo as a 56.4% favourite
        # over a middleweight who last fought in 2019. Against Diego Ferreira --
        # the man actually in the cage -- he is a 30.3% underdog. That row could
        # never even grade: ESPN reports the real name, nothing matches, silent
        # void at 14 days. The error would have vanished instead of showing up
        # as a loss, which is the worst way for a model to be wrong.
        # resolve_bout_name = _trusted_name + the middle-name retry, so a slug that
        # wins the swap ('carlos-diego-ferreira-3134') still lands on the rating
        # instead of failing resolve() and dropping the bout silently.
        from ufc_blend_predict import resolve_bout_name
        bouts = []
        for v in live.values():
            k1 = resolve_bout_name(v.get("f1", ""), v.get("f1_slug"), scores)
            k2 = resolve_bout_name(v.get("f2", ""), v.get("f2_slug"), scores)
            if not k1 or not k2: continue
            bouts.append({"f1": v["f1"], "f2": v["f2"],
                          "p1": round(ufc_temperature.prob(scores[k1], scores[k2], _T), 4),
                          "q1": v.get("cons1")})
        nl = ufc_grade.log_card(name, cdate, bouts)
        ng, panel = ufc_grade.grade_all(HERE / "data" / "fighter_bouts.csv")
        json.dump(panel, open(HERE / "output" / "ledger.json", "w"), indent=1)
        shutil.copy(HERE / "output" / "ledger.json", HERE / "docs" / "ledger.json")
        # Merge, do not overwrite. This block used to rebuild status.json from
        # scratch with card_src hardcoded to "cloud", which stamped over the
        # "auto" flag an unreviewed card swap had just set, and re-stamped
        # odds_asof after the build had already read it.
        _prev["event"] = name
        json.dump(_prev, open(_stp, "w"))
        print(f"Ledger: logged {nl}, settled {ng}, record n={panel.get('n', 0)}")
    except Exception as e:
        # Loud, with a traceback. This used to print one grey line and then
        # write status "rebuilt" anyway, so a ledger that silently stopped
        # recording looked identical to one that was working -- and the whole
        # point of the ledger is to catch the model being wrong.
        import traceback
        print("!! LEDGER STEP FAILED — the forward record did NOT update this run")
        print(f"!! {type(e).__name__}: {e}")
        traceback.print_exc()
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
