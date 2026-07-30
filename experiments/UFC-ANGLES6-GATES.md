==============================================================================
UFC ANGLES 6 — GATES 2-4, second-pass baseline (EXPER carried)
==============================================================================
decisive subset n=6283   candidates: mil_d, kdabs_d
second-pass baseline: a=1.6 c=-0.06 g=-0.06 L=-0.05  extra=(('exp_d', -0.03),)  HOLDOUT -0.64407 (n=1395)

--- MILEAGE strikes absorbed, hundreds   b=-0.03  holdout dLL +0.00322  periods 3/3  train_win=True
  GATE 2 SHUFFLED PLACEBO
  WITHIN-YEAR x120: reached the real gain   0/120  robust win   2/120  JOINT   0/120  p=0.0083
    (the two marginals disagree — which is exactly why the joint count is the one reported as p)
  GLOBAL      x120: reached the real gain   0/120  robust win   0/120  JOINT   0/120  p=0.0083

  GATE 4 SHAPE mil_d (fitted b=-0.03, holdout n=1395): win rate by quintile of the term. A negative b claims this column DESCENDS.
    q1  mil_d in [-8.00,-2.68]  n= 279  A wins  59.5%
    q2  mil_d in [-2.66,-0.61]  n= 279  A wins  54.8%
    q3  mil_d in [-0.60,+0.68]  n= 279  A wins  49.1%
    q4  mil_d in [+0.68,+3.11]  n= 279  A wins  43.7%
    q5  mil_d in [+3.11,+8.00]  n= 279  A wins  36.2%
    -> ordered as claimed

--- KDABS   knockdowns absorbed   b=-0.06  holdout dLL +0.00107  periods 2/3  train_win=False
  GATE 2 SHUFFLED PLACEBO
  WITHIN-YEAR x120: reached the real gain   5/120  robust win   0/120  JOINT   0/120  p=0.0083
    (the two marginals disagree — which is exactly why the joint count is the one reported as p)
  GLOBAL      x120: reached the real gain   6/120  robust win   1/120  JOINT   0/120  p=0.0083

  GATE 4 SHAPE kdabs_d (fitted b=-0.06, holdout n=1395): win rate by quintile of the term. A negative b claims this column DESCENDS.
    q1  kdabs_d in [-6.00,-1.00]  n= 279  A wins  49.5%
    q2  kdabs_d in [-1.00,+0.00]  n= 279  A wins  47.0%
    q3  kdabs_d in [+0.00,+0.00]  n= 279  A wins  53.4%
    q4  kdabs_d in [+0.00,+2.00]  n= 279  A wins  53.0%
    q5  kdabs_d in [+2.00,+6.00]  n= 279  A wins  40.5%
    -> NOT ordered — the sign is coming from a tail, not from a gradient

--- GATE 3 CROSS-SEASON (each era refits the whole pipeline)

EARLY  train 2012-2016, hold 2017-2019  (holdout n=1090)  base a=1.6 g=-0.06 L=0.1
  MILEAGE strikes absorbed, hundreds b= -0.03 dLL +0.00082 periods 2/3 -> win, not robust
  KDABS   knockdowns absorbed b= -0.06 dLL +0.00037 periods 2/3 -> win, not robust

MID    train 2012-2019, hold 2020-2022  (holdout n=1159)  base a=1.6 g=-0.06 L=0.05
  MILEAGE strikes absorbed, hundreds b= -0.03 dLL -0.00100 periods 1/3 -> NULL
  KDABS   knockdowns absorbed b= -0.06 dLL -0.00290 periods 0/3 -> NULL

LATE   train 2012-2022, hold 2023-2026  (holdout n=1395)  base a=1.6 g=-0.06 L=-0.05
  MILEAGE strikes absorbed, hundreds b= -0.03 dLL +0.00322 periods 3/3 -> ROBUST WIN
  KDABS   knockdowns absorbed b= -0.06 dLL +0.00107 periods 2/3 -> win, not robust
