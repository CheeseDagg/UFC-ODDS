==============================================================================
UFC ANGLES 6 — mileage and weight: the two career histories Elo cannot carry
==============================================================================
unique bouts: 8686 (1994-03-11..2026-06-14)
both DOB known: 8439 (97%)   both with prior bouts: 6504 (75%)   weight-ladder known: 6386 (74%)
HOLDOUT accumulator- AND weight-complete: 1415/1771 (79.9%)

--- DECISIVE SUBSET: age-, accumulator- and weight-complete (n=6283)
    rows where the term is not identically zero: QUICK 287, WTUP 904, WTNEW 589
    A term that is zero on most of the panel is not thereby weak, but
    its effective sample IS that count, and the ceilings are read
    against it rather than against n.

baseline (Elo + chin + age + layoff): a=1.6 c=-0.06 g=-0.06 L=-0.05  TRAIN LL -0.66558
baseline HOLDOUT -0.64497 (n=1395)
MILEAGE strikes absorbed, hundreds           b= -0.03  train_win=True   holdout dLL +0.00379  periods 3/3  -> ROBUST WIN
CAGE    career cage hours [MILEAGE's control] b= -0.07  train_win=False  holdout dLL +0.00267  periods 3/3  -> win, not robust
KDABS   knockdowns absorbed                  b= -0.06  train_win=False  holdout dLL +0.00156  periods 2/3  -> win, not robust
WTUP    rungs moved up since last bout       b=  0.06  train_win=True   holdout dLL -0.00010  periods 1/3  -> NULL
WTNEW   first bout ever at this weight       b= -0.08  train_win=False  holdout dLL -0.00034  periods 1/3  -> NULL
QUICK   turnaround under 60 days             b= -0.08  train_win=True   holdout dLL -0.00011  periods 1/3  -> NULL
EXPER   bouts so far, tens [CONTROL]         b= -0.07  train_win=True   holdout dLL +0.00187  periods 3/3  -> ROBUST WIN

--- CEILINGS. ORACLE = what a model that knew the true coefficient
    would buy (a hard bound). FITTED = what this pipeline actually
    recovers when the effect is real. n_rob/n_seed = how often a
    PLANTED effect survived the ship rule; that count, not a magic
    number, is what decides 'invisible' from 'dead'.
MILEAGE strikes absorbed, hundreds           oracle(b=-0.03) +0.00180 [+0.00074..+0.00317]  fitted +0.00180  plant 0/3  measured +0.00379   measured >= ORACLE: noise by construction
CAGE    career cage hours [MILEAGE's control] oracle(b=-0.07) +0.00094 [+0.00055..+0.00115]  fitted +0.00094  plant 0/3  measured +0.00267   measured >= ORACLE: noise by construction
KDABS   knockdowns absorbed                  oracle(b=-0.06) +0.00236 [+0.00022..+0.00442]  fitted +0.00236  plant 0/3  measured +0.00156   inside the oracle's seed spread: unreadable
WTUP    rungs moved up since last bout       oracle(b=+0.06) +0.00029 [-0.00014..+0.00076]  fitted -0.00003  plant 1/3  measured -0.00010   inside the oracle's seed spread: unreadable
WTNEW   first bout ever at this weight         (plant b=-0.08 absorbed by the baseline, oracle -0.00002 — stepping up)
WTNEW   first bout ever at this weight         (plant b=-0.16 absorbed by the baseline, oracle -0.00000 — stepping up)
WTNEW   first bout ever at this weight       oracle(b=-0.28) +0.00037 [-0.00052..+0.00114]  fitted +0.00051  plant 0/3  measured -0.00034   inside the oracle's seed spread: unreadable
QUICK   turnaround under 60 days               (plant b=-0.08 absorbed by the baseline, oracle -0.00007 — stepping up)
QUICK   turnaround under 60 days               (plant b=-0.16 absorbed by the baseline, oracle -0.00017 — stepping up)
QUICK   turnaround under 60 days             oracle(b=-0.28) +0.00008 [-0.00034..+0.00031]  fitted -0.00033  plant 0/3  measured -0.00011   inside the oracle's seed spread: unreadable
EXPER   bouts so far, tens [CONTROL]         oracle(b=-0.07) +0.00016 [-0.00040..+0.00064]  fitted -0.00054  plant 0/3  measured +0.00187   measured >= ORACLE: noise by construction

--- SECOND PASS: EXPER is now IN THE BASELINE. Every accumulator here
    counts up as a career runs, so all six are correlated with plain
    experience and with each other. An accumulator judged without
    EXPER underneath it is EXPERIENCE IN A WIG. Only this pass is
    quoted as a finding; the first pass names suspects.
baseline (Elo + chin + age + layoff + EXPER): a=1.6 c=-0.06 g=-0.06 L=-0.05  exp_d=-0.03  TRAIN LL -0.66549
baseline HOLDOUT -0.64407 (n=1395)
MILEAGE strikes absorbed, hundreds           b= -0.03  train_win=True   holdout dLL +0.00322  periods 3/3  -> ROBUST WIN
CAGE    career cage hours [MILEAGE's control] b=  0.07  train_win=False  holdout dLL -0.00471  periods 0/3  -> NULL
KDABS   knockdowns absorbed                  b= -0.06  train_win=False  holdout dLL +0.00107  periods 2/3  -> win, not robust
WTUP    rungs moved up since last bout       b=  0.06  train_win=True   holdout dLL -0.00010  periods 1/3  -> NULL
WTNEW   first bout ever at this weight       b= -0.08  train_win=False  holdout dLL -0.00033  periods 1/3  -> NULL
QUICK   turnaround under 60 days             b= -0.08  train_win=True   holdout dLL -0.00012  periods 1/3  -> NULL

--- CEILINGS. ORACLE = what a model that knew the true coefficient
    would buy (a hard bound). FITTED = what this pipeline actually
    recovers when the effect is real. n_rob/n_seed = how often a
    PLANTED effect survived the ship rule; that count, not a magic
    number, is what decides 'invisible' from 'dead'.
MILEAGE strikes absorbed, hundreds           oracle(b=-0.03) +0.00131 [-0.00063..+0.00328]  fitted +0.00131  plant 0/3  measured +0.00322   measured >= ORACLE: noise by construction
CAGE    career cage hours [MILEAGE's control]   (plant b=+0.07 absorbed by the baseline, oracle -0.00182 — stepping up)
CAGE    career cage hours [MILEAGE's control]   (plant b=+0.15 absorbed by the baseline, oracle -0.00532 — stepping up)
CAGE    career cage hours [MILEAGE's control]   (plant b=+0.25 absorbed by the baseline, oracle -0.01493 — stepping up)
CAGE    career cage hours [MILEAGE's control]   (plant b=+0.40 absorbed by the baseline, oracle -0.01585 — stepping up)
CAGE    career cage hours [MILEAGE's control] oracle(b=+0.40) -0.01585 [-0.01853..-0.01416]  fitted +0.00257  plant 1/3  measured -0.00471   PROBE UNINFORMATIVE: the oracle came out -0.01585, i.e. the refit baseline absorbed the planted effect. Plant weaker, or accept that this term is not separable from the baseline by this construction — do NOT read a verdict off this line
KDABS   knockdowns absorbed                  oracle(b=-0.06) +0.00257 [+0.00023..+0.00509]  fitted +0.00257  plant 0/3  measured +0.00107   inside the oracle's seed spread: unreadable
WTUP    rungs moved up since last bout       oracle(b=+0.06) +0.00033 [-0.00011..+0.00081]  fitted -0.00001  plant 1/3  measured -0.00010   inside the oracle's seed spread: unreadable
WTNEW   first bout ever at this weight         (plant b=-0.08 absorbed by the baseline, oracle -0.00004 — stepping up)
WTNEW   first bout ever at this weight       oracle(b=-0.16) +0.00001 [-0.00048..+0.00051]  fitted +0.00013  plant 1/3  measured -0.00033   inside the oracle's seed spread: unreadable
QUICK   turnaround under 60 days               (plant b=-0.08 absorbed by the baseline, oracle -0.00007 — stepping up)
QUICK   turnaround under 60 days               (plant b=-0.16 absorbed by the baseline, oracle -0.00013 — stepping up)
QUICK   turnaround under 60 days             oracle(b=-0.28) +0.00005 [-0.00034..+0.00027]  fitted -0.00032  plant 0/3  measured -0.00012   inside the oracle's seed spread: unreadable

Ship rule: ROBUST WIN in the SECOND PASS, and a measured gain at or
above the FITTED threshold while under the ORACLE bound. Anything
that clears it still owes gates 2-4 in ufc_gates before it ships.

================================================================================
DECISION — read this before the tables above
================================================================================

NOTHING FROM ROUND 6 SHIPS. Six candidates, four dead on the holdout, one
(CAGE) killed by its own control, and one (MILEAGE) that looked like the best
result this repo has ever produced and is not.

MILEAGE, in full, because the disagreement between the gates is the finding.

  SECOND PASS      b=-0.03, holdout dLL +0.00322, periods 3/3, ROBUST WIN.
                   For scale: LAYAGE shipped at +0.00178 and ACTIV at +0.00063.
  GATE 2 PLACEBO   PASSED, and not narrowly. 120 within-year shuffles reached
                   the observed gain 0 times; 120 global shuffles, 0 times.
                   Joint p=0.0083 both ways. The win is not shape.
  GATE 4 SHAPE     PASSED, and cleanly. Raw holdout win rate by quintile of
                   the term: 59.5 / 54.8 / 49.1 / 43.7 / 36.2 — monotone across
                   23 points. Against the second-pass baseline's own
                   predictions the residual is monotone too: +4.42, +3.12,
                   -1.20, -3.63, -6.89. The baseline really is miscalibrated
                   along this axis in this holdout.
  GATE 1 CEILING   FAILED, decisively, once the probe had enough seeds. Plant a
                   TRUE mileage effect of exactly the fitted -0.03 into the
                   panel and the pipeline recovers it 0 times out of 12. Mean
                   oracle -0.00019, i.e. a model HANDED the true coefficient
                   gains nothing. A -0.03 mileage effect is invisible to this
                   panel. So whatever produced +0.00322 on the real data, it
                   cannot be a -0.03 mileage effect being detected, because
                   this panel demonstrably cannot detect one.
  GATE 3 SEASON    FAILED. EARLY (hold 2017-19) +0.00082, 2/3, not robust.
                   MID (hold 2020-22) -0.00100, 1/3, NULL. LATE (hold 2023-26)
                   +0.00322, 3/3. The term works in exactly one era, and it is
                   the era the ship rule tunes on.

  READ: gates 2 and 4 together certify that something real is happening in the
  2023-2026 holdout along the mileage axis. Gates 1 and 3 together say it is
  not accumulated damage. An era-specific miscalibration of the BASELINE that
  happens to line up with a career accumulator passes a placebo (it is not
  shape) and passes a shape check (it is a genuine gradient) and still fails
  to replicate anywhere else, because it was never the accumulator. That is
  the whole pattern, and it is why gate 3 exists.

CAGE IS THE CLEANEST RESULT IN THE ROUND AND IT IS A NEGATIVE ONE.
First pass, no EXPER in the baseline: +0.00267, periods 3/3. Second pass, EXPER
carried at -0.03: -0.00471, periods 0/3. A 3/3 holdout win became a 0/3 NULL by
adding one control. Career cage time was experience wearing a damage costume,
exactly as predicted, and the size of the flip is the measurement of how much
work the control does. Every accumulator round after this one must carry EXPER.

KDABS is unreadable, not dead: oracle +0.00257 with the measured +0.00107 inside
the seed spread, and its shape check fails (the sign comes from the top
quintile, 40.5%, with q1-q4 flat) — so even the gradient MILEAGE has, this
does not have.
WTUP, WTNEW and QUICK are dead on the holdout with nothing to salvage. QUICK is
the one to revisit if the panel grows: only 287 of 6,283 rows are non-zero, and
a planted effect was recovered 1/3, which is an unreadable panel rather than a
refuted claim.

TWO METHOD CHANGES CAME OUT OF THIS ROUND AND BOTH ARE LOAD-BEARING.

1. THE CEILING LADDER NOW PLANTS AT THE FITTED MAGNITUDE AND STEPS UP.
   Rounds 3-5 planted at the STRONGEST grid value and stepped DOWN only when
   the oracle came back non-positive. On MILEAGE that rule planted b=-0.30
   against a fitted b=-0.03 — a world where the effect is ten times what the
   data claims — found it trivially detectable (oracle +0.074, plant 3/3), and
   printed DEAD on the grounds that "an effect of this size would have shown".
   True, and about a different effect. In rounds 3-5 the fitted coefficients sat
   near the grid walls so the two ladders coincided and the defect never
   surfaced. It surfaced here because the fit is an order of magnitude off the
   wall. WORTH RE-READING ACTIV'S CEILING UNDER THE NEW LADDER.

2. THE SECOND-PASS CONTROL GRID WAS TOO COARSE NEAR ZERO AND THE CONTROL FIT
   TO EXACTLY ZERO. EXPER's TRAIN optimum is near -0.04; the round-5 control
   grid's nearest rungs were -0.08 and 0.0, and -0.08 overshoots badly enough
   to score worse than carrying no term at all. So the first draft's "second
   pass" was a bit-for-bit rerun of the first pass, with every candidate still
   free to impersonate experience — and it would have shipped CAGE. The
   experiment now shouts when a control pins at zero, because a control that
   fits to zero controls nothing and nothing about the output looks wrong.

--------------------------------------------------------------------------------
RETROACTIVE: ACTIV DOES NOT SHIP EITHER
--------------------------------------------------------------------------------
The ladder fix above was applied to round 3's only outstanding candidate. ACTIV
fits at b=+0.10; the old ladder planted at the grid wall, b=+0.30, three times
the effect the data claims. Re-read at its own fitted magnitude, 12 seeds,
age-complete subset n=8439:

  plant b=+0.30  oracle +0.00476 [-0.00137..+0.01150]  fitted +0.00501  6/12
                 -> "won but sits inside the oracle's own seed spread:
                     UNPROVEN, needs a placebo"          (the old reading)
  plant b=+0.10  oracle +0.00014 [-0.00160..+0.00203]  fitted +0.00029  1/12
                 -> "measured >= ORACLE: noise by construction"

A true +0.10 activity effect is recovered once in twelve tries and buys a model
that KNOWS it +0.00014. ACTIV measured +0.00063 — four times what full knowledge
of the effect is worth. Same signature as MILEAGE, and the same verdict.

That leaves LAYAGE as the only surviving UFC angle in six rounds, and LAYAGE is
unaffected by the fix: it fits at -0.08, which is already the smallest magnitude
on its own grid, so the old ladder had stepped all the way down to the fitted
value before it stopped. Its ceiling was and remains PROBE UNINFORMATIVE — the
baseline absorbs the plant at every rung — and its case rests on the 300-shuffle
placebo (p=0.0033) and the three-era replication, not on a ceiling.
