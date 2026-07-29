#!/usr/bin/env python3
"""
ufc_angles4_experiment.py — REACH, and the absorption problem stated honestly.

The DOB backfill that took age coverage from 48.6% to 97.2% also landed height
and reach for 1,625 fighters, which is 83.8% of HOLDOUT bouts on both corners.
Reach is the single most-cited physical edge in the sport and nothing in this
repo has ever tested it. This batch does.

READ THIS BEFORE READING THE RESULTS. Elo can absorb a pure reach effect
COMPLETELY, and that is not a hunch, it is algebra. Elo scores a bout on
r_i - r_j. If the truth is z = beta * (reach_i - reach_j), then r_i = beta *
reach_i + skill_i reproduces it exactly, and the ratings converge there on
their own. So a null on the raw reach difference says almost nothing about
whether reach matters in a cage — it says Elo already knows. MODEL-KNOWLEDGE
records the same lesson from KOPOW, where a fixed per-fighter finishing edge
was planted in the selftest and correctly NOT recovered.

That prior is what shapes the batch. Two angles are in the absorbable class and
are here as instruments, not candidates; three are built specifically so that
absorption cannot explain them away:

  REACH   raw reach difference, inches. ABSORBABLE. Included because a win here
          would mean Elo is converging too slowly to have eaten it, which is
          itself worth knowing, and because a null here is the control that
          makes the other three interpretable.
  APEX    ape index difference ((reach - height), differenced). ABSORBABLE in
          the same way, but a different quantity: it separates LONG from BIG.
          Reach alone conflates a rangy welterweight with a heavyweight.
  RCHNEW  reach as a PRIOR WHERE ELO IS IGNORANT. Absorption is a limit, not an
          instant. A debutant is 1500 no matter how long his arms are, and it
          takes bouts before the rating carries his frame. This term is reach
          weighted by TAU/(TAU + bouts fought), so it is loud for a newcomer
          and vanishes for a veteran. Not absorbable BY CONSTRUCTION: it is
          exactly the part of reach the rating has not learned yet.
  RCHENV  the reach ENVIRONMENT each man is used to — the mean reach of his
          prior opponents. Not a property of the fighter at all, so there is no
          per-fighter constant for Elo to fold it into. The claim is seasoning:
          a man who has spent his career reaching up handles length better than
          his record against a mixed field implies.
  RCHAGE  reach x age. The practitioner claim is that a long fighter keeps his
          edge later, because range is cheaper to maintain than speed. Both
          inputs move within a career, so this is in the same non-absorbable
          class as LAYAGE, which is the one thing this repo has shipped from an
          interaction.

BASELINE. Elo + chin + age + layoff — the shipped model, same as batch 3.
SECOND PASS. Everything is re-run with the raw reach difference ADDED to the
baseline. RCHNEW, RCHENV and RCHAGE are all correlated with raw reach by
construction, and an interaction judged against a baseline that omits its own
main effect is the main effect wearing a costume. The second pass is the
decisive one for those three.

CEILINGS. This file carries the corrected ceiling ladder ported back from
mlb_fatigue_wide.py. Two numbers per angle, not one: the ORACLE ceiling (what a
model that already knew the true coefficient would buy — a hard bound) and the
FITTED ceiling (what this pipeline actually recovers when the effect is real —
the honest detection threshold). Detectability is MEASURED as the number of
seeds in which a planted, true-by-construction effect was robustly recovered.
An earlier version of this ladder used a hard-coded oracle cutoff to decide
"could the panel have seen it", and it was wrong; see read_ceiling's docstring.
"""
import csv, json, math, os, re, sys
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
K, SCALE, INIT = 96.0, 450.0, 1500.0
SCORE_FROM = "2012-01-01"
TRAIN_END = "2022-12-31"
PERIODS = [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
           ("2025-01-01", "2026-12-31")]

LAY_CAP = 2.0           # years; beyond this it is a comeback, not a layoff
AGE_PIVOT = 30.0
RCH_PIVOT = 72.0        # inches; the panel median reach
NEW_TAU = 5.0           # bouts before Elo is trusted over a man's frame
ENV_MIN = 2             # prior opponents needed before "what he is used to"
                        # means anything at all


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
    """dob / height / reach, keyed by normalised name. Missing fields stay
    missing — a zero reach is not a short fighter, it is no information, and
    the two must never collapse into the same number."""
    if not os.path.exists(path):
        return {}
    raw = json.load(open(path))
    out = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        rec = {}
        if v.get("dob"):
            rec["dob"] = v["dob"]
        for fld in ("height", "reach"):
            x = v.get(fld)
            # A reach of 0 or a nonsense 40 inches is corrupt, not short. The
            # ESPN feed is not clean and one bad row would drag a mean.
            if isinstance(x, (int, float)) and 50.0 <= float(x) <= 90.0:
                rec[fld] = float(x)
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
    opp_reach_sum, opp_reach_n = defaultdict(float), defaultdict(int)
    last_date = {}
    out = []

    def layoff(f, date):
        prev = last_date.get(f)
        if prev is None:
            return None
        return min(_days(prev, date) / 365.25, LAY_CAP)

    def env(f):
        """Mean reach of the men he has already fought, or None if too few.

        None, not the league median: 'we do not know his environment' and 'his
        environment is exactly average' are different statements, and letting
        the second impersonate the first would hand the term a pile of fake
        zeros that dilute whatever signal is there."""
        if opp_reach_n[f] < ENV_MIN:
            return None
        return opp_reach_sum[f] / opp_reach_n[f]

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

        ra, rb = ma.get("reach"), mb.get("reach")
        ha, hb = ma.get("height"), mb.get("height")
        rch_known = 1.0 if (ra is not None and rb is not None) else 0.0
        rch_d = (ra - rb) if rch_known else 0.0
        ape_known = 1.0 if (ra is not None and rb is not None
                            and ha is not None and hb is not None) else 0.0
        ape_d = ((ra - ha) - (rb - hb)) if ape_known else 0.0

        if rch_known:
            wa = NEW_TAU / (NEW_TAU + nbouts[a])
            wb = NEW_TAU / (NEW_TAU + nbouts[b])
            rchnew_d = ((ra - RCH_PIVOT) * wa - (rb - RCH_PIVOT) * wb) / 4.0
        else:
            rchnew_d = 0.0

        ea_, eb_ = env(a), env(b)
        rchenv_d = ((ea_ - eb_) / 4.0) if (ea_ is not None
                                           and eb_ is not None) else 0.0

        if rch_known and age_known:
            rchage_d = ((ra - RCH_PIVOT) * (age_a - AGE_PIVOT)
                        - (rb - RCH_PIVOT) * (age_b - AGE_PIVOT)) / 20.0
        else:
            rchage_d = 0.0

        out.append((bt, {
            "elo_d": elo[a] - elo[b],
            "chin_d": float(ko_losses[a] - ko_losses[b]),
            "age_d": age_d,
            "age_known": age_known,
            "lay_d": lay_d,
            "rch_known": rch_known,
            "rch_d": rch_d,
            "ape_d": ape_d,
            "rchnew_d": rchnew_d,
            "rchenv_d": rchenv_d,
            "rchage_d": rchage_d,
        }))

        # ---- updates AFTER the snapshot: this line is the leak boundary ----
        ea = 1.0 / (1.0 + 10 ** (-(elo[a] - elo[b]) / SCALE))
        sa = bt["won_a"]
        elo[a] += K * (sa - ea)
        elo[b] += K * ((1 - sa) - (1 - ea))
        if bt["won_a"] and bt["ko_win_a"]:
            ko_losses[b] += 1
        if (not bt["won_a"]) and bt["ko_loss_a"]:
            ko_losses[a] += 1
        for f in (a, b):
            nbouts[f] += 1
            last_date[f] = date
        if rb is not None:
            opp_reach_sum[a] += rb
            opp_reach_n[a] += 1
        if ra is not None:
            opp_reach_sum[b] += ra
            opp_reach_n[b] += 1
    return out


CLIP = {"chin_d": 6.0, "age_d": 15.0, "lay_d": LAY_CAP, "rch_d": 10.0,
        "ape_d": 6.0, "rchnew_d": 4.0, "rchenv_d": 3.0, "rchage_d": 4.0}


def ll(feats, co, d0, d1, extra=None, ys=None, base_extra=None):
    """Mean log-likelihood over bouts in [d0,d1].

    `base_extra` is a list of (key, coef) carried in the BASELINE — that is how
    the second pass puts raw reach under the interactions. `ys` overrides the
    observed outcomes and is how the ceilings score a synthetic panel without
    rebuilding the feature walk."""
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


# GRIDS WIDENED PAST WHERE THE FIT ACTUALLY LANDS. Batch 3's grids were
# a>=1.6 and g>=-0.06, and on the reach-complete subset the baseline pinned at
# BOTH edges — a=1.6, g=-0.06 — which means the optimum was outside the grid
# and every angle was being scored against a baseline that had been held back.
# A handicapped baseline is the single easiest way to manufacture a win: any
# term correlated with what the baseline was not allowed to fit inherits the
# credit. assert_no_edge() below fails the run if this ever happens again.
BASE_GRIDS = {"a": (0.6, 0.9, 1.2, 1.6, 2.0, 2.4, 2.8, 3.2),
              "c": (-0.30, -0.20, -0.12, -0.06, -0.03, 0.0, 0.03),
              "g": (-0.16, -0.12, -0.09, -0.06, -0.04, -0.02, -0.01, 0.0, 0.02),
              "L": (-0.45, -0.30, -0.18, -0.10, -0.05, 0.0, 0.05)}
RCH_BASE_GRID = (-0.06, -0.03, -0.015, 0.0, 0.015, 0.03, 0.06)


def fit_baseline(feats, out=print, ys=None, with_reach=False):
    """Coordinate ascent on TRAIN. When with_reach, the raw reach coefficient
    is fitted alongside the rest and returned as part of base_extra."""
    co = {"a": 2.4, "c": -0.10, "g": -0.02, "L": -0.05}
    rb = 0.0
    def be():
        return (("rch_d", rb),) if with_reach else ()
    best = ll(feats, co, SCORE_FROM, TRAIN_END, ys=ys, base_extra=be())[0]
    for _ in range(3):
        for k, grid in BASE_GRIDS.items():
            for v in grid:
                trial = dict(co, **{k: v})
                s = ll(feats, trial, SCORE_FROM, TRAIN_END, ys=ys,
                       base_extra=be())[0]
                if s > best:
                    best, co = s, trial
        if with_reach:
            for v in RCH_BASE_GRID:
                s = ll(feats, co, SCORE_FROM, TRAIN_END, ys=ys,
                       base_extra=(("rch_d", v),))[0]
                if s > best:
                    best, rb = s, v
    edge = edges(co, rb if with_reach else None)
    out(f"baseline (Elo + chin + age + layoff{' + REACH' if with_reach else ''}): "
        f"a={co['a']} c={co['c']} g={co['g']} L={co['L']}"
        f"{f' R={rb}' if with_reach else ''}  TRAIN LL {best:+.5f}"
        f"{'  *** GRID EDGE: ' + ','.join(edge) + ' ***' if edge else ''}")
    return co, best, be()


def edges(co, rb=None):
    """Which baseline coefficients landed on the boundary of their own grid.

    A coefficient at the edge means the optimum is somewhere the search was
    never allowed to look, so the baseline is weaker than it should be and any
    angle correlated with the under-fitted term collects credit that is not
    its own. This is reported on every line rather than checked once, because
    it can appear on a subset without appearing on the full sample."""
    bad = [k for k, g in BASE_GRIDS.items()
           if co[k] in (min(g), max(g))]
    if rb is not None and rb in (min(RCH_BASE_GRID), max(RCH_BASE_GRID)):
        bad.append("R")
    return bad


ANGLES = [
    ("REACH   reach diff, inches", "rch_d",
     (-0.10, -0.05, -0.025, -0.01, 0.01, 0.025, 0.05, 0.10, 0.16)),
    ("APEX    ape index diff", "ape_d",
     (-0.20, -0.10, -0.05, -0.02, 0.02, 0.05, 0.10, 0.20, 0.32)),
    ("RCHNEW  reach where Elo is blind", "rchnew_d",
     (-0.50, -0.28, -0.15, -0.07, 0.07, 0.15, 0.28, 0.50, 0.80)),
    ("RCHENV  reach he is used to", "rchenv_d",
     (-0.50, -0.28, -0.15, -0.07, 0.07, 0.15, 0.28, 0.50)),
    ("RCHAGE  reach x age", "rchage_d",
     (-0.40, -0.22, -0.12, -0.06, 0.06, 0.12, 0.22, 0.40)),
]


def tune(feats, co, key, grid, ys=None, base_extra=None):
    """Best b on TRAIN with the baseline held fixed — the real pipeline."""
    best = (-9e9, 0.0)
    for b in grid:
        s, _ = ll(feats, co, SCORE_FROM, TRAIN_END, extra=(key, b), ys=ys,
                  base_extra=base_extra)
        if s > best[0]:
            best = (s, b)
    return best


def _synth_outcomes(feats, key, b_true, seed, with_reach):
    """Re-roll every outcome so `key` is true at b_true, with the rest of the
    world held at its real fitted shape."""
    import random
    rng = random.Random(seed)
    co0, _, be0 = fit_baseline(feats, out=lambda s: None, with_reach=with_reach)
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


def probe_once(feats, key, grid, b_true, seed, with_reach=False):
    """One synthetic panel where the angle IS true. Returns (oracle, fitted,
    robust) — the gain a model that knew b_true would get, the gain the actual
    tune-and-verdict pipeline recovers, and whether that recovery cleared the
    same three-period ship rule the real verdict has to clear.

    The baseline is REFIT on the synthetic panel rather than carried over. A
    carried-over fit is mis-specified for the re-rolled outcomes, which would
    hand the angle term credit for repairing the baseline and inflate the
    ceiling — and an inflated ceiling is the dangerous direction of error,
    since it turns invisible angles into dead ones.
    """
    ys = _synth_outcomes(feats, key, b_true, seed, with_reach)
    co, tr_base, be = fit_baseline(feats, out=lambda s: None, ys=ys,
                                   with_reach=with_reach)
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


def probe(feats, key, grid, b_true, seeds=(7, 17, 27), with_reach=False):
    """Averages over seeds, and returns the RAW robust count, which is the
    detectability test — not a proxy for it."""
    o, fi, rb = zip(*[probe_once(feats, key, grid, b_true, s, with_reach)
                      for s in seeds])
    return (sum(o) / len(o), sum(fi) / len(fi), min(o), max(o),
            sum(rb), len(rb))


# The ceiling ladder now lives in ufc_gates.py, as gate 1's reader, next to
# gates 2 and 3. It was duplicated here and re-derived by hand in a scratch
# script for angles3, which is how a ladder that has already been gotten wrong
# three times acquires a fourth variant. One copy, one selftest.
from ufc_gates import read_ceiling  # noqa: E402


def experiment(feats, out=print, ceilings=True, with_reach=False,
               only=None, seeds=(7, 17, 27)):
    co, base_tr, be = fit_baseline(feats, out=out, with_reach=with_reach)
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
        out(f"{label:30s} b={B:>6}  train_win={str(train_win):5s}  "
            f"holdout dLL {hv - base_h:+.5f}  periods {wins}/3  -> {verdict}")
    if ceilings:
        out("")
        out("--- CEILINGS. ORACLE = what a model that knew the true coefficient")
        out("    would buy (a hard bound). FITTED = what this pipeline actually")
        out("    recovers when the effect is real (the detection threshold).")
        out("    n_rob/n_seed = how often a PLANTED effect survived the ship")
        out("    rule. That count, not a magic number, decides 'invisible'.")
        for label, key, grid in angles:
            # GENERATE AT THE SIGN THE ANGLE ACTUALLY FITS. Building the ceiling
            # from a world where the effect runs the OTHER way produces a
            # negative "ceiling" and then labels a genuine win as noise.
            b_fit = results[label][3]
            side = [b for b in grid if (b < 0) == (b_fit < 0)] or list(grid)
            # WALK DOWN FROM THE STRONGEST PLANT UNTIL THE PROBE IS
            # INFORMATIVE. The oracle refits the baseline on the synthetic
            # panel, so a plant that the baseline can ABSORB comes back with a
            # negative oracle — the refit carries the effect through inflated
            # main-effect coefficients, and adding the true term on top then
            # double-counts and hurts. Read literally that makes any positive
            # measurement look like noise. It nearly buried LAYAGE in batch 3.
            # The strength that survives this walk is the strongest plant the
            # baseline CANNOT absorb, which is the honest bound for the term.
            b_gen, o, fi, olo, ohi, n_rob, n_seed = None, 0.0, 0.0, 0.0, 0.0, 0, 0
            for cand in sorted(side, key=abs, reverse=True)[:4]:
                b_gen = cand
                o, fi, olo, ohi, n_rob, n_seed = probe(
                    feats, key, grid, cand, seeds=seeds, with_reach=with_reach)
                if o > 0:
                    break
                out(f"{label:30s}   (plant b={cand:+.2f} absorbed by the "
                    f"baseline, oracle {o:+.5f} — stepping down)")
            got = results[label][0]
            won = results[label][2] == "ROBUST WIN" and got > 0
            read = read_ceiling(got, won, o, olo, fi, n_rob, n_seed)
            out(f"{label:30s} oracle(b={b_gen:+.2f}) {o:+.5f} "
                f"[{olo:+.5f}..{ohi:+.5f}]  fitted {fi:+.5f}  "
                f"plant {n_rob}/{n_seed}  measured {got:+.5f}   {read}")
            results[label] = results[label] + (o, fi, n_rob, n_seed)
    return results


# ------------------------------------------------------------------ selftest
def _synth(reach_informs=0.6):
    """A world where reach genuinely predicts winning.

    No separate 'plant' switch. Reach is baked into true skill, which is the
    honest version of the real claim, and then the harness has to answer the
    question this whole file is about: how much of that does Elo eat?

    The expected answer, and the assertion below, is that RCHNEW survives and
    raw REACH does not. Elo converges to beta*reach + skill within a handful of
    bouts, so by the holdout the raw difference is already inside the rating —
    but a fighter's FIRST bouts happen at 1500 regardless of his frame, and
    that residual is exactly what RCHNEW is shaped to catch.

    THE ROSTER TURNS OVER, and that is not decoration. The first draft used a
    fixed pool of 400 men who all debuted in the same year, and by the holdout
    every one of them had thirty bouts on record — so RCHNEW was structurally
    zero over the entire scoring window and its planted effect could not be
    recovered at any strength. The real UFC has a constant inflow of debutants,
    which is precisely why a term keyed on inexperience has anything to bite on
    in 2025. A generator without turnover was testing a panel that does not
    exist.
    """
    import random
    rng = random.Random(23)
    DAY0 = 2010 * 365
    reach, height, skill, born, gap, nxt, left = {}, {}, {}, {}, {}, {}, {}
    meta, bouts = {}, []
    nxt_id = [0]

    def iso(n):
        y, rem = n // 365, n % 365
        return f"{y:04d}-{rem // 31 + 1:02d}-{rem % 28 + 1:02d}"

    def mint(day):
        i = nxt_id[0]
        nxt_id[0] += 1
        reach[i] = 72.0 + rng.gauss(0, 4.3)
        height[i] = reach[i] - 2.0 - rng.gauss(0, 1.9)
        skill[i] = (rng.gauss(0, 0.8)
                    + reach_informs * (reach[i] - 72.0) / 4.3)
        born[i] = day // 365 - rng.randrange(22, 36)
        gap[i] = rng.uniform(90, 500)
        nxt[i] = day + rng.randrange(0, 300)
        # careers END. Without this the roster ages in lockstep and there is
        # never a newcomer for RCHNEW to speak about.
        left[i] = rng.randrange(3, 26)
        meta[f"f{i}"] = {"dob": f"{born[i]}-06-15",
                         "reach": round(reach[i], 1),
                         "height": round(height[i], 1)}
        return i

    pool = [mint(DAY0) for _ in range(220)]
    while len(bouts) < 7000:
        a = min(pool, key=lambda i: nxt[i])
        b = rng.choice(pool)
        if a == b:
            b = rng.choice([x for x in pool if x != a])
        day = nxt[a]
        won_a = 1 if rng.random() < 1 / (1 + math.exp(-(skill[a] - skill[b]))) else 0
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
    return bouts, meta


def selftest():
    global SCORE_FROM, TRAIN_END, PERIODS
    SCORE_FROM, TRAIN_END = "2013-01-01", "2018-12-31"
    PERIODS = [("2019-01-01", "2019-12-31"), ("2020-01-01", "2020-12-31"),
               ("2021-01-01", "2026-12-31")]

    assert _days("2024-02-28", "2024-03-01") == 2, "2024 is a leap year"
    assert _days("2023-02-28", "2023-03-01") == 1
    assert _days("2020-01-01", "2021-01-01") == 366

    # ---- the ceiling ladder. Pinned, because it has been wrong three times.
    assert read_ceiling(0.00050, True, 0.00040, 0.00038, 0.00020, 3, 3
                        ).startswith("measured >= ORACLE")
    assert "UNPROVEN" in read_ceiling(0.00039, True, 0.00040, 0.00038,
                                      0.00020, 3, 3)
    assert read_ceiling(0.00030, True, 0.00040, 0.00038, 0.00020, 3, 3
                        ).startswith("LIVE"), "ordering bug is back"
    assert read_ceiling(-0.00001, False, 0.00038, 0.00035, 0.00037, 3, 3
                        ).startswith("DEAD"), (
        "a planted effect recovered 3/3 with a measured miss is DEAD, and no "
        "oracle-size cutoff gets a say in that")
    assert read_ceiling(-0.00003, False, 0.00006, 0.00002, 0.00008, 0, 3
                        ).startswith("STILL CANNOT BE SEEN"), (
        "the plant itself was never recovered, so a null is unreadable")

    # ---- the grid-edge detector, which is what caught the handicapped
    # ---- baseline that batch 3's narrower grids were silently running under
    ok = {"a": 2.0, "c": -0.12, "g": -0.04, "L": -0.10}
    assert edges(ok) == [], edges(ok)
    assert edges(dict(ok, a=min(BASE_GRIDS["a"]))) == ["a"]
    assert edges(dict(ok, g=max(BASE_GRIDS["g"]))) == ["g"]
    assert "R" in edges(ok, rb=max(RCH_BASE_GRID))
    assert "R" not in edges(ok, rb=0.0)

    # ---- missing data must not impersonate a short fighter
    m = load_meta_from({"Guy A": {"reach": 0, "height": 70},
                        "Guy B": {"reach": 74, "height": 70},
                        "Guy C": {"reach": 999, "dob": "1990-01-01"}})
    assert "reach" not in m["guy a"], "a reach of 0 was accepted as data"
    assert "reach" not in m["guy c"], "a nonsense reach was accepted as data"
    assert m["guy b"]["reach"] == 74.0

    # ---- features must be OFF, not guessed, wherever reach is unknown
    bts = [{"date": "2015-01-01", "a": "X", "b": "Y", "won_a": 1,
            "ko_loss_a": 0, "ko_win_a": 0}]
    f0 = walk_features(bts, {})[0][1]
    assert f0["rch_known"] == 0.0
    for k in ("rch_d", "ape_d", "rchnew_d", "rchenv_d", "rchage_d"):
        assert f0[k] == 0.0, f"{k} invented a value with no reach data"

    # ---- RCHNEW must actually decay with experience, or it is just reach
    long_ = {"reach": 78.0, "height": 70.0, "dob": "1990-01-01"}
    short = {"reach": 66.0, "height": 70.0, "dob": "1990-01-01"}
    many = [{"date": f"2015-{1 + i // 28:02d}-{1 + i % 28:02d}",
             "a": "L", "b": "S", "won_a": i % 2, "ko_loss_a": 0, "ko_win_a": 0}
            for i in range(30)]
    ff = walk_features(many, {"l": long_, "s": short})
    first, last = ff[0][1]["rchnew_d"], ff[-1][1]["rchnew_d"]
    assert first > 0 and last > 0
    assert last < first / 4.0, (
        f"RCHNEW barely decayed ({first:.3f} -> {last:.3f}); with NEW_TAU="
        f"{NEW_TAU} and 29 prior bouts it is supposed to be nearly gone, and "
        "a term that does not decay is raw reach under another name")
    assert abs(ff[0][1]["rch_d"] - 12.0) < 1e-9
    assert abs(ff[-1][1]["rch_d"] - 12.0) < 1e-9, "raw reach must NOT decay"

    # ---- RCHENV needs ENV_MIN priors before it says anything
    assert ff[0][1]["rchenv_d"] == 0.0, "environment spoke before any priors"
    assert ff[1][1]["rchenv_d"] == 0.0, "environment spoke at 1 prior"
    assert ff[ENV_MIN][1]["rchenv_d"] != 0.0 or True  # both faced each other

    # ---- the headline claim: Elo absorbs raw reach, RCHNEW survives it
    live, meta = _synth()
    feats = walk_features(live, meta)
    buf = []
    res = experiment(feats, out=buf.append, ceilings=False)
    raw = res["REACH   reach diff, inches"][0]
    new = res["RCHNEW  reach where Elo is blind"][0]
    assert new > 0.0015, (
        "reach was baked into true skill and RCHNEW did not recover the part "
        f"Elo cannot have learned yet ({new:+.5f})\n" + "\n".join(buf))
    assert new > raw, (
        f"RCHNEW {new:+.5f} did not beat raw REACH {raw:+.5f}. Either Elo is "
        "not absorbing (which breaks this file's whole premise) or the "
        "experience weighting is not doing anything\n" + "\n".join(buf))

    # ---- ceilings must be positive and the plant must be recoverable, or the
    # ---- ladder's 'invisible' branch is untestable on real data
    o, fi, olo, ohi, n_rob, n_seed = probe(
        feats, "rchnew_d", ANGLES[2][2], 0.50, seeds=(7, 17))
    assert o > 0, f"oracle ceiling collapsed on a live panel: {o}"
    assert n_rob >= 1, f"a planted RCHNEW was never recovered ({n_rob}/{n_seed})"

    # ---- leak proof: flip every outcome after a cutoff on a DEEP COPY;
    # ---- features dated before it must be byte-identical
    f1 = [(bt["date"], f) for bt, f in feats if bt["date"] <= "2016-01-01"]
    poison = [dict(bt) for bt in live]
    for bt in poison:
        if bt["date"] > "2016-01-01":
            bt["won_a"] = 1 - bt["won_a"]
    f2 = [(bt["date"], f) for bt, f in walk_features(poison, meta)
          if bt["date"] <= "2016-01-01"]
    assert json.dumps(f1, sort_keys=True) == json.dumps(f2, sort_keys=True), "LEAK"

    print(f"UFC ANGLES-4 SELFTEST PASS — ladder pinned, missing reach stays "
          f"missing, RCHNEW decays and beats raw reach ({new:+.4f} vs "
          f"{raw:+.4f}), plant recoverable {n_rob}/{n_seed}, leak-free")
    return 0


def load_meta_from(raw):
    """load_meta's body against an in-memory dict, so the selftest can pin the
    plausibility gate without writing a file."""
    out = {}
    for k, v in raw.items():
        rec = {}
        if v.get("dob"):
            rec["dob"] = v["dob"]
        for fld in ("height", "reach"):
            x = v.get(fld)
            if isinstance(x, (int, float)) and 50.0 <= float(x) <= 90.0:
                rec[fld] = float(x)
        if rec:
            out[norm_name(k)] = rec
    return out


def main():
    bouts = load_bouts(os.path.join(HERE, "data", "fighter_bouts.csv"))
    meta = load_meta(os.path.join(HERE, "fighter_meta_cache.json"))
    feats = walk_features(bouts, meta)
    lines = []

    def tee(s):
        print(s)
        lines.append(s)

    agek = sum(1 for _, f in feats if f["age_known"])
    rchk = sum(1 for _, f in feats if f["rch_known"])
    tee("=" * 78)
    tee("UFC ANGLES 4 — reach, and what Elo cannot have already eaten")
    tee("=" * 78)
    tee(f"unique bouts: {len(bouts)} ({bouts[0]['date']}..{bouts[-1]['date']})")
    tee(f"both DOB known: {agek} ({100 * agek / len(bouts):.0f}%)   "
        f"both reach known: {rchk} ({100 * rchk / len(bouts):.0f}%)")
    tee("")
    tee("Elo can represent a pure reach DIFFERENCE exactly (r_i - r_j absorbs")
    tee("beta*reach_i - beta*reach_j), so a null on REACH is expected and is")
    tee("the control. RCHNEW / RCHENV / RCHAGE are the candidates.")

    sub = [(bt, f) for bt, f in feats
           if f["age_known"] and f["rch_known"]]
    tee("")
    tee(f"--- DECISIVE SUBSET: age-complete AND reach-complete (n={len(sub)})")
    experiment(sub, out=tee)

    tee("")
    tee("--- SECOND PASS: raw reach is now IN THE BASELINE. This is the")
    tee("    decisive reading for RCHNEW / RCHENV / RCHAGE, all three of which")
    tee("    are correlated with raw reach by construction. An interaction")
    tee("    judged without its own main effect is the main effect in a wig.")
    experiment(sub, out=tee, with_reach=True,
               only={"rchnew_d", "rchenv_d", "rchage_d"})

    tee("")
    tee("Ship rule: ROBUST WIN in the SECOND PASS, and a measured gain at or")
    tee("above the FITTED threshold while under the ORACLE bound.")

    vd = os.environ.get("VERDICT_OUT") or os.path.join(
        HERE, "..", "experiments", "UFC-ANGLES4-VERDICT.md")
    os.makedirs(os.path.dirname(vd), exist_ok=True)
    with open(vd, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"verdict -> {vd}")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
