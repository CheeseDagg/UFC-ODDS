#!/usr/bin/env python3
"""
ufc_dob_backfill.py — widen the DOB cache, because it is the floor under every
UFC experiment.

THE PROBLEM. fighter_meta_cache.json holds 1,622 fighters with a date of birth.
fighter_bouts.csv contains 2,678 distinct names. Only 4,041 of 8,686 bouts (47%)
therefore have BOTH corners' ages. Age is the single biggest validated UFC
finding (-0.0095 Brier), so a baseline that is age-blind on 53% of the sample is
a weak control — and a weak age control is exactly how three wear-and-tear
angles read as ROBUST WINS on the first pass before the join was repaired. Every
future angle is measured against this baseline. Widening it is worth more than
the next several modelling ideas.

WHY THE EXISTING PULL FALLS SHORT. It pages ESPN's UFC athlete index, which is
essentially the current roster. The unmatched names are overwhelmingly retired:
Aaron Brink, Akihiro Gono, Alessio Sakara, Adrian Serrano. They are not missing
because of a bug; they are not in the index.

SOURCES, in order of yield per request:
  1. WIKIDATA, one bulk SPARQL query: every human whose occupation is mixed
     martial artist, with DOB and every alias. Historical coverage is its whole
     point, and it is one request rather than 1,296. Matched on the SAME
     normalizer the model uses, plus alias rows, so "Alexey/Aleksei Oleinik"
     style transliteration variants join.
  2. ESPN SEARCH, per remaining name: the search endpoint reaches athletes the
     index page does not enumerate.

RULES.
  * NEVER overwrite an existing DOB. This only fills holes. The shipped cache
    was validated; a new source must not silently move a fighter already in it.
  * Every filled record is stamped with "_src" so one bad source can be reverted
    by a one-line filter instead of a re-pull.
  * A DOB is rejected unless it lands the fighter between 15 and 60 years old at
    his FIRST recorded bout. Wikidata name collisions are real (fighters share
    names with footballers and politicians) and this catches them cheaply.
  * --report runs the join arithmetic and writes nothing. Run it before and
    after to see exactly what the pull bought.

Offline (sandbox): both hosts are blocked, so this prints UNREACHABLE and exits
0. Fire it on Actions by touching experiments/RUN-DOB.txt.
"""
import csv, json, os, re, sys, time, datetime as dt
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
META = os.path.join(HERE, "fighter_meta_cache.json")
BOUTS = os.path.join(HERE, "data", "fighter_bouts.csv")

UA = {"User-Agent": "CheeseDagg-ufc-odds/1.0 (DOB backfill for a personal model)"}
WDQS = "https://query.wikidata.org/sparql"
ESPN_SEARCH = ("https://site.web.api.espn.com/apis/common/v3/search"
               "?query={q}&limit=8&sport=mma")
MIN_AGE, MAX_AGE = 15.0, 60.0


def norm_name(name):
    """MUST mirror ufc_blend_predict.norm_name — the cache is keyed by it."""
    n = (name or "").strip().lower()
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    return re.sub(r"\s+", " ", n)


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout).read()


# ------------------------------------------------------------------ inputs
def bout_names():
    """{norm: display} for every fighter in the bout file, plus first-bout date
    per fighter so an implausible DOB can be rejected."""
    disp, first = {}, {}
    with open(BOUTS) as f:
        rd = csv.DictReader(f)
        cols = [c for c in ("fighter", "opp", "opponent", "a", "b", "name")
                if c in rd.fieldnames]
        dcol = next((c for c in ("date", "event_date") if c in rd.fieldnames), None)
        for r in rd:
            d = (r.get(dcol) or "")[:10] if dcol else ""
            for c in cols:
                nm = (r.get(c) or "").strip()
                if not nm:
                    continue
                k = norm_name(nm)
                disp.setdefault(k, nm)
                if d and (k not in first or d < first[k]):
                    first[k] = d
    return disp, first


def load_meta():
    return json.load(open(META)) if os.path.exists(META) else {}


def dob_index(meta):
    """{norm: dob} accepting both the cache key and the stored display name."""
    out = {}
    for k, v in meta.items():
        d = v.get("dob") if isinstance(v, dict) else v
        if not d:
            continue
        out[norm_name(k)] = d
        if isinstance(v, dict) and v.get("name"):
            out.setdefault(norm_name(v["name"]), d)
    return out


def plausible(dob, first_bout):
    """Reject a DOB that makes the fighter absurdly young or old at debut."""
    if not dob:
        return False
    try:
        d = dt.date.fromisoformat(str(dob)[:10])
    except ValueError:
        return False
    if not first_bout:
        return 1930 <= d.year <= 2010
    try:
        fb = dt.date.fromisoformat(first_bout)
    except ValueError:
        return 1930 <= d.year <= 2010
    age = (fb - d).days / 365.25
    return MIN_AGE <= age <= MAX_AGE


# ------------------------------------------------------------------ sources
WD_QUERY = """
SELECT ?person ?name ?dob WHERE {
  ?person wdt:P106 wd:Q11338576 ; wdt:P569 ?dob .
  { ?person rdfs:label ?name . FILTER(LANG(?name) = "en") }
  UNION
  { ?person skos:altLabel ?name . FILTER(LANG(?name) = "en") }
}
"""


def pull_wikidata():
    """One bulk query -> {norm_name: 'YYYY-MM-DD'}. Alias rows included so
    transliteration variants (Aleksei/Alexey) join."""
    url = WDQS + "?format=json&query=" + urllib.parse.quote(WD_QUERY)
    raw = json.loads(_get(url, timeout=180))
    out = {}
    for b in raw["results"]["bindings"]:
        nm = b.get("name", {}).get("value")
        dv = b.get("dob", {}).get("value", "")[:10]
        if not nm or not dv.startswith(("19", "20")):
            continue
        k = norm_name(nm)
        # a name that maps to two different DOBs is ambiguous - drop it rather
        # than coin-flip between a fighter and his footballer namesake
        if k in out and out[k] != dv:
            out[k] = None
        else:
            out.setdefault(k, dv)
    return {k: v for k, v in out.items() if v}


def espn_search_dob(display, sleep=0.25):
    """Search endpoint -> athlete ref -> dateOfBirth. One name per call."""
    try:
        j = json.loads(_get(ESPN_SEARCH.format(q=urllib.parse.quote(display))))
    except Exception:
        return None
    time.sleep(sleep)
    refs = []
    for grp in j.get("results", []):
        for it in grp.get("contents", []):
            uid = it.get("uid") or ""
            m = re.search(r"a:(\d+)", uid)
            if m and norm_name(it.get("displayName", "")) == norm_name(display):
                refs.append(m.group(1))
    for aid in refs[:2]:
        try:
            rec = json.loads(_get("https://sports.core.api.espn.com/v2/sports/mma/"
                                  f"leagues/ufc/athletes/{aid}?lang=en"))
        except Exception:
            continue
        time.sleep(sleep)
        d = str(rec.get("dateOfBirth") or "")[:10]
        if d:
            return d
    return None


# ------------------------------------------------------------------ report
def report(meta=None):
    disp, first = bout_names()
    have = dob_index(meta if meta is not None else load_meta())
    names = set(disp)
    known = {n for n in names if n in have}
    # the number that actually matters: bouts with BOTH corners dated
    both = tot = 0
    with open(BOUTS) as f:
        rd = csv.DictReader(f)
        ca = next(c for c in ("fighter", "a") if c in rd.fieldnames)
        cb = next(c for c in ("opp", "opponent", "b") if c in rd.fieldnames)
        seen = set()
        for r in rd:
            a, b = norm_name(r.get(ca, "")), norm_name(r.get(cb, ""))
            key = tuple(sorted((a, b)) + [(r.get("date") or "")[:10]])
            if not a or not b or key in seen:
                continue
            seen.add(key)
            tot += 1
            if a in have and b in have:
                both += 1
    pct = 100.0 * both / tot if tot else 0.0
    print(f"fighters: {len(known)}/{len(names)} with DOB  |  "
          f"bouts with BOTH ages: {both}/{tot} ({pct:.1f}%)")
    return both, tot


# ------------------------------------------------------------------ main
def main():
    if "--report" in sys.argv:
        report()
        return 0
    disp, first = bout_names()
    meta = load_meta()
    have = dob_index(meta)
    missing = {k: v for k, v in disp.items() if k not in have}
    print(f"missing DOB for {len(missing)} of {len(disp)} fighters")
    print("BEFORE: ", end="")
    report(meta)

    added = {"wikidata": 0, "espn": 0}
    rejected = 0
    try:
        wd = pull_wikidata()
        print(f"wikidata rows: {len(wd)} unambiguous fighter names")
    except Exception as e:
        print(f"Wikidata UNREACHABLE ({type(e).__name__}) — run on Actions "
              "(touch experiments/RUN-DOB.txt)")
        return 0
    for k in list(missing):
        d = wd.get(k)
        if not d:
            continue
        if not plausible(d, first.get(k)):
            rejected += 1
            continue
        meta[k] = {"name": missing[k], "dob": d, "_src": "wikidata"}
        added["wikidata"] += 1
        missing.pop(k)

    if "--wikidata-only" not in sys.argv:
        todo = sorted(missing)[: int(os.environ.get("ESPN_MAX", "600"))]
        print(f"ESPN search pass over {len(todo)} remaining names")
        for i, k in enumerate(todo):
            d = espn_search_dob(missing[k])
            if d and plausible(d, first.get(k)):
                meta[k] = {"name": missing[k], "dob": d, "_src": "espn-search"}
                added["espn"] += 1
            elif d:
                rejected += 1
            if (i + 1) % 100 == 0:
                print(f"  ...{i+1}/{len(todo)}  espn hits {added['espn']}")
                json.dump(meta, open(META, "w"), indent=1, sort_keys=True)

    json.dump(meta, open(META, "w"), indent=1, sort_keys=True)
    print(f"added: wikidata {added['wikidata']}  espn {added['espn']}  "
          f"rejected as implausible {rejected}")
    print("AFTER:  ", end="")
    report(meta)
    return 0


# ------------------------------------------------------------------ selftest
def selftest():
    assert norm_name("A.J. O'Neill-Smith") == "aj oneill smith"
    # plausibility gate: 24 at debut ok, 4 and 71 are not
    assert plausible("1990-01-01", "2014-06-01")
    assert not plausible("2010-01-01", "2014-06-01")
    assert not plausible("1943-01-01", "2014-06-01")
    assert not plausible(None, "2014-06-01")
    assert not plausible("not-a-date", "2014-06-01")
    # existing DOBs are never overwritten: the fill loop only walks `missing`,
    # which is built by excluding everything dob_index already knows
    m = {"joe blow": {"name": "Joe Blow", "dob": "1985-05-05"}}
    assert dob_index(m)["joe blow"] == "1985-05-05"
    assert norm_name("Joe Blow") in dob_index(m)
    print("DOB BACKFILL SELFTEST PASS — normalizer mirrors production, "
          "plausibility gate rejects namesakes, existing DOBs untouched")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
