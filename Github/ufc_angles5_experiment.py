#!/usr/bin/env python3
"""
ufc_angles5_experiment.py — STANCE, and the one direction Elo cannot represent.

The round-8 sweep took HOLDOUT stance coverage from 1.0% (18 bouts — no panel
at all) to 91.8% (1,626 of 1,771). Southpaw advantage is the oldest folk claim
in the sport and this repo has never been able to test it. Now it can.

READ THIS BEFORE READING THE RESULTS, because the naive version of the test is
guaranteed to return nothing and the reason is algebra, not data.

Elo scores a bout on r_i - r_j. MODEL-KNOWLEDGE calls this the ABSORPTION
THEOREM: if the truth is z = beta * (x_i - x_j) for any per-fighter quantity x,
then r_i = beta * x_i + skill_i reproduces it exactly and the ratings converge
there unaided. A null on such a term does not say the trait is worthless. It
says Elo already knows.

THE THEOREM APPLIES TO STANCE, and that is not obvious until it is written out.
A plain southpaw edge is the indicator difference 1(i=S) - 1(j=S), which is
f(i) - f(j) with f(S)=c, f(O)=f(W)=0. Absorbable. So SPMAIN is a CONTROL, not a
candidate, in exactly the way raw reach was in batch 4.

BUT ABSORPTION IS A LIMIT, NOT AN INSTANT, AND THE UFC NEVER REACHES IT. Every
fighter debuts at 1500 no matter which foot is forward, and it takes bouts
before the rating carries his stance. UFC careers are short and the inflow of
debutants never stops, so a fraction of the panel is always un-absorbed. The
selftest measures this rather than assuming it: a 0.55-logit per-fighter
southpaw bonus planted into true skill comes back as a REAL, ROBUST SPMAIN win
on a panel with realistic turnover. That is not a refutation of the theorem, it
is the theorem's rate of convergence showing up as a finite-sample residual —
and it is why SPNEW, which is the same edge weighted toward men Elo has barely
seen, beats SPMAIN on that panel. Read SPMAIN accordingly: a win on it is
evidence about CONVERGENCE SPEED, not about southpaws.

BUT STANCE IS NOT A NUMBER, IT IS A TYPE, AND WITH THREE TYPES THE ABSORBABLE
SUBSPACE IS NOT THE WHOLE SPACE. A stance effect is an antisymmetric 3x3
matchup matrix M(s_i, s_j) = -M(s_j, s_i). That matrix has THREE free numbers:
M(O,S), M(O,W), M(S,W). Everything Elo can absorb has the form f(s_i) - f(s_j),
which has only TWO free numbers (f(S)-f(O) and f(W)-f(O)) and satisfies

    M(O,W) = M(O,S) + M(S,W)                       (additivity / transitivity)

So there is exactly ONE direction in stance space that no rating system of the
Elo family can ever represent: the failure of that identity. Solving for the
component orthogonal to both absorbable directions gives

    M(O,S) = +1,  M(O,W) = -1,  M(S,W) = +1

which is a ROCK-PAPER-SCISSORS CYCLE: orthodox beats southpaw beats switch
beats orthodox. That is the CYCLE angle below, and it is the single cleanest
non-absorbable term this repo has ever tested — it does not rely on a
within-career accumulator or an ignorance weighting to escape absorption, it is
structurally orthogonal to everything Elo can hold. A sign flip on its
coefficient is the other cycle (orthodox beats switch beats southpaw beats
orthodox); both are inside the grid, so the fit picks the direction.

THE SIX TERMS.

  SPMAIN  1(i=S) - 1(j=S). ABSORBABLE IN THE LIMIT. The control. A win here
          means Elo is converging too slowly to have eaten it — a statement
          about ratings, not about stance.
  SWMAIN  1(i=W) - 1(j=W). Same class, and the second basis vector of the
          absorbable subspace. Both controls go into the second pass baseline.
  CYCLE   the orthogonal residual described above. NOT ABSORBABLE, by
          construction, and provably so — the selftest checks the two dot
          products rather than taking the derivation on trust.
  SPFAM   unfamiliarity. The folk claim is not really "southpaws are better",
          it is "orthodox fighters do not get reps against southpaws". That is
          a statement about the OPPONENT'S HISTORY, which grows within a
          career, so it is outside the absorbable class for the same reason
          layoff and age are. Term: how unfamiliar each man is with the OTHER
          man's stance, differenced.
  SPNEW   the southpaw edge weighted by TAU/(TAU + bouts), i.e. loud where Elo
          has not had time to learn the fighter and silent for a veteran. Its
          unweighted limit is exactly SPMAIN, so anything it finds is the
          weighting and nothing else.
  XSTNC   cross-stance x Elo gap. A symmetric indicator can only enter an
          antisymmetric model by MULTIPLYING an antisymmetric quantity, and
          that product is not absorbable. The question it asks is not "who
          wins" but "does the favourite's edge SHRINK in a cross-stance bout" —
          a calibration term, not a ranking term, and the only angle in this
          repo that could move a price without moving a pick.

BASELINE. Elo + chin + age + layoff — the shipped model, same as batches 3-4.
SECOND PASS. SPMAIN and SWMAIN are moved INTO the baseline and the four
candidates are re-read. CYCLE is orthogonal to both by construction, so its
verdict should barely move; if it moves a lot, the orthogonality claim is wrong
somewhere and the run says so out loud.

CEILINGS. Gate 1's ladder, imported from ufc_gates so there is one copy. Two
numbers per angle: the ORACLE (what a model that knew the true coefficient
would buy — a hard bound) and the FITTED threshold, plus n_rob/n_seed, the
MEASURED number of seeds in which a planted true-by-construction effect
survived the whole ship rule. A non-positive oracle means the refit baseline
absorbed the plant and the probe is uninformative, not that the angle is dead;
the ladder walks the plant strength down until it finds one the baseline cannot
eat.
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
AGE_PIVOT = 30.0
NEW_TAU = 5.0           # bouts before Elo is trusted over a man's stance
FAM_TAU = 2.0           # bouts against a stance before it stops being strange

# Only three stances have enough of a panel to mean anything. The cache also
# holds 'Open Stance' (3 fighters) and 'Sideways' (2). Those are NOT folded
# into Orthodox — a five-man bucket cannot be estimated and pretending they are
# orthodox would put five men's results on a type they do not have.
STANCE = {"orthodox": "O", "southpaw": "S", "switch": "W"}

# The absorbable subspace, written down rather than assumed. Both are exactly
# f(i) - f(j) for a per-fighter indicator f, so Elo can represent either one
# perfectly and a null on either says nothing about the sport.
IND = {"sp_d": "S", "sw_d": "W"}

# The cycle. c[(x, y)] is the payoff to x against y, antisymmetric, zero on the
# diagonal, and orthogonal to every f(i) - f(j). Derivation in the docstring;
# the selftest checks it numerically instead of trusting the derivation.
CYC = {("O", "S"): 1.0, ("S", "O"): -1.0,
       ("O", "W"): -1.0, ("W", "O"): 1.0,
       ("S", "W"): 1.0, ("W", "S"): -1.0}


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


def load_bouts(path):
    """One row per bout, oriented to fighter A (the mirror row is dropped)."""
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
        })
    bouts.sort(key=lambda x: x["date"])
    return bouts


def load_meta(path):
    """dob + stance, keyed by normalised name. An unrecognised stance string
    stays MISSING rather than defaulting to orthodox: 66% of the roster is
    orthodox, so 'default to the mode' would quietly assign the most common
    answer to every fighter the scrape failed on and inflate coverage with
    guesses."""
    if not os.path.exists(path):
        return {}
    return meta_from(json.load(open(path)))


def meta_from(raw):
    out = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        rec = {}
        if v.get("dob"):
            rec["dob"] = v["dob"]
        s = STANCE.get(str(v.get("stance") or "").strip().lower())
        if s:
            rec["stance"] = s
        if rec:
            out[norm_name(k)] = rec
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
    updates any accumulator, so no row can see its own outcome."""
    meta = meta or {}
    elo = defaultdict(lambda: INIT)
    ko_losses = defaultdict(int)
    nbouts = defaultdict(int)
    seen_st = defaultdict(int)      # (fighter, stance) -> prior bouts faced
    last_date = {}
    out = []

    def layoff(f, date):
        prev = last_date.get(f)
        if prev is None:
            return None
        return min(_days(prev, date) / 365.25, LAY_CAP)

    def unfam(f, s):
        """How strange stance s still is to fighter f. 1.0 at zero exposure,
        decaying toward 0. A COUNT would say a man with 20 southpaw bouts is
        ten times as ready as a man with 2, which is not the claim — the claim
        is that the first couple of reps do nearly all the work."""
        return FAM_TAU / (FAM_TAU + seen_st[(f, s)])

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

        sa, sb = ma.get("stance"), mb.get("stance")
        st_known = 1.0 if (sa and sb) else 0.0

        if st_known:
            sp_d = float(sa == "S") - float(sb == "S")
            sw_d = float(sa == "W") - float(sb == "W")
            cyc_d = CYC.get((sa, sb), 0.0)
            cross = 1.0 if sa != sb else 0.0
            # SPFAM. Fighter a is helped when b has not seen a's stance, and
            # hurt when a has not seen b's. Zero on same-stance bouts by
            # design: there is nothing unfamiliar about the look you use
            # yourself, and letting O-vs-O rows carry a value would fill 47%
            # of the panel with a quantity the claim says nothing about.
            spfam_d = (unfam(b, sa) - unfam(a, sb)) if cross else 0.0
            wa = NEW_TAU / (NEW_TAU + nbouts[a])
            wb = NEW_TAU / (NEW_TAU + nbouts[b])
            spnew_d = sp_d * (wa + wb) / 2.0
            xst_d = cross * (elo[a] - elo[b]) / SCALE
        else:
            sp_d = sw_d = cyc_d = spfam_d = spnew_d = xst_d = 0.0

        out.append((bt, {
            "elo_d": elo[a] - elo[b],
            "chin_d": float(ko_losses[a] - ko_losses[b]),
            "age_d": age_d,
            "age_known": age_known,
            "lay_d": lay_d,
            "st_known": st_known,
            "sp_d": sp_d,
            "sw_d": sw_d,
            "cyc_d": cyc_d,
            "spfam_d": spfam_d,
            "spnew_d": spnew_d,
            "xst_d": xst_d,
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
        for f in (a, b):
            nbouts[f] += 1
            last_date[f] = date
        # Exposure updates whenever the OPPONENT'S stance is known, even if the
        # fighter's own is not — his own stance is irrelevant to what he has
        # been made to look at.
        if sb:
            seen_st[(a, sb)] += 1
        if sa:
            seen_st[(b, sa)] += 1
    return out


CLIP = {"chin_d": 6.0, "age_d": 15.0, "lay_d": LAY_CAP,
        "sp_d": 1.0, "sw_d": 1.0, "cyc_d": 1.0, "spfam_d": 1.0,
        "spnew_d": 1.0, "xst_d": 2.0}


def ll(feats, co, d0, d1, extra=None, ys=None, base_extra=None):
    """Mean log-likelihood over bouts in [d0,d1].

    `base_extra` is a list of (key, coef) carried in the BASELINE — that is how
    the second pass puts the two absorbable stance indicators under the
    candidates. `ys` overrides the observed outcomes and is how the ceilings
    score a synthetic panel without rebuilding the feature walk."""
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
ST_BASE_GRID = (-0.30, -0.18, -0.10, -0.05, 0.0, 0.05, 0.10, 0.18, 0.30)


def edges(co, be=()):
    """Which baseline coefficients landed on the boundary of their own grid.

    A coefficient at the edge means the optimum is somewhere the search was
    never allowed to look, so the baseline is weaker than it should be and any
    angle correlated with the under-fitted term collects credit that is not its
    own. Reported on every line rather than checked once, because it can show
    up on a subset without showing up on the full sample."""
    bad = [k for k, g in BASE_GRIDS.items() if co[k] in (min(g), max(g))]
    bad += [k for k, v in be
            if v in (min(ST_BASE_GRID), max(ST_BASE_GRID))]
    return bad


def fit_baseline(feats, out=print, ys=None, with_stance=False):
    """Coordinate ascent on TRAIN. When with_stance, the two ABSORBABLE stance
    indicators are fitted alongside the rest and returned as base_extra."""
    co = {"a": 2.4, "c": -0.10, "g": -0.02, "L": -0.05}
    ind = {"sp_d": 0.0, "sw_d": 0.0}

    def be():
        return tuple(sorted(ind.items())) if with_stance else ()

    best = ll(feats, co, SCORE_FROM, TRAIN_END, ys=ys, base_extra=be())[0]
    for _ in range(3):
        for k, grid in BASE_GRIDS.items():
            for v in grid:
                trial = dict(co, **{k: v})
                s = ll(feats, trial, SCORE_FROM, TRAIN_END, ys=ys,
                       base_extra=be())[0]
                if s > best:
                    best, co = s, trial
        if with_stance:
            for k in ind:
                for v in ST_BASE_GRID:
                    keep = ind[k]
                    ind[k] = v
                    s = ll(feats, co, SCORE_FROM, TRAIN_END, ys=ys,
                           base_extra=be())[0]
                    if s > best:
                        best = s
                    else:
                        ind[k] = keep
    edge = edges(co, be())
    tag = (f"  SP={ind['sp_d']} SW={ind['sw_d']}" if with_stance else "")
    out(f"baseline (Elo + chin + age + layoff"
        f"{' + STANCE INDICATORS' if with_stance else ''}): "
        f"a={co['a']} c={co['c']} g={co['g']} L={co['L']}{tag}  "
        f"TRAIN LL {best:+.5f}"
        f"{'  *** GRID EDGE: ' + ','.join(edge) + ' ***' if edge else ''}")
    return co, best, be()


# GRIDS RUN PAST WHERE ANY REAL EFFECT COULD SIT. A fit that pins at the grid
# maximum is not an estimate, it is a censored one, and two censored numbers
# cannot be compared — the first draft of the selftest had SPMAIN and SPNEW
# both stuck at their walls and was asking which of two 0.30s was larger.
ANGLES = [
    ("SPMAIN  southpaw indicator [ABSORBABLE]", "sp_d",
     (-0.60, -0.40, -0.25, -0.15, -0.07, 0.07, 0.15, 0.25, 0.40, 0.60)),
    ("SWMAIN  switch indicator [ABSORBABLE]", "sw_d",
     (-0.60, -0.40, -0.25, -0.15, -0.07, 0.07, 0.15, 0.25, 0.40, 0.60)),
    ("CYCLE   O>S>W>O, orthogonal to Elo", "cyc_d",
     (-0.60, -0.40, -0.25, -0.15, -0.07, 0.07, 0.15, 0.25, 0.40, 0.60)),
    ("SPFAM   he has not seen that look", "spfam_d",
     (-0.90, -0.60, -0.35, -0.20, -0.10, 0.10, 0.20, 0.35, 0.60, 0.90)),
    ("SPNEW   stance where Elo is blind", "spnew_d",
     (-0.90, -0.60, -0.35, -0.20, -0.10, 0.10, 0.20, 0.35, 0.60, 0.90)),
    ("XSTNC   cross-stance x Elo gap", "xst_d",
     (-1.40, -1.00, -0.60, -0.35, -0.18, 0.18, 0.35, 0.60, 1.00, 1.40)),
]
CANDIDATES = {"cyc_d", "spfam_d", "spnew_d", "xst_d"}


def tune(feats, co, key, grid, ys=None, base_extra=None):
    """Best b on TRAIN with the baseline held fixed — the real pipeline."""
    best = (-9e9, 0.0)
    for b in grid:
        s, _ = ll(feats, co, SCORE_FROM, TRAIN_END, extra=(key, b), ys=ys,
                  base_extra=base_extra)
        if s > best[0]:
            best = (s, b)
    return best


def _synth_outcomes(feats, key, b_true, seed, with_stance):
    """Re-roll every outcome so `key` is true at b_true, with the rest of the
    world held at its real fitted shape."""
    import random
    rng = random.Random(seed)
    co0, _, be0 = fit_baseline(feats, out=lambda s: None,
                              with_stance=with_stance)
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


def probe_once(feats, key, grid, b_true, seed, with_stance=False):
    """One synthetic panel where the angle IS true. Returns (oracle, fitted,
    robust). The baseline is REFIT on the synthetic panel rather than carried
    over: a carried-over fit is mis-specified for the re-rolled outcomes, which
    would hand the angle term credit for repairing the baseline and inflate the
    ceiling — and an inflated ceiling is the dangerous direction of error,
    since it turns invisible angles into dead ones."""
    ys = _synth_outcomes(feats, key, b_true, seed, with_stance)
    co, tr_base, be = fit_baseline(feats, out=lambda s: None, ys=ys,
                                   with_stance=with_stance)
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


def probe(feats, key, grid, b_true, seeds=(7, 17, 27), with_stance=False):
    """Averages over seeds, and returns the RAW robust count, which is the
    detectability test — not a proxy for it."""
    o, fi, rb = zip(*[probe_once(feats, key, grid, b_true, s, with_stance)
                      for s in seeds])
    return (sum(o) / len(o), sum(fi) / len(fi), min(o), max(o),
            sum(rb), len(rb))


from ufc_gates import read_ceiling  # noqa: E402


def experiment(feats, out=print, ceilings=True, with_stance=False,
               only=None, seeds=(7, 17, 27)):
    co, base_tr, be = fit_baseline(feats, out=out, with_stance=with_stance)
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
        out(f"{label:40s} b={B:>6}  train_win={str(train_win):5s}  "
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
            # WALK DOWN FROM THE STRONGEST PLANT UNTIL THE PROBE IS
            # INFORMATIVE. The oracle refits the baseline on the synthetic
            # panel, so a plant the baseline can ABSORB comes back with a
            # NEGATIVE oracle — the refit carries the effect through inflated
            # main-effect coefficients and adding the true term on top then
            # double-counts and hurts. Read literally that makes any positive
            # measurement look like noise; it nearly buried LAYAGE in batch 3.
            # For SPMAIN and SWMAIN a negative oracle is not a bug at all, it
            # is the absorption theorem being demonstrated on demand.
            b_gen, o, fi, olo, ohi, n_rob, n_seed = None, 0.0, 0.0, 0.0, 0.0, 0, 0
            for cand in sorted(side, key=abs, reverse=True)[:4]:
                b_gen = cand
                o, fi, olo, ohi, n_rob, n_seed = probe(
                    feats, key, grid, cand, seeds=seeds, with_stance=with_stance)
                if o > 0:
                    break
                out(f"{label:40s}   (plant b={cand:+.2f} absorbed by the "
                    f"baseline, oracle {o:+.5f} — stepping down)")
            got = results[label][0]
            won = results[label][2] == "ROBUST WIN" and got > 0
            read = read_ceiling(got, won, o, olo, fi, n_rob, n_seed)
            out(f"{label:40s} oracle(b={b_gen:+.2f}) {o:+.5f} "
                f"[{olo:+.5f}..{ohi:+.5f}]  fitted {fi:+.5f}  "
                f"plant {n_rob}/{n_seed}  measured {got:+.5f}   {read}")
            results[label] = results[label] + (o, fi, n_rob, n_seed)
    return results


# ------------------------------------------------------------------ selftest
def _synth(cycle=0.0, sp_bonus=0.0, seed=23, n_bouts=7000):
    """A world with a real stance structure, and a roster that TURNS OVER.

    Two knobs, because the file makes two different claims and they need
    different worlds. `sp_bonus` puts a plain per-fighter southpaw edge into
    true skill — the absorption theorem says Elo eats it and SPMAIN must come
    back near-null. `cycle` puts a rock-paper-scissors matchup effect into the
    bout itself, which is not a per-fighter quantity at all and therefore
    cannot be eaten.

    ROSTER TURNOVER IS NOT DECORATION. Batch 4 learned this the hard way: a
    fixed pool that all debuts at once means every man has thirty bouts by the
    holdout, so any term keyed on inexperience is structurally zero over the
    entire scoring window and its plant can never be recovered at any strength.
    The real UFC has constant inflow, which is exactly why SPNEW has anything
    to bite on in 2025.

    SWITCH IS OVERWEIGHTED HERE (12% against roughly 5% in the cache) on
    purpose. The cycle can only be seen through bouts involving switch
    fighters, and a synthetic panel that reproduces the real scarcity would be
    testing the panel's thinness rather than the estimator. What the real panel
    can see is a question for the CEILING, which is measured on the real panel.
    """
    import random
    rng = random.Random(seed)
    DAY0 = 2010 * 365
    skill, born, gap, nxt, left, st = {}, {}, {}, {}, {}, {}
    meta, bouts = {}, []
    nxt_id = [0]

    def iso(n):
        y, rem = n // 365, n % 365
        return f"{y:04d}-{rem // 31 + 1:02d}-{rem % 28 + 1:02d}"

    def mint(day):
        i = nxt_id[0]
        nxt_id[0] += 1
        r = rng.random()
        st[i] = "O" if r < 0.66 else ("S" if r < 0.88 else "W")
        skill[i] = rng.gauss(0, 0.8) + (sp_bonus if st[i] == "S" else 0.0)
        born[i] = day // 365 - rng.randrange(22, 36)
        gap[i] = rng.uniform(90, 500)
        nxt[i] = day + rng.randrange(0, 300)
        left[i] = rng.randrange(3, 26)   # careers END
        meta[f"f{i}"] = {"dob": f"{born[i]}-06-15",
                         "stance": {"O": "Orthodox", "S": "Southpaw",
                                    "W": "Switch"}[st[i]]}
        return i

    pool = [mint(DAY0) for _ in range(220)]
    while len(bouts) < n_bouts:
        a = min(pool, key=lambda i: nxt[i])
        b = rng.choice(pool)
        if a == b:
            b = rng.choice([x for x in pool if x != a])
        day = nxt[a]
        z = skill[a] - skill[b] + cycle * CYC.get((st[a], st[b]), 0.0)
        won_a = 1 if rng.random() < 1 / (1 + math.exp(-z)) else 0
        ko = rng.random() < 0.32
        bouts.append({"date": iso(day), "a": f"F{a}", "b": f"F{b}",
                      "won_a": won_a,
                      "ko_loss_a": 1 if (not won_a and ko) else 0,
                      "ko_win_a": 1 if (won_a and ko) else 0})
        for f in (a, b):
            nxt[f] = day + int(rng.expovariate(1.0 / gap[f])) + 30
            left[f] -= 1
            if left[f] <= 0:
                pool.remove(f)
                pool.append(mint(day))
    bouts.sort(key=lambda x: x["date"])
    # THROUGH meta_from, NOT AROUND IT. The generator writes 'Orthodox' /
    # 'Southpaw' / 'Switch' exactly as ufcstats does, and walk_features expects
    # the O/S/W codes. Handing it the raw strings does NOT crash: st_known
    # comes back 1.0 because the field is truthy, every stance column comes
    # back 0.0 because no comparison matches, and the whole selftest then
    # reports NULL on a panel that was built to contain a 0.55-logit effect.
    # It did exactly that on the first run.
    return bouts, meta_from(meta)


def _pairfeat(sa, sb, key):
    """The value of one stance column for a single (sa, sb) matchup, computed
    through walk_features so the algebra below tests the CODE and not a second
    hand-written copy of it."""
    bts = [{"date": "2015-01-01", "a": "A", "b": "B", "won_a": 1,
            "ko_loss_a": 0, "ko_win_a": 0}]
    full = {"O": "Orthodox", "S": "Southpaw", "W": "Switch"}
    m = {"a": {"stance": sa}, "b": {"stance": sb}}
    return walk_features(bts, meta_from(
        {"A": {"stance": full[sa]}, "B": {"stance": full[sb]}}))[0][1][key]


def selftest():
    global SCORE_FROM, TRAIN_END, PERIODS
    SCORE_FROM, TRAIN_END = "2013-01-01", "2018-12-31"
    PERIODS = [("2019-01-01", "2019-12-31"), ("2020-01-01", "2020-12-31"),
               ("2021-01-01", "2026-12-31")]

    assert _days("2024-02-28", "2024-03-01") == 2, "2024 is a leap year"
    assert _days("2020-01-01", "2021-01-01") == 366

    # ---- THE THEOREM, CHECKED ON THE CODE RATHER THAN ON THE DERIVATION.
    # An antisymmetric stance effect is three numbers: its values on (O,S),
    # (O,W) and (S,W). Everything Elo can absorb has the form f(i) - f(j) and
    # therefore satisfies M(O,W) = M(O,S) + M(S,W). The two indicator columns
    # must obey that identity; the cycle column must violate it, and must be
    # orthogonal to both. If any of these four lines ever fails, CYCLE is no
    # longer the non-absorbable direction and every verdict below it is void.
    PAIRS = (("O", "S"), ("O", "W"), ("S", "W"))
    for k in ("sp_d", "sw_d", "cyc_d"):
        for x, y in PAIRS:
            assert _pairfeat(x, y, k) == -_pairfeat(y, x, k), (
                f"{k} is not antisymmetric on ({x},{y}) — a matchup column "
                "that does not flip with the corners is scoring the row order")
        assert _pairfeat(x, x, k) == 0.0
    for k in ("sp_d", "sw_d"):
        v = [_pairfeat(x, y, k) for x, y in PAIRS]
        assert abs(v[1] - (v[0] + v[2])) < 1e-12, (
            f"{k} was supposed to be the ABSORBABLE control and it is not "
            f"additive ({v}) — it has a cycle component, so a null on it "
            "would no longer prove what this file says it proves")
    cy = [_pairfeat(x, y, "cyc_d") for x, y in PAIRS]
    assert abs(cy[1] - (cy[0] + cy[2])) > 1.0, (
        f"CYCLE satisfies M(O,W) = M(O,S) + M(S,W) ({cy}), which means it IS "
        "of the form f(i)-f(j) and Elo can absorb it after all")
    for k in ("sp_d", "sw_d"):
        v = [_pairfeat(x, y, k) for x, y in PAIRS]
        dot = sum(p * q for p, q in zip(v, cy))
        assert abs(dot) < 1e-12, (
            f"CYCLE is not orthogonal to {k} (dot {dot}); the second pass "
            "would then move CYCLE's verdict and neither reading would be "
            "interpretable")

    # ---- the ceiling ladder. Pinned, because it has been wrong three times.
    assert read_ceiling(0.00050, True, 0.00040, 0.00038, 0.00020, 3, 3
                        ).startswith("measured >= ORACLE")
    assert read_ceiling(0.00030, True, 0.00040, 0.00038, 0.00020, 3, 3
                        ).startswith("LIVE"), "ordering bug is back"
    assert read_ceiling(-0.00001, False, 0.00038, 0.00035, 0.00037, 3, 3
                        ).startswith("DEAD")
    assert read_ceiling(-0.00003, False, 0.00006, 0.00002, 0.00008, 0, 3
                        ).startswith("STILL CANNOT BE SEEN")
    assert read_ceiling(0.0004, True, -0.0002, -0.0004, 0.0, 0, 3
                        ).startswith("PROBE UNINFORMATIVE")

    # ---- the grid-edge detector
    ok = {"a": 2.0, "c": -0.12, "g": -0.04, "L": -0.10}
    assert edges(ok) == [], edges(ok)
    assert edges(dict(ok, a=min(BASE_GRIDS["a"]))) == ["a"]
    assert "sp_d" in edges(ok, (("sp_d", max(ST_BASE_GRID)),))
    assert "sp_d" not in edges(ok, (("sp_d", 0.0),))

    # ---- an unrecognised stance must stay MISSING, not default to the mode
    m = meta_from({"Guy A": {"stance": "Open Stance"},
                   "Guy B": {"stance": "Southpaw"},
                   "Guy C": {"stance": ""}, "Guy D": {"stance": None}})
    assert "guy a" not in m, "'Open Stance' was folded into a real bucket"
    assert m["guy b"]["stance"] == "S"
    assert "guy c" not in m and "guy d" not in m

    # ---- every stance column must be OFF where a stance is unknown
    f0 = walk_features([{"date": "2015-01-01", "a": "X", "b": "Y", "won_a": 1,
                         "ko_loss_a": 0, "ko_win_a": 0}], {})[0][1]
    assert f0["st_known"] == 0.0
    for k in ("sp_d", "sw_d", "cyc_d", "spfam_d", "spnew_d", "xst_d"):
        assert f0[k] == 0.0, f"{k} invented a value with no stance data"

    # ---- SPNEW must decay with experience or it is SPMAIN under another name
    many = [{"date": f"2015-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "a": "L", "b": "S", "won_a": i % 2, "ko_loss_a": 0, "ko_win_a": 0}
            for i in range(30)]
    mm = meta_from({"L": {"stance": "Southpaw"}, "S": {"stance": "Orthodox"}})
    ff = walk_features(many, mm)
    first, last = ff[0][1]["spnew_d"], ff[-1][1]["spnew_d"]
    assert first > 0 and last > 0 and last < first / 4.0, (
        f"SPNEW barely decayed ({first:.3f} -> {last:.3f}); with NEW_TAU="
        f"{NEW_TAU} and 29 prior bouts it should be nearly gone, and a term "
        "that does not decay is the southpaw main effect in a wig")
    assert ff[0][1]["sp_d"] == 1.0 and ff[-1][1]["sp_d"] == 1.0, (
        "the absorbable indicator must NOT decay — it is the control")

    # ---- SPFAM must fall as a man gets reps against the other look
    fam0, fam1 = ff[0][1]["spfam_d"], ff[-1][1]["spfam_d"]
    assert fam0 == 0.0, (
        "at the first meeting neither man has seen the other's stance, so the "
        "unfamiliarity difference must be exactly zero, not merely small")
    assert abs(fam1) < 0.05, (
        f"after 29 mutual meetings SPFAM is still {fam1:+.3f} — the exposure "
        "counter is not accumulating")

    # ---- SAME-STANCE ROWS MUST BE SILENT on the cross-stance terms
    same = walk_features(
        [{"date": "2015-01-01", "a": "P", "b": "Q", "won_a": 1,
          "ko_loss_a": 0, "ko_win_a": 0}],
        meta_from({"P": {"stance": "Orthodox"},
                   "Q": {"stance": "Orthodox"}}))[0][1]
    assert same["st_known"] == 1.0
    for k in ("spfam_d", "xst_d", "cyc_d", "sp_d", "sw_d"):
        assert same[k] == 0.0, f"{k} spoke in an orthodox-vs-orthodox bout"

    # ---- CLAIM 1: a plain per-fighter southpaw edge is absorbable IN THE
    # ---- LIMIT, and the UFC does not reach the limit. What survives is
    # ---- concentrated on the men Elo has barely seen, so SPNEW must beat
    # ---- SPMAIN — the same relationship batch 4 found between RCHNEW and raw
    # ---- REACH. Asserting SPMAIN itself is NEAR ZERO would be asserting that
    # ---- Elo converges instantly, which is false and which the first draft of
    # ---- this file asserted anyway (SPMAIN came back +0.00581, a robust win).
    live, meta = _synth(sp_bonus=0.55)
    feats = walk_features(live, meta)
    # PRECONDITION, because the failure it catches is silent. If the generator
    # and walk_features disagree about the stance encoding, st_known still
    # reads 1.0 (the field is truthy) while every stance column reads 0.0, and
    # the experiment then reports NULL on a panel built to contain a 0.55-logit
    # effect. Counting live rows per column is the only thing that notices.
    for k in ("sp_d", "sw_d", "cyc_d", "spfam_d", "spnew_d", "xst_d"):
        nz = sum(1 for _, f in feats if f[k] != 0.0)
        assert nz > 200, (
            f"only {nz} rows of {len(feats)} carry a non-zero {k} — the "
            "synthetic panel is not exercising the column it is meant to test")
    buf = []
    r1 = experiment(feats, out=buf.append, ceilings=False)
    spm = r1["SPMAIN  southpaw indicator [ABSORBABLE]"][0]
    spn = r1["SPNEW   stance where Elo is blind"][0]
    cyc0 = r1["CYCLE   O>S>W>O, orthogonal to Elo"][0]
    assert spm > 0.0, (
        f"a per-fighter southpaw bonus of 0.55 logits was planted and SPMAIN "
        f"recovered {spm:+.5f} — the column cannot even see an effect that "
        "was written directly into it\n" + "\n".join(buf))
    assert spn > spm, (
        f"SPNEW {spn:+.5f} did not beat SPMAIN {spm:+.5f}. The unabsorbed part "
        "of a per-fighter edge is supposed to live on the fighters Elo has not "
        "learned yet; if the ignorance weighting buys nothing, SPNEW is SPMAIN "
        "with extra arithmetic and should be dropped\n" + "\n".join(buf))
    assert cyc0 < spm, (
        f"CYCLE picked up {cyc0:+.5f} from a world containing NO cycle, "
        "against SPMAIN's {spm:+.5f}. A term that reads a plain per-fighter "
        "bonus as a matchup cycle is not orthogonal to the absorbable "
        "subspace in practice, whatever the algebra says\n" + "\n".join(buf))

    # ---- CLAIM 2: a CYCLE is NOT eaten, because Elo cannot represent it
    live2, meta2 = _synth(cycle=0.55, seed=31)
    feats2 = walk_features(live2, meta2)
    buf2 = []
    r2 = experiment(feats2, out=buf2.append, ceilings=False)
    cyc = r2["CYCLE   O>S>W>O, orthogonal to Elo"][0]
    cyc_v = r2["CYCLE   O>S>W>O, orthogonal to Elo"][2]
    spm2 = r2["SPMAIN  southpaw indicator [ABSORBABLE]"][0]
    assert cyc > 0.0030 and cyc_v == "ROBUST WIN", (
        f"a rock-paper-scissors cycle of 0.55 logits was planted and CYCLE "
        f"recovered {cyc:+.5f} ({cyc_v}). If the one direction Elo provably "
        "cannot represent is not recoverable on a panel built to contain it, "
        "no null this file prints is readable\n" + "\n".join(buf2))
    assert cyc > spm2, (
        f"in a world whose ONLY stance structure is a cycle, the absorbable "
        f"indicator SPMAIN scored {spm2:+.5f} against CYCLE's {cyc:+.5f}. The "
        "two are supposed to be orthogonal; if the indicator can eat a cycle, "
        "the second pass is not a control, it is a competitor\n"
        + "\n".join(buf2))

    # ---- the plant must be recoverable, or the ladder's 'invisible' branch
    # ---- is untestable and every DEAD verdict is unsupported
    o, fi, olo, ohi, n_rob, n_seed = probe(
        feats2, "cyc_d", ANGLES[2][2], 0.60, seeds=(7, 17))
    assert o > 0, f"oracle ceiling collapsed on a live panel: {o}"
    assert n_rob >= 1, f"a planted CYCLE was never recovered ({n_rob}/{n_seed})"

    # ---- leak proof: flip every outcome after a cutoff on a DEEP COPY;
    # ---- features dated before it must be byte-identical
    f1 = [(bt["date"], f) for bt, f in feats2 if bt["date"] <= "2016-01-01"]
    poison = [dict(bt) for bt in live2]
    for bt in poison:
        if bt["date"] > "2016-01-01":
            bt["won_a"] = 1 - bt["won_a"]
    f2 = [(bt["date"], f) for bt, f in walk_features(poison, meta2)
          if bt["date"] <= "2016-01-01"]
    assert json.dumps(f1, sort_keys=True) == json.dumps(f2, sort_keys=True), "LEAK"

    print(f"UFC ANGLES-5 SELFTEST PASS — CYCLE is antisymmetric, non-additive "
          f"and orthogonal to both indicators; a planted southpaw bonus leaves "
          f"a residual that SPNEW reads better than SPMAIN ({spn:+.5f} vs "
          f"{spm:+.5f}) and CYCLE does not read at all ({cyc0:+.5f}); a "
          f"planted cycle is recovered ({cyc:+.5f}, {cyc_v}) where SPMAIN "
          f"cannot see it ({spm2:+.5f}); plant recoverable {n_rob}/{n_seed}; "
          f"leak-free")
    return 0


def main():
    bouts = load_bouts(os.path.join(HERE, "data", "fighter_bouts.csv"))
    meta = load_meta(os.path.join(HERE, "fighter_meta_cache.json"))
    feats = walk_features(bouts, meta)
    lines = []

    def tee(s):
        print(s)
        lines.append(s)

    agek = sum(1 for _, f in feats if f["age_known"])
    stk = sum(1 for _, f in feats if f["st_known"])
    tee("=" * 78)
    tee("UFC ANGLES 5 — stance, and the one direction Elo cannot represent")
    tee("=" * 78)
    tee(f"unique bouts: {len(bouts)} ({bouts[0]['date']}..{bouts[-1]['date']})")
    tee(f"both DOB known: {agek} ({100 * agek / len(bouts):.0f}%)   "
        f"both stances known: {stk} ({100 * stk / len(bouts):.0f}%)")

    hold = [(bt, f) for bt, f in feats if bt["date"] >= PERIODS[0][0]]
    hk = sum(1 for _, f in hold if f["st_known"])
    tee(f"HOLDOUT both stances known: {hk}/{len(hold)} "
        f"({100.0 * hk / max(len(hold), 1):.1f}%) — round 7 had this at 1.0%")

    mix = defaultdict(int)
    for bt, f in feats:
        if f["st_known"]:
            mix[(abs(f["sp_d"]), abs(f["sw_d"]), abs(f["cyc_d"]))] += 1
    tee("")
    tee("Elo can represent 1(i=S) - 1(j=S) and 1(i=W) - 1(j=W) EXACTLY, so")
    tee("SPMAIN and SWMAIN are controls and a null on either is expected.")
    tee("CYCLE is the component orthogonal to both — the failure of")
    tee("M(O,W) = M(O,S) + M(S,W) — and no Elo rating can hold it.")

    sub = [(bt, f) for bt, f in feats if f["age_known"] and f["st_known"]]
    tee("")
    tee(f"--- DECISIVE SUBSET: age-complete AND stance-complete (n={len(sub)})")
    experiment(sub, out=tee)

    tee("")
    tee("--- SECOND PASS: the two ABSORBABLE indicators are now IN THE")
    tee("    BASELINE. SPNEW and SPFAM need this, because a term built on the")
    tee("    southpaw indicator will impersonate the indicator itself if the")
    tee("    indicator is not already spoken for. CYCLE is orthogonal to both")
    tee("    by construction, so its verdict should barely move — if it moves")
    tee("    a lot, the orthogonality claim is wrong and nothing here holds.")
    experiment(sub, out=tee, with_stance=True, only=CANDIDATES)

    tee("")
    tee("Ship rule: ROBUST WIN in the SECOND PASS, and a measured gain at or")
    tee("above the FITTED threshold while under the ORACLE bound.")

    vd = os.environ.get("VERDICT_OUT") or os.path.join(
        HERE, "..", "experiments", "UFC-ANGLES5-VERDICT.md")
    os.makedirs(os.path.dirname(vd), exist_ok=True)
    with open(vd, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"verdict -> {vd}")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
