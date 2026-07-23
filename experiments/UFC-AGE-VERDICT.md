Loading /home/runner/work/UFC-ODDS/UFC-ODDS/Github/data/fighter_bouts.csv ...
Deduped 17372 mirrored rows -> 8686 unique fights (1994-03-11 .. 2026-06-14).
No fighter_meta_cache.json -- attempting DOB/reach pull ...
Discovered 0 fighter detail pages.
Pull complete: 0 total fighter meta records (0 new).
========================================================================
WALK-FORWARD  (train = fights before 2022-03-26, holdout = on/after)
  total fights: 8686   train: 6514   holdout: 2172
------------------------------------------------------------------------
REFERENCE (holdout Brier, ALL holdout fights):
  pure Elo                 : 0.2448
  Elo + feature blend      : 0.2393  (baseline)
========================================================================
VERDICT: age/reach test PENDING -- no DOB/reach available in this
run. The leak-free baseline reproduced (Elo blend beats pure Elo:
        -0.0055 Brier). To test AGE + REACH, populate the cache by
        running `--pull` on GitHub Actions, then re-run.
========================================================================
