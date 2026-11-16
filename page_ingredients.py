"""Ingredient library: one table of everything, and a detail panel for the ingredient you pick."""
from html import escape

import streamlit as st

from core import ING, INGREDIENTS, PHASES, PRODUCTS, build_formulas, fmt, page_header, phase_of, roles_of, text_table

page_header("04", "Ingredients", "The ingredient", "library",
            "Look up any ingredient, see how much of it each formula uses, and find products on the market that contain it.")

F = build_formulas()
amount = {s: {i["id"]: i["pct"] for i in F[s]["items"]} for s in F}
used = lambda i: i["id"] in amount["A"] or i["id"] in amount["B"]

c1, c2 = st.columns([1, 2], gap="large")
only_used = c1.toggle("Only ingredients in formula A or B", value=False, key="only_used")
search = c2.text_input("Search", placeholder="Search by name or what it does", label_visibility="collapsed").strip().lower()
shown = [i for i in INGREDIENTS if (used(i) or not only_used)
         and search in " ".join([i["inci"], i["short"], i["func"] or "", *roles_of(i)]).lower()]
if not shown:
    st.info("No ingredient matches. Clear the search, or switch the filter off.")
    st.stop()

usual = lambda i: "q.s." if i["min"] is None else f"{fmt(i['min'])}–{fmt(i['max'])}%"
st.markdown(text_table(
    ["Ingredient", "What it does", "Phase", "A (%)", "B (%)", "Usual level"],
    [[escape(i["short"]), escape(", ".join(roles_of(i))), PHASES[phase_of(i)][0],
      fmt(amount["A"][i["id"]]) if i["id"] in amount["A"] else "–",
      fmt(amount["B"][i["id"]]) if i["id"] in amount["B"] else "–", usual(i)] for i in shown]), unsafe_allow_html=True)
st.write("")

names = {i["short"]: i["id"] for i in shown}
if st.session_state.get("pick_ing") not in names:
    st.session_state.pop("pick_ing", None)
i = ING[names[st.selectbox("Show details for", list(names), key="pick_ing")]]

left, right = st.columns(2, gap="large")
with left:
    st.markdown(f"#### {i['inci']}")
    st.caption(i["func"])
    facts = [f"Phase: {PHASES[phase_of(i)][0]}", f"Usual level: {usual(i)}"]
    if i["rhlb"] is not None:
        facts.append(f"Required HLB: {fmt(i['rhlb'])}")
    if i["hlb"] is not None:
        facts.append(f"HLB: {fmt(i['hlb'])}")
    if i["charge"] and i["charge"] != "none":
        facts.append(f"Charge: {i['charge']}")
    if i["ph_min"] is not None:
        facts.append(f"pH range: {fmt(i['ph_min'])}–{fmt(i['ph_max'])}")
    st.markdown("  \n".join(facts))
    st.write(i["notes"] or "")
    if i["id"] != "aqua":
        st.caption("Values are estimates: verify with the supplier TDS.")
with right:
    st.markdown("**Found in the market**")
    codes = [c for c in (i["products"] or "").split(";") if c in PRODUCTS]
    if codes:
        for c in codes:
            st.markdown(f"- [{PRODUCTS[c]['name']}]({PRODUCTS[c]['url']}) ({PRODUCTS[c]['type']})")
    else:
        st.write("No market product added yet. Add its code to the “products” column in ingredients.csv.")
