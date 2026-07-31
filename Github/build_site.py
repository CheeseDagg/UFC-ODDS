#!/usr/bin/env python3
"""Build the hosted tool: fetch -> parse (regenerate card) -> build_widget ->
make_offline -> docs/. Run with --local to skip the live fetch and reuse an
existing raw.json (used for testing / offline rebuilds)."""
import json, subprocess, shutil, sys, pathlib, datetime as dt
HERE = pathlib.Path(__file__).parent
PY_ = sys.executable
FLAGS = {"--local", "--selftest"}
PIN_GRACE_DAYS = 1          # a pin stays usable through the day after its card
def run(*args):
    subprocess.run([PY_, *args], cwd=HERE, check=True)


def pin_card(pin_path):
    """-> (name, date) of the card a pinned raw.json prices; ('','') if unreadable."""
    try:
        J = json.load(open(pin_path))
        name = (J["data"]["eventOfferTable"].get("name") or "")
        evs = (J["data"].get("upcomingEvents") or {}).get("edges", [])
        return name, next((e["node"]["date"] for e in evs
                           if e["node"].get("name") == name), "") or ""
    except Exception:
        return "", ""


def pin_is_stale(pin_date, today, grace_days=PIN_GRACE_DAYS):
    """True when a pinned feed prices a card that has already happened.

    THE BUG THIS CLOSES. fightodds_raw.json is a manual override: a home-pulled
    feed committed to sidestep the datacenter-IP degradation GitHub Actions
    hits. It had no expiry. The copy in the repo priced UFC 329 (2026-07-11),
    two cards in the past, and because the override runs BEFORE the live fetch,
    every build -- the nightly workflow included -- regenerated
    odds/parsed_odds.json and odds/upcoming.csv back to that dead card, silently
    replacing the live 2026-08-01 board. A pin that cannot expire is not a pin,
    it is a freeze.

    An unreadable or undated pin counts as stale. Refusing to build from a file
    we cannot date is the safe direction: the cost is one live fetch, while the
    cost of trusting it is overwriting the current card with an unknown one."""
    if not pin_date:
        return True
    try:
        d = dt.date.fromisoformat(str(pin_date)[:10])
    except ValueError:
        return True
    return d < today - dt.timedelta(days=grace_days)


def main():
    bad = [a for a in sys.argv[1:] if a not in FLAGS]
    if bad:
        # Silently ignoring an unknown flag once cost a real card: `build_site.py
        # --selftest` was assumed to be a no-op check and instead ran a full
        # build, clobbering the live odds files. Unknown args now stop the build.
        sys.exit(f"unknown argument(s): {' '.join(bad)}\nusage: build_site.py "
                 f"[--local] [--selftest]")
    if "--selftest" in sys.argv:
        return selftest()
    local = "--local" in sys.argv
    raw = HERE / "raw.json"
    # PIN OVERRIDE: if a home-pulled fightodds_raw.json is committed, build from it
    # and skip the live fetch entirely. This sidesteps the GitHub datacenter-IP
    # feed degradation (stale/wrong matchups served to GH's IP). Drop the file in
    # to pin a card; delete it to let the daily auto-refresh resume. A pin whose
    # card has already been fought is ignored -- see pin_is_stale.
    pin = HERE / "fightodds_raw.json"
    if pin.exists():
        pname, pdate = pin_card(pin)
        if pin_is_stale(pdate, dt.date.today()):
            print(f">> PIN IGNORED: {pin.name} prices "
                  f"{pname or '(unreadable)'} [{pdate or 'undated'}], already "
                  f"fought. Using the live fetch instead; delete the file to "
                  f"silence this.")
            if not local:
                run("fetch_odds.py")
        else:
            print(f">> PINNED: building from committed {pin.name} "
                  f"({pname} {pdate}); live fetch skipped.")
            shutil.copy(pin, raw)
    elif not local:
        run("fetch_odds.py")
    if not raw.exists():
        sys.exit("no raw.json (commit fightodds_raw.json, or run without --local to fetch)")
    (HERE / "odds").mkdir(exist_ok=True)
    (HERE / "docs").mkdir(exist_ok=True)
    J = json.load(open(raw))
    eot = J["data"]["eventOfferTable"]; name = eot.get("name", "")
    evs = (J["data"].get("upcomingEvents") or {}).get("edges", [])
    date = next((e["node"]["date"] for e in evs if e["node"].get("name") == name), "")
    print(f"Card: {name}  date={date or '(unknown)'}")
    run("parse_fightodds.py", "raw.json", "-o", "odds/parsed_odds.json",
        "--upcoming", "odds/upcoming.csv", "--date", date)
    run("build_widget.py")
    run("make_offline.py")
    # ---- forward ledger: log this card's model+market, settle prior cards ----
    try:
        import math, csv as _csv, ufc_grade
        _rj = json.load(open(HERE / "output" / "ufc_ratings.json"))
        _fl = _rj["fighters"] if isinstance(_rj, dict) else _rj
        scores = {ufc_grade.norm(f["name"]): f.get("model_score") for f in _fl}
        card = json.load(open(HERE / "odds" / "parsed_odds.json"))
        u = list(_csv.DictReader(open(HERE / "odds" / "upcoming.csv")))
        cdate = (u[0].get("date") if u else "") or date
        # The odds feed's display name is free text and is occasionally simply
        # the wrong fighter, while the slug beside it is keyed on the site's own
        # ID. _trusted_name prefers the slug when the two name different people;
        # the bad name then fails to resolve, s1 is None, and the bout is left
        # out of the ledger rather than logged against a stranger's record.
        # (2026-08-01 shipped f2='Charles Oliveira' with slug
        # 'michael-oliveira-50272' -- a former champion priced into a fight he
        # was not in.)
        from ufc_blend_predict import _trusted_name
        bouts = []
        for v in card.values():
            k1 = ufc_grade.resolve(_trusted_name(v.get("f1", ""), v.get("f1_slug")), scores)
            k2 = ufc_grade.resolve(_trusted_name(v.get("f2", ""), v.get("f2_slug")), scores)
            s1 = scores.get(k1) if k1 else None
            s2 = scores.get(k2) if k2 else None
            if s1 is None or s2 is None: continue
            bouts.append({"f1": v["f1"], "f2": v["f2"],
                          "p1": 1 / (1 + math.exp(-(s1 - s2))),
                          "q1": v.get("cons1")})
        nl = ufc_grade.log_card(name, cdate, bouts)
        ng, panel = ufc_grade.grade_all(HERE / "data" / "fighter_bouts.csv")
        json.dump(panel, open(HERE / "output" / "ledger.json", "w"), indent=1)
        shutil.copy(HERE / "output" / "ledger.json", HERE / "docs" / "ledger.json")
        import datetime as _dt
        _st = {"odds_asof": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="minutes"),
               "event": name, "card_src": "home"}
        json.dump(_st, open(HERE / "docs" / "status.json", "w"))
        msg = f"Ledger: logged {nl} new bouts, settled {ng}; record n={panel.get('n',0)}"
        if panel.get("n"): msg += f", acc {panel['acc']}%, Brier {panel['brier']}"
        if panel.get("market", {}).get("disagree_n") is not None:
            m = panel["market"]
            msg += f" | vs market: {m['disagree_n']} disagreements"
            if m.get("disagree_model_right") is not None:
                msg += f", model right {m['disagree_model_right']}%"
        print(msg)
    except Exception as e:
        print(f"Ledger step skipped ({type(e).__name__}: {e})")
    shutil.copy(HERE / "output" / "ufc_skill_explorer.html", HERE / "docs" / "index.html")
    shutil.copy(HERE / "output" / "ufc_skill_explorer_phone.html", HERE / "docs" / "phone.html")
    # tiny redirect so phones get the mobile layout automatically
    (HERE / "docs" / ".nojekyll").write_text("")
    print("Built docs/index.html  +  docs/phone.html")


def selftest():
    """Offline checks. Touches no odds file and runs no build step -- the whole
    point is that asking this script to check itself never rebuilds anything."""
    ok = [0, 0]

    def chk(c, msg):
        ok[1] += 1
        ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + msg)

    import tempfile, os
    today = dt.date(2026, 7, 23)
    chk(pin_is_stale("2026-07-11", today), "a pin two cards in the past is stale")
    chk(not pin_is_stale("2026-08-01", today), "a pin for the next card is live")
    chk(not pin_is_stale("2026-07-23", today), "a pin for today's card is live")
    chk(not pin_is_stale("2026-07-22", today), "a pin one day past is inside the grace day")
    chk(pin_is_stale("2026-07-21", today), "a pin two days past is stale")
    chk(pin_is_stale("", today), "an undated pin is treated as stale, not trusted")
    chk(pin_is_stale("not-a-date", today), "an unparseable pin date is treated as stale")

    tmp = tempfile.mkdtemp()
    good = os.path.join(tmp, "pin.json")
    json.dump({"data": {"eventOfferTable": {"name": "UFC 400: A vs. B"},
                        "upcomingEvents": {"edges": [
                            {"node": {"name": "UFC 399", "date": "2026-07-11"}},
                            {"node": {"name": "UFC 400: A vs. B", "date": "2026-08-01"}}]}}},
              open(good, "w"))
    chk(pin_card(good) == ("UFC 400: A vs. B", "2026-08-01"),
        "pin_card reads the priced card's name and date")
    junk = os.path.join(tmp, "junk.json")
    open(junk, "w").write("not json")
    chk(pin_card(junk) == ("", ""), "an unreadable pin yields no name/date")
    chk(pin_is_stale(pin_card(junk)[1], today),
        "an unreadable pin therefore never overrides the live fetch")

    # the flag trap: only known flags are accepted, everything else stops the run
    chk(FLAGS == {"--local", "--selftest"}, "flag whitelist is exactly --local/--selftest")

    # the slug guard this build path now shares with the blend
    from ufc_blend_predict import _trusted_name
    chk(_trusted_name("Charles Oliveira", "michael-oliveira-50272") == "michael oliveira",
        "ledger step trusts the ID-backed slug over a wrong display name")
    chk(_trusted_name("Dennis Buzukja", "dennis-buzukia-29076") == "Dennis Buzukja",
        "harmless slug spelling drift does not trip the ledger guard")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
