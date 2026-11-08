"""Predicted sensory page: how formulas A and B should feel, and why."""
from html import escape

import streamlit as st

from core import SLOTS, build_formulas, feel_differences, product_form, sensory_flags, sensory_svg, tag

st.title("Predicted sensory")
st.caption("How theory says formulas A and B will feel on skin. Build the formulas on the Formulation page.")

F = build_formulas()
A, B = F["A"], F["B"]
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
