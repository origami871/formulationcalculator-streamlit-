"""Formulation page: build formulas A and B side by side, then read their predicted feel and check each country's rules.

The top of the page is bench.html: the ingredient library and the two formulas, with drag and drop, sliders,
the bottles and the stability checks. It sends the formulas here a moment after every change (through a hidden
text box, as the Studio does), and the two sections below it are worked out from them in Python.
"""
from html import escape

import streamlit as st
import streamlit.components.v1 as components

from core import (COUNTRIES, OBLIGATIONS, SLOTS, amount_changes, build_formulas, compliance, feel_differences,
                  formula_state, inbox_event, interactive_page, outbox, page_header, pill, product_form,
                  section_header, sense_changes, sensory_flags, sensory_svg, set_formula, table_html, tag)

page_header("02", "Formulation", "Two formulas,", "side by side",
            "Choose ingredients from the library and build two O/W emulsions side by side. Their bottles and stability "
            "checks update as you work, and their predicted feel and each country's rules follow below.")

# ---- The workbench (bench.html) ----
event = inbox_event("bench_inbox")
if event and event.get("type") == "formulas":
    for slot in SLOTS:
        f = (event.get("formulas") or {}).get(slot)
        if isinstance(f, dict):
            set_formula(slot, f.get("amounts"), f.get("name"), f.get("ptype"), f.get("ph"))

st.markdown("""<style>
.st-key-bench_inbox,[data-testid="stTextInput"]:has(input[aria-label="bench-inbox"]){display:none}
[data-testid="stMain"] iframe{border:0;display:block;width:100%}
</style>""", unsafe_allow_html=True)
st.text_input("bench-inbox", key="bench_inbox", label_visibility="collapsed")
outbox("fx-bench-outbox", {"formulas": {slot: formula_state(slot) for slot in SLOTS}})
components.html(interactive_page("bench.html"), height=1500, scrolling=False)

F = build_formulas()
A, B = F["A"], F["B"]

# ---- Predicted feel ----
section_header("03", "Predicted feel", "How they", "feel",
               "How theory says each formula will feel on skin. It follows the ingredients and amounts you set above.")

# The formulas as they were when this page was opened, so the changes made since can be listed.
now = {s: {"amounts": {i["id"]: i["pct"] for i in F[s]["items"][1:] if i["pct"] > 0}, "sense": F[s]["sense"]} for s in SLOTS}
if st.session_state.get("sn_fresh", True) or "sn_baseline" not in st.session_state:
    st.session_state["sn_baseline"] = now
    st.session_state["sn_fresh"] = False
baseline = st.session_state["sn_baseline"]

if A["sense"] is None or B["sense"] is None:
    st.info("Add ingredients with sensory data to both formulas to compare their predicted feel.")
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

with st.expander("What your changes did", expanded=any(amount_changes(baseline[s]["amounts"], now[s]["amounts"]) for s in SLOTS)):
    st.caption("Compared with the formulas as they were when you opened this page.")
    for slot, col in zip(SLOTS, st.columns(2, gap="large")):
        recipe = amount_changes(baseline[slot]["amounts"], now[slot]["amounts"])
        feel_moves = sense_changes(baseline[slot]["sense"], now[slot]["sense"])
        col.markdown(f"{tag(slot)} **{escape(F[slot]['name'])}**", unsafe_allow_html=True)
        if not recipe and not feel_moves:
            col.write("No changes yet.")
            continue
        if recipe:
            col.markdown("**Recipe**\n" + "\n".join(f"- {x}" for x in recipe))
        if feel_moves:
            col.markdown("**Predicted feel**\n" + "\n".join(f"- {x}" for x in feel_moves))
    if st.button("Compare from now on", key="btn_sn_reset"):
        st.session_state["sn_baseline"] = now
        st.rerun()

with st.expander("How the feel is estimated"):
    st.markdown(
        "Each ingredient has a 0–5 score per attribute in `ingredients.csv`. A negative score reduces the "
        "attribute, as starch does for greasiness. Score × % adds up across the formula, and the total is "
        "placed on a 0–10 scale that levels off at high use.\n\n"
        "- **Spreadability** is the %-weighted average spread score of the oil phase, reduced in very thick products.\n"
        "- **Absorption speed** falls as greasiness and skin film rise.\n"
        "- **Product form** comes from the Body score.\n\n"
        "The scores are starting estimates from general formulation theory, not panel data. "
        "Edit them in the CSV as you test real batches, and only trust a difference of a point or more.")

# ---- Compliance ----
section_header("04", "Compliance", "Where can you", "sell it?",
               "Checks each formula against the ingredient rules on file for the countries you plan to sell in "
               "(regulations.csv). It covers only the ingredients and rules in that file, so it is a first screen "
               "and not legal advice.")
countries = st.multiselect("Selling in", COUNTRIES, key="countries")
if not countries:
    st.info("Choose at least one country to check.")
else:
    results = {c: {s: compliance(F[s]["items"], F[s]["ptype"], F[s]["ph"], c) for s in SLOTS} for c in countries}
    st.markdown(table_html(["Country", tag("A"), tag("B")],
                           [[c, *[pill(results[c][s][0]) for s in SLOTS]] for c in countries]), unsafe_allow_html=True)
    st.write("")
    for country in countries:
        failing = any(results[country][s][0] == "fail" for s in SLOTS)
        with st.expander(f"{country}: details and what to do before selling", expanded=failing):
            for slot, col in zip(SLOTS, st.columns(2, gap="large")):
                overall, rows = results[country][slot]
                col.markdown(f"{tag(slot)} {pill(overall)}", unsafe_allow_html=True)
                order = {"high": 0, "warn": 1, "info": 2, "ok": 3}
                show = {"high": col.error, "warn": col.warning, "info": col.info, "ok": col.success}
                for level, title, detail, source, confidence in sorted(rows, key=lambda r: order[r[0]]):
                    text = f"**{title}** — {detail}"
                    if source:
                        text += f" [Source]({source})"
                    if confidence == "confirm":
                        text += " *Confirm against the current official text.*"
                    show[level](text)
            st.markdown("**Before you sell in this country**")
            for r in (o for o in OBLIGATIONS if o["country"] == country):
                line = f"- **{r['item']}.** {r['detail']}"
                if r["source"]:
                    line += f" [Source]({r['source']})"
                if r["confidence"] == "confirm":
                    line += " *Confirm on the official site.*"
                st.markdown(line)
