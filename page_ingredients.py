"""Ingredient library: one table of everything, and a detail panel for the ingredient you pick."""
import pandas as pd
import streamlit as st

from core import ING, INGREDIENTS, PHASES, PRODUCTS, build_formulas, fmt, phase_of

st.title("Ingredients")
st.caption("Look up any ingredient, see how much of it each formula uses, and find products on the market that contain it.")

F = build_formulas()
amount = {s: {i["id"]: i["pct"] for i in F[s]["items"]} for s in F}
used = lambda i: i["id"] in amount["A"] or i["id"] in amount["B"]

only_used = st.toggle("Only ingredients in formula A or B", value=True, key="only_used")
shown = [i for i in INGREDIENTS if used(i)] if only_used else INGREDIENTS
if not shown:
    st.info("No ingredients are ticked yet. Choose some on the Formulation page, or switch the filter off.")
    st.stop()

table = pd.DataFrame([{
    "Ingredient": i["short"], "Category": i["cat"], "Phase": PHASES[phase_of(i)][0],
    "A (%)": fmt(amount["A"][i["id"]]) if i["id"] in amount["A"] else "–",
    "B (%)": fmt(amount["B"][i["id"]]) if i["id"] in amount["B"] else "–",
    "Usual level": "q.s." if i["min"] is None else f"{fmt(i['min'])}–{fmt(i['max'])}%",
} for i in shown])
st.dataframe(table, hide_index=True, width="stretch")

names = {i["short"]: i["id"] for i in shown}
if st.session_state.get("pick_ing") not in names:
    st.session_state.pop("pick_ing", None)
i = ING[names[st.selectbox("Show details for", list(names), key="pick_ing")]]

left, right = st.columns(2, gap="large")
with left:
    st.markdown(f"#### {i['inci']}")
    st.caption(i["func"])
    facts = [f"Phase: {PHASES[phase_of(i)][0]}",
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
    st.write(i["notes"])
    if i["id"] != "aqua":
        st.caption("Values are estimates: verify with the supplier TDS.")
with right:
    st.markdown("**Found in the market**")
    codes = [c for c in (i["products"] or "").split(";") if c]
    if codes:
        for c in codes:
            st.markdown(f"- [{PRODUCTS[c]['name']}]({PRODUCTS[c]['url']}) ({PRODUCTS[c]['type']})")
    else:
        st.write("No market product added yet. Add its code to the “products” column in ingredients.csv.")
