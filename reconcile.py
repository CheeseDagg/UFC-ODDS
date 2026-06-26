"""Map fightodds.io fighter spellings onto the dataset's canonical names.

fightodds.io and the ratings dataset routinely disagree on spelling:
  Sharabutdin -> Shara, Asu Almabaev -> Almabayev, Michał -> Michal,
  Abusupiyan -> Abus, Daniel -> Daniil, "Javier Reyes Rugeles" -> "Javier Reyes".
Left unreconciled, the odds key wouldn't line up with the bout and every
mis-spelled rated fighter would render as "no data". This maps the blob's
names onto the dataset's spellings so a single paste yields a fully-linked card.

Conservative by design: when a name can't be matched with confidence — a genuine
debutant, or a surname match whose first names are too different to trust — it is
LEFT UNCHANGED rather than mapped to the wrong person. Showing a fighter as
unpriceable is acceptable; attaching someone else's record to them is not.
"""
import json, re, unicodedata, difflib

# Hand-verified overrides for cases the heuristic can't reach on its own.
ALIAS = {
    "javierreyesrugeles": "Javier Reyes",
    # Abdul Rakhman Yakhyaev — fightodds.io flips this fighter's spelling
    # between pulls (one-word "Abdulrakhman", hyphenated, "Rahman" vs "Rakhman").
    # Pin every plausible form to the dataset's name so he never greys out.
    "abdulrakhmanyakhyaev": "Abdul Rakhman Yakhyaev",
    "abdulrahmanyakhyaev":  "Abdul Rakhman Yakhyaev",
    "abdurakhmanyakhyaev":  "Abdul Rakhman Yakhyaev",
    "abdurrahmanyakhyaev":  "Abdul Rakhman Yakhyaev",
}


def _norm(s):
    """Loose key used for MATCHING only: strip accents, fold the Polish ł
    (NFKD leaves it intact), lowercase, keep alphanumerics."""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.replace("\u0142", "l").replace("\u0141", "l")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _tokens(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = s.replace("\u0142", "l").replace("\u0141", "l").lower()
    return [t for t in re.split(r"[^a-z0-9]+", s) if t]


def load_roster(ratings_path):
    """[{name, div, bouts}] for every rated fighter + prospect in the dataset."""
    d = json.load(open(ratings_path))
    out = []
    for f in d.get("fighters", []):
        out.append({"name": f["name"], "div": f.get("division", ""),
                    "bouts": f.get("ufc_bouts", 5)})
    for p in d.get("prospects", []):
        out.append({"name": p["name"], "div": p.get("division", ""),
                    "bouts": p.get("ufc_bouts", 1)})
    return out


class Reconciler:
    def __init__(self, roster):
        self.by_norm, self.by_last = {}, {}
        self.div, self.bouts = {}, {}
        for r in roster:
            n = r["name"]
            self.by_norm.setdefault(_norm(n), n)
            self.div[n] = r["div"]
            self.bouts[n] = r["bouts"]
            t = _tokens(n)
            if t:
                self.by_last.setdefault(t[-1], []).append(n)
        self._lastkeys = list(self.by_last.keys())

    @staticmethod
    def _first(n):
        t = _tokens(n)
        return t[0] if t else ""

    def _fscore(self, fn, cand):
        cf = self._first(cand)
        if not fn or not cf:
            return 0.0
        if cf.startswith(fn[:4]) or fn.startswith(cf[:4]):
            return 1.0
        return difflib.SequenceMatcher(None, fn, cf).ratio()

    def match(self, name):
        """(canonical_name, division) — or (name, None) when no confident match."""
        k = _norm(name)
        if k in ALIAS:
            c = ALIAS[k]
            return c, self.div.get(c)
        if k in self.by_norm:                       # exact (after accent fold)
            c = self.by_norm[k]
            return c, self.div.get(c)
        toks = _tokens(name)
        fn = toks[0] if toks else ""
        surn = []
        if toks:
            surn.append(toks[-1])
        if len(toks) >= 3:                          # Spanish double surnames
            surn.append(toks[-2])
        cands = []
        for s in surn:
            cands += self.by_last.get(s, [])
        if not cands:                               # fuzzy surname, tight cutoff
            for s in surn:
                for c in difflib.get_close_matches(s, self._lastkeys, n=3, cutoff=0.84):
                    cands += self.by_last[c]
        cands = list(dict.fromkeys(cands))
        if not cands:
            return name, None
        best = max(cands, key=lambda c: self._fscore(fn, c))
        if self._fscore(fn, best) < 0.5:            # first names too different
            return name, None
        return best, self.div.get(best)

    def match_pref(self, name, slug=""):
        """Prefer the fightodds.io SLUG for matching. Slugs carry a permanent
        numeric id and stay constant even when the feed flips a fighter's
        display-name spelling between pulls, so matching on the slug makes a
        fighter resolve the SAME way every build (no flicker, no greying).
        Falls back to the display name only when the slug doesn't resolve."""
        sn = _name_from_slug(slug)
        if sn:
            c, d = self.match(sn)
            if d is not None:                       # slug resolved to a dataset fighter
                return c, d
        return self.match(name)


def _name_from_slug(slug):
    """fightodds.io slugs look like 'abdulrakhman-yakhyaev-42963' — a stable
    stem plus a permanent id. Strip the trailing id and turn the hyphenated
    stem into a plain name we can run through the matcher. Stable across the
    feed's pull-to-pull spelling flips."""
    s = re.sub(r"-\d+$", "", str(slug or "")).strip()
    return s.replace("-", " ").strip()


def reconcile_odds(odds, rec, keyfn):
    """Re-key + relabel an odds dict onto canonical names.
    keyfn = the caller's nm() so the new key matches what the tool computes."""
    out, report = {}, []
    for o in odds.values():
        f1b, f2b = o["f1"], o["f2"]
        f1, d1 = rec.match_pref(f1b, o.get("f1_slug", ""))
        f2, d2 = rec.match_pref(f2b, o.get("f2_slug", ""))
        o = dict(o)
        o["f1"], o["f2"] = f1, f2
        out["|".join(sorted([keyfn(f1), keyfn(f2)]))] = o
        report.append((f1b, f1, d1))
        report.append((f2b, f2, d2))
    return out, report


def reconcile_card(rows, rec):
    """Map each bout's r/b to canonical names; fill a blank weight_class from
    the fighters' divisions (agree -> use it; disagree -> the more-established
    fighter's division; if neither maps -> left blank)."""
    for row in rows:
        r1, d1 = rec.match_pref(row["r"], row.get("r_slug", ""))
        r2, d2 = rec.match_pref(row["b"], row.get("b_slug", ""))
        row["r"], row["b"] = r1, r2
        if not row.get("wc"):
            if d1 and d2 and d1 == d2:
                row["wc"] = d1
            elif d1 or d2:
                if d1 and d2:
                    row["wc"] = d1 if rec.bouts.get(r1, 0) >= rec.bouts.get(r2, 0) else d2
                else:
                    row["wc"] = d1 or d2
    return rows
