"""
Formulator Builder — Streamlit version
=====================================
Run on your own computer:   streamlit run app.py
Data lives in two CSV files you can open in Excel:
  ingredients.csv  -> one row per ingredient (add new rows here)
  products.csv     -> market products (code, name, type, link)

The file is split into parts:
  PART A  load the data
  PART B  the "theory" (rule-based stability check + suggested formula)
  PART C  drawing the bottle
  PART D  the page layout
  PART E  trial log + machine-learning prediction
"""
from datetime import date
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


def pct_key(ing_id):
    return f"pct_{ing_id}"


def selected_ids():
    """Ingredients that are ticked in the sidebar (water is always included)."""
    return ["aqua"] + [i["id"] for i in INGREDIENTS
                       if i["id"] != "aqua" and st.session_state.get(f"sel_{i['id']}", False)]


def current_items():
    """List of the selected ingredients with their % (water = q.s. to 100)."""
    items = []
    for ing_id in selected_ids():
        if ing_id == "aqua":
            continue
        items.append({**ING[ing_id], "pct": float(st.session_state.get(pct_key(ing_id), ING[ing_id]["typ"]) or 0)})
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


def suggest():
    """Theory-based first draft: typical levels, emulsifier ≈ 22% of oil phase, HLB-matched split."""
    ids = [i for i in selected_ids() if i != "aqua"]
    for i in ids:
        st.session_state[pct_key(i)] = float(ING[i]["typ"])
    oil_ids = [i for i in ids if ING[i]["phase"] == "Oil" and ING[i]["cat"] != "Emulsifier"]
    em_ids = [i for i in ids if ING[i]["cat"] == "Emulsifier"]
    oil_total = sum(st.session_state[pct_key(i)] for i in oil_ids)
    if not em_ids or oil_total == 0:
        return
    em_target = 0.22 * oil_total
    known = [i for i in oil_ids if ING[i]["rhlb"] is not None]
    r_hlb = (sum(ING[i]["rhlb"] * st.session_state[pct_key(i)] for i in known)
             / sum(st.session_state[pct_key(i)] for i in known)) if known else 10
    shares = {i: 1 / len(em_ids) for i in em_ids}
    if len(em_ids) == 2:
        a, b = ING[em_ids[0]], ING[em_ids[1]]
        if a["hlb"] != b["hlb"]:
            x = min(0.7, max(0.3, (r_hlb - b["hlb"]) / (a["hlb"] - b["hlb"])))
            shares = {a["id"]: x, b["id"]: 1 - x}
    for i in em_ids:
        e = ING[i]
        st.session_state[pct_key(i)] = round(min(e["max"], max(e["min"], shares[i] * em_target)), 1)


def clear_all():
    for i in INGREDIENTS:
        st.session_state[f"sel_{i['id']}"] = False


# ============================================================
# PART C — DRAW THE BOTTLE (SVG picture)
# ============================================================
def bottle_svg(items):
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
    return (f'<svg viewBox="0 0 220 440" style="width:100%;max-width:340px;display:block;margin:auto">'
            f'<defs><clipPath id="clip"><path d="{body}"/></clipPath></defs>'
            f'<rect x="96" y="40" width="28" height="60" rx="4" fill="#d9d2c6"/>'
            f'<rect x="72" y="22" width="76" height="22" rx="8" fill="#8a8175"/>'
            f'<rect x="144" y="28" width="46" height="10" rx="4" fill="#8a8175"/>'
            f'<rect x="80" y="96" width="60" height="28" rx="6" fill="#8a8175"/>'
            f'<path d="{body}" fill="#f6f3ee"/><g clip-path="url(#clip)">{bands}</g>'
            f'<path d="{body}" fill="none" stroke="#3a352e" stroke-width="2.5"/>'
            f'<path d="M58,160 Q56,260 60,380" stroke="rgba(255,255,255,.55)" stroke-width="6" fill="none" stroke-linecap="round"/>'
            f'</svg>')


# ============================================================
# PART D — PAGE LAYOUT
# ============================================================
st.title("🧴 Formulator Builder")
st.caption("Pick your ingredients, get a theory-based starting formula for an O/W emulsion, "
           "see the predicted stability risks, and compare with products already on the market.")

# ---- Left: ingredient picker (sidebar) ----
with st.sidebar:
    st.header("1 · Choose ingredients")
    fname = st.text_input("Formula name", "Body lotion trial 1")
    ptype = st.radio("Product type", ["Leave-on", "Rinse-off"], horizontal=True)
    ph = st.number_input("Target pH", min_value=3.0, max_value=9.0, value=5.5, step=0.1)
    st.button("Suggest starting formula", on_click=suggest, type="primary", use_container_width=True)
    st.button("Clear all", on_click=clear_all, use_container_width=True)
    search = st.text_input("Search", placeholder="INCI or common name").lower()
    for cat in CATEGORIES:
        group = [i for i in INGREDIENTS if i["cat"] == cat and i["id"] != "aqua"
                 and search in (i["inci"] + i["short"]).lower()]
        if group:
            st.markdown(f"<span style='color:{CATEGORIES[cat]}'>■</span> **{cat}**", unsafe_allow_html=True)
            for i in group:
                st.checkbox(i["inci"], key=f"sel_{i['id']}", help=i["func"])

# make sure every ticked ingredient has a starting %
for ing_id in selected_ids()[1:]:
    st.session_state.setdefault(pct_key(ing_id), float(ING[ing_id]["typ"]))

col_bottle, col_adjust = st.columns([1, 1.2], gap="large")

# ---- Right: adjust % and stability check ----
with col_adjust:
    st.subheader("3 · Adjust % and check stability")
    for ing_id in selected_ids():
        i = ING[ing_id]
        if ing_id == "aqua":
            continue
        tiny = i["max"] is not None and i["max"] < 0.01
        st.number_input(f"{i['short']}  (usual {fmt(i['min'])}–{fmt(i['max'])}%{' q.s.' if i['qs'] else ''})",
                        min_value=0.0, step=0.0001 if tiny else 0.1, format="%.4f" if tiny else "%.2f",
                        key=pct_key(ing_id))
    items = current_items()
    st.markdown(f"**Water (Aqua): {fmt(items[0]['pct'])}%** — q.s. to 100%")

    checks, score = analyse(items, ptype, ph)
    if score is not None:
        label = "Low predicted risk" if score >= 80 else "Moderate risk" if score >= 55 else "High risk"
        st.metric("Stability score (theory-based, out of 100)", f"{score}", label,
                  delta_color="normal" if score >= 80 else "off" if score >= 55 else "inverse")
    order = {"high": 0, "warn": 1, "info": 2, "ok": 3}
    show = {"high": st.error, "warn": st.warning, "info": st.info, "ok": st.success}
    for level, title, detail in sorted(checks, key=lambda c: order[c[0]]):
        show[level](f"**{title}** — {detail}")

# ---- Centre: the bottle ----
with col_bottle:
    st.subheader("2 · Your formulation")
    st.markdown(bottle_svg(items), unsafe_allow_html=True)
    used = dict.fromkeys(i["cat"] for i in items)
    st.markdown(" ".join(f"<span style='color:{CATEGORIES[c]}'>■</span> {c}" for c in used), unsafe_allow_html=True)
    st.caption("Layer heights follow % w/w. Very small ingredients are enlarged so you can still read them.")

# ---- Bottom: ingredient cards ----
st.divider()
st.subheader("4 · Ingredient details & market products")
cols = st.columns(3)
for n, i in enumerate(items):
    with cols[n % 3].container(border=True):
        st.markdown(f"<div style='height:6px;background:{CATEGORIES[i['cat']]};border-radius:3px'></div>", unsafe_allow_html=True)
        st.markdown(f"**{i['inci']}**  \n<small>{i['func']}</small>", unsafe_allow_html=True)
        facts = [f"In this formula: **{fmt(i['pct'])}%**", f"Phase: {i['phase']}",
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
# PART E — TRIAL LOG + MACHINE LEARNING
# ============================================================
st.divider()
st.subheader("5 · Trial log — your training data for the ML model")
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

c1, c2 = st.columns([1, 2])
result = c1.selectbox("Lab result", ["Not tested yet", "Stable (passed)", "Separation / creaming", "Grainy / crystals",
                                     "Viscosity drift", "pH drift", "Microbial fail", "Other"])
notes = c2.text_input("Notes", placeholder="e.g. 4 weeks at 45 °C, slight oil ring")
if st.button("Save formula to log", type="primary"):
    row = {"date": str(date.today()), "name": fname, "product_type": ptype, "target_pH": ph,
           **{f: 0.0 for f in FEATURES}, "predicted_score": score, "lab_result": result, "notes": notes}
    for i in items:
        row[i["inci"]] = round(i["pct"], 4)
    st.session_state.log = pd.concat([st.session_state.log, pd.DataFrame([row])], ignore_index=True)

log = st.session_state.log
st.dataframe(log, use_container_width=True, hide_index=True)
st.download_button("Download trial log (CSV)", log.to_csv(index=False), "formulator_trials.csv", "text/csv")

st.subheader("6 · Machine-learning prediction")
tested = log[log["lab_result"] != "Not tested yet"]
passed = (tested["lab_result"] == "Stable (passed)").astype(int)
if len(tested) < 8 or passed.nunique() < 2:
    st.info(f"The model needs at least 8 lab-tested trials, including both passes and fails. "
            f"You have {len(tested)} tested trial(s) so far. Until then, use the theory-based score above.")
else:
    from sklearn.ensemble import RandomForestClassifier

    X = tested[FEATURES].astype(float)
    model = RandomForestClassifier(n_estimators=200, random_state=0).fit(X, passed)
    now = pd.DataFrame([{f: 0.0 for f in FEATURES}])
    for i in items:
        now.loc[0, i["inci"]] = i["pct"]
    p_pass = model.predict_proba(now[FEATURES])[0][list(model.classes_).index(1)]
    st.metric("Predicted chance of passing stability", f"{p_pass:.0%}")
    st.caption(f"Random forest trained on {len(tested)} of your lab trials. With small data this is a rough "
               "guide; it gets better with every trial you log.")
    imp = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False).head(6)
    imp = imp[imp > 0]
    st.bar_chart(imp, horizontal=True)
    st.caption("Ingredients the model relies on most when predicting a pass or fail.")

st.divider()
st.caption("Prototype for a Temasek Polytechnic project. Use levels, HLB and pH values are estimates for learning "
           "purposes: check them against supplier technical data sheets. A good score means lower predicted risk, "
           "not guaranteed stability; always run stability tests.")
