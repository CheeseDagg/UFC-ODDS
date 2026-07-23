Loading /home/runner/work/UFC-ODDS/UFC-ODDS/Github/data/fighter_bouts.csv ...
Deduped 17372 mirrored rows -> 8686 unique fights (1994-03-11 .. 2026-06-14).
Loaded 1637 cached DOB/reach records.
========================================================================
WALK-FORWARD  (train = fights before 2022-03-26, holdout = on/after)
  total fights: 8686   train: 6514   holdout: 2172
------------------------------------------------------------------------
REFERENCE (holdout Brier, ALL holdout fights):
  pure Elo                 : 0.2448
  Elo + feature blend      : 0.2393  (baseline)
------------------------------------------------------------------------
AGE/REACH COVERAGE: 4006/8686 fights have DOB+reach for both corners (46.1%)
  matched train: 2238   matched holdout: 1768
------------------------------------------------------------------------
HOLDOUT Brier on matched subset (lower = better):
  baseline (Elo+blend)         : 0.2395
  + age only                   : 0.2299  (-0.0096)
  + reach only                 : 0.2396  (+0.0001)
  + age + reach (treatment)    : 0.2300  (-0.0095)
------------------------------------------------------------------------
PER-PERIOD holdout Brier (baseline -> +age+reach):
  2022-2023  n=690    0.2440 -> 0.2324  (-0.0117)  improved
  2024-2025  n=888    0.2368 -> 0.2282  (-0.0086)  improved
  2026-2026  n=190    0.2355 -> 0.2298  (-0.0057)  improved
========================================================================
VERDICT
------------------------------------------------------------------------
  Baseline holdout Brier (matched)   : 0.2395
  +age+reach holdout Brier (matched) : 0.2300
  Brier improvement                  : -0.0095 (negative = better)
  Bootstrap 95% CI on delta          : [-0.0129, -0.0060]
  P(age+reach helps)                 : 1.00
  Periods improved                   : 3/3
  Age-curve shape                    : peak age ~= 19.0  [inverted-U (peaks then declines)]
------------------------------------------------------------------------
  ==> ROBUST YES: age and/or reach improve holdout accuracy by
      0.0095 Brier, consistently across periods.
========================================================================
