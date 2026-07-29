#!/usr/bin/env python3
"""
ufc_blend_predict.py — parallel A/B ledger: production model vs research blend.

Production logs its win-prob per bout to data/ufc_predictions.csv (via
ufc_grade.log_card inside build_site.py) and settles results into
data/ufc_graded.csv. A walk-forward-validated RESEARCH model (online Elo +
EMA form features + age curve; see ufc_age_experiment.py) beat a pure Elo
baseline out-of-sample. This script logs THAT model's predictions for the
same upcoming card IN PARALLEL — to data/ufc_predictions_blend.csv /
data/ufc_graded_blend.csv — so the live ledger grades production vs research
head-to-head on identical bouts with identical grading rules.

THE RESEARCH MODEL (validated components only):
  * online Elo (K=96, scale=450, base 1500) over data/fighter_bouts.csv
    (mirrored rows deduped, chronological);
  * per-fighter EMA (alpha=0.4, PRIOR fights only) of: strike margin
    ((sig_l - sig_l_opp)/max(mins,1)), grappling margin ((td_l - td_l_opp)
    + ctrl/60), control minutes (ctrl/60), won, and submission attempts
    (the `sub` column — a validated win);
  * fights-to-date and log1p(days since last fight);
  * AGE at fight date from DOB (fighter_meta_cache.json): age diff and
    (age-28)^2 diff — the validated big win. Reach was a null result and is
    deliberately EXCLUDED.

TWO logistics are fit on ALL completed fights (this is live prediction and
every feature is as-of the fight date, so there is no leakage):
  * model A includes the age terms, fit on fights where BOTH corners have a
    DOB in the meta cache;
  * model B excludes age (fallback when either DOB is missing).
Both standardize on their fit set and are intercept-free via the mirror
+/-X trick (each fight enters as (x, y) and (-x, 1-y), so column means are
exactly 0 and p(f1) + p(f2) == 1 by construction). L2 uses C ~= 0.25.

RUNTIME (default): rebuild state -> fit A/B -> read the upcoming card the
way build_site.py does (odds/parsed_odds.json f1/f2/cons1 + date from
odds/upcoming.csv first row, falling back to today) -> resolve card names to
state names with ufc_grade.resolve (unresolvable bouts skipped) -> log to
the *_blend files by temporarily overriding ufc_grade.PLOG/GRADED
(saved/restored in try/finally) -> settle prior blend logs with
ufc_grade.grade_all -> write output/blend_ab.json comparing the production
ledger's summary with the blend ledger's summary.

--grade-only : skip prediction; just settle prior blend logs + write panel.
--selftest   : offline synthetic end-to-end test (temp dirs; must pass).

main() is FAIL-SOFT for default/--grade-only: any exception prints one line
and exits 0 so the refresh pipeline never breaks. This script NEVER writes
to data/ufc_predictions.csv or data/ufc_graded.csv (the production files).
"""
import os
import re
import sys
import csv
import json
import math
import datetime as dt

try:
    import numpy as np          # needed only for fitting (not for --grade-only)
except Exception:               # pragma: no cover
    np = None

import ufc_grade

HERE = os.path.dirname(os.path.abspath(__file__))
BOUTS_CSV = os.path.join(HERE, "data", "fighter_bouts.csv")
META_CACHE = os.path.join(HERE, "fighter_meta_cache.json")
PARSED_ODDS = os.path.join(HERE, "odds", "parsed_odds.json")
UPCOMING = os.path.join(HERE, "odds", "upcoming.csv")
PLOG_BLEND = os.path.join(HERE, "data", "ufc_predictions_blend.csv")
GRADED_BLEND = os.path.join(HERE, "data", "ufc_graded_blend.csv")
PANEL_JSON = os.path.join(HERE, "output", "blend_ab.json")
PROD_GRADED = ufc_grade.GRADED          # captured at import — read-only use

ELO_K = 96.0
ELO_SCALE = 450.0
ELO_BASE = 1500.0
EMA_ALPHA = 0.4
L2 = 1.0 / 0.25                          # sklearn-style C ~= 0.25
DEBUT_DSL = math.log1p(365.0)            # neutral layoff for debutants

FEATS_B = ["elo", "strike_ema", "grap_ema", "ctrl_ema", "won_ema",
           "sub_ema", "nfights", "dsl", "chin"]
# "chin" = cumulative KO/TKO losses BEFORE this fight. Validated 2026-07-29
# (ufc_angles_experiment): robust win vs Elo-only (+0.0089 LL/bout, 3/3
# periods) AND vs Elo+age (+0.0052, 3/3) — damage accrual is real signal
# beyond age. (Win-streak momentum tested same day: survives Elo-only but
# NOT age-adjusted robustly -> not shipped.)
FEATS_A = FEATS_B + ["age_diff", "age2_diff"]


def norm_name(name):
    """fighter_meta_cache.json key normalization (mirrors ufc_age_experiment)."""
    n = (name or "").strip().lower()
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    n = re.sub(r"\s+", " ", n)
    return n


def _f(row, k):
    try:
        return float(row.get(k) or 0.0)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# walk-forward state (mirrors ufc_age_experiment's leak-free discipline:
# features come from fights STRICTLY BEFORE the one being scored)
# ---------------------------------------------------------------------------

class FighterState:
    __slots__ = ("elo", "n", "last", "ema", "ko_losses")

    def __init__(self):
        self.elo = ELO_BASE
        self.n = 0
        self.last = None                                  # date of last fight
        self.ema = {"strike": None, "grap": None, "ctrl": None,
                    "won": None, "sub": None}
        self.ko_losses = 0


def _fight_vals(row):
    """Per-fight raw values from the fighter's own perspective row."""
    mins = max(_f(row, "secs") / 60.0, 1.0)
    return {
        "strike": (_f(row, "sig_l") - _f(row, "sig_l_opp")) / mins,
        "grap": (_f(row, "td_l") - _f(row, "td_l_opp")) + _f(row, "ctrl") / 60.0,
        "ctrl": _f(row, "ctrl") / 60.0,
        "won": _f(row, "won"),
        "sub": _f(row, "sub"),
    }


def _pre_feats(st, fight_date):
    """Pre-fight per-fighter feature values (prior fights only; neutral
    defaults for debutants so nothing about the current fight leaks in)."""
    e = st.ema
    if st.last is None:
        dsl = DEBUT_DSL
    else:
        dsl = math.log1p(max((fight_date - st.last).days, 0))
    return [
        st.elo,
        0.0 if e["strike"] is None else e["strike"],
        0.0 if e["grap"] is None else e["grap"],
        0.0 if e["ctrl"] is None else e["ctrl"],
        0.5 if e["won"] is None else e["won"],
        0.0 if e["sub"] is None else e["sub"],
        float(st.n),
        dsl,
        float(st.ko_losses),
    ]


def _update_state(st, row, fight_date):
    vals = _fight_vals(row)
    for k, v in vals.items():
        st.ema[k] = v if st.ema[k] is None else (EMA_ALPHA * v +
                                                 (1.0 - EMA_ALPHA) * st.ema[k])
    st.n += 1
    st.last = fight_date
    if _f(row, "lost_by_ko") >= 1.0:
        st.ko_losses += 1


def dedupe_fights(rows):
    """Collapse mirrored rows into one fight each, chronological. Side A is
    the alphabetically-first name (orientation cancels: mirror-trick fit)."""
    by_key = {}
    for r in rows:
        d, a, b = r.get("date"), r.get("fighter"), r.get("opp")
        if not (d and a and b):
            continue
        by_key.setdefault((d, tuple(sorted((a, b)))), {})[a] = r
    fights = []
    for (d, pair), persp in by_key.items():
        if len(persp) != 2:
            continue                                   # missing mirror — skip
        try:
            date = dt.date.fromisoformat(d)
        except ValueError:
            continue
        A, B = pair
        fights.append({"date": date, "A": A, "B": B,
                       "rowA": persp[A], "rowB": persp[B],
                       "yA": int(_f(persp[A], "won"))})
    fights.sort(key=lambda x: (x["date"], x["A"], x["B"]))
    return fights


def load_meta(path):
    """meta cache -> {norm_name: dob_date} (DOB only; reach was a null)."""
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        raw = json.load(f)
    out = {}
    for k, v in raw.items():
        d = v.get("dob") if isinstance(v, dict) else None
        if d:
            try:
                out[k] = dt.date.fromisoformat(d)
            except ValueError:
                pass
    return out


def _age_terms(dob1, dob2, fight_date):
    a1 = (fight_date - dob1).days / 365.25
    a2 = (fight_date - dob2).days / 365.25
    return [a1 - a2, (a1 - 28.0) ** 2 - (a2 - 28.0) ** 2]


def build_state_and_data(bouts_csv, dobs):
    """One chronological pass: emit leak-free training rows, update state.
    Returns (state, XA, yA, XB, yB) — A rows only where both corners have DOB."""
    with open(bouts_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    fights = dedupe_fights(rows)
    state = {}
    XA, ya, XB, yb = [], [], [], []
    for fg in fights:
        A, B = fg["A"], fg["B"]
        sA = state.setdefault(A, FighterState())
        sB = state.setdefault(B, FighterState())
        x = [p - q for p, q in zip(_pre_feats(sA, fg["date"]),
                                   _pre_feats(sB, fg["date"]))]
        XB.append(x)
        yb.append(fg["yA"])
        dA, dB = dobs.get(norm_name(A)), dobs.get(norm_name(B))
        if dA and dB:
            XA.append(x + _age_terms(dA, dB, fg["date"]))
            ya.append(fg["yA"])
        # ---- update AFTER scoring (leak-free) ----
        eA = 1.0 / (1.0 + 10.0 ** ((sB.elo - sA.elo) / ELO_SCALE))
        sA.elo += ELO_K * (fg["yA"] - eA)
        sB.elo += ELO_K * ((1 - fg["yA"]) - (1.0 - eA))
        _update_state(sA, fg["rowA"], fg["date"])
        _update_state(sB, fg["rowB"], fg["date"])
    return state, XA, ya, XB, yb


# ---------------------------------------------------------------------------
# no-intercept logistic via the mirror +/-X trick (numpy GD + L2)
# ---------------------------------------------------------------------------

def fit_mirror_logistic(X, y, l2=L2, iters=3000, lr=0.5):
    """Fit on the mirrored set [(x,y), (-x,1-y)]: column means are exactly 0,
    so standardization is a pure 1/sd scale and p(x) + p(-x) == 1 exactly."""
    if np is None:
        raise RuntimeError("numpy required for fitting")
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim != 2 or len(X) == 0:
        raise ValueError("empty design matrix")
    Xm = np.vstack([X, -X])
    ym = np.concatenate([y, 1.0 - y])
    sd = Xm.std(axis=0)
    sd[sd < 1e-8] = 1.0
    Xs = Xm / sd
    n, d = Xs.shape
    w = np.zeros(d)
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Xs @ w, -35, 35)))
        g = p - ym
        w -= lr * (Xs.T @ g / n + l2 * w / n)

    def predict(x):
        z = float((np.asarray(x, dtype=float) / sd) @ w)
        return 1.0 / (1.0 + math.exp(-max(min(z, 35.0), -35.0)))

    return predict


# ---------------------------------------------------------------------------
# card assembly (mirrors build_site.py) + prediction
# ---------------------------------------------------------------------------

def read_card(parsed_json, upcoming_csv):
    with open(parsed_json) as f:
        card = json.load(f)
    values = list(card.values())
    cdate = ""
    if os.path.exists(upcoming_csv):
        with open(upcoming_csv, newline="") as f:
            u = list(csv.DictReader(f))
        cdate = (u[0].get("date") or "").strip() if u else ""
    if not cdate:
        cdate = dt.date.today().isoformat()
    event = next((v.get("event") for v in values if v.get("event")), "") or "UFC card"
    return event, cdate, values


def predict_card(state, pred_a, pred_b, dobs, values, cdate):
    """-> (bouts for log_card, per-bout detail incl. which model fired)."""
    keys = {ufc_grade.norm(name): name for name in state}
    try:
        fdate = dt.date.fromisoformat(cdate)
    except (ValueError, TypeError):
        fdate = dt.date.today()
    bouts, details = [], []
    STALE_YEARS = 6                        # a namesake guard, not a comeback penalty
    for v in values:
        k1 = ufc_grade.resolve(v.get("f1", ""), keys)
        k2 = ufc_grade.resolve(v.get("f2", ""), keys)
        # NAMESAKE GUARD (the 'Rick Davis 2006' bug): if the resolved history's last
        # fight is >6 years before this card, it is almost certainly a DIFFERENT person
        # with the same name (UFC re-signs almost nobody after 6+ years out). Treat the
        # card fighter as unknown -> bout is skipped rather than priced off a stranger's
        # 20-year-old record.
        for kk in ("k1", "k2"):
            k = locals()[kk]
            if k:
                st = state[keys[k]]
                if st.last is not None and (fdate - st.last).days > STALE_YEARS * 365:
                    if kk == "k1": k1 = None
                    else: k2 = None
        if not k1 or not k2 or k1 == k2:
            continue                       # unknown to the state — skip bout
        n1, n2 = keys[k1], keys[k2]
        x = [p - q for p, q in zip(_pre_feats(state[n1], fdate),
                                   _pre_feats(state[n2], fdate))]
        d1, d2 = dobs.get(norm_name(n1)), dobs.get(norm_name(n2))
        if d1 and d2 and pred_a is not None:
            model = "A"
            p1 = pred_a(x + _age_terms(d1, d2, fdate))
        else:
            model = "B"
            p1 = pred_b(x)
        bouts.append({"f1": v["f1"], "f2": v["f2"], "p1": p1,
                      "q1": v.get("cons1")})
        details.append({"f1": v["f1"], "f2": v["f2"], "p1": p1,
                        "model": model})
    return bouts, details


# ---------------------------------------------------------------------------
# blend ledger I/O — the ONLY place ufc_grade paths are overridden
# ---------------------------------------------------------------------------

def log_and_settle(event, cdate, bouts, plog, graded, bouts_csv,
                   delta_csv, prod_graded, panel_path):
    """Log to the blend files and settle, by temporarily pointing ufc_grade
    at the blend paths (saved/restored in try/finally — production
    ufc_predictions.csv / ufc_graded.csv are never written)."""
    saved = (ufc_grade.PLOG, ufc_grade.GRADED)
    try:
        ufc_grade.PLOG, ufc_grade.GRADED = plog, graded
        ufc_grade.ensure_files()
        n_new = ufc_grade.log_card(event, cdate, bouts) if bouts else 0
        n_settled, panel = ufc_grade.grade_all(bouts_csv, delta_csv=delta_csv)
    finally:
        ufc_grade.PLOG, ufc_grade.GRADED = saved
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "production": ufc_grade.summarize(ufc_grade.load_csv(prod_graded)),
        "blend": panel,
        "n_logged_now": n_new,
        "note": "same bouts, same grading; head-to-head of production p1 "
                "vs research blend",
    }
    os.makedirs(os.path.dirname(panel_path), exist_ok=True)
    with open(panel_path, "w") as f:
        json.dump(out, f, indent=1)
    return n_new, n_settled, out


def run(bouts_csv=BOUTS_CSV, meta_path=META_CACHE, parsed_json=PARSED_ODDS,
        upcoming_csv=UPCOMING, plog=PLOG_BLEND, graded=GRADED_BLEND,
        panel_path=PANEL_JSON, delta_csv=None, prod_graded=None,
        grade_only=False):
    """Full pipeline. delta_csv=None -> ufc_grade's default results_delta.csv.
    Returns a dict of everything the selftest needs to inspect."""
    if prod_graded is None:
        prod_graded = PROD_GRADED
    if grade_only:
        n_new, n_settled, out = log_and_settle(
            "", "", [], plog, graded, bouts_csv, delta_csv, prod_graded,
            panel_path)
        return {"n_logged": n_new, "n_settled": n_settled, "panel": out,
                "details": [], "state": None}
    dobs = load_meta(meta_path)
    state, XA, ya, XB, yb = build_state_and_data(bouts_csv, dobs)
    if not XB:
        raise RuntimeError("no completed fights in %s" % bouts_csv)
    pred_b = fit_mirror_logistic(XB, yb)
    pred_a = fit_mirror_logistic(XA, ya) if len(XA) >= 20 else None
    event, cdate, values = read_card(parsed_json, upcoming_csv)
    bouts, details = predict_card(state, pred_a, pred_b, dobs, values, cdate)
    n_new, n_settled, out = log_and_settle(
        event, cdate, bouts, plog, graded, bouts_csv, delta_csv,
        prod_graded, panel_path)
    return {"n_logged": n_new, "n_settled": n_settled, "panel": out,
            "details": details, "state": state, "pred_a": pred_a,
            "pred_b": pred_b, "dobs": dobs, "event": event, "cdate": cdate,
            "n_fights": len(XB), "n_fights_a": len(XA)}


# ---------------------------------------------------------------------------
# SELFTEST — offline, synthetic, temp dirs; never touches production paths
# ---------------------------------------------------------------------------

def selftest():
    import tempfile
    tmp = tempfile.mkdtemp(prefix="ufc_blend_selftest_")
    today = dt.date.today()
    card_date = (today - dt.timedelta(days=3)).isoformat()

    names = ["Alpha Kick", "Bravo Punch", "Charlie Slam", "Delta Knee",
             "Echo Guard", "Foxtrot Jab", "Golf Elbow", "Hotel Choke"]
    # DOBs for 6 of 8 — Golf Elbow / Hotel Choke deliberately missing
    meta = {}
    for i, nm in enumerate(names[:6]):
        meta[norm_name(nm)] = {"dob": "19%02d-0%d-15" % (88 + i, 1 + i % 9),
                               "reach": None, "height": None, "name": nm}
    meta_path = os.path.join(tmp, "meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f)

    # ~40 synthetic fights (mirrored rows), chronological, seeded outcomes
    import random
    rng = random.Random(7)
    rows = []
    d0 = dt.date(2022, 1, 8)
    n_fights = 0
    for k in range(39):
        i = k % 8
        j = (k * 3 + 1) % 8
        if i == j:
            j = (j + 1) % 8
        a, b = names[i], names[j]
        awin = 1 if rng.random() < (0.5 + 0.04 * (j - i)) else 0
        fd = (d0 + dt.timedelta(days=14 * k)).isoformat()
        sig_a, sig_b = rng.randint(20, 90), rng.randint(20, 90)
        td_a, td_b = rng.randint(0, 4), rng.randint(0, 4)
        ctl_a, ctl_b = rng.randint(0, 300), rng.randint(0, 300)
        sub_a, sub_b = rng.randint(0, 2), rng.randint(0, 2)
        for (fgt, opp, w, sl, so, tl, to, ct, sb) in (
                (a, b, awin, sig_a, sig_b, td_a, td_b, ctl_a, sub_a),
                (b, a, 1 - awin, sig_b, sig_a, td_b, td_a, ctl_b, sub_b)):
            rows.append({"fighter": fgt, "opp": opp, "date": fd,
                         "division": "X", "secs": "900",
                         "sig_l": str(sl), "sig_l_opp": str(so),
                         "td_l": str(tl), "td_l_opp": str(to),
                         "ctrl": str(ct), "sub": str(sb),
                         "won": str(w), "decided": "1"})
        n_fights += 1
    # one completed fight ON the card date: Alpha beats Bravo -> the logged
    # card prediction for this pair must settle from the bouts csv itself
    for (fgt, opp, w) in (("Alpha Kick", "Bravo Punch", 1),
                          ("Bravo Punch", "Alpha Kick", 0)):
        rows.append({"fighter": fgt, "opp": opp, "date": card_date,
                     "division": "X", "secs": "900", "sig_l": "50",
                     "sig_l_opp": "40", "td_l": "1", "td_l_opp": "0",
                     "ctrl": "120", "sub": "1", "won": str(w), "decided": "1"})
    n_fights += 1
    bouts_csv = os.path.join(tmp, "fighter_bouts.csv")
    cols = ["fighter", "opp", "date", "division", "secs", "sig_l",
            "sig_l_opp", "td_l", "td_l_opp", "ctrl", "sub", "won", "decided"]
    with open(bouts_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    # synthetic card: one both-DOB bout (-> model A), one missing-DOB bout
    # (-> model B), one unresolvable bout (-> skipped)
    card = {
        "alphakick|bravopunch": {"f1": "Alpha Kick", "f2": "Bravo Punch",
                                 "cons1": 0.55, "event": "Synth Card"},
        "echoguard|golfelbow": {"f1": "Golf Elbow", "f2": "Echo Guard",
                                "cons1": 0.48, "event": "Synth Card"},
        "nobody|missing": {"f1": "Zoe Nobody", "f2": "Nemo Missing",
                           "cons1": 0.5, "event": "Synth Card"},
    }
    parsed_json = os.path.join(tmp, "parsed_odds.json")
    with open(parsed_json, "w") as f:
        json.dump(card, f)
    upcoming_csv = os.path.join(tmp, "upcoming.csv")
    with open(upcoming_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "R_fighter", "B_fighter"])
        w.writeheader()
        w.writerow({"date": card_date, "R_fighter": "Alpha Kick",
                    "B_fighter": "Bravo Punch"})

    plog = os.path.join(tmp, "ufc_predictions_blend.csv")
    graded = os.path.join(tmp, "ufc_graded_blend.csv")
    panel_path = os.path.join(tmp, "blend_ab.json")
    nodelta = os.path.join(tmp, "no_delta.csv")            # absent -> ignored
    prod_stub = os.path.join(tmp, "prod_graded_stub.csv")  # absent -> n=0 panel

    # (f) production paths must be untouched: snapshot before
    orig_plog, orig_graded = ufc_grade.PLOG, ufc_grade.GRADED
    prod_stat = {p: (os.stat(p).st_size, os.stat(p).st_mtime_ns)
                 for p in (orig_plog, orig_graded) if os.path.exists(p)}

    kw = dict(bouts_csv=bouts_csv, meta_path=meta_path,
              parsed_json=parsed_json, upcoming_csv=upcoming_csv,
              plog=plog, graded=graded, panel_path=panel_path,
              delta_csv=nodelta, prod_graded=prod_stub)
    r = run(**kw)

    # (a) state built, features exist, Elo moved
    st = r["state"]
    assert len(st) == 8, "expected 8 fighters in state, got %d" % len(st)
    assert any(abs(s.elo - ELO_BASE) > 1.0 for s in st.values()), "Elo never moved"
    assert all(s.n > 0 for s in st.values()), "fight counts missing"
    a_st = st["Alpha Kick"]
    assert a_st.ema["strike"] is not None and a_st.ema["won"] is not None, \
        "EMA features missing"
    assert len(_pre_feats(a_st, today)) == len(FEATS_B), "feature width drift"
    assert r["n_fights"] == n_fights, (r["n_fights"], n_fights)
    assert r["n_fights_a"] < r["n_fights"], "model A fit set must be a strict subset"

    # (b) both routing paths taken: both-DOB -> A, missing-DOB -> B
    by_pair = {frozenset((d["f1"], d["f2"])): d for d in r["details"]}
    assert len(r["details"]) == 2, "unresolvable bout was not skipped"
    da = by_pair[frozenset(("Alpha Kick", "Bravo Punch"))]
    db = by_pair[frozenset(("Golf Elbow", "Echo Guard"))]
    assert da["model"] == "A", "both-DOB bout must route to model A"
    assert db["model"] == "B", "missing-DOB bout must route to model B"

    # (c) sane probabilities + exact mirror symmetry by construction
    for d in r["details"]:
        assert 0.05 < d["p1"] < 0.95, "prob out of range: %r" % d
    swapped = [{"f1": v["f2"], "f2": v["f1"], "cons1": None, "event": "Synth"}
               for v in card.values()]
    _, det2 = predict_card(st, r["pred_a"], r["pred_b"], r["dobs"],
                           swapped, card_date)
    p2 = {frozenset((d["f1"], d["f2"])): d["p1"] for d in det2}
    for pair, d in by_pair.items():
        assert abs(d["p1"] + p2[pair] - 1.0) < 1e-9, \
            "mirror probabilities must sum to 1"

    # (d) idempotent logging: second run logs 0 new
    assert r["n_logged"] == 2, r["n_logged"]
    r2 = run(**kw)
    assert r2["n_logged"] == 0, "second run must log nothing new"

    # (e) grading settled the Alpha/Bravo bout (result in bouts csv); the
    # Golf/Echo bout stays pending (recent, no result); panel has both keys
    assert r["n_settled"] == 1, r["n_settled"]
    assert r["panel"]["blend"]["n"] == 1
    assert r["panel"]["blend"]["acc"] in (0.0, 100.0)
    with open(panel_path) as f:
        panel = json.load(f)
    assert "production" in panel and "blend" in panel, panel.keys()
    assert "n_logged_now" in panel and "generated" in panel
    assert panel["production"]["n"] == 0            # stub prod ledger, offline
    graded_rows = ufc_grade.load_csv(graded)
    assert len(graded_rows) == 1 and graded_rows[0]["outcome"] == "f1", graded_rows
    # settled probability is model A's own p1 for Alpha, not production's
    assert abs(float(graded_rows[0]["p1"]) - round(da["p1"], 4)) < 1e-6

    # --grade-only path: settles nothing new but rewrites the panel
    os.remove(panel_path)
    rg = run(grade_only=True, **{k: v for k, v in kw.items()
                                 if k not in ("meta_path", "parsed_json",
                                              "upcoming_csv")})
    assert rg["n_settled"] == 0 and os.path.exists(panel_path)

    # (f) ufc_grade paths restored; production files untouched; no production-
    # named files sneaked into the temp dir
    assert ufc_grade.PLOG == orig_plog and ufc_grade.GRADED == orig_graded, \
        "ufc_grade paths not restored"
    for p, sig in prod_stat.items():
        assert (os.stat(p).st_size, os.stat(p).st_mtime_ns) == sig, \
            "production file modified: %s" % p
    assert not os.path.exists(os.path.join(tmp, "ufc_predictions.csv"))
    assert not os.path.exists(os.path.join(tmp, "ufc_graded.csv"))
    assert not os.path.exists(prod_stub), "prod stub must never be created"

    print("UFC BLEND A/B SELFTEST PASS — state+EMA+Elo build, A/B routing, "
          "mirror symmetry, idempotent log, settle, panel, prod untouched")
    return 0


# ---------------------------------------------------------------------------
# MAIN — fail-soft for pipeline modes; --selftest fails loudly by design
# ---------------------------------------------------------------------------

def main(argv):
    if "--selftest" in argv:
        return selftest()
    grade_only = "--grade-only" in argv
    try:
        r = run(grade_only=grade_only)
        pb = r["panel"]["blend"]
        msg = ("Blend A/B: logged %d new, settled %d; blend record n=%d"
               % (r["n_logged"], r["n_settled"], pb.get("n", 0)))
        if pb.get("n"):
            msg += ", acc %s%%, Brier %s" % (pb.get("acc"), pb.get("brier"))
        if not grade_only:
            n_a = sum(1 for d in r["details"] if d["model"] == "A")
            msg += " | card '%s' %s: %d bouts (%d age-model)" % (
                r["event"], r["cdate"], len(r["details"]), n_a)
        print(msg)
    except Exception as e:
        print("Blend A/B step skipped (%s: %s)" % (type(e).__name__, e))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
