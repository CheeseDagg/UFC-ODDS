#!/usr/bin/env python3
"""Build the hosted tool: fetch -> parse (regenerate card) -> build_widget ->
make_offline -> docs/. Run with --local to skip the live fetch and reuse an
existing raw.json (used for testing / offline rebuilds)."""
import json, subprocess, shutil, sys, pathlib
HERE = pathlib.Path(__file__).parent
PY_ = sys.executable
def run(*args):
    subprocess.run([PY_, *args], cwd=HERE, check=True)
def main():
    local = "--local" in sys.argv
    raw = HERE / "raw.json"
    # PIN OVERRIDE: if a home-pulled fightodds_raw.json is committed, build from it
    # and skip the live fetch entirely. This sidesteps the GitHub datacenter-IP
    # feed degradation (stale/wrong matchups served to GH's IP). Drop the file in
    # to pin a card; delete it to let the daily auto-refresh resume.
    pin = HERE / "fightodds_raw.json"
    if pin.exists():
        print(f">> PINNED: building from committed {pin.name} (live fetch skipped).")
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
        bouts = []
        for v in card.values():
            k1 = ufc_grade.resolve(v.get("f1", ""), scores)
            k2 = ufc_grade.resolve(v.get("f2", ""), scores)
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
if __name__ == "__main__":
    main()
