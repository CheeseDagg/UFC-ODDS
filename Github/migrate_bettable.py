#!/usr/bin/env python3
"""One-time migration: bring a committed parsed_odds.json onto the CURRENT contract.

Two things changed in the pipeline after this pin was written, and the pin is the
only copy of the card that exists here (the fightodds.io feed answers 403 from
this container, and no raw.json survived). Both fixes live in parse_fightodds and
reconcile, so every future fetch gets them for free; this re-derives them for the
one file that predates them.

  1. IDENTITY. reconcile.match_pref used to let the feed's free-text display name
     override the ID-backed slug when the two named different people. It was wrong
     in all three cases on record, and the pin is carrying one of them:
     'Billy Quarantillo vs Cezar Ferreira' beside slug 'carlos-diego-ferreira-3134'
     -- a middleweight who last fought in 2019 standing in for the lightweight who
     is actually in the cage. Every model path now resolves this correctly, but the
     site reads the pin, so the wrong man was still being published. Re-running
     reconcile_odds over the stored slugs fixes the names AND the pair keys the
     template looks bouts up by; odds/upcoming.csv is rewritten to agree, because a
     key the card CSV cannot reproduce is a bout with no odds attached.

  2. BETTABLE. parse_fightodds now restricts best1/best2 to books the bet can actually be
placed at (BETTABLE) and publishes the old all-books number separately as
any1/any2. The pinned odds file on disk predates that change: its best1/best2 are
still "highest number anywhere in the 20-book feed", which on the Aug 8 card made
18 of 18 headline prices unplaceable.

The feed is not reachable from here, so rather than leave a stale pin quoting
Caesars and Polymarket as "your price" until the next successful fetch, this
recomputes the fields in place from the per-book lines already stored in the
file's own `books` array (which parse writes from the same cleaned `good` set the
best-price calculation uses).

Caveat stated out loud: `books` only contains rows that priced BOTH sides, so a
book that posted one side only is invisible here. That cannot change best1/best2
for FanDuel (it prices both sides or neither), and it can only move the median
used for shop1/shop2 by one row. Everything the next real fetch writes will be
computed by parse_fightodds itself; this is a bridge, not a second code path.

Idempotent. Run: python3 migrate_bettable.py odds/parsed_odds.json
"""
import csv, json, statistics, sys, pathlib

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from parse_fightodds import BETTABLE, am_to_p, p_to_am, nm
import reconcile as _rec


def reconcile_pin(d, roster_path=HERE / "output" / "ufc_ratings.json",
                  card_path=HERE / "odds" / "upcoming.csv"):
    """Re-run name reconciliation over an already-parsed odds dict, in place.

    This is the same call parse_fightodds makes (reconcile_odds with the same nm),
    so it is not a second identity policy -- it is the existing one applied to a
    file that was written before the policy was fixed.

    The card CSV is rewritten from the SAME result rather than reconciled
    separately, because upcoming.csv has no slug columns: reconcile_card can only
    see the free-text display name, which is precisely the string that lied. The
    odds dict does carry slugs, so the corrected name is only derivable there, and
    the CSV has to be told. Rows are matched to bouts on the OLD pair key, which is
    exactly what the CSV was written from.

    A bout whose fighter changed also loses its weight class: the old value was
    attached to a different human. It is refilled from the two corrected fighters'
    divisions using the same agree/disagree rule as reconcile_card, and left blank
    when neither resolves rather than carrying the stranger's division forward."""
    if not pathlib.Path(roster_path).exists():
        print(f"  ! no roster at {roster_path} — names left as-is")
        return d, {}
    rec = _rec.Reconciler(_rec.load_roster(roster_path))
    # Same two calls reconcile_odds makes, done here so the OLD key stays in hand:
    # reconcile_odds returns a dict re-keyed on the new names and drops the mapping,
    # and the mapping is the only thing that can find the matching card-CSV row.
    out, renamed = {}, {}
    for v in d.values():
        o1, o2 = v.get("f1", ""), v.get("f2", "")
        f1, _d1 = rec.match_pref(o1, v.get("f1_slug", ""))
        f2, _d2 = rec.match_pref(o2, v.get("f2_slug", ""))
        v = dict(v)
        v["f1"], v["f2"] = f1, f2
        out["|".join(sorted([nm(f1), nm(f2)]))] = v
        if _rec._norm(o1) != _rec._norm(f1) or _rec._norm(o2) != _rec._norm(f2):
            renamed["|".join(sorted([nm(o1), nm(o2)]))] = (o1, o2, f1, f2)
            print(f"  identity: {o1} vs {o2}  ->  {f1} vs {f2}")
    if len(out) != len(d):
        print(f"  ! WARNING: {len(d)} bouts collapsed to {len(out)} after renaming — "
              f"two bouts now key to the same pair; NOT rewriting the card CSV")
        return out, {}
    if not renamed:
        print("  identity: no bout changed fighter (already reconciled)")
        return out, renamed
    cp = pathlib.Path(card_path)
    if not cp.exists():
        print(f"  ! {cp} missing — card CSV NOT updated; the site will look these "
              f"bouts up under the old key and find no odds")
        return out, renamed
    rows = list(csv.DictReader(open(cp)))
    hdr = ["date", "location", "R_fighter", "B_fighter", "weight_class",
           "title_bout", "section"]
    n = 0
    for r in rows:
        okey = "|".join(sorted([nm(r["R_fighter"]), nm(r["B_fighter"])]))
        if okey not in renamed:
            continue
        o1, o2, f1, f2 = renamed[okey]
        # Keep the CSV's own R/B orientation. The odds file's f1/f2 order is not the
        # card's, so each side is mapped by which ORIGINAL string it came from --
        # read off the pre-edit values, not the ones just assigned.
        rf, bf = r["R_fighter"], r["B_fighter"]
        r["R_fighter"] = f1 if _rec._norm(rf) == _rec._norm(o1) else f2
        r["B_fighter"] = f2 if _rec._norm(rf) == _rec._norm(o1) else f1
        d1, d2 = rec.div.get(r["R_fighter"]), rec.div.get(r["B_fighter"])
        was = r["weight_class"]
        if d1 and d2:
            r["weight_class"] = d1 if d1 == d2 else (
                d1 if rec.bouts.get(r["R_fighter"], 0) >= rec.bouts.get(r["B_fighter"], 0) else d2)
        else:
            r["weight_class"] = d1 or d2 or ""
        print(f"  card CSV: {o1} vs {o2} [{was}]  ->  "
              f"{r['R_fighter']} vs {r['B_fighter']} [{r['weight_class'] or 'wc?'}]")
        n += 1
    with open(cp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=hdr)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in hdr})
    print(f"  card CSV: {n} of {len(rows)} row(s) rewritten -> {cp}")
    return out, renamed


def migrate(path):
    p = pathlib.Path(path)
    d = json.load(open(p))
    d, _ = reconcile_pin(d)
    changed = 0
    for k, v in d.items():
        books = v.get("books") or []
        if not books:
            continue
        c1 = [(a1, b) for b, a1, a2 in books if a1 is not None and b in BETTABLE]
        c2 = [(a2, b) for b, a1, a2 in books if a2 is not None and b in BETTABLE]
        best1, best1book = (max(c1, key=lambda x: x[0]) if c1 else (None, None))
        best2, best2book = (max(c2, key=lambda x: x[0]) if c2 else (None, None))
        o1 = [(a1, b) for b, a1, a2 in books if a1 is not None]
        o2 = [(a2, b) for b, a1, a2 in books if a2 is not None]
        any1, any1book = (max(o1, key=lambda x: x[0]) if o1 else (None, None))
        any2, any2book = (max(o2, key=lambda x: x[0]) if o2 else (None, None))

        med1 = statistics.median([am_to_p(a1) for b, a1, a2 in books if a1 is not None])
        med2 = statistics.median([am_to_p(a2) for b, a1, a2 in books if a2 is not None])

        was = (v.get("best1"), v.get("best2"), v.get("best1book"), v.get("best2book"))
        v["best1"], v["best2"] = best1, best2
        v["best1book"], v["best2book"] = best1book, best2book
        v["any1"], v["any2"] = any1, any2
        v["any1book"], v["any2book"] = any1book, any2book
        v["med1am"], v["med2am"] = p_to_am(med1), p_to_am(med2)
        v["shop1"] = round(med1 - am_to_p(best1), 4) if best1 is not None else None
        v["shop2"] = round(med2 - am_to_p(best2), 4) if best2 is not None else None
        now = (best1, best2, best1book, best2book)
        if was != now:
            changed += 1
            print(f"  {v.get('f1','?')} vs {v.get('f2','?')}")
            print(f"    best was {was[0]} ({was[2]}) / {was[1]} ({was[3]})"
                  f"  ->  {now[0]} ({now[2]}) / {now[1]} ({now[3]})")
    json.dump(d, open(p, "w"), indent=1)
    print(f"{changed} of {len(d)} bouts had an unplaceable headline price; {p} rewritten.")
    return 0


if __name__ == "__main__":
    sys.exit(migrate(sys.argv[1] if len(sys.argv) > 1 else "odds/parsed_odds.json"))
