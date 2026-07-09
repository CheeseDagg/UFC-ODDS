"""
ufc_grade.py — the forward ledger. Every card build logs each bout's model win
probability and the devigged market consensus PRE-FIGHT; results are settled
from data/fighter_bouts.csv on later rebuilds (the same scrape the ratings
train on). This turns the tool's retrospective calibration into a LIVE record,
including the house disagreement study: when model and market pick opposite
corners, who's right?

Outcomes: 'f1' | 'f2' | 'void' (no result within VOID_DAYS of the card —
cancellations, pull-outs) | pending (not written; retried each rebuild).
Idempotent by (date, fighter-pair).
"""
import os, csv, math, datetime as dt, unicodedata, re

HERE = os.path.dirname(os.path.abspath(__file__))
PLOG = os.path.join(HERE, "data", "ufc_predictions.csv")
GRADED = os.path.join(HERE, "data", "ufc_graded.csv")
COLS = ["logged", "event", "date", "f1", "f2", "p1", "q1", "outcome"]
VOID_DAYS = 14

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())

TRANSLIT = str.maketrans({"ł":"l","Ł":"l","ø":"o","Ø":"o","đ":"d","Đ":"d",
                           "ß":"ss","æ":"ae","Æ":"ae","þ":"th","ð":"d"})

def _ed1(a, b):
    """edit distance <= 1 (insert/delete/substitute) — cheap, exact."""
    if a == b: return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1: return False
    if la > lb: a, b, la, lb = b, a, lb, la
    i = j = diff = 0
    while i < la and j < lb:
        if a[i] == b[j]: i += 1; j += 1
        else:
            diff += 1
            if diff > 1: return False
            if la == lb: i += 1
            j += 1
    return True

def resolve(name, keys):
    """name -> the norm-key in `keys` it denotes, or None. Tiers:
    exact -> transliterated exact -> token-anchored (last-name edit<=1 AND
    first-name prefix), accepted ONLY if exactly one candidate survives —
    six Magomedovs must never be guessed between."""
    n = norm(name)
    if n in keys: return n
    n2 = norm((name or "").translate(TRANSLIT))
    if n2 in keys: return n2
    toks = re.sub(r"[^a-z ]", "", unicodedata.normalize("NFKD",
                  (name or "").translate(TRANSLIT)).encode("ascii","ignore").decode().lower()).split()
    if len(toks) < 2: return None
    first, last = toks[0], toks[-1]
    cands = []
    for k in keys:
        # norm keys have no spaces; anchor the surname on the suffix, trying
        # windows of len(last) +/- 1 so a one-letter-longer spelling still aligns
        mL = None
        if k.endswith(last):
            mL = len(last)
        elif len(last) > 4:
            for L in (len(last) - 1, len(last), len(last) + 1):
                if 0 < L <= len(k) and _ed1(k[-L:], last):
                    mL = L; break
        if mL is None: continue
        stem = k[: len(k) - mL]
        if stem.startswith(first[:4]) or first.startswith(stem[:4] or "\0") or _ed1(stem, first):
            cands.append(k)
    return cands[0] if len(cands) == 1 else None

def _pair(f1, f2):
    return tuple(sorted((norm(f1), norm(f2))))

def ensure_files():
    os.makedirs(os.path.dirname(PLOG), exist_ok=True)
    for p, cols in ((PLOG, COLS[:-1]), (GRADED, COLS)):
        if not os.path.exists(p):
            with open(p, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=cols).writeheader()

def load_csv(p):
    if not os.path.exists(p): return []
    with open(p) as f: return list(csv.DictReader(f))

def log_card(event, date, bouts):
    """bouts: [{f1,f2,p1,q1?}] with p1 = P(f1 wins) from the model's own
    scores, q1 = devigged market consensus for f1 (optional)."""
    ensure_files()
    have = {(r["date"],) + _pair(r["f1"], r["f2"]) for r in load_csv(PLOG)}
    today = dt.date.today().isoformat()
    new = 0
    with open(PLOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS[:-1])
        for b in bouts:
            k = (str(date),) + _pair(b["f1"], b["f2"])
            if k in have or b.get("p1") is None: continue
            w.writerow({"logged": today, "event": event, "date": date,
                        "f1": b["f1"], "f2": b["f2"],
                        "p1": round(float(b["p1"]), 4),
                        "q1": ("" if b.get("q1") is None else round(float(b["q1"]), 4))})
            new += 1
    return new

def _results_map(bouts_csv):
    """fighter_bouts.csv -> {(normA, normB, date): winner_norm}."""
    res = {}
    with open(bouts_csv) as f:
        for r in csv.DictReader(f):
            a, b, d = norm(r.get("fighter")), norm(r.get("opp")), (r.get("date") or "").strip()
            if not (a and b and d): continue
            try: won = int(float(r.get("won", "") or 0))
            except ValueError: continue
            key = (min(a, b), max(a, b), d)
            if won == 1: res[key] = a
            elif key not in res: res[key] = res.get(key)  # keep any prior winner
            if won == 0 and res.get(key) is None:
                res[key] = b if int(float(r.get("decided", "1") or 1)) else None
    return res

def settle_row(row, res):
    a, b = norm(row["f1"]), norm(row["f2"])
    d = (row["date"] or "").strip()
    for dd in (d,) + tuple((dt.date.fromisoformat(d) + dt.timedelta(days=k)).isoformat()
                           for k in (-1, 1) if _isdate(d)):
        w = res.get((min(a, b), max(a, b), dd))
        if w:
            return "f1" if w == a else "f2"
    if _isdate(d) and (dt.date.today() - dt.date.fromisoformat(d)).days > VOID_DAYS:
        return "void"
    return "pending"

def _isdate(s):
    try: dt.date.fromisoformat(s); return True
    except (ValueError, TypeError): return False

def grade_all(bouts_csv):
    ensure_files()
    preds = load_csv(PLOG)
    if not preds: return 0, summarize([])
    done = {(r["date"],) + _pair(r["f1"], r["f2"]) for r in load_csv(GRADED)}
    res = _results_map(bouts_csv)
    new = []
    for r in preds:
        k = (r["date"],) + _pair(r["f1"], r["f2"])
        if k in done: continue
        o = settle_row(r, res)
        if o == "pending": continue
        r2 = dict(r); r2["outcome"] = o
        new.append(r2)
    if new:
        with open(GRADED, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            for r in new: w.writerow(r)
    return len(new), summarize(load_csv(GRADED))

def summarize(rows):
    live = [r for r in rows if r.get("outcome") in ("f1", "f2")]
    panel = {"n": len(live), "voids": sum(1 for r in rows if r.get("outcome") == "void"),
             "events": len({r["event"] for r in rows}) if rows else 0}
    if not live: return panel
    p = [float(r["p1"]) for r in live]
    y = [1.0 if r["outcome"] == "f1" else 0.0 for r in live]
    panel["acc"] = round(100 * sum(1 for pi, yi in zip(p, y) if (pi > 0.5) == (yi == 1)) / len(live), 1)
    panel["brier"] = round(sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(live), 4)
    M = [(float(r["p1"]), float(r["q1"]), 1.0 if r["outcome"] == "f1" else 0.0)
         for r in live if r.get("q1") not in ("", None)]
    if M:
        macc = sum(1 for pm, qm, yy in M if (qm > 0.5) == (yy == 1)) / len(M)
        dis = [(pm, qm, yy) for pm, qm, yy in M if (pm > 0.5) != (qm > 0.5)]
        panel["market"] = {"n": len(M), "acc": round(100 * macc, 1),
                           "disagree_n": len(dis),
                           "disagree_model_right": (round(100 * sum(
                               1 for pm, _q, yy in dis if (pm > 0.5) == (yy == 1)) / len(dis), 1)
                               if dis else None)}
    return panel

def selftest():
    import tempfile, json
    global PLOG, GRADED
    tmp = tempfile.mkdtemp()
    PLOG, GRADED = os.path.join(tmp, "p.csv"), os.path.join(tmp, "g.csv")
    today = dt.date.today()
    recent = (today - dt.timedelta(days=3)).isoformat()
    stale = (today - dt.timedelta(days=30)).isoformat()
    bouts = [{"f1": "Rafael Fiziev", "f2": "Manuel Torres", "p1": 0.62, "q1": 0.497},
             {"f1": "Ghost Fighter", "f2": "Cancelled Guy", "p1": 0.55, "q1": 0.60},
             {"f1": "Óscar Piñera", "f2": "Old Result", "p1": 0.40, "q1": 0.45}]
    assert log_card("Test Card", recent, bouts) == 3
    assert log_card("Test Card", recent, bouts) == 0                 # idempotent
    log_card("Stale Card", stale, [{"f1": "Never", "f2": "Happened", "p1": 0.7, "q1": 0.65}])
    # results csv: Torres upsets Fiziev; accents/pair-orientation; stale card absent
    rcsv = os.path.join(tmp, "bouts.csv")
    with open(rcsv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fighter", "opp", "date", "won", "decided"])
        w.writeheader()
        w.writerow({"fighter": "Manuel Torres", "opp": "Rafael Fiziev", "date": recent, "won": 1, "decided": 1})
        w.writerow({"fighter": "Rafael Fiziev", "opp": "Manuel Torres", "date": recent, "won": 0, "decided": 1})
        w.writerow({"fighter": "Oscar Pinera", "opp": "Old Result", "date": recent, "won": 1, "decided": 1})
    n, p = grade_all(rcsv)
    # settles: Fiziev bout (f2 wins), Pinera bout (f1 wins, accent-matched),
    # stale Never/Happened -> void; recent Ghost/Cancelled -> pending (day 3 < 14)
    assert n == 3, n
    assert p["n"] == 2 and p["voids"] == 1
    assert p["acc"] == 0.0        # p=.62 picked f1 (lost), p=.40 picked f2 (lost)
    b_exp = round(((0.62 - 0) ** 2 + (0.40 - 1) ** 2) / 2, 4)
    assert p["brier"] == b_exp, (p["brier"], b_exp)
    m = p["market"]
    # market: Fiziev q=.497 picked f2 ✓ right; Pinera q=.45 picked f2 ✗ wrong -> 50%
    # disagreements: Fiziev (model f1 vs market f2) -> model wrong there
    assert m["n"] == 2 and m["acc"] == 50.0
    assert m["disagree_n"] == 1 and m["disagree_model_right"] == 0.0
    n2, _ = grade_all(rcsv)
    assert n2 == 0                                  # idempotent grading
    json.dumps(p)
    # resolver: real Baku-card drift cases
    K = {norm(x) for x in ["Nazim Sadykhov","Asu Almabayev","Michal Oleksiejczuk",
         "Nursulton Ruziboev","Shara Magomedov","Abus Magomedov","Umar Nurmagomedov",
         "Said Nurmagomedov","Rashid Magomedov","Rafael Fiziev"]}
    assert resolve("Nazim Sadykhov", K) == norm("Nazim Sadykhov")          # exact
    assert resolve("Michał Oleksiejczuk", K) == norm("Michal Oleksiejczuk") # ł translit
    assert resolve("Asu Almabaev", K) == norm("Asu Almabayev")             # ed1 last name
    assert resolve("Nursultan Ruziboev", K) == norm("Nursulton Ruziboev")  # vowel drift
    assert resolve("Sharabutdin Magomedov", K) == norm("Shara Magomedov")  # short form
    assert resolve("Abusupiyan Magomedov", K) == norm("Abus Magomedov")
    assert resolve("Islam Magomedov", K) is None       # ambiguous surname -> refuse
    assert resolve("Matheus Camilo", K) is None        # genuinely absent
    print("UFC LEDGER SELFTEST PASS — log/settle idempotent, accents, pair orientation, "
          "void window, Brier exact, market disagreement live")
    return 0

if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv: sys.exit(selftest())
    print("library — wired into build_site.py")
