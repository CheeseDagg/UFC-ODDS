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
import json, re, unicodedata, difflib, datetime

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
                    "bouts": f.get("ufc_bouts", 5),
                    "last": f.get("last_fight_year")})
    for p in d.get("prospects", []):
        out.append({"name": p["name"], "div": p.get("division", ""),
                    "bouts": p.get("ufc_bouts", 1),
                    "last": p.get("last_fight_year")})
    return out


# Minimum given-name similarity before a surname candidate may be accepted.
#
# This was 0.5, and 0.5 on a four-letter first name is two shared characters:
#   _tokpair('mike','rick')       = 0.5000   -> resolved Mike Davis to RICK Davis
#   _tokpair('michael','charles') = 0.5714   -> resolved Michael Oliveira to CHARLES
#   _tokpair('cezar','carlos')    = 0.5455   -> resolved Cezar Ferreira to a stranger
# Every real spelling variant this module exists to absorb scores far higher,
# because the four-character prefix rule in _tokpair already returns 1.0 for them:
#   daniel/daniil 1.00, abus/abusupiyan 1.00, shara/sharabutdin 1.00,
#   and honest typos land ~0.89 (jose/jhose, kevin/kevn).
# So the band between 0.5 and 0.72 contains no legitimate matches, only namesake
# collisions. Measured on the 2,586-name roster by injecting one drop/swap/substitute
# typo into every given name (2,277 usable perturbations):
#   cutoff 0.50 -> 99.74% recall    cutoff 0.72 -> 99.69% recall (one name lost)
#   cutoff 0.80 -> 84.89% recall    cutoff 0.85 -> 56.57% recall
# 0.72 costs one perturbed name out of 2,277 and removes both wrong-person
# resolutions on record. 0.80 costs 15 points of recall for nothing extra.
GIVEN_MIN = 0.72

# A name score cannot tell "Carlos Diego Ferreira -> Diego Ferreira" (same man,
# extra given name) from "Eduardo Henrique da Silva -> Henrique da Silva"
# (different men, extra given name). On 2026-08-13 the second pair scored 0.9
# and a flyweight debutant was about to render with a retired light
# heavyweight's 2016-18 record. What separates the pairs is not the string, it
# is the person: Diego was active in the division on the ticket, the LHW was
# nine years gone and seven weight classes away. So metadata gets a veto.
#
#   STALE_YEARS: a candidate whose last dataset fight is >6 years old is
#   refused on fuzzy hits — the same line ufc_blend_predict draws for namesake
#   slugs ("a Rick Davis who last fought in 2006"). Exact-spelling hits are
#   exempt: a same-name comeback is likelier than a same-exact-name stranger.
#
#   LADDER: refused when the bout's stated weight class and the candidate's
#   division are 3+ rungs apart, or the women's flags disagree. Real
#   short-notice jumps span two rungs (McGregor fought welterweight while
#   listed featherweight), so two is allowed; Flyweight-vs-LHW is seven.
#   Unknown or catchweight strings skip the check — the guard exists to catch
#   absurd joins, not to police plausible moves.
STALE_YEARS = 6
LADDER = ["strawweight", "flyweight", "bantamweight", "featherweight",
          "lightweight", "welterweight", "middleweight", "light heavyweight",
          "heavyweight"]


def _rung(div):
    """(is_womens, ladder_index) or None when the string names no rung."""
    d = str(div or "").lower().replace("’", "'").strip()
    w = d.startswith("women")
    d = re.sub(r"^women'?s\s*", "", d).strip()
    return (w, LADDER.index(d)) if d in LADDER else None


def _rung_ok(wc, div):
    a, b = _rung(wc), _rung(div)
    if not a or not b:
        return True
    return a[0] == b[0] and abs(a[1] - b[1]) <= 2


class Reconciler:
    def __init__(self, roster):
        self.by_norm, self.by_last = {}, {}
        self.div, self.bouts, self.last = {}, {}, {}
        for r in roster:
            n = r["name"]
            self.by_norm.setdefault(_norm(n), n)
            self.div[n] = r["div"]
            self.bouts[n] = r["bouts"]
            self.last[n] = r.get("last")
            t = _tokens(n)
            if t:
                self.by_last.setdefault(t[-1], []).append(n)
        self._lastkeys = list(self.by_last.keys())

    def _fresh(self, cand):
        ly = self.last.get(cand)
        return not ly or datetime.date.today().year - ly <= STALE_YEARS

    @staticmethod
    def _givens(n):
        """Every token that is not the surname. Scoring only token[0] was a real bug:
        the fightodds.io slug 'carlos-diego-ferreira-3134' becomes 'carlos diego
        ferreira', whose first token is 'carlos' — which scores 0.545 against
        *Cezar* Ferreira and 0.182 against *Diego* Ferreira, so the matcher
        confidently returned the wrong human being. 'diego' is an exact hit on the
        right man and was thrown away because it sat in the middle. Compare every
        given-name token on both sides and keep the best pair."""
        t = _tokens(n)
        return t[:-1] if len(t) > 1 else t

    @staticmethod
    def _tokpair(a, b):
        if not a or not b:
            return 0.0
        if b.startswith(a[:4]) or a.startswith(b[:4]):
            return 1.0
        return difflib.SequenceMatcher(None, a, b).ratio()

    def _fscore(self, fns, cand):
        """fns may be a single token (legacy callers) or a list of given-name tokens.

        The leading token still outranks the middle ones. Without that weight,
        'Lavar Jose Johnson' resolves to *Jose* Johnson — both 'lavar' and 'jose'
        score a perfect 1.0 against their own man, and a bare max() breaks the tie
        arbitrarily. MIDW=0.9 makes a middle-name hit beat a weak leading-name hit
        (0.90 > 0.545, which is what rescues Diego Ferreira) but lose to a strong
        one (0.90 < 1.0, which is what protects Lavar Johnson)."""
        MIDW = 0.9
        if isinstance(fns, str):
            fns = [fns] if fns else []
        cfs = self._givens(cand)
        if not fns or not cfs:
            return 0.0
        return max(self._tokpair(a, b) * (1.0 if (i == 0 and j == 0) else MIDW)
                   for i, a in enumerate(fns) for j, b in enumerate(cfs))

    def _rawscore(self, fns, cand):
        """Tie-break only: the best raw similarity between any two given-name
        tokens, with no prefix shortcut and no position weight.

        _tokpair returns a flat 1.0 for any four-character prefix agreement, which
        is what lets 'Abus' find 'Abusupiyan' — but it also makes 'SeungGuk' and
        'SeungWoo' both score exactly 1.0 against a 'Seung*' query, and 'Shanna'
        and 'Shane' both score 1.0 against 'Shan*'. A bare max() then breaks those
        ties by dict iteration order, i.e. arbitrarily, and picks a real but
        different fighter. Raw ratio separates them (seungguk/seungwoo 0.75 vs
        1.00 for the true one) without touching the acceptance threshold."""
        if isinstance(fns, str):
            fns = [fns] if fns else []
        cfs = self._givens(cand)
        if not fns or not cfs:
            return 0.0
        return max(difflib.SequenceMatcher(None, a, b).ratio() for a in fns for b in cfs)

    def match(self, name, wc=None):
        """(canonical_name, division) — or (name, None) when no confident match.
        wc, when the caller knows the bout's weight class, lets a division-
        impossible candidate be refused (see the guard block above)."""
        k = _norm(name)
        if k in ALIAS:
            c = ALIAS[k]                            # hand-verified: no guards
            return c, self.div.get(c)
        if k in self.by_norm:                       # exact (after accent fold)
            c = self.by_norm[k]
            if not _rung_ok(wc, self.div.get(c)):   # two Bruno Silvas problem
                return name, None
            return c, self.div.get(c)
        toks = _tokens(name)
        fn = self._givens(name)
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
        best = max(cands, key=lambda c: (self._fscore(fn, c), self._rawscore(fn, c)))
        if self._fscore(fn, best) < GIVEN_MIN:      # given names too different
            return name, None
        # The name evidence points at `best`. If that person cannot be in this
        # cage — years gone, or the wrong end of the weight ladder — the honest
        # output is UNRESOLVED, not the next-best-scoring stranger. Falling
        # through to another candidate here is how wrong-person joins happen.
        if not self._fresh(best) or not _rung_ok(wc, self.div.get(best)):
            return name, None
        return best, self.div.get(best)

    def match_pref(self, name, slug="", wc=None):
        """Prefer the fightodds.io SLUG for matching. Slugs carry a permanent numeric id
        and stay constant even when the feed flips a fighter's display-name spelling
        between pulls, so matching on the slug makes a fighter resolve the SAME way every
        build (no flicker, no greying).

        WHEN DISPLAY NAME AND SLUG ARE DIFFERENT PEOPLE, THE SLUG WINS.

        This used to be the other way round — 'if the display name also resolves, the
        display name wins' — on the theory that a mislabeled slug was the likelier
        failure. The repo's own data says the opposite, in every case on record:

          * Aliev vs Davis, 2026-07-25. Display 'Rick Davis', slug 'mike-davis-…'.
            data/ufc_predictions_blend.csv logged RICK Davis; data/results_delta.csv
            records the fight that actually happened as Nurullo Aliev vs MIKE Davis.
            The display-wins rule picked the wrong man, and the Rick Davis it picked
            last fought in 2006 — which is why a separate namesake guard (>6y stale)
            had to be bolted on afterwards to suppress the damage.
          * Elliott vs Oliveira, 2026-08-01. Display 'Charles Oliveira', slug
            'michael-oliveira-50272'. Charles is a former champion at Elo ~1985;
            resolving the display name priced Elliott at 20% in a bout that is
            actually unrateable.
          * Quarantillo vs Ferreira, 2026-08-08. Display 'Cezar Ferreira', slug
            'carlos-diego-ferreira-3134'. Cezar is a middleweight who last fought in
            2019; Diego is the lightweight in the cage. Display-wins made Quarantillo
            a 56.4% favourite when he is a 30.3% underdog against the real opponent.

        Three for three, the free-text display name was the thing that lied. The
        discriminator is the same one ufc_blend_predict._trusted_name uses, so the
        odds/display path and the model path can no longer disagree about who is
        fighting: compare given name and surname SEPARATELY (a whole-string ratio is
        useless here — 'charles oliveira' vs 'michael oliveira' scores 0.81 on the
        shared surname alone, which is exactly the case that must be caught). Near on
        both -> same person, ordinary spelling drift ('dennis-buzukia-29076' for
        'Dennis Buzukja'), keep the display spelling. Otherwise take the slug."""
        sn = _name_from_slug(slug)
        slug_c, slug_d = self.match(sn, wc) if sn else (name, None)
        name_c, name_d = self.match(name, wc)
        if slug_d is not None:
            if name_d is not None and name_c != slug_c and _same_person(name, sn):
                # Both resolve, they disagree, yet the two strings ARE the same
                # person by given+surname — so the disagreement is a matcher
                # artefact on a spelling variant, not a mislabeled bout. Keep the
                # display name's resolution, which is the one the card is written in.
                return name_c, name_d
            return slug_c, slug_d
        if sn and name_d is not None and not _same_person(name, sn):
            # THE UNRATEABLE-DEBUTANT TRAP. The slug is ID-backed and names
            # somebody the dataset has never heard of; the display name beside it
            # names a different human who IS in the dataset. Falling back to the
            # display name here is how Elliott vs MICHAEL Oliveira got priced off
            # CHARLES Oliveira's championship record — the fighter is unrateable,
            # and the honest output is a blank, not a stranger's Elo. Leave the
            # bout's own text in place with no division so every downstream
            # consumer treats it as unresolved.
            return name, None
        return name_c, name_d


SLUG_MATCH = 0.80      # below this, display name and slug name are different people


def _same_person(display, slugname):
    """Are these two strings the same human? Given name and surname compared
    separately and both required — the shared surname in 'charles oliveira' vs
    'michael oliveira' carries a whole-string ratio to 0.81, so a whole-string
    test would wave through precisely the swap it is supposed to catch.

    Kept numerically identical to ufc_blend_predict._trusted_name (SLUG_MATCH =
    0.80) so the display path and the model path never disagree about identity.
    Middle names are ignored on purpose: 'carlos diego ferreira' vs 'diego
    ferreira' is the same man, and comparing first-to-first would call them
    different."""
    dt_, st_ = _tokens(display), _tokens(slugname)
    if not dt_ or not st_:
        return True                       # nothing to contradict; caller's default
    def near(a, b):
        return difflib.SequenceMatcher(None, a, b).ratio() >= SLUG_MATCH
    if not near(dt_[-1], st_[-1]):        # different surnames
        return False
    # Any given-name token matching any other is enough — this is the middle-name
    # case, and it is the reason _givens/_fscore exist above.
    dg, sg = (dt_[:-1] or dt_), (st_[:-1] or st_)
    return any(near(a, b) for a in dg for b in sg)


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
        f1, d1 = rec.match_pref(f1b, o.get("f1_slug", ""), wc=o.get("wc"))
        f2, d2 = rec.match_pref(f2b, o.get("f2_slug", ""), wc=o.get("wc"))
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
        r1, d1 = rec.match_pref(row["r"], row.get("r_slug", ""), wc=row.get("wc"))
        r2, d2 = rec.match_pref(row["b"], row.get("b_slug", ""), wc=row.get("wc"))
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


def selftest():
    """Pins on the REAL roster file — every case below happened on a live card."""
    import os
    ok = [0, 0]
    def chk(c, m):
        ok[1] += 1; ok[0] += bool(c)
        print(f"{'PASS' if c else 'FAIL'}  {m}")

    here = os.path.dirname(os.path.abspath(__file__))
    rec = Reconciler(load_roster(os.path.join(here, "output", "ufc_ratings.json")))

    got = rec.match("Eduardo Henrique da Silva", wc="Flyweight")
    chk(got == ("Eduardo Henrique da Silva", None),
        "2026-08-13, UFC 330: the flyweight late-replacement does NOT join the "
        "dataset's Henrique da Silva (LHW, last fight 2017) -- he renders "
        f"unpriceable instead of wearing a stranger's record (got {got})")
    got = rec.match("Eduardo Henrique da Silva")
    chk(got[1] is None,
        "with no weight class stated, staleness alone still refuses the join "
        "-- nine years gone is not a spelling variant")
    got = rec.match_pref("Eduardo Henrique da Silva",
                         "eduardo-henrique-da-silva-99999", wc="Flyweight")
    chk(got == ("Eduardo Henrique da Silva", None),
        "the guard holds on the real call path (match_pref with a slug)")

    got = rec.match("Carlos Diego Ferreira", wc="Lightweight")
    chk(got[0] == "Diego Ferreira",
        "the middle-token rescue SURVIVES the guards: Carlos Diego Ferreira "
        "still resolves to Diego Ferreira (active, right division)")
    got = rec.match("Ian Garry", wc="Welterweight")
    chk(got[0] == "Ian Machado Garry",
        "Ian Garry still resolves to Ian Machado Garry -- the live card's "
        "other real reconciliation keeps working")
    got = rec.match("Islam Makhachev", wc="Welterweight")
    chk(got[0] == "Islam Makhachev",
        "an exact-spelling hit with a sane weight class passes untouched")

    chk(not _rung_ok("Flyweight", "Light Heavyweight"),
        "seven rungs apart is refused")
    chk(_rung_ok("Featherweight", "Welterweight"),
        "two rungs is allowed -- McGregor fought WW while listed FW; the "
        "guard catches absurd joins, not real short-notice moves")
    chk(not _rung_ok("Women's Flyweight", "Flyweight"),
        "the women's flag must agree even when the rung matches")
    chk(_rung_ok("Catchweight", "Lightweight") and _rung_ok(None, "Lightweight"),
        "unknown weight-class strings skip the check rather than guess")

    chk(not rec._fresh("Henrique da Silva"),
        "the 2017 LHW is stale by the same >6y line ufc_blend_predict draws")
    chk(rec._fresh("Diego Ferreira"),
        "a 2025 fighter is fresh")
    print(f"\n{ok[0]}/{ok[1]} checks pass")
    return 0 if ok[0] == ok[1] else 1


if __name__ == "__main__":
    import sys
    sys.exit(selftest())
