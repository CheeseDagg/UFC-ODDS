========================================================================
UFC ANGLES 2 — wear and tear beyond chin
baseline already contains Elo + CHIN + AGE (both shipped/validated)
========================================================================
unique bouts: 8686 (1994-03-11..2026-06-14)  both-DOB known: 4223 (49%)

--- FULL SAMPLE (age term diluted: it is 0 wherever a DOB is missing)
baseline (Elo + chin + age): a=1.6 c=-0.06 g=-0.06  TRAIN LL -0.67202
baseline HOLDOUT -0.65011 (n=1771)
KDABS   knockdowns absorbed  b= -0.03  train_win=True   holdout dLL +0.00114  periods 3/3  -> ROBUST WIN
MILEAGE career hours fought  b= -0.05  train_win=False  holdout dLL +0.00208  periods 3/3  -> win, not robust
ABSORB  sig absorbed / min   b= -0.18  train_win=True   holdout dLL +0.00380  periods 1/3  -> win, not robust
DIVCHG  weight-class move    b=  0.05  train_win=True   holdout dLL -0.00019  periods 1/3  -> NULL

--- AGE-COMPLETE SUBSET (n=4223) — the decisive test
baseline (Elo + chin + age): a=1.6 c=-0.12 g=-0.06  TRAIN LL -0.66698
baseline HOLDOUT -0.64830 (n=1491)
KDABS   knockdowns absorbed  b= -0.03  train_win=True   holdout dLL +0.00015  periods 1/3  -> win, not robust
MILEAGE career hours fought  b= -0.05  train_win=False  holdout dLL +0.00137  periods 2/3  -> win, not robust
ABSORB  sig absorbed / min   b=  -0.1  train_win=True   holdout dLL +0.00137  periods 1/3  -> win, not robust
DIVCHG  weight-class move    b=   0.1  train_win=True   holdout dLL -0.00063  periods 1/3  -> NULL

Ship rule: ROBUST WIN on the AGE-COMPLETE subset. An angle that wins
only on the full sample is most likely re-discovering age.
