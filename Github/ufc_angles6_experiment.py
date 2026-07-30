#!/usr/bin/env python3
"""
ufc_angles6_experiment.py — MILEAGE and WEIGHT, the two career histories the
rating cannot carry.

Rounds 1-5 have already killed most of the easy ideas, and the reason they died
is almost always the same one. MODEL-KNOWLEDGE calls it the ABSORPTION THEOREM:
if the truth is z = beta * (x_i - x_j) for any per-fighter quantity x, then a
rating r_i = beta * x_i + skill_i reproduces it exactly and Elo converges there
unaided. Reach died to it. Plain stance died to it. A null on such a term is not
evidence the trait is worthless — it is evidence Elo already knows.

So round 6 only proposes terms from the two classes that ESCAPE the theorem:

  (a) WITHIN-CAREER ACCUMULATORS. A quantity that GROWS during a career cannot
      be a fixed per-fighter number, so no static rating can hold it. This is
      why age and layoff survived where reach did not. Everything below in the
      MILEAGE family is of this class.
  (b) NON-LINEARITIES the baseline's linear term structurally cannot express.
      QUICK is of this class: the baseline already carries layoff LINEARLY, so
      a short-turnaround indicator can only win by being a shape that a line
      through the same variable cannot draw.

THE SIX TERMS.

  MILEAGE  cumulative significant strikes ABSORBED over the UFC career, in
           hundreds, differenced. This is the accumulating-damage claim, and it
           is NOT what chin_d measures. chin_d counts KO LOSSES — a handful of
           discrete catastrophes, most fighters at 0 or 1. MILEAGE counts the
           thousand small ones that never ended a fight. If damage is
           cumulative and sub-clinical, chin_d is looking only at the tail of
           the distribution that the claim is about.
  CAGE     cumulative cage time in hours, differenced. The same accumulator
           with the strikes taken out, which is the point: it is the CONTROL
           for MILEAGE. A man who has absorbed 900 strikes has usually also
           fought a long time, and "he has been in there a lot" is a different
           claim from "he has been hit a lot". Both are in, and the second pass
           decides which one is carrying the other.
  KDABS    cumulative knockdowns absorbed, differenced. Sits BETWEEN chin_d and
           MILEAGE on the severity ladder — a knockdown is a concussive event
           that did not end the bout, so it is neither a catastrophe nor a jab.
           If there is a damage effect at all, this is where the resolution is
           best.
  WTUP     signed rungs of the weight ladder moved since the fighter's previous
           bout, differenced. This is the sharpest of the six as a claim about
           Elo specifically: a rating earned at featherweight is being spent at
           lightweight, and the rating has no idea. It changes bout-to-bout
           within a career, so it is class (a). SIGNED rather than an
           absolute-value indicator, because moving up and moving down are not
           the same event and averaging them to a magnitude would cancel a real
           effect against itself.
  WTNEW    first bout the fighter has ever had at THIS division, differenced.
           The unsigned companion to WTUP: the cost of unfamiliar weight
           regardless of direction, which WTUP cannot see because it is
           antisymmetric in direction by construction.
  QUICK    turnaround under 60 days, differenced. Class (b). The baseline
           carries lay_d linearly with a cap at 2 years, so it reads "less rest
           is worse" (or better) as a straight line. QUICK asks whether the
           very short end BREAKS that line — a short-notice replacement is a
           categorically different animal from a man on a normal 4-month camp,
           and no slope through the same axis can say so.

  EXPER    bouts so far, in tens, differenced. THE CONTROL, and it does not go
           in the first pass baseline for the same reason the stance indicators
           did not in round 5 — it is itself a within-career accumulator, so it
           is a candidate in its own right, and burying it would be assuming
           the answer. It goes into the SECOND PASS baseline, under all six.

THE SECOND PASS IS THE WHOLE TEST FOR THIS ROUND. Every accumulator here is
strongly correlated with every other one, because they all count up as a career
runs. An accumulator judged without EXPER in the baseline is EXPERIENCE IN A
WIG. First-pass wins on MILEAGE, CAGE and KDABS should therefore be read as
suspects, not findings, and only the second-pass verdict is quoted anywhere.

DECISIVE SUBSET. Both fighters DOB-known, both with at least one prior UFC bout,
and both with a ladder-known current and previous division. The prior-bout
requirement is not fussiness: on a debut row every accumulator is 0, and that 0
does not mean "this man has taken no damage", it means "we have no record of a
career that happened somewhere else". Feeding those rows in as genuine zeros
would put the panel's largest MILEAGE differences on its least reliable rows.

BASELINE. Elo + chin + age + layoff — the shipped model, same as rounds 3-5.
CEILINGS. Gate 1's ladder, imported from ufc_gates so there is one copy. ORACLE
= what a model that knew the true coefficient would buy (a hard bound), FITTED =
what this pipeline actually recovers, n_rob/n_seed = how often a PLANTED effect
survived the whole ship rule. A measured gain at or above its own oracle is
noise by construction.
SHIP RULE. ROBUST WIN in the SECOND PASS, and a measured gain at or above the
FITTED threshold while under the ORACLE bound. Then gates 2-4 in ufc_gates.
"""
import csv, json, math, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
K, SCALE, INIT = 96.0, 450.0, 1500.0
SCORE_FROM = "2012-01-01"
TRAIN_END = "2022-12-31"
PERIODS = [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
           ("2025-01-01", "2026-12-31")]

LAY_CAP = 2.0
QUICK_DAYS = 60.0       # what counts as a short-notice turnaround

# THE WEIGHT LADDER. Rungs are one division apart WITHIN a sex; the two ladders
# are separate namespaces and a move between them is not a move, it is a data
# error. Catch Weight, Open Weight and Unknown get NO rung — a catchweight bout
# is by definition not at a division, and giving it the nearest one would
# manufacture a fake move both into and out of it.
LADDER = {
    "flyweight": ("M", 1), "bantamweight": ("M", 2), "featherweight": ("M", 3),
    "lightweight": ("M", 4), "welterweight": ("M", 5), "middleweight": ("M", 6),
    "light heavyweight": ("M", 7), "heavyweight": ("M", 8),
    "women's strawweight": ("F", 1), "women's flyweight": ("F", 2),
    "women's bantamweight": ("F", 3), "women's featherweight": ("F", 4),
}


def _f(x, d=0.0):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return d


def norm_name(name):
    """MUST mirror ufc_blend_predict.norm_name — the meta cache is keyed by it."""
    n = (name or "").strip().lower()
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    return re.sub(r"\s+", " ", n)


def rung(division):
    return LADDER.get(str(division or "").strip().lower())


def load_bouts(path):
    """One row per bout, oriented to fighter A (the mirror row is dropped).

    The kept row carries BOTH men's damage: sig_l_opp is what A absorbed and
    sig_l is what A landed, which is what B absorbed. So dropping the mirror
    costs nothing here — everything the accumulators need is on one row."""
    rows = list(csv.DictReader(open(path)))
    seen, bouts = set(), []
    for r in rows:
        key = (r["date"],) + tuple(sorted([r["fighter"], r["opp"]]))
        if key in seen or r["won"] not in ("0", "1"):
            continue
        seen.add(key)
        bouts.append({
            "date": r["date"], "a": r["fighter"], "b": r["opp"],
            "won_a": int(r["won"]),
            "ko_loss_a": int(_f(r.get("lost_by_ko"))),
            "ko_win_a": int(_f(r.get("won_by_ko"))),
            "div": r.get("division"),
            "secs": _f(r.get("secs")),
            "abs_a": _f(r.get("sig_l_opp")),   # strikes A absorbed
            "abs_b": _f(r.get("sig_l")),       # strikes B absorbed
            "kda_a": _f(r.get("kd_abs")),      # knockdowns A absorbed
            "kda_b": _f(r.get("kd")),          # knockdowns B absorbed
        })
    bouts.sort(key=lambda x: x["date"])
    return bouts


def load_meta(path):
    if not os.path.exists(path):
        return {}
    return meta_from(json.load(open(path)))


def meta_from(raw):
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict) and v.get("dob"):
            out[norm_name(k)] = {"dob": v["dob"]}
    return out


def _age(dob, date):
    try:
        y0, m0, d0 = (int(x) for x in dob.split("-"))
        y1, m1, d1 = (int(x) for x in date.split("-"))
    except (ValueError, AttributeError):
        return None
    return (y1 - y0) + ((m1 - m0) * 30.44 + (d1 - d0)) / 365.25


def _days(d0, d1):
    def ord_(d):
        y, m, dd = (int(x) for x in d.split("-"))
        if m <= 2:
            y, m = y - 1, m + 12
        return (365 * y + y // 4 - y // 100 + y // 400
                + (153 * (m - 3) + 2) // 5 + dd)
    return ord_(d1) - ord_(d0)


def walk_features(bouts, meta=None):
    """One chronological pass. Every feature is snapshotted BEFORE the bout
    updates any accumulator, so no row can see its own outcome — and for a
    round built entirely out of accumulators that boundary is the experiment.
    A MILEAGE that included the current bout's absorbed strikes would be a
    thinly disguised copy of the result."""
    meta = meta or {}
    elo = defaultdict(lambda: INIT)
    ko_losses = defaultdict(int)
    nbouts = defaultdict(int)
    absorbed = defaultdict(float)   # career sig strikes taken
    cage = defaultdict(float)       # career seconds
    kdabs = defaultdict(float)      # career knockdowns taken
    last_date = {}
    last_rung = {}                  # fighter -> (sex, rung) of PREVIOUS bout
    seen_div = defaultdict(set)     # fighter -> divisions already fought at
    out = []

    def layoff(f, date):
        prev = last_date.get(f)
        if prev is None:
            return None
        return min(_days(prev, date) / 365.25, LAY_CAP)

    for bt in bouts:
        a, b, date = bt["a"], bt["b"], bt["date"]
        na, nb = norm_name(a), norm_name(b)
        ma, mb = meta.get(na, {}), meta.get(nb, {})

        age_a = _age(ma["dob"], date) if ma.get("dob") else None
        age_b = _age(mb["dob"], date) if mb.get("dob") else None
        age_known = 1.0 if (age_a is not None and age_b is not None) else 0.0
        age_d = (age_a - age_b) if age_known else 0.0

        la, lb = layoff(a, date), layoff(b, date)
        lay_known = 1.0 if (la is not None and lb is not None) else 0.0
        lay_d = (la - lb) if lay_known else 0.0

        # QUICK. Indicator, not a slope — the whole point is the shape the
        # linear lay_d cannot draw. Undefined (0) where either layoff is.
        if lay_known:
            qa = 1.0 if _days(last_date[a], date) < QUICK_DAYS else 0.0
            qb = 1.0 if _days(last_date[b], date) < QUICK_DAYS else 0.0
            quick_d = qa - qb
        else:
            quick_d = 0.0

        # Accumulators are only MEANINGFUL once a man has a prior bout on
        # record. acc_known gates the decisive subset rather than the values,
        # so the walk stays simple and the subset does the excluding.
        acc_known = 1.0 if (nbouts[a] > 0 and nbouts[b] > 0) else 0.0
        mil_d = (absorbed[a] - absorbed[b]) / 100.0
        cage_d = (cage[a] - cage[b]) / 3600.0
        kdabs_d = float(kdabs[a] - kdabs[b])
        exp_d = (nbouts[a] - nbouts[b]) / 10.0

        cur = rung(bt["div"])
        pa, pb = last_rung.get(a), last_rung.get(b)
        wt_known = 1.0 if (cur and pa and pb
                           and pa[0] == cur[0] and pb[0] == cur[0]) else 0.0
        if wt_known:
            wtup_d = float((cur[1] - pa[1]) - (cur[1] - pb[1]))
        else:
            wtup_d = 0.0
        if cur:
            wtnew_d = (float(bt["div"] not in seen_div[a])
                       - float(bt["div"] not in seen_div[b]))
        else:
            wtnew_d = 0.0

        out.append((bt, {
            "elo_d": elo[a] - elo[b],
            "chin_d": float(ko_losses[a] - ko_losses[b]),
            "age_d": age_d,
            "age_known": age_known,
            "lay_d": lay_d,
            "acc_known": acc_known,
            "wt_known": wt_known,
            "mil_d": mil_d,
            "cage_d": cage_d,
            "kdabs_d": kdabs_d,
            "wtup_d": wtup_d,
            "wtnew_d": wtnew_d,
            "quick_d": quick_d,
            "exp_d": exp_d,
        }))

        # ---- updates AFTER the snapshot: this line is the leak boundary ----
        ea = 1.0 / (1.0 + 10 ** (-(elo[a] - elo[b]) / SCALE))
        y = bt["won_a"]
        elo[a] += K * (y - ea)
        elo[b] += K * ((1 - y) - (1 - ea))
        if y and bt["ko_win_a"]:
            ko_losses[b] += 1
        if (not y) and bt["ko_loss_a"]:
            ko_losses[a] += 1
        absorbed[a] += bt["abs_a"]
        absorbed[b] += bt["abs_b"]
        kdabs[a] += bt["kda_a"]
        kdabs[b] += bt["kda_b"]
        for f in (a, b):
            nbouts[f] += 1
            last_date[f] = date
            cage[f] += bt["secs"]
            if bt["div"]:
                seen_div[f].add(bt["div"])
            if cur:
                last_rung[f] = cur
    return out


CLIP = {"chin_d": 6.0, "age_d": 15.0, "lay_d": LAY_CAP,
        "mil_d": 8.0, "cage_d": 3.0, "kdabs_d": 6.0,
        "wtup_d": 3.0, "wtnew_d": 1.0, "quick_d": 1.0, "exp_d": 2.5}


def ll(feats, co, d0, d1, extra=None, ys=None, base_extra=None):
    """Mean log-likelihood over bouts in [d0,d1]."""
    tot = n = 0
    ek, eb = extra if extra else (None, 0.0)
    for i, (bt, f) in enumerate(feats):
        if not (d0 <= bt["date"] <= d1):
            continue
        z = (co["a"] * f["elo_d"] / SCALE
             + co["c"] * max(-6.0, min(6.0, f["chin_d"]))
             + co["g"] * max(-15.0, min(15.0, f["age_d"]))
             + co["L"] * max(-LAY_CAP, min(LAY_CAP, f["lay_d"])))
        for bk, bv in (base_extra or ()):
            cl = CLIP[bk]
            z += bv * max(-cl, min(cl, f[bk]))
        if ek:
            cl = CLIP[ek]
            z += eb * max(-cl, min(cl, f[ek]))
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
        p = min(max(p, 1e-9), 1 - 1e-9)
        y = bt["won_a"] if ys is None else ys[i]
        tot += y * math.log(p) + (1 - y) * math.log(1 - p)
        n += 1
    return (tot / n if n else 0.0), n


BASE_GRIDS = {"a": (0.6, 0.9, 1.2, 1.6, 2.0, 2.4, 2.8, 3.2),
              "c": (-0.30, -0.20, -0.12, -0.06, -0.03, 0.0, 0.03, 0.06),
              "g": (-0.16, -0.12, -0.09, -0.06, -0.04, -0.02, -0.01, 0.0,
                    0.02, 0.04),
              "L": (-0.45, -0.30, -0.18, -0.10, -0.05, 0.0, 0.05, 0.10)}
# FINER THAN THE ANGLE GRIDS ON PURPOSE. The first draft of this file used the
# round-5 control grid (steps of 0.08 near zero) and the second pass came back
# with exp_d PINNED AT 0.0 — the TRAIN optimum sits near -0.04, and -0.08
# overshoots it by enough to score worse than not carrying the term at all. A
# control that fits to zero does not control anything: the second pass silently
# became a rerun of the first, with every candidate still free to impersonate
# experience. The zero-pin is now also checked for and shouted about below.
CTRL_BASE_GRID = (-0.40, -0.25, -0.15, -0.10, -0.06, -0.03, 0.0,
                  0.03, 0.06, 0.10, 0.15, 0.25, 0.40)
CTRL = ("exp_d",)


def edges(co, be=()):
    """Which baseline coefficients landed on the boundary of their own grid.
    A censored estimate is not an estimate, and an under-fitted baseline hands
    free credit to any angle correlated with the term it under-fitted."""
    bad = [k for k, g in BASE_GRIDS.items() if co[k] in (min(g), max(g))]
    bad += [k for k, v in be
            if v in (min(CTRL_BASE_GRID), max(CTRL_BASE_GRID))]
    return bad


def fit_baseline(feats, out=print, ys=None, with_ctrl=False):
    """Coordinate ascent on TRAIN. When with_ctrl, EXPER is fitted alongside
    the rest and returned as base_extra — that is the second pass."""
    co = {"a": 2.4, "c": -0.10, "g": -0.02, "L": -0.05}
    ind = {k: 0.0 for k in CTRL}

    def be():
        return tuple(sorted(ind.items())) if with_ctrl else ()

    best = ll(feats, co, SCORE_FROM, TRAIN_END, ys=ys, base_extra=be())[0]
    for _ in range(3):
        for k, grid in BASE_GRIDS.items():
            for v in grid:
                trial = dict(co, **{k: v})
                s = ll(feats, trial, SCORE_FROM, TRAIN_END, ys=ys,
                       base_extra=be())[0]
                if s > best:
                    best, co = s, trial
        if with_ctrl:
            for k in ind:
                for v in CTRL_BASE_GRID:
                    keep = ind[k]
                    ind[k] = v
                    s = ll(feats, co, SCORE_FROM, TRAIN_END, ys=ys,
                           base_extra=be())[0]
                    if s > best:
                        best = s
                    else:
                        ind[k] = keep
    edge = edges(co, be())
    if with_ctrl:
        dead = [k for k, v in ind.items() if v == 0.0]
        if dead:
            out(f"*** CONTROL PINNED AT ZERO: {','.join(dead)} — the second "
                f"pass is a RERUN OF THE FIRST and controls nothing. Almost "
                f"always a grid too coarse near zero, not a real null.")
    tag = ("  " + " ".join(f"{k}={v}" for k, v in sorted(ind.items()))
           if with_ctrl else "")
    out(f"baseline (Elo + chin + age + layoff"
        f"{' + EXPER' if with_ctrl else ''}): "
        f"a={co['a']} c={co['c']} g={co['g']} L={co['L']}{tag}  "
        f"TRAIN LL {best:+.5f}"
        f"{'  *** GRID EDGE: ' + ','.join(edge) + ' ***' if edge else ''}")
    return co, best, be()


# GRIDS RUN PAST WHERE ANY REAL EFFECT COULD SIT. A fit that pins at the grid
# maximum is a censored number, and two censored numbers cannot be compared.
ANGLES = [
    ("MILEAGE strikes absorbed, hundreds", "mil_d",
     (-0.30, -0.20, -0.12, -0.07, -0.03, 0.03, 0.07, 0.12, 0.20, 0.30)),
    ("CAGE    career cage hours [MILEAGE's control]", "cage_d",
     (-0.60, -0.40, -0.25, -0.15, -0.07, 0.07, 0.15, 0.25, 0.40, 0.60)),
    ("KDABS   knockdowns absorbed", "kdabs_d",
     (-0.50, -0.32, -0.20, -0.12, -0.06, 0.06, 0.12, 0.20, 0.32, 0.50)),
    ("WTUP    rungs moved up since last bout", "wtup_d",
     (-0.50, -0.32, -0.20, -0.12, -0.06, 0.06, 0.12, 0.20, 0.32, 0.50)),
    ("WTNEW   first bout ever at this weight", "wtnew_d",
     (-0.70, -0.45, -0.28, -0.16, -0.08, 0.08, 0.16, 0.28, 0.45, 0.70)),
    ("QUICK   turnaround under 60 days", "quick_d",
     (-0.70, -0.45, -0.28, -0.16, -0.08, 0.08, 0.16, 0.28, 0.45, 0.70)),
    ("EXPER   bouts so far, tens [CONTROL]", "exp_d",
     (-0.60, -0.40, -0.25, -0.15, -0.07, 0.07, 0.15, 0.25, 0.40, 0.60)),
]
CANDIDATES = {"mil_d", "cage_d", "kdabs_d", "wtup_d", "wtnew_d", "quick_d"}


def tune(feats, co, key, grid, ys=None, base_extra=None):
    """Best b on TRAIN with the baseline held fixed — the real pipeline."""
    best = (-9e9, 0.0)
    for b in grid:
        s, _ = ll(feats, co, SCORE_FROM, TRAIN_END, extra=(key, b), ys=ys,
                  base_extra=base_extra)
        if s > best[0]:
            best = (s, b)
    return best


def _synth_outcomes(feats, key, b_true, seed, with_ctrl):
    """Re-roll every outcome so `key` is true at b_true, with the rest of the
    world held at its real fitted shape."""
    import random
    rng = random.Random(seed)
    co0, _, be0 = fit_baseline(feats, out=lambda s: None, with_ctrl=with_ctrl)
    ys, cl = [], CLIP[key]
    for bt, f in feats:
        z = (co0["a"] * f["elo_d"] / SCALE
             + co0["c"] * max(-6.0, min(6.0, f["chin_d"]))
             + co0["g"] * max(-15.0, min(15.0, f["age_d"]))
             + co0["L"] * max(-LAY_CAP, min(LAY_CAP, f["lay_d"]))
             + b_true * max(-cl, min(cl, f[key])))
        for bk, bv in be0:
            if bk != key:
                z += bv * max(-CLIP[bk], min(CLIP[bk], f[bk]))
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
        ys.append(1 if rng.random() < p else 0)
    return ys


def probe_once(feats, key, grid, b_true, seed, with_ctrl=False):
    """One synthetic panel where the angle IS true. The baseline is REFIT on
    the synthetic panel rather than carried over: a carried-over fit is
    mis-specified for the re-rolled outcomes, which would hand the angle term
    credit for repairing the baseline and inflate the ceiling — the dangerous
    direction, since it turns invisible angles into dead ones."""
    ys = _synth_outcomes(feats, key, b_true, seed, with_ctrl)
    co, tr_base, be = fit_baseline(feats, out=lambda s: None, ys=ys,
                                   with_ctrl=with_ctrl)
    h0, h1 = PERIODS[0][0], PERIODS[-1][1]
    base, _ = ll(feats, co, h0, h1, ys=ys, base_extra=be)
    orc, _ = ll(feats, co, h0, h1, extra=(key, b_true), ys=ys, base_extra=be)
    tr, B = tune(feats, co, key, grid, ys=ys, base_extra=be)
    fit_, _ = ll(feats, co, h0, h1, extra=(key, B), ys=ys, base_extra=be)
    wins = 0
    for p0, p1 in PERIODS:
        b0, _ = ll(feats, co, p0, p1, ys=ys, base_extra=be)
        v0, _ = ll(feats, co, p0, p1, extra=(key, B), ys=ys, base_extra=be)
        wins += 1 if v0 > b0 else 0
    robust = 1 if (tr > tr_base and fit_ > base and wins == 3) else 0
    return orc - base, fit_ - base, robust


def probe(feats, key, grid, b_true, seeds=(7, 17, 27), with_ctrl=False):
    """Averages over seeds, and returns the RAW robust count, which is the
    detectability test — not a proxy for it."""
    o, fi, rb = zip(*[probe_once(feats, key, grid, b_true, s, with_ctrl)
                      for s in seeds])
    return (sum(o) / len(o), sum(fi) / len(fi), min(o), max(o),
            sum(rb), len(rb))


from ufc_gates import read_ceiling  # noqa: E402


def experiment(feats, out=print, ceilings=True, with_ctrl=False,
               only=None, seeds=(7, 17, 27)):
    co, base_tr, be = fit_baseline(feats, out=out, with_ctrl=with_ctrl)
    h0, h1 = PERIODS[0][0], PERIODS[-1][1]
    base_h, nh = ll(feats, co, h0, h1, base_extra=be)
    out(f"baseline HOLDOUT {base_h:+.5f} (n={nh})")
    angles = [a for a in ANGLES if only is None or a[1] in only]
    results = {}
    for label, key, grid in angles:
        tr, B = tune(feats, co, key, grid, base_extra=be)
        train_win = tr > base_tr
        hv, _ = ll(feats, co, h0, h1, extra=(key, B), base_extra=be)
        wins = 0
        for p0, p1 in PERIODS:
            b0, _ = ll(feats, co, p0, p1, base_extra=be)
            v0, _ = ll(feats, co, p0, p1, extra=(key, B), base_extra=be)
            wins += 1 if v0 > b0 else 0
        verdict = ("ROBUST WIN" if (train_win and hv > base_h and wins == 3)
                   else ("win, not robust" if hv > base_h else "NULL"))
        results[label] = (hv - base_h, wins, verdict, B)
        out(f"{label:44s} b={B:>6}  train_win={str(train_win):5s}  "
            f"holdout dLL {hv - base_h:+.5f}  periods {wins}/3  -> {verdict}")
    if ceilings:
        out("")
        out("--- CEILINGS. ORACLE = what a model that knew the true coefficient")
        out("    would buy (a hard bound). FITTED = what this pipeline actually")
        out("    recovers when the effect is real. n_rob/n_seed = how often a")
        out("    PLANTED effect survived the ship rule; that count, not a magic")
        out("    number, is what decides 'invisible' from 'dead'.")
        for label, key, grid in angles:
            b_fit = results[label][3]
            side = [b for b in grid if (b < 0) == (b_fit < 0)] or list(grid)
            # PLANT AT THE FITTED MAGNITUDE FIRST, THEN STEP UP. Rounds 3-5
            # started this ladder at the STRONGEST grid value and only stepped
            # DOWN when the oracle came back non-positive. On this round that
            # rule misreads its own best result, and the reason generalises:
            #
            #   MILEAGE fits at b=-0.03. Planting b=-0.30 builds a world where
            #   mileage is TEN TIMES the effect the data claims, and a world
            #   like that is trivially detectable — oracle +0.074, plant 3/3.
            #   read_ceiling then compares the MEASURED +0.0038 against a
            #   FITTED threshold of +0.072 built from that other world, fails
            #   it, and prints "DEAD: a planted effect of this size was
            #   recovered 3/3, so a real one would have shown". Which is true
            #   and irrelevant: an effect of THAT size would have shown. The
            #   question the gate exists to ask is whether an effect of the
            #   size actually measured could have been seen.
            #
            # In round 5 the fitted coefficients sat near the grid walls, so
            # strongest-first and fitted-first were the same ladder and the
            # defect never surfaced. Here they are an order of magnitude
            # apart. Stepping UP (not down) still handles the absorbed-plant
            # case the old ladder was built for: if the baseline eats a plant
            # at the fitted size, a larger one is what breaks free.
            b_gen, o, fi, olo, ohi, n_rob, n_seed = None, 0.0, 0.0, 0.0, 0.0, 0, 0
            ladder = (sorted([b for b in side if abs(b) >= abs(b_fit)], key=abs)
                      or sorted(side, key=abs, reverse=True))
            for cand in ladder[:4]:
                b_gen = cand
                o, fi, olo, ohi, n_rob, n_seed = probe(
                    feats, key, grid, cand, seeds=seeds, with_ctrl=with_ctrl)
                if o > 0:
                    break
                out(f"{label:44s}   (plant b={cand:+.2f} absorbed by the "
                    f"baseline, oracle {o:+.5f} — stepping up)")
            got = results[label][0]
            won = results[label][2] == "ROBUST WIN" and got > 0
            read = read_ceiling(got, won, o, olo, fi, n_rob, n_seed)
            out(f"{label:44s} oracle(b={b_gen:+.2f}) {o:+.5f} "
                f"[{olo:+.5f}..{ohi:+.5f}]  fitted {fi:+.5f}  "
                f"plant {n_rob}/{n_seed}  measured {got:+.5f}   {read}")
            results[label] = results[label] + (o, fi, n_rob, n_seed)
    return results


# ------------------------------------------------------------------ selftest
def selftest():
    ok = True

    def chk(cond, msg):
        nonlocal ok
        print(("  PASS  " if cond else "  FAIL  ") + msg)
        ok = ok and bool(cond)

    print("=" * 78)
    print("ufc_angles6 selftest")
    print("=" * 78)

    # 1. THE LADDER. A move must be one rung per division and must NOT be
    #    computable across sexes — the two ladders are separate namespaces.
    chk(rung("Lightweight") == ("M", 4), "ladder: Lightweight is M rung 4")
    chk(rung("Women's Flyweight") == ("F", 2), "ladder: W-Flyweight is F rung 2")
    chk(rung("Catch Weight") is None, "ladder: Catch Weight has NO rung")
    chk(rung("Open Weight") is None, "ladder: Open Weight has NO rung")
    chk(rung("Unknown") is None, "ladder: Unknown has NO rung")
    chk(rung("Flyweight")[0] != rung("Women's Flyweight")[0],
        "ladder: men's and women's Flyweight are different namespaces")

    # 2. THE LEAK BOUNDARY. Build a 3-bout toy career and assert every
    #    accumulator is snapshotted BEFORE the bout that feeds it. This is the
    #    single assertion the whole round rests on: a MILEAGE that saw its own
    #    bout would be a copy of the result wearing a feature's name.
    toy = [
        {"date": "2020-01-01", "a": "X", "b": "Y", "won_a": 1,
         "ko_loss_a": 0, "ko_win_a": 0, "div": "Lightweight", "secs": 900.0,
         "abs_a": 10.0, "abs_b": 40.0, "kda_a": 0.0, "kda_b": 1.0},
        {"date": "2020-06-01", "a": "X", "b": "Z", "won_a": 1,
         "ko_loss_a": 0, "ko_win_a": 0, "div": "Welterweight", "secs": 300.0,
         "abs_a": 5.0, "abs_b": 20.0, "kda_a": 0.0, "kda_b": 0.0},
        {"date": "2020-07-10", "a": "X", "b": "Y", "won_a": 0,
         "ko_loss_a": 0, "ko_win_a": 0, "div": "Welterweight", "secs": 600.0,
         "abs_a": 30.0, "abs_b": 8.0, "kda_a": 1.0, "kda_b": 0.0},
    ]
    fx = walk_features(toy, {})
    f0, f1, f2 = (f for _, f in fx)
    chk(f0["mil_d"] == 0.0 and f0["acc_known"] == 0.0,
        "leak: bout 1 has zero mileage and acc_known=0 (both debuts)")
    chk(abs(f1["mil_d"] - 0.10) < 1e-9,
        "leak: bout 2 sees X's 10 absorbed from bout 1 and nothing from its own")
    chk(f1["acc_known"] == 0.0, "leak: bout 2 acc_known=0 (Z is a debut)")
    chk(abs(f2["mil_d"] - (15.0 - 40.0) / 100.0) < 1e-9,
        "leak: bout 3 sees X=15 Y=40 — its own 30/8 are NOT in the snapshot")
    chk(f2["acc_known"] == 1.0, "leak: bout 3 acc_known=1 (both have history)")
    chk(abs(f2["cage_d"] - (1200.0 - 900.0) / 3600.0) < 1e-9,
        "leak: cage time excludes the current bout's 600s")
    chk(f2["kdabs_d"] == -1.0, "leak: KDABS X=0 Y=1 before bout 3")
    chk(abs(f2["exp_d"] - 0.1) < 1e-9,
        "leak: by bout 3 X has 2 prior bouts and Y has 1 -> +0.1")

    # 3. WTUP AND WTNEW. Bout 2 moves X up a rung (LW->WW) while Z debuts, so
    #    wt_known must be 0. Bout 3 is X (prev WW) vs Y (prev LW) at WW: X is
    #    steady, Y is moving up one, so the DIFFERENCE is -1 in X's favour.
    chk(f1["wt_known"] == 0.0, "weight: bout 2 wt_known=0 (Z has no prior bout)")
    chk(f2["wt_known"] == 1.0, "weight: bout 3 wt_known=1")
    chk(abs(f2["wtup_d"] - (-1.0)) < 1e-9,
        "weight: bout 3 wtup_d = X moves 0 rungs, Y moves +1 -> -1")
    chk(f1["wtnew_d"] == 0.0,
        "weight: bout 2 both men new to Welterweight -> 0 by difference")
    chk(abs(f2["wtnew_d"] - (-1.0)) < 1e-9,
        "weight: bout 3 X has fought WW, Y has not -> -1")

    # 4. QUICK. Bout 3 is 39 days after bout 2 for X (quick) and 191 days
    #    after bout 1 for Y (not quick).
    chk(_days("2020-06-01", "2020-07-10") == 39, "quick: date arithmetic")
    chk(abs(f2["quick_d"] - 1.0) < 1e-9,
        "quick: bout 3 X on 39 days, Y on 191 -> +1")
    chk(f0["quick_d"] == 0.0, "quick: undefined on debut rows -> 0")

    # 5. NON-ABSORBABILITY, MEASURED RATHER THAN ASSERTED. Plant a MILEAGE
    #    effect into the REAL panel and check the pipeline recovers its sign.
    #    An absorbable term would come back flat or wrong-signed after the
    #    baseline refit; that is exactly what happened to reach in round 4.
    bp = os.path.join(HERE, "data", "fighter_bouts.csv")
    if os.path.exists(bp):
        bouts = load_bouts(bp)
        meta = load_meta(os.path.join(HERE, "fighter_meta_cache.json"))
        feats = walk_features(bouts, meta)
        sub = [(bt, f) for bt, f in feats
               if f["age_known"] and f["acc_known"] and f["wt_known"]]
        chk(len(sub) > 1500, f"panel: decisive subset is usable (n={len(sub)})")
        grid = dict((k, g) for _, k, g in ANGLES)["mil_d"]
        ys = _synth_outcomes(sub, "mil_d", -0.20, 7, False)
        co, _, be = fit_baseline(sub, out=lambda s: None, ys=ys)
        _, B = tune(sub, co, "mil_d", grid, ys=ys, base_extra=be)
        chk(B < 0, f"power: a planted MILEAGE of -0.20 recovers negative (b={B})")
        # And the reverse sign, so the check is not just "the fit likes
        # negative numbers on this feature".
        ys2 = _synth_outcomes(sub, "mil_d", +0.20, 7, False)
        co2, _, be2 = fit_baseline(sub, out=lambda s: None, ys=ys2)
        _, B2 = tune(sub, co2, "mil_d", grid, ys=ys2, base_extra=be2)
        chk(B2 > 0, f"power: a planted MILEAGE of +0.20 recovers positive (b={B2})")
    else:
        print("  SKIP  panel checks (no fighter_bouts.csv)")

    print("=" * 78)
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    bouts = load_bouts(os.path.join(HERE, "data", "fighter_bouts.csv"))
    meta = load_meta(os.path.join(HERE, "fighter_meta_cache.json"))
    feats = walk_features(bouts, meta)
    lines = []

    def tee(s):
        print(s)
        lines.append(s)

    ceilings = "--no-ceilings" not in sys.argv
    agek = sum(1 for _, f in feats if f["age_known"])
    acck = sum(1 for _, f in feats if f["acc_known"])
    wtk = sum(1 for _, f in feats if f["wt_known"])
    tee("=" * 78)
    tee("UFC ANGLES 6 — mileage and weight: the two career histories Elo "
        "cannot carry")
    tee("=" * 78)
    tee(f"unique bouts: {len(bouts)} ({bouts[0]['date']}..{bouts[-1]['date']})")
    tee(f"both DOB known: {agek} ({100 * agek / len(bouts):.0f}%)   "
        f"both with prior bouts: {acck} ({100 * acck / len(bouts):.0f}%)   "
        f"weight-ladder known: {wtk} ({100 * wtk / len(bouts):.0f}%)")

    hold = [(bt, f) for bt, f in feats if bt["date"] >= PERIODS[0][0]]
    hk = sum(1 for _, f in hold if f["acc_known"] and f["wt_known"])
    tee(f"HOLDOUT accumulator- AND weight-complete: {hk}/{len(hold)} "
        f"({100.0 * hk / max(len(hold), 1):.1f}%)")

    sub = [(bt, f) for bt, f in feats
           if f["age_known"] and f["acc_known"] and f["wt_known"]]
    nq = sum(1 for _, f in sub if f["quick_d"] != 0)
    nw = sum(1 for _, f in sub if f["wtup_d"] != 0)
    nn = sum(1 for _, f in sub if f["wtnew_d"] != 0)
    tee("")
    tee(f"--- DECISIVE SUBSET: age-, accumulator- and weight-complete "
        f"(n={len(sub)})")
    tee(f"    rows where the term is not identically zero: "
        f"QUICK {nq}, WTUP {nw}, WTNEW {nn}")
    tee("    A term that is zero on most of the panel is not thereby weak, but")
    tee("    its effective sample IS that count, and the ceilings are read")
    tee("    against it rather than against n.")
    tee("")
    experiment(sub, out=tee, ceilings=ceilings)

    tee("")
    tee("--- SECOND PASS: EXPER is now IN THE BASELINE. Every accumulator here")
    tee("    counts up as a career runs, so all six are correlated with plain")
    tee("    experience and with each other. An accumulator judged without")
    tee("    EXPER underneath it is EXPERIENCE IN A WIG. Only this pass is")
    tee("    quoted as a finding; the first pass names suspects.")
    experiment(sub, out=tee, ceilings=ceilings, with_ctrl=True, only=CANDIDATES)

    tee("")
    tee("Ship rule: ROBUST WIN in the SECOND PASS, and a measured gain at or")
    tee("above the FITTED threshold while under the ORACLE bound. Anything")
    tee("that clears it still owes gates 2-4 in ufc_gates before it ships.")

    vd = os.environ.get("VERDICT_OUT") or os.path.join(
        HERE, "..", "experiments", "UFC-ANGLES6-VERDICT.md")
    os.makedirs(os.path.dirname(vd), exist_ok=True)
    with open(vd, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"verdict -> {vd}")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
