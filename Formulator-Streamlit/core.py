"""
Shared code for every page of Formulator Builder.

  PART A  load the data (four CSV files you can open in Excel)
  PART B  formulas: state, phases, stability theory, suggested formula
  PART C  compliance: ingredient rules per country
  PART D  sensory theory
  PART E  drawing: sensory chart, tables, page style
  PART F  suggestions: a free optimiser that searches for formulas
  PART G  small helpers shared by the pages
  PART H  the interactive pages (studio.html, bench.html) and their link to Streamlit
  PART I  Claude: the Ask Claude button in the corner of every page
  PART J  sample trial log
"""
import base64
import csv
import json
import os
import random
import re
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

HERE = Path(__file__).parent


# ============================================================
# PART A — LOAD THE DATA
# ============================================================
def _records(name):
    df = pd.read_csv(HERE / name)
    # turn empty cells (NaN) into None so they are easy to test with "is None"
    return df.astype(object).where(pd.notna(df), None).to_dict("records")


@st.cache_data
def load_data():
    prods = pd.read_csv(HERE / "products.csv").set_index("code").to_dict("index")
    return (_records("ingredients.csv"), prods, _records("regulations.csv"), _records("obligations.csv"),
            _records("watchlist.csv"))


INGREDIENTS, PRODUCTS, REGULATIONS, OBLIGATIONS, WATCHLIST = load_data()
ING = {i["id"]: i for i in INGREDIENTS}
COUNTRIES = list(dict.fromkeys(r["country"] for r in OBLIGATIONS))


def roles_of(i):
    """The jobs an ingredient does in a formula, main job first. Some do two: the "roles" column of
    ingredients.csv lists them separated by ; (an ingredient without one falls back to its category)."""
    return [r.strip() for r in str(i.get("roles") or i["cat"]).split(";") if r.strip()]


def pool_key(role):
    """Where the Suggest page keeps the ingredients allowed for one job."""
    return "sg_pool_" + re.sub(r"\W+", "_", role).strip("_").lower()


ROLE_GROUPS = {}  # main job -> ingredient ids, in the order of the file
for _i in INGREDIENTS:
    if _i["id"] != "aqua":
        ROLE_GROUPS.setdefault(roles_of(_i)[0], []).append(_i["id"])

# colour of each category (used in the bottle and the ingredient list)
# Same families as the Studio bottle: light blues = oil phase, deep blues = water phase, oranges = added cool.
CATEGORIES = {
    "Base": "#0297DE", "Humectant": "#0277B0", "Emollient": "#CDEBFA", "Butter": "#A5DBF6",
    "Fatty alcohol": "#F2FAFE", "Emulsifier": "#7FCBF2", "Thickener / sensory": "#03A9F4",
    "Antioxidant": "#FFC4B0", "pH adjuster": "#FFA588", "Preservative": "#FC734D",
}

# design tokens for the parts Streamlit's theme cannot reach (SVG pictures, tags, tables)
TOKENS = {
    "light": {"ink": "#2a251f", "muted": "#6b6357", "line": "#d9d2c6", "surface": "#fdfcfa", "sunken": "#f6f3ee",
              "bottle_line": "#3a352e", "A": "#1c6a86", "B": "#a8520f", "on_tag": "#ffffff", "on_primary": "#ffffff",
              "high": "#b3261e", "warn": "#8a5a00", "ok": "#2e6b4f"},
    "dark": {"ink": "#EAF4FA", "muted": "#9DB2BF", "line": "#1B2B36", "surface": "#02070A", "sunken": "#0A1820",
             "bottle_line": "#BFD3DE", "A": "#0297DE", "B": "#FC734D", "on_tag": "#02070A", "on_primary": "#02070A",
             "high": "#FC734D", "warn": "#FFB199", "ok": "#7CCBF2"},
}
MONO = "'IBM Plex Mono', ui-monospace, monospace"


def T():
    """Design tokens. The whole site uses the midnight Studio look, whatever theme the browser asks for."""
    return TOKENS["dark"]


SLOTS = ("A", "B")
# first-visit example, so the comparison has something to show; "Clear all" empties it
EXAMPLES = {
    "A": ("Light lotion (example)", ["glycerin", "coco", "dba", "cetearyl", "glucoside", "kcp", "tapioca"]),
    "B": ("Rich cream (example)", ["glycerin", "cct", "almond", "shea", "cetearyl", "glucoside", "kcp"]),
}


def fmt(n):
    if n is None:
        return "–"
    return f"{n:.4f}".rstrip("0").rstrip(".") if abs(n) < 0.01 else f"{n:.2f}".rstrip("0").rstrip(".")


# The target pH of a formula is a range, because the right pH depends on the ingredients and the product.
PH_DEFAULT = (5.0, 6.0)


def ph_span(ph):
    """Target pH as (low, high). A single number, as older saved formulas have, becomes a range of one point."""
    if ph is None:
        return PH_DEFAULT
    if isinstance(ph, (int, float)):
        return (float(ph), float(ph))
    lo, hi = float(ph[0]), float(ph[1])
    return (min(lo, hi), max(lo, hi))


def ph_text(ph):
    lo, hi = ph_span(ph)
    return fmt(lo) if lo == hi else f"{fmt(lo)}–{fmt(hi)}"


# ============================================================
# PART B — FORMULAS: STATE, PHASES, STABILITY THEORY
# ============================================================
def pct_key(slot, ing_id):
    return f"{slot}_pct_{ing_id}"


def sel_key(slot, ing_id):
    return f"{slot}_sel_{ing_id}"


def persistent_keys():
    """Widget values that must survive a visit to another page (Streamlit drops widgets that are not on screen)."""
    marks = ("_sel_", "_pct_", "_name", "_ptype", "_ph")
    return [k for k in st.session_state if (k[:2] in ("A_", "B_") and any(m in k for m in marks)) or k.startswith("sg_")] + [
        k for k in ("countries", "save_slot", "pick_ing", "guide_country") if k in st.session_state]


def selected_ids(slot):
    """Ingredients that are in the formula (water is always included)."""
    return ["aqua"] + [i["id"] for i in INGREDIENTS
                       if i["id"] != "aqua" and st.session_state.get(sel_key(slot, i["id"]), False)]


def current_items(slot):
    """List of the selected ingredients with their % (water = q.s. to 100)."""
    items = []
    for ing_id in selected_ids(slot):
        if ing_id == "aqua":
            continue
        items.append({**ING[ing_id], "pct": float(st.session_state.get(pct_key(slot, ing_id), ING[ing_id]["typ"]) or 0)})
    water = 100 - sum(i["pct"] for i in items)
    return [{**ING["aqua"], "pct": water}] + items


# the three phases of a formulation sheet: A water, B oil, C extra additives added when cool
PHASES = {"water": ("Water phase", "A"), "oil": ("Oil phase", "B"), "extra": ("Extra additives", "C")}


def phase_of(i):
    return "extra" if i["phase"] == "Cool-down" else "oil" if i["phase"] == "Oil" else "water"


def phases(items):
    """Ingredients above 0%, grouped by phase and sorted largest first."""
    out = {p: [] for p in PHASES}
    for i in sorted(items, key=lambda i: -i["pct"]):
        if i["pct"] > 0:
            out[phase_of(i)].append(i)
    return out


# Each rule adds one check: "high" = -20 points, "warn" = -7 points.
def analyse(items, ptype, ph):
    checks = []
    add = lambda level, title, detail: checks.append((level, title, detail))

    water = items[0]["pct"]
    oils = [i for i in items if i["phase"] == "Oil" and i["cat"] != "Emulsifier"]
    emuls = [i for i in items if i["cat"] == "Emulsifier"]
    fatty = [i for i in items if i["cat"] == "Fatty alcohol"]
    pres = [i for i in items if i["cat"] == "Preservative"]
    oil_total = sum(i["pct"] for i in oils)
    em_total = sum(i["pct"] for i in emuls)
    fatty_total = sum(i["pct"] for i in fatty)
    ids = [i["id"] for i in items]

    if len(items) == 1:
        return [("info", "Only water so far", "Add ingredients, or press “Suggest starting formula”.")], None

    # 1. Total and water
    if water < 0:
        add("high", "Over 100%", f"Non-water ingredients add up to {fmt(100 - water)}%. Reduce some amounts.")
    elif water < 50:
        add("warn", "Low water content", f"Water is only {fmt(water)}%. Very low water can make an O/W emulsion too thick or flip it to W/O.")
    else:
        add("ok", "Total = 100%", f"Water q.s. to {fmt(water)}%.")

    # 2. Use levels
    for i in items[1:]:
        if i["qs"] or i["min"] is None:
            continue
        if i["pct"] > i["max"]:
            add("high", f"{i['short']} above usual maximum", f"{fmt(i['pct'])}% is above the usual {fmt(i['max'])}%.")
        elif i["pct"] < i["min"]:
            add("warn", f"{i['short']} below usual level", f"{fmt(i['pct'])}% may be too little to work (usual {fmt(i['min'])}–{fmt(i['max'])}%).")

    # 3. Emulsifier present and amount
    if oil_total > 0 and not emuls:
        add("high", "No emulsifier", "Oil and water will separate. Add an emulsifier such as Cetearyl Glucoside or Potassium Cetyl Phosphate.")
    elif oil_total > 0:
        ratio = em_total / oil_total
        txt = f"Emulsifier is {ratio * 100:.0f}% of the oil phase (rule of thumb: about 15–30%)."
        if ratio < 0.10:
            add("high", "Too little emulsifier for the oil load", txt)
        elif ratio < 0.15:
            add("warn", "Emulsifier on the low side", txt)
        elif ratio > 0.40:
            add("warn", "Excess emulsifier", txt + " Too much can feel soapy or tacky.")
        else:
            add("ok", "Emulsifier amount OK", txt)

    # 4. HLB match (weighted averages)
    known = [i for i in oils if i["rhlb"] is not None and i["pct"] > 0]
    unknown = [i for i in oils if i["rhlb"] is None and i["pct"] > 0]
    if known and emuls and em_total > 0:
        r_hlb = sum(i["rhlb"] * i["pct"] for i in known) / sum(i["pct"] for i in known)
        b_hlb = sum(i["hlb"] * i["pct"] for i in emuls) / em_total
        d = abs(r_hlb - b_hlb)
        txt = (f"Oil phase needs HLB ≈ {r_hlb:.1f}; your emulsifier blend gives ≈ {b_hlb:.1f} (difference {d:.1f}). "
               "Indicative only: glucoside/phosphate systems also stabilise through liquid crystals.")
        add("ok" if d <= 1.5 else "warn" if d <= 3 else "high",
            "HLB matched" if d <= 1.5 else "HLB slightly off" if d <= 3 else "HLB mismatch", txt)
    if unknown:
        add("info", "Missing required-HLB data",
            f"{', '.join(i['short'] for i in unknown)} left out of the HLB calculation. Add the value from the supplier TDS.")

    # 5. Oil phase size
    if oil_total > 0:
        if oil_total < 5:
            add("warn", "Very light oil phase", f"Oil phase {fmt(oil_total)}%: likely a thin, watery lotion.")
        elif oil_total > 40:
            add("high", "Oil phase very high", f"Oil phase {fmt(oil_total)}% is hard to keep stable as O/W.")
        elif oil_total > 30:
            add("warn", "Rich oil phase", f"Oil phase {fmt(oil_total)}%: needs a strong emulsifier system.")
        else:
            add("ok", "Oil phase in lotion range", f"Oil phase {fmt(oil_total)}% (typical 10–30%).")

    # 6. Fatty alcohol (structure)
    if oil_total > 0 and fatty_total == 0:
        add("warn", "No fatty alcohol", "Without a thickener such as cetearyl alcohol, the lotion stays thin and droplets can cream (rise) over time.")
    elif fatty_total > 7:
        add("warn", "High fatty alcohol", f"{fmt(fatty_total)}% may feel waxy and keep thickening during storage.")

    # 7. Duplicates
    if "cetstear" in ids and "cetearyl" in ids:
        add("warn", "Duplicate ingredient", "Cetyl/Stearyl Alcohol and Cetearyl Alcohol are the same material. Keep only one.")

    # 8. Shea graininess
    for i in items:
        if i["id"] == "shea" and i["pct"] > 5:
            add("warn", "Graininess risk", f"Shea butter at {fmt(i['pct'])}% can form crystals. Cool the batch quickly while stirring.")

    # 9. Oxidation
    unsat = [i for i in items if i["unsaturated"] and i["pct"] > 0]
    if unsat and not any(i["cat"] == "Antioxidant" for i in items):
        add("warn", "Rancidity risk",
            f"{' and '.join(i['short'] for i in unsat)} can oxidise. Consider adding an antioxidant (e.g. tocopherol 0.1–0.5%).")

    # 10. Preservation (legal limits for preservatives are checked in the compliance section)
    if not pres:
        add("high", "No preservative", "Any water-based product will grow microbes. Add a preservative system.")
    if "mit" in ids and len(pres) == 1:
        add("warn", "Weak against yeast and mould", "MIT alone has poor antifungal activity. A second preservative is usually needed.")
    if "tapioca" in ids and pres:
        add("info", "Starch raises microbial load", "Check preservative efficacy with a challenge test.")

    # 11. pH: the target is a range, and every ingredient with a working range should cover it
    lo, hi = ph_span(ph)
    for i in items:
        if i["ph_min"] is None:
            continue
        works = f"{i['short']} works best at pH {fmt(i['ph_min'])}–{fmt(i['ph_max'])}"
        if hi < i["ph_min"] or lo > i["ph_max"]:
            add("warn", f"pH outside {i['short']} range", f"Target pH {ph_text(ph)}; {works}.")
        elif lo < i["ph_min"] or hi > i["ph_max"]:
            add("info", f"Keep the pH inside the {i['short']} range", f"{works}, which covers only part of your target pH {ph_text(ph)}.")
    if "naoh" in ids and not any(i["cat"] == "Acid / polymer" for i in items):
        add("info", "NaOH may not be needed", "Nothing acidic is in the formula yet. Add NaOH only if the measured pH is below target.")

    # 12. Charge clash
    charges = {i["charge"] for i in items}
    if "anionic" in charges and "cationic" in charges:
        add("high", "Charge incompatibility", "Anionic and cationic ingredients can react and destabilise the emulsion.")

    score = 100 - 20 * sum(c[0] == "high" for c in checks) - 7 * sum(c[0] == "warn" for c in checks)
    if water < 0:
        score = 0
    return checks, max(0, min(100, score))


def complete_formula(slot):
    """Tick what a basic O/W emulsion is missing and untick what cannot stay. Returns (added, removed)."""
    ids = selected_ids(slot)[1:]
    cats = {ING[i]["cat"] for i in ids}
    ptype = st.session_state[f"{slot}_ptype"]
    lo, hi = ph_span(st.session_state.get(f"{slot}_ph"))
    added, removed = [], []
    if "Humectant" not in cats:
        added.append("glycerin")
    if not cats & {"Emollient", "Butter"}:
        added.append("coco")
    if "Fatty alcohol" not in cats:
        added.append("cetearyl")
    if "Emulsifier" not in cats:
        added.append("glucoside")
        if ING["kcp"]["ph_min"] <= lo and hi <= ING["kcp"]["ph_max"]:
            added.append("kcp")
    if ptype == "Rinse-off" and "Preservative" not in cats:
        added.append("mit")
    if ptype == "Leave-on" and "mit" in ids:
        removed.append("mit")
    if ptype == "Leave-on" and "pheno" in ING and not [i for i in ids if ING[i]["cat"] == "Preservative" and i != "mit"]:
        added.append("pheno")
    if "toco" in ING and "Antioxidant" not in cats and any(ING[i]["unsaturated"] for i in ids + added):
        added.append("toco")
    if "cetstear" in ids and "cetearyl" in ids:
        removed.append("cetstear")
    for i in added:
        st.session_state[sel_key(slot, i)] = True
    for i in removed:
        st.session_state[sel_key(slot, i)] = False
    return added, removed


def suggest(slot):
    """Theory-based first draft: fill the gaps, typical levels, oil phase ≤ 25%, emulsifier ≈ 22% of it, HLB-matched split."""
    added, removed = complete_formula(slot)
    ids = [i for i in selected_ids(slot) if i != "aqua"]
    for i in ids:
        st.session_state[pct_key(slot, i)] = float(ING[i]["typ"])
    oil_ids = [i for i in ids if ING[i]["phase"] == "Oil" and ING[i]["cat"] != "Emulsifier"]
    em_ids = [i for i in ids if ING[i]["cat"] == "Emulsifier"]
    oil_total = sum(st.session_state[pct_key(slot, i)] for i in oil_ids)
    if oil_total > 25:  # many oils ticked: trim the emollients and butters, not the fatty alcohol
        soft = [i for i in oil_ids if ING[i]["cat"] in ("Emollient", "Butter")]
        soft_total = sum(st.session_state[pct_key(slot, i)] for i in soft)
        scale = max(0, soft_total - (oil_total - 25)) / soft_total
        for i in soft:
            st.session_state[pct_key(slot, i)] = round(max(ING[i]["min"], ING[i]["typ"] * scale), 1)
        oil_total = sum(st.session_state[pct_key(slot, i)] for i in oil_ids)
    em_target = 0.22 * oil_total
    known = [i for i in oil_ids if ING[i]["rhlb"] is not None]
    r_hlb = (sum(ING[i]["rhlb"] * st.session_state[pct_key(slot, i)] for i in known)
             / sum(st.session_state[pct_key(slot, i)] for i in known)) if known else 10
    shares = {i: 1 / len(em_ids) for i in em_ids}
    if len(em_ids) == 2:
        a, b = ING[em_ids[0]], ING[em_ids[1]]
        if a["hlb"] != b["hlb"]:
            x = min(0.7, max(0.3, (r_hlb - b["hlb"]) / (a["hlb"] - b["hlb"])))
            shares = {a["id"]: x, b["id"]: 1 - x}
    for i in em_ids:
        e = ING[i]
        st.session_state[pct_key(slot, i)] = round(min(e["max"], max(e["min"], shares[i] * em_target)), 1)
    return added, removed


def set_formula(slot, amounts, name=None, ptype=None, ph=None):
    """Replace formula A or B. amounts is {ingredient id: %}; name, product type and pH stay as they are unless given.
    Everything is checked first, because the interactive pages send it from the browser."""
    amounts = {i: max(0.0, min(100.0, float(p))) for i, p in (amounts or {}).items() if i in ING and i != "aqua"}
    for i in INGREDIENTS:
        st.session_state[sel_key(slot, i["id"])] = i["id"] in amounts
    for i, p in amounts.items():
        st.session_state[pct_key(slot, i)] = p
    if name is not None:
        st.session_state[f"{slot}_name"] = str(name).strip()[:60] or f"Formula {slot}"
    if ptype in ("Leave-on", "Rinse-off"):
        st.session_state[f"{slot}_ptype"] = ptype
    if ph is not None:
        try:
            lo, hi = ph_span(ph)
            st.session_state[f"{slot}_ph"] = (max(3.0, min(9.0, lo)), max(3.0, min(9.0, hi)))
        except (TypeError, ValueError, IndexError):
            pass


def formula_state(slot):
    """Formula A or B in the shape the interactive pages use."""
    return {"name": st.session_state.get(f"{slot}_name", f"Formula {slot}"),
            "ptype": st.session_state.get(f"{slot}_ptype", "Leave-on"),
            "ph": list(ph_span(st.session_state.get(f"{slot}_ph"))),
            "amounts": {i["id"]: i["pct"] for i in current_items(slot)[1:]}}


def build_formulas():
    """Everything the pages need to know about formula A and B."""
    F = {}
    for slot in SLOTS:
        items = current_items(slot)
        ptype, ph = st.session_state[f"{slot}_ptype"], ph_span(st.session_state.get(f"{slot}_ph"))
        checks, score = analyse(items, ptype, ph)
        F[slot] = {"slot": slot, "name": st.session_state[f"{slot}_name"], "items": items, "ptype": ptype, "ph": ph,
                   "checks": checks, "score": score, "stats": stats(items), "sense": sensory(items)}
    return F


# ============================================================
# PART C — COMPLIANCE: INGREDIENT RULES PER COUNTRY
# regulations.csv holds one rule per row:
#   prohibited  the ingredient may not be used (in the products named in applies_to)
#   max_pct     the ingredient may not exceed "limit" % in the formula
#   max_ph      the finished product pH must stay below "limit"
# An ingredient with no row for a country is "no rule on file", which is not the same as allowed.
# ============================================================
def compliance(items, ptype, ph, country):
    """Returns (overall, rows). overall is "fail", "ok" or None; rows are (level, title, detail, source, confidence)."""
    present = {i["id"]: i for i in items[1:] if i["pct"] > 0}
    if not present:
        return None, []
    rows, applied, covered = [], set(), set()
    for r in REGULATIONS:
        if r["country"] != country or r["ingredient"] not in present:
            continue
        i, name = present[r["ingredient"]], present[r["ingredient"]]["short"]
        covered.add(i["id"])
        if r["applies_to"] not in ("Both", ptype):
            continue
        applied.add(i["id"])
        src = (r["note"], r["source"], r["confidence"])
        if r["rule"] == "prohibited":
            rows.append(("high", f"{name} is not allowed in {ptype.lower()} products", *src))
        elif r["rule"] == "max_pct":
            if i["pct"] > r["limit"]:
                rows.append(("high", f"{name} is above the legal limit", f"{fmt(i['pct'])}% against a limit of {fmt(r['limit'])}%. {r['note']}", *src[1:]))
            else:
                rows.append(("ok", f"{name} is within the legal limit", f"{fmt(i['pct'])}% against a limit of {fmt(r['limit'])}%. {r['note']}", *src[1:]))
        elif r["rule"] == "max_ph":
            lo, hi = ph_span(ph)
            if lo >= r["limit"]:
                rows.append(("high", f"Target pH is too high for {name}", f"Target pH {ph_text(ph)} must stay below {fmt(r['limit'])}. {r['note']}", *src[1:]))
            elif hi >= r["limit"]:
                rows.append(("info", f"Keep the pH below {fmt(r['limit'])} for {name}", f"Part of your target pH {ph_text(ph)} is above the limit. {r['note']}", *src[1:]))
            else:
                rows.append(("ok", f"Target pH is within the {name} limit", f"Target pH {ph_text(ph)} is below {fmt(r['limit'])}. {r['note']}", *src[1:]))
    for ing_id in covered - applied:
        rows.append(("ok", f"{present[ing_id]['short']}: no limit for {ptype.lower()} products", "The rule on file applies only to the other product type.", "", "sourced"))
    unchecked = [i["short"] for i in present.values() if i["id"] not in covered]
    if unchecked:
        rows.append(("info", "No rule on file", f"{', '.join(unchecked)}. This is not a clearance. Check the country's lists of prohibited, "
                     "restricted and permitted ingredients, and add any rule you find to regulations.csv.", "", "sourced"))
    return ("fail" if any(r[0] == "high" for r in rows) else "ok"), rows


STATUS_WORDS = {"fail": "Not compliant", "ok": "No conflicts found", None: "Nothing to check"}


# ============================================================
# PART D — SENSORY THEORY
# Each ingredient has a 0–5 score per sensory column in ingredients.csv
# (negative = reduces it, e.g. starch reduces greasiness).
# Score × % adds up to a "load". level = 10 × load / (load + mid), so a load
# equal to "mid" gives 5/10 and the feel levels off at high use, as it does on skin.
# ============================================================
SENSES = {  # key: (label, stage of use, load that gives 5/10)
    "body": ("Body", "pick-up", 20),
    "spread": ("Spreadability", "rub-out", None),
    "absorb": ("Absorption speed", "rub-out", None),
    "grease": ("Greasiness", "after-feel", 30),
    "tack": ("Tackiness", "after-feel", 24),
    "dry": ("Dry, powdery finish", "after-feel", 40),
    "film": ("Skin film", "after-feel", 35),
}
# key: (what the higher formula will likely do, the theory behind it)
FEEL = {
    "body": ("feels thicker on pick-up", "Fatty alcohols and emulsifiers build a gel network in the water phase, and butters add solid fat."),
    "spread": ("spreads more easily", "Low-viscosity esters spread faster than triglycerides, plant oils and butters."),
    "absorb": ("sinks in faster", "Light esters leave the surface quickly, while heavy oils and butters stay on top."),
    "grease": ("feels greasier after rub-in", "Plant oils and butters leave more residue. Starch absorbs some of it."),
    "tack": ("feels tackier as it dries", "Glycerin holds water at the skin surface as the product dries down."),
    "dry": ("has a drier, more powdery finish", "Light esters and starch leave little residue behind."),
    "film": ("leaves a heavier skin film", "Butters, oils and fatty alcohols form an occlusive layer that slows water loss."),
}


def stats(items):
    """The structural numbers of a formula."""
    oils = [i for i in items if i["phase"] == "Oil" and i["cat"] != "Emulsifier"]
    emuls = [i for i in items if i["cat"] == "Emulsifier"]
    oil = sum(i["pct"] for i in oils)
    em = sum(i["pct"] for i in emuls)
    return {"water": items[0]["pct"], "oil": oil, "em": em,
            "fatty": sum(i["pct"] for i in items if i["cat"] == "Fatty alcohol"),
            "ratio": em / oil * 100 if oil > 0 else None}


def sensory(items):
    """Predicted feel on a 0–10 scale, or None when nothing has sensory data yet."""
    known = [i for i in items[1:] if i["body"] is not None and i["pct"] > 0]
    if not known:
        return None
    clamp = lambda n: max(0, min(10, n))
    out = {}
    for key, (_, _, mid) in SENSES.items():
        if mid:
            load = max(0, sum(i[key] * i["pct"] for i in known))
            out[key] = 10 * load / (load + mid)
    spreaders = [i for i in known if i["spread"] is not None]
    out["spread"] = None
    if spreaders:
        average = sum(i["spread"] * i["pct"] for i in spreaders) / sum(i["pct"] for i in spreaders)
        out["spread"] = clamp(2 * average - 0.3 * max(0, out["body"] - 5))  # thick products drag
    out["absorb"] = clamp(10 - 0.6 * out["grease"] - 0.4 * out["film"])
    return out


def drivers(high, low, key):
    """The two ingredients that explain most of the gap between two formulas on one attribute."""
    cols = ("grease", "film") if key == "absorb" else (key,)
    push = lambda i: sum((i[c] or 0) * i["pct"] for c in cols)
    gap = {}
    for i in high[1:]:
        gap[i["short"]] = gap.get(i["short"], 0) + push(i)
    for i in low[1:]:
        gap[i["short"]] = gap.get(i["short"], 0) - push(i)
    return [name for name, n in sorted(gap.items(), key=lambda p: -p[1])[:2] if n > 0]


def product_form(sense):
    body = sense["body"]
    return "Milk or serum" if body < 3 else "Lotion" if body < 6 else "Cream" if body < 8 else "Rich cream or butter"


def sensory_flags(f):
    """Feel problems that come from one ingredient being pushed too far."""
    flags = []
    s = f["stats"]
    level = {i["id"]: i["pct"] for i in f["items"]}
    if level.get("glycerin", 0) > 8:
        flags.append(f"Glycerin at {fmt(level['glycerin'])}% can feel sticky.")
    if level.get("tapioca", 0) > 5:
        flags.append(f"Tapioca starch at {fmt(level['tapioca'])}% can leave white marks or drag.")
    if level.get("shea", 0) > 5:
        flags.append(f"Shea butter at {fmt(level['shea'])}% can feel grainy if the batch cools slowly.")
    if s["ratio"] is not None and s["ratio"] > 40:
        flags.append(f"Emulsifier at {s['ratio']:.0f}% of the oil phase can feel soapy or tacky.")
    if s["fatty"] > 7:
        flags.append(f"Fatty alcohol at {fmt(s['fatty'])}% can feel waxy.")
    return flags


def feel_differences(a, b):
    """Attributes that differ by at least 1 point, largest first."""
    out = []
    for key, (label, _, _) in SENSES.items():
        x, y = a["sense"][key], b["sense"][key]
        if x is None or y is None or abs(x - y) < 1:
            continue
        hi, lo = (a, b) if x > y else (b, a)
        # absorption falls as grease and film rise, so its gap comes from the slower formula
        names = drivers(lo["items"], hi["items"], key) if key == "absorb" else drivers(hi["items"], lo["items"], key)
        cause = f" Gap comes mostly from {' and '.join(names)}." if names else ""
        out.append((abs(x - y), hi["slot"], FEEL[key][0], f"{label} {max(x, y):.1f} against {min(x, y):.1f}.{cause} {FEEL[key][1]}"))
    return [row[1:] for row in sorted(out, key=lambda r: -r[0])]


# ============================================================
# PART E — DRAWING: SENSORY CHART, TABLES, PAGE STYLE
# ============================================================
def marker(slot, x, y):
    """A is a circle and B a diamond, so the formulas differ by shape as well as colour."""
    t = T()
    ring = f'stroke="{t["surface"]}" stroke-width="2"'
    if slot == "A":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{t["A"]}" {ring}/>'
    return f'<rect x="{x - 6:.1f}" y="{y - 6:.1f}" width="12" height="12" transform="rotate(45 {x:.1f} {y:.1f})" fill="{t["B"]}" {ring}/>'


def sensory_svg(a, b):
    """Paired dots: one row per attribute, A and B on the same 0–10 scale."""
    t = T()
    left, right, row, head = 150, 466, 46, 34
    x_of = lambda n: left + (right - left) * n / 10
    height = head + row * len(SENSES) + 22
    text = lambda x, y, s, fill, size=13, anchor="start", weight=400, family="inherit": (
        f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" text-anchor="{anchor}" '
        f'font-weight="{weight}" font-family="{family}">{s}</text>')
    grid = ""
    for n in (0, 5, 10):
        grid += f'<line x1="{x_of(n)}" x2="{x_of(n)}" y1="{head - 8}" y2="{height - 20}" stroke="{t["line"]}"/>'
        grid += text(x_of(n), height - 5, n, t["muted"], 12, "middle", family=MONO)
    rows = ""
    for n, (key, (label, stage, _)) in enumerate(SENSES.items()):
        y = head + row * n + row / 2 - 4
        va, vb = a["sense"][key], b["sense"][key]
        rows += text(0, y - 3, label, t["ink"], 14, weight=500) + text(0, y + 13, stage, t["muted"], 12)
        if va is not None and vb is not None:
            rows += f'<line x1="{x_of(va):.1f}" x2="{x_of(vb):.1f}" y1="{y}" y2="{y}" stroke="{t["muted"]}" stroke-width="2"/>'
        rows += marker("A", x_of(va), y) if va is not None else ""
        rows += marker("B", x_of(vb), y) if vb is not None else ""
        show = lambda v: "–" if v is None else f"{v:.1f}"
        rows += text(486, y + 5, show(va), t["ink"], 13, family=MONO) + text(530, y + 5, show(vb), t["ink"], 13, family=MONO)
    legend = (marker("A", 8, 12) + text(22, 17, "Formula A", t["ink"], 13)
              + marker("B", 118, 12) + text(132, 17, "Formula B", t["ink"], 13)
              + text(486, 17, "A", t["muted"], 12, family=MONO) + text(530, 17, "B", t["muted"], 12, family=MONO))
    return (f'<svg viewBox="0 0 566 {height}" role="img" aria-label="Predicted sensory profile of formula A and B" '
            f'style="width:100%;display:block">{legend}{grid}{rows}</svg>')


def tag(slot):
    return f'<span class="fx-tag fx-{slot}">{slot}</span>'


def text_table(head, rows):
    """A table of words (table_html is for numbers): everything left-aligned in the normal font."""
    return table_html(head, rows).replace('class="fx-table"', 'class="fx-table fx-text"', 1)


def pill(overall):
    kind = {"fail": "high", "ok": "ok", None: "muted"}[overall]
    return f'<span class="fx-pill fx-{kind}">{STATUS_WORDS[overall]}</span>'


def table_html(head, rows):
    """A small comparison table; the first column is text and the rest are numbers."""
    cells = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="fx-table"><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table>'


SITE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter+Tight:wght@400;500;600&display=swap');
:root{--fx-ink:#02070A;--fx-blue:#0297DE;--fx-orange:#FC734D;--fx-paper:#EAF4FA;--fx-muted:rgba(234,244,250,.62);
  --fx-faint:rgba(234,244,250,.38);--fx-line:rgba(234,244,250,.14);--fx-panel:rgba(234,244,250,.045);
  --fx-serif:"PP Editorial New","Instrument Serif",Georgia,serif;
  --fx-sans:"PP Neue Montreal","Neue Montreal","Inter Tight",system-ui,sans-serif}
.stApp{color:var(--fx-paper);font-family:var(--fx-sans);background-color:var(--fx-ink);background-attachment:fixed;
  background-image:radial-gradient(700px circle at 18% -5%,rgba(2,151,222,.16),transparent 70%),radial-gradient(900px circle at 92% 108%,rgba(252,115,77,.07),transparent 70%)}
[data-testid="stHeader"]{background:rgba(2,7,10,.86);backdrop-filter:blur(10px);border-bottom:1px solid var(--fx-line)}
[data-testid="stSidebar"]{background:#040d12;border-right:1px solid var(--fx-line)}
[data-testid="stMainBlockContainer"]{max-width:1280px;padding-top:5.5rem}
.stApp p,.stApp li,.stApp label,.stApp input,.stApp textarea,.stApp button,.stApp [data-baseweb="select"]{font-family:var(--fx-sans)}
.stApp h1,.stApp h2,.stApp h3,.stApp h4{font-family:var(--fx-serif)!important;font-weight:400!important;letter-spacing:-.01em;line-height:1.05;color:var(--fx-paper)}
.stApp h2{font-size:clamp(34px,3.6vw,52px)}
.stApp h3{font-size:clamp(28px,2.8vw,40px)}
.stApp h4{font-size:28px}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:var(--fx-muted)}
.stApp hr{border-color:var(--fx-line)}
.stApp a{color:var(--fx-blue)}

/* page header, the same shape as the Studio's section headers */
.fx-eyebrow{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:var(--fx-faint)}
.fx-eyebrow b{color:var(--fx-orange);font-weight:500;margin-right:.6em}
.stApp h1.fx-h1{font-size:clamp(44px,5.4vw,84px);margin:14px 0 18px;padding:0;line-height:1}
.fx-h1 em{font-style:italic;color:var(--fx-orange)}
.fx-lead{color:var(--fx-muted);max-width:62ch;margin:0 0 26px;font-size:16px;line-height:1.5}

/* buttons are pills; the main action is electric blue */
.stApp .stButton button,.stApp .stDownloadButton button,.stApp .stFormSubmitButton button,.stApp [data-testid="stPageLink"] a{
  border-radius:999px;border:1px solid var(--fx-line);background:transparent;color:var(--fx-paper);padding:.45rem 1.1rem;transition:border-color .2s,background .2s}
.stApp .stButton button:hover,.stApp .stDownloadButton button:hover{border-color:var(--fx-paper);color:var(--fx-paper)}
.stApp button[kind="primary"],.stApp [data-testid="stBaseButton-primary"]{background:var(--fx-blue);border-color:var(--fx-blue)}
.stApp button[kind="primary"]:hover,.stApp [data-testid="stBaseButton-primary"]:hover{background:#28b0f2;border-color:#28b0f2}
.stApp button[kind="primary"] p,.stApp [data-testid="stBaseButton-primary"] p{color:var(--fx-ink);font-weight:500}
.stApp button:disabled{opacity:.4}

/* inputs sit on the same faint panel as the Studio cards */
.stApp [data-baseweb="input"],.stApp [data-baseweb="base-input"],.stApp [data-baseweb="textarea"],.stApp [data-baseweb="select"]>div{
  background:var(--fx-panel)!important;border-color:var(--fx-line)!important;border-radius:10px!important}
.stApp [data-baseweb="base-input"]{border:0!important}
.stApp [data-baseweb="input"]:focus-within,.stApp [data-baseweb="select"]>div:focus-within{border-color:var(--fx-blue)!important}
.stApp [data-testid="stNumberInput"] button{background:transparent;color:var(--fx-muted)}
.stApp [data-baseweb="tag"]{background:rgba(2,151,222,.2)!important;border-radius:999px!important;color:var(--fx-paper)!important}
.stApp [data-testid="stWidgetLabel"] p{color:var(--fx-muted);font-size:14px}
.stApp [data-testid="stFileUploaderDropzone"]{background:var(--fx-panel);border:1px dashed var(--fx-line);border-radius:16px}

/* cards: expanders, alerts, metrics, tables */
.stApp [data-testid="stExpander"] details{border:1px solid var(--fx-line);border-radius:16px;background:var(--fx-panel);overflow:hidden}
.stApp [data-testid="stExpander"] summary:hover{color:var(--fx-blue)}
.stApp [data-testid="stAlert"]{border-radius:14px}
.stApp [data-testid="stAlertContainer"]{border-radius:14px;border:1px solid var(--fx-line)}
.stApp [data-testid="stMetric"]{border:1px solid var(--fx-line);border-radius:16px;background:var(--fx-panel);padding:16px 18px}
.stApp [data-testid="stMetricValue"]{font-family:var(--fx-serif);font-size:54px;line-height:1}
.stApp [data-testid="stMetricLabel"] p{color:var(--fx-muted)}
.stApp [data-testid="stDataFrame"]{border:1px solid var(--fx-line);border-radius:14px;overflow:hidden}
.stApp [data-baseweb="tab-list"]{gap:4px}
.stApp button[data-baseweb="tab"]{border-radius:999px;padding:6px 14px}
.stApp button[data-baseweb="tab"][aria-selected="true"]{background:var(--fx-panel)}

/* section headers inside a page, and the small step cards */
.fx-section{margin-top:72px}
.stApp h2.fx-h2{font-size:clamp(36px,4vw,60px);margin:12px 0 14px;padding:0;line-height:1}
.fx-h2 em{font-style:italic;color:var(--fx-orange)}
.fx-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:0 0 28px}
.fx-step{border:1px solid var(--fx-line);border-radius:16px;background:var(--fx-panel);padding:16px 18px}
.fx-step span{font-size:12px;letter-spacing:.14em;color:var(--fx-orange)}
.fx-step b{display:block;font-family:var(--fx-serif);font-weight:400;font-size:24px;line-height:1.1;margin:6px 0 8px}
.fx-step p{margin:0;color:var(--fx-muted);font-size:14px!important;line-height:1.45}
.stApp [data-testid="stPills"] button,.stApp [data-testid="stBaseButton-pills"],.stApp [data-testid="stBaseButton-pillsActive"]{border-radius:999px}

/* Ask Claude: a button fixed to the bottom right corner of every page */
.st-key-fx_claude{position:fixed;right:22px;bottom:22px;z-index:1000;width:auto!important}
.st-key-fx_claude [data-testid="stPopover"]>div>button,.st-key-fx_claude [data-testid="stPopoverButton"]{background:var(--fx-blue);border:1px solid var(--fx-blue);
  border-radius:999px;padding:.6rem 1.2rem;box-shadow:0 12px 40px rgba(2,151,222,.35)}
.st-key-fx_claude [data-testid="stPopover"]>div>button:hover,.st-key-fx_claude [data-testid="stPopoverButton"]:hover{background:#28b0f2;border-color:#28b0f2}
.st-key-fx_claude [data-testid="stPopover"]>div>button *,.st-key-fx_claude [data-testid="stPopoverButton"] *{color:var(--fx-ink);font-weight:500}
[data-testid="stPopoverBody"]{background:#040d12;border:1px solid var(--fx-line);border-radius:20px;width:min(420px,calc(100vw - 28px));max-height:min(680px,calc(100vh - 110px));
  box-shadow:0 24px 80px rgba(0,0,0,.6)}
p.fx-chat-title{font-family:var(--fx-serif)!important;font-size:30px!important;line-height:1;margin:0 0 8px}
.fx-chat-title em{font-style:italic;color:var(--fx-orange)}
p.fx-chat-sub{color:var(--fx-muted);font-size:13px!important;margin:0 0 4px}
.fx-msg{max-width:92%;width:fit-content;padding:10px 14px;border-radius:16px;font-size:14.5px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere;margin:0 0 2px}
.fx-msg.fx-user{margin-left:auto;background:rgba(2,151,222,.16);border:1px solid rgba(2,151,222,.4);border-bottom-right-radius:4px}
.fx-msg.fx-assistant{background:var(--fx-panel);border:1px solid var(--fx-line);border-bottom-left-radius:4px}
.fx-msg.fx-error{border:1px solid rgba(252,115,77,.5);background:rgba(252,115,77,.08)}
"""


def page_header(number, eyebrow, title, accent, lead):
    """The big header at the top of every page: small numbered label, serif title with one orange word, a lead line."""
    st.markdown(f'<div class="fx-eyebrow"><b>{number}</b>{escape(eyebrow)}</div>'
                f'<h1 class="fx-h1">{escape(title)} <em>{escape(accent)}</em></h1>'
                f'<p class="fx-lead">{escape(lead)}</p>', unsafe_allow_html=True)


def section_header(number, eyebrow, title, accent, lead=""):
    """A numbered section inside a page, the same shape as the sections of the Studio."""
    st.markdown(f'<div class="fx-section"><div class="fx-eyebrow"><b>{number}</b>{escape(eyebrow)}</div>'
                f'<h2 class="fx-h2">{escape(title)} <em>{escape(accent)}</em></h2>'
                + (f'<p class="fx-lead">{escape(lead)}</p>' if lead else "") + "</div>", unsafe_allow_html=True)


def inject_css():
    t = T()
    st.markdown(f"<style>{SITE_CSS}</style>", unsafe_allow_html=True)
    st.markdown(f"""<style>
.fx-tag {{display:inline-block;min-width:1.5em;padding:0 .4em;border-radius:3px;text-align:center;font-weight:600;color:{t['on_tag']}}}
.fx-A {{background:{t['A']}}}
.fx-B {{background:{t['B']}}}
.fx-table {{width:100%;border-collapse:collapse;font-size:14px}}
.fx-table th {{text-align:right;font-weight:500;color:{t['muted']};border:0;border-bottom:1px solid {t['line']};padding:6px 8px}}
.fx-table td {{text-align:right;border:0;border-bottom:1px solid {t['line']};padding:6px 8px;font-family:{MONO};font-variant-numeric:tabular-nums}}
.fx-table th:first-child, .fx-table td:first-child {{text-align:left;padding-left:0;font-family:inherit}}
.fx-note {{margin:0 0 12px}}
.fx-note small {{color:{t['muted']};display:block}}
.fx-table.fx-text th, .fx-table.fx-text td {{text-align:left;font-family:inherit;vertical-align:top}}
.fx-pill {{display:inline-block;padding:1px 10px;border:1px solid currentColor;border-radius:999px;font-size:14px;font-weight:500}}
.fx-high {{color:{t['high']}}}
.fx-ok {{color:{t['ok']}}}
.fx-muted {{color:{t['muted']}}}
button[kind="primary"], button[kind="primary"] p {{color:{t['on_primary']}}}
</style>""", unsafe_allow_html=True)


# ============================================================
# PART F — SUGGESTIONS: A FREE OPTIMISER
# No account and no cost: it tries thousands of combinations of the ingredients you allow,
# scores each one with the same stability, compliance and sensory theory used elsewhere,
# and keeps the best three. fitness = stability score - 5 x (average distance from the sensory goal).
# A formula that breaks a chosen country's rule is thrown away, not just marked down.
# ============================================================
GOALS = {  # sensory goal on the 0-10 scale of the Sensory page
    "Light, fast-absorbing lotion": {"body": 4, "spread": 8, "absorb": 8, "grease": 1, "tack": 2, "dry": 5, "film": 3},
    "Silky, non-greasy lotion": {"body": 5, "spread": 7, "absorb": 7, "grease": 1, "tack": 1, "dry": 4, "film": 3},
    "Rich, nourishing cream": {"body": 7, "spread": 4, "absorb": 4, "grease": 5, "tack": 3, "dry": 1, "film": 6},
}


def eligible(pool, ptype):
    """Ingredients the optimiser can use. It needs sensory scores, cannot measure pH for NaOH,
    drops the duplicate fatty alcohol, and never puts MIT in a leave-on product."""
    pool = [i for i in pool if ING[i]["body"] is not None and ING[i]["cat"] != "pH adjuster"
            and not (ptype == "Leave-on" and i == "mit")]
    return [i for i in pool if not (i == "cetstear" and "cetearyl" in pool)]


def has_core(pool):
    """A suggestion needs an oil, a fatty alcohol and an emulsifier to make an emulsion."""
    cats = {ING[i]["cat"] for i in pool}
    return bool(cats & {"Emollient", "Butter"}) and "Fatty alcohol" in cats and "Emulsifier" in cats


def optimise(pool, ptype, ph, countries, target, seed=0, tries=6000, count=3):
    """Up to "count" distinct formulas, best first. Each is a dict with amounts, stability, dist, sense and items."""
    rng = random.Random(seed)
    pool = eligible(pool, ptype)
    pick = lambda *cats: [i for i in pool if ING[i]["cat"] in cats]
    oils, fatty, emuls = pick("Emollient", "Butter"), pick("Fatty alcohol"), pick("Emulsifier")
    humect, extra, pres = pick("Humectant"), pick("Thickener / sensory"), pick("Preservative")
    if not (oils and fatty and emuls):
        return []
    clamp = lambda n, lo, hi: max(lo, min(hi, n))

    def amount(i, factor):
        e = ING[i]
        return e["typ"] if e["max"] < 0.01 else round(clamp(e["typ"] * factor, e["min"], e["max"]), 1)

    def build(state):
        """Add the emulsifiers: about r x oil phase in total, split by HLB when there are two."""
        base, ems, r = state
        a = dict(base)
        oil = sum(p for i, p in base.items() if ING[i]["phase"] == "Oil")
        known = [(ING[i]["rhlb"], p) for i, p in base.items() if ING[i]["rhlb"] is not None and ING[i]["phase"] == "Oil"]
        r_hlb = sum(h * p for h, p in known) / sum(p for _, p in known) if known else 10
        shares = {ems[0]: 1.0}
        if len(ems) == 2:
            e1, e2 = ING[ems[0]], ING[ems[1]]
            x = clamp((r_hlb - e2["hlb"]) / (e1["hlb"] - e2["hlb"]), .3, .7) if e1["hlb"] != e2["hlb"] else .5
            shares = {ems[0]: x, ems[1]: 1 - x}
        for i, s in shares.items():
            e = ING[i]
            a[i] = round(clamp(s * r * oil, e["min"], e["max"]), 1)
        return a

    seen = {}

    def evaluate(state):
        a = build(state)
        key = tuple(sorted(a.items()))
        if key not in seen:
            items = [{**ING["aqua"], "pct": 100 - sum(a.values())}] + [{**ING[i], "pct": p} for i, p in a.items()]
            seen[key] = None
            if items[0]["pct"] >= 40:
                _, stability = analyse(items, ptype, ph)
                if all(compliance(items, ptype, ph, c)[0] != "fail" for c in countries):
                    sense = sensory(items)
                    gaps = [abs(sense[k] - v) for k, v in target.items() if sense[k] is not None]
                    dist = sum(gaps) / len(gaps)
                    seen[key] = {"state": state, "amounts": a, "items": items, "sense": sense, "stability": stability,
                                 "dist": dist, "fit": stability - 5 * dist, "ptype": ptype, "ph": ph}
        return seen[key]

    for _ in range(tries):
        chosen = rng.sample(oils, rng.randint(1, min(3, len(oils)))) + [rng.choice(fatty)]
        if humect and rng.random() < .85:
            chosen.append(rng.choice(humect))
        if extra and rng.random() < .4:
            chosen.append(rng.choice(extra))
        if pres and rng.random() < .5:
            chosen.append(rng.choice(pres))
        evaluate(({i: amount(i, rng.uniform(.6, 1.6)) for i in chosen},
                  rng.sample(emuls, rng.randint(1, min(2, len(emuls)))), rng.uniform(.17, .30)))

    # polish the best draws: nudge one amount (or the emulsifier ratio) at a time and keep what helps
    for best in sorted((r for r in seen.values() if r), key=lambda r: -r["fit"])[:12]:
        for _ in range(40):
            base, ems, r = best["state"]
            base = dict(base)
            if rng.random() < .15:
                r = clamp(r + rng.choice([-.02, .02]), .15, .35)
            else:
                i = rng.choice(list(base))
                if ING[i]["max"] < 0.01:
                    continue
                step = rng.choice([-1, 1]) * max(.5, base[i] * .2)
                base[i] = round(clamp(base[i] + step, ING[i]["min"], ING[i]["max"]), 1)
            cand = evaluate((base, ems, r))
            if cand and cand["fit"] > best["fit"]:
                best = cand

    ranked = sorted((r for r in seen.values() if r), key=lambda r: -r["fit"])
    out, used = [], set()
    for res in ranked:  # prefer different ingredient sets over tweaks of one
        ids = frozenset(res["amounts"])
        if ids not in used:
            used.add(ids)
            out.append(res)
        if len(out) == count:
            break
    return out + [r for r in ranked if r not in out][:count - len(out)]


def load_suggestion(result, slot, name):
    """Put a suggested formula into formula A or B (runs as a button callback)."""
    set_formula(slot, result["amounts"], name, result["ptype"], result["ph"])
    st.session_state["sg_loaded"] = slot

# ============================================================
# PART G — SMALL HELPERS SHARED BY THE PAGES
# ============================================================
def recipe_rows(items):
    """Rows for table_html: each phase as a bold heading, then its ingredients largest first."""
    rows = []
    for phase, (label, letter) in PHASES.items():
        members = [i for i in items if i["pct"] > 0 and phase_of(i) == phase]
        if members:
            rows.append([f"<b>{label} ({letter})</b>", ""])
            rows += [[escape(i["short"]), f"{fmt(i['pct'])}%"] for i in sorted(members, key=lambda i: -i["pct"])]
    return rows


def rule_text(country, ing_id):
    """What regulations.csv says about one ingredient in one country, in plain words, or None."""
    parts = []
    for r in REGULATIONS:
        if r["country"] != country or r["ingredient"] != ing_id:
            continue
        where = "All products" if r["applies_to"] == "Both" else str(r["applies_to"])
        what = {"prohibited": "not allowed", "max_pct": f"up to {fmt(r['limit'])}%",
                "max_ph": f"product pH below {fmt(r['limit'])}"}.get(r["rule"], str(r["rule"]))
        parts.append(f"{where}: {what}")
    return "; ".join(parts) or None


def amount_changes(old, new):
    """Plain-language list of what changed between two {ingredient id: %} dicts."""
    out = []
    for i, p in new.items():
        if i not in old:
            out.append(f"Added {ING[i]['short']} ({fmt(p)}%)")
        elif abs(p - old[i]) >= 0.05:
            out.append(f"{ING[i]['short']}: {fmt(old[i])}% → {fmt(p)}%")
    out += [f"Removed {ING[i]['short']}" for i in old if i not in new]
    return out


def sense_changes(old, new):
    """Sensory attributes that moved by at least 0.3 points between two predictions, largest move first."""
    rows = []
    for key, (label, _, _) in SENSES.items():
        a, b = (old or {}).get(key), (new or {}).get(key)
        if a is not None and b is not None and abs(b - a) >= 0.3:
            rows.append((abs(b - a), f"{label}: {a:.1f} → {b:.1f} ({b - a:+.1f})".replace("-", "−").replace("−>", "->")))
    return [text for _, text in sorted(rows, reverse=True)]


# ============================================================
# PART H — THE INTERACTIVE PAGES AND THEIR LINK TO STREAMLIT
# studio.html (Studio) and bench.html (Formulation) are plain HTML, CSS and JavaScript shown inside the page.
# Both use fx_shared.js. Python hands them the data from the CSV files, reads the messages they type into a
# hidden text box, and writes its replies into a hidden element that they re-read.
#
# Fonts: put the PP Editorial New and PP Neue Montreal files (.woff2 or .otf, named PPEditorialNew-Regular,
# PPEditorialNew-Italic, PPNeueMontreal-Book, PPNeueMontreal-Medium) in a folder named fonts next to app.py and
# they are used automatically. Without them the pages fall back to Instrument Serif and Inter Tight.
# ============================================================
WEIGHTS = {"thin": 100, "ultralight": 200, "light": 300, "book": 400, "regular": 400, "medium": 500,
           "semibold": 600, "ultrabold": 800, "bold": 700}


def raw_rows(name):
    with open(HERE / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def font_faces():
    """@font-face rules for every licensed font file found in the fonts folder, embedded in the page."""
    css = ""
    for f in sorted((HERE / "fonts").glob("*")):
        low, ext = f.stem.lower().replace(" ", "").replace("-", ""), f.suffix.lower()
        family = "PP Editorial New" if "editorialnew" in low else "PP Neue Montreal" if "neuemontreal" in low else None
        if family is None or ext not in (".woff2", ".woff", ".otf", ".ttf"):
            continue
        weight = next((w for k, w in WEIGHTS.items() if k in low), 400)
        style = "italic" if "italic" in low else "normal"
        kind = {".woff2": "woff2", ".woff": "woff", ".otf": "opentype", ".ttf": "truetype"}[ext]
        data = base64.b64encode(f.read_bytes()).decode()
        css += (f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:{style};font-display:swap;'
                f'src:url(data:font/{ext[1:]};base64,{data}) format("{kind}")}}\n')
    return css


@st.cache_data
def _page(name, stamp):  # stamp changes when a file changes, which makes Streamlit build the page again
    html = (HERE / name).read_text(encoding="utf-8")
    data = {"ingredients": raw_rows("ingredients.csv"), "products": raw_rows("products.csv"),
            "regulations": raw_rows("regulations.csv")}
    shared = (HERE / "fx_shared.js").read_text(encoding="utf-8")
    html = html.replace('<script src="fx_shared.js"></script>', f"<script>\n{shared}\n</script>")
    html = html.replace("/*__DATA__*/null", json.dumps(data).replace("</", "<\\/"))
    return html.replace("/*__FONTS__*/", font_faces())


def interactive_page(name):
    """studio.html or bench.html as one self-contained page: shared script, data and fonts written into it."""
    watched = [HERE / name, HERE / "fx_shared.js", HERE / "ingredients.csv", HERE / "products.csv",
               HERE / "regulations.csv", *(HERE / "fonts").glob("*")]
    return _page(name, tuple(p.stat().st_mtime for p in watched if p.is_file()))


def inbox_event(key):
    """The newest message an interactive page typed into its hidden text box. Each message arrives once."""
    try:
        event = json.loads(st.session_state.get(key) or "null")
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get("id") == st.session_state.get(key + "_done"):
        return None
    st.session_state[key + "_done"] = event.get("id")
    return event


def outbox(element_id, payload):
    """Write Python's reply where the interactive page can read it."""
    text = base64.b64encode(json.dumps(payload).encode()).decode()
    st.markdown(f'<div id="{element_id}" hidden>{text}</div>', unsafe_allow_html=True)


# ============================================================
# PART I — CLAUDE
# Ask Claude needs an API key. Never put the key in a file you upload to GitHub. Instead:
#   on Streamlit Community Cloud:  app menu > Settings > Secrets, and add the line
#                                  ANTHROPIC_API_KEY = "sk-ant-..."
#   on your own computer:          put the same line in .streamlit/secrets.toml (keep that file off GitHub)
# A visitor can also type their own key into the Ask Claude panel. It is kept in memory for that visit only.
# Without a key everything else still works and the panel says Claude is not connected.
# ============================================================
MODEL = "claude-opus-5-5"
MAX_QUESTIONS = 40  # per visit on the site's own key, so one visitor cannot run up the bill
STARTERS = ["What should I change first?", "How can I make it feel lighter?", "Explain my stability score"]


def secret(name):
    try:
        value = st.secrets.get(name)
    except Exception:  # no secrets file at all
        value = None
    return value or os.environ.get(name)


def claude_key():
    return st.session_state.get("fx_user_key") or secret("ANTHROPIC_API_KEY")


def claude_ready():
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(claude_key())


def system_prompt():
    library = "\n".join(
        f"- {i['inci']} ({i['short']}): {', '.join(roles_of(i))}, {i['phase']} phase, "
        f"usual {fmt(i['min'])}-{fmt(i['max'])}%. {i['notes']}" for i in INGREDIENTS)
    return (
        "You are the formulation assistant inside Formulator Builder, a tool for building oil-in-water cosmetic "
        "emulsions such as body lotions and creams. The person asking is working on the formulation, or the two "
        "formulations A and B, shown in the <current_formula> block of their latest message. It lists the "
        "ingredients by phase with % w/w and the tool's theory-based stability checks, and may include the "
        "predicted feel and a compliance summary.\n\n"
        "Answer the question about that formulation directly and practically: say what to change, by how much, and "
        "why. Prefer ingredients from the library below, because those are the ones the person can add in the tool; "
        "if something outside the library would clearly work better, say so and name it. The stability score and "
        "feel numbers are predictions from formulation theory, not measurements, so treat them as indications. "
        "Legal limits vary by country and change over time; when one matters, give what you know and tell the "
        "person to confirm it against the current official text. A formula is only proven by making a batch and "
        "running stability and preservative challenge tests; mention this when it bears on the question, without "
        "repeating it in every answer.\n\n"
        "The answer is shown in a small chat panel that displays plain text only. Write short paragraphs in plain "
        "sentences, with no Markdown symbols such as asterisks, pound signs or tables. Keep most answers under "
        "150 words unless the question needs more.\n\n"
        f"Ingredient library:\n{library}")


def ask_claude(history, question, context):
    """Returns (role, text): role is "assistant" for an answer or "error" for a message to show instead."""
    try:
        import anthropic
    except ImportError:
        return "error", "Claude is not installed on the server. Add the line anthropic to requirements.txt and redeploy."
    key = claude_key()
    if not key:
        return "error", "Claude is not connected yet. Add ANTHROPIC_API_KEY to the app's secrets, or enter your own key."
    messages = [{"role": m["role"], "content": m["text"]} for m in history if m["role"] in ("user", "assistant")]
    messages.append({"role": "user", "content": f"<current_formula>\n{context}\n</current_formula>\n\n{question}"})
    request = dict(model=MODEL, max_tokens=16000, system=system_prompt(), messages=messages,
                   output_config={"effort": "medium"})
    client = anthropic.Anthropic(api_key=key)
    try:
        try:
            # if the safety system declines a question, let the API hand it to a fallback model
            reply = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request)
        except TypeError:  # an older anthropic package without the fallbacks option
            reply = client.messages.create(**request)
    except anthropic.AuthenticationError:
        return "error", "The Claude API key was rejected. Check the key and try again."
    except anthropic.RateLimitError:
        return "error", "Claude is busy right now. Wait a moment and ask again."
    except anthropic.APIStatusError as e:
        return "error", f"Claude returned an error ({e.status_code}). Try again in a moment."
    except anthropic.APIConnectionError:
        return "error", "Could not reach Claude. Check the internet connection and try again."
    if reply.stop_reason == "refusal":
        return "error", "Claude declined to answer that question. Try asking it differently."
    text = "".join(b.text for b in reply.content if b.type == "text").strip()
    return ("assistant", text) if text else ("error", "Claude sent back an empty answer. Try again.")


def answer(question, context, q=None):
    """Ask Claude and add the question and the reply to this visit's conversation, shared by every page."""
    chat = st.session_state.setdefault("fx_chat", [])
    question = str(question)[:2000]
    own_key = bool(st.session_state.get("fx_user_key"))
    if not own_key and sum(m["role"] == "user" for m in chat) >= MAX_QUESTIONS:
        role, text = "error", "You have reached the question limit for this visit. Reload the page to start again."
    else:
        role, text = ask_claude(chat, question, str(context)[:20000])
    chat.append({"role": "user", "text": question, "q": q})
    chat.append({"role": role, "text": text})
    return role, text


def formula_text(f, countries=()):
    """One formula in plain words, for Claude."""
    lines = [f"Formula {f['slot']}: {f['name']} ({f['ptype']}, target pH {ph_text(f['ph'])})"]
    for phase, (label, _) in PHASES.items():
        members = [i for i in f["items"] if i["pct"] > 0 and phase_of(i) == phase]
        if members:
            lines.append(f"{label}: " + ", ".join(f"{i['inci']} {fmt(i['pct'])}%" for i in members))
    lines.append(f"Stability score (theory): {'n/a' if f['score'] is None else f['score']}/100")
    lines += [f"[{level}] {title}: {detail}" for level, title, detail in f["checks"] if level != "ok"]
    if f["sense"]:
        feel = ", ".join(f"{label} {f['sense'][k]:.1f}" for k, (label, _, _) in SENSES.items() if f["sense"][k] is not None)
        lines.append(f"Predicted feel, 0-10 (reads as {product_form(f['sense']).lower()}): {feel}")
    for country in countries:
        overall, rows = compliance(f["items"], f["ptype"], f["ph"], country)
        problems = "; ".join(title for level, title, *_ in rows if level == "high")
        lines.append(f"Compliance in {country}: {STATUS_WORDS[overall]}" + (f" ({problems})" if problems else ""))
    return "\n".join(lines)


def claude_corner():
    """The Ask Claude button in the bottom right corner. It opens a small chat about formulas A and B."""
    chat = st.session_state.setdefault("fx_chat", [])
    bubble = lambda m: f'<div class="fx-msg fx-{m["role"]}">{escape(m["text"])}</div>'
    with st.container(key="fx_claude"):
        with st.popover("Ask Claude"):
            st.markdown('<p class="fx-chat-title">Ask <em>Claude</em></p><p class="fx-chat-sub">Claude sees formulas A and B: '
                        'their ingredients, amounts, stability checks, predicted feel and compliance.</p>',
                        unsafe_allow_html=True)
            box = st.container(height=320, border=False) if chat else st.container()
            for m in chat:
                box.markdown(bubble(m), unsafe_allow_html=True)
            picked = None
            if not chat:
                for n, text in enumerate(STARTERS):
                    if st.button(text, key=f"fx_starter_{n}"):
                        picked = text
            with st.form("fx_claude_form", clear_on_submit=True, border=False):
                typed = st.text_area("Your question", key="fx_claude_q", max_chars=2000, height=80,
                                     placeholder="Ask about formula A or B", label_visibility="collapsed")
                sent = st.form_submit_button("Ask", type="primary")
            question = picked or (typed.strip() if sent and typed else None)
            if question:
                box.markdown(bubble({"role": "user", "text": question}), unsafe_allow_html=True)
                with box:
                    with st.spinner("Claude is thinking…"):
                        F = build_formulas()
                        countries = st.session_state.get("countries", [])
                        answer(question, "\n\n".join(formula_text(F[s], countries) for s in SLOTS))
                st.rerun()
            if not claude_ready():
                st.caption("Claude is not connected yet. The site owner adds ANTHROPIC_API_KEY to the app's secrets, "
                           "or you can use your own key below.")
            else:
                st.caption("Claude's answers are guidance, not a substitute for stability, safety and challenge testing.")
            with st.expander("Use your own Claude API key"):
                st.caption("Optional. Create a key at platform.claude.com. It is kept in memory for this visit only "
                           "and is never saved or shown.")
                typed_key = st.text_input("Anthropic API key", type="password", key="fx_user_key_in",
                                          placeholder="sk-ant-…", label_visibility="collapsed")
                if typed_key:
                    st.session_state["fx_user_key"] = typed_key.strip()
                if st.session_state.get("fx_user_key"):
                    st.caption("Your own key is in use for this visit.")
                    if st.button("Stop using my key", key="fx_user_key_clear"):
                        st.session_state.pop("fx_user_key", None)
                        st.session_state.pop("fx_user_key_in", None)
                        st.rerun()


# ============================================================
# PART J — SAMPLE TRIAL LOG
# Fifteen made-up lab trials, so the Trial log page and its machine-learning model can be tried before you
# have results of your own. They follow the usual patterns: too little emulsifier separates, a lot of shea
# turns grainy, no preservative fails the microbial test. Replace them with your real results.
# ============================================================
TRIAL_FEATURES = [i["inci"] for i in INGREDIENTS]
LOG_COLS = ["date", "name", "product_type", "target_pH", *TRIAL_FEATURES, "predicted_score", "lab_result", "notes"]
RESULTS = ["Not tested yet", "Stable (passed)", "Separation / creaming", "Grainy / crystals", "Viscosity drift",
           "pH drift", "Microbial fail", "Other"]
SAMPLE_TRIALS = [  # name, product type, {ingredient id: %}, lab result, notes
    ("Light lotion v1", "Leave-on", {"glycerin": 4, "coco": 5, "dba": 3, "cetearyl": 3, "glucoside": 1.5, "kcp": 0.9, "tapioca": 2, "pheno": 0.9},
     "Stable (passed)", "12 weeks at 40 °C, no change"),
    ("Light lotion v2, less emulsifier", "Leave-on", {"glycerin": 4, "coco": 6, "dba": 4, "cetearyl": 3, "glucoside": 0.5, "pheno": 0.9},
     "Separation / creaming", "Oil layer after 2 weeks at 45 °C"),
    ("Rich cream v1", "Leave-on", {"glycerin": 4, "cct": 5, "almond": 3, "shea": 3, "cetearyl": 3, "glucoside": 1.7, "kcp": 1.4, "pheno": 0.9, "toco": 0.2},
     "Stable (passed)", "12 weeks at 40 °C, no change"),
    ("Rich cream, high shea", "Leave-on", {"glycerin": 4, "cct": 4, "almond": 3, "shea": 8, "cetearyl": 3, "glucoside": 2, "kcp": 1.5, "pheno": 0.9, "toco": 0.2},
     "Grainy / crystals", "Grains after 3 freeze-thaw cycles"),
    ("Body milk, no fatty alcohol", "Leave-on", {"glycerin": 3, "coco": 6, "cct": 4, "glucoside": 2, "pheno": 0.9},
     "Separation / creaming", "Creamed after 4 weeks at room temperature"),
    ("Body milk v2", "Leave-on", {"glycerin": 3, "coco": 6, "cct": 4, "cetearyl": 2, "glucoside": 2, "kcp": 0.5, "pheno": 0.9},
     "Stable (passed)", "8 weeks at 40 °C, no change"),
    ("Almond lotion, no preservative", "Leave-on", {"glycerin": 4, "almond": 6, "coco": 4, "cetearyl": 3, "glucoside": 2, "kcp": 0.7},
     "Microbial fail", "Failed the challenge test at day 7"),
    ("Almond lotion v2", "Leave-on", {"glycerin": 4, "almond": 6, "coco": 4, "cetearyl": 3, "glucoside": 2, "kcp": 0.7, "pheno": 0.9, "toco": 0.2},
     "Stable (passed)", "Passed the challenge test, 12 weeks at 40 °C"),
    ("Butter cream, low emulsifier", "Leave-on", {"glycerin": 5, "shea": 6, "cct": 6, "almond": 4, "cetearyl": 4, "glucoside": 1, "pheno": 1},
     "Separation / creaming", "Oil ring after 1 week at 45 °C"),
    ("Butter cream v2", "Leave-on", {"glycerin": 5, "shea": 4, "cct": 6, "almond": 4, "cetearyl": 4, "glucoside": 2.2, "kcp": 1.8, "pheno": 1, "toco": 0.3},
     "Stable (passed)", "12 weeks at 40 °C, slight thickening"),
    ("In-shower lotion v1", "Rinse-off", {"glycerin": 3, "cct": 8, "shea": 3, "cetearyl": 4, "glucoside": 2, "kcp": 1.3, "mit": 0.0015},
     "Microbial fail", "Mould at week 6: MIT alone was not enough"),
    ("In-shower lotion v2", "Rinse-off", {"glycerin": 3, "cct": 8, "shea": 3, "cetearyl": 4, "glucoside": 2, "kcp": 1.3, "mit": 0.0015, "pheno": 0.8},
     "Stable (passed)", "Passed the challenge test"),
    ("Starch lotion, heavy fatty alcohol", "Leave-on", {"glycerin": 4, "coco": 5, "cetearyl": 7, "glucoside": 2, "tapioca": 5, "pheno": 0.9},
     "Viscosity drift", "Thickened to a paste by week 8"),
    ("Dry-touch lotion", "Leave-on", {"glycerin": 3, "dba": 6, "coco": 4, "cetearyl": 2.5, "glucoside": 1.6, "kcp": 0.7, "tapioca": 2, "pheno": 0.9},
     "Stable (passed)", "12 weeks at 40 °C, no change"),
    ("Glycerin-rich lotion", "Leave-on", {"glycerin": 8, "coco": 5, "cetearyl": 3, "glucoside": 1.2, "kcp": 0.6, "pheno": 0.9},
     "Not tested yet", "Batch made, stability test starts next week"),
]


def sample_trial_rows():
    """The sample trials as rows of the trial log (one dict per trial, with the columns of LOG_COLS)."""
    rows = []
    for n, (name, ptype, amounts, result, notes) in enumerate(SAMPLE_TRIALS):
        amounts = {i: float(p) for i, p in amounts.items() if i in ING}
        items = [{**ING["aqua"], "pct": 100 - sum(amounts.values())}] + [{**ING[i], "pct": p} for i, p in amounts.items()]
        _, score = analyse(items, ptype, PH_DEFAULT)
        row = {"date": f"2026-{8 + n // 6:02d}-{3 + 4 * (n % 6):02d}", "name": name, "product_type": ptype,
               "target_pH": ph_text(PH_DEFAULT), **{c: 0.0 for c in TRIAL_FEATURES}, "predicted_score": score,
               "lab_result": result, "notes": notes}
        for i in items:
            row[i["inci"]] = round(i["pct"], 4)
        rows.append(row)
    return rows
