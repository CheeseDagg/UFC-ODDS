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
