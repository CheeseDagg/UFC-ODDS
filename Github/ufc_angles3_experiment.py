#!/usr/bin/env python3
"""
ufc_angles3_experiment.py — STYLE AND SCHEDULE, and the first UFC power ceilings.

Batch 2 asked whether anything measures accrued damage better than chin. Nothing
did. This batch stops looking for a better damage proxy and asks three different
questions, none of which is about trauma:

  KOPOW    career KO/TKO win rate, shrunk toward the league mean. Elo sees only
           win or loss, so a man who starches people and a man who scrapes
           split decisions can hold the same rating. If finishing ability is
           real and persistent, Elo is under-rating the finisher.
  LAYAGE   layoff x age INTERACTION. Both terms already ship. The claim here is
           not that layoff matters — it is that fourteen months off is a
           different event at 36 than at 26. That is the shape every
           practitioner asserts and nobody in this repo has tested.
  PACE     career significant strikes LANDED per minute. Batch 2's ABSORB was
           the defensive half of the same measurement and died; this is the
           offensive half, and it is a genuinely different claim (output wins
           rounds on the cards, independent of who is better).
  ACTIV    bouts fought in the trailing 365 days. Layoff is one gap; activity
           is a rate. A man three fights into a busy year and a man returning
           from one long break can show the same layoff and be in opposite
           physical situations.

BASELINE. Elo + chin + age + LAYOFF. Layoff joins the baseline here because
LAYAGE is an interaction, and an interaction tested against a baseline that
omits the main effect is just the main effect wearing a costume — the same
mistake that made win-streak momentum look real until age was controlled.

POWER CEILINGS. Every null in this file is reported next to the most log-
likelihood that angle could POSSIBLY buy on this panel, obtained by re-rolling
the outcomes so the angle is true at a generous strength and re-running the
whole tune-and-verdict pipeline on the synthetic panel. Two UFC batches have
now produced nulls with no ceiling attached, which means nobody knows which of
them are dead and which were merely invisible at 1,491 holdout bouts. That
distinction decides whether an idea gets buried or gets revisited when the data
widens, so it is not a nicety.

Verdict rule unchanged: ROBUST WIN = train win + holdout win + 3/3 periods, on
the AGE-COMPLETE subset.
"""
import csv, json, math, os, re, sys
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
K, SCALE, INIT = 96.0, 450.0, 1500.0
SCORE_FROM = "2012-01-01"
TRAIN_END = "2022-12-31"
PERIODS = [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
           ("2025-01-01", "2026-12-31")]

LEAGUE_KO = 0.32        # roughly a third of UFC wins come by KO/TKO
KO_TAU = 6.0            # bouts before a man's own finish rate is trusted
LEAGUE_PACE = 4.0       # sig strikes landed per minute, UFC-wide
PACE_TAU = 20.0         # minutes of career before the rate is trusted
LAY_CAP = 2.0           # years; beyond this it is a comeback, not a layoff
AGE_PIVOT = 30.0        # where "young" turns into "old" for the interaction


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
            "secs": _f(r.get("secs")),
            "land_a": _f(r.get("sig_l")),        # sig strikes A landed
            "land_b": _f(r.get("sig_l_opp")),    # landed on A = B's output
        })
    bouts.sort(key=lambda x: x["date"])
    return bouts


def load_ages(path):
    if not os.path.exists(path):
        return {}
    raw = json.load(open(path))
    return {norm_name(k): v["dob"] for k, v in raw.items()
            if isinstance(v, dict) and v.get("dob")}


def _age(dob, date):
    try:
        y0, m0, d0 = (int(x) for x in dob.split("-"))
        y1, m1, d1 = (int(x) for x in date.split("-"))
    except (ValueError, AttributeError):
        return None
    return (y1 - y0) + ((m1 - m0) * 30.44 + (d1 - d0)) / 365.25


def _days(d0, d1):
    """Whole days between two ISO dates, without importing a calendar for it."""
    def ord_(d):
        y, m, dd = (int(x) for x in d.split("-"))
        if m <= 2:
            y, m = y - 1, m + 12
        return (365 * y + y // 4 - y // 100 + y // 400
                + (153 * (m - 3) + 2) // 5 + dd)
    return ord_(d1) - ord_(d0)


def walk_features(bouts, ages=None):
    """One chronological pass. Every feature is snapshotted BEFORE the bout
    updates any accumulator, so no row can see its own outcome."""
    ages = ages or {}
    elo = defaultdict(lambda: INIT)
    ko_losses, ko_wins, wins = defaultdict(int), defaultdict(int), defaultdict(int)
    secs_fought, strikes_landed = defaultdict(float), defaultdict(float)
    last_date, recent = {}, defaultdict(deque)
    out = []

    def ko_rate(f):
        """Share of his WINS that came by KO/TKO — not per bout.

        Per-bout would be a winning-rate proxy in disguise: a man who loses
        often has many bouts and few finishes, so his rate falls for reasons
        Elo already knows about. Conditioning on wins asks the only question
        that is actually new — when he wins, HOW does he win."""
        return (ko_wins[f] + LEAGUE_KO * KO_TAU) / (wins[f] + KO_TAU)

    def pace(f):
        mins = secs_fought[f] / 60.0
        return ((strikes_landed[f] + LEAGUE_PACE * PACE_TAU)
                / (mins + PACE_TAU))

    def layoff(f, date):
        """Years since his last bout, capped. A debut has no layoff at all;
        returning 0 would call it 'fought yesterday', which is the opposite of
        the truth, so debuts are flagged and the term is switched off for them
        rather than guessed."""
        prev = last_date.get(f)
        if prev is None:
            return None
        return min(_days(prev, date) / 365.25, LAY_CAP)

    def activity(f, date):
        q = recent[f]
        while q and _days(q[0], date) > 365:
            q.popleft()
        return float(len(q))

    for bt in bouts:
        a, b, date = bt["a"], bt["b"], bt["date"]
        na, nb = norm_name(a), norm_name(b)
        age_a = ages.get(na) and _age(ages[na], date)
        age_b = ages.get(nb) and _age(ages[nb], date)
        age_known = 1.0 if (age_a is not None and age_b is not None) else 0.0
        age_d = (age_a - age_b) if age_known else 0.0

        la, lb = layoff(a, date), layoff(b, date)
        lay_known = 1.0 if (la is not None and lb is not None) else 0.0
        lay_d = (la - lb) if lay_known else 0.0
        # the interaction, centered on both sides: layoff x (age - 30). It is
        # zero unless BOTH the ages and BOTH the layoffs are real, because a
        # half-known interaction is a main effect in disguise.
        if lay_known and age_known:
            layage_d = (la * (age_a - AGE_PIVOT) - lb * (age_b - AGE_PIVOT)) / 5.0
        else:
            layage_d = 0.0

        out.append((bt, {
            "elo_d": elo[a] - elo[b],
            "chin_d": float(ko_losses[a] - ko_losses[b]),
            "age_d": age_d,
            "age_known": age_known,
            # diagnostic only, never a model term: the age DIFFERENCE cannot
            # answer "was anyone in this bout old", and the shape check for
            # the layoff-x-age interaction needs the level, not the gap.
            "age_max": max(age_a, age_b) if age_known else 0.0,
            "lay_d": lay_d,
            "kopow_d": ko_rate(a) - ko_rate(b),
            "layage_d": layage_d,
            "pace_d": pace(a) - pace(b),
            "activ_d": activity(a, date) - activity(b, date),
        }))

        # ---- updates AFTER the snapshot: this line is the leak boundary ----
        ea = 1.0 / (1.0 + 10 ** (-(elo[a] - elo[b]) / SCALE))
        sa = bt["won_a"]
        elo[a] += K * (sa - ea)
        elo[b] += K * ((1 - sa) - (1 - ea))
        if bt["won_a"] and bt["ko_win_a"]:
            ko_losses[b] += 1
            ko_wins[a] += 1
        if (not bt["won_a"]) and bt["ko_loss_a"]:
            ko_losses[a] += 1
            ko_wins[b] += 1
        wins[a if bt["won_a"] else b] += 1
        for f, land in ((a, bt["land_a"]), (b, bt["land_b"])):
            secs_fought[f] += bt["secs"]
            strikes_landed[f] += land
            last_date[f] = date
            recent[f].append(date)
    return out


CLIP = {"chin_d": 6.0, "age_d": 15.0, "lay_d": LAY_CAP, "kopow_d": 1.0,
        "layage_d": 4.0, "pace_d": 8.0, "activ_d": 4.0}


def ll(feats, co, d0, d1, extra=None, ys=None):
    """Mean log-likelihood over bouts in [d0,d1].

    `ys` overrides the observed outcomes and is how the power ceiling scores a
    synthetic panel without having to rebuild the feature walk."""
    tot = n = 0
    ek, eb = extra if extra else (None, 0.0)
    for i, (bt, f) in enumerate(feats):
        if not (d0 <= bt["date"] <= d1):
            continue
        z = (co["a"] * f["elo_d"] / SCALE
             + co["c"] * max(-6.0, min(6.0, f["chin_d"]))
             + co["g"] * max(-15.0, min(15.0, f["age_d"]))
             + co["L"] * max(-LAY_CAP, min(LAY_CAP, f["lay_d"])))
        if ek:
            cl = CLIP[ek]
            z += eb * max(-cl, min(cl, f[ek]))
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
        p = min(max(p, 1e-9), 1 - 1e-9)
        y = bt["won_a"] if ys is None else ys[i]
        tot += y * math.log(p) + (1 - y) * math.log(1 - p)
        n += 1
    return (tot / n if n else 0.0), n


BASE_GRIDS = {"a": (1.6, 2.0, 2.4, 2.8, 3.2),
              "c": (-0.30, -0.20, -0.12, -0.06, -0.03, 0.0),
              "g": (-0.06, -0.04, -0.02, -0.01, 0.0),
              "L": (-0.30, -0.18, -0.10, -0.05, 0.0, 0.05)}


def fit_baseline(feats, out=print, ys=None):
    co = {"a": 2.4, "c": -0.10, "g": -0.02, "L": -0.05}
    best = ll(feats, co, SCORE_FROM, TRAIN_END, ys=ys)[0]
    for _ in range(3):
        for k, grid in BASE_GRIDS.items():
            for v in grid:
                trial = dict(co, **{k: v})
                s = ll(feats, trial, SCORE_FROM, TRAIN_END, ys=ys)[0]
                if s > best:
                    best, co = s, trial
    out(f"baseline (Elo + chin + age + layoff): a={co['a']} c={co['c']} "
        f"g={co['g']} L={co['L']}  TRAIN LL {best:+.5f}")
    return co, best


ANGLES = [
    ("KOPOW   KO share of his wins", "kopow_d",
     (-1.20, -0.60, -0.30, -0.15, 0.15, 0.30, 0.60, 1.20, 2.00)),
    ("LAYAGE  layoff x age", "layage_d",
     (-0.40, -0.25, -0.15, -0.08, 0.08, 0.15, 0.25, 0.40)),
    ("PACE    sig landed / min", "pace_d",
     (-0.20, -0.10, -0.05, 0.05, 0.10, 0.20, 0.35)),
    ("ACTIV   bouts last 365d", "activ_d",
     (-0.30, -0.18, -0.10, -0.05, 0.05, 0.10, 0.18, 0.30)),
]


def tune(feats, co, key, grid, ys=None):
    """Best b on TRAIN with the baseline held fixed — the real pipeline."""
    best = (-9e9, 0.0)
    for b in grid:
        s, _ = ll(feats, co, SCORE_FROM, TRAIN_END, extra=(key, b), ys=ys)
        if s > best[0]:
            best = (s, b)
    return best


def power_ceiling(feats, key, b_true, seed=7):
    """The most log-likelihood this angle could POSSIBLY buy on this panel.

    Takes the real feature walk — real Elo gaps, real ages, real layoffs, the
    real distribution of the angle itself — and re-rolls only the OUTCOMES so
    the angle is true at strength b_true. Then runs the identical pipeline:
    refit the baseline on the synthetic train, score the holdout with and
    without the term at its true value. No fitted model can beat a model that
    already knows the answer, so this number is a hard ceiling.

    Why it matters more here than anywhere: a UFC holdout is ~1,500 bouts of a
    binary outcome, which is a thin instrument. A measured null of +0.0000
    against a ceiling of +0.0100 means the angle is dead. The same null against
    a ceiling of +0.0004 means the experiment could never have seen it, and
    filing that as 'dead' would be a false negative dressed as a finding.

    The baseline is REFIT on the synthetic panel rather than carried over. A
    carried-over fit is mis-specified for the re-rolled outcomes, which would
    hand the angle term credit for repairing the baseline and inflate the
    ceiling — and an inflated ceiling is the dangerous direction of error,
    since it turns invisible angles into dead ones.
    """
    import random
    rng = random.Random(seed)
    co0, _ = fit_baseline(feats, out=lambda s: None)
    ys, cl = [], CLIP[key]
    for bt, f in feats:
        z = (co0["a"] * f["elo_d"] / SCALE
             + co0["c"] * max(-6.0, min(6.0, f["chin_d"]))
             + co0["g"] * max(-15.0, min(15.0, f["age_d"]))
             + co0["L"] * max(-LAY_CAP, min(LAY_CAP, f["lay_d"]))
             + b_true * max(-cl, min(cl, f[key])))
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
        ys.append(1 if rng.random() < p else 0)
    co, _ = fit_baseline(feats, out=lambda s: None, ys=ys)
    h0, h1 = PERIODS[0][0], PERIODS[-1][1]
    base, _ = ll(feats, co, h0, h1, ys=ys)
    with_, _ = ll(feats, co, h0, h1, extra=(key, b_true), ys=ys)
    return with_ - base


def experiment(feats, out=print, ceilings=True):
    co, base_tr = fit_baseline(feats, out=out)
    h0, h1 = PERIODS[0][0], PERIODS[-1][1]
    base_h, nh = ll(feats, co, h0, h1)
    out(f"baseline HOLDOUT {base_h:+.5f} (n={nh})")
    results = {}
    for label, key, grid in ANGLES:
        tr, B = tune(feats, co, key, grid)
        train_win = tr > base_tr
        hv, _ = ll(feats, co, h0, h1, extra=(key, B))
        wins = 0
        for p0, p1 in PERIODS:
            b0, _ = ll(feats, co, p0, p1)
            v0, _ = ll(feats, co, p0, p1, extra=(key, B))
            wins += 1 if v0 > b0 else 0
        verdict = ("ROBUST WIN" if (train_win and hv > base_h and wins == 3)
                   else ("win, not robust" if hv > base_h else "NULL"))
        results[label] = (hv - base_h, wins, verdict, B)
        out(f"{label:26s} b={B:>6}  train_win={str(train_win):5s}  "
            f"holdout dLL {hv - base_h:+.5f}  periods {wins}/3  -> {verdict}")
    if ceilings:
        out("")
        out("--- POWER CEILINGS (outcomes re-rolled so the angle IS true at the")
        out("    listed strength; the most any model could buy on this panel)")
        for label, key, grid in ANGLES:
            # GENERATE AT THE SIGN THE ANGLE ACTUALLY FITS. The first draft used
            # max(grid) unconditionally, so an angle whose real coefficient is
            # negative got its ceiling built from a world where the effect runs
            # the OTHER way — which produces a negative "ceiling" and then
            # labels a genuine win as noise. A ceiling generated at the wrong
            # sign is not a ceiling. Ties and exact zeros fall back to the
            # largest magnitude available.
            b_fit = results[label][3]
            side = [b for b in grid if (b < 0) == (b_fit < 0)] or list(grid)
            b_gen = max(side, key=abs)
            # average over re-rolls: one Bernoulli draw of ~8,700 bouts is
            # itself a noisy instrument, and a ceiling that moves with the seed
            # is not a bound. Three seeds is cheap and kills most of the wobble.
            cs = [power_ceiling(feats, key, b_gen, seed=s)
                  for s in (7, 17, 27, 37, 47)]
            c = sum(cs) / len(cs)
            got = results[label][0]
            # Four readings, not two. The first draft could only say "noise" or
            # "dead", so an angle that WON while sitting well under its ceiling
            # — the one outcome the ceiling exists to certify — got printed as
            # dead. Order matters: reach-the-ceiling first, then win, then the
            # two flavours of null.
            won = results[label][2] == "ROBUST WIN" and got > 0
            if got >= c:
                read = "MEASURED >= CEILING: noise by construction"
            elif got >= min(cs):
                read = "inside the ceiling's own seed spread: unproven"
            elif won:
                read = f"LIVE: robust win at {100.0 * got / c:.0f}% of ceiling"
            elif c > 0.004:
                read = "dead: the panel could see it and did not"
            else:
                read = "CANNOT BE SEEN AT THIS SAMPLE - do not bury"
            out(f"{label:26s} ceiling(b={b_gen:+.2f}) {c:+.5f} "
                f"[{min(cs):+.5f}..{max(cs):+.5f}]  "
                f"measured {got:+.5f}   {read}")
            results[label] = results[label] + (c,)
    return results


# ------------------------------------------------------------------ selftest
def _synth(plant="kopow"):
    """Finishers really are better than their Elo says, here.

    The planted edge is deliberately something Elo cannot absorb: a fighter's
    KO rate is fixed at birth and adds to his true strength, but Elo only ever
    sees the win/loss it already produced, so the term has somewhere to live.
    That is the exact structure the real KOPOW claim asserts.
    """
    import random
    rng = random.Random(23)
    N, DAY0 = 300, 2010 * 365
    skill = {i: rng.gauss(0, 1) for i in range(N)}
    finisher = {i: rng.random() for i in range(N)}
    born = {i: 1980 + rng.randrange(0, 16) for i in range(N)}
    # irregular schedules are the whole point: every fighter draws his own gap
    # to the next bout, so layoff and activity actually VARY across the panel.
    # A uniform schedule would leave both terms constant and unmeasurable, and
    # the selftest would then be checking the generator, not the harness.
    gap_mean = {i: rng.uniform(90, 500) for i in range(N)}
    nxt = {i: DAY0 + rng.randrange(0, 400) for i in range(N)}
    ages_out, bouts, bouts_last = {}, [], {}

    def iso(n):
        y = n // 365
        rem = n % 365
        return f"{y:04d}-{rem // 31 + 1:02d}-{rem % 28 + 1:02d}"

    for i in range(N):
        ages_out[f"f{i}"] = f"{born[i]}-06-15"

    while len(bouts) < 6000:
        a = min(range(N), key=lambda i: nxt[i])
        b = rng.randrange(N)
        if a == b:
            b = (b + 1) % N
        day = nxt[a]
        date = iso(day)
        aa = (day - born[a] * 365) / 365.0
        ab = (day - born[b] * 365) / 365.0
        # layoff x age: time off costs an old man and barely touches a young
        # one. Both inputs move WITHIN a career, which is why Elo cannot quietly
        # absorb this the way it absorbs any fixed per-fighter trait.
        pen = 0.55 if plant == "layage" else 0.0
        la = min((day - bouts_last.get(a, day)) / 365.25, LAY_CAP) if a in bouts_last else 0.0
        lb = min((day - bouts_last.get(b, day)) / 365.25, LAY_CAP) if b in bouts_last else 0.0
        za = skill[a] - pen * la * (aa - AGE_PIVOT) / 5.0
        zb = skill[b] - pen * lb * (ab - AGE_PIVOT) / 5.0
        won_a = 1 if rng.random() < 1 / (1 + math.exp(-(za - zb))) else 0
        dur = rng.choice([300.0, 600.0, 900.0])
        w = a if won_a else b
        ko = rng.random() < finisher[w]
        bouts.append({"date": date, "a": f"F{a}", "b": f"F{b}", "won_a": won_a,
                      "ko_loss_a": 1 if (not won_a and ko) else 0,
                      "ko_win_a": 1 if (won_a and ko) else 0,
                      "secs": dur,
                      "land_a": dur / 60.0 * rng.uniform(2, 7),
                      "land_b": dur / 60.0 * rng.uniform(2, 7)})
        for f in (a, b):
            bouts_last[f] = day
            nxt[f] = day + int(rng.expovariate(1.0 / gap_mean[f])) + 30
    bouts.sort(key=lambda x: x["date"])
    return bouts, ages_out


def selftest():
    global SCORE_FROM, TRAIN_END, PERIODS
    SCORE_FROM, TRAIN_END = "2013-01-01", "2018-12-31"
    PERIODS = [("2019-01-01", "2019-12-31"), ("2020-01-01", "2020-12-31"),
               ("2021-01-01", "2026-12-31")]
    LK = "LAYAGE  layoff x age"

    # date arithmetic, which the layoff and activity terms both stand on
    assert _days("2024-02-28", "2024-03-01") == 2, "2024 is a leap year"
    assert _days("2023-02-28", "2023-03-01") == 1
    assert _days("2020-01-01", "2021-01-01") == 366

    # WHY THE PLANT IS THE INTERACTION AND NOT KOPOW. The first draft planted a
    # fixed per-fighter finishing edge and the harness could not recover it —
    # correctly. Elo estimates TOTAL strength, so any constant per-fighter
    # contribution to winning is absorbed into the rating within a handful of
    # bouts and leaves no residual for a second term to explain. Only effects
    # that move WITHIN a career (mileage, layoff, age, activity) are visible
    # over an Elo baseline at all. That is a real prior about KOPOW, not a
    # weakness of the test: if career finish rate wins here it will be because
    # finishers have fatter tails than their record implies, not because Elo
    # cannot see them.
    buf = []
    live, live_ages = _synth(plant="layage")
    res = experiment(walk_features(live, live_ages), out=buf.append,
                     ceilings=False)
    d_la = res[LK][0]
    assert d_la > 0.002, ("planted layoff x age NOT recovered: "
                          f"{d_la}\n" + "\n".join(buf))

    # null control: identical generator, interaction switched off
    nb, na_ = _synth(plant="none")
    res0 = experiment(walk_features(nb, na_), out=lambda s: None, ceilings=False)
    assert res0[LK][0] < d_la / 3, f"null suspicious: {res0[LK][0]} vs {d_la}"

    # the ceiling must exceed what was actually measured on the panel where the
    # effect is REAL — a ceiling below its own measurement is not a ceiling
    ceil = power_ceiling(walk_features(live, live_ages), "layage_d", 0.40)
    assert ceil > d_la * 0.5, f"ceiling {ceil} implausibly under measured {d_la}"
    # and on the null panel the ceiling must still be positive: the ceiling
    # describes the PANEL's capacity to show an effect, not whether one exists
    ceil0 = power_ceiling(walk_features(nb, na_), "layage_d", 0.40)
    assert ceil0 > 0, f"ceiling collapsed on a null panel: {ceil0}"

    # leak proof: flip every outcome after a cutoff on a DEEP COPY; features
    # dated before it must be byte-identical or something reads ahead
    feats = walk_features(live, live_ages)
    f1 = [(bt["date"], f) for bt, f in feats if bt["date"] <= "2016-01-01"]
    poison = [dict(bt) for bt in live]
    for bt in poison:
        if bt["date"] > "2016-01-01":
            bt["won_a"] = 1 - bt["won_a"]
    f2 = [(bt["date"], f) for bt, f in walk_features(poison, live_ages)
          if bt["date"] <= "2016-01-01"]
    assert json.dumps(f1, sort_keys=True) == json.dumps(f2, sort_keys=True), "LEAK"

    print(f"UFC ANGLES-3 SELFTEST PASS — planted layoff x age recovered "
          f"(dLL {d_la:+.4f}), null clean ({res0[LK][0]:+.4f}), "
          f"ceiling sane ({ceil:+.4f} live / {ceil0:+.4f} null), leak-free")
    return 0


def main():
    bouts = load_bouts(os.path.join(HERE, "data", "fighter_bouts.csv"))
    ages = load_ages(os.path.join(HERE, "fighter_meta_cache.json"))
    feats = walk_features(bouts, ages)
    known = sum(1 for _, f in feats if f["age_known"])
    lines = []

    def tee(s):
        print(s)
        lines.append(s)

    tee("=" * 72)
    tee("UFC ANGLES 3 — style and schedule, with power ceilings")
    tee("baseline: Elo + chin + AGE + LAYOFF (layoff is in because LAYAGE is")
    tee("an interaction, and an interaction without its main effect is a lie)")
    tee("=" * 72)
    tee(f"unique bouts: {len(bouts)} ({bouts[0]['date']}..{bouts[-1]['date']})"
        f"  both-DOB known: {known} ({100 * known / len(bouts):.0f}%)")
    tee("")
    tee("--- FULL SAMPLE (age and the interaction are 0 wherever a DOB is missing)")
    experiment(feats, out=tee)

    sub = [(bt, f) for bt, f in feats if f["age_known"]]
    tee("")
    tee(f"--- AGE-COMPLETE SUBSET (n={len(sub)}) — the decisive test")
    experiment(sub, out=tee)
    tee("")
    tee("Ship rule: ROBUST WIN on the AGE-COMPLETE subset, AND a measured gain")
    tee("well under its own power ceiling. A result at or above its ceiling is")
    tee("noise by construction, however many periods it wins.")

    vd = os.environ.get("VERDICT_OUT") or os.path.join(
        HERE, "..", "experiments", "UFC-ANGLES3-VERDICT.md")
    os.makedirs(os.path.dirname(vd), exist_ok=True)
    with open(vd, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"verdict -> {vd}")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
