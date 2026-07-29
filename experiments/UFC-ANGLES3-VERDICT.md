========================================================================
UFC ANGLES 3 — style and schedule, with power ceilings
baseline: Elo + chin + AGE + LAYOFF (layoff is in because LAYAGE is
an interaction, and an interaction without its main effect is a lie)
========================================================================
unique bouts: 8686 (1994-03-11..2026-06-14)  both-DOB known: 8439 (97%)

--- FULL SAMPLE (age and the interaction are 0 wherever a DOB is missing)
baseline (Elo + chin + age + layoff): a=1.6 c=-0.06 g=-0.06 L=-0.05  TRAIN LL -0.66890
baseline HOLDOUT -0.64776 (n=1771)
KOPOW   KO share of his wins b= -0.15  train_win=False  holdout dLL -0.00032  periods 0/3  -> NULL
LAYAGE  layoff x age       b= -0.08  train_win=True   holdout dLL +0.00176  periods 3/3  -> ROBUST WIN
PACE    sig landed / min   b=  0.05  train_win=False  holdout dLL +0.00020  periods 2/3  -> win, not robust
ACTIV   bouts last 365d    b=   0.1  train_win=True   holdout dLL +0.00077  periods 3/3  -> ROBUST WIN

--- POWER CEILINGS (outcomes re-rolled so the angle IS true at the
    listed strength; the most any model could buy on this panel)
KOPOW   KO share of his wins oracle(b=-1.20) +0.00194 [+0.00009..+0.00317]  fitted +0.00194  plant recovered 1/3  measured -0.00032
                             -> STILL CANNOT BE SEEN - do not bury (a planted effect was itself only recovered 1/3)
LAYAGE  layoff x age         (plant b=-0.40 absorbed by the baseline, oracle -0.00523 — stepping down)
LAYAGE  layoff x age         (plant b=-0.25 absorbed by the baseline, oracle -0.00180 — stepping down)
LAYAGE  layoff x age         (plant b=-0.15 absorbed by the baseline, oracle -0.00093 — stepping down)
LAYAGE  layoff x age         (plant b=-0.08 absorbed by the baseline, oracle -0.00027 — stepping down)
LAYAGE  layoff x age       oracle(b=-0.08) -0.00027 [-0.00090..+0.00036]  fitted -0.00037  plant recovered 0/3  measured +0.00176
                             -> PROBE UNINFORMATIVE: the oracle came out -0.00027, i.e. the refit baseline absorbed the planted effect. Plant weaker, or accept that this term is not separable from the baseline by this construction — do NOT read a verdict off this line
PACE    sig landed / min   oracle(b=+0.35) +0.02062 [+0.01743..+0.02479]  fitted +0.02062  plant recovered 3/3  measured +0.00020
                             -> DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
ACTIV   bouts last 365d    oracle(b=+0.30) +0.00089 [-0.00077..+0.00238]  fitted +0.00160  plant recovered 1/3  measured +0.00077
                             -> won but sits inside the oracle's own seed spread: UNPROVEN, needs a placebo

--- AGE-COMPLETE SUBSET (n=8439) — the decisive test
baseline (Elo + chin + age + layoff): a=1.6 c=-0.06 g=-0.06 L=-0.05  TRAIN LL -0.66837
baseline HOLDOUT -0.64746 (n=1748)
KOPOW   KO share of his wins b= -0.15  train_win=False  holdout dLL -0.00034  periods 0/3  -> NULL
LAYAGE  layoff x age       b= -0.08  train_win=True   holdout dLL +0.00178  periods 3/3  -> ROBUST WIN
PACE    sig landed / min   b=  0.05  train_win=False  holdout dLL +0.00020  periods 2/3  -> win, not robust
ACTIV   bouts last 365d    b=   0.1  train_win=True   holdout dLL +0.00063  periods 3/3  -> ROBUST WIN

--- POWER CEILINGS (outcomes re-rolled so the angle IS true at the
    listed strength; the most any model could buy on this panel)
KOPOW   KO share of his wins oracle(b=-1.20) +0.00424 [+0.00016..+0.00668]  fitted +0.00424  plant recovered 2/3  measured -0.00034
                             -> DEAD: a planted effect of this size was recovered 2/3, so a real one would have shown
LAYAGE  layoff x age         (plant b=-0.40 absorbed by the baseline, oracle -0.00394 — stepping down)
LAYAGE  layoff x age         (plant b=-0.25 absorbed by the baseline, oracle -0.00209 — stepping down)
LAYAGE  layoff x age         (plant b=-0.15 absorbed by the baseline, oracle -0.00167 — stepping down)
LAYAGE  layoff x age         (plant b=-0.08 absorbed by the baseline, oracle -0.00031 — stepping down)
LAYAGE  layoff x age       oracle(b=-0.08) -0.00031 [-0.00038..-0.00024]  fitted -0.00062  plant recovered 0/3  measured +0.00178
                             -> PROBE UNINFORMATIVE: the oracle came out -0.00031, i.e. the refit baseline absorbed the planted effect. Plant weaker, or accept that this term is not separable from the baseline by this construction — do NOT read a verdict off this line
PACE    sig landed / min   oracle(b=+0.35) +0.02067 [+0.01672..+0.02297]  fitted +0.02067  plant recovered 3/3  measured +0.00020
                             -> DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
ACTIV   bouts last 365d    oracle(b=+0.30) +0.00317 [-0.00260..+0.00653]  fitted +0.00480  plant recovered 2/3  measured +0.00063
                             -> won but sits inside the oracle's own seed spread: UNPROVEN, needs a placebo

Ship rule: ROBUST WIN on the AGE-COMPLETE subset, AND a measured gain
well under its own power ceiling. A result at or above its ceiling is
noise by construction, however many periods it wins.
