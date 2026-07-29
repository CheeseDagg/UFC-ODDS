# DOB backfill run status

run    30477147995  attempt 7
sha    30f0a6ad57538f9d540398df62ce91ddf76891d2
when   2026-07-29T18:01:05Z

step outcomes (failure here is the whole point of this file):
  selftest  success
  before    success
  backfill  success
  after     success
  angles    success

coverage BEFORE:
  fighters: 1433/2678 with DOB  |  bouts with BOTH ages: 4223/8686 (48.6%)
coverage AFTER:
  fighters: 2554/2678 with DOB  |  bouts with BOTH ages: 8439/8686 (97.2%)

--- backfill tail (last 200 lines) ---
missing DOB for 1245 of 2678 fighters
BEFORE: fighters: 1433/2678 with DOB  |  bouts with BOTH ages: 4223/8686 (48.6%)
ufcstats pass
  challenge solved: nonce=9a2244d25fb38201 n=121 -> /__c, 1 cookie(s) held
  warmed cookie jar: 29869 chars, 1 cookie(s) held, still challenged=False
  ufcstats index: 4575 fighters enumerated
  1209 of them are names we are missing — fetching details
  ...200/1209  hits 196
  banked: 183 DOBs so far
  ...400/1209  hits 391
  banked: 366 DOBs so far
  ...600/1209  hits 583
  banked: 547 DOBs so far
  ...800/1209  hits 779
  banked: 728 DOBs so far
  ...1000/1209  hits 978
  banked: 919 DOBs so far
  ...1200/1209  hits 1177
  banked: 1112 DOBs so far
  ufcstats filled 1121 DOBs, 1102 stances
wikidata rows: 20686 unambiguous fighter names
ESPN search pass over 124 remaining names
  ...100/124  espn hits 0
added: ufcstats 1121  wikidata 0  espn 0  stances 1102  rejected as implausible 6
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
