========================================================================
UFC ANGLES 2 — wear and tear beyond chin
baseline already contains Elo + CHIN + AGE (both shipped/validated)
========================================================================
unique bouts: 8686 (1994-03-11..2026-06-14)  both-DOB known: 4041 (47%)

--- FULL SAMPLE (age term diluted: it is 0 wherever a DOB is missing)
baseline (Elo + chin + age): a=1.6 c=-0.06 g=-0.06  TRAIN LL -0.67261
baseline HOLDOUT -0.65024 (n=1771)
KDABS   knockdowns absorbed  b= -0.03  train_win=True   holdout dLL +0.00114  periods 3/3  -> ROBUST WIN
MILEAGE career hours fought  b= -0.05  train_win=False  holdout dLL +0.00208  periods 3/3  -> win, not robust
ABSORB  sig absorbed / min   b= -0.18  train_win=True   holdout dLL +0.00381  periods 1/3  -> win, not robust
DIVCHG  weight-class move    b=  0.05  train_win=True   holdout dLL -0.00019  periods 1/3  -> NULL

--- AGE-COMPLETE SUBSET (n=4041) — the decisive test
baseline (Elo + chin + age): a=1.6 c=-0.12 g=-0.06  TRAIN LL -0.66812
baseline HOLDOUT -0.64853 (n=1486)
KDABS   knockdowns absorbed  b= -0.03  train_win=True   holdout dLL +0.00015  periods 1/3  -> win, not robust
MILEAGE career hours fought  b= -0.05  train_win=False  holdout dLL +0.00136  periods 2/3  -> win, not robust
ABSORB  sig absorbed / min   b=  -0.1  train_win=True   holdout dLL +0.00136  periods 1/3  -> win, not robust
DIVCHG  weight-class move    b=   0.1  train_win=True   holdout dLL -0.00064  periods 1/3  -> NULL

Ship rule: ROBUST WIN on the AGE-COMPLETE subset. An angle that wins
only on the full sample is most likely re-discovering age.

------------------------------------------------------------------------
WHAT THIS COSTS US, AND THE ONE FIX WORTH DOING

The age control is only half-strength. fighter_meta_cache.json holds 1,637
fighters (1,622 with a DOB); fighter_bouts.csv has 2,678 distinct names. So
4,041 of 8,686 bouts carry both ages and the rest carry none. Every angle
tested from here is measured against a baseline that is age-blind on more
than half the sample, which is exactly the hole that made three of these four
angles read as wins on the first pass.

Widening the DOB pull is worth more than the next four angles combined. It is
not a modelling idea, it is the floor everything else stands on.
