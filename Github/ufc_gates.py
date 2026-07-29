"""Gates 2 and 3 of the ship rule, as a module instead of four scratch files.

THE SHIP RULE, in order, and why it is in that order:

  GATE 1  POWER CEILING       could this panel have seen the effect at all?
  GATE 2  SHUFFLED PLACEBO    can a term carrying NO information reach this?
  GATE 3  CROSS-SEASON        does it survive being asked about another era?
  GATE 4  SHAPE CHECK         does the fitted coefficient mean what it claims?

Gate 1 lives in the experiment files (probe / read_ceiling). Gates 2 and 3
were run out of /tmp during the LAYAGE and ACTIV validation, which meant the
methodology that decided whether a term ships existed only as scratch. That
is backwards: the code that kills an angle deserves at least the care of the
code that proposes one. This file is that code, with a selftest.

WHAT A SHUFFLE ACTUALLY DOES. Permuting a feature column across rows breaks
the row<->feature link while preserving the feature's marginal distribution
EXACTLY — same values, same spread, same skew, same outliers. So the shuffled
term has every property of the real one except the only one that matters. If
the pipeline can extract a win from that, the pipeline is extracting a win
from shape, not from information, and the real term's win means nothing.

TWO SHUFFLES, BECAUSE THEY ANSWER DIFFERENT QUESTIONS.

  GLOBAL       permute across the whole panel. This also destroys the TIME
               structure, so a term that wins only because of WHEN its large
               values fall will beat this placebo easily and look real. It is
               the lenient test and it is reported for contrast.
  WITHIN-YEAR  permute only among bouts in the same calendar year. Time
               structure survives; only the row pairing dies. This is the
               strict test, and it is the one that matters for a term like
               ACTIV whose distribution moved hard in 2020 — under a global
               shuffle, "2020 was weird" is enough to manufacture a win.

THE JOINT NULL IS THE ONE THAT DECIDES. The first placebo run counted two
things separately — how often a placebo matched the GAIN, and how often it
scored a ROBUST WIN — and for ACTIV those two disagreed sharply: 8-10/150
against 0/150. Reporting either number alone picks a side of that
disagreement by accident, and the side you pick decides whether the angle
ships. The event actually observed is "a robust win of at least this size",
so the null rate of that CONJUNCTION is the p-value with a claim on the
decision. Both marginals are still printed, because a large gap between them
is itself informative: it says the robustness criterion and the size
criterion are being cleared by different things.

The p-value is (hits + 1) / (N + 1), not hits / N. The +1 is the observed
statistic counting as one of its own draws — without it, zero hits reports
p = 0, which claims more certainty than N shuffles can buy.
"""
import importlib
import inspect
import os
import random
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# Gate 3's three eras. DISJOINT holdouts, each with its own baseline fit and
# its own knob tune — nothing is carried across from one era to the next. A
# term that only works on 2023-2026 is a property of 2023-2026, and the only
# way to find that out is to refit the whole pipeline somewhere else.
SPLITS = [
    ("EARLY  train 2012-2016, hold 2017-2019", "2012-01-01", "2016-12-31",
     [("2017-01-01", "2017-12-31"), ("2018-01-01", "2018-12-31"),
      ("2019-01-01", "2019-12-31")]),
    ("MID    train 2012-2019, hold 2020-2022", "2012-01-01", "2019-12-31",
     [("2020-01-01", "2020-12-31"), ("2021-01-01", "2021-12-31"),
      ("2022-01-01", "2022-12-31")]),
    ("LATE   train 2012-2022, hold 2023-2026", "2012-01-01", "2022-12-31",
     [("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"),
      ("2025-01-01", "2026-12-31")]),
]


def read_ceiling(got, won, o, olo, fi, n_rob, n_seed):
    """GATE 1's reader: turn a power ceiling into a verdict.

    Canonical copy. It lives here rather than in an experiment file because
    every batch needs it and a ladder that exists in three places is a ladder
    that will differ in three places — which is not hypothetical, since this
    one has been gotten wrong three separate times already:

      twice by testing "too small to see" BEFORE "did it win", which prints
      real wins as invisible;

      and once by using a hard-coded oracle cutoff (c > 0.004) to stand in for
      detectability. That cutoff mislabelled MLB's LOAD: oracle +0.00038, a
      hair under the line, printed "cannot be seen" on the very run where the
      fitted pipeline recovered a PLANTED load effect robustly in 3 of 3
      seeds. The panel could see it. The constant said otherwise.

    So detectability is MEASURED, never assumed. n_rob/n_seed is the count of
    seeds in which a planted, true-by-construction effect actually survived
    the full ship rule, and that is the direct answer to "could this panel
    have seen it" — a question no constant can answer, because it depends on
    the panel, the term's own distribution, and the holdout size together.

    ORACLE (o) is what a model that already KNEW the true coefficient would
    gain: a hard bound, since no fitted model beats one handed the answer.
    FITTED (fi) is what the real tune-and-verdict pipeline recovers from a
    panel where the effect is true. Caveat worth carrying: when the plant is
    generated AT a grid point, tune recovers it exactly and fi == o, so fitted
    does little independent work and n_rob/n_seed carries the ladder.
    """
    if o <= 0.0:
        # A NON-POSITIVE ORACLE IS A BROKEN PROBE, NOT A DEAD ANGLE, and this
        # rung exists because the missing guard nearly buried LAYAGE — the one
        # validated UFC term — the moment the baseline grids were widened.
        #
        # The mechanism is worth stating, because it will recur. The oracle is
        # built by planting the effect at strength b and REFITTING the baseline
        # on the synthetic panel. If the planted term is closely correlated
        # with terms already IN the baseline — layoff x age is a product of two
        # baseline main effects — a well-specified baseline simply absorbs it.
        # Widening the grids made the baseline better at exactly that, so the
        # refit ate the plant and adding the true coefficient on top of an
        # already-compensating baseline HURT. The bound came out negative.
        #
        # Read literally, "measured >= oracle" then fires for any positive
        # measurement and prints noise-by-construction over a term that passed
        # a 300-shuffle placebo at p=0.0033 and replicated in three disjoint
        # eras. The probe failed; the angle did not.
        return (f"PROBE UNINFORMATIVE: the oracle came out {o:+.5f}, i.e. the "
                "refit baseline absorbed the planted effect. Plant weaker, or "
                "accept that this term is not separable from the baseline by "
                "this construction — do NOT read a verdict off this line")
    if got >= o:
        return "measured >= ORACLE: noise by construction"
    if got >= olo:
        return ("won but sits inside the oracle's own seed spread: "
                "UNPROVEN, needs a placebo" if won else
                "inside the oracle's seed spread: unreadable")
    if won and got >= fi:
        return f"LIVE: robust win at {100.0 * got / o:.0f}% of oracle"
    if n_rob * 2 < n_seed:
        return (f"STILL CANNOT BE SEEN - do not bury (a planted effect "
                f"was itself only recovered {n_rob}/{n_seed})")
    return (f"DEAD: a planted effect of this size was recovered "
            f"{n_rob}/{n_seed}, so a real one would have shown")


class Panel:
    """One experiment module plus one feature list, with the baseline fitted.

    Exists because angles3 and angles4 do NOT have the same signatures —
    angles4's fit_baseline takes with_reach and returns three values, angles3's
    takes neither and returns two. Rather than fork the gate code per module
    (which is how two copies drift apart and stop testing the same thing), the
    difference is absorbed here once, by inspecting the signature.
    """

    def __init__(self, mod, feats, with_reach=False):
        self.M = mod
        self.feats = feats
        self.with_reach = with_reach
        self._wants_reach = "with_reach" in inspect.signature(
            mod.fit_baseline).parameters
        self._wants_base_extra = "base_extra" in inspect.signature(
            mod.ll).parameters
        self.refit()

    def refit(self):
        """Fit the baseline against the module's CURRENT PERIODS/TRAIN_END.

        Gate 3 mutates those module globals between eras, so the baseline has
        to be refittable rather than fixed at construction. Refitting is the
        entire point — an era's verdict computed against another era's
        baseline coefficients is not a replication, it is a transplant.
        """
        M = self.M
        if self._wants_reach:
            co, tr, be = M.fit_baseline(self.feats, out=lambda s: None,
                                        with_reach=self.with_reach)
            self.base_extra = be
        else:
            co, tr = M.fit_baseline(self.feats, out=lambda s: None)
            self.base_extra = None
        self.co, self.base_tr = co, tr
        self.h0, self.h1 = M.PERIODS[0][0], M.PERIODS[-1][1]
        self.base_h, self.n_hold = self._ll(self.feats, self.h0, self.h1)
        return self

    def _ll(self, fe, d0, d1, extra=None):
        kw = {"extra": extra}
        if self._wants_base_extra:
            kw["base_extra"] = self.base_extra
        return self.M.ll(fe, self.co, d0, d1, **kw)

    def verdict(self, fe, key, grid):
        """(holdout gain, periods won, train improved) for one feature list.

        The three pieces are returned separately rather than collapsed to a
        boolean because the placebo needs to count the CONJUNCTION and each
        marginal, and a function that returns only the conjunction cannot
        report the disagreement between them.
        """
        M = self.M
        kw = {"base_extra": self.base_extra} if self._wants_base_extra else {}
        tr, B = M.tune(fe, self.co, key, grid, **kw)
        hv, _ = self._ll(fe, self.h0, self.h1, extra=(key, B))
        w = sum(1 for p0, p1 in M.PERIODS
                if self._ll(fe, p0, p1, extra=(key, B))[0]
                > self._ll(fe, p0, p1)[0])
        return hv - self.base_h, w, tr > self.base_tr, B


def shuffled(fe, key, rng, within_year):
    """Permute one feature column, leaving every other column pinned.

    Only `key` moves. If the whole row were shuffled, the baseline features
    would move with it and the baseline itself would degrade, which would hand
    the placebo an easy win against a broken control — the placebo has to be
    scored against the SAME baseline the real term was scored against.
    """
    vals = [f[key] for _, f in fe]
    if within_year:
        idx = defaultdict(list)
        for i, (bt, _) in enumerate(fe):
            idx[bt["date"][:4]].append(i)
        new = list(vals)
        for _, ii in idx.items():
            pool = [vals[i] for i in ii]
            rng.shuffle(pool)
            for i, v in zip(ii, pool):
                new[i] = v
        vals = new
    else:
        vals = list(vals)
        rng.shuffle(vals)
    return [(bt, dict(f, **{key: v})) for (bt, f), v in zip(fe, vals)]


def gate2(panel, key, grid, n=150, within_year=True, seed=4242, out=print):
    """Shuffled placebo. Returns the joint p-value and both marginals."""
    real, rw, _, B = panel.verdict(panel.feats, key, grid)
    rng = random.Random(seed)
    ge = rob = joint = 0
    for _ in range(n):
        d, w, tw, _ = panel.verdict(shuffled(panel.feats, key, rng,
                                             within_year), key, grid)
        big, robust = d >= real, (tw and d > 0 and w == 3)
        ge += big
        rob += robust
        joint += (big and robust)
    p = (joint + 1.0) / (n + 1.0)
    tag = "WITHIN-YEAR" if within_year else "GLOBAL"
    out(f"  {tag:11s} x{n}: reached the real gain {ge:3d}/{n}  "
        f"robust win {rob:3d}/{n}  JOINT {joint:3d}/{n}  p={p:.4f}")
    if ge and not rob or rob and not ge:
        out("    (the two marginals disagree — which is exactly why the "
            "joint count is the one reported as p)")
    return {"real": real, "b": B, "periods": rw, "ge": ge, "rob": rob,
            "joint": joint, "n": n, "p": p}


def gate3(mod, feats, keys, with_reach=False, out=print):
    """Cross-season replication across three disjoint eras.

    Restores the module globals afterwards. A gate that leaves SCORE_FROM
    pointing at 2016 would silently corrupt every experiment run after it in
    the same process, and the failure would surface somewhere else entirely.
    """
    keep = (mod.SCORE_FROM, mod.TRAIN_END, mod.PERIODS)
    rows = []
    try:
        for name, sf, te, pers in SPLITS:
            mod.SCORE_FROM, mod.TRAIN_END, mod.PERIODS = sf, te, pers
            p = Panel(mod, feats, with_reach=with_reach)
            out(f"\n{name}  (holdout n={p.n_hold})  "
                f"base a={p.co['a']} g={p.co['g']} L={p.co['L']}")
            for label, k, grid in mod.ANGLES:
                if k not in keys:
                    continue
                d, w, tw, B = p.verdict(feats, k, grid)
                v = ("ROBUST WIN" if (tw and d > 0 and w == 3)
                     else "win, not robust" if d > 0 else "NULL")
                out(f"  {label:26s} b={B:>6} dLL {d:+.5f} "
                    f"periods {w}/3 -> {v}")
                rows.append({"era": name.split()[0], "label": label, "key": k,
                             "b": B, "d": d, "periods": w, "verdict": v})
    finally:
        mod.SCORE_FROM, mod.TRAIN_END, mod.PERIODS = keep
    return rows


def selftest():
    """Two panels: one where the term is real, one where it is pure noise.

    A placebo harness that never clears anything is indistinguishable from a
    placebo harness that is broken, so BOTH directions are asserted.
    """
    mod = importlib.import_module("ufc_angles3_experiment")

    # --- shuffled() must permute ONLY the named column, and within-year must
    # --- keep every value inside its own year. If either fails, the placebo
    # --- is testing something other than the term.
    fe = [({"date": f"20{20 + i // 4}-05-0{i % 4 + 1}"},
           {"x": float(i), "y": float(-i)}) for i in range(12)]
    sh = shuffled(fe, "x", random.Random(1), within_year=True)
    assert [f["y"] for _, f in sh] == [f["y"] for _, f in fe], (
        "the placebo moved a column it was not asked to move — the baseline "
        "would degrade and the placebo would be scored against a handicap")
    assert sorted(f["x"] for _, f in sh) == sorted(f["x"] for _, f in fe)
    for yr in ("2020", "2021", "2022"):
        a = sorted(f["x"] for bt, f in fe if bt["date"][:4] == yr)
        b = sorted(f["x"] for bt, f in sh if bt["date"][:4] == yr)
        assert a == b, (
            f"within-year shuffle leaked values across {yr} — that is the "
            "global shuffle wearing the strict shuffle's name, and it is the "
            "difference between p=0.06 and p=0.003 on ACTIV")
    gl = shuffled(fe, "x", random.Random(1), within_year=False)
    assert [f["x"] for _, f in gl] != [f["x"] for _, f in sh], (
        "global and within-year produced identical permutations — one of "
        "them is not doing what it says")

    # --- gate3 must put the module's globals back. Assert it even when the
    # --- body raises, because the damage from a leaked SCORE_FROM shows up in
    # --- some later experiment, not here.
    keep = (mod.SCORE_FROM, mod.TRAIN_END, mod.PERIODS)

    class Boom(Exception):
        pass

    def explode(*a, **k):
        raise Boom()

    real_panel = Panel
    try:
        globals()["Panel"] = explode
        try:
            gate3(mod, [], {"layage_d"}, out=lambda s: None)
        except Boom:
            pass
    finally:
        globals()["Panel"] = real_panel
    assert (mod.SCORE_FROM, mod.TRAIN_END, mod.PERIODS) == keep, (
        "gate3 left the module's era globals mutated after an exception; "
        "every experiment run later in this process would be silently scored "
        "against the wrong window")

    # --- the real test: a planted effect must beat its own placebo, and a
    # --- pure-noise column must not.
    bouts, ages = _synth_panel(mod)
    feats = [(b, f) for b, f in mod.walk_features(bouts, ages)
             if f["age_known"]]
    p = Panel(mod, feats)
    key, grid = "lay_d", (-0.45, -0.30, -0.18, -0.10, 0.0, 0.10)
    d, w, tw, _ = p.verdict(feats, key, grid)
    assert d > 0 and w == 3 and tw, (
        f"the PLANT itself was not detected (dLL {d:+.5f}, periods {w}/3) — "
        "nothing downstream of this means anything, because the placebo "
        "would then be exonerating a term the panel never found")
    hit = gate2(p, key, grid, n=12, within_year=True, out=lambda s: None)

    rng = random.Random(5)
    noise = [(bt, dict(f, lay_d=rng.gauss(0, 0.6))) for bt, f in feats]
    pn = Panel(mod, noise)
    miss = gate2(pn, key, grid, n=12, within_year=True, out=lambda s: None)

    # THE DISCRIMINATOR HERE IS `ge`, NOT `joint`, AND THAT IS NOT A FUDGE.
    # Against a noise column, tune correctly picks b=0, so the "real" gain is
    # 0.0 and no shuffle can score a robust win either — joint is 0/12 for the
    # plant AND for the noise, and an assertion on joint would pass while
    # comparing nothing at all (it did, in the first draft of this selftest).
    # The marginal that actually separates them is how often a shuffle MATCHES
    # the observed gain: impossible against a real effect, routine against a
    # gain of zero. On live panels the two marginals both carry information
    # and the joint is the reported p; on this fixture only one of them can.
    assert hit["ge"] * 3 <= hit["n"] and miss["ge"] * 2 > miss["n"], (
        f"placebo did not separate signal from shape: planted column matched "
        f"{hit['ge']}/{hit['n']}, noise column matched {miss['ge']}/"
        f"{miss['n']} — expected the first near zero and the second a "
        "majority")
    assert hit["p"] == 1.0 / (hit["n"] + 1.0), (
        "zero joint hits must report p = 1/(N+1), not 0 — N shuffles cannot "
        "buy certainty and a p of 0 claims they can")

    # --- gate 1's ladder, pinned. These are the three readings it has
    # --- historically gotten wrong; they are asserted here because this is
    # --- now the only copy and every experiment file imports it.
    assert read_ceiling(0.005, True, 0.004, 0.003, 0.004, 3, 3
                        ).startswith("measured >= ORACLE")
    assert read_ceiling(0.0020, True, 0.0100, 0.0090, 0.0015, 3, 3
                        ).startswith("LIVE"), (
        "a robust win comfortably under its oracle is the ONE outcome the "
        "ceiling exists to certify, and two earlier drafts printed it as dead")
    assert read_ceiling(-0.00001, False, 0.00038, 0.00035, 0.00037, 3, 3
                        ).startswith("DEAD"), (
        "a planted effect recovered 3/3 with a measured miss is DEAD, and no "
        "oracle-size cutoff gets a say in that — that constant is exactly "
        "what mislabelled MLB's LOAD")
    assert read_ceiling(-0.00001, False, 0.00038, 0.00035, 0.00037, 1, 3
                        ).startswith("STILL CANNOT BE SEEN"), (
        "same miss, same tiny oracle, but the plant was only recovered 1/3 — "
        "that is an unreadable panel, not a dead angle, and the two must not "
        "collapse into each other")

    print("UFC GATES SELFTEST PASS — column-local shuffle, within-year stays "
          "in year, gate3 restores globals on failure, plant detected and "
          f"unreachable by placebo ({hit['ge']}/{hit['n']}) where noise is "
          f"reachable ({miss['ge']}/{miss['n']})")


def _synth_panel(mod, n_men=140, seed=11):
    """A small panel where layoff genuinely predicts losing.

    Deliberately NOT the module's own _synth: this fixture has to plant an
    effect in a feature the gate is about to shuffle, and it has to be small
    enough that a 12-shuffle selftest finishes in seconds.
    """
    import datetime
    rng = random.Random(seed)
    D0 = datetime.date(2012, 1, 5)
    skill = {i: rng.gauss(0, 0.9) for i in range(n_men)}
    dob = {i: f"19{85 + i % 12}-{i % 9 + 1:02d}-15" for i in range(n_men)}
    last = {i: None for i in range(n_men)}
    bouts, day = [], 0
    while day < 365 * 13:
        day += rng.randrange(2, 9)
        a, b = rng.sample(range(n_men), 2)
        d = (D0 + datetime.timedelta(days=day)).isoformat()

        def lay(i):
            return (0.0 if last[i] is None
                    else min(2.0, (day - last[i]) / 365.25))
        # The plant: a long layoff LOSES. Big enough that 12 shuffles can see
        # it, since a selftest that needs 150 shuffles will not get run.
        z = skill[a] - skill[b] - 1.2 * (lay(a) - lay(b))
        won = 1 if rng.random() < 1.0 / (1.0 + pow(2.718281828, -z)) else 0
        bouts.append({"date": d, "a": f"F{a}", "b": f"F{b}", "won_a": won,
                      "ko_loss_a": 0, "ko_win_a": won, "secs": 900.0,
                      "land_a": 40.0, "land_b": 38.0})
        last[a] = last[b] = day
    bouts.sort(key=lambda x: x["date"])
    return bouts, {mod.norm_name(f"F{i}"): dob[i] for i in range(n_men)}


def main():
    """CLI: python ufc_gates.py <module> <key[,key...]> [N]"""
    if "--selftest" in sys.argv:
        return selftest()
    name = sys.argv[1] if len(sys.argv) > 1 else "ufc_angles3_experiment"
    keys = set((sys.argv[2] if len(sys.argv) > 2
                else "layage_d,activ_d").split(","))
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    mod = importlib.import_module(name)
    bouts = mod.load_bouts(os.path.join(mod.HERE, "data",
                                        "fighter_bouts.csv"))
    loader = getattr(mod, "load_ages", None) or mod.load_meta
    meta = loader(os.path.join(mod.HERE, "fighter_meta_cache.json"))
    feats = [(b, f) for b, f in mod.walk_features(bouts, meta)
             if f["age_known"]]
    p = Panel(mod, feats)
    print(f"{name}: n={len(feats)} holdout n={p.n_hold} base {p.co}")
    print("\n=== GATE 2  shuffled placebo ===")
    for label, k, grid in mod.ANGLES:
        if k not in keys:
            continue
        real, rw, _, B = p.verdict(feats, k, grid)
        print(f"\n{label}: REAL b={B} dLL {real:+.5f} periods {rw}/3")
        gate2(p, k, grid, n=n, within_year=False)
        gate2(p, k, grid, n=n, within_year=True)
    print("\n=== GATE 3  cross-season replication ===")
    gate3(mod, feats, keys)


if __name__ == "__main__":
    main()
