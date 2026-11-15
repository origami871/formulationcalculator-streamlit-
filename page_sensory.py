"""Predicted sensory page: how formulas A and B should feel, and why."""
from html import escape

import streamlit as st

from core import (SLOTS, amount_changes, build_formulas, feel_differences, product_form, recipe_rows, sense_changes,
                  sensory_flags, sensory_svg, table_html, tag)

st.title("Predicted sensory")
st.caption("How theory says formulas A and B will feel on skin. It updates from the amounts and ingredients you set on "
           "the Formulation page.")

F = build_formulas()
A, B = F["A"], F["B"]

# Remember the formulas at each visit, so the next visit can show what the changes did to the feel.
now = {s: {"amounts": {i["id"]: i["pct"] for i in F[s]["items"][1:] if i["pct"] > 0}, "sense": F[s]["sense"]} for s in SLOTS}
if st.session_state.get("sn_fresh", True):  # first run of a new visit to this page
    st.session_state["sn_baseline"] = st.session_state.get("sn_last")
    st.session_state["sn_last"] = now
    st.session_state["sn_fresh"] = False  # reruns during this visit keep the same comparison
baseline = st.session_state.get("sn_baseline")

if A["sense"] is None or B["sense"] is None:
    st.info("Tick ingredients with sensory data in both formulas on the Formulation page to see their predicted feel.")
    st.stop()

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

st.subheader("What changed since your last visit")
if baseline is None:
    st.caption("Change an amount or an ingredient on the Formulation page, then come back here to see how it moves the feel.")
else:
    for slot, col in zip(SLOTS, st.columns(2, gap="large")):
        recipe = amount_changes(baseline[slot]["amounts"], now[slot]["amounts"])
        feel_moves = sense_changes(baseline[slot]["sense"], now[slot]["sense"])
        col.markdown(f"{tag(slot)} **{escape(F[slot]['name'])}**", unsafe_allow_html=True)
        if not recipe and not feel_moves:
            col.write("No changes.")
            continue
        if recipe:
            col.markdown("**Recipe**\n" + "\n".join(f"- {x}" for x in recipe))
        if feel_moves:
            col.markdown("**Predicted feel**\n" + "\n".join(f"- {x}" for x in feel_moves))

for s in SLOTS:
    for flag in sensory_flags(F[s]):
        st.warning(f"**Formula {s}** — {flag}")
    missing = [i["short"] for i in F[s]["items"][1:] if i["body"] is None and i["pct"] > 0]
    if missing:
        st.info(f"**Formula {s}** — {', '.join(missing)} left out of the sensory estimate. "
                "Add its scores to ingredients.csv from the supplier TDS.")

with st.expander("Recipes behind this chart"):
    for slot, col in zip(SLOTS, st.columns(2, gap="large")):
        col.markdown(f"{tag(slot)} **{escape(F[slot]['name'])}**", unsafe_allow_html=True)
        col.markdown(table_html(["", "%"], recipe_rows(F[slot]["items"])), unsafe_allow_html=True)

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
