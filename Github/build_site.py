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
    shutil.copy(HERE / "output" / "ufc_skill_explorer.html", HERE / "docs" / "index.html")
    shutil.copy(HERE / "output" / "ufc_skill_explorer_phone.html", HERE / "docs" / "phone.html")
    # tiny redirect so phones get the mobile layout automatically
    (HERE / "docs" / ".nojekyll").write_text("")
    print("Built docs/index.html  +  docs/phone.html")
if __name__ == "__main__":
    main()
