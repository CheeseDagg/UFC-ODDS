==============================================================================
UFC ANGLES 5 — stance, and the one direction Elo cannot represent
==============================================================================
unique bouts: 8686 (1994-03-11..2026-06-14)
both DOB known: 8439 (97%)   both stances known: 7108 (82%)
HOLDOUT both stances known: 1626/1771 (91.8%) — round 7 had this at 1.0%

Elo can represent 1(i=S) - 1(j=S) and 1(i=W) - 1(j=W) EXACTLY, so
SPMAIN and SWMAIN are controls and a null on either is expected.
CYCLE is the component orthogonal to both — the failure of
M(O,W) = M(O,S) + M(S,W) — and no Elo rating can hold it.

--- DECISIVE SUBSET: age-complete AND stance-complete (n=7108)
baseline (Elo + chin + age + layoff): a=1.6 c=-0.06 g=-0.06 L=-0.05  TRAIN LL -0.66928
baseline HOLDOUT -0.65044 (n=1626)
SPMAIN  southpaw indicator [ABSORBABLE]  b=  0.07  train_win=True   holdout dLL -0.00012  periods 2/3  -> NULL
SWMAIN  switch indicator [ABSORBABLE]    b= -0.07  train_win=False  holdout dLL -0.00040  periods 0/3  -> NULL
CYCLE   O>S>W>O, orthogonal to Elo       b= -0.07  train_win=True   holdout dLL +0.00026  periods 2/3  -> win, not robust
SPFAM   he has not seen that look        b=   0.2  train_win=True   holdout dLL +0.00011  periods 1/3  -> win, not robust
SPNEW   stance where Elo is blind        b=   0.2  train_win=True   holdout dLL -0.00064  periods 0/3  -> NULL
XSTNC   cross-stance x Elo gap           b= -0.18  train_win=False  holdout dLL +0.00009  periods 2/3  -> win, not robust

--- CEILINGS. ORACLE = what a model that knew the true coefficient
    would buy (a hard bound). FITTED = what this pipeline actually
    recovers when the effect is real. n_rob/n_seed = how often a
    PLANTED effect survived the ship rule; that count, not a magic
    number, is what decides 'invisible' from 'dead'.
SPMAIN  southpaw indicator [ABSORBABLE]  oracle(b=+0.60) +0.01351 [+0.01223..+0.01584]  fitted +0.01351  plant 3/3  measured -0.00012   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
SWMAIN  switch indicator [ABSORBABLE]    oracle(b=-0.60) +0.00712 [+0.00340..+0.01225]  fitted +0.00712  plant 3/3  measured -0.00040   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
CYCLE   O>S>W>O, orthogonal to Elo       oracle(b=-0.60) +0.01818 [+0.01754..+0.01889]  fitted +0.01818  plant 3/3  measured +0.00026   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
SPFAM   he has not seen that look        oracle(b=+0.90) +0.01101 [+0.00714..+0.01315]  fitted +0.01101  plant 3/3  measured +0.00011   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
SPNEW   stance where Elo is blind        oracle(b=+0.90) +0.00892 [+0.00734..+0.01079]  fitted +0.00892  plant 1/3  measured -0.00064   STILL CANNOT BE SEEN - do not bury (a planted effect was itself only recovered 1/3)
XSTNC   cross-stance x Elo gap             (plant b=-1.40 absorbed by the baseline, oracle -0.00038 — stepping down)
XSTNC   cross-stance x Elo gap             (plant b=-1.00 absorbed by the baseline, oracle -0.00056 — stepping down)
XSTNC   cross-stance x Elo gap           oracle(b=-0.60) +0.00007 [-0.00155..+0.00101]  fitted +0.00060  plant 0/3  measured +0.00009   measured >= ORACLE: noise by construction

--- SECOND PASS: the two ABSORBABLE indicators are now IN THE
    BASELINE. SPNEW and SPFAM need this, because a term built on the
    southpaw indicator will impersonate the indicator itself if the
    indicator is not already spoken for. CYCLE is orthogonal to both
    by construction, so its verdict should barely move — if it moves
    a lot, the orthogonality claim is wrong and nothing here holds.
baseline (Elo + chin + age + layoff + STANCE INDICATORS): a=1.6 c=-0.06 g=-0.06 L=-0.05  SP=0.1 SW=0.0  TRAIN LL -0.66899
baseline HOLDOUT -0.65071 (n=1626)
CYCLE   O>S>W>O, orthogonal to Elo       b= -0.07  train_win=False  holdout dLL -0.00013  periods 1/3  -> NULL
SPFAM   he has not seen that look        b=   0.1  train_win=True   holdout dLL -0.00003  periods 1/3  -> NULL
SPNEW   stance where Elo is blind        b=   0.1  train_win=False  holdout dLL -0.00057  periods 0/3  -> NULL
XSTNC   cross-stance x Elo gap           b= -0.18  train_win=False  holdout dLL +0.00010  periods 2/3  -> win, not robust

--- CEILINGS. ORACLE = what a model that knew the true coefficient
    would buy (a hard bound). FITTED = what this pipeline actually
    recovers when the effect is real. n_rob/n_seed = how often a
    PLANTED effect survived the ship rule; that count, not a magic
    number, is what decides 'invisible' from 'dead'.
CYCLE   O>S>W>O, orthogonal to Elo       oracle(b=-0.60) +0.00868 [+0.00698..+0.01040]  fitted +0.00919  plant 3/3  measured -0.00013   DEAD: a planted effect of this size was recovered 3/3, so a real one would have shown
SPFAM   he has not seen that look        oracle(b=+0.90) +0.00420 [+0.00061..+0.00675]  fitted +0.00458  plant 2/3  measured -0.00003   DEAD: a planted effect of this size was recovered 2/3, so a real one would have shown
SPNEW   stance where Elo is blind        oracle(b=+0.90) +0.00259 [+0.00099..+0.00452]  fitted +0.00318  plant 1/3  measured -0.00057   STILL CANNOT BE SEEN - do not bury (a planted effect was itself only recovered 1/3)
XSTNC   cross-stance x Elo gap             (plant b=-1.40 absorbed by the baseline, oracle -0.00008 — stepping down)
XSTNC   cross-stance x Elo gap             (plant b=-1.00 absorbed by the baseline, oracle -0.00023 — stepping down)
XSTNC   cross-stance x Elo gap             (plant b=-0.60 absorbed by the baseline, oracle -0.00037 — stepping down)
XSTNC   cross-stance x Elo gap             (plant b=-0.35 absorbed by the baseline, oracle -0.00013 — stepping down)
XSTNC   cross-stance x Elo gap           oracle(b=-0.35) -0.00013 [-0.00121..+0.00054]  fitted +0.00052  plant 0/3  measured +0.00010   PROBE UNINFORMATIVE: the oracle came out -0.00013, i.e. the refit baseline absorbed the planted effect. Plant weaker, or accept that this term is not separable from the baseline by this construction — do NOT read a verdict off this line

Ship rule: ROBUST WIN in the SECOND PASS, and a measured gain at or
above the FITTED threshold while under the ORACLE bound.
