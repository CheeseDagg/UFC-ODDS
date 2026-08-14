#!/usr/bin/env python3
"""ufc_lag_backtest.py — is the blend miscalibrated by CAREER LENGTH?

    python3 ufc_lag_backtest.py            # real replay, writes ufc_lag_backtest.txt
    python3 ufc_lag_backtest.py --selftest

UFC 330 (2026-08-13) showed one shape three times: the model overrated a
long-career decliner (Luque, 67 vs the market's 49), ran cool on a
six-fight riser (Orolbai, 77 vs 88), and priced a 20-fight streak about
right (Robertson). The hypothesis: online Elo converges slowly from its
prior, so short careers read underrated and long declines read overrated.

Three receipts on one card is an anecdote. This replays the model's own
design over every fight in the dataset, leak-free and chronological:
walk the fights exactly as build_state_and_data does, record each fight's
pre-update feature row AND each side's pre-fight bout count, fit the
production logistic on the FIRST 70% only, and measure predicted-vs-
actual on the untouched last 30%, bucketed by career length.

The verdict is earned, not asserted: the same harness must first stay
QUIET on a synthetic null world (static true strengths -> Elo tracks
fine) and must DETECT a planted-lag world (strengths that drift with
career age -> Elo lags by construction). A detector that cannot pass its
control is not a detector -- f5hist's broken synthetic control taught
that the expensive way.

Buckets: short <=6 prior UFC fights, mid 7-15, long 16+. Two views:
  * side-level calibration: every eval side lands in its bucket;
  * matchup-level (the UFC 330 shape): fights pairing different buckets,
    scored from the SHORTER career's side.
Flat buckets kill the diagnosis. A real slope earns the blend a
career-length term. Either way the number decides.
"""
import math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ufc_blend_predict as B

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'ufc_lag_backtest.txt')
FIT_FRAC = 0.7
BUCKETS = (('short', 0, 6), ('mid', 7, 15), ('long', 16, 10 ** 9))


def bucket(n):
    for name, lo, hi in BUCKETS:
        if lo <= n <= hi:
            return name


def walk(fights):
    """One chronological pass: per fight, the PRE-update design row, both
    sides' pre-fight bout counts, and each side's last-5 win rate (the
    momentum the UFC 330 cells condition on). State evolves independent of
    any fit, so a single walk serves training prefix and evaluation tail."""
    state, last5, out = {}, {}, []
    for fg in fights:
        sA = state.setdefault(fg['A'], B.FighterState())
        sB = state.setdefault(fg['B'], B.FighterState())
        hA = last5.setdefault(fg['A'], [])
        hB = last5.setdefault(fg['B'], [])
        x = [p - q for p, q in zip(B._pre_feats(sA, fg['date']),
                                   B._pre_feats(sB, fg['date']))]
        out.append({'x': x, 'y': fg['yA'], 'nA': sA.n, 'nB': sB.n,
                    'r5A': sum(hA) / len(hA) if hA else None,
                    'r5B': sum(hB) / len(hB) if hB else None,
                    'date': fg['date']})
        eA = 1.0 / (1.0 + 10.0 ** ((sB.elo - sA.elo) / B.ELO_SCALE))
        sA.elo += B.ELO_K * (fg['yA'] - eA)
        sB.elo += B.ELO_K * ((1 - fg['yA']) - (1.0 - eA))
        B._update_state(sA, fg['rowA'], fg['date'])
        B._update_state(sB, fg['rowB'], fg['date'])
        hA.append(fg['yA']); hB.append(1 - fg['yA'])
        del hA[:-5], hB[:-5]
    return out


def cell(n, r5):
    """The UFC 330 cells: a SHORT career arriving on wins (Orolbai, 5-1) and
    a LONG career leaving on losses (Luque, 3-5 since '22). r5 is the
    last-5 win rate; None (a debut) can be neither.

    Fine print the control world taught: short-winning-underrated is
    expected from Elo convergence ALONE -- conditioning on early wins
    selects fighters whose rating is still climbing from the 1500 prior,
    drift or no drift. The cells' job on real data is the MAGNITUDE; the
    drift question belongs to the plain length buckets."""
    if r5 is None:
        return None
    if 3 <= n <= 8 and r5 >= 0.7:
        return 'short-winning'
    if n >= 16 and r5 <= 0.4:
        return 'long-declining'
    return None


def evaluate(rows, fit_frac=FIT_FRAC, iters=3000):
    """Fit on the prefix, score the tail, bucket both views."""
    cut = int(len(rows) * fit_frac)
    train, ev = rows[:cut], rows[cut:]
    predict = B.fit_mirror_logistic([r['x'] for r in train],
                                    [r['y'] for r in train], iters=iters)
    sides = {name: [] for name, _, _ in BUCKETS}      # (pred, won)
    cells = {'short-winning': [], 'long-declining': []}
    for r in ev:
        p = predict(r['x'])
        sides[bucket(r['nA'])].append((p, r['y']))
        sides[bucket(r['nB'])].append((1 - p, 1 - r['y']))
        cA, cB = cell(r['nA'], r['r5A']), cell(r['nB'], r['r5B'])
        if cA:
            cells[cA].append((p, r['y']))
        if cB:
            cells[cB].append((1 - p, 1 - r['y']))
    return sides, cells, len(train), len(ev)


def _row(name, v):
    """(line, signed bias or None). Bias = actual - predicted; the band is
    the plain binomial 95% on the actual rate. A row only speaks past it."""
    if not v:
        return f"  {name:<15} n=0", None
    n = len(v)
    pred = sum(p for p, _ in v) / n
    act = sum(y for _, y in v) / n
    band = 1.96 * math.sqrt(max(act * (1 - act), 1e-9) / n)
    bias = act - pred
    mark = ''
    if abs(bias) > band:
        mark = '  << model UNDERRATES' if bias > 0 else '  << model OVERRATES'
    return (f"  {name:<15} n={n:<5} predicted {pred*100:5.1f}%  "
            f"actual {act*100:5.1f}%  bias {bias*100:+5.1f} "
            f"(band ±{band*100:.1f}){mark}",
            bias if abs(bias) > band else None)


def table(sides, cells):
    """(lines, verdict). The named UFC 330 cells carry the verdict; the
    plain length buckets print beside them as context."""
    lines, flags = ["  -- the UFC 330 cells --"], {}
    for name in ('short-winning', 'long-declining'):
        line, bias = _row(name, cells[name])
        lines.append(line)
        if bias is not None:
            flags[name] = bias
    lines.append("  -- plain length buckets --")
    for name, _, _ in BUCKETS:
        line, bias = _row(name, sides[name])
        lines.append(line)
        if bias is not None:
            flags[name] = bias
    sw, ld = flags.get('short-winning'), flags.get('long-declining')
    if (sw is not None and sw > 0) or (ld is not None and ld < 0):
        wrong_way = (sw is not None and sw < 0) or (ld is not None and ld > 0)
        verdict = 'MIXED -- cells disagree' if wrong_way else 'UFC-330 SHAPE CONFIRMED'
    elif flags:
        verdict = 'MISCALIBRATED, but not the UFC 330 shape'
    else:
        verdict = 'FLAT -- the UFC 330 pattern reads as coincidence'
    return lines, verdict


def main():
    import csv
    with open(B.BOUTS_CSV, newline='') as f:
        rows = list(csv.DictReader(f))
    fights = B.dedupe_fights(rows)
    walked = walk(fights)
    sides, cells, ntr, nev = evaluate(walked)
    lines, verdict = table(sides, cells)
    hdr = (f"career-length calibration replay -- {len(fights)} fights, "
           f"fit on first {ntr}, judged on last {nev} (out of sample)\n"
           f"model: the production no-age design (Elo core), fit by the "
           f"production fitter\n")
    txt = hdr + '\n'.join(lines) + f"\n\nVERDICT: {verdict}\n"
    print(txt)
    open(OUT, 'w').write(txt)
    return 0


# ---------------------------------------------------------------------------
# synthetic worlds -- the control must pass before the finding counts
# ---------------------------------------------------------------------------

def _mkrow(won):
    return {'secs': 900, 'sig_l': 0, 'sig_l_opp': 0, 'td_l': 0, 'td_l_opp': 0,
            'ctrl': 0, 'won': won, 'sub': 0, 'lost_by_ko': 0, 'stats_known': '1'}


def _world(seed, lag, n_fights=2400):
    """Synthetic fight history with the two properties real rosters have and
    the first draft of this world lacked: CONTINUOUS DEBUTS (a closed pool of
    80 meant everyone was 20 fights deep by the evaluation tail -- the short
    bucket was empty exactly where it was judged) and HETEROGENEOUS arcs
    (per-fighter rise rates and decline onsets; a uniform linear-in-n drift
    is absorbed by the model's own n feature and detects nothing).

    lag=False: static true strengths -- buckets must read FLAT.
    lag=True: each fighter rises at their own rate early and decays past
    their own onset -- a moving truth that finite-K Elo lags by construction."""
    import datetime as dt
    import random
    rng = random.Random(seed)
    strength, arc, nf = {}, {}, {}
    def debut(k):
        strength[k] = rng.gauss(0, 1.0)
        arc[k] = (rng.uniform(0.05, 0.3),           # rise per fight, first 10
                  rng.randint(10, 20),              # decline onset
                  rng.uniform(0.1, 0.35))           # decay per fight past onset
        nf[k] = 0
    for k in range(24):
        debut(k)
    nxt = 24
    fights, day = [], dt.date(2015, 1, 1)
    for k in range(n_fights):
        if rng.random() < 0.03:                     # steady debut influx
            debut(nxt); nxt += 1
        active = [f for f in strength if nf[f] < 30]
        while len(active) < 8:                      # roster never runs dry
            debut(nxt); active.append(nxt); nxt += 1
        i, j = rng.sample(active, 2)
        def true_s(f):
            s = strength[f]
            if lag:
                up, onset, down = arc[f]
                s += up * min(nf[f], 10) - down * max(nf[f] - onset, 0)
            return s
        pi = 1.0 / (1.0 + math.exp(-(true_s(i) - true_s(j))))
        yi = 1 if rng.random() < pi else 0
        A, Bn = f"f{i:03d}", f"f{j:03d}"
        fg = {'date': day, 'A': A, 'B': Bn, 'yA': yi,
              'rowA': _mkrow(yi), 'rowB': _mkrow(1 - yi)}
        if A > Bn:
            fg = {'date': day, 'A': Bn, 'B': A, 'yA': 1 - yi,
                  'rowA': _mkrow(1 - yi), 'rowB': _mkrow(yi)}
        fights.append(fg)
        nf[i] += 1; nf[j] += 1
        day += dt.timedelta(days=1 + (k % 3))
    return fights


def flags_of(groups):
    """{name: signed bias} for every group whose bias clears its band."""
    out = {}
    for name, v in groups.items():
        _, bias = _row(name, v)
        if bias is not None:
            out[name] = bias
    return out


def selftest():
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    chk(bucket(0) == 'short' and bucket(6) == 'short' and bucket(7) == 'mid'
        and bucket(15) == 'mid' and bucket(16) == 'long',
        "bucket edges sit exactly at 6/7 and 15/16")

    chk(cell(5, 0.8) == 'short-winning' and cell(20, 0.2) == 'long-declining'
        and cell(5, 0.4) is None and cell(20, 0.8) is None
        and cell(0, None) is None,
        "the named cells are exactly Orolbai's and Luque's shapes; a debut "
        "and everyone mid-shaped stay out of them")

    rows = walk(_world(7, lag=False))
    chk(len(rows) == 2400 and rows[0]["nA"] == 0 and rows[0]["r5A"] is None,
        "the walk records PRE-fight counts and last-5 (debuts have neither)")
    _, _, ntr, nev = evaluate(rows, iters=500)
    chk(ntr == 1680 and nev == 720,
        "the fit sees only the first 70%; the judged tail is untouched")

    sides, cells, _, _ = evaluate(rows, iters=800)
    fl = flags_of(sides)
    chk(fl == {},
        f"CONTROL: the static world's PLAIN buckets are flat (got {fl}) -- "
        "the null world is null about career-arc drift, and a detector that "
        "finds drift where none exists is not a detector. (The momentum "
        "cells MAY flag here: Elo converging from its prior is real even in "
        "a static world -- that is the fine print, not a false positive.)")

    sides, cells, _, _ = evaluate(walk(_world(11, lag=True)), iters=800)
    fl = flags_of(sides)
    chk(fl != {},
        f"PLANTED: career-arc drift moves the PLAIN buckets (got {fl}) -- "
        "the harness has the power to see a moving truth that Elo lags")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == '__main__':
    sys.exit(selftest() if '--selftest' in sys.argv else main())
