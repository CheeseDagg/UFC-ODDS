#!/usr/bin/env python3
"""Build-time integrity guard. Checks the always-valid invariants of the shipped
data so a future code change can't silently corrupt the tool. Run automatically at
the end of build_widget; also runnable standalone (`python3 validate_build.py`).

These are invariants that must hold REGARDLESS of data updates — so it does NOT
hardcode the rated-set hash (that legitimately changes when new fights are added).
Exits non-zero if any hard invariant fails, so an autonomous rebuild surfaces the
problem instead of shipping a broken tool.
"""
import json, math, sys
from pathlib import Path
from collections import Counter

OUT = Path(__file__).parent / "output"
AX = ["Striking", "StrikingDefense", "Wrestling", "Grappling", "Power", "Chin", "Cardio"]


def validate():
    errs, warns = [], []
    R = json.loads((OUT / "ufc_ratings.json").read_text())
    F, P = R["fighters"], R["prospects"]
    wd = json.loads((OUT / "widget_data.json").read_text())

    # ---- rated fighters ----
    if not F:
        errs.append("no rated fighters")
    # ratings in range, only Cardio may be null
    oor = [(f["name"], a, f["ratings"].get(a)) for f in F for a in AX
           if f["ratings"].get(a) is not None and not (0 <= f["ratings"][a] <= 100)]
    if oor:
        errs.append(f"{len(oor)} rated axis ratings outside 0-100, e.g. {oor[:3]}")
    nn = [(f["name"], a) for f in F for a in AX
          if a != "Cardio" and f["ratings"].get(a) is None]
    if nn:
        errs.append(f"{len(nn)} null non-Cardio rated axes, e.g. {nn[:3]}")
    # unique names
    dups = [n for n, c in Counter(f["name"] for f in F).items() if c > 1]
    if dups:
        errs.append(f"{len(dups)} duplicate rated names: {dups[:5]}")
    # every rated fighter scoreable + has a record + a real division
    noscore = [f["name"] for f in F if f.get("model_score") is None]
    if noscore:
        errs.append(f"{len(noscore)} rated fighters missing model_score, e.g. {noscore[:3]}")
    norec = [f["name"] for f in F if not f.get("record")]
    if norec:
        errs.append(f"{len(norec)} rated fighters missing record, e.g. {norec[:3]}")
    unkdiv = [f["name"] for f in F if f.get("division") in (None, "", "Unknown")]
    if unkdiv:
        errs.append(f"{len(unkdiv)} rated fighters with Unknown division, e.g. {unkdiv[:3]}")
    # model_score range sanity (logit units; should be a few SD, not exploded)
    ms = [f["model_score"] for f in F if f.get("model_score") is not None]
    if ms and (min(ms) < -6 or max(ms) > 6):
        errs.append(f"model_score out of sane logit range [{min(ms):.2f},{max(ms):.2f}]")
    # every matchup probability is a valid 0-1
    if len(ms) >= 2:
        p = 1 / (1 + math.exp(-(max(ms) - min(ms))))
        if not (0 < p < 1):
            errs.append("win probability not in (0,1)")
        if p > 0.99:
            warns.append(f"most-lopsided matchup is {p:.1%} — unusually confident; check temperature")

    # ---- prospects ----
    pbad = [(p["name"], a, p["ratings"].get(a)) for p in P for a in AX
            if p["ratings"].get(a) is not None and not (0 <= p["ratings"][a] <= 120)]
    if pbad:
        errs.append(f"{len(pbad)} prospect ratings wildly out of range, e.g. {pbad[:3]}")

    # ---- regional résumé must be CLEAN (UFC fights excluded) ----
    reg = wd.get("regional", {})
    if reg:
        nopre = [k for k, v in reg.items() if v.get("pre_bouts") is None]
        if nopre:
            errs.append(f"{len(nopre)} regional entries missing pre_bouts (clean-RRS not applied)")
        # big_league strings should parse as W-L of non-negative ints
        try:
            bad_bl = [k for k, v in reg.items() if v.get("big_league")
                      and any(int(x) < 0 for x in str(v["big_league"]).split("-")[:2])]
            if bad_bl:
                errs.append(f"{len(bad_bl)} regional big_league records malformed/negative")
        except Exception as e:
            warns.append(f"could not validate regional big_league: {e}")

    # ---- calibration (honest reliability diagram) ----
    cal = wd.get("calibration") or {}
    if not cal.get("buckets"):
        warns.append("no calibration buckets baked in")
    else:
        if not (0.5 <= cal.get("acc", 0) <= 0.75):
            warns.append(f"calibration acc {cal.get('acc')} outside expected 0.50-0.75")
        if not (0.18 <= cal.get("brier", 1) <= 0.27):
            warns.append(f"calibration Brier {cal.get('brier')} outside expected 0.18-0.27")
        # buckets monotonic-ish and within-bucket gap not extreme
        big = [b for b in cal["buckets"] if b["n"] >= 30 and abs(b["actual"] - b["pred"]) > 0.12]
        if big:
            warns.append(f"{len(big)} well-populated calibration buckets miss by >12pts")

    # ---- upcoming card present & well-formed ----
    up = wd.get("upcoming") or {}
    ub = up.get("bouts") or []
    if ub:
        empty = [i for i, b in enumerate(ub) if not (b.get("r") and b.get("b"))]
        if empty:
            errs.append(f"{len(empty)} upcoming bouts missing a fighter name")

    return errs, warns, len(F), len(P)


def main(strict=True):
    errs, warns, nf, npr = validate()
    print(f"[validate] {nf} rated + {npr} prospects checked")
    for w in warns:
        print(f"  ! WARN: {w}")
    if errs:
        print(f"  \u2717 {len(errs)} INTEGRITY ERROR(S):")
        for e in errs:
            print(f"      - {e}")
        if strict:
            print("[validate] BUILD INTEGRITY FAILED")
            sys.exit(2)
    else:
        print(f"[validate] OK \u2014 all integrity invariants hold"
              + (f" ({len(warns)} warning(s))" if warns else ""))
    return len(errs)


if __name__ == "__main__":
    main(strict="--soft" not in sys.argv)
