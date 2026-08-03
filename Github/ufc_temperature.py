#!/usr/bin/env python3
"""Fit the temperature that turns a model-score difference into a win probability.

WHY THIS FILE EXISTS.

`model_score` in output/ufc_ratings.json is documented as being in "logit units",
and every consumer took that at face value:

    p1 = 1 / (1 + exp(-(s1 - s2)))

It is not true. The scores are opponent-adjusted ridge coefficients normalized
within division; their spread is compressed relative to log-odds by a factor of
roughly two. The consequence was that the tool never had an opinion. Across the
24 bouts in the live ledger the mean distance from a coin flip was 0.049 -- the
most lopsided matchup the site had ever published was 65.7%, while the market on
the same card ran to 80.8%. A model that says 52% about everything cannot be
wrong in an interesting way, and cannot be right in a useful one either.

WHY THE NUMBER IS FIT HERE INSTEAD OF READ FROM calibration.json.

output/calibration.json carries T=3.17. That number is too hot for this score
file, and the reason is worth writing down because it will bite again.

The ratings are RECENCY-WEIGHTED and fit on the same bout history they are
scored against, so a fight's own result is partly baked into its participants'
current scores -- and the more recent the fight, the more of it is baked in.
Fitting T era by era makes the gradient visible:

    era          n     fitted T    accuracy
    2005-2012  1064      2.05        62.0%
    2013-2016  1252      2.02        65.2%
    2017-2019  1050      1.91        67.1%
    2020-2022  1114      2.14        68.2%
    2023-2024   738      2.87        75.5%
    2025-2027   382      3.86        76.8%

T and accuracy climb together as the memory gets fresher. That is leakage, not
skill: the model does not actually know 2025 fights three times better than 2015
fights. Anything fit on recent bouts inherits the inflation, which is how 3.17
got there.

So T is fit on the OLDEST cohort, where the recency weight has decayed to near
nothing and the score is closest to an honest out-of-sample opinion. Fitting on
the least-leaked data biases T DOWN, and down is the safe direction: an
under-confident betting tool loses less than an over-confident one.

The sanity check that this lands in the right place is that the honest
walk-forward in calibration.json reports 60.7% accuracy, and the era used here
reports 62-65% -- the same model, not the 76% fantasy of the recent slice.

Run:  python3 ufc_temperature.py          # fit, write output/temperature.json
      python3 ufc_temperature.py --selftest
"""
import csv, json, math, pathlib, statistics, sys

HERE = pathlib.Path(__file__).parent
RATINGS = HERE / "output" / "ufc_ratings.json"
BOUTS = HERE / "data" / "fighter_bouts.csv"
OUT = HERE / "output" / "temperature.json"

# The cohort the fit is allowed to see. Everything from 2020 on is close enough
# to the recency window to have its own outcome folded into the scores.
FIT_ERA = (2005, 2019)

# A hard ceiling on how confident a single score gap is ever allowed to make us.
# The honest walk-forward has 9 fights above 80% in 1184, and its top bucket
# averages 83%. Nothing in this model earns 95%.
P_CAP = 0.90


def _sig(z):
    return 1.0 / (1.0 + math.exp(-max(-35.0, min(35.0, z))))


def prob(s1, s2, T):
    """The one place a score difference becomes a probability. Capped.

    The cap is not cosmetic. Score differences are unbounded in principle --
    two heavyweights at opposite ends of the file differ by 2.77 -- and a
    parlay leg priced at 99% by a model whose honest accuracy is 62% is how a
    tool talks someone into a bet nothing supports."""
    p = _sig(T * (s1 - s2))
    return min(max(p, 1.0 - P_CAP), P_CAP)


def load_pairs(ratings=RATINGS, bouts=BOUTS):
    """-> [(score_diff, won, year)], one row per bout (not per fighter)."""
    import ufc_grade as G
    J = json.load(open(ratings))
    fl = J["fighters"] if isinstance(J, dict) else J
    sc = {G.norm(f["name"]): f["model_score"] for f in fl
          if f.get("model_score") is not None}
    seen, out = set(), []
    for r in csv.DictReader(open(bouts)):
        a, b, d = G.norm(r["fighter"]), G.norm(r["opp"]), r["date"]
        # fighter_bouts.csv stores each bout twice, once from each corner.
        # Keeping both would double-count every result in the likelihood.
        k = (d, *sorted([a, b]))
        if k in seen:
            continue
        seen.add(k)
        if a in sc and b in sc and r["won"] in ("0", "1"):
            out.append((sc[a] - sc[b], int(r["won"]), int(d[:4])))
    return out


def nll(T, D):
    s = 0.0
    for d, y, _ in D:
        p = min(max(_sig(T * d), 1e-12), 1 - 1e-12)
        s -= y * math.log(p) + (1 - y) * math.log(1 - p)
    return s / len(D)


def fit_T(D, lo=0.05, hi=12.0, iters=90):
    """Golden-section on mean negative log-likelihood. One parameter, convex
    enough in practice; the bracket is wide enough to catch a scale change."""
    for _ in range(iters):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if nll(m1, D) < nll(m2, D):
            hi = m2
        else:
            lo = m1
    return (lo + hi) / 2


def reliability(T, D, edges=(0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 1.01)):
    """Bucketed predicted-vs-actual, folded to the favourite's side."""
    bk = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        sel = []
        for d, y, _ in D:
            p = _sig(T * d)
            if p < 0.5:
                p, y = 1 - p, 1 - y
            if lo <= p < hi:
                sel.append((p, y))
        if sel:
            bk.append({"lo": lo, "hi": min(hi, 1.0), "n": len(sel),
                       "pred": round(statistics.mean(p for p, _ in sel), 4),
                       "actual": round(statistics.mean(y for _, y in sel), 4)})
    return bk


def main():
    D = load_pairs()
    fit = [x for x in D if FIT_ERA[0] <= x[2] <= FIT_ERA[1]]
    if len(fit) < 500:
        sys.exit(f"only {len(fit)} bouts in the fit era -- refusing to fit a "
                 f"temperature on that; check data/fighter_bouts.csv")
    T = round(fit_T(fit), 3)
    acc = statistics.mean(((T * d > 0) == (y == 1)) for d, y, _ in fit if d)
    br = statistics.mean((_sig(T * d) - y) ** 2 for d, y, _ in fit)
    era_tab = []
    for a, b in ((2005, 2012), (2013, 2016), (2017, 2019),
                 (2020, 2022), (2023, 2024), (2025, 2030)):
        E = [x for x in D if a <= x[2] <= b]
        if len(E) < 150:
            continue
        Te = round(fit_T(E), 2)
        era_tab.append({"era": f"{a}-{b}", "n": len(E), "T": Te,
                        "acc": round(statistics.mean(
                            ((Te * d > 0) == (y == 1)) for d, y, _ in E if d), 4)})
    payload = {
        "T": T, "p_cap": P_CAP,
        "fit_era": f"{FIT_ERA[0]}-{FIT_ERA[1]}", "n": len(fit),
        "acc": round(acc, 4), "brier": round(br, 4),
        "buckets": reliability(T, fit),
        "era_leakage_scan": era_tab,
        "note": ("Fit on the least-leaked era on purpose; the ratings are "
                 "recency-weighted and fit on this same history, so recent "
                 "bouts inflate T. See module docstring."),
    }
    OUT.parent.mkdir(exist_ok=True)
    json.dump(payload, open(OUT, "w"), indent=1)
    print(f"T = {T}  (fit on {len(fit)} bouts, {FIT_ERA[0]}-{FIT_ERA[1]}; "
          f"acc {acc*100:.1f}%, Brier {br:.4f}, cap {P_CAP})")
    print(f"{'bucket':>12s} {'n':>5s} {'pred':>7s} {'actual':>7s}")
    for b in payload["buckets"]:
        print(f"{b['lo']:.2f}-{b['hi']:<6.2f} {b['n']:5d} "
              f"{b['pred']:7.3f} {b['actual']:7.3f}")
    print("\nleakage scan (why the fit era is old):")
    for e in era_tab:
        print(f"  {e['era']:>10s} n={e['n']:5d}  T={e['T']:5.2f}  "
              f"acc={e['acc']*100:.1f}%")
    print(f"\nwrote {OUT}")
    return 0


def load_T(path=OUT, strict=True):
    """Read the fitted temperature. Never silently defaults to 1.0.

    A missing file used to be indistinguishable from T=1, and T=1 is exactly
    the bug this module exists to close -- it looks like a working pipeline and
    publishes 52% about everything. Callers that cannot fail (the browser
    bundle) get an explicit value baked in at build time instead."""
    try:
        J = json.load(open(path))
        T, cap = float(J["T"]), float(J.get("p_cap", P_CAP))
    except Exception as e:
        if strict:
            raise RuntimeError(
                f"no usable {path} ({type(e).__name__}: {e}) -- run "
                f"ufc_temperature.py before building; refusing to fall back to "
                f"T=1, which silently flattens every probability to a coin flip")
        return None, None
    if not (0.5 <= T <= 8.0):
        raise RuntimeError(f"temperature {T} outside sane range [0.5, 8.0]")
    return T, cap


def selftest():
    ok = [0, 0]

    def chk(c, m):
        ok[1] += 1
        ok[0] += bool(c)
        print(("PASS  " if c else "FAIL  ") + m)

    chk(abs(prob(0.0, 0.0, 2.0) - 0.5) < 1e-12, "equal scores are a coin flip")
    chk(prob(1.0, 0.0, 2.0) > prob(0.5, 0.0, 2.0), "a bigger gap is more confident")
    chk(abs(prob(0.3, -0.2, 2.0) + prob(-0.2, 0.3, 2.0) - 1.0) < 1e-12,
        "the two corners sum to exactly 1")
    chk(prob(9.0, -9.0, 2.0) == P_CAP, "an absurd gap is capped, not 99.99%")
    chk(prob(-9.0, 9.0, 2.0) == 1 - P_CAP, "the cap is symmetric")
    # the bug being closed: T=1 vs a fitted T on a realistic gap
    g = 0.42
    chk(prob(g, 0, 1.0) < 0.61 and prob(g, 0, 2.0) > 0.66,
        "T=1 flattens a real skill gap; the fitted T does not")

    # a monotone likelihood check: the fitter must recover a planted T
    import random
    random.seed(7)
    for plant in (1.4, 2.0, 3.0):
        D = []
        for _ in range(40000):
            d = random.gauss(0, 0.6)
            D.append((d, 1 if random.random() < _sig(plant * d) else 0, 2010))
        got = fit_T(D)
        chk(abs(got - plant) < 0.12,
            f"fitter recovers a planted T={plant} (got {got:.3f})")

    # load_T must refuse rather than default
    try:
        load_T(pathlib.Path("/nonexistent/temperature.json"))
        chk(False, "a missing temperature file raises instead of defaulting")
    except RuntimeError:
        chk(True, "a missing temperature file raises instead of defaulting")
    chk(load_T(pathlib.Path("/nonexistent/x.json"), strict=False) == (None, None),
        "strict=False still never yields 1.0")

    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
