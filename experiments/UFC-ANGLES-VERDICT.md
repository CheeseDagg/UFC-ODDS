======================================================================
UFC ANGLES — chin decay + streak momentum vs walk-forward Elo
======================================================================
baseline Elo-only: a=1.6  TRAIN LL -0.68153  HOLDOUT -0.67842 (n=1771)
CHIN (KO-losses diff)    b=-0.12  train_win=True  holdout dLL +0.00885  periods 3/3  -> ROBUST WIN
STREAK (momentum diff)   b=0.03  train_win=True  holdout dLL +0.00328  periods 3/3  -> ROBUST WIN
Ship rule: ROBUST WIN only (train win + holdout win + 3/3 periods).
