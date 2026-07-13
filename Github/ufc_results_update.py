#!/usr/bin/env python3
"""
ufc_results_update.py — keep fight RESULTS current, incrementally, on Actions.

The fighter-ratings dataset is a June-14 baseline built by the offline ridge
model. Skills drift slowly; RECORDS drift every Saturday. This script closes
that gap: it scrapes ufcstats.com for events completed AFTER the stored
through-date, parses each fight's result, and appends them to
data/results_delta.csv. build_widget merges the delta into every fighter's
displayed history/record at build time — ratings numbers untouched.

State:   data/results_through.txt   (a date; only events after it are pulled)
Output:  data/results_delta.csv     (event_date,event,winner,loser,method,round)

Fail-loud: if new events exist but zero fights parse, exit 1 — a silent empty
append after a markup change is exactly the failure mode we refuse to have.
"""
import os, re, csv, sys, time, datetime as dt
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
STATE = os.path.join(DATA, "results_through.txt")
DELTA = os.path.join(DATA, "results_delta.csv")
LIST_URL = "http://ufcstats.com/statistics/events/completed?page=all"
UA = {"User-Agent": "Mozilla/5.0 (results updater; github actions)"}

def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def parse_event_list(html):
    """[(date, name, url)] for completed events, newest first."""
    out = []
    # each event row: <a class="b-link ..." href="EVENT_URL">NAME</a> ... <span class="b-statistics__date">DATE</span>
    for m in re.finditer(
        r'<a[^>]+class="b-link[^"]*"[^>]+href="(http://ufcstats\.com/event-details/[^"]+)"[^>]*>\s*([^<]+?)\s*</a>'
        r'.*?<span[^>]*class="b-statistics__date"[^>]*>\s*([^<]+?)\s*</span>',
        html, re.S):
        url, name, date_s = m.group(1), m.group(2).strip(), m.group(3).strip()
        try:
            d = dt.datetime.strptime(date_s, "%B %d, %Y").date()
        except ValueError:
            continue
        out.append((d, name, url))
    return out

def parse_event_fights(html):
    """[(winner, loser, method, round)] from an event-details page.
    Each fight row on ufcstats: the row is marked win/nc/draw via i-flag; the
    two fighter names are the first two b-link entries in the row; winner is
    listed first on completed bouts with a 'win' flag."""
    fights = []
    rows = re.split(r'<tr[^>]*class="b-fight-details__table-row[^"]*"', html)[1:]
    for row in rows:
        flag = re.search(r'b-flag__text">\s*(win|nc|draw)\s*<', row)
        names = re.findall(r'<a[^>]+class="b-link\s+b-link_style_black"[^>]*>\s*([^<]+?)\s*</a>', row)
        # columns render as <p class="b-fight-details__table-text">VALUE</p>;
        # METHOD and ROUND live among them — method is the first cell containing
        # KO/SUB/DEC markers, round is a lone small integer cell
        cells = [c.strip() for c in re.findall(r'<p[^>]*b-fight-details__table-text[^>]*>\s*([^<]*?)\s*</p>', row)]
        if not flag or len(names) < 2:
            continue
        method = next((c for c in cells if re.match(r'^(KO/TKO|SUB|U-DEC|S-DEC|M-DEC|DEC|DQ|Overturned|CNC)', c)), "")
        rnd = next((c for c in cells if re.fullmatch(r'[1-5]', c)), "")
        if flag.group(1) == "win":
            fights.append((names[0], names[1], method, rnd))
        elif flag.group(1) in ("nc", "draw"):
            fights.append((names[0], names[1], flag.group(1).upper(), rnd))
    return fights

def method_short(m):
    m = (m or "").upper()
    if m.startswith("KO"): return "KO"
    if m.startswith("SUB"): return "SUB"
    if "DEC" in m: return "DEC"
    if m in ("NC", "CNC", "OVERTURNED"): return "NC"
    if m == "DRAW": return "DRAW"
    if m.startswith("DQ"): return "DQ"
    return m[:8] or "?"

def main():
    through = dt.date(2026, 6, 14)
    if os.path.exists(STATE):
        through = dt.date.fromisoformat(open(STATE).read().strip())
    print(f"results through: {through}")

    events = parse_event_list(fetch(LIST_URL))
    if not events:
        sys.exit("FATAL: event list parsed to zero events — ufcstats markup changed?")
    today = dt.date.today()
    new = [(d, n, u) for (d, n, u) in events if through < d <= today]
    print(f"events on ufcstats: {len(events)} | new since through-date: {len(new)}")
    if not new:
        print("nothing to do — records already current"); return

    added, newest = 0, through
    rows = []
    for d, name, url in sorted(new):
        try:
            fights = parse_event_fights(fetch(url))
        except Exception as e:
            print(f"  [skip] {name}: {type(e).__name__}"); continue
        print(f"  {d} {name}: {len(fights)} fights")
        for w, l, meth, rnd in fights:
            rows.append([d.isoformat(), name, w, l, method_short(meth), rnd])
            added += 1
        newest = max(newest, d)
        time.sleep(1.0)                      # polite to ufcstats

    if new and added == 0:
        sys.exit("FATAL: new events found but ZERO fights parsed — markup changed; refusing silent no-op")

    os.makedirs(DATA, exist_ok=True)
    exists = os.path.exists(DELTA)
    seen = set()
    if exists:
        for r in csv.reader(open(DELTA)):
            seen.add(tuple(r[:4]))
    with open(DELTA, "a", newline="") as f:
        wtr = csv.writer(f)
        if not exists:
            wtr.writerow(["event_date","event","winner","loser","method","round"])
        for r in rows:
            if tuple(r[:4]) in seen: continue
            wtr.writerow(r)
    open(STATE, "w").write(newest.isoformat())
    print(f"\nappended {added} results · through-date now {newest}")

# ---------------------------------------------------------------- selftest
FIXTURE_LIST = '''
<tr><td><a class="b-link b-link_style_black" href="http://ufcstats.com/event-details/aaa111">UFC 329: McGregor vs. Holloway</a>
<span class="b-statistics__date">July 11, 2026</span></td></tr>
<tr><td><a class="b-link b-link_style_black" href="http://ufcstats.com/event-details/bbb222">UFC Fight Night: Old vs. Older</a>
<span class="b-statistics__date">May 16, 2026</span></td></tr>
'''
FIXTURE_EVENT = '''
<tr class="b-fight-details__table-row x">
 <td><i class="b-flag"><i class="b-flag__inner"><i class="b-flag__text">win</i></i></i></td>
 <td><a class="b-link b-link_style_black" href="f1">Benoit Saint Denis</a>
     <a class="b-link b-link_style_black" href="f2">Paddy Pimblett</a></td>
 <td><p class="b-fight-details__table-text">SUB</p><p class="b-fight-details__table-text">Rear naked choke</p></td>
 <td><p class="b-fight-details__table-text">2</p></td>
</tr>
<tr class="b-fight-details__table-row y">
 <td><i class="b-flag"><i class="b-flag__inner"><i class="b-flag__text">win</i></i></i></td>
 <td><a class="b-link b-link_style_black" href="f3">Gable Steveson</a>
     <a class="b-link b-link_style_black" href="f4">Elisha Ellison</a></td>
 <td><p class="b-fight-details__table-text">KO/TKO</p><p class="b-fight-details__table-text">Knees</p></td>
 <td><p class="b-fight-details__table-text">1</p></td>
</tr>
'''
def selftest():
    evs = parse_event_list(FIXTURE_LIST)
    assert len(evs) == 2 and evs[0][0] == dt.date(2026,7,11), evs
    assert "329" in evs[0][1] and evs[0][2].endswith("aaa111")
    fights = parse_event_fights(FIXTURE_EVENT)
    assert len(fights) == 2, fights
    (w,l,m,r) = fights[0]
    assert w=="Benoit Saint Denis" and l=="Paddy Pimblett" and m=="SUB" and r=="2", fights[0]
    assert fights[1][0]=="Gable Steveson" and method_short(fights[1][2])=="KO" and fights[1][3]=="1"
    assert method_short("U-DEC")=="DEC" and method_short("KO/TKO")=="KO" and method_short("nc")=="NC"
    print("RESULTS-UPDATER SELFTEST PASS — event list, fight rows, methods, rounds all parse")
    return 0

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    main()
