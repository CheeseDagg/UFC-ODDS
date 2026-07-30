#!/usr/bin/env python3
"""Gates 2-4 for whatever ANGLES 6 sends through, run against the SECOND-PASS
baseline (Elo + chin + age + layoff + EXPER).

RUNNING THESE AGAINST THE FIRST PASS WOULD BE THE WHOLE POINT THROWN AWAY.
Every candidate in round 6 is a within-career accumulator, so every one of them
is correlated with plain experience. A placebo that exonerates MILEAGE against
a baseline with no EXPER in it has exonerated "this man has had a lot of
fights" — and CAGE, which is the cleanest available proxy for exactly that,
went from a 3/3 holdout win to a 0/3 NULL the moment EXPER entered the
baseline. That collapse is the evidence that the control is load-bearing.

  GATE 2  SHUFFLED PLACEBO, within-year. Can a column carrying the term's
          exact marginal distribution but NO row-level information reach the
          observed gain AND a robust win? The joint count is the p-value.
  GATE 3  CROSS-SEASON. Refit the entire pipeline in three disjoint eras. A
          term that only works in 2023-2026 is a property of 2023-2026.
  GATE 4  SHAPE. Does the fitted coefficient mean what the claim says? For an
          accumulator the claim is monotone and signed, so the check is that
          the effect is present in the tails and ordered across bins — a term
          that fits negative overall but is flat inside the panel is fitting
          something other than accumulated damage.
"""
import os
import sys
from collections import defaultdict

import ufc_angles6_experiment as M
from ufc_gates import Panel, gate2, gate3

HERE = os.path.dirname(os.path.abspath(__file__))


def build():
    bouts = M.load_bouts(os.path.join(HERE, "data", "fighter_bouts.csv"))
    meta = M.load_meta(os.path.join(HERE, "fighter_meta_cache.json"))
    feats = M.walk_features(bouts, meta)
    return [(bt, f) for bt, f in feats
            if f["age_known"] and f["acc_known"] and f["wt_known"]]


def gate4(feats, key, b, out=print):
    """SHAPE. Bin the panel by the term and report the holdout win rate in
    each bin, against what the fitted coefficient predicts.

    A signed accumulator claims an ORDERED effect: more of it on A's side than
    B's should mean A wins less often, monotonically. A coefficient can come
    out negative because of one extreme tail while the middle of the panel is
    flat, and that is a different — much weaker — claim than the one the term
    is making. Reported as raw win rates, because a calibration curve that
    needs a model to interpret is not a check on the model.
    """
    h0, h1 = M.PERIODS[0][0], M.PERIODS[-1][1]
    cl = M.CLIP[key]
    rows = [(max(-cl, min(cl, f[key])), bt["won_a"]) for bt, f in feats
            if h0 <= bt["date"] <= h1]
    rows.sort()
    n = len(rows)
    if n < 40:
        out(f"  GATE 4 {key}: only {n} holdout rows — no shape to read")
        return
    q = 5
    out(f"  GATE 4 SHAPE {key} (fitted b={b:+.2f}, holdout n={n}): win rate by "
        f"quintile of the term. A negative b claims this column DESCENDS.")
    prev = None
    mono = True
    for i in range(q):
        lo, hi = i * n // q, (i + 1) * n // q
        chunk = rows[lo:hi]
        wr = 100.0 * sum(y for _, y in chunk) / len(chunk)
        out(f"    q{i + 1}  {key} in [{chunk[0][0]:+.2f},{chunk[-1][0]:+.2f}]"
            f"  n={len(chunk):4d}  A wins {wr:5.1f}%")
        if prev is not None and ((b < 0 and wr > prev + 3.0)
                                 or (b > 0 and wr < prev - 3.0)):
            mono = False
        prev = wr
    out(f"    -> {'ordered as claimed' if mono else 'NOT ordered — the sign is coming from a tail, not from a gradient'}")


def main():
    keys = [k for k in sys.argv[1:] if not k.startswith("-")] or ["mil_d"]
    n_shuf = int(os.environ.get("N_SHUFFLE", "150"))
    feats = build()
    lines = []

    def tee(s):
        print(s)
        lines.append(s)

    grids = {k: g for _, k, g in M.ANGLES}
    labels = {k: lab for lab, k, _ in M.ANGLES}

    tee("=" * 78)
    tee("UFC ANGLES 6 — GATES 2-4, second-pass baseline (EXPER carried)")
    tee("=" * 78)
    tee(f"decisive subset n={len(feats)}   candidates: {', '.join(keys)}")

    p = Panel(M, feats, with_reach=True)   # Panel finds with_ctrl by shape
    tee(f"second-pass baseline: a={p.co['a']} c={p.co['c']} g={p.co['g']} "
        f"L={p.co['L']}  extra={p.base_extra}  HOLDOUT {p.base_h:+.5f} "
        f"(n={p.n_hold})")
    if p.base_extra and all(v == 0.0 for _, v in p.base_extra):
        tee("*** CONTROL PINNED AT ZERO — these gates are running the FIRST "
            "pass and prove nothing about experience. STOP.")
        return 1

    for k in keys:
        d, w, tw, B = p.verdict(feats, k, grids[k])
        tee("")
        tee(f"--- {labels[k]}   b={B:+.2f}  holdout dLL {d:+.5f}  "
            f"periods {w}/3  train_win={tw}")
        tee("  GATE 2 SHUFFLED PLACEBO")
        gate2(p, k, grids[k], n=n_shuf, within_year=True, out=tee)
        gate2(p, k, grids[k], n=n_shuf, within_year=False, out=tee)
        tee("")
        gate4(feats, k, B, out=tee)

    tee("")
    tee("--- GATE 3 CROSS-SEASON (each era refits the whole pipeline)")
    gate3(M, feats, set(keys), with_reach=True, out=tee)

    vd = os.environ.get("VERDICT_OUT") or os.path.join(
        HERE, "..", "experiments", "UFC-ANGLES6-GATES.md")
    os.makedirs(os.path.dirname(vd), exist_ok=True)
    with open(vd, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"gates -> {vd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
