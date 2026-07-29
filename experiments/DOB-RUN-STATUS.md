# DOB backfill run status

run    30480422150  attempt 8
sha    1dcc23510a68c51ad42ca60e6903da95a21d0a07
when   2026-07-29T18:42:17Z

step outcomes (failure here is the whole point of this file):
  selftest  success
  before    success
  backfill  success
  after     success
  angles    success
  stance    success
  angles4   success

coverage BEFORE:
  fighters: 2554/2678 with DOB  |  bouts with BOTH ages: 8439/8686 (97.2%)
coverage AFTER:
  fighters: 2554/2678 with DOB  |  bouts with BOTH ages: 8439/8686 (97.2%)

--- stance coverage ---
ALL: both stances known 7112/8686 (81.9%)
HOLDOUT: both stances known 1626/1771 (91.8%)
Counter({'Orthodox': 1740, 'Southpaw': 396, 'Switch': 145, 'Open Stance': 3, 'Sideways': 2})

--- backfill tail (last 200 lines) ---
missing DOB for 124 of 2678 fighters
missing STANCE for 1282 fighters active since 2015-01-01 (1256 of them already have a DOB and would never have been fetched)
BEFORE: fighters: 2554/2678 with DOB  |  bouts with BOTH ages: 8439/8686 (97.2%)
ufcstats pass
  challenge solved: nonce=f3fb53375b080823 n=569 -> /__c, 1 cookie(s) held
  warmed cookie jar: 29869 chars, 1 cookie(s) held, still challenged=False
  ufcstats index: 4575 fighters enumerated
  1303 of them are names we are missing — fetching details
  ...200/1303  hits 196
  banked: 0 DOBs so far
  ...400/1303  hits 392
  banked: 0 DOBs so far
  ...600/1303  hits 585
  banked: 0 DOBs so far
  ...800/1303  hits 780
  banked: 0 DOBs so far
  ...1000/1303  hits 978
  banked: 0 DOBs so far
  ...1200/1303  hits 1175
  banked: 0 DOBs so far
  ufcstats filled 0 DOBs, 1195 stances
wikidata rows: 20686 unambiguous fighter names
ESPN search pass over 124 remaining names
  ...100/124  espn hits 0
added: ufcstats 0  wikidata 0  espn 0  stances 1195  rejected as implausible 5
AFTER:  fighters: 2554/2678 with DOB  |  bouts with BOTH ages: 8439/8686 (97.2%)

--- angles tail (last 40 lines) ---
========================================================================
UFC ANGLES 2 — wear and tear beyond chin
baseline already contains Elo + CHIN + AGE (both shipped/validated)
========================================================================
unique bouts: 8686 (1994-03-11..2026-06-14)  both-DOB known: 8439 (97%)

--- FULL SAMPLE (age term diluted: it is 0 wherever a DOB is missing)
baseline (Elo + chin + age): a=1.6 c=-0.06 g=-0.06  TRAIN LL -0.66896
baseline HOLDOUT -0.64843 (n=1771)
KDABS   knockdowns absorbed  b= -0.03  train_win=False  holdout dLL +0.00095  periods 3/3  -> win, not robust
MILEAGE career hours fought  b=  0.05  train_win=True   holdout dLL -0.00322  periods 0/3  -> NULL
ABSORB  sig absorbed / min   b= -0.18  train_win=True   holdout dLL +0.00364  periods 1/3  -> win, not robust
DIVCHG  weight-class move    b=  0.05  train_win=True   holdout dLL -0.00019  periods 1/3  -> NULL

--- AGE-COMPLETE SUBSET (n=8439) — the decisive test
baseline (Elo + chin + age): a=1.6 c=-0.06 g=-0.06  TRAIN LL -0.66844
baseline HOLDOUT -0.64809 (n=1748)
KDABS   knockdowns absorbed  b= -0.03  train_win=False  holdout dLL +0.00094  periods 3/3  -> win, not robust
MILEAGE career hours fought  b=  0.05  train_win=False  holdout dLL -0.00317  periods 0/3  -> NULL
ABSORB  sig absorbed / min   b= -0.18  train_win=True   holdout dLL +0.00378  periods 2/3  -> win, not robust
DIVCHG  weight-class move    b=  0.05  train_win=False  holdout dLL -0.00016  periods 2/3  -> NULL

Ship rule: ROBUST WIN on the AGE-COMPLETE subset. An angle that wins
only on the full sample is most likely re-discovering age.
verdict -> ../experiments/UFC-ANGLES2-VERDICT-WIDENED.md

--- reach angles (batch 4) tail (last 120 lines) ---
UFC ANGLES-4 SELFTEST PASS — ladder pinned, missing reach stays missing, RCHNEW decays and beats raw reach (+0.0198 vs +0.0153), plant recoverable 1/2, leak-free
==============================================================================
UFC ANGLES 4 — reach, and what Elo cannot have already eaten
==============================================================================
unique bouts: 8686 (1994-03-11..2026-06-14)
both DOB known: 8439 (97%)   both reach known: 4006 (46%)

Elo can represent a pure reach DIFFERENCE exactly (r_i - r_j absorbs
beta*reach_i - beta*reach_j), so a null on REACH is expected and is
the control. RCHNEW / RCHENV / RCHAGE are the candidates.

--- DECISIVE SUBSET: age-complete AND reach-complete (n=4006)
baseline (Elo + chin + age + layoff): a=1.2 c=-0.06 g=-0.06 L=-0.18  TRAIN LL -0.66692
baseline HOLDOUT -0.64912 (n=1484)
REACH   reach diff, inches     b= 0.025  train_win=True   holdout dLL +0.00007  periods 1/3  -> win, not robust
APEX    ape index diff         b=  0.05  train_win=True   holdout dLL -0.00214  periods 1/3  -> NULL
RCHNEW  reach where Elo is blind b=  0.15  train_win=True   holdout dLL +0.00037  periods 3/3  -> ROBUST WIN
RCHENV  reach he is used to    b=  0.15  train_win=True   holdout dLL +0.00056  periods 2/3  -> win, not robust
RCHAGE  reach x age            b=  0.06  train_win=False  holdout dLL -0.00085  periods 1/3  -> NULL

--- CEILINGS. ORACLE = what a model that knew the true coefficient
    would buy (a hard bound). FITTED = what this pipeline actually
    recovers when the effect is real (the detection threshold).
    n_rob/n_seed = how often a PLANTED effect survived the ship
    rule. That count, not a magic number, decides 'invisible'.
REACH   reach diff, inches     oracle(b=+0.16) +0.03431 [+0.02959..+0.04004]  fitted +0.03431  plant 3/3  measured +0.00007   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
APEX    ape index diff         oracle(b=+0.32) +0.08118 [+0.07486..+0.08457]  fitted +0.08118  plant 3/3  measured -0.00214   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
RCHNEW  reach where Elo is blind oracle(b=+0.80) +0.02201 [+0.01953..+0.02483]  fitted +0.02201  plant 3/3  measured +0.00037   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
RCHENV  reach he is used to    oracle(b=+0.50) +0.00247 [+0.00127..+0.00311]  fitted +0.00210  plant 2/3  measured +0.00056   DEAD: a planted effect of this size was recovered 2/3, so a real one would have shown
RCHAGE  reach x age            oracle(b=+0.40) +0.03204 [+0.02393..+0.03782]  fitted +0.03204  plant 3/3  measured -0.00085   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown

--- SECOND PASS: raw reach is now IN THE BASELINE. This is the
    decisive reading for RCHNEW / RCHENV / RCHAGE, all three of which
    are correlated with raw reach by construction. An interaction
    judged without its own main effect is the main effect in a wig.
baseline (Elo + chin + age + layoff + REACH): a=1.2 c=-0.06 g=-0.06 L=-0.18 R=0.015  TRAIN LL -0.66649
baseline HOLDOUT -0.64888 (n=1484)
RCHNEW  reach where Elo is blind b=  0.07  train_win=True   holdout dLL +0.00002  periods 2/3  -> win, not robust
RCHENV  reach he is used to    b=  0.15  train_win=True   holdout dLL +0.00054  periods 2/3  -> win, not robust
RCHAGE  reach x age            b=  0.06  train_win=False  holdout dLL -0.00105  periods 1/3  -> NULL

--- CEILINGS. ORACLE = what a model that knew the true coefficient
    would buy (a hard bound). FITTED = what this pipeline actually
    recovers when the effect is real (the detection threshold).
    n_rob/n_seed = how often a PLANTED effect survived the ship
    rule. That count, not a magic number, decides 'invisible'.
RCHNEW  reach where Elo is blind oracle(b=+0.80) +0.00965 [+0.00761..+0.01224]  fitted +0.01025  plant 3/3  measured +0.00002   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
RCHENV  reach he is used to    oracle(b=+0.50) +0.00274 [+0.00183..+0.00361]  fitted +0.00247  plant 1/3  measured +0.00054   STILL CANNOT BE SEEN - do not bury (a planted effect was itself only recovered 1/3)
RCHAGE  reach x age            oracle(b=+0.40) +0.02973 [+0.01980..+0.03679]  fitted +0.02973  plant 3/3  measured -0.00105   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown

Ship rule: ROBUST WIN in the SECOND PASS, and a measured gain at or
above the FITTED threshold while under the ORACLE bound.
verdict -> ../experiments/UFC-ANGLES4-VERDICT.md
