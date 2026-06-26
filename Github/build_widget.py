"""
Stage 3: turn output/ufc_ratings.json into the compact embedded array and inject
it into the HTML template, producing the self-contained output/ufc_skill_explorer.html.
Column order MUST match the C map in the template.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "output"
DATA = HERE / "data"
TEMPLATE = HERE / "ufc_skill_explorer_template.html"
UPCOMING = HERE / "odds" / "upcoming.csv"

DIVS = ["Women's Strawweight", "Women's Flyweight", "Women's Bantamweight",
        "Flyweight", "Bantamweight", "Featherweight", "Lightweight", "Welterweight",
        "Middleweight", "Light Heavyweight", "Heavyweight"]
CONF = ["low", "medium", "high"]
STANCE = ["", "Orthodox", "Southpaw", "Switch", "Open Stance", "Sideways"]


def _n(x, dp=0):
    if x is None:
        return 0
    return round(x, dp) if dp else round(x)


def _si(s):
    return STANCE.index(s) if s in STANCE else 0


def load_upcoming():
    """Read the next card (fighters, weight class, title flag) for the in-tool
    upcoming-card panel. Returns None if unavailable so the panel hides cleanly."""
    if not UPCOMING.exists():
        return None
    try:
        import pandas as pd
        u = pd.read_csv(UPCOMING)
    except Exception:
        return None
    if len(u) == 0 or "R_fighter" not in u.columns:
        return None
    bouts = []
    for r in u.itertuples(index=False):
        rf, bf = getattr(r, "R_fighter", None), getattr(r, "B_fighter", None)
        if not isinstance(rf, str) or not isinstance(bf, str):
            continue
        bouts.append({
            "r": rf.strip(), "b": bf.strip(),
            "wc": (getattr(r, "weight_class", "") or "").strip() if isinstance(getattr(r, "weight_class", ""), str) else "",
            "title": bool(getattr(r, "title_bout", False)),
            "section": ((getattr(r, "section", "main") or "main").strip().lower()
                        if isinstance(getattr(r, "section", "main"), str) else "main"),
            # manual handicapping flags (short-notice / injury / missed weight / etc.)
            # entered per-fighter in the card CSV; surfaced in the tool, never fed to the model.
            "rnote": (getattr(r, "R_note", "") or "").strip() if isinstance(getattr(r, "R_note", ""), str) else "",
            "bnote": (getattr(r, "B_note", "") or "").strip() if isinstance(getattr(r, "B_note", ""), str) else "",
        })
    if not bouts:
        return None
    date = str(u["date"].iloc[0]) if "date" in u.columns else ""
    loc = ""
    if "location" in u.columns and isinstance(u["location"].iloc[0], str):
        loc = u["location"].iloc[0].strip()
    # the UFC APEX uses a 25-ft Octagon (vs the standard 30 ft) for every card it
    # hosts; flag it so the tool can surface the small-cage stylistic context.
    cage = "small" if "apex" in loc.lower() else None
    return {"date": date, "location": loc, "bouts": bouts, "cage": cage}


def main():
    d = json.load(open(OUT / "ufc_ratings.json"))
    import pandas as pd
    bouts = pd.read_csv(DATA / "fighter_bouts.csv")
    stats = pd.read_csv(DATA / "ufc_fight_stats.csv")

    # ── improved style classifier (used for style-split keys) ──────────────
    # Incorporates TD rate (wrestlers can be missed by rating-only class) and
    # KO rate (pure punchers can blend with well-rounded at moderate ratings).
    def classify(name):
        f = next((x for x in d["fighters"] if x["name"] == name), None)
        if not f:
            return None
        r = f["ratings"]; m = f.get("measured", {})
        strike = max(r.get("Striking") or 50, r.get("Power") or 50)
        grap   = max(r.get("Wrestling") or 50, r.get("Grappling") or 50)
        td15   = m.get("TD_per15") or 0
        tot_w  = f.get("finishes", {}).get("total_wins") or 1
        ko_w   = f.get("finishes", {}).get("ko_wins") or 0
        ko_rate = ko_w / max(tot_w, 1)
        td_bonus  = 10 if td15 >= 2.5 else (5 if td15 >= 1.5 else 0)
        ko_bonus  = 5  if ko_rate >= 0.6 else (3 if ko_rate >= 0.4 else 0)
        eff_grap   = grap + td_bonus
        eff_strike = strike + ko_bonus
        if eff_strike - eff_grap >= 8: return "striker"
        if eff_grap - eff_strike >= 8: return "grappler"
        return "mixed"

    bouts["opp_style"] = bouts["opp"].apply(classify)

    # ── body-shot % per style (for "throws more body shots vs wrestlers" read) ─
    # Parse body_l from fight_stats.csv (format "x of y")
    def parse_l(x):
        try: return int(str(x).split(' of ')[0])
        except: return 0
    stats["body_l"]  = stats["BODY"].apply(parse_l)
    stats["sig_l"]   = stats["SIG.STR."].apply(parse_l)
    stats["key"]     = stats["EVENT"] + "||" + stats["BOUT"]
    # aggregate per fighter per bout
    fg = stats.groupby(["key","FIGHTER"])[["body_l","sig_l"]].sum().reset_index()
    fg.columns = ["key","fighter","body_l","sig_l"]
    # join with opponent info
    fg2 = fg.merge(fg, on="key", suffixes=("","_opp"))
    fg2 = fg2[fg2["fighter"] != fg2["fighter_opp"]].rename(columns={"fighter_opp":"opp"})
    # attach opp_style
    fg2["opp_style"] = fg2["opp"].apply(classify)

    def splits(name):
        """Return per-style split data (6 + 2 body cols)."""
        fb   = bouts[bouts["fighter"] == name]
        fb2  = fg2[fg2["fighter"] == name]
        out  = {}
        for style in ("striker", "grappler"):
            sub   = fb[fb["opp_style"] == style]
            sub2  = fb2[fb2["opp_style"] == style]
            n     = len(sub)
            if n < 2:
                out[style] = (None, None, 0, None)
                continue
            mins = sub["secs"].sum() / 60.0 or 1
            td15  = round(sub["td_l"].sum() / mins * 15, 1)
            ctrl15 = round(sub["ctrl"].sum() / mins * 15 / 60, 2)
            # body %: body_l / sig_l across those bouts
            bl = sub2["body_l"].sum(); sl = sub2["sig_l"].sum()
            body_pct = round(bl / max(sl, 1) * 100, 1) if sl >= 10 else None
            out[style] = (td15, ctrl15, n, body_pct)
        s = out["striker"]; g = out["grappler"]
        # vsST: td15, ctrl15, n, body_pct  /  vsGR: same
        return [s[0], s[1], s[2], s[3], g[0], g[1], g[2], g[3]]

    split_map = {f["name"]: splits(f["name"]) for f in d["fighters"]}

    recs = []
    for f in d["fighters"]:
        r, m = f["ratings"], f["measured"]
        sl, sp, ph, fi = f["strike_location"], f["strike_position"], f["physical"], f["finishes"]
        row = [
            f["name"], DIVS.index(f["division"]), f["ufc_bouts"], CONF.index(f["confidence"]),
            r["Striking"], r["StrikingDefense"], r["Wrestling"], r["Grappling"], r["Power"], r["Chin"], r["Cardio"],
            _n(m["SLpM"], 2), _n(m["Str_acc"], 1), _n(m["SApM"], 2), _n(m["Str_def"], 1),
            _n(m["TD_per15"], 2), _n(m["TD_def"], 1), _n(m["Sub_per15"], 2), _n(m["Ctrl_per15"], 2), _n(m["cardio_retention"], 2),
            _n(sl["head_pct"]), _n(sl["body_pct"]), _n(sl["leg_pct"]),
            _n(sp["distance_pct"]), _n(sp["clinch_pct"]), _n(sp["ground_pct"]),
            _n(ph["height_in"]), _n(ph["reach_in"]), _si(ph["stance"]), _n(ph["reach_vs_div"], 1),
            fi["ko_wins"], fi["ko_losses"], 1 if f["active"] else 0, f["last_fight_year"] or 0,
            _n(f.get("model_score"), 3),
            fi.get("sub_wins", 0), fi.get("dec_wins", 0), fi.get("total_wins", 0),
            f.get("record", {}).get("losses", 0), f.get("record", {}).get("draws_nc", 0),
            _n(f.get("record", {}).get("max_gap", 0), 1),
            f.get("cardio_rounds", 0),
        ]
        recs.append({"row": row, "name": f["name"], "hist": f.get("history", [])})
    recs.sort(key=lambda x: (x["row"][1], -x["row"][4]))
    f_map = {f["name"]: f for f in d["fighters"]}

    # index map on the FINAL order, then encode each history opponent as a row
    # index (int) when that opponent is rated, else keep the name string
    name_to_idx = {rc["name"]: i for i, rc in enumerate(recs)}

    def normname(s):
        return s.lower().strip().replace(".", "").replace("'", "")
    norm_idx = {normname(rc["name"]): i for i, rc in enumerate(recs)}

    # ── per-fighter career splits (DISPLAY-ONLY, descriptive history) ──────────
    # Record vs longer/shorter-reach opponents and vs striker/grappler styles, from
    # each fighter's own UFC history. Every UFC opponent (1+ bout) is in fighters or
    # prospects, so opponent reach/style is fully resolvable. Shown only behind a hard
    # sample guard (>=5 fights per side) and framed as descriptive, NOT predictive —
    # league-wide these splits are weak, and thin per-fighter samples are noisy.
    def _style3(rt):
        s = rt.get("Striking"); sd = rt.get("StrikingDefense")
        wr = rt.get("Wrestling"); gr = rt.get("Grappling")
        if None in (s, sd, wr, gr):
            return None
        diff = (s + sd) / 2 - (wr + gr) / 2
        return "striker" if diff > 5 else "grappler" if diff < -5 else "balanced"
    _opp_reach, _opp_style = {}, {}
    for fr in (d.get("fighters", []) + d.get("prospects", [])):
        nn = normname(fr["name"])
        rch = (fr.get("physical") or {}).get("reach_in")
        if rch is not None:
            _opp_reach[nn] = rch
        st = _style3(fr.get("ratings") or {})
        if st:
            _opp_style[nn] = st

    def career_splits(name, hist):
        me = (f_map.get(name, {}).get("physical") or {}).get("reach_in")
        rl = [0, 0]; rs = [0, 0]; stk = [0, 0]; grp = [0, 0]
        for e in (hist or []):
            opp, won = e[0], (e[2] if len(e) > 2 else None)
            if won not in (0, 1):
                continue
            nn = normname(opp); orr = _opp_reach.get(nn); ost = _opp_style.get(nn)
            if me is not None and orr is not None:
                (rl if orr > me else rs if orr < me else [0, 0])[0 if won else 1] += 1
            if ost == "striker":
                stk[0 if won else 1] += 1
            elif ost == "grappler":
                grp[0 if won else 1] += 1
        out = {}
        if rl[0] + rl[1] >= 5 and rs[0] + rs[1] >= 5:
            out["reach"] = {"longer": rl, "shorter": rs}
        if stk[0] + stk[1] >= 5 and grp[0] + grp[1] >= 5:
            out["style"] = {"striker": stk, "grappler": grp}
        return out or None

    rows = []
    for rc in recs:
        enc = []
        for entry in rc["hist"]:
            opp, year, won = entry[0], entry[1], entry[2]
            meth = entry[3] if len(entry) > 3 else ""
            ref = norm_idx.get(normname(opp), opp)   # int index if rated, else name string
            enc.append([ref, year, won, meth])
        rc["row"].append(enc)   # column 42: history
        sp = split_map.get(rc["name"]) or [None,None,0,None,None,None,0,None]
        rc["row"].extend(sp)   # cols 43-50: vsST_td,ctrl,n,body  vsGR_td,ctrl,n,body
        # recent-form ratings (7 axes, None if <2 recent bouts) — cols 51-57
        rr = f_map[rc["name"]].get("recent_ratings") or [None]*7
        rc["row"].extend(rr)
        # strength-of-schedule percentile (0-100) — col 58
        rc["row"].append(f_map[rc["name"]].get("sos_pct"))
        # control-resistance percentile (0-100) — col 59
        rc["row"].append(f_map[rc["name"]].get("ctrl_def_pct"))
        # model contribution vector (10 features + sos, sums to model_score) — col 60
        rc["row"].append(f_map[rc["name"]].get("model_comp"))
        # age in years as of data-through date (None if unknown) — col 61
        rc["row"].append(f_map[rc["name"]].get("age"))
        # leg-kick exposure: absorbed per 15 (display) — col 62; opp-adjusted excess — col 63
        lk = f_map[rc["name"]].get("legkick") or {}
        rc["row"].append(lk.get("abs_per15"))
        rc["row"].append(lk.get("vuln"))
        # knockdowns landed per 15 min (power translation) — col 64
        rc["row"].append(_n(f_map[rc["name"]]["measured"].get("KD_per15"), 2))
        # submission losses (derived, display-only) — col 65
        rc["row"].append(int((f_map[rc["name"]].get("finishes") or {}).get("sub_losses", 0)))
        _fm = f_map[rc["name"]]
        # knockdowns absorbed per 15 (durability) — col 66
        rc["row"].append(_n((_fm.get("measured") or {}).get("KDabs_per15"), 2))
        # best wins (top-3 rated opponents beaten) as [ref|name, pct] — col 67
        _bw = []
        for _o, _p in (_fm.get("best_wins") or []):
            _bw.append([norm_idx.get(normname(_o), _o), _p])
        rc["row"].append(_bw)
        # ranked-opponent record [w,l] vs top-20% — col 68
        rc["row"].append(_fm.get("ranked_record"))
        # finish rounds (list of round numbers) — col 69
        rc["row"].append(_fm.get("finish_rounds") or [])
        # last fight date (YYYY-MM-DD) — col 70
        rc["row"].append(_fm.get("last_fight_date"))
        # overall percentile (0-100) — col 71
        rc["row"].append(_fm.get("overall_pct"))
        # win% vs a median rated fighter (calibrated) — col 72
        rc["row"].append(_fm.get("vs_avg_pct"))
        # stylistic archetype — col 73
        rc["row"].append(_fm.get("archetype"))
        # stylistic comps (nearest profiles) as row refs — col 74
        rc["row"].append([norm_idx.get(normname(_c), _c) for _c in (_fm.get("comps") or [])])
        # 8 standardized style components for the finish-method read — col 75
        rc["row"].append(_fm.get("style8"))
        # per-fighter career splits (descriptive, guarded) — col 76
        rc["row"].append(career_splits(rc["name"], rc["hist"]))
        rows.append(rc["row"])
    payload = {"divs": DIVS, "conf": CONF, "stance": STANCE, "rows": rows}
    payload["prospects"] = d.get("prospects", [])
    payload["div_avg"] = d.get("div_avg", {})
    payload["finish_models"] = d.get("finish_models")    # finish-method read (display-only)

    # ── regional resume for under-5-fight prospects ────────────────────────
    # SCOUTING CONTEXT ONLY. Read the ranked output of build_regional_sos.py
    # (opponent-quality resume + pro-win weight, from FightMatrix). Keyed by
    # normalized name for the prospect card. This is NEVER fed into the ratings
    # engine or the win model — it is a descriptive display layer, nothing more.
    # Absent file => the block simply doesn't render.
    def _nn(s):
        return s.lower().strip().replace(".", "").replace("'", "")
    reg = {}
    reg_path = HERE / "regional" / "regional_dataset_ranked.json"
    if reg_path.exists():
        try:
            for r in json.loads(reg_path.read_text()):
                reg[_nn(r["name"])] = {
                    "rrs": r.get("RRS"), "per_fight": r.get("rrs_per_fight"),
                    "big_league": r.get("big_league"), "q540": r.get("q540"),
                    "n_ranked": r.get("n_ranked_beat"), "n_major": r.get("n_major_wins"),
                    "pre_bouts": r.get("pre_bouts"),
                    "best": r.get("best_wins", []),
                }
        except Exception:
            reg = {}
    payload["regional"] = reg

    # ── scouting context on prospect cards (DISPLAY-ONLY, never fed to any model) ──
    # Pre-UFC record in major promotions (Bellator/PFL/ONE/RIZIN-tier). IMPORTANT:
    # FightMatrix's "big league" tally INCLUDES UFC fights for many prospects, so the
    # raw number can't be read as pre-UFC experience. We isolate it by subtracting the
    # fighter's UFC record. This is descriptive background only (a prospect who arrives
    # with a proven high-level career elsewhere) — verified to have only a WEAK link to
    # UFC results, so it is not, and must not be presented as, a win predictor.
    raw_reg_path = HERE / "regional" / "regional_dataset.json"
    raw_by_name = {}
    if raw_reg_path.exists():
        try:
            for r in json.loads(raw_reg_path.read_text()).get("prospects", []):
                raw_by_name[_nn(r["name"])] = r
        except Exception:
            raw_by_name = {}
    for p in payload["prospects"]:
        rr = raw_by_name.get(_nn(p.get("name", "")))
        if not rr:
            continue
        bl = rr.get("big_league")
        rec = p.get("record") or {}
        uw, ul = int(rec.get("wins", 0)), int(rec.get("losses", 0))
        if isinstance(bl, (list, tuple)) and len(bl) >= 2:
            pw, pl = max(0, int(bl[0]) - uw), max(0, int(bl[1]) - ul)   # pre-UFC major record
            if (pw + pl) >= 1:
                p["maj"] = [pw, pl]

    # honest walk-forward reliability diagram (compute_calibration.py); display-only
    cal_path = OUT / "calibration.json"
    if cal_path.exists():
        try:
            payload["calibration"] = json.loads(cal_path.read_text())
        except Exception:
            pass

    try:
        import pandas as pd
        ev = pd.read_csv(DATA / "ufc_event_details.csv")
        through = pd.to_datetime(ev["DATE"], errors="coerce").max()
        payload["through"] = through.strftime("%B %-d, %Y")
        payload["through_iso"] = through.strftime("%Y-%m-%d")
    except Exception:
        payload["through"] = None
    up = load_upcoming()
    if up:
        payload["upcoming"] = up
    data = json.dumps(payload, separators=(",", ":"))
    (OUT / "widget_data.json").write_text(data)

    html = TEMPLATE.read_text().replace("__UFC_DATA__", data)
    if "__UFC_DATA__" in html:
        raise SystemExit("template placeholder not replaced")
    # Bake in market odds from the latest fightodds.io pull(s), if present.
    odds_path = HERE / "odds" / "parsed_odds.json"
    odds_json = odds_path.read_text().strip() if odds_path.exists() else "{}"
    n_odds = 0
    try:
        n_odds = len(json.loads(odds_json))
    except Exception:
        odds_json = "{}"
    html = html.replace("__ODDS_DATA__", odds_json)
    if "__ODDS_DATA__" in html:
        raise SystemExit("odds placeholder not replaced")
    # odds freshness: use the parsed_odds.json modification date as the import date
    try:
        import datetime as _dt
        _asof = _dt.date.fromtimestamp(odds_path.stat().st_mtime).strftime("%b %-d, %Y") if (odds_path.exists() and n_odds) else ""
    except Exception:
        _asof = ""
    html = html.replace("__ODDS_ASOF__", json.dumps(_asof))
    (OUT / "ufc_skill_explorer.html").write_text(html)
    up_n = len(up["bouts"]) if up else 0
    print(f"Built ufc_skill_explorer.html ({len(html)//1024} KB, {len(rows)} fighters, {up_n} upcoming bouts, {n_odds} fights priced)")

    # Self-check the shipped data: integrity invariants that must hold regardless of
    # data updates. Fails loudly (non-zero exit) so a future change can't silently
    # corrupt the tool. Soft-fails to a warning only if the validator itself errors.
    try:
        import validate_build
        validate_build.main(strict=True)
    except SystemExit:
        raise
    except Exception as _e:
        print(f"[validate] could not run integrity guard: {_e}")


if __name__ == "__main__":
    main()
