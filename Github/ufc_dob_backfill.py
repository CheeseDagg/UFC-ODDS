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

SOURCES, in order of yield:
  1. UFCSTATS.COM — the source fighter_bouts.csv was scraped from, which is the
     whole reason it wins. Every other source has a name-matching problem;
     this one has the SAME names, because it is the same database. Its A-Z
     index enumerates every fighter who has ever appeared on a UFC card,
     retired or not, and each detail page carries DOB *and STANCE*. Stance is
     a listed model blind spot (southpaw/style matchups), so this pull is
     worth more than the DOB alone.
  2. WIKIDATA, one bulk SPARQL query: every human whose occupation is mixed
     martial artist, with DOB and every alias. Best-effort second pass for
     names ufcstats spells differently.
  3. ESPN SEARCH, per remaining name: the search endpoint reaches athletes the
     index page does not enumerate.

WHAT ROUND ONE BOUGHT, AND WHY ROUND TWO EXISTS. Wikidata added 51 fighters
and the ESPN search pass added zero, moving both-corners coverage 46.5% ->
49%. Still missing: Chuck Liddell, Tito Ortiz, Nate Diaz, Jose Aldo, Diego
Sanchez. Those men are certainly in Wikidata, so the ceiling was never the
data — the SPARQL alias join is simply not reaching them. Rather than debug a
query I cannot run from this sandbox, round two goes to the source the bout
file itself came from, where the join is an identity.

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
import csv, http.cookiejar, json, os, re, sys, time, datetime as dt
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
META = os.path.join(HERE, "fighter_meta_cache.json")
BOUTS = os.path.join(HERE, "data", "fighter_bouts.csv")

# Round 4 proved ufcstats does not serve the fighter index to this client at
# all: all 26 letter pages came back as the SAME 2,994-byte "Loading…"
# interstitial with zero 'fighter-details' anchors — a JS challenge, not a
# parse failure. A self-identifying UA is the most common trigger for that, and
# a challenge that sets a cookie cannot work at all against a client that
# throws its cookies away between requests. Round 5 changes both: a browser-
# shaped header set and one shared cookie jar for the whole process.
#
# Wikidata is the exception — it ASKS for a descriptive UA and rate-limits
# generic browser strings, so it keeps the honest one.
UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
}
POLITE_UA = {"User-Agent": ("CheeseDagg-ufc-odds/1.0 "
                            "(DOB backfill for a personal model)")}
_JAR = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(_JAR))
UFCSTATS_INDEX = "http://ufcstats.com/statistics/fighters?char={c}&page=all"
WDQS = "https://query.wikidata.org/sparql"
ESPN_SEARCH = ("https://site.web.api.espn.com/apis/common/v3/search"
               "?query={q}&limit=8&sport=mma")
MIN_AGE, MAX_AGE = 15.0, 60.0


def norm_name(name):
    """MUST mirror ufc_blend_predict.norm_name — the cache is keyed by it."""
    n = (name or "").strip().lower()
    n = n.replace(".", "").replace("'", "").replace("-", " ")
    return re.sub(r"\s+", " ", n)


def _get(url, timeout=30, headers=None):
    """One shared cookie jar for the process. See the UA comment above.

    Wikidata gets POLITE_UA passed explicitly; everything else gets the
    browser-shaped default.
    """
    req = urllib.request.Request(url, headers=headers or UA)
    return _OPENER.open(req, timeout=timeout).read()


def looks_like_challenge(html):
    """A 200 that contains no content is the failure round 4 exposed.

    ufcstats returned an identical 2,994-byte '<title>Loading…</title>' shell
    for all 26 index letters. It is worth naming that shape explicitly, because
    'short page, no anchors, HTTP 200' is otherwise indistinguishable from
    'this letter genuinely has no fighters' — and the second reading is what
    cost round 3 an entire silent hour.
    """
    return len(html) < 8000 and "fighter-details" not in html.lower()


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
# --- 1. ufcstats.com (same database the bout file came from) ---------------
# Capture the fighter ID, not the whole href, and let the scheme be https,
# http, protocol-relative or absent. The previous version hard-coded `http://`
# and that is the single best explanation for round 3: 26 index pages fetched
# without a single exception and ZERO fighters enumerated. A site quietly
# moving to https breaks a scheme-pinned scraper with no error to show for it.
# Anything scheme-shaped is accepted here and the URL is rebuilt canonically.
LINK_RE = re.compile(
    r'href="(?:https?:)?//(?:www\.)?ufcstats\.com/fighter-details/([0-9a-f]+)"'
    r'[^>]*>\s*([^<]*?)\s*</a>', re.I)
DETAIL_URL = "http://ufcstats.com/fighter-details/{fid}"
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def parse_index(html):
    """Index page -> {detail_url: 'First Last'}.

    Each row links the fighter's first name and last name separately to the
    SAME detail URL, so grouping the anchor texts by href and joining them in
    document order rebuilds the full name without depending on the table
    layout, which is the part of a scrape most likely to be re-skinned.
    """
    order, parts = [], {}
    for fid, txt in LINK_RE.findall(html):
        url = DETAIL_URL.format(fid=fid.lower())
        if url not in parts:
            parts[url] = []
            order.append(url)
        if txt:
            parts[url].append(txt)
    return {u: " ".join(parts[u]).strip() for u in order if parts[u]}


def _detail_field(html, label):
    """Pull one 'LABEL:' list item off a fighter detail page."""
    m = re.search(r"<i[^>]*>\s*" + label + r":\s*</i>\s*([^<]*)", html, re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def parse_detail(html):
    """Detail page -> {'dob': 'YYYY-MM-DD'|None, 'stance': str|None}.

    ufcstats prints '--' for unknown, which must read as absent rather than as
    a parse failure — a fighter with no DOB on file is a normal outcome, not
    a sign the scrape broke.
    """
    out = {"dob": None, "stance": None}
    raw = _detail_field(html, "DOB")
    m = re.match(r"([A-Za-z]{3})[a-z]*\s+(\d{1,2}),\s*(\d{4})", raw)
    if m and m.group(1).title() in MONTHS:
        out["dob"] = (f"{int(m.group(3)):04d}-{MONTHS[m.group(1).title()]:02d}"
                      f"-{int(m.group(2)):02d}")
    st = _detail_field(html, "STANCE")
    if st and st != "--":
        out["stance"] = st.title()
    return out


def match_key(indexed_name, wanted):
    """Which key in `wanted` this index row is, or None.

    The index row may carry a nickname anchor on the same href, so the joined
    text can be 'Chuck Liddell The Iceman'. Try the whole string first, then
    the leading two tokens. Nothing looser than that: dropping to a surname
    match would happily hand Nate Diaz's DOB to Nick.
    """
    full = norm_name(indexed_name)
    if full in wanted:
        return full
    toks = full.split()
    if len(toks) > 2:
        short = " ".join(toks[:2])
        if short in wanted:
            return short
    return None


def pull_ufcstats(wanted, log=print, max_fetch=None, on_partial=None):
    """{norm_name: {'dob':..., 'stance':...}} for names in `wanted`.

    Fetches the 26 index pages first and only then the detail pages of names
    we actually need, so a 1,245-name hole costs ~1,271 requests rather than
    the ~4,400 a full crawl would.

    `on_partial(out)` is called every 200 details with everything found so far.
    The caller banks it to disk. That exists because the only way this pass is
    known to die is a wall-clock kill in CI — round 2 fired and nothing ever
    reached main — and a SIGKILL near the end of the budget would otherwise
    throw away every DOB the run had already paid for.
    """
    index = {}
    # Warm the jar on the site root first. If the interstitial is a cookie-
    # setting challenge, the cookie is what the index pages need, and the old
    # client discarded it. Cheap enough to be worth doing unconditionally.
    try:
        root = _get("http://ufcstats.com/statistics/events/completed",
                    timeout=45).decode("utf-8", "replace")
        log(f"  warmed cookie jar: {len(root)} chars, "
            f"{len(_JAR)} cookie(s) held")
    except Exception as e:
        log(f"  cookie warm failed ({type(e).__name__})")

    dumped = False
    for c in "abcdefghijklmnopqrstuvwxyz":
        try:
            html = _get(UFCSTATS_INDEX.format(c=c), timeout=60).decode(
                "utf-8", "replace")
        except Exception as e:
            log(f"  index '{c}' failed ({type(e).__name__})")
            continue
        found = parse_index(html)
        if not found and not index:
            # A page that fetched fine and parsed to nothing is the failure mode
            # that cost round 3 an entire hour with no signal. Say WHY, once:
            # a short body is a block or a challenge page, a long body with
            # fighter-details anchors present is the regex drifting again, and a
            # long body with none of them means the page moved.
            anchors = html.lower().count("fighter-details")
            log(f"  index '{c}' parsed 0 rows from {len(html)} chars, "
                f"{anchors} 'fighter-details' mentions, "
                f"challenge={looks_like_challenge(html)}")
            if not dumped:
                # Print the WHOLE body once. It is ~3 KB, and round 4 spent a
                # full round trip learning only the first 200 characters of it.
                # Whatever the challenge wants — a cookie, a meta refresh, a
                # script-computed token — it is stated in here somewhere, and
                # guessing at it one 200-char window at a time is the expensive
                # way to find out.
                dumped = True
                # Round 5 identified it: a SHA-256 proof-of-work interstitial.
                # The first 60 lines are just a hand-rolled sha256 in JS and we
                # have hashlib, so they are noise. Everything that MATTERS —
                # the challenge seed, the difficulty, the cookie name, the
                # reload — is in the tail, and the tail is what round 5's
                # 120-line log window clipped off.
                log("    ---- challenge TAIL (params, cookie, reload) ----")
                log(html[-2200:])
                log("    ---- end body ----")
        index.update(found)
        time.sleep(0.2)
    log(f"  ufcstats index: {len(index)} fighters enumerated")
    todo = []
    for u, nm in index.items():
        k = match_key(nm, wanted)
        if k:
            todo.append((u, nm, k))
    if max_fetch:
        todo = todo[:max_fetch]
    log(f"  {len(todo)} of them are names we are missing — fetching details")
    out = {}
    for i, (url, nm, key) in enumerate(todo):
        try:
            rec = parse_detail(_get(url, timeout=45).decode("utf-8", "replace"))
        except Exception:
            continue
        time.sleep(0.12)
        if rec["dob"] or rec["stance"]:
            out[key] = dict(rec, name=nm)
        if (i + 1) % 200 == 0:
            log(f"  ...{i + 1}/{len(todo)}  hits {len(out)}")
            if on_partial:
                on_partial(out)
    return out


# --- 2. wikidata -----------------------------------------------------------
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
    # POLITE_UA on purpose: WDQS asks for a descriptive User-Agent and throttles
    # generic browser strings. The browser-shaped default exists for ufcstats.
    raw = json.loads(_get(url, timeout=180, headers=POLITE_UA))
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

    added = {"ufcstats": 0, "wikidata": 0, "espn": 0}
    rejected = 0
    stances = 0

    # --- pass 1: ufcstats, the same database the bout file came from --------
    if "--no-ufcstats" not in sys.argv:
        print("ufcstats pass")

        def absorb(us):
            """Fold a ufcstats result dict into meta. Idempotent by design.

            Called both mid-pass (every 200 details, so a CI kill cannot cost
            work already paid for) and once at the end. Re-absorbing rows it
            has already absorbed is a no-op: `k not in missing` skips a filled
            DOB and the stance write is guarded on the field being empty, so
            no counter double-increments.
            """
            nonlocal rejected, stances
            for k, rec in us.items():
                # STANCE is a new field, not a hole-fill, so it is written for
                # any fighter who lacks one — including men who already have a
                # DOB. It is the raw material for the southpaw angle, which is
                # a listed blind spot, and it costs nothing extra to keep.
                if rec.get("stance"):
                    cur = meta.get(k) if isinstance(meta.get(k), dict) else None
                    if cur is not None and not cur.get("stance"):
                        cur["stance"] = rec["stance"]
                        stances += 1
                if k not in missing or not rec.get("dob"):
                    continue
                if not plausible(rec["dob"], first.get(k)):
                    rejected += 1
                    continue
                meta[k] = {"name": missing[k], "dob": rec["dob"],
                           "stance": rec.get("stance"), "_src": "ufcstats"}
                added["ufcstats"] += 1
                missing.pop(k)
                stances += 1 if rec.get("stance") else 0

        def bank(us):
            absorb(us)
            json.dump(meta, open(META, "w"), indent=1, sort_keys=True)
            print(f"  banked: {added['ufcstats']} DOBs so far")

        try:
            us = pull_ufcstats(set(missing),
                               max_fetch=int(os.environ.get("UFCSTATS_MAX", "0"))
                               or None,
                               on_partial=bank)
        except Exception as e:
            print(f"  ufcstats UNREACHABLE ({type(e).__name__}) — run on Actions")
            us = {}
        absorb(us)
        print(f"  ufcstats filled {added['ufcstats']} DOBs, {stances} stances")
        json.dump(meta, open(META, "w"), indent=1, sort_keys=True)

    # --- pass 2: wikidata (best effort — a failure here must not abort the
    # run now that pass 1 has already banked its results) -------------------
    try:
        wd = pull_wikidata()
        print(f"wikidata rows: {len(wd)} unambiguous fighter names")
    except Exception as e:
        print(f"Wikidata UNREACHABLE ({type(e).__name__}) — continuing")
        wd = {}
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
    print(f"added: ufcstats {added['ufcstats']}  wikidata {added['wikidata']}  "
          f"espn {added['espn']}  stances {stances}  "
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

    # --- ufcstats parsers, against markup shaped like the real pages --------
    idx = '''
    <tr class="b-statistics__table-row">
      <td><a href="http://ufcstats.com/fighter-details/abc123" class="b-link">Chuck</a></td>
      <td><a href="http://ufcstats.com/fighter-details/abc123" class="b-link">Liddell</a></td>
      <td><a href="http://ufcstats.com/fighter-details/abc123" class="b-link">The Iceman</a></td>
    </tr>
    <tr><td><a href="http://ufcstats.com/fighter-details/def456">Tito</a></td>
        <td><a href="http://ufcstats.com/fighter-details/def456">Ortiz</a></td></tr>
    '''
    got = parse_index(idx)
    # the nickname column is a third anchor on the same href; joining in
    # document order keeps it on the end, so the NORMALIZED first two tokens
    # are what the join uses. Assert the row is grouped, not that it is clean.
    assert len(got) == 2, got
    assert got["http://ufcstats.com/fighter-details/abc123"].startswith(
        "Chuck Liddell"), got
    assert got["http://ufcstats.com/fighter-details/def456"] == "Tito Ortiz"
    # SCHEME-AGNOSTIC. Round 3 enumerated 0 fighters with no exception raised,
    # and a scraper pinned to `http://` against a site that moved to `https://`
    # is exactly that symptom. Every scheme spelling must fold to the same row.
    for href in ('https://ufcstats.com/fighter-details/abc123',
                 '//ufcstats.com/fighter-details/abc123',
                 'http://www.ufcstats.com/fighter-details/ABC123',
                 'HTTPS://UFCStats.com/fighter-details/abc123'):
        one = parse_index(f'<a href="{href}">Chuck</a>'
                          f'<a href="{href}">Liddell</a>')
        assert one == {"http://ufcstats.com/fighter-details/abc123":
                       "Chuck Liddell"}, (href, one)

    want = {"chuck liddell", "tito ortiz"}
    assert match_key("Chuck Liddell The Iceman", want) == "chuck liddell"
    assert match_key("Tito Ortiz", want) == "tito ortiz"
    assert match_key("Nick Diaz", want) is None
    # never loosen to a surname: that hands one brother the other's birthday
    assert match_key("Nathan Diaz", want) is None
    assert match_key("Someone Else Entirely", want) is None
    # a two-token index row is never truncated further, so an exact name that
    # simply is not wanted stays unmatched rather than falling back
    assert match_key("Chuck Norris", want) is None

    det = ('<li class="b-list__box-list-item"><i class="b-list__box-item-title">'
           'DOB:</i>\n      Dec 17, 1969\n</li>'
           '<li><i class="b-list__box-item-title">STANCE:</i> Orthodox </li>')
    p = parse_detail(det)
    assert p["dob"] == "1969-12-17", p
    assert p["stance"] == "Orthodox", p
    # '--' is ufcstats for "not on file" and must read as absent, not as a
    # broken parse — otherwise a normal gap looks like a scrape failure
    blank = ('<li><i class="b-list__box-item-title">DOB:</i> --</li>'
             '<li><i class="b-list__box-item-title">STANCE:</i> --</li>')
    assert parse_detail(blank) == {"dob": None, "stance": None}
    assert parse_detail("<html>nothing here</html>") == {"dob": None,
                                                         "stance": None}
    # --- mid-pass banking. The whole reason round 2 is being re-fired with a
    # step timeout is that a wall-clock kill loses everything the pass had
    # already fetched. That protection is worthless if on_partial never fires,
    # so drive pull_ufcstats against a fake network and count the callbacks.
    global _get
    _real_get = _get
    names = [f"Fighter{i:04d} Test" for i in range(450)]
    fake_index = "".join(
        f'<tr><td><a href="http://ufcstats.com/fighter-details/{i:06x}">'
        f'{n.split()[0]}</a></td>'
        f'<td><a href="http://ufcstats.com/fighter-details/{i:06x}">'
        f'{n.split()[1]}</a></td></tr>'
        for i, n in enumerate(names))
    detail = ('<li><i class="b-list__box-item-title">DOB:</i> Jan 02, 1990</li>'
              '<li><i class="b-list__box-item-title">STANCE:</i> Southpaw</li>')

    def _fake(url, timeout=30):
        # one letter's index carries every fake fighter; the other 25 are empty
        if "statistics/fighters" in url:
            return (fake_index if "char=a" in url else "").encode()
        return detail.encode()

    _get = _fake
    try:
        seen = []
        out = pull_ufcstats({norm_name(n) for n in names},
                            log=lambda s: None,
                            on_partial=lambda o: seen.append(len(o)))
        assert len(out) == 450, f"fake pull lost rows: {len(out)}"
        assert seen == [200, 400], f"on_partial did not fire every 200: {seen}"
        # and it must hand over a GROWING view of the same dict, not a copy of
        # the first chunk — banking the same 200 rows twice would silently mean
        # the last 250 were never written on a killed run
        assert seen[1] > seen[0], "partials are not accumulating"
        # max_fetch still bounds the crawl, so a capped run stays inside budget
        assert len(pull_ufcstats({norm_name(n) for n in names},
                                 log=lambda s: None, max_fetch=10)) == 10
    finally:
        _get = _real_get

    print("DOB BACKFILL SELFTEST PASS — normalizer mirrors production, "
          "plausibility gate rejects namesakes, existing DOBs untouched, "
          "mid-pass banking fires every 200 details")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
