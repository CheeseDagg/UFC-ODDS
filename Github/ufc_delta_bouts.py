#!/usr/bin/env python3
"""
ufc_delta_bouts.py — fold post-baseline RESULTS into the modelling state.

THE GAP THIS CLOSES
  data/fighter_bouts.csv is a full-stat scrape and it ends 2026-06-14. Every
  card since then lives only in data/results_delta.csv, which the results
  workflow appends after each Saturday. Nothing merged the two:

    * build_widget.apply_results_delta merges the delta into the DISPLAYED
      record only, and says so in its own docstring -- "Rating values are
      deliberately untouched". So output/ufc_ratings.json stays on the
      baseline forever.
    * ufc_blend_predict.build_state_and_data reads fighter_bouts.csv and
      nothing else, so the research blend's Elo, fight counts and layoff
      clocks are all frozen at the baseline too.
    * results_delta.csv IS read by ufc_grade -- but only to SETTLE bets.
      The results graded the ledger and then went in the bin.

  Net effect: the model predicted a card while pretending the last four
  cards never happened. Not a wrong number -- a stale one.

WHAT IS AND IS NOT RECOVERABLE FROM A RESULT ROW
  results_delta carries (date, event, winner, loser, method, round). That is
  enough for:
    won .......... the outcome itself
    lost_by_ko ... method KO/TKO, charged to the loser (feeds ko_losses)
    n ............ the fight happened, so the fight counter advances
    last ......... the layoff clock resets, which is the term most damaged
                   by staleness -- a fighter who fought three weeks ago was
                   being scored as six weeks more rusty than he is
  It is NOT enough for the EMA form terms (strike margin, grappling margin,
  control minutes, submission attempts), which need per-fight stats.

  Those are left ALONE, not zero-filled. A zero would enter the EMA as a
  real observation meaning "fought and did nothing", which is a strong and
  false claim; skipping leaves the EMA at its last genuine value, which is
  merely out of date. Rows carry stats_known=0 to say which case they are.

  Draws and no-contests are dropped: an Elo update needs a binary outcome
  and results_delta stores both corners as the winner for these. They are
  ~1% of bouts and pretending they were wins would be worse than the gap.

Usage
  python3 ufc_delta_bouts.py             # report what would merge
  python3 ufc_delta_bouts.py --selftest  # offline unit checks
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOUTS = os.path.join(HERE, "data", "fighter_bouts.csv")
DELTA = os.path.join(HERE, "data", "results_delta.csv")

# methods that do not produce a binary Elo outcome
NON_DECISIVE = {"Draw", "DRAW", "NC"}


def _pair(d, a, b):
    return (d, tuple(sorted((a, b))))


def _canon(name, keys, resolve, norm):
    """Map a result-row name onto the spelling fighter_bouts uses, so the two
    sources land on ONE state entry. An unresolved name is a genuine debutant
    (verified: all 17 unresolved names across the four post-baseline cards
    have no near-match in the 2678-fighter history) and is kept verbatim."""
    k = resolve(name, keys)
    return keys[norm(k)] if k and norm(k) in keys else (k or name)


def delta_rows(delta_csv=DELTA, bouts_csv=BOUTS, resolve=None, norm=None):
    """-> (rows, report). Mirrored fighter_bouts-shaped dicts for every
    decisive post-baseline bout not already present in fighter_bouts."""
    if resolve is None or norm is None:
        import ufc_grade
        resolve, norm = ufc_grade.resolve, ufc_grade.norm

    have, names, last_bout_date = set(), set(), ""
    if os.path.exists(bouts_csv):
        with open(bouts_csv, newline="") as f:
            for r in csv.DictReader(f):
                names.add(r["fighter"])
                have.add(_pair(r["date"], r["fighter"], r["opp"]))
                if r["date"] > last_bout_date:
                    last_bout_date = r["date"]
    keys = {norm(n): n for n in names}

    rows, skipped, dupes, debut = [], 0, 0, set()
    seen_pairs = set()
    if os.path.exists(delta_csv):
        with open(delta_csv, newline="") as f:
            for r in csv.DictReader(f):
                d = (r.get("event_date") or "").strip()
                w, l = (r.get("winner") or "").strip(), (r.get("loser") or "").strip()
                meth = (r.get("method") or "").strip()
                if not (d and w and l):
                    continue
                if meth in NON_DECISIVE:
                    skipped += 1
                    continue
                w = _canon(w, keys, resolve, norm)
                l = _canon(l, keys, resolve, norm)
                key = _pair(d, w, l)
                if key in have or key in seen_pairs:
                    dupes += 1
                    continue
                seen_pairs.add(key)
                for nm in (w, l):
                    if norm(nm) not in keys:
                        debut.add(nm)
                ko = 1.0 if meth == "KO/TKO" else 0.0
                rows.append(_row(w, l, d, 1.0, 0.0))
                rows.append(_row(l, w, d, 0.0, ko))
    report = {"bouts": len(rows) // 2, "rows": len(rows),
              "non_decisive_skipped": skipped, "already_in_bouts": dupes,
              "debutants": sorted(debut), "bouts_csv_through": last_bout_date}
    return rows, report


def _row(fighter, opp, date, won, lost_by_ko):
    """A fighter_bouts-shaped row with stats blank and stats_known=0.

    The stat columns are written as empty strings rather than 0 so that any
    consumer which does not honour stats_known gets a parse failure or a
    visible blank, not a silently plausible zero."""
    return {"fighter": fighter, "opp": opp, "date": date, "division": "",
            "secs": "", "sig_l": "", "sig_a": "", "sig_l_opp": "",
            "sig_a_opp": "", "td_l": "", "td_a": "", "td_l_opp": "",
            "td_a_opp": "", "ctrl": "", "sub": "", "kd": "", "kd_abs": "",
            "won": won, "decided": 1.0, "won_by_ko": "", "lost_by_ko": lost_by_ko,
            "won_by_sub": "", "won_by_dec": "", "year": int(date[:4]),
            "stats_known": 0}


def selftest():
    ok = [0, 0]

    def chk(c, msg):
        ok[1] += 1
        ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + msg)

    import tempfile
    tmp = tempfile.mkdtemp()
    b = os.path.join(tmp, "bouts.csv")
    dl = os.path.join(tmp, "delta.csv")
    cols = list(_row("a", "b", "2020-01-01", 1.0, 0.0).keys())
    cols.remove("stats_known")
    with open(b, "w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=cols)
        wtr.writeheader()
        for r in (_row("Alpha Ant", "Beta Bee", "2026-06-01", 1.0, 0.0),
                  _row("Beta Bee", "Alpha Ant", "2026-06-01", 0.0, 1.0)):
            r = dict(r); r.pop("stats_known"); wtr.writerow(r)
    with open(dl, "w", newline="") as f:
        wtr = csv.writer(f)
        wtr.writerow(["event_date", "event", "winner", "loser", "method", "round"])
        wtr.writerow(["2026-06-01", "old card", "Alpha Ant", "Beta Bee", "DEC", 3])
        wtr.writerow(["2026-07-11", "new card", "Alpha Ant", "Cee Cat", "KO/TKO", 1])
        wtr.writerow(["2026-07-18", "new card 2", "Beta Bee", "Dee Dog", "SUB", 2])
        wtr.writerow(["2026-07-18", "new card 2", "Eee Eel", "Eff Fox", "Draw", 3])

    ident = lambda s: "".join(c for c in str(s).lower() if c.isalnum())
    res = lambda n, keys: keys.get(ident(n))
    rows, rep = delta_rows(dl, b, resolve=res, norm=ident)

    chk(rep["bouts"] == 2, "two new bouts merge, the pre-baseline one does not")
    chk(rep["already_in_bouts"] == 1, "a bout already in fighter_bouts is dropped")
    chk(rep["non_decisive_skipped"] == 1, "a Draw is skipped, not scored as a win")
    chk(rep["debutants"] == ["Cee Cat", "Dee Dog"], "debutants identified")

    by = {(r["fighter"], r["date"]): r for r in rows}
    chk(by[("Alpha Ant", "2026-07-11")]["won"] == 1.0
        and by[("Cee Cat", "2026-07-11")]["won"] == 0.0, "mirrored rows disagree on won")
    chk(by[("Cee Cat", "2026-07-11")]["lost_by_ko"] == 1.0,
        "a KO/TKO loss is charged to the loser")
    chk(by[("Dee Dog", "2026-07-18")]["lost_by_ko"] == 0.0,
        "a submission loss is NOT a ko loss")
    chk(all(r["sig_l"] == "" and r["ctrl"] == "" for r in rows),
        "stat columns are blank, never zero")
    chk(all(r["stats_known"] == 0 for r in rows), "every delta row is flagged stats_known=0")
    chk(len(rows) == 2 * rep["bouts"], "every bout emits exactly two mirrored rows")

    # idempotence: merging twice must not double-count
    rows2, _ = delta_rows(dl, b, resolve=res, norm=ident)
    chk(len(rows2) == len(rows), "a second call returns the same rows (idempotent)")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    rows, rep = delta_rows()
    print(f"fighter_bouts.csv runs through {rep['bouts_csv_through']}")
    print(f"results_delta merges {rep['bouts']} bout(s) -> {rep['rows']} mirrored rows")
    print(f"  skipped {rep['non_decisive_skipped']} non-decisive (draw/NC), "
          f"{rep['already_in_bouts']} already in fighter_bouts")
    print(f"  {len(rep['debutants'])} debutant(s) entering at base Elo: "
          + ", ".join(rep["debutants"]))
    dates = sorted({r["date"] for r in rows})
    print(f"  card dates: {', '.join(dates)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
