"""
Shared code for every page of Formulator Builder.

  PART A  load the data (four CSV files you can open in Excel)
  PART B  formulas: state, phases, stability theory, suggested formula
  PART C  compliance: ingredient rules per country
  PART D  sensory theory
  PART E  drawing: bottle, sensory chart, tables, page style
  PART F  suggestions: a free optimiser that searches for formulas
"""
import random
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

# colour of each category (used in the bottle and the ingredient list)
CATEGORIES = {
    "Base": "#a9d3ee", "Humectant": "#9fd8c8", "Emollient": "#f2c46d", "Butter": "#e8a95b",
    "Fatty alcohol": "#e9dcc0", "Emulsifier": "#c9a3e0", "Thickener / sensory": "#d6c7ae",
    "pH adjuster": "#c4c4c4", "Preservative": "#f29c9c",
}

# design tokens for the parts Streamlit's theme cannot reach (SVG pictures, tags, tables)
TOKENS = {
    "light": {"ink": "#2a251f", "muted": "#6b6357", "line": "#d9d2c6", "surface": "#fdfcfa", "sunken": "#f6f3ee",
              "bottle_line": "#3a352e", "A": "#1c6a86", "B": "#a8520f", "on_tag": "#ffffff", "on_primary": "#ffffff",
              "high": "#b3261e", "warn": "#8a5a00", "ok": "#2e6b4f"},
    "dark": {"ink": "#f3ede3", "muted": "#b3aa9b", "line": "#4a443a", "surface": "#1d1a16", "sunken": "#27231e",
             "bottle_line": "#cfc7b8", "A": "#7cc4e3", "B": "#f0a95c", "on_tag": "#1d1a16", "on_primary": "#1d1a16",
             "high": "#f2a099", "warn": "#e8c06a", "ok": "#8fd0ae"},
}
MONO = "'IBM Plex Mono', ui-monospace, monospace"


def T():
    """Tokens for the theme the viewer is using right now."""
    return TOKENS[st.context.theme.type or "light"]


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
    """Ingredients that are ticked in the sidebar (water is always included)."""
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
        return [("info", "Start by ticking ingredients", "Then press “Suggest starting formula”.")], None

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

    # 11. pH
    for i in items:
        if i["ph_min"] is not None and not (i["ph_min"] <= ph <= i["ph_max"]):
            add("warn", f"pH outside {i['short']} range", f"Target pH {ph}; {i['short']} works best at pH {fmt(i['ph_min'])}–{fmt(i['ph_max'])}.")
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
    ph = st.session_state[f"{slot}_ph"]
    added, removed = [], []
    if "Humectant" not in cats:
        added.append("glycerin")
    if not cats & {"Emollient", "Butter"}:
        added.append("coco")
    if "Fatty alcohol" not in cats:
        added.append("cetearyl")
    if "Emulsifier" not in cats:
        added.append("glucoside")
        if ING["kcp"]["ph_min"] <= ph <= ING["kcp"]["ph_max"]:
            added.append("kcp")
    if ptype == "Rinse-off" and "Preservative" not in cats:
        added.append("mit")
    if ptype == "Leave-on" and "mit" in ids:
        removed.append("mit")
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


def suggest_clicked(slot):
    """Run the suggestion and say what it did, because a formula that was already complete looks unchanged."""
    added, removed = suggest(slot)
    names = lambda ids: ", ".join(ING[i]["short"].rstrip(".") for i in ids)
    parts = [f"Formula {slot}:"]
    if added:
        parts.append(f"Added {names(added)}.")
    if removed:
        parts.append(f"Removed {names(removed)}.")
    st.toast(" ".join(parts + ["Levels set to theory-based starting points."]))


def clear_all(slot):
    for i in INGREDIENTS:
        st.session_state[sel_key(slot, i["id"])] = False


def copy_formula(src, dst):
    """Start one formula from the other, so a single change can be tested against it."""
    for i in INGREDIENTS:
        st.session_state[sel_key(dst, i["id"])] = st.session_state.get(sel_key(src, i["id"]), False)
    for ing_id in selected_ids(src)[1:]:
        st.session_state[pct_key(dst, ing_id)] = st.session_state.get(pct_key(src, ing_id), float(ING[ing_id]["typ"]))
    st.session_state[f"{dst}_name"] = f"{st.session_state[f'{src}_name']} (copy)"
    st.session_state[f"{dst}_ptype"] = st.session_state[f"{src}_ptype"]
    st.session_state[f"{dst}_ph"] = st.session_state[f"{src}_ph"]


def build_formulas():
    """Everything the pages need to know about formula A and B."""
    F = {}
    for slot in SLOTS:
        items = current_items(slot)
        ptype, ph = st.session_state[f"{slot}_ptype"], st.session_state[f"{slot}_ph"]
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
            if ph >= r["limit"]:
                rows.append(("high", f"Target pH is too high for {name}", f"Target pH {ph} must stay below {fmt(r['limit'])}. {r['note']}", *src[1:]))
            else:
                rows.append(("ok", f"Target pH is within the {name} limit", f"Target pH {ph} is below {fmt(r['limit'])}. {r['note']}", *src[1:]))
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
# PART E — DRAWING: BOTTLE, SENSORY CHART, TABLES, PAGE STYLE
# ============================================================
def bottle_html(items, slot):
    """A pump bottle drawn to scale, with the ingredient list beside it grouped by phase.

    Layer heights follow % w/w exactly. The only exception is a layer under about 0.8%,
    which is drawn 2 px thick so it stays visible.
    """
    t = T()
    groups = phases(items)
    ytop, ybot, min_h = 110, 356, 2.0
    H = ybot - ytop
    stack = [i for p in PHASES for i in groups[p]]  # water at the bottom, then oil, then extras
    total = sum(i["pct"] for i in stack) or 1
    small = {i["id"] for i in stack if i["pct"] / total * H < min_h}
    big_total = sum(i["pct"] for i in stack if i["id"] not in small) or 1
    free = H - min_h * len(small)
    height = {i["id"]: min_h if i["id"] in small else free * i["pct"] / big_total for i in stack}

    body = (f"M20,{ytop + 24} Q20,{ytop} 46,{ytop} L104,{ytop} Q130,{ytop} 130,{ytop + 24} "
            f"L130,{ybot - 22} Q130,{ybot} 104,{ybot} L46,{ybot} Q20,{ybot} 20,{ybot - 22} Z")
    y, bands, lines = ybot, "", ""
    for p in PHASES:
        for i in groups[p]:
            y -= height[i["id"]]
            bands += (f'<rect x="14" y="{y:.2f}" width="122" height="{height[i["id"]]:.2f}" '
                      f'fill="{CATEGORIES[i["cat"]]}" stroke="rgba(0,0,0,.12)" stroke-width=".5"/>')
        if groups[p] and p != "extra":
            lines += f'<line x1="14" x2="136" y1="{y:.2f}" y2="{y:.2f}" stroke="{t["bottle_line"]}" stroke-width="1.5"/>'
    svg = (f'<svg viewBox="0 0 150 372" role="img" aria-label="Formula {slot} drawn to scale" style="width:150px;flex:none">'
           f'<defs><clipPath id="clip{slot}"><path d="{body}"/></clipPath></defs>'
           f'<rect x="65" y="56" width="20" height="56" rx="4" fill="#d9d2c6"/>'
           f'<rect x="46" y="36" width="58" height="20" rx="8" fill="#8a8175"/>'
           f'<rect x="98" y="41" width="40" height="9" rx="3" fill="#8a8175"/>'
           f'<rect x="52" y="{ytop - 16}" width="46" height="24" rx="6" fill="#8a8175"/>'
           f'<path d="{body}" fill="#f6f3ee"/><g clip-path="url(#clip{slot})">{bands}{lines}</g>'
           f'<path d="{body}" fill="none" stroke="{t["bottle_line"]}" stroke-width="2.5"/>'
           f'<path d="M32,{ytop + 40} Q30,{(ytop + ybot) // 2} 34,{ybot - 36}" stroke="rgba(255,255,255,.5)" '
           f'stroke-width="5" fill="none" stroke-linecap="round"/></svg>')

    rows = ""
    for p in reversed(list(PHASES)):  # extras on top, as in the bottle
        if not groups[p]:
            continue
        label, letter = PHASES[p]
        rows += (f'<div class="fx-phase"><span>{label} ({letter})</span>'
                 f'<span>{fmt(sum(i["pct"] for i in groups[p]))}%</span></div>')
        for i in groups[p]:
            rows += (f'<div class="fx-line"><span class="fx-sw" style="background:{CATEGORIES[i["cat"]]}"></span>'
                     f'<span>{escape(i["short"])}</span><b>{fmt(i["pct"])}%</b></div>')
    note = ("Drawn to scale. Layers under 0.8% are drawn 2 px thick so they stay visible." if small
            else "Drawn to scale: layer height follows % w/w.")
    return f'<div class="fx-bottle">{svg}<div class="fx-list">{rows}<p class="fx-scale">{note}</p></div></div>'


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


def pill(overall):
    kind = {"fail": "high", "ok": "ok", None: "muted"}[overall]
    return f'<span class="fx-pill fx-{kind}">{STATUS_WORDS[overall]}</span>'


def table_html(head, rows):
    """A small comparison table; the first column is text and the rest are numbers."""
    cells = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="fx-table"><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table>'


def inject_css():
    t = T()
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
.fx-bottle {{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}}
.fx-list {{flex:1;min-width:190px}}
.fx-phase {{display:flex;justify-content:space-between;font-weight:600;border-bottom:1px solid {t['line']};margin-top:14px;padding-bottom:4px}}
.fx-phase:first-child {{margin-top:0}}
.fx-line {{display:flex;gap:8px;align-items:center;padding:3px 0}}
.fx-line b {{margin-left:auto;font-weight:400;font-family:{MONO};font-variant-numeric:tabular-nums}}
.fx-sw {{width:12px;height:12px;border-radius:3px;border:1px solid rgba(0,0,0,.2);flex:none}}
.fx-scale {{color:{t['muted']};font-size:13px;margin:12px 0 0}}
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


def optimise(pool, ptype, ph, countries, target, seed=0, tries=6000):
    """Up to three distinct formulas, best first. Each is a dict with amounts, stability, dist, sense and items."""
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
    for res in ranked:  # prefer three different ingredient sets over three tweaks of one
        ids = frozenset(res["amounts"])
        if ids not in used:
            used.add(ids)
            out.append(res)
        if len(out) == 3:
            break
    return out + [r for r in ranked if r not in out][:3 - len(out)]


def load_suggestion(result, slot, name):
    """Put a suggested formula into formula A or B (runs as a button callback)."""
    for i in INGREDIENTS:
        st.session_state[sel_key(slot, i["id"])] = i["id"] in result["amounts"]
    for i, p in result["amounts"].items():
        st.session_state[pct_key(slot, i)] = p
    st.session_state[f"{slot}_name"] = name
    st.session_state[f"{slot}_ptype"] = result["ptype"]
    st.session_state[f"{slot}_ph"] = result["ph"]
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
        where = {"Leave-on": "Leave-on", "Rinse-off": "Rinse-off", "Both": "All products"}[r["applies_to"]]
        what = {"prohibited": "not allowed", "max_pct": f"up to {fmt(r['limit'])}%",
                "max_ph": f"product pH below {fmt(r['limit'])}"}[r["rule"]]
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