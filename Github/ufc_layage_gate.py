#!/usr/bin/env python3
"""ufc_layage_gate.py — gates 2 and 3 for the LAYAGE angle.

The power ceiling (gate 1) already ran inside ufc_angles3_experiment.py and
LAYAGE cleared it: +0.00213 measured against a +0.00645 ceiling on the
age-complete subset, i.e. a third of what the panel could possibly show. That
is the profile of a real but modest effect. It is NOT enough on its own —
two fake ROBUST WINs in two days is the whole reason this file exists.

GATE 2, SHUFFLED PLACEBO. Permute the layoff-x-age feature across bouts and
re-run the ENTIRE tune-and-verdict pipeline, grid search included. If the ship
rule fires often on shuffled data, the ship rule is the problem, not the angle.
The shuffle deliberately keeps the real marginal distribution of the feature —
its lumpiness, its zeros, its fat tail of long layoffs — and destroys only the
pairing with the bout. That isolates exactly one question: does WHICH bout the
value is attached to matter?

GATE 3, SHAPE. A real "time off hurts an old man" effect has commitments it
cannot wriggle out of:
  * it must live where the layoff lives. Bouts taken on a normal turnaround
    have almost no layoff, so the term is near zero there; the effect must be
    carried by the long-gap bouts, not spread evenly.
  * it must live where the age is. Two 26-year-olds coming off a year out
    should show little; the term exists to say that the SAME year off costs
    the older man more.
  * it must not depend on the pivot being at exactly 30. If the fit collapses
    when the pivot moves two years, the angle is a grid artifact.
A term that wins overall but fails all three is re-describing something else.
"""
import os
import random
import sys

import ufc_angles3_experiment as A

KEY = "layage_d"
LABEL = "LAYAGE  layoff x age"
TRIALS = int(os.environ.get("PLACEBO_TRIALS", "24"))


def _grid():
    for label, key, grid in A.ANGLES:
        if key == KEY:
            return grid
    raise SystemExit("LAYAGE not in ANGLES")


def verdict_on(feats, out=lambda s: None):
    """Run the real pipeline on one panel and return (dLL, periods, B, robust).

    Deliberately calls the same fit/tune/score functions the experiment uses
    rather than a reimplementation — a placebo that runs different code is
    testing different code.
    """
    co, base_tr = A.fit_baseline(feats, out=out)
    h0, h1 = A.PERIODS[0][0], A.PERIODS[-1][1]
    base_h, _ = A.ll(feats, co, h0, h1)
    tr, B = A.tune(feats, co, KEY, _grid())
    hv, _ = A.ll(feats, co, h0, h1, extra=(KEY, B))
    wins = 0
    for p0, p1 in A.PERIODS:
        b0, _ = A.ll(feats, co, p0, p1)
        v0, _ = A.ll(feats, co, p0, p1, extra=(KEY, B))
        wins += 1 if v0 > b0 else 0
    robust = (tr > base_tr) and hv > base_h and wins == 3
    return hv - base_h, wins, B, robust


def shuffled(feats, seed):
    """Same bouts, same feature values, re-paired at random.

    Copies the feature dicts rather than mutating them: the caller's panel is
    reused across every trial and a mutation here would silently corrupt trial
    N+1 with trial N's shuffle.
    """
    rng = random.Random(seed)
    vals = [f[KEY] for _, f in feats]
    rng.shuffle(vals)
    return [(bt, dict(f, **{KEY: v})) for (bt, f), v in zip(feats, vals)]


def main():
    bouts = A.load_bouts(os.path.join(A.HERE, "data", "fighter_bouts.csv"))
    ages = A.load_ages(os.path.join(A.HERE, "fighter_meta_cache.json"))
    feats = A.walk_features(bouts, ages)
    sub = [(bt, f) for bt, f in feats if f["age_known"]]
    lines = []

    def tee(s):
        print(s)
        lines.append(s)

    tee("=" * 72)
    tee("LAYAGE GATE — shuffled placebo + shape, on the AGE-COMPLETE subset")
    tee("=" * 72)
    real_d, real_w, real_b, real_r = verdict_on(sub)
    tee(f"REAL  n={len(sub)}  b={real_b:+.2f}  holdout dLL {real_d:+.5f}  "
        f"periods {real_w}/3  robust={real_r}")

    # ---------------------------------------------------------------- gate 2
    tee("")
    tee(f"--- GATE 2: SHUFFLED PLACEBO ({TRIALS} trials, full pipeline each)")
    fires, beats, ds = 0, 0, []
    for t in range(TRIALS):
        d, w, b, r = verdict_on(shuffled(sub, 1000 + t))
        ds.append(d)
        fires += 1 if r else 0
        beats += 1 if d >= real_d else 0
    ds.sort()
    tee(f"ship rule fired on noise: {fires}/{TRIALS} "
        f"({100.0 * fires / TRIALS:.0f}%)")
    tee(f"noise dLL >= real ({real_d:+.5f}): {beats}/{TRIALS} "
        f"({100.0 * beats / TRIALS:.0f}%)  <- this is the p-value")
    tee(f"noise dLL  min {ds[0]:+.5f}  median {ds[len(ds) // 2]:+.5f}  "
        f"max {ds[-1]:+.5f}")

    # ---------------------------------------------------------------- gate 3
    tee("")
    tee("--- GATE 3: SHAPE (the effect must live where its inputs live)")

    def slice_verdict(name, keep):
        s = [(bt, f) for bt, f in sub if keep(bt, f)]
        if len(s) < 600:
            tee(f"{name:34s} n={len(s):5d}  too thin to read")
            return
        d, w, b, r = verdict_on(s)
        tee(f"{name:34s} n={len(s):5d}  b={b:+.2f}  dLL {d:+.5f}  {w}/3")

    # where the layoff actually is. lay_d is a DIFFERENCE, so a big absolute
    # value means one man came off a long gap and the other did not — which is
    # precisely the situation the term claims to price.
    slice_verdict("long-gap bouts (|lay_d|>0.5y)",
                  lambda bt, f: abs(f["lay_d"]) > 0.5)
    slice_verdict("even-turnaround bouts (<=0.5y)",
                  lambda bt, f: abs(f["lay_d"]) <= 0.5)
    # where the age is. age_d is also a difference; what matters for this angle
    # is the LEVEL, so use the older man in the bout.
    slice_verdict("has a fighter 33+",
                  lambda bt, f: f.get("age_max", 0.0) >= 33.0)
    slice_verdict("both fighters under 31",
                  lambda bt, f: 0.0 < f.get("age_max", 0.0) < 31.0)

    tee("")
    tee("--- pivot sensitivity (a grid artifact dies when the pivot moves;")
    tee("    and the high pivots are a DEGENERACY PROBE: as the pivot rises")
    tee("    past every fighter's age, (age-pivot) is negative for everyone")
    tee("    and the interaction collapses into a rescaled LAYOFF main effect.")
    tee("    If dLL kept climbing out to 60 the 'interaction' would really be")
    tee("    a repair to the baseline's layoff term. It must peak in the")
    tee("    middle and decay, and the peak must sit at a plausible age.")
    tee("    NOTE: the peak is NOT adopted as the pivot — these are holdout")
    tee("    numbers, and moving a constant to the best one of them is how a")
    tee("    shape check turns into a leak. The shipped pivot stays at 30.")
    base_pivot = A.AGE_PIVOT
    for pv in (27.0, 29.0, 30.0, 31.0, 33.0, 36.0, 40.0, 45.0, 50.0, 60.0):
        A.AGE_PIVOT = pv
        f2 = A.walk_features(bouts, ages)
        s2 = [(bt, f) for bt, f in f2 if f["age_known"]]
        d, w, b, r = verdict_on(s2)
        tee(f"pivot {pv:4.0f}   b={b:+.2f}  dLL {d:+.5f}  periods {w}/3  "
            f"robust={r}")
    A.AGE_PIVOT = base_pivot

    vd = os.environ.get("VERDICT_OUT") or os.path.join(
        A.HERE, "..", "experiments", "UFC-LAYAGE-GATE.md")
    os.makedirs(os.path.dirname(vd), exist_ok=True)
    with open(vd, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"verdict -> {vd}")
    return 0


def selftest():
    """The placebo must be a real shuffle and must not corrupt its input."""
    feats = [({"date": f"20{10 + i // 50:02d}-01-01"},
              {KEY: float(i), "elo_d": 0.0}) for i in range(200)]
    before = [f[KEY] for _, f in feats]
    sh = shuffled(feats, 1)
    after = [f[KEY] for _, f in feats]
    assert before == after, "shuffle mutated the caller's panel"
    assert sorted(f[KEY] for _, f in sh) == sorted(before), "values changed"
    assert [f[KEY] for _, f in sh] != before, "shuffle was a no-op"
    # two different seeds must not produce the same permutation
    assert ([f[KEY] for _, f in shuffled(feats, 1)]
            != [f[KEY] for _, f in shuffled(feats, 2)]), "seed ignored"
    print("LAYAGE GATE SELFTEST PASS — shuffle is non-destructive, "
          "value-preserving, seeded")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
