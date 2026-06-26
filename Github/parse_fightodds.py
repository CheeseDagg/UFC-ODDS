#!/usr/bin/env python3
"""
parse_fightodds.py  --  ingest a fightodds.io GraphQL response (the
`data.eventOfferTable` blob you copy out of DevTools -> Network) and distill it
into a compact odds file the scouting tool bakes in.

Per fight it computes, from ~24 sportsbooks:
  - consensus no-vig win probability (median across books; robust to glitched lines)
  - best available price per side + which book offers it  (line-shopping edge)
  - recent line movement, using each book's `oddsPrev` (LAST tick, not the open)
  - sharp-book consensus vs public-book consensus (the one place signal can hide)

Usage:
  python3 parse_fightodds.py <input.json> [<input2.json> ...] -o odds/parsed_odds.json
Multiple inputs merge; later pulls overwrite earlier ones for the same fight.
"""
import json, sys, re, statistics, unicodedata, argparse, pathlib

# Low-margin / sharp books vs high-volume public books.
SHARP  = {"Pinnacle", "Circa", "BetOnline", "Bookmaker"}
PUBLIC = {"DraftKings", "FanDuel", "BetMGM", "Caesars", "BetRivers", "HardRockBet"}


def nm(s):
    """Normalize a name: strip accents, lowercase, drop non-alphanumerics.
    Must match the JS normalizer in the template exactly."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def am_to_p(a):
    """American odds -> implied probability (with vig)."""
    if a is None:
        return None
    a = float(a)
    if a < 0:
        return (-a) / ((-a) + 100.0)
    return 100.0 / (a + 100.0)


def p_to_am(p):
    """Probability -> American odds (rounded)."""
    if p is None:
        return None
    p = min(max(p, 1e-6), 1 - 1e-6)
    if p >= 0.5:
        return -int(round(100.0 * p / (1.0 - p)))
    return int(round(100.0 * (1.0 - p) / p))


def novig(p1, p2):
    """Two-way vig removal: normalize the pair to sum to 1."""
    if p1 is None or p2 is None:
        return None
    s = p1 + p2
    if s <= 0:
        return None
    return p1 / s


def _full_name(f):
    return (str(f.get("firstName", "")).strip() + " " +
            str(f.get("lastName", "")).strip()).strip()


def parse_event(J):
    eot = (J.get("data", {}) or {}).get("eventOfferTable") or J.get("eventOfferTable")
    if not eot:
        return {}
    event = eot.get("name", "") or ""
    out = {}
    for fe in (eot.get("fightOffers", {}) or {}).get("edges", []):
        n = fe.get("node", {}) or {}
        if n.get("isCancelled"):
            continue
        fr1, fr2 = n.get("fighter1", {}) or {}, n.get("fighter2", {}) or {}
        f1n, f2n = _full_name(fr1), _full_name(fr2)
        f1s, f2s = fr1.get("slug", ""), fr2.get("slug", "")
        if not f1n or not f2n:
            continue
        feed_best1, feed_best2 = n.get("bestOdds1"), n.get("bestOdds2")

        # ---- pass 1: collect every book's lines ----
        rows = []
        for oe in (n.get("straightOffers", {}) or {}).get("edges", []):
            b = oe.get("node", {}) or {}
            book = (b.get("sportsbook", {}) or {}).get("shortName", "")
            o1, o2 = (b.get("outcome1") or {}), (b.get("outcome2") or {})
            a1, a2 = o1.get("odds"), o2.get("odds")
            pv = novig(am_to_p(a1), am_to_p(a2))
            pvp = novig(am_to_p(o1.get("oddsPrev")), am_to_p(o2.get("oddsPrev")))
            rows.append({"book": book, "a1": a1, "a2": a2, "pv": pv, "pvp": pvp})

        nv_all = [r["pv"] for r in rows if r["pv"] is not None]
        if not nv_all:
            continue
        prelim = statistics.median(nv_all)
        # Drop flipped/glitched lines (e.g. a book that maps outcome1/outcome2
        # backwards) before trusting any of its numbers.
        BAND = 0.22
        good = [r for r in rows if r["pv"] is not None and abs(r["pv"] - prelim) < BAND]
        if not good:
            good = [r for r in rows if r["pv"] is not None]

        cons1 = statistics.median([r["pv"] for r in good])
        prevs = [r["pvp"] for r in good if r["pvp"] is not None]
        move1 = (cons1 - statistics.median(prevs)) if prevs else None
        sharp = [r["pv"] for r in good if r["book"] in SHARP]
        public = [r["pv"] for r in good if r["book"] in PUBLIC]
        sharp1 = statistics.median(sharp) if sharp else None
        public1 = statistics.median(public) if public else None

        # ---- best available price, computed from the cleaned books only ----
        # (highest American number = most favorable to the bettor on each side)
        c1 = [(r["a1"], r["book"]) for r in good if r["a1"] is not None]
        c2 = [(r["a2"], r["book"]) for r in good if r["a2"] is not None]
        best1, best1book = (max(c1, key=lambda x: x[0]) if c1 else (feed_best1, None))
        best2, best2book = (max(c2, key=lambda x: x[0]) if c2 else (feed_best2, None))

        # Median ACTUAL (vigged) price per side, the market hold, and the real
        # per-fight line-shop edge = how much the best book beats the typical one,
        # in implied-probability points (best price implies a LOWER prob = value).
        raw1 = [am_to_p(r["a1"]) for r in good if r["a1"] is not None]
        raw2 = [am_to_p(r["a2"]) for r in good if r["a2"] is not None]
        med1_raw = statistics.median(raw1) if raw1 else None
        med2_raw = statistics.median(raw2) if raw2 else None
        holds = [am_to_p(r["a1"]) + am_to_p(r["a2"]) - 1.0
                 for r in good if r["a1"] is not None and r["a2"] is not None]
        hold = statistics.median(holds) if holds else None
        shop1 = (med1_raw - am_to_p(best1)) if (med1_raw is not None and best1 is not None) else None
        shop2 = (med2_raw - am_to_p(best2)) if (med2_raw is not None and best2 is not None) else None

        key = "|".join(sorted([nm(f1n), nm(f2n)]))
        out[key] = {
            "f1": f1n, "f2": f2n,
            "f1_slug": f1s, "f2_slug": f2s,
            "cons1": round(cons1, 4), "cons2": round(1 - cons1, 4),
            "am1": p_to_am(cons1), "am2": p_to_am(1 - cons1),
            "best1": best1, "best2": best2,
            "best1book": best1book, "best2book": best2book,
            "med1am": p_to_am(med1_raw) if med1_raw is not None else None,
            "med2am": p_to_am(med2_raw) if med2_raw is not None else None,
            "shop1": round(shop1, 4) if shop1 is not None else None,
            "shop2": round(shop2, 4) if shop2 is not None else None,
            "hold": round(hold, 4) if hold is not None else None,
            "move1": round(move1, 4) if move1 is not None else None,
            "sharp1": round(sharp1, 4) if sharp1 is not None else None,
            "public1": round(public1, 4) if public1 is not None else None,
            "nbooks": len(good),
            # per-book lines (cleaned): [book, americanF1, americanF2] — only books
            # that priced BOTH sides, so a parlay leg can be placed there. Enables
            # ranking books by what they pay on a full parlay (a book missing any
            # selected leg is dropped from that parlay downstream).
            "books": [[r["book"], r["a1"], r["a2"]]
                      for r in good if r["a1"] is not None and r["a2"] is not None],
            "event": event,
        }
    return out


# ── card extraction: derive the matchup list (for upcoming.csv) from the SAME
#    blob, so one paste feeds both the odds and the card. Fighter names + order
#    are always present; weight class / title / main-vs-prelim segment are pulled
#    defensively (field names vary), with safe fallbacks + CLI overrides. ────────
def _wc_of(n):
    for k in ("weightClass", "weight", "division", "weightClassName", "weightclass"):
        v = n.get(k)
        if isinstance(v, dict):
            v = v.get("name") or v.get("weightClass") or v.get("shortName") or ""
        if v:
            return re.sub(r"\s+", " ", str(v)).strip()
    return ""

def _title_of(n):
    return bool(n.get("isTitleFight") or n.get("titleFight")
                or n.get("isChampionship") or n.get("isTitle"))

def _seg_of(n):
    # explicit boolean main-card flag
    for k in ("isMainCard", "isMain", "mainCard"):
        if n.get(k) is not None:
            return "main" if n.get(k) else "prelim"
    # explicit segment string
    for k in ("cardSegment", "segment", "section", "card"):
        v = n.get(k)
        if isinstance(v, dict):
            v = v.get("name") or v.get("type") or ""
        if v:
            s = str(v).lower()
            if "main" in s:
                return "main"
            if "prelim" in s or "early" in s:
                return "prelim"
    return None

def parse_card(J):
    """Ordered list of {r,b,wc,title,seg} for every live bout, in blob order."""
    eot = (J.get("data", {}) or {}).get("eventOfferTable") or J.get("eventOfferTable")
    if not eot:
        return []
    rows = []
    for fe in (eot.get("fightOffers", {}) or {}).get("edges", []):
        n = fe.get("node", {}) or {}
        if n.get("isCancelled"):
            continue
        fr1, fr2 = n.get("fighter1", {}) or {}, n.get("fighter2", {}) or {}
        r, b = _full_name(fr1), _full_name(fr2)
        if not r or not b:
            continue
        rows.append({"r": r, "b": b,
                     "r_slug": fr1.get("slug", ""), "b_slug": fr2.get("slug", ""),
                     "wc": _wc_of(n),
                     "title": _title_of(n), "seg": _seg_of(n)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("-o", "--out", default="odds/parsed_odds.json")
    ap.add_argument("--upcoming", default=None,
                    help="ALSO write the card (matchups) to this CSV, derived from the same blob "
                         "(e.g. odds/upcoming.csv) — one paste feeds both odds and card")
    ap.add_argument("--date", default="", help="event date YYYY-MM-DD for the card CSV")
    ap.add_argument("--location", default="", help="event location for the card CSV")
    ap.add_argument("--main", type=int, default=None,
                    help="mark the first N bouts (in blob order) as main card, the rest prelim "
                         "(use if the blob has no segment field)")
    ap.add_argument("--reverse", action="store_true",
                    help="reverse the blob's fight order (use if the main event lands last)")
    ap.add_argument("--roster", default=None,
                    help="path to output/ufc_ratings.json; maps fightodds.io spellings onto the "
                         "dataset's names so odds link and rated fighters resolve, and fills weight "
                         "classes from each fighter's division (auto-detected in ./output if omitted)")
    a = ap.parse_args()

    # ── name reconciliation: load the dataset roster so the blob's spellings get
    #    mapped onto the names the tool knows — one paste yields a fully-linked card ──
    rec = _rec = None
    rpath = a.roster
    if rpath is None:
        for cand in ("output/ufc_ratings.json", "ufc_ratings.json"):
            if pathlib.Path(cand).exists():
                rpath = cand
                break
    if rpath and pathlib.Path(rpath).exists():
        try:
            import reconcile as _rec
            rec = _rec.Reconciler(_rec.load_roster(rpath))
            print(f"  reconciling fighter names against {rpath}")
        except Exception as e:
            print(f"  ! reconciliation unavailable ({e}); keeping fightodds.io spellings")
            _rec = None
    else:
        print("  note: no roster found (output/ufc_ratings.json) — keeping fightodds.io spellings; "
              "rated names may show as 'no data'. Pass --roster to map them.")

    merged = {}
    for path in a.inputs:
        try:
            J = json.load(open(path))
        except Exception as e:
            print(f"  ! skip {path}: {e}")
            continue
        ev = parse_event(J)
        merged.update(ev)
        print(f"  + {path}: {len(ev)} fights")

    if rec is not None:
        merged, _rep = _rec.reconcile_odds(merged, rec, nm)
        seen_rep = {}
        for b, c, d in _rep:
            seen_rep[b] = (c, d)
        mapped = [(b, c) for b, (c, d) in seen_rep.items() if _rec._norm(b) != _rec._norm(c)]
        debut = [b for b, (c, d) in seen_rep.items() if d is None]
        if mapped:
            print(f"  reconciled {len(mapped)} spelling(s) onto dataset names:")
            for b, c in sorted(mapped):
                print(f"      {b}  ->  {c}")
        if debut:
            print(f"  not in dataset (kept, will show unpriceable): {', '.join(sorted(debut))}")

    outp = pathlib.Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    json.dump(merged, open(outp, "w"), separators=(",", ":"))
    print(f"\nwrote {len(merged)} fights -> {outp}")
    for v in list(merged.values())[:5]:
        mv = f"{v['move1']:+.1%}" if v["move1"] is not None else "na"
        sh = f"{v['sharp1']:.0%}" if v["sharp1"] is not None else "na"
        pb = f"{v['public1']:.0%}" if v["public1"] is not None else "na"
        print(f"  {v['f1']:<22} vs {v['f2']:<22} | f1 {v['cons1']:.0%} "
              f"| best {v['best1']:>5}@{v['best1book'] or '?':<11} move {mv:>6} "
              f"| sharp {sh} vs pub {pb} | {v['nbooks']}bk")

    # ── one-paste-feeds-both: also emit the card CSV from the same blob(s) ──
    if a.upcoming:
        import csv as _csv
        card, seen = [], set()
        for path in a.inputs:
            try:
                J = json.load(open(path))
            except Exception:
                continue
            for row in parse_card(J):
                key = "|".join(sorted([nm(row["r"]), nm(row["b"])]))
                if key in seen:
                    continue
                seen.add(key)
                card.append(row)
        if a.reverse:
            card.reverse()
        # main/prelim: --main overrides; else use any segment the blob provided; else all main
        if a.main is not None:
            for i, row in enumerate(card):
                row["section"] = "main" if i < a.main else "prelim"
        elif any(r.get("seg") in ("main", "prelim") for r in card):
            for row in card:
                row["section"] = row["seg"] if row.get("seg") in ("main", "prelim") else "main"
        else:
            for row in card:
                row["section"] = "main"
        if rec is not None:
            _rec.reconcile_card(card, rec)   # canonical names + weight class from divisions
        up = pathlib.Path(a.upcoming)
        up.parent.mkdir(parents=True, exist_ok=True)
        with open(up, "w", newline="") as fh:
            wtr = _csv.writer(fh)
            wtr.writerow(["date", "location", "R_fighter", "B_fighter",
                          "weight_class", "title_bout", "section"])
            for row in card:
                wtr.writerow([a.date, a.location, row["r"], row["b"], row["wc"],
                              "True" if row["title"] else "False", row["section"]])
        n_wc = sum(1 for r in card if r["wc"])
        n_seg = sum(1 for r in card if r.get("seg") in ("main", "prelim"))
        print(f"\nwrote {len(card)} bouts -> {up}  "
              f"(weight class on {n_wc}/{len(card)}, segment on {n_seg}/{len(card)})")
        for row in card:
            print(f"  [{row['section']:6}] {row['r']} vs {row['b']}  ({row['wc'] or 'wc?'})")
        if not a.date:
            print("  note: pass --date YYYY-MM-DD to set the card date")
        if a.main is None and n_seg < len(card):
            print("  note: blob had no clear main/prelim split — pass --main N to mark the first N as main")


if __name__ == "__main__":
    main()
