#!/usr/bin/env python3
"""
ufc_angles_experiment.py — two untested UFC angles vs a walk-forward Elo base:
  CHIN  cumulative KO/TKO losses before the bout (damage accrual — does a
        beat-up chin predict losing beyond what Elo already knows?)
  STREAK current win/loss streak length (momentum beyond rating).
Data: committed fighter_bouts.csv (each bout twice, fighter/opp mirror).
Model: p = sigmoid(a*elo_term + b*angle_diff), mirror-symmetric (no intercept,
difference features only). a tuned for the baseline on TRAIN (<=2022); each
angle's b grid-tuned on TRAIN; verdict = 2023+ holdout LL, 3 periods, ROBUST
WIN only. Selftest: planted chin effect recovered on synthetic, null clean,
future-poisoning leaves prior features byte-identical.
"""
import csv, json, math, os, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
K, SCALE, INIT = 96.0, 450.0, 1500.0
SCORE_FROM = "2012-01-01"   # Elo burn-in
TRAIN_END = "2022-12-31"
PERIODS = [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
           ("2025-01-01", "2026-12-31")]

def load_bouts(path):
    rows = list(csv.DictReader(open(path)))
    seen, bouts = set(), []
    for r in rows:
        key = (r["date"],) + tuple(sorted([r["fighter"], r["opp"]]))
        if key in seen:
            continue
        seen.add(key)
        if r["won"] not in ("0", "1"):
            continue
        bouts.append({"date": r["date"], "a": r["fighter"], "b": r["opp"],
                      "won_a": int(r["won"]),
                      "ko_loss_a": int(r.get("lost_by_ko", 0) or 0),
                      "ko_win_a": int(r.get("won_by_ko", 0) or 0)})
    bouts.sort(key=lambda x: x["date"])
    return bouts

def walk_features(bouts):
    """Chronological; features strictly from PRIOR bouts."""
    elo = defaultdict(lambda: INIT)
    ko_losses = defaultdict(int)
    streak = defaultdict(int)      # +n win streak, -n loss streak
    out = []
    for bt in bouts:
        a, b = bt["a"], bt["b"]
        f = {"elo_d": elo[a] - elo[b],
             "chin_d": ko_losses[a] - ko_losses[b],
             "stk_d": streak[a] - streak[b]}
        out.append((bt, f))
        ea = 1.0 / (1.0 + 10 ** (-(elo[a] - elo[b]) / SCALE))
        sa = bt["won_a"]
        elo[a] += K * (sa - ea); elo[b] += K * ((1 - sa) - (1 - ea))
        if bt["won_a"]:
            streak[a] = max(1, streak[a] + 1); streak[b] = min(-1, streak[b] - 1)
        else:
            streak[b] = max(1, streak[b] + 1); streak[a] = min(-1, streak[a] - 1)
        if bt["won_a"] and bt.get("ko_win_a"):
            ko_losses[b] += 1
        if (not bt["won_a"]) and bt.get("ko_loss_a"):
            ko_losses[a] += 1
    return out

def ll(feats, a_coef, b_coef, key, d0, d1):
    tot = n = 0
    for bt, f in feats:
        if not (d0 <= bt["date"] <= d1):
            continue
        z = a_coef * f["elo_d"] / SCALE
        if b_coef:
            z += b_coef * max(-4, min(4, f[key]))
        p = 1.0 / (1.0 + math.exp(-z))
        p = min(max(p, 1e-9), 1 - 1e-9)
        y = bt["won_a"]
        tot += y * math.log(p) + (1 - y) * math.log(1 - p)
        n += 1
    return (tot / n if n else 0.0), n

def experiment(feats, out=print):
    best = (-9e9, None)
    for a in (1.6, 2.0, 2.4, 2.8, 3.2):
        s, _ = ll(feats, a, 0, "", SCORE_FROM, TRAIN_END)
        if s > best[0]:
            best = (s, a)
    base_tr, A = best
    h0, h1 = PERIODS[0][0], PERIODS[-1][1]
    base_h, nh = ll(feats, A, 0, "", h0, h1)
    out(f"baseline Elo-only: a={A}  TRAIN LL {base_tr:+.5f}  "
        f"HOLDOUT {base_h:+.5f} (n={nh})")
    results = {}
    for name, key, grid in [("CHIN (KO-losses diff)", "chin_d",
                             (-0.30, -0.20, -0.12, -0.06, -0.03)),
                            ("STREAK (momentum diff)", "stk_d",
                             (0.01, 0.03, 0.06, 0.10, 0.15))]:
        bt_ = (-9e9, None)
        for b in grid:
            s, _ = ll(feats, A, b, key, SCORE_FROM, TRAIN_END)
            if s > bt_[0]:
                bt_ = (s, b)
        tr, B = bt_
        train_win = tr > base_tr
        hv, _ = ll(feats, A, B, key, h0, h1)
        wins = 0
        for p0, p1 in PERIODS:
            b0, _ = ll(feats, A, 0, "", p0, p1)
            v0, _ = ll(feats, A, B, key, p0, p1)
            wins += 1 if v0 > b0 else 0
        verdict = ("ROBUST WIN" if (train_win and hv > base_h and wins == 3)
                   else ("win, not robust" if hv > base_h else "NULL"))
        results[name] = (hv - base_h, wins, verdict, B)
        out(f"{name:24s} b={B}  train_win={train_win}  "
            f"holdout dLL {hv-base_h:+.5f}  periods {wins}/3  -> {verdict}")
    return results

def selftest():
    import random
    rng = random.Random(5)
    # synthetic: 300 fighters, true skill; chin: each KO loss REALLY degrades
    skill = {i: rng.gauss(0, 1) for i in range(300)}
    ko_true = defaultdict(int)
    bouts = []
    d = 0
    for _ in range(6000):
        a, b = rng.randrange(300), rng.randrange(300)
        if a == b:
            continue
        d += 1
        date = f"20{10 + d // 500:02d}-{(d // 40) % 12 + 1:02d}-{d % 28 + 1:02d}"
        za = skill[a] - 0.5 * ko_true[a]
        zb = skill[b] - 0.5 * ko_true[b]
        pa = 1 / (1 + math.exp(-(za - zb)))
        won_a = 1 if rng.random() < pa else 0
        ko = rng.random() < 0.35
        bouts.append({"date": date, "a": f"F{a}", "b": f"F{b}", "won_a": won_a,
                      "ko_loss_a": 1 if (not won_a and ko) else 0,
                      "ko_win_a": 1 if (won_a and ko) else 0})
        if ko:
            ko_true[b if won_a else a] += 1
    bouts.sort(key=lambda x: x["date"])
    feats = walk_features(bouts)
    global SCORE_FROM, TRAIN_END, PERIODS
    SCORE_FROM, TRAIN_END = "2013-01-01", "2018-12-31"
    PERIODS = [("2019-01-01", "2019-12-31"), ("2020-01-01", "2020-12-31"),
               ("2021-01-01", "2026-12-31")]
    buf = []
    res = experiment(feats, out=lambda s: buf.append(s))
    d_chin = res["CHIN (KO-losses diff)"][0]
    assert d_chin > 0.002, f"planted chin NOT recovered: {d_chin}\n" + "\n".join(buf)
    # null: ko flags stripped (on a COPY) -> chin adds nothing
    null_bouts = [dict(bt) for bt in bouts]
    for bt in null_bouts:
        bt["ko_loss_a"], bt["ko_win_a"] = 0, 0
    res0 = experiment(walk_features(null_bouts), out=lambda s: None)
    assert res0["CHIN (KO-losses diff)"][0] < d_chin / 3, "null suspicious"
    # leak: poison outcomes after a cutoff (on a COPY); earlier features identical
    f1 = [(bt["date"], f) for bt, f in feats if bt["date"] <= "2016-01-01"]
    poison = [dict(bt) for bt in bouts]
    for bt in poison:
        if bt["date"] > "2016-01-01":
            bt["won_a"] = 1 - bt["won_a"]
    f2 = [(bt["date"], f) for bt, f in walk_features(poison) if bt["date"] <= "2016-01-01"]
    assert json.dumps(f1, sort_keys=True) == json.dumps(f2, sort_keys=True), "LEAK"
    print(f"UFC ANGLES SELFTEST PASS — planted chin recovered (dLL {d_chin:+.4f}), "
          "null clean, leak-free")
    return 0

def main():
    bouts = load_bouts(os.path.join(HERE, "data", "fighter_bouts.csv"))
    print(f"unique bouts: {len(bouts)} ({bouts[0]['date']}..{bouts[-1]['date']})")
    feats = walk_features(bouts)
    lines = []
    def tee(s):
        print(s); lines.append(s)
    tee("=" * 70)
    tee("UFC ANGLES — chin decay + streak momentum vs walk-forward Elo")
    tee("=" * 70)
    experiment(feats, out=tee)
    tee("Ship rule: ROBUST WIN only (train win + holdout win + 3/3 periods).")
    vd = os.path.join(HERE, "..", "experiments", "UFC-ANGLES-VERDICT.md")
    os.makedirs(os.path.dirname(vd), exist_ok=True)
    with open(vd, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"verdict -> {vd}")
    return 0

if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
