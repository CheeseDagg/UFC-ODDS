========================================================================
LAYAGE GATE — shuffled placebo + shape, on the AGE-COMPLETE subset
========================================================================
REAL  n=4223  b=-0.15  holdout dLL +0.00213  periods 3/3  robust=True

--- GATE 2: SHUFFLED PLACEBO (24 trials, full pipeline each)
ship rule fired on noise: 0/24 (0%)
noise dLL >= real (+0.00213): 0/24 (0%)  <- this is the p-value
noise dLL  min -0.00619  median -0.00063  max +0.00135

--- GATE 3: SHAPE (the effect must live where its inputs live)
long-gap bouts (|lay_d|>0.5y)      n=  720  b=-0.08  dLL +0.00413  3/3
even-turnaround bouts (<=0.5y)     n= 3503  b=-0.25  dLL +0.00120  2/3
has a fighter 33+                  n= 2162  b=-0.15  dLL +0.00155  3/3
both fighters under 31             n= 1174  b=-0.15  dLL +0.00088  2/3

--- pivot sensitivity (a grid artifact dies when the pivot moves;
    and the high pivots are a DEGENERACY PROBE: as the pivot rises
    past every fighter's age, (age-pivot) is negative for everyone
    and the interaction collapses into a rescaled LAYOFF main effect.
    If dLL kept climbing out to 60 the 'interaction' would really be
    a repair to the baseline's layoff term. It must peak in the
    middle and decay, and the peak must sit at a plausible age.
    NOTE: the peak is NOT adopted as the pivot — these are holdout
    numbers, and moving a constant to the best one of them is how a
    shape check turns into a leak. The shipped pivot stays at 30.
pivot   27   b=-0.15  dLL +0.00164  periods 3/3  robust=True
pivot   29   b=-0.15  dLL +0.00202  periods 3/3  robust=True
pivot   30   b=-0.15  dLL +0.00213  periods 3/3  robust=True
pivot   31   b=-0.15  dLL +0.00220  periods 3/3  robust=True
pivot   33   b=-0.15  dLL +0.00221  periods 3/3  robust=True
pivot   36   b=-0.15  dLL +0.00195  periods 3/3  robust=True
pivot   40   b=-0.08  dLL +0.00107  periods 3/3  robust=True
pivot   45   b=-0.08  dLL +0.00042  periods 2/3  robust=False
pivot   50   b=-0.08  dLL -0.00033  periods 1/3  robust=False
pivot   60   b=-0.08  dLL -0.00171  periods 1/3  robust=False
