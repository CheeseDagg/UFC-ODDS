========================================================================
UFC ANGLES 3 — style and schedule, with power ceilings
baseline: Elo + chin + AGE + LAYOFF (layoff is in because LAYAGE is
an interaction, and an interaction without its main effect is a lie)
========================================================================
unique bouts: 8686 (1994-03-11..2026-06-14)  both-DOB known: 4223 (49%)

--- FULL SAMPLE (age and the interaction are 0 wherever a DOB is missing)
baseline (Elo + chin + age + layoff): a=1.6 c=-0.06 g=-0.06 L=-0.1  TRAIN LL -0.67183
baseline HOLDOUT -0.64885 (n=1771)
KOPOW   KO share of his wins b= -0.15  train_win=False  holdout dLL -0.00032  periods 0/3  -> NULL
LAYAGE  layoff x age       b= -0.25  train_win=True   holdout dLL +0.00297  periods 3/3  -> ROBUST WIN
PACE    sig landed / min   b=  0.05  train_win=True   holdout dLL +0.00019  periods 2/3  -> win, not robust
ACTIV   bouts last 365d    b=   0.1  train_win=True   holdout dLL +0.00045  periods 3/3  -> ROBUST WIN

--- POWER CEILINGS (outcomes re-rolled so the angle IS true at the
    listed strength; the most any model could buy on this panel)
KOPOW   KO share of his wins ceiling(b=-1.20) +0.00248 [+0.00034..+0.00384]  measured -0.00032   CANNOT BE SEEN AT THIS SAMPLE - do not bury
LAYAGE  layoff x age       ceiling(b=-0.40) +0.00386 [+0.00056..+0.00831]  measured +0.00297   inside the ceiling's own seed spread: unproven
PACE    sig landed / min   ceiling(b=+0.35) +0.02137 [+0.01702..+0.02624]  measured +0.00019   dead: the panel could see it and did not
ACTIV   bouts last 365d    ceiling(b=+0.30) +0.00559 [+0.00282..+0.00950]  measured +0.00045   LIVE: robust win at 8% of ceiling

--- AGE-COMPLETE SUBSET (n=4223) — the decisive test
baseline (Elo + chin + age + layoff): a=1.6 c=-0.12 g=-0.06 L=-0.18  TRAIN LL -0.66592
baseline HOLDOUT -0.64713 (n=1491)
KOPOW   KO share of his wins b=  -0.6  train_win=True   holdout dLL -0.00240  periods 0/3  -> NULL
LAYAGE  layoff x age       b= -0.15  train_win=True   holdout dLL +0.00213  periods 3/3  -> ROBUST WIN
PACE    sig landed / min   b=  0.05  train_win=True   holdout dLL +0.00031  periods 2/3  -> win, not robust
ACTIV   bouts last 365d    b=   0.1  train_win=True   holdout dLL -0.00061  periods 0/3  -> NULL

--- POWER CEILINGS (outcomes re-rolled so the angle IS true at the
    listed strength; the most any model could buy on this panel)
KOPOW   KO share of his wins ceiling(b=-1.20) +0.00416 [+0.00271..+0.00836]  measured -0.00240   dead: the panel could see it and did not
LAYAGE  layoff x age       ceiling(b=-0.40) +0.00645 [+0.00332..+0.01016]  measured +0.00213   LIVE: robust win at 33% of ceiling
PACE    sig landed / min   ceiling(b=+0.35) +0.02040 [+0.01130..+0.02600]  measured +0.00031   dead: the panel could see it and did not
ACTIV   bouts last 365d    ceiling(b=+0.30) +0.01162 [+0.00646..+0.01806]  measured -0.00061   dead: the panel could see it and did not

Ship rule: ROBUST WIN on the AGE-COMPLETE subset, AND a measured gain
well under its own power ceiling. A result at or above its ceiling is
noise by construction, however many periods it wins.
