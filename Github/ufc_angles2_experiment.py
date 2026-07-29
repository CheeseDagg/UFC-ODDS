#!/usr/bin/env python3
"""
ufc_angles2_experiment.py — WEAR AND TEAR, round two.

Chin (cumulative KO/TKO losses) shipped on 2026-07-29 as a robust win over both
Elo-only and Elo+age. That says damage accrual is real signal. This batch asks
whether chin is the BEST measure of accrued damage or just the crudest one:

  KDABS    cumulative knockdowns ABSORBED before the bout. Chin only counts
           fights a man LOST by KO. Getting dropped twice and winning a decision
           is invisible to chin but is the same trauma. Strictly finer-grained.
  MILEAGE  cumulative career seconds fought (in hours). Not trauma — odometer.
           Age says how old he is; mileage says how hard those years were.
  ABSORB   career significant strikes absorbed per minute, regressed toward the
           league mean. A durability/defence rate rather than a count.
  DIVCHG   weight-class movement vs his previous bout (+1 up, -1 down). Moving
           up means facing bigger men; moving down means a harder cut.

BASELINE INCLUDES AGE AND CHIN. That is the point. Last night win-streak
momentum beat Elo-only and died against Elo+age — it was a youth proxy wearing
a momentum costume. Any angle here that is secretly "he is old" or "he has been
knocked out" must clear the terms that already say so.

Model: p = sigmoid(a*elo_d/SCALE + c*chin_d + g*age_d + b*angle_d), mirror-
symmetric (difference features only, no intercept). Baseline coefficients tuned
on TRAIN (<=2022) by coordinate ascent; each angle's b grid-tuned on TRAIN with
the baseline held fixed; verdict on the 2023+ holdout split into 3 periods.
ROBUST WIN only = train win + holdout win + 3/3 periods.
"""
import csv, json, math, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
K, SCALE, INIT = 96.0, 450.0, 1500.0
SCORE_FROM = "2012-01-01"     # Elo burn-in: ratings are junk before this
TRAIN_END = "2022-12-31"
PERIODS = [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
           ("2025-01-01", "2026-12-31")]
LEAGUE_ABSORB = 4.0           # ~sig strikes absorbed per minute, UFC-wide
ABSORB_TAU = 20.0             # minutes of career before the rate is trusted

# Ordered light -> heavy. Anything unmapped (catchweight, open weight, women's
# divisions written oddly) yields no DIVCHG signal rather than a fake one.
DIV_RANK = {"strawweight": 0, "women's strawweight": 0, "flyweight": 1,
            "women's flyweight": 1, "bantamweight": 2, "women's bantamweight": 2,
            "featherweight": 3, "women's featherweight": 3, "lightweight": 4,
            "welterweight": 5, "middleweight": 6, "light heavyweight": 7,
            "heavyweight": 8}


def _f(x, d=0.0):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return d


def load_bouts(path):
    """Dedupe the fighter/opp mirror rows into one row per bout.

    The per-bout stats we keep are oriented to fighter A: kd_abs_a is what A
    absorbed, sig_l_opp_a is what landed ON A. B's mirror comes from A's own
    columns (what A landed is what B absorbed), so one row carries both sides.
    """
    rows = list(csv.DictReader(open(path)))
    seen, bouts = set(), []
    for r in rows:
        key = (r["date"],) + tuple(sorted([r["fighter"], r["opp"]]))
        if key in seen:
            continue
        seen.add(key)
        if r["won"] not in ("0", "1"):
            continue
        bouts.append({
            "date": r["date"], "a": r["fighter"], "b": r["opp"],
            "won_a": int(r["won"]),
            "ko_loss_a": int(_f(r.get("lost_by_ko"))),
            "ko_win_a": int(_f(r.get("won_by_ko"))),
            "secs": _f(r.get("secs")),
            "kd_abs_a": _f(r.get("kd_abs")),      # knockdowns A absorbed
            "kd_abs_b": _f(r.get("kd")),          # A's knockdowns = B absorbed
            "absorb_a": _f(r.get("sig_l_opp")),   # sig strikes landed on A
            "absorb_b": _f(r.get("sig_l")),       # A landed = B absorbed
            "div": (r.get("division") or "").strip().lower(),
        })
    bouts.sort(key=lambda x: x["date"])
    return bouts


def norm_name(name):
    """MUST mirror ufc_blend_predict.norm_name — the meta cache is keyed by it.
    A plain .lower() joins only 51% of fighters (periods, apostrophes and
    hyphens differ between the bout CSV and the ESPN meta pull), which silently
    zeroes the age term and would let a pure age proxy pass as a new angle."""
    n = (name or "").strip().lower()
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    return re.sub(r"\s+", " ", n)


def load_ages(path):
    """{normalized name: date-of-birth string}. Missing DOB yields age_d = 0
    for that bout, never a guessed age."""
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


def walk_features(bouts, ages=None):
    """One chronological pass. Every feature is captured BEFORE the bout is
    used to update any accumulator, so no row can see its own outcome."""
    ages = ages or {}
    elo = defaultdict(lambda: INIT)
    ko_losses = defaultdict(int)
    kd_absorbed = defaultdict(float)
    secs_fought = defaultdict(float)
    strikes_absorbed = defaultdict(float)
    last_div = {}
    out = []

    def absorb_rate(f):
        mins = secs_fought[f] / 60.0
        return ((strikes_absorbed[f] + LEAGUE_ABSORB * ABSORB_TAU)
                / (mins + ABSORB_TAU))

    def div_change(f, div):
        prev = last_div.get(f)
        if prev is None or prev not in DIV_RANK or div not in DIV_RANK:
            return 0.0
        return float(DIV_RANK[div] - DIV_RANK[prev])

    for bt in bouts:
        a, b, div = bt["a"], bt["b"], bt["div"]
        na, nb = norm_name(a), norm_name(b)
        age_d, age_known = 0.0, 0.0
        if na in ages and nb in ages:
            aa, ab = _age(ages[na], bt["date"]), _age(ages[nb], bt["date"])
            if aa is not None and ab is not None:
                age_d, age_known = aa - ab, 1.0
        f = {
            "elo_d": elo[a] - elo[b],
            "chin_d": float(ko_losses[a] - ko_losses[b]),
            "age_d": age_d,
            "age_known": age_known,
            "kdabs_d": kd_absorbed[a] - kd_absorbed[b],
            "mile_d": (secs_fought[a] - secs_fought[b]) / 3600.0,
            "absorb_d": absorb_rate(a) - absorb_rate(b),
            "divchg_d": div_change(a, div) - div_change(b, div),
        }
        out.append((bt, f))

        # ---- updates AFTER the feature snapshot ----
        ea = 1.0 / (1.0 + 10 ** (-(elo[a] - elo[b]) / SCALE))
        sa = bt["won_a"]
        elo[a] += K * (sa - ea)
        elo[b] += K * ((1 - sa) - (1 - ea))
        if bt["won_a"] and bt["ko_win_a"]:
            ko_losses[b] += 1
        if (not bt["won_a"]) and bt["ko_loss_a"]:
            ko_losses[a] += 1
        kd_absorbed[a] += bt["kd_abs_a"]
        kd_absorbed[b] += bt["kd_abs_b"]
        secs_fought[a] += bt["secs"]
        secs_fought[b] += bt["secs"]
        strikes_absorbed[a] += bt["absorb_a"]
        strikes_absorbed[b] += bt["absorb_b"]
        last_div[a] = div
        last_div[b] = div
    return out


def ll(feats, co, d0, d1, extra=None):
    """Mean log-likelihood over bouts in [d0,d1]. `co` holds the baseline
    coefficients; `extra` is an optional (key, b) angle term."""
    tot = n = 0
    ek, eb = extra if extra else (None, 0.0)
    for bt, f in feats:
        if not (d0 <= bt["date"] <= d1):
            continue
        z = (co["a"] * f["elo_d"] / SCALE
             + co["c"] * max(-6.0, min(6.0, f["chin_d"]))
             + co["g"] * max(-15.0, min(15.0, f["age_d"])))
        if ek:
            z += eb * max(-4.0, min(4.0, f[ek]))
        p = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
        p = min(max(p, 1e-9), 1 - 1e-9)
        y = bt["won_a"]
        tot += y * math.log(p) + (1 - y) * math.log(1 - p)
        n += 1
    return (tot / n if n else 0.0), n


def fit_baseline(feats, out=print):
    """Coordinate ascent on TRAIN over the three shipped terms."""
    co = {"a": 2.4, "c": -0.10, "g": -0.02}
    grids = {"a": (1.6, 2.0, 2.4, 2.8, 3.2),
             "c": (-0.30, -0.20, -0.12, -0.06, -0.03, 0.0),
             "g": (-0.06, -0.04, -0.02, -0.01, 0.0)}
    best = ll(feats, co, SCORE_FROM, TRAIN_END)[0]
    for _ in range(3):
        for k, grid in grids.items():
            for v in grid:
                trial = dict(co, **{k: v})
                s = ll(feats, trial, SCORE_FROM, TRAIN_END)[0]
                if s > best:
                    best, co = s, trial
    out(f"baseline (Elo + chin + age): a={co['a']} c={co['c']} g={co['g']}  "
        f"TRAIN LL {best:+.5f}")
    return co, best


ANGLES = [
    ("KDABS   knockdowns absorbed", "kdabs_d",
     (-0.30, -0.20, -0.12, -0.06, -0.03)),
    ("MILEAGE career hours fought", "mile_d",
     (-0.30, -0.18, -0.10, -0.05, 0.05, 0.10)),
    ("ABSORB  sig absorbed / min", "absorb_d",
     (-0.30, -0.18, -0.10, -0.05, 0.05)),
    ("DIVCHG  weight-class move", "divchg_d",
     (-0.30, -0.18, -0.10, -0.05, 0.05, 0.10, 0.18)),
]


def experiment(feats, out=print):
    co, base_tr = fit_baseline(feats, out=out)
    h0, h1 = PERIODS[0][0], PERIODS[-1][1]
    base_h, nh = ll(feats, co, h0, h1)
    out(f"baseline HOLDOUT {base_h:+.5f} (n={nh})")
    results = {}
    for label, key, grid in ANGLES:
        bt_ = (-9e9, 0.0)
        for b in grid:
            s, _ = ll(feats, co, SCORE_FROM, TRAIN_END, extra=(key, b))
            if s > bt_[0]:
                bt_ = (s, b)
        tr, B = bt_
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
        out(f"{label:28s} b={B:>6}  train_win={str(train_win):5s}  "
            f"holdout dLL {hv - base_h:+.5f}  periods {wins}/3  -> {verdict}")
    return results


# ------------------------------------------------------------------ selftest
def _synth(plant_mileage=True):
    """Fighters really DO decay with mileage here. Elo cannot fully track it
    because decay is continuous while Elo only moves on results, which is
    exactly the situation the real angle claims to exploit."""
    import random
    rng = random.Random(11)
    skill = {i: rng.gauss(0, 1) for i in range(300)}
    secs = defaultdict(float)
    bouts, d = [], 0
    while len(bouts) < 6000:
        a, b = rng.randrange(300), rng.randrange(300)
        if a == b:
            continue
        d += 1
        date = f"20{10 + d // 500:02d}-{(d // 40) % 12 + 1:02d}-{d % 28 + 1:02d}"
        pen = 0.45 if plant_mileage else 0.0
        za = skill[a] - pen * (secs[a] / 3600.0)
        zb = skill[b] - pen * (secs[b] / 3600.0)
        won_a = 1 if rng.random() < 1 / (1 + math.exp(-(za - zb))) else 0
        dur = rng.choice([300.0, 600.0, 900.0])
        ko = rng.random() < 0.30
        bouts.append({"date": date, "a": f"F{a}", "b": f"F{b}", "won_a": won_a,
                      "ko_loss_a": 1 if (not won_a and ko) else 0,
                      "ko_win_a": 1 if (won_a and ko) else 0,
                      "secs": dur,
                      "kd_abs_a": float(rng.random() < 0.12),
                      "kd_abs_b": float(rng.random() < 0.12),
                      "absorb_a": dur / 60.0 * 4.0, "absorb_b": dur / 60.0 * 4.0,
                      "div": "lightweight"})
        secs[f"F{a}"] = secs[a] = secs[a] + dur
        secs[f"F{b}"] = secs[b] = secs[b] + dur
    bouts.sort(key=lambda x: x["date"])
    return bouts


def selftest():
    global SCORE_FROM, TRAIN_END, PERIODS
    SCORE_FROM, TRAIN_END = "2013-01-01", "2018-12-31"
    PERIODS = [("2019-01-01", "2019-12-31"), ("2020-01-01", "2020-12-31"),
               ("2021-01-01", "2026-12-31")]
    MK = "MILEAGE career hours fought"

    buf = []
    live = _synth(plant_mileage=True)
    res = experiment(walk_features(live), out=buf.append)
    d_mile = res[MK][0]
    assert d_mile > 0.002, ("planted mileage NOT recovered: "
                            f"{d_mile}\n" + "\n".join(buf))

    # null control: same generator, decay switched off -> mileage must go quiet
    res0 = experiment(walk_features(_synth(plant_mileage=False)),
                      out=lambda s: None)
    assert res0[MK][0] < d_mile / 3, f"null suspicious: {res0[MK][0]} vs {d_mile}"

    # leak proof: flip every outcome after a cutoff on a DEEP COPY; features
    # dated before the cutoff must be byte-identical or something reads ahead.
    feats = walk_features(live)
    f1 = [(bt["date"], f) for bt, f in feats if bt["date"] <= "2016-01-01"]
    poison = [dict(bt) for bt in live]
    for bt in poison:
        if bt["date"] > "2016-01-01":
            bt["won_a"] = 1 - bt["won_a"]
    f2 = [(bt["date"], f) for bt, f in walk_features(poison)
          if bt["date"] <= "2016-01-01"]
    assert json.dumps(f1, sort_keys=True) == json.dumps(f2, sort_keys=True), "LEAK"

    print(f"UFC ANGLES-2 SELFTEST PASS — planted mileage recovered "
          f"(dLL {d_mile:+.4f}), null clean ({res0[MK][0]:+.4f}), leak-free")
    return 0


def main():
    bouts = load_bouts(os.path.join(HERE, "data", "fighter_bouts.csv"))
    ages = load_ages(os.path.join(HERE, "fighter_meta_cache.json"))
    known = sum(1 for bt in bouts
                if norm_name(bt["a"]) in ages and norm_name(bt["b"]) in ages)
    if known < 0.5 * len(bouts):
        print(f"::warning::age join weak ({known}/{len(bouts)}) — the baseline "
              "is not properly age-adjusted; treat wins as unproven")
    feats = walk_features(bouts, ages)
    lines = []

    def tee(s):
        print(s)
        lines.append(s)

    tee("=" * 72)
    tee("UFC ANGLES 2 — wear and tear beyond chin")
    tee("baseline already contains Elo + CHIN + AGE (both shipped/validated)")
    tee("=" * 72)
    tee(f"unique bouts: {len(bouts)} ({bouts[0]['date']}..{bouts[-1]['date']})"
        f"  both-DOB known: {known} ({100 * known / len(bouts):.0f}%)")
    tee("")
    tee("--- FULL SAMPLE (age term diluted: it is 0 wherever a DOB is missing)")
    experiment(feats, out=tee)

    # The decisive pass. On the full sample the age term is switched off for
    # more than half the bouts, so an age proxy can still slip through on the
    # rest. Here every bout carries a real age difference, so anything that
    # survives is carrying information age does not.
    sub = [(bt, f) for bt, f in feats if f["age_known"]]
    tee("")
    tee(f"--- AGE-COMPLETE SUBSET (n={len(sub)}) — the decisive test")
    sub_res = experiment(sub, out=tee)
    tee("")
    tee("Ship rule: ROBUST WIN on the AGE-COMPLETE subset. An angle that wins")
    tee("only on the full sample is most likely re-discovering age.")
    # VERDICT_OUT lets a re-run (e.g. after the DOB backfill widens the age
    # control) write beside the original instead of clobbering it — the two
    # verdicts are only interesting side by side.
    vd = os.environ.get("VERDICT_OUT") or os.path.join(
        HERE, "..", "experiments", "UFC-ANGLES2-VERDICT.md")
    os.makedirs(os.path.dirname(vd), exist_ok=True)
    with open(vd, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"verdict -> {vd}")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
