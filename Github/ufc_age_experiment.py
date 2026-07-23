#!/usr/bin/env python3
"""
UFC AGE + REACH experiment harness  (standalone, self-contained)
================================================================

GOAL
----
Test whether fighter AGE (derived from date-of-birth) and REACH make fight
win-probability predictions MORE ACCURATE than a leak-free Elo + feature-blend
baseline, on data/fighter_bouts.csv.

Why a new harness: an earlier experiment on fighter_bouts.csv (17,372 rows,
leak-free Elo holdout Brier ~= 0.2454) improved holdout Brier to ~= 0.2388 with
a striking/grappling/experience/recent-form blend, but that file has NO
birthdates, so it could not test a true AGE curve. This harness adds DOB + reach
scraped from ufcstats.com fighter detail pages, then re-runs a leak-free
walk-forward and prints a VERDICT.

NETWORK NOTE
------------
This cloud session's egress is BLOCKED (403 'Tunnel connection failed' to
ufcstats/ESPN). That is expected. The data pull is written DEFENSIVELY: if the
host is unreachable it prints a clear one-line message and exits 0. The pull is
designed to run on GitHub Actions (where ufcstats.com is reachable) and caches
DOB/reach to fighter_meta_cache.json so it need not re-scrape every run.

USAGE
-----
    python3 ufc_age_experiment.py --selftest   # offline, NO network, must pass
    python3 ufc_age_experiment.py --pull       # scrape DOB/reach -> cache (Actions)
    python3 ufc_age_experiment.py              # run experiment + print VERDICT
                                               #   (auto-scrapes if cache absent)

Dependencies: numpy only (stdlib for everything else). Install with:
    pip install --break-system-packages numpy

This is a STANDALONE experiment. It reads data/fighter_bouts.csv read-only and
writes only fighter_meta_cache.json. It modifies NO production file.
"""

import sys
import os
import re
import csv
import json
import math
import time
import datetime as dt

try:
    import numpy as np
except Exception:  # pragma: no cover
    sys.stderr.write("numpy is required: pip install --break-system-packages numpy\n")
    raise

HERE = os.path.dirname(os.path.abspath(__file__))
BOUTS_CSV = os.path.join(HERE, "data", "fighter_bouts.csv")
META_CACHE = os.path.join(HERE, "fighter_meta_cache.json")

# ufcstats serves on the www host (bare-host TLS fails; in-page links are www too).
# Try each variant in order until one answers.
UFCSTATS_LIST_VARIANTS = (
    "http://www.ufcstats.com/statistics/fighters?char={c}&page=all",
    "https://www.ufcstats.com/statistics/fighters?char={c}&page=all",
    "http://ufcstats.com/statistics/fighters?char={c}&page=all",
)
UFCSTATS_LIST = UFCSTATS_LIST_VARIANTS[0]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")

# ---------------------------------------------------------------------------
# 1. PARSERS  (pure, no network -- exercised by --selftest)
# ---------------------------------------------------------------------------

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}

_DOB_RE = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})")
_REACH_RE = re.compile(r'(\d+(?:\.\d+)?)\s*"')
_HEIGHT_RE = re.compile(r"(\d+)'\s*(\d+)\s*\"")


def parse_dob(s):
    """'Feb 12, 1988' -> datetime.date(1988, 2, 12).  '--'/'' -> None."""
    if not s:
        return None
    m = _DOB_RE.search(s)
    if not m:
        return None
    mon = _MONTHS.get(m.group(1))
    if not mon:
        return None
    try:
        return dt.date(int(m.group(3)), mon, int(m.group(2)))
    except ValueError:
        return None


def parse_reach(s):
    """'76\"' -> 76.0 ; '--' or '' -> None."""
    if not s:
        return None
    m = _REACH_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_height(s):
    """'5\\' 11\"' -> 71.0 inches ; '--' or '' -> None."""
    if not s:
        return None
    m = _HEIGHT_RE.search(s)
    if not m:
        return None
    return float(m.group(1)) * 12 + float(m.group(2))


def norm_name(name):
    """Normalize a fighter name for joining ufcstats <-> fighter_bouts."""
    n = (name or "").strip().lower()
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    n = re.sub(r"\s+", " ", n)
    return n


# ---------------------------------------------------------------------------
# 1b. DATA PULL  (network; degrades cleanly on block)
# ---------------------------------------------------------------------------

def _http_get(url, timeout=45):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _is_block_error(e):
    txt = str(e).lower()
    return ("403" in txt or "forbidden" in txt or "tunnel" in txt or
            "connection failed" in txt or "timed out" in txt or
            "name or service" in txt or "no route" in txt or
            "connection refused" in txt or "ssl" in txt)


# ufcstats fighter-detail parsing ------------------------------------------
_DETAIL_URL_RE = re.compile(r"https?://(?:www\.)?ufcstats\.com/fighter-details/[0-9a-f]+")
_NAME_RE = re.compile(
    r'<span class="b-content__title-highlight">\s*(.*?)\s*</span>', re.S)


def _extract_detail_urls(list_html):
    return sorted(set(_DETAIL_URL_RE.findall(list_html)))


def parse_fighter_detail(html):
    """Return {name, dob, reach, height} from a ufcstats fighter-detail page.

    Robust to whitespace; returns None fields when data is '--'.
    """
    name_m = _NAME_RE.search(html)
    name = re.sub(r"\s+", " ", name_m.group(1)).strip() if name_m else None

    def _field(label):
        # match  <i ...>LABEL:</i>  VALUE  (VALUE may be on same or next line)
        m = re.search(label + r":\s*</i>\s*([^<]*)", html)
        return m.group(1).strip() if m else ""

    dob_raw = _field("DOB")
    reach_raw = _field("Reach")
    height_raw = _field("Height")
    return {
        "name": name,
        "dob": parse_dob(dob_raw),
        "reach": parse_reach(reach_raw),
        "height": parse_height(height_raw),
    }


def load_cache():
    if not os.path.exists(META_CACHE):
        return {}
    try:
        with open(META_CACHE) as f:
            raw = json.load(f)
    except Exception:
        return {}
    out = {}
    for k, v in raw.items():
        out[k] = {
            "dob": dt.date.fromisoformat(v["dob"]) if v.get("dob") else None,
            "reach": v.get("reach"),
            "height": v.get("height"),
            "name": v.get("name", k),
            "_url": v.get("_url"),
        }
    return out


def save_cache(meta):
    ser = {}
    for k, v in meta.items():
        ser[k] = {
            "dob": v["dob"].isoformat() if v.get("dob") else None,
            "reach": v.get("reach"),
            "height": v.get("height"),
            "name": v.get("name", k),
            "_url": v.get("_url"),      # resume marker — must survive save/load
        }
    tmp = META_CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ser, f, indent=0)
    os.replace(tmp, META_CACHE)


def pull_meta(sleep=0.25, limit=None):
    """Scrape ufcstats for DOB/reach/height. Cache incrementally.

    Returns (meta_dict, ok). ok=False means the host was unreachable
    (blocked) -- caller should print a message and continue/exit gracefully.
    """
    meta = load_cache()

    # 1) gather detail URLs from the a-z list pages. Pick the first host variant that
    # answers with actual detail links (bare-host TLS fails; links live on www).
    urls = set()
    letters = "abcdefghijklmnopqrstuvwxyz"
    list_tpl = None
    for tpl in UFCSTATS_LIST_VARIANTS:
        try:
            html = _http_get(tpl.format(c="a"))
            found = _extract_detail_urls(html)
            print("probe %s -> %d detail links" % (tpl.format(c="a"), len(found)))
            if found:
                list_tpl = tpl
                urls.update(found)
                break
        except Exception as e:
            print("probe failed (%s): %s" % (type(e).__name__, tpl.format(c="a")))
            continue
    if list_tpl is None:
        print("ufcstats yielded no fighter links (blocked or bot-walled) -- trying ESPN.")
        return pull_meta_espn(meta, sleep=sleep, limit=limit)
    try:
        for c in letters[1:]:
            html = _http_get(list_tpl.format(c=c))
            urls.update(_extract_detail_urls(html))
            time.sleep(sleep)
    except Exception as e:
        if _is_block_error(e):
            print("ufcstats became UNREACHABLE during list crawl (%s) -- continuing "
                  "with %d pages found so far." % (type(e).__name__, len(urls)))
        else:
            raise

    urls = sorted(urls)
    if limit:
        urls = urls[:limit]
    print("Discovered %d fighter detail pages." % len(urls))

    # 2) fetch each detail page (resume-safe via url->done marker in cache)
    done = {v.get("_url") for v in meta.values() if isinstance(v, dict)}
    n_new = 0
    for i, url in enumerate(urls):
        if url in done:
            continue
        try:
            html = _http_get(url)
        except Exception as e:
            if _is_block_error(e):
                print("ufcstats became UNREACHABLE mid-pull (%s) after %d new "
                      "records -- partial cache saved; re-run to resume."
                      % (type(e).__name__, n_new))
                save_cache(meta)
                return meta, False
            time.sleep(1.0)
            continue
        rec = parse_fighter_detail(html)
        if rec.get("name"):
            key = norm_name(rec["name"])
            rec["_url"] = url
            meta[key] = rec
            n_new += 1
        if n_new % 100 == 0 and n_new:
            save_cache(meta)
            print("  ... %d new records cached" % n_new)
        time.sleep(sleep)

    save_cache(meta)
    print("Pull complete: %d total fighter meta records (%d new)."
          % (len(meta), n_new))
    return meta, True


# ---- ESPN fallback: ufcstats bot-walls the Actions runner (pages load but carry
# 0 fighter links). ESPN's core API is proven reachable from Actions (the results
# workflow uses ESPN daily) and its athlete records carry dateOfBirth + reach. ----
ESPN_LIST = ("https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc/"
             "athletes?limit=1000&page={p}")


def _espn_rec_from_json(d):
    """athlete JSON -> {name, dob, reach, height} (reach/height already inches)."""
    name = (d.get("displayName") or d.get("fullName") or "").strip()
    dob = None
    raw = str(d.get("dateOfBirth") or "")[:10]
    if raw:
        try:
            dob = dt.date.fromisoformat(raw)
        except ValueError:
            dob = None
    def _f(k):
        v = d.get(k)
        try:
            v = float(v)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None
    return {"name": name or None, "dob": dob, "reach": _f("reach"), "height": _f("height")}


def pull_meta_espn(meta, sleep=0.2, limit=None):
    """Page through ESPN's UFC athlete index and fetch each athlete record.
    Resume-safe via the _url marker persisted in the cache."""
    print("Falling back to ESPN core API for DOB/reach ...")
    refs = []
    try:
        first = json.loads(_http_get(ESPN_LIST.format(p=1)))
        pages = int(first.get("pageCount") or 1)
        refs += [it.get("$ref") for it in first.get("items", []) if it.get("$ref")]
        for p in range(2, pages + 1):
            j = json.loads(_http_get(ESPN_LIST.format(p=p)))
            refs += [it.get("$ref") for it in j.get("items", []) if it.get("$ref")]
            time.sleep(sleep)
    except Exception as e:
        print("ESPN athlete index UNREACHABLE (%s) -- run --pull on GitHub Actions."
              % type(e).__name__)
        return meta, False
    if limit:
        refs = refs[:limit]
    print("ESPN athlete refs: %d" % len(refs))
    done = {v.get("_url") for v in meta.values() if isinstance(v, dict)}
    n_new = 0
    for ref in refs:
        if ref in done:
            continue
        try:
            rec = _espn_rec_from_json(json.loads(_http_get(ref)))
        except Exception as e:
            if _is_block_error(e):
                print("ESPN became UNREACHABLE mid-pull (%s) after %d new records -- "
                      "partial cache saved; re-run to resume." % (type(e).__name__, n_new))
                save_cache(meta)
                return meta, False
            time.sleep(1.0)
            continue
        if rec.get("name") and (rec.get("dob") or rec.get("reach")):
            key = norm_name(rec["name"])
            # never clobber a richer existing record with a poorer one
            old = meta.get(key)
            if not (old and old.get("dob") and rec.get("dob") is None):
                rec["_url"] = ref
                meta[key] = rec
                n_new += 1
        if n_new and n_new % 200 == 0:
            save_cache(meta)
            print("  ... %d new ESPN records cached" % n_new)
        time.sleep(sleep)
    save_cache(meta)
    print("ESPN pull complete: %d total fighter meta records (%d new)." % (len(meta), n_new))
    return meta, True


# ---------------------------------------------------------------------------
# 2. LEAK-FREE FEATURE BUILDER  (walk-forward)
# ---------------------------------------------------------------------------

def load_bouts(path=BOUTS_CSV):
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def _f(row, k):
    try:
        return float(row.get(k) or 0.0)
    except ValueError:
        return 0.0


def dedupe_fights(rows):
    """Collapse the two mirrored rows of each fight into one directed example.

    Side A = alphabetically-first fighter name (deterministic, orientation is
    a modeling nuisance we cancel by using signed A-B differentials + label).
    Returns fights sorted chronologically, each carrying BOTH perspective rows
    so per-fighter running state can be updated from each side.
    """
    by_key = {}
    for r in rows:
        d = r["date"]
        a, b = r["fighter"], r["opp"]
        key = (d, tuple(sorted((a, b))))
        by_key.setdefault(key, {})[r["fighter"]] = r
    fights = []
    for (d, pair), persp in by_key.items():
        if len(persp) != 2:
            # a mirror is missing -- skip (cannot form a clean example)
            continue
        A, B = pair  # sorted -> A < B
        rowA, rowB = persp[A], persp[B]
        try:
            date = dt.date.fromisoformat(d)
        except ValueError:
            continue
        fights.append({
            "date": date, "A": A, "B": B,
            "rowA": rowA, "rowB": rowB,
            "yA": int(_f(rowA, "won")),   # did A win (A perspective row)
            "division": rowA.get("division", ""),
        })
    fights.sort(key=lambda x: (x["date"], x["A"], x["B"]))
    return fights


class FighterState:
    __slots__ = ("elo", "n", "wins", "last3",
                 "sig_l", "sig_a", "secs", "td_l", "ctrl", "kd", "sub")

    def __init__(self):
        self.elo = 1500.0
        self.n = 0
        self.wins = 0
        self.last3 = []          # most-recent-first list of 0/1
        self.sig_l = 0.0         # cumulative sig strikes landed
        self.sig_a = 0.0         # cumulative sig strikes absorbed
        self.secs = 0.0          # cumulative fight seconds
        self.td_l = 0.0          # cumulative takedowns landed
        self.ctrl = 0.0          # cumulative control seconds
        self.kd = 0.0            # cumulative knockdowns
        self.sub = 0.0           # cumulative submission attempts


def _rate_feats(st):
    """Pre-fight rate features from a fighter's *prior* fights only.

    Returns a dict of career rates; neutral zeros when the fighter is a debutant
    (n == 0), so a fight leaks NOTHING about its own or future outcomes.
    """
    if st.n == 0 or st.secs <= 0:
        return dict(sig_pm=0.0, strike_diff_pm=0.0, td_pm=0.0,
                    ctrl_frac=0.0, kd_pm=0.0, sub_pm=0.0,
                    winrate=0.5, last3=0.5, exp=0.0)
    mins = st.secs / 60.0
    last3 = (sum(st.last3) / len(st.last3)) if st.last3 else 0.5
    return dict(
        sig_pm=st.sig_l / mins,
        strike_diff_pm=(st.sig_l - st.sig_a) / mins,
        td_pm=st.td_l / mins,
        ctrl_frac=st.ctrl / st.secs,
        kd_pm=st.kd / mins,
        sub_pm=st.sub / mins,
        winrate=st.wins / st.n,
        last3=last3,
        exp=math.log1p(st.n),
    )


def _update_state(st, row, won):
    st.sig_l += _f(row, "sig_l")
    st.sig_a += _f(row, "sig_l_opp")
    st.secs += _f(row, "secs")
    st.td_l += _f(row, "td_l")
    st.ctrl += _f(row, "ctrl")
    st.kd += _f(row, "kd")
    st.sub += _f(row, "sub")
    st.n += 1
    st.wins += int(won)
    st.last3 = ([int(won)] + st.last3)[:3]


ELO_K = 24.0
ELO_SCALE = 400.0


def build_dataset(fights, meta=None):
    """Walk chronologically, emitting one leak-free example per fight.

    Every feature at fight i is computed from state accumulated over fights
    STRICTLY BEFORE i, then state is updated. Elo is an online running rating
    (also updated only after the fight is scored) so it never sees its own
    result. DOB is static, so age-at-fight is trivially leak-free.

    Returns dict of numpy arrays.
    """
    meta = meta or {}
    state = {}

    def get(name):
        st = state.get(name)
        if st is None:
            st = state[name] = FighterState()
        return st

    feat_names = ["elo_diff", "exp_diff", "sig_diff", "strike_diff",
                  "td_diff", "ctrl_diff", "kd_diff", "sub_diff",
                  "winrate_diff", "last3_diff"]
    F = {k: [] for k in feat_names}
    age_diff, age2_diff, reach_diff = [], [], []
    has_meta = []
    Y, DATES = [], []

    for fg in fights:
        A, B = fg["A"], fg["B"]
        sA, sB = get(A), get(B)
        fa, fb = _rate_feats(sA), _rate_feats(sB)

        elA, elB = sA.elo, sB.elo
        F["elo_diff"].append(elA - elB)
        F["exp_diff"].append(fa["exp"] - fb["exp"])
        F["sig_diff"].append(fa["sig_pm"] - fb["sig_pm"])
        F["strike_diff"].append(fa["strike_diff_pm"] - fb["strike_diff_pm"])
        F["td_diff"].append(fa["td_pm"] - fb["td_pm"])
        F["ctrl_diff"].append(fa["ctrl_frac"] - fb["ctrl_frac"])
        F["kd_diff"].append(fa["kd_pm"] - fb["kd_pm"])
        F["sub_diff"].append(fa["sub_pm"] - fb["sub_pm"])
        F["winrate_diff"].append(fa["winrate"] - fb["winrate"])
        F["last3_diff"].append(fa["last3"] - fb["last3"])

        # ---- treatment: age (from DOB) + reach ----
        mA = meta.get(norm_name(A))
        mB = meta.get(norm_name(B))
        ok = (mA and mB and mA.get("dob") and mB.get("dob") and
              mA.get("reach") and mB.get("reach"))
        if ok:
            ageA = (fg["date"] - mA["dob"]).days / 365.25
            ageB = (fg["date"] - mB["dob"]).days / 365.25
            # center at 28 so linear & quadratic terms are near-orthogonal
            cA, cB = ageA - 28.0, ageB - 28.0
            age_diff.append(cA - cB)
            age2_diff.append(cA * cA - cB * cB)
            reach_diff.append(float(mA["reach"]) - float(mB["reach"]))
            has_meta.append(True)
        else:
            age_diff.append(0.0)
            age2_diff.append(0.0)
            reach_diff.append(0.0)
            has_meta.append(False)

        Y.append(fg["yA"])
        DATES.append(fg["date"])

        # ---- update state AFTER scoring (leak-free) ----
        eA = 1.0 / (1.0 + 10.0 ** ((elB - elA) / ELO_SCALE))
        sA.elo = elA + ELO_K * (fg["yA"] - eA)
        sB.elo = elB + ELO_K * ((1 - fg["yA"]) - (1.0 - eA))
        _update_state(sA, fg["rowA"], fg["yA"])
        _update_state(sB, fg["rowB"], 1 - fg["yA"])

    ds = {k: np.asarray(v, dtype=float) for k, v in F.items()}
    ds["age_diff"] = np.asarray(age_diff, dtype=float)
    ds["age2_diff"] = np.asarray(age2_diff, dtype=float)
    ds["reach_diff"] = np.asarray(reach_diff, dtype=float)
    ds["has_meta"] = np.asarray(has_meta, dtype=bool)
    ds["y"] = np.asarray(Y, dtype=float)
    ds["dates"] = np.asarray([d.toordinal() for d in DATES], dtype=float)
    ds["years"] = np.asarray([d.year for d in DATES], dtype=int)
    ds["_feat_names"] = feat_names
    return ds


# ---------------------------------------------------------------------------
# 3. LOGISTIC MODEL  (numpy; standardize on train, gradient descent + L2)
# ---------------------------------------------------------------------------

def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def logloss(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit_logistic(X, y, l2=1.0, iters=4000, lr=0.5):
    """Standardize columns on the given (train) data, fit w & bias by GD+L2.

    Returns a predictor callable p = f(Xnew) and the fitted (mu, sd, w, b).
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-8] = 1.0
    Xs = (X - mu) / sd
    n, d = Xs.shape
    w = np.zeros(d)
    b = 0.0
    for _ in range(iters):
        p = sigmoid(Xs @ w + b)
        g = p - y
        gw = Xs.T @ g / n + l2 * w / n
        gb = g.mean()
        w -= lr * gw
        b -= lr * gb

    def predict(Xnew):
        Xn = (np.asarray(Xnew, dtype=float) - mu) / sd
        return sigmoid(Xn @ w + b)

    return predict, dict(mu=mu, sd=sd, w=w, b=b)


def _design(ds, cols, mask=None):
    idx = np.arange(len(ds["y"])) if mask is None else np.where(mask)[0]
    X = np.column_stack([ds[c][idx] for c in cols])
    return X, ds["y"][idx], idx


# ---------------------------------------------------------------------------
# EXPERIMENT
# ---------------------------------------------------------------------------

BASE_BLEND = ["elo_diff", "exp_diff", "sig_diff", "strike_diff", "td_diff",
              "ctrl_diff", "kd_diff", "sub_diff", "winrate_diff", "last3_diff"]
TREAT_EXTRA = ["age_diff", "age2_diff", "reach_diff"]


def _holdout_split(dates, frac=0.75):
    order = np.argsort(dates)
    cut = dates[order[int(len(order) * frac)]]
    train = dates < cut
    hold = dates >= cut
    return train, hold, cut


def run_experiment(ds, meta_available):
    n = len(ds["y"])
    train, hold, cut = _holdout_split(ds["dates"], 0.75)
    cut_date = dt.date.fromordinal(int(cut))
    print("=" * 72)
    print("WALK-FORWARD  (train = fights before %s, holdout = on/after)" % cut_date)
    print("  total fights: %d   train: %d   holdout: %d"
          % (n, int(train.sum()), int(hold.sum())))

    # ---- reference: pure Elo ----
    Xtr, ytr, _ = _design(ds, ["elo_diff"], train)
    Xho, yho, _ = _design(ds, ["elo_diff"], hold)
    pred, _ = fit_logistic(Xtr, ytr)
    br_elo = brier(pred(Xho), yho)

    # ---- baseline: Elo + validated feature blend ----
    Xtr, ytr, _ = _design(ds, BASE_BLEND, train)
    Xho, yho, _ = _design(ds, BASE_BLEND, hold)
    pred_base, _ = fit_logistic(Xtr, ytr)
    br_base = brier(pred_base(Xho), yho)

    print("-" * 72)
    print("REFERENCE (holdout Brier, ALL holdout fights):")
    print("  pure Elo                 : %.4f" % br_elo)
    print("  Elo + feature blend      : %.4f  (baseline)" % br_base)

    if not meta_available or ds["has_meta"].sum() == 0:
        print("=" * 72)
        print("VERDICT: age/reach test PENDING -- no DOB/reach available in this")
        print("run. The leak-free baseline reproduced (Elo blend beats pure Elo:")
        print("        %+.4f Brier). To test AGE + REACH, populate the cache by"
              % (br_base - br_elo))
        print("        running `--pull` on GitHub Actions, then re-run.")
        print("=" * 72)
        return

    # ---- treatment: restrict to fights with DOB+reach for BOTH corners ----
    hm = ds["has_meta"]
    tr_m = train & hm
    ho_m = hold & hm
    cov = hm.sum()
    print("-" * 72)
    print("AGE/REACH COVERAGE: %d/%d fights have DOB+reach for both corners "
          "(%.1f%%)" % (cov, n, 100.0 * cov / n))
    print("  matched train: %d   matched holdout: %d"
          % (int(tr_m.sum()), int(ho_m.sum())))
    if ho_m.sum() < 200 or tr_m.sum() < 500:
        print("  (coverage low -- verdict is indicative, not final)")

    # fair comparison: both models fit on the SAME matched-train, scored on the
    # SAME matched-holdout subset.
    Xtr_b, ytr_b, _ = _design(ds, BASE_BLEND, tr_m)
    Xho_b, yho_b, _ = _design(ds, BASE_BLEND, ho_m)
    pb, _ = fit_logistic(Xtr_b, ytr_b)
    br_base_m = brier(pb(Xho_b), yho_b)

    cols_t = BASE_BLEND + TREAT_EXTRA
    Xtr_t, ytr_t, _ = _design(ds, cols_t, tr_m)
    Xho_t, yho_t, _ = _design(ds, cols_t, ho_m)
    pt, coef_t = fit_logistic(Xtr_t, ytr_t)
    br_treat_m = brier(pt(Xho_t), yho_t)

    # age-only and reach-only ablations
    def _brier_with(extra):
        c = BASE_BLEND + extra
        xt, yt, _ = _design(ds, c, tr_m)
        xh, yh, _ = _design(ds, c, ho_m)
        p, cf = fit_logistic(xt, yt)
        return brier(p(xh), yh), cf

    br_age, coef_age = _brier_with(["age_diff", "age2_diff"])
    br_reach, _ = _brier_with(["reach_diff"])

    print("-" * 72)
    print("HOLDOUT Brier on matched subset (lower = better):")
    print("  baseline (Elo+blend)         : %.4f" % br_base_m)
    print("  + age only                   : %.4f  (%+.4f)"
          % (br_age, br_age - br_base_m))
    print("  + reach only                 : %.4f  (%+.4f)"
          % (br_reach, br_reach - br_base_m))
    print("  + age + reach (treatment)    : %.4f  (%+.4f)"
          % (br_treat_m, br_treat_m - br_base_m))

    # ---- per-period robustness (holdout split into year buckets) ----
    print("-" * 72)
    print("PER-PERIOD holdout Brier (baseline -> +age+reach):")
    yrs = ds["years"][ho_m]
    p_base = pb(Xho_b)
    p_treat = pt(Xho_t)
    y_ho = yho_b
    improved = 0
    periods = 0
    # bucket years into ~3 chronological groups for stable n
    uy = np.unique(yrs)
    if len(uy) >= 3:
        edges = np.array_split(uy, 3)
        buckets = [(int(e[0]), int(e[-1])) for e in edges]
    else:
        buckets = [(int(uy.min()), int(uy.max()))]
    for lo, hi in buckets:
        m = (yrs >= lo) & (yrs <= hi)
        if m.sum() < 30:
            continue
        bb = brier(p_base[m], y_ho[m])
        bt = brier(p_treat[m], y_ho[m])
        flag = "improved" if bt < bb else "worse"
        print("  %d-%d  n=%-5d  %.4f -> %.4f  (%+.4f)  %s"
              % (lo, hi, int(m.sum()), bb, bt, bt - bb, flag))
        periods += 1
        improved += int(bt < bb)

    # ---- bootstrap CI on the age+reach Brier delta ----
    rng = np.random.default_rng(0)
    diffs = []
    base_e = (p_base - y_ho) ** 2
    treat_e = (p_treat - y_ho) ** 2
    d0 = float(np.mean(treat_e - base_e))
    m = len(y_ho)
    for _ in range(2000):
        idx = rng.integers(0, m, m)
        diffs.append(np.mean(treat_e[idx] - base_e[idx]))
    diffs = np.array(diffs)
    lo_ci, hi_ci = np.percentile(diffs, [2.5, 97.5])
    p_beneficial = float(np.mean(diffs < 0))

    # ---- age-curve shape from fitted coefficients (age-only model) ----
    # features age_diff=(cA-cB), age2_diff=(cA^2-cB^2) with c=age-28.
    # single-fighter contribution: c1*c + c2*c^2, peak at c* = -c1/(2 c2).
    mu = coef_age["mu"]; sd = coef_age["sd"]; w = coef_age["w"]
    names = BASE_BLEND + ["age_diff", "age2_diff"]
    ia = names.index("age_diff"); ib = names.index("age2_diff")
    # de-standardize coefficients back to raw feature scale
    c1 = w[ia] / sd[ia]
    c2 = w[ib] / sd[ib]
    peak_txt = "n/a"
    if abs(c2) > 1e-9:
        c_star = -c1 / (2 * c2)
        peak_age = 28.0 + c_star
        shape = "inverted-U (peaks then declines)" if c2 < 0 else "U (improves with age)"
        peak_txt = "peak age ~= %.1f  [%s]" % (peak_age, shape)

    print("=" * 72)
    print("VERDICT")
    print("-" * 72)
    delta = br_treat_m - br_base_m
    verdict_pos = (delta < 0) and (hi_ci < 0 or p_beneficial >= 0.9) \
        and (periods > 0 and improved >= max(1, periods - 1))
    print("  Baseline holdout Brier (matched)   : %.4f" % br_base_m)
    print("  +age+reach holdout Brier (matched) : %.4f" % br_treat_m)
    print("  Brier improvement                  : %+.4f (negative = better)" % delta)
    print("  Bootstrap 95%% CI on delta          : [%+.4f, %+.4f]" % (lo_ci, hi_ci))
    print("  P(age+reach helps)                 : %.2f" % p_beneficial)
    print("  Periods improved                   : %d/%d" % (improved, periods))
    print("  Age-curve shape                    : %s" % peak_txt)
    print("-" * 72)
    if verdict_pos:
        print("  ==> ROBUST YES: age and/or reach improve holdout accuracy by")
        print("      %.4f Brier, consistently across periods." % (-delta))
    elif delta < 0:
        print("  ==> WEAK/MIXED: nominal improvement of %.4f Brier but not" % (-delta))
        print("      robust across periods / bootstrap. Treat as inconclusive.")
    else:
        print("  ==> NO: age+reach do not improve holdout Brier over the")
        print("      Elo+blend baseline on this data.")
    print("=" * 72)


# ---------------------------------------------------------------------------
# 4. OFFLINE SELFTEST  (NO network)
# ---------------------------------------------------------------------------

def _selftest():
    fails = []

    def check(name, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        print("  [%s] %s%s" % (status, name, ("  -- " + detail) if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("SELFTEST (offline, synthetic)")
    print("-" * 72)

    # (b) parsers -----------------------------------------------------------
    check("parse_dob('Feb 12, 1988')", parse_dob("Feb 12, 1988") == dt.date(1988, 2, 12))
    check("parse_dob('DOB: Aug 05, 1990')", parse_dob("Aug 05, 1990") == dt.date(1990, 8, 5))
    check("parse_dob('--') is None", parse_dob("--") is None)
    check("parse_dob('') is None", parse_dob("") is None)
    check("parse_reach('76\"') == 76", parse_reach('76"') == 76.0)
    check("parse_reach('70.5\"') == 70.5", parse_reach('70.5"') == 70.5)
    check("parse_reach('--') is None", parse_reach("--") is None)
    check("parse_height(\"5' 11\\\"\") == 71", parse_height("5' 11\"") == 71.0)
    check("parse_height('--') is None", parse_height("--") is None)

    sample_detail = (
        '<span class="b-content__title-highlight"> Jon Doe </span>'
        '<li><i class="b-list__box-item-title">Height:</i> 5\' 11" </li>'
        '<li><i class="b-list__box-item-title">Reach:</i> 76" </li>'
        '<li><i class="b-list__box-item-title">DOB:</i> Feb 12, 1988 </li>')
    rec = parse_fighter_detail(sample_detail)
    check("detail parser name", rec["name"] == "Jon Doe")
    check("detail parser dob", rec["dob"] == dt.date(1988, 2, 12))
    check("detail parser reach", rec["reach"] == 76.0)
    check("detail parser height", rec["height"] == 71.0)

    urls_html = ('a href="http://ufcstats.com/fighter-details/abc123def456" '
                 'x http://ufcstats.com/fighter-details/abc123def456 '
                 'http://ufcstats.com/fighter-details/deadbeef0001')
    urls = _extract_detail_urls(urls_html)
    check("detail-url extraction dedupes", len(urls) == 2)

    # ESPN fallback record parser (offline fixture mirrors the core-API shape)
    er = _espn_rec_from_json({"displayName": "Jane Roe",
                              "dateOfBirth": "1991-06-03T07:00Z",
                              "reach": 68.0, "height": 66.0})
    check("espn parser name", er["name"] == "Jane Roe")
    check("espn parser dob", er["dob"] == dt.date(1991, 6, 3))
    check("espn parser reach", er["reach"] == 68.0)
    er2 = _espn_rec_from_json({"displayName": "No Data Guy", "reach": 0})
    check("espn parser missing fields -> None", er2["dob"] is None and er2["reach"] is None)

    # (c) logistic scoring math --------------------------------------------
    check("sigmoid(0)==0.5", abs(sigmoid(0.0) - 0.5) < 1e-12)
    check("brier(0.5) on balanced == 0.25",
          abs(brier(np.full(100, 0.5), np.array([0, 1] * 50)) - 0.25) < 1e-9)
    # recover a known linear coefficient sign/scale
    rng = np.random.default_rng(1)
    xx = rng.normal(size=(4000, 1))
    yy = (rng.uniform(size=4000) < sigmoid(1.5 * xx[:, 0])).astype(float)
    pf, cf = fit_logistic(xx, yy, l2=0.01, iters=6000, lr=0.5)
    # de-standardize slope back to raw scale
    raw_slope = cf["w"][0] / cf["sd"][0]
    check("logistic recovers slope ~1.5 (got %.2f)" % raw_slope,
          abs(raw_slope - 1.5) < 0.4, "raw_slope=%.3f" % raw_slope)
    check("logistic prob monotone",
          pf(np.array([[-2.0]]))[0] < pf(np.array([[2.0]]))[0])

    # (a) LEAK-FREENESS of fight-history features --------------------------
    # Build a synthetic mirrored bout table; the definitive leak test is that
    # altering a FUTURE fight's stats must NOT change an earlier example's
    # features.
    def synth_rows(future_sig):
        base = []
        names = ["Al", "Bo", "Cy", "Di"]
        d = dt.date(2010, 1, 1)
        # 6 fights in time order among 4 fighters
        schedule = [("Al", "Bo", 1), ("Cy", "Di", 1), ("Al", "Cy", 0),
                    ("Bo", "Di", 1), ("Al", "Di", 1), ("Bo", "Cy", 0)]
        for i, (a, b, awin) in enumerate(schedule):
            dd = (d + dt.timedelta(days=30 * i)).isoformat()
            sig = future_sig if i == 5 else 10  # tamper only with the LAST fight
            for (f, o, w) in [(a, b, awin), (b, a, 1 - awin)]:
                base.append(dict(
                    fighter=f, opp=o, date=dd, division="X", secs="300",
                    sig_l=str(sig), sig_a="10", sig_l_opp="10", sig_a_opp=str(sig),
                    td_l="1", td_a="2", td_l_opp="0", td_a_opp="1",
                    ctrl="60", sub="0", kd="0", kd_abs="0", won=str(w),
                    decided="1", won_by_ko="0", lost_by_ko="0",
                    won_by_sub="0", won_by_dec="1", year="2010"))
        return base

    ds1 = build_dataset(dedupe_fights(synth_rows(10)))
    ds2 = build_dataset(dedupe_fights(synth_rows(9999)))  # tamper last fight only
    # every example EXCEPT the last must be byte-identical across the two builds
    same = True
    for c in ds1["_feat_names"]:
        if not np.allclose(ds1[c][:-1], ds2[c][:-1]):
            same = False
    check("future-fight tampering does not leak into earlier features", same)
    # and the last example's OWN features must also be identical (features come
    # from PRIOR fights, not the current one that was tampered)
    last_same = all(np.isclose(ds1[c][-1], ds2[c][-1]) for c in ds1["_feat_names"])
    check("current fight's own result does not leak into its features", last_same)
    # debutants get neutral features (n==0)
    check("debut fight has zero elo_diff & neutral winrate_diff",
          abs(ds1["elo_diff"][0]) < 1e-9 and abs(ds1["winrate_diff"][0]) < 1e-9)

    # (d) PLANTED AGE EFFECT recovered on synthetic data -------------------
    # Simulate fights where the ONLY signal is an age prime-curve peaking at 29,
    # plus reach. If the harness works, +age+reach must beat the no-age baseline
    # on a held-out slice, and the recovered peak must land near 29.
    rng = np.random.default_rng(7)
    NF = 400  # fighters
    dobs = {}
    reaches = {}
    for i in range(NF):
        key = "F%03d" % i
        # birth dates spread so ages at fight span ~20..40
        dobs[key] = dt.date(1978 + int(rng.integers(0, 16)),
                            1 + int(rng.integers(0, 12)),
                            1 + int(rng.integers(0, 28)))
        reaches[key] = 68.0 + float(rng.integers(0, 12))

    def prime(age):
        return -0.02 * (age - 29.0) ** 2  # peaks at 29

    rows = []
    start = dt.date(2005, 1, 1)
    fnames = list(dobs.keys())
    for k in range(6000):
        a, b = rng.choice(fnames, size=2, replace=False)
        fdate = start + dt.timedelta(days=int(rng.integers(0, 365 * 12)))
        ageA = (fdate - dobs[a]).days / 365.25
        ageB = (fdate - dobs[b]).days / 365.25
        z = (prime(ageA) - prime(ageB)) + 0.05 * (reaches[a] - reaches[b])
        pA = sigmoid(z)
        awin = int(rng.uniform() < pA)
        dd = fdate.isoformat()
        for (f, o, w) in [(a, b, awin), (b, a, 1 - awin)]:
            rows.append(dict(
                fighter=f, opp=o, date=dd, division="X", secs="300",
                sig_l="10", sig_a="10", sig_l_opp="10", sig_a_opp="10",
                td_l="0", td_a="0", td_l_opp="0", td_a_opp="0",
                ctrl="0", sub="0", kd="0", kd_abs="0", won=str(w),
                decided="1", won_by_ko="0", lost_by_ko="0",
                won_by_sub="0", won_by_dec="1", year=str(fdate.year)))

    meta = {norm_name(k): {"dob": dobs[k], "reach": reaches[k],
                           "height": None, "name": k} for k in dobs}
    fights = dedupe_fights(rows)
    ds = build_dataset(fights, meta)
    train, hold, _ = _holdout_split(ds["dates"], 0.75)
    hm = ds["has_meta"]
    trm, hom = train & hm, hold & hm

    xb, yb, _ = _design(ds, BASE_BLEND, trm)
    xhb, yhb, _ = _design(ds, BASE_BLEND, hom)
    pb, _ = fit_logistic(xb, yb)
    br_b = brier(pb(xhb), yhb)

    ct = BASE_BLEND + TREAT_EXTRA
    xt, yt, _ = _design(ds, ct, trm)
    xht, yht, _ = _design(ds, ct, hom)
    pt, _ = fit_logistic(xt, yt)
    br_t = brier(pt(xht), yht)

    check("planted age+reach effect IMPROVES holdout Brier "
          "(base %.4f -> treat %.4f)" % (br_b, br_t), br_t < br_b - 1e-3,
          "no improvement")

    # recovered peak age from an age-only fit
    ca = BASE_BLEND + ["age_diff", "age2_diff"]
    xa, ya, _ = _design(ds, ca, trm)
    pa, cfa = fit_logistic(xa, ya)
    names = ca
    ia = names.index("age_diff"); ib = names.index("age2_diff")
    c1 = cfa["w"][ia] / cfa["sd"][ia]
    c2 = cfa["w"][ib] / cfa["sd"][ib]
    peak = 28.0 + (-c1 / (2 * c2)) if abs(c2) > 1e-9 else float("nan")
    check("recovered age-curve peaks near 29 (got %.1f)" % peak,
          c2 < 0 and 26.0 <= peak <= 32.0, "peak=%.2f c2=%.4f" % (peak, c2))

    print("-" * 72)
    if fails:
        print("SELFTEST FAILED: %d/%d checks failed -> %s"
              % (len(fails), len(fails), ", ".join(fails)))
        return 1
    print("SELFTEST PASSED: all checks green.")
    return 0


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main(argv):
    if "--selftest" in argv:
        return _selftest()

    if "--pull" in argv:
        lim = None
        for a in argv:
            if a.startswith("--limit="):
                lim = int(a.split("=", 1)[1])
        _, ok = pull_meta(limit=lim)
        return 0  # exit 0 even when blocked (defensive)

    # default: run the experiment
    if not os.path.exists(BOUTS_CSV):
        print("Missing %s -- run from the repo so data/ is present." % BOUTS_CSV)
        return 0
    print("Loading %s ..." % BOUTS_CSV)
    rows = load_bouts()
    fights = dedupe_fights(rows)
    print("Deduped %d mirrored rows -> %d unique fights (%s .. %s)."
          % (len(rows), len(fights),
             fights[0]["date"], fights[-1]["date"]))

    meta = load_cache()
    meta_available = len(meta) > 0
    if not meta_available:
        # try to pull; degrades to a clear message + empty meta if blocked
        print("No fighter_meta_cache.json -- attempting DOB/reach pull ...")
        meta, ok = pull_meta()
        meta_available = len(meta) > 0
    else:
        print("Loaded %d cached DOB/reach records." % len(meta))

    ds = build_dataset(fights, meta)
    run_experiment(ds, meta_available)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
