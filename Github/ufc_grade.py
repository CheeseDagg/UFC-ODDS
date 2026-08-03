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
DELTA = os.path.join(HERE, "data", "results_delta.csv")
COLS = ["logged", "event", "date", "f1", "f2", "p1", "q1", "outcome"]
VOID_DAYS = 14

TRANSLIT = str.maketrans({"ł":"l","Ł":"l","ø":"o","Ø":"o","đ":"d","Đ":"d",
                           "ß":"ss","æ":"ae","Æ":"ae","þ":"th","ð":"d"})

def norm(s):
    # TRANSLIT runs BEFORE NFKD because these letters are atomic code points, not
    # base+combining-mark pairs: NFKD leaves 'ł' intact and the ascii encode then
    # DELETES it, so 'Błachowicz' silently became 'bachowicz'. Accented letters
    # (Čepo, Janičić) do decompose and were always fine -- the bug was confined to
    # the non-decomposing set above.
    #
    # This matters outside resolve(). resolve() papered over it with a second
    # transliterated lookup, but _pair/_results_map/settle_row call norm() directly:
    # a bout logged from the odds feed as 'Jan Blachowicz' produced the key
    # 'janblachowicz' while the same bout scraped as 'Jan Błachowicz' produced
    # 'janbachowicz', so the prediction could never settle and sat pending until
    # it aged out as a void.
    s = unicodedata.normalize("NFKD", (s or "").translate(TRANSLIT))
    return re.sub(r"[^a-z]", "", s.encode("ascii", "ignore").decode().lower())

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
    six Magomedovs must never be guessed between.

    Deliberately NOT loosened to (first-initial + surname). Measured against the
    1228-fighter ratings file, that key is ambiguous in 22 buckets — 'Lerone
    Murphy'/'Lauren Murphy' and 'Demetrious Johnson'/'DaMarques Johnson' among
    them — so it would have to refuse those anyway, while the 4-char first-name
    prefix below already accepts every unambiguous case. It also rescues nothing:
    on the card that prompted the check, none of the unresolved fighters had a
    surname present in the ratings file at all."""
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

def _results_map_delta(delta_csv):
    """results_delta.csv (fresh completed cards written by the results workflow) ->
    {(normA, normB, date): winner_norm}. This is how the ledger settles bouts that
    finished AFTER the last fighter_bouts.csv ratings scrape. Without it grade_all only
    ever sees the frozen ratings-baseline file, so no logged prediction from a new card
    can settle and the advertised LIVE record stays stuck at n=0."""
    res = {}
    if not delta_csv or not os.path.exists(delta_csv):
        return res
    with open(delta_csv) as f:
        for r in csv.DictReader(f):
            if (r.get("method") or "").strip() in ("Draw", "NC"):
                continue                 # no winner -> let the prediction void, never mis-settle
            w, l = norm(r.get("winner")), norm(r.get("loser"))
            d = (r.get("event_date") or "").strip()
            if not (w and l and d):
                continue
            res[(min(w, l), max(w, l), d)] = w
    return res

def grade_all(bouts_csv, delta_csv=None):
    ensure_files()
    if delta_csv is None:
        delta_csv = DELTA
    preds = load_csv(PLOG)
    if not preds: return 0, summarize([])
    done = {(r["date"],) + _pair(r["f1"], r["f2"]) for r in load_csv(GRADED)}
    res = _results_map(bouts_csv)
    # merge in fresh results (new cards not yet in the ratings scrape); keep the
    # authoritative bouts_csv winner if a bout somehow appears in both.
    for k, w in _results_map_delta(delta_csv).items():
        res.setdefault(k, w)
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
        # LIKE FOR LIKE. panel["acc"] above is over every graded bout; market["acc"] can
        # only be over the ones that carried a devigged consensus. Today those sets are
        # the same size, so the two figures happen to be comparable -- but the moment one
        # bout logs without a price they silently stop being, and nothing here would say
        # so. model_acc is the model's rate on the market's own subset, always.
        pacc = sum(1 for pm, _q, yy in M if (pm > 0.5) == (yy == 1)) / len(M)
        panel["market"] = {"n": len(M), "acc": round(100 * macc, 1),
                           "model_acc": round(100 * pacc, 1),
                           "disagree_n": len(dis),
                           "disagree_model_right": (round(100 * sum(
                               1 for pm, _q, yy in dis if (pm > 0.5) == (yy == 1)) / len(dis), 1)
                               if dis else None),
                           # THE HALF THIS PANEL NEVER CARRIED: how often the MARKET was
                           # right on exactly the bouts where the model claimed to know
                           # better. It is currently 100.0 -- the model is 0 for 5 against
                           # the price. "model right 0%" already reads badly, but a reader
                           # cannot tell from it whether the market was any good on those
                           # same bouts or whether they were all coin-flips nobody called.
                           # There are no draws in this ledger so the two sum to 100; it is
                           # counted rather than derived so it stays correct if that changes.
                           "disagree_market_right": (round(100 * sum(
                               1 for _p, qm, yy in dis if (qm > 0.5) == (yy == 1)) / len(dis), 1)
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
    _nodelta = os.path.join(tmp, "nodelta.csv")           # isolate from the real results_delta
    n, p = grade_all(rcsv, delta_csv=_nodelta)
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
    # BOTH HALVES OF THE DISAGREEMENT. The panel used to publish only the model's rate
    # on the bouts where it took the other side of the price. On the one disagreement
    # here the model said f1, the market said f2, and f2 won: model 0%, market 100%.
    assert m["disagree_market_right"] == 100.0, m
    # no draws in this ledger, so the two sum to 100 -- asserted so that a future change
    # (a draw/NC settling as anything but a void) has to come back through this test.
    assert m["disagree_model_right"] + m["disagree_market_right"] == 100.0, m
    # model_acc is over the priced subset, the same games market["acc"] is over. Both
    # graded bouts carry a q1 here, so it equals the overall acc -- the point is that it
    # is COMPUTED over M rather than reusing panel["acc"], which stops being comparable
    # the moment one bout logs without a consensus price.
    assert m["model_acc"] == 0.0, m
    n2, _ = grade_all(rcsv, delta_csv=_nodelta)
    assert n2 == 0                                  # idempotent grading
    json.dumps(p)
    # DELTA SETTLE: a bout that finished after the ratings scrape lives ONLY in
    # results_delta.csv — grade_all must settle it from there, else the LIVE ledger is
    # permanently stuck at n=0 (the actual production bug this fixes).
    dtmp = os.path.join(tmp, "delta.csv")
    with open(dtmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["event_date", "event", "winner", "loser", "method", "round"])
        w.writeheader()
        w.writerow({"event_date": recent, "event": "Fresh Card", "winner": "Manuel Torres",
                    "loser": "Rafael Fiziev", "method": "?", "round": 3})
    dm = _results_map_delta(dtmp)
    _a, _b = norm("Manuel Torres"), norm("Rafael Fiziev")
    assert dm[(min(_a, _b), max(_a, _b), recent)] == _a, "delta winner must map correctly"
    assert _results_map_delta(os.path.join(tmp, "missing.csv")) == {}   # missing file -> empty, no crash
    # a fresh temp ledger: the Fiziev/Torres prediction settles from delta alone (no bouts_csv row)
    _op, _og = PLOG, GRADED
    PLOG, GRADED = os.path.join(tmp, "p2.csv"), os.path.join(tmp, "g2.csv")
    log_card("Delta Card", recent, [{"f1": "Rafael Fiziev", "f2": "Manuel Torres", "p1": 0.62, "q1": 0.5}])
    _empty_bouts = os.path.join(tmp, "empty_bouts.csv")
    with open(_empty_bouts, "w", newline="") as f:
        csv.DictWriter(f, fieldnames=["fighter", "opp", "date", "won", "decided"]).writeheader()
    nd, pd_ = grade_all(_empty_bouts, delta_csv=dtmp)
    assert nd == 1 and pd_["n"] == 1, (nd, pd_)      # settled purely from results_delta
    PLOG, GRADED = _op, _og
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
    # NON-DECOMPOSING LETTERS. These are single code points, so NFKD alone leaves
    # them for the ascii encode to delete. norm() must transliterate them itself:
    # resolve() has a translit fallback but _pair/settle_row do not, and a settle
    # key that disagrees with the logging key never matches.
    assert norm("Jan Błachowicz") == "janblachowicz"
    assert norm("Jan Błachowicz") == norm("Jan Blachowicz"), \
        "diacritic and ascii spellings must produce ONE ledger key, else no settle"
    assert norm("Michał Oleksiejczuk") == "michaloleksiejczuk"
    assert norm("Jørgen Sørensen") == "jorgensorensen"
    assert norm("Đorđe Weiß") == "dordeweiss"
    # combining-mark accents already decomposed correctly; lock that in so the
    # translit change above cannot regress them
    assert norm("Vlasto Čepo") == "vlastocepo"
    assert norm("Miloš Janičić") == "milosjanicic"
    assert norm("Óscar Piñera") == "oscarpinera"
    # the pair key is what actually settles a bout — it must survive the spelling
    # the results scrape happens to use
    assert _pair("Jan Blachowicz", "Navajo Stirling") == _pair("Jan Błachowicz", "Navajo Stirling")
    # AMBIGUITY MUST REFUSE, NOT GUESS. A wrong resolution logs a prediction
    # against a stranger's record, which is strictly worse than a dropped bout.
    A = {norm(x) for x in ["Lerone Murphy", "Lauren Murphy", "Demetrious Johnson",
                           "DaMarques Johnson", "Justin Tafa", "Junior Tafa"]}
    assert resolve("L Murphy", A) is None      # shared initial+surname, two people
    assert resolve("J Tafa", A) is None        # brothers -> refuse
    assert resolve("D Johnson", A) is None
    assert resolve("Lerone Murphy", A) == norm("Lerone Murphy")   # unambiguous still resolves
    assert resolve("Demetrious Johnson", A) == norm("Demetrious Johnson")
    print("UFC LEDGER SELFTEST PASS — log/settle idempotent, accents, non-decomposing "
          "letters (ł/ø/đ/ß), pair orientation, ambiguity refused, void window, "
          "Brier exact, market disagreement live")
    return 0

if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv: sys.exit(selftest())
    print("library — wired into build_site.py")
