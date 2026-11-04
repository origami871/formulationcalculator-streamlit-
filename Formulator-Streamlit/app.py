"""
Formulator Builder — Streamlit version
=====================================
Run on your own computer:   streamlit run app.py
Data lives in two CSV files you can open in Excel:
  ingredients.csv  -> one row per ingredient (add new rows here)
  products.csv     -> market products (code, name, type, link)
Colours and fonts live in .streamlit/config.toml and TOKENS below.

Two formulas (A and B) are built and compared at the same time.

The file is split into parts:
  PART A  load the data
  PART B  the "theory" (rule-based stability check + suggested formula)
  PART C  the sensory theory + what differs between A and B
  PART D  drawing the bottle and the sensory chart
  PART E  the page layout
  PART F  trial log + machine-learning prediction
"""
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Formulator Builder", page_icon="🧴", layout="wide")
HERE = Path(__file__).parent

# ============================================================
# PART A — LOAD THE DATA
# ============================================================
@st.cache_data
def load_data():
    ing = pd.read_csv(HERE / "ingredients.csv")
    prods = pd.read_csv(HERE / "products.csv")
    # turn empty cells (NaN) into None so they are easy to test with "is None"
    ing = ing.astype(object).where(pd.notna(ing), None)
    return ing.to_dict("records"), prods.set_index("code").to_dict("index")

INGREDIENTS, PRODUCTS = load_data()
ING = {i["id"]: i for i in INGREDIENTS}

# colour of each category (used in the bottle and the cards)
CATEGORIES = {
    "Base": "#a9d3ee", "Humectant": "#9fd8c8", "Emollient": "#f2c46d", "Butter": "#e8a95b",
    "Fatty alcohol": "#e9dcc0", "Emulsifier": "#c9a3e0", "Thickener / sensory": "#d6c7ae",
    "pH adjuster": "#c4c4c4", "Preservative": "#f29c9c",
}

# design tokens for the parts Streamlit's theme cannot reach (SVG pictures, tags, tables)
TOKENS = {
    "light": {"ink": "#2a251f", "muted": "#6b6357", "line": "#d9d2c6", "surface": "#fdfcfa", "sunken": "#f6f3ee",
              "bottle_line": "#3a352e", "A": "#1c6a86", "B": "#a8520f", "on_tag": "#ffffff", "on_primary": "#ffffff"},
    "dark": {"ink": "#f3ede3", "muted": "#b3aa9b", "line": "#4a443a", "surface": "#1d1a16", "sunken": "#27231e",
             "bottle_line": "#cfc7b8", "A": "#7cc4e3", "B": "#f0a95c", "on_tag": "#1d1a16", "on_primary": "#1d1a16"},
}
T = TOKENS[st.context.theme.type or "light"]
MONO = "'IBM Plex Mono', ui-monospace, monospace"

SLOTS = ("A", "B")
# first-visit example, so the comparison has something to show; "Clear all" empties it
EXAMPLES = {
    "A": ("Light lotion (example)", ["glycerin", "coco", "dba", "cetearyl", "glucoside", "kcp", "tapioca"]),
    "B": ("Rich cream (example)", ["glycerin", "cct", "almond", "shea", "cetearyl", "glucoside", "kcp"]),
}


def pct_key(slot, ing_id):
    return f"{slot}_pct_{ing_id}"


def sel_key(slot, ing_id):
    return f"{slot}_sel_{ing_id}"


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


def fmt(n):
    if n is None:
        return "–"
    return f"{n:.4f}".rstrip("0").rstrip(".") if abs(n) < 0.01 else f"{n:.2f}".rstrip("0").rstrip(".")


# ============================================================
# PART B — THE THEORY
# Each rule adds one check: "high" = -20 points, "warn" = -7 points.
# ============================================================
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

    # 10. Preservation
    mit = next((i for i in items if i["id"] == "mit"), None)
    if not pres:
        add("high", "No preservative", "Any water-based product will grow microbes. Add a preservative system.")
    if mit:
        if ptype == "Leave-on":
            add("high", "MIT not allowed in leave-on", "Methylisothiazolinone is prohibited in leave-on cosmetics under the ASEAN Cosmetic Directive. Swap to another preservative.")
        elif mit["pct"] > 0.0015:
            add("high", "MIT above rinse-off limit", f"{fmt(mit['pct'])}% is above the 0.0015% maximum.")
        if len(pres) == 1:
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


def suggest(slot):
    """Theory-based first draft: typical levels, emulsifier ≈ 22% of oil phase, HLB-matched split."""
    ids = [i for i in selected_ids(slot) if i != "aqua"]
    for i in ids:
        st.session_state[pct_key(slot, i)] = float(ING[i]["typ"])
    oil_ids = [i for i in ids if ING[i]["phase"] == "Oil" and ING[i]["cat"] != "Emulsifier"]
    em_ids = [i for i in ids if ING[i]["cat"] == "Emulsifier"]
    oil_total = sum(st.session_state[pct_key(slot, i)] for i in oil_ids)
    if not em_ids or oil_total == 0:
        return
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


# ============================================================
# PART C — THE SENSORY THEORY + WHAT DIFFERS BETWEEN A AND B
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
    """The structural numbers of a formula, used to compare A and B."""
    oils = [i for i in items if i["phase"] == "Oil" and i["cat"] != "Emulsifier"]
    emuls = [i for i in items if i["cat"] == "Emulsifier"]
    oil = sum(i["pct"] for i in oils)
    em = sum(i["pct"] for i in emuls)
    known = [i for i in oils if i["rhlb"] is not None and i["pct"] > 0]
    r_hlb = sum(i["rhlb"] * i["pct"] for i in known) / sum(i["pct"] for i in known) if known else None
    b_hlb = sum(i["hlb"] * i["pct"] for i in emuls) / em if em > 0 else None
    return {"water": items[0]["pct"], "oil": oil, "em": em,
            "fatty": sum(i["pct"] for i in items if i["cat"] == "Fatty alcohol"),
            "ratio": em / oil * 100 if oil > 0 else None, "r_hlb": r_hlb, "b_hlb": b_hlb,
            "gap": abs(r_hlb - b_hlb) if r_hlb is not None and b_hlb is not None else None}


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


def structure_differences(a, b):
    """Plain-language differences in structure and stability, each with its theory."""
    out = []
    sa, sb = a["stats"], b["stats"]

    def gap(key, size):
        """Which formula is higher on a number, if the gap is big enough to matter."""
        if sa[key] is None or sb[key] is None or abs(sa[key] - sb[key]) < size:
            return None
        return (a, b) if sa[key] > sb[key] else (b, a)

    if pair := gap("oil", 3):
        hi, lo = pair
        out.append((hi["slot"], "Larger oil phase", f"{fmt(hi['stats']['oil'])}% against {fmt(lo['stats']['oil'])}%. "
                    "More droplets give a richer product but need more emulsifier to keep them apart."))
    if pair := gap("fatty", 1):
        hi, lo = pair
        out.append((hi["slot"], "Stronger gel network", f"Fatty alcohol {fmt(hi['stats']['fatty'])}% against {fmt(lo['stats']['fatty'])}%. "
                    "More network holds droplets in place and slows creaming, but viscosity can keep rising in storage."))
    if pair := gap("ratio", 5):
        hi, lo = pair
        out.append((hi["slot"], "More emulsifier per unit of oil", f"{hi['stats']['ratio']:.0f}% of the oil phase against {lo['stats']['ratio']:.0f}%. "
                    "More droplet coverage, with a soapy feel if it passes about 40%."))
    if pair := gap("gap", 0.5):
        worse, better = pair
        out.append((better["slot"], "Closer HLB match", f"Difference {better['stats']['gap']:.1f} against {worse['stats']['gap']:.1f}. "
                    "A closer match usually means a finer, more stable emulsion."))
    if a["score"] != b["score"]:
        hi, lo = (a, b) if a["score"] > b["score"] else (b, a)
        out.append((hi["slot"], "Lower predicted stability risk", f"Score {hi['score']} against {lo['score']}."))
    for f, other in ((a, b), (b, a)):
        risks = [c[1] for c in f["checks"] if c[0] in ("high", "warn")]
        only = [r for r in risks if r not in [c[1] for c in other["checks"]]]
        if only:
            out.append((f["slot"], "Risks only this formula has", ", ".join(only) + "."))
    return out


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
# PART D — DRAW THE BOTTLE AND THE SENSORY CHART (SVG pictures)
# ============================================================
def bottle_svg(items, slot):
    items = sorted([i for i in items if i["pct"] > 0], key=lambda i: -i["pct"])
    top, bottom, min_h = 125, 420, 15
    H = bottom - top
    total = sum(i["pct"] for i in items) or 1
    heights, fixed, flex = {}, 0, 0
    for i in items:
        h = i["pct"] / total * H
        if h < min_h:
            heights[i["id"]] = min_h
            fixed += min_h
        else:
            flex += i["pct"]
    for i in items:
        if i["id"] not in heights:
            heights[i["id"]] = max(min_h, (H - fixed) * i["pct"] / flex)
    scale = H / (sum(heights.values()) or 1)

    body = "M44,150 Q44,125 70,122 L150,122 Q176,125 176,150 L176,400 Q176,422 152,422 L68,422 Q44,422 44,400 Z"
    y, bands = bottom, ""
    for i in items:
        h = heights[i["id"]] * scale
        y -= h
        fs = min(12, max(9, h * 0.55))
        bands += (f'<rect x="40" y="{y:.1f}" width="140" height="{h:.1f}" fill="{CATEGORIES[i["cat"]]}" stroke="rgba(0,0,0,.08)"/>'
                  f'<text x="110" y="{y + h / 2:.1f}" text-anchor="middle" dominant-baseline="central" '
                  f'font-size="{fs:.1f}" fill="#2a251f" font-family="sans-serif">{i["short"]} · {fmt(i["pct"])}%</text>')
    return (f'<svg viewBox="0 0 220 440" style="width:100%;max-width:300px;display:block;margin:auto">'
            f'<defs><clipPath id="clip{slot}"><path d="{body}"/></clipPath></defs>'
            f'<rect x="96" y="40" width="28" height="60" rx="4" fill="#d9d2c6"/>'
            f'<rect x="72" y="22" width="76" height="22" rx="8" fill="#8a8175"/>'
            f'<rect x="144" y="28" width="46" height="10" rx="4" fill="#8a8175"/>'
            f'<rect x="80" y="96" width="60" height="28" rx="6" fill="#8a8175"/>'
            f'<path d="{body}" fill="#f6f3ee"/><g clip-path="url(#clip{slot})">{bands}</g>'
            f'<path d="{body}" fill="none" stroke="{T["bottle_line"]}" stroke-width="2.5"/>'
            f'<path d="M58,160 Q56,260 60,380" stroke="rgba(255,255,255,.55)" stroke-width="6" fill="none" stroke-linecap="round"/>'
            f'</svg>')


def marker(slot, x, y):
    """A is a circle and B a diamond, so the formulas differ by shape as well as colour."""
    ring = f'stroke="{T["surface"]}" stroke-width="2"'
    if slot == "A":
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7" fill="{T["A"]}" {ring}/>'
    return f'<rect x="{x - 6:.1f}" y="{y - 6:.1f}" width="12" height="12" transform="rotate(45 {x:.1f} {y:.1f})" fill="{T["B"]}" {ring}/>'


def sensory_svg(a, b):
    """Paired dots: one row per attribute, A and B on the same 0–10 scale."""
    left, right, row, head = 150, 466, 46, 34
    x_of = lambda n: left + (right - left) * n / 10
    height = head + row * len(SENSES) + 22
    text = lambda x, y, s, fill, size=13, anchor="start", weight=400, family="inherit": (
        f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" text-anchor="{anchor}" '
        f'font-weight="{weight}" font-family="{family}">{s}</text>')
    grid = ""
    for n in (0, 5, 10):
        grid += f'<line x1="{x_of(n)}" x2="{x_of(n)}" y1="{head - 8}" y2="{height - 20}" stroke="{T["line"]}"/>'
        grid += text(x_of(n), height - 5, n, T["muted"], 12, "middle", family=MONO)
    rows = ""
    for n, (key, (label, stage, _)) in enumerate(SENSES.items()):
        y = head + row * n + row / 2 - 4
        va, vb = a["sense"][key], b["sense"][key]
        rows += text(0, y - 3, label, T["ink"], 14, weight=500) + text(0, y + 13, stage, T["muted"], 12)
        if va is not None and vb is not None:
            rows += f'<line x1="{x_of(va):.1f}" x2="{x_of(vb):.1f}" y1="{y}" y2="{y}" stroke="{T["muted"]}" stroke-width="2"/>'
        rows += marker("A", x_of(va), y) if va is not None else ""
        rows += marker("B", x_of(vb), y) if vb is not None else ""
        show = lambda v: "–" if v is None else f"{v:.1f}"
        rows += text(486, y + 5, show(va), T["ink"], 13, family=MONO) + text(530, y + 5, show(vb), T["ink"], 13, family=MONO)
    legend = (marker("A", 8, 12) + text(22, 17, "Formula A", T["ink"], 13)
              + marker("B", 118, 12) + text(132, 17, "Formula B", T["ink"], 13)
              + text(486, 17, "A", T["muted"], 12, family=MONO) + text(530, 17, "B", T["muted"], 12, family=MONO))
    return (f'<svg viewBox="0 0 566 {height}" role="img" aria-label="Predicted sensory profile of formula A and B" '
            f'style="width:100%;display:block">{legend}{grid}{rows}</svg>')


def tag(slot):
    return f'<span class="fx-tag fx-{slot}">{slot}</span>'


def table_html(head, rows):
    """A small comparison table; the first column is text and the rest are numbers."""
    cells = "".join(f"<th>{h}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="fx-table"><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table>'


# ============================================================
# PART E — PAGE LAYOUT
# ============================================================
st.markdown(f"""<style>
.fx-tag {{display:inline-block;min-width:1.5em;padding:0 .4em;border-radius:3px;text-align:center;font-weight:600;color:{T['on_tag']}}}
.fx-A {{background:{T['A']}}}
.fx-B {{background:{T['B']}}}
.fx-table {{width:100%;border-collapse:collapse;font-size:14px}}
.fx-table th {{text-align:right;font-weight:500;color:{T['muted']};border:0;border-bottom:1px solid {T['line']};padding:6px 8px}}
.fx-table td {{text-align:right;border:0;border-bottom:1px solid {T['line']};padding:6px 8px;font-family:{MONO};font-variant-numeric:tabular-nums}}
.fx-table th:first-child, .fx-table td:first-child {{text-align:left;padding-left:0;font-family:inherit}}
.fx-note {{margin:0 0 12px}}
.fx-note small {{color:{T['muted']};display:block}}
button[kind="primary"], button[kind="primary"] p {{color:{T['on_primary']}}}
</style>""", unsafe_allow_html=True)

st.title("🧴 Formulator Builder")
st.caption("Build two O/W emulsions side by side, see their predicted stability risks, and compare how theory "
           "says they differ in structure and on skin.")

if "seeded" not in st.session_state:
    st.session_state.seeded = True
    for slot, (name, ids) in EXAMPLES.items():
        st.session_state[f"{slot}_name"] = name
        st.session_state[f"{slot}_ptype"] = "Leave-on"
        st.session_state[f"{slot}_ph"] = 5.5
        for ing_id in ids:
            st.session_state[sel_key(slot, ing_id)] = True
        suggest(slot)

# ---- Left: ingredient picker (sidebar), one tab per formula ----
with st.sidebar:
    st.header("1 · Choose ingredients")
    search = st.text_input("Search", placeholder="INCI or common name").lower()
    for slot, tab in zip(SLOTS, st.tabs([f"Formula {s}" for s in SLOTS])):
        other = "B" if slot == "A" else "A"
        with tab:
            st.text_input("Formula name", key=f"{slot}_name")
            st.radio("Product type", ["Leave-on", "Rinse-off"], horizontal=True, key=f"{slot}_ptype")
            st.number_input("Target pH", min_value=3.0, max_value=9.0, step=0.1, key=f"{slot}_ph")
            st.button("Suggest starting formula", on_click=suggest, args=(slot,), type="primary",
                      width="stretch", key=f"{slot}_suggest")
            st.button(f"Copy from formula {other}", on_click=copy_formula, args=(other, slot),
                      width="stretch", key=f"{slot}_copy")
            st.button("Clear all", on_click=clear_all, args=(slot,), width="stretch", key=f"{slot}_clear")
            for cat in CATEGORIES:
                group = [i for i in INGREDIENTS if i["cat"] == cat and i["id"] != "aqua"
                         and search in (i["inci"] + i["short"]).lower()]
                if group:
                    st.markdown(f"<span style='color:{CATEGORIES[cat]}'>■</span> **{cat}**", unsafe_allow_html=True)
                    for i in group:
                        st.checkbox(i["inci"], key=sel_key(slot, i["id"]), help=i["func"])

# make sure every ticked ingredient has a starting %
for slot in SLOTS:
    for ing_id in selected_ids(slot)[1:]:
        st.session_state.setdefault(pct_key(slot, ing_id), float(ING[ing_id]["typ"]))

# ---- Top: both formulas, row by row so A and B line up ----
st.subheader("2 · Your formulas")
row_head, row_bottle, row_adjust, row_check = (st.columns(2, gap="large") for _ in range(4))
F = {}
for n, slot in enumerate(SLOTS):
    row_head[n].markdown(f"#### {tag(slot)} {escape(st.session_state[f'{slot}_name'])}", unsafe_allow_html=True)
    with row_adjust[n]:
        for ing_id in selected_ids(slot):
            i = ING[ing_id]
            if ing_id == "aqua":
                continue
            tiny = i["max"] is not None and i["max"] < 0.01
            st.number_input(f"{i['short']}  (usual {fmt(i['min'])}–{fmt(i['max'])}%{' q.s.' if i['qs'] else ''})",
                            min_value=0.0, step=0.0001 if tiny else 0.1, format="%.4f" if tiny else "%.2f",
                            key=pct_key(slot, ing_id))
        items = current_items(slot)
        st.markdown(f"**Water (Aqua): {fmt(items[0]['pct'])}%** — q.s. to 100%")

    ptype, ph = st.session_state[f"{slot}_ptype"], st.session_state[f"{slot}_ph"]
    checks, score = analyse(items, ptype, ph)
    F[slot] = {"slot": slot, "name": st.session_state[f"{slot}_name"], "items": items, "ptype": ptype, "ph": ph,
               "checks": checks, "score": score, "stats": stats(items), "sense": sensory(items)}

    with row_check[n]:
        if score is not None:
            label = "Low predicted risk" if score >= 80 else "Moderate risk" if score >= 55 else "High risk"
            st.metric("Stability score (theory-based, out of 100)", f"{score}", label,
                      delta_color="normal" if score >= 80 else "off" if score >= 55 else "inverse")
        order = {"high": 0, "warn": 1, "info": 2, "ok": 3}
        show = {"high": st.error, "warn": st.warning, "info": st.info, "ok": st.success}
        passed = [c for c in checks if c[0] == "ok"]
        for level, title, detail in sorted([c for c in checks if c[0] != "ok"], key=lambda c: order[c[0]]):
            show[level](f"**{title}** — {detail}")
        if passed:
            with st.expander(f"Passed checks ({len(passed)})"):
                for level, title, detail in passed:
                    st.success(f"**{title}** — {detail}")

    with row_bottle[n]:
        st.markdown(bottle_svg(items, slot), unsafe_allow_html=True)
        used = dict.fromkeys(i["cat"] for i in items)
        st.markdown(" ".join(f"<span style='color:{CATEGORIES[c]}'>■</span> {c}" for c in used), unsafe_allow_html=True)
st.caption("Layer heights follow % w/w. Very small ingredients are enlarged so you can still read them.")

A, B = F["A"], F["B"]
ready = A["sense"] is not None and B["sense"] is not None

# ---- Theory comparison ----
st.divider()
st.subheader("3 · How the formulas differ")
if A["score"] is None or B["score"] is None:
    st.info("Tick ingredients in both formulas to compare them.")
else:
    c1, c2 = st.columns(2, gap="large")
    pct = lambda n: "–" if n is None else f"{fmt(n)}%"
    one = lambda n: "–" if n is None else f"{n:.1f}"
    head = ["", tag("A"), tag("B")]
    metrics = [("Stability score", A["score"], B["score"]),
               ("Water", pct(A["stats"]["water"]), pct(B["stats"]["water"])),
               ("Oil phase", pct(A["stats"]["oil"]), pct(B["stats"]["oil"])),
               ("Fatty alcohol", pct(A["stats"]["fatty"]), pct(B["stats"]["fatty"])),
               ("Emulsifier", pct(A["stats"]["em"]), pct(B["stats"]["em"])),
               ("Emulsifier as % of oil", one(A["stats"]["ratio"]), one(B["stats"]["ratio"])),
               ("Required HLB of oils", one(A["stats"]["r_hlb"]), one(B["stats"]["r_hlb"])),
               ("Emulsifier blend HLB", one(A["stats"]["b_hlb"]), one(B["stats"]["b_hlb"]))]
    c1.markdown("**Structure**")
    c1.markdown(table_html(head, metrics), unsafe_allow_html=True)

    level = {s: {i["id"]: i["pct"] for i in F[s]["items"]} for s in SLOTS}
    rows = []
    for i in INGREDIENTS:
        x, y = level["A"].get(i["id"]), level["B"].get(i["id"])
        if x is None and y is None:
            continue
        delta = (y or 0) - (x or 0)
        rows.append((i["short"], pct(x), pct(y), "0" if abs(delta) < 0.00005 else f"{delta:+.4g}".replace("-", "−")))
    c2.markdown("**Recipe**")
    c2.markdown(table_html(["", tag("A"), tag("B"), "B − A"], rows), unsafe_allow_html=True)

    st.markdown("**What the theory predicts**")
    notes = structure_differences(A, B)
    if not notes:
        st.markdown("The two formulas are structurally very close.")
    for slot, title, detail in notes:
        st.markdown(f'<p class="fx-note">{tag(slot)} <b>{title}</b><small>{escape(detail)}</small></p>', unsafe_allow_html=True)

# ---- Sensory prediction ----
st.divider()
st.subheader("4 · Predicted sensory")
if not ready:
    st.info("Tick ingredients with sensory data in both formulas to see their predicted feel.")
else:
    c1, c2 = st.columns([1.25, 1], gap="large")
    c1.markdown(sensory_svg(A, B), unsafe_allow_html=True)
    with c2:
        forms = " &nbsp; ".join(f"{tag(s)} <b>{product_form(F[s]['sense'])}</b>" for s in SLOTS)
        st.markdown(f'<p class="fx-note">{forms}<small>Likely product form</small></p>', unsafe_allow_html=True)
        feel = feel_differences(A, B)
        if not feel:
            st.markdown("The two formulas should feel very similar: no attribute differs by a full point.")
        for slot, title, detail in feel:
            st.markdown(f'<p class="fx-note">{tag(slot)} <b>{title}</b><small>{escape(detail)}</small></p>', unsafe_allow_html=True)
    for s in SLOTS:
        for flag in sensory_flags(F[s]):
            st.warning(f"**Formula {s}** — {flag}")
        missing = [i["short"] for i in F[s]["items"][1:] if i["body"] is None and i["pct"] > 0]
        if missing:
            st.info(f"**Formula {s}** — {', '.join(missing)} left out of the sensory estimate. "
                    "Add its scores to ingredients.csv from the supplier TDS.")
    with st.expander("How this is estimated"):
        st.markdown(
            "Each ingredient has a 0–5 score per attribute in `ingredients.csv`. A negative score reduces the "
            "attribute, as starch does for greasiness. Score × % adds up across the formula, and the total is "
            "placed on a 0–10 scale that levels off at high use.\n\n"
            "- **Spreadability** is the %-weighted average spread score of the oil phase, reduced in very thick products.\n"
            "- **Absorption speed** falls as greasiness and skin film rise.\n"
            "- **Product form** comes from the Body score.\n\n"
            "The scores are starting estimates from general formulation theory, not panel data. "
            "Edit them in the CSV as you test real batches, and only trust a difference of a point or more.")

# ---- Bottom: ingredient cards ----
st.divider()
st.subheader("5 · Ingredient details & market products")
cols = st.columns(3)
level = {s: {i["id"]: i["pct"] for i in F[s]["items"]} for s in SLOTS}
cards = [i for i in INGREDIENTS if i["id"] in level["A"] or i["id"] in level["B"]]
for n, i in enumerate(cards):
    with cols[n % 3].container(border=True):
        st.markdown(f"<div style='height:6px;background:{CATEGORIES[i['cat']]};border-radius:3px'></div>", unsafe_allow_html=True)
        st.markdown(f"**{i['inci']}**  \n<small>{i['func']}</small>", unsafe_allow_html=True)
        amounts = " · ".join(f"{s} **{fmt(level[s][i['id']])}%**" if i["id"] in level[s] else f"{s} –" for s in SLOTS)
        facts = [f"In these formulas: {amounts}", f"Phase: {i['phase']}",
                 "Usual level: q.s." if i["min"] is None else f"Usual level: {fmt(i['min'])}–{fmt(i['max'])}%"]
        if i["rhlb"] is not None:
            facts.append(f"Required HLB: {fmt(i['rhlb'])}")
        if i["hlb"] is not None:
            facts.append(f"HLB: {fmt(i['hlb'])}")
        if i["charge"] != "none":
            facts.append(f"Charge: {i['charge']}")
        if i["ph_min"] is not None:
            facts.append(f"pH range: {fmt(i['ph_min'])}–{fmt(i['ph_max'])}")
        st.markdown("  \n".join(facts))
        st.caption(i["notes"])
        codes = [c for c in (i["products"] or "").split(";") if c]
        if codes:
            st.markdown("**Found in the market:**  \n" + "  \n".join(
                f"[{PRODUCTS[c]['name']}]({PRODUCTS[c]['url']}) ({PRODUCTS[c]['type']})" for c in codes))
        else:
            st.markdown("_No market product added yet. Add its code to the “products” column._")
        if i["id"] != "aqua":
            st.caption("⚠️ Values are estimates: verify with the supplier TDS")

# ============================================================
# PART F — TRIAL LOG + MACHINE LEARNING
# ============================================================
st.divider()
st.subheader("6 · Trial log — your training data for the ML model")
st.caption("Streamlit Cloud does not keep files between visits, so download the CSV after each session "
           "and upload it again next time.")

FEATURES = [i["inci"] for i in INGREDIENTS]
LOG_COLS = ["date", "name", "product_type", "target_pH", *FEATURES, "predicted_score", "lab_result", "notes"]
if "log" not in st.session_state:
    st.session_state.log = pd.DataFrame(columns=LOG_COLS)

up = st.file_uploader("Load a saved trial log (CSV)", type="csv")
if up is not None and st.session_state.get("loaded_file") != up.name:
    df = pd.read_csv(up)
    for c in LOG_COLS:
        if c not in df.columns:
            df[c] = 0 if c in FEATURES else ""
    st.session_state.log = df[LOG_COLS]
    st.session_state.loaded_file = up.name

c0, c1, c2 = st.columns([1, 1, 2])
save_slot = c0.radio("Formula to save", SLOTS, horizontal=True, format_func=lambda s: f"Formula {s}", key="save_slot")
result = c1.selectbox("Lab result", ["Not tested yet", "Stable (passed)", "Separation / creaming", "Grainy / crystals",
                                     "Viscosity drift", "pH drift", "Microbial fail", "Other"])
notes = c2.text_input("Notes", placeholder="e.g. 4 weeks at 45 °C, slight oil ring")
if st.button("Save formula to log", type="primary"):
    f = F[save_slot]
    row = {"date": str(date.today()), "name": f["name"], "product_type": f["ptype"], "target_pH": f["ph"],
           **{c: 0.0 for c in FEATURES}, "predicted_score": f["score"], "lab_result": result, "notes": notes}
    for i in f["items"]:
        row[i["inci"]] = round(i["pct"], 4)
    st.session_state.log = pd.concat([st.session_state.log, pd.DataFrame([row])], ignore_index=True)

log = st.session_state.log
st.dataframe(log, width="stretch", hide_index=True)
st.download_button("Download trial log (CSV)", log.to_csv(index=False), "formulator_trials.csv", "text/csv")

st.subheader("7 · Machine-learning prediction")
tested = log[log["lab_result"] != "Not tested yet"]
passed = (tested["lab_result"] == "Stable (passed)").astype(int)
if len(tested) < 8 or passed.nunique() < 2:
    st.info(f"The model needs at least 8 lab-tested trials, including both passes and fails. "
            f"You have {len(tested)} tested trial(s) so far. Until then, use the theory-based score above.")
else:
    from sklearn.ensemble import RandomForestClassifier

    X = tested[FEATURES].astype(float)
    model = RandomForestClassifier(n_estimators=200, random_state=0).fit(X, passed)
    for slot, col in zip(SLOTS, st.columns(2)):
        now = pd.DataFrame([{c: 0.0 for c in FEATURES}])
        for i in F[slot]["items"]:
            now.loc[0, i["inci"]] = i["pct"]
        p_pass = model.predict_proba(now[FEATURES])[0][list(model.classes_).index(1)]
        col.metric(f"Formula {slot}: predicted chance of passing stability", f"{p_pass:.0%}")
    st.caption(f"Random forest trained on {len(tested)} of your lab trials. With small data this is a rough "
               "guide; it gets better with every trial you log.")
    imp = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False).head(6)
    imp = imp[imp > 0]
    st.bar_chart(imp, horizontal=True)
    st.caption("Ingredients the model relies on most when predicting a pass or fail.")

st.divider()
st.caption("Prototype for a Temasek Polytechnic project. Use levels, HLB, pH and sensory values are estimates for "
           "learning purposes: check them against supplier technical data sheets. A good score means lower predicted "
           "risk, not guaranteed stability, and predicted feel is no substitute for a sensory panel. Always run "
           "stability tests.")
