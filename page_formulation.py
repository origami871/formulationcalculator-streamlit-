"""Main page: build formulas A and B, read their stability, and check them against each country's rules."""
from html import escape

import streamlit as st

from core import (CATEGORIES, COUNTRIES, ING, INGREDIENTS, OBLIGATIONS, PHASES, SLOTS, bottle_html, build_formulas,
                  clear_all, compliance, copy_formula, fmt, pct_key, phase_of, pill, sel_key, selected_ids,
                  suggest_clicked, table_html, tag)

st.title("Formulator Builder")
st.caption("Build two O/W emulsions side by side, see their predicted stability risks, and check them against "
           "the rules of the countries you plan to sell in.")

# ---- Sidebar: ingredient picker, one tab per formula ----
with st.sidebar:
    st.header("Choose ingredients")
    search = st.text_input("Search", placeholder="INCI or common name").lower()
    for slot, tab in zip(SLOTS, st.tabs([f"Formula {s}" for s in SLOTS])):
        other = "B" if slot == "A" else "A"
        with tab:
            st.text_input("Formula name", key=f"{slot}_name")
            st.radio("Product type", ["Leave-on", "Rinse-off"], horizontal=True, key=f"{slot}_ptype")
            st.number_input("Target pH", min_value=3.0, max_value=9.0, step=0.1, key=f"{slot}_ph")
            st.button("Suggest starting formula", on_click=suggest_clicked, args=(slot,), type="primary",
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

# ---- Both formulas, row by row so A and B line up ----
F = build_formulas()
row_head, row_bottle, row_adjust, row_check = (st.columns(2, gap="large") for _ in range(4))
for n, slot in enumerate(SLOTS):
    f = F[slot]
    row_head[n].markdown(f"#### {tag(slot)} {escape(f['name'])}", unsafe_allow_html=True)
    row_bottle[n].markdown(bottle_html(f["items"], slot), unsafe_allow_html=True)

    with row_adjust[n]:
        st.markdown("**Amounts (% w/w)**")
        chosen = [ING[i] for i in selected_ids(slot) if i != "aqua"]
        for phase, (label, letter) in PHASES.items():
            members = [i for i in chosen if phase_of(i) == phase]
            if phase == "water":
                st.caption(f"{label} ({letter})")
                st.markdown(f"Water (Aqua): **{fmt(f['items'][0]['pct'])}%** (q.s. to 100%)")
            elif members:
                st.caption(f"{label} ({letter})")
            for i in members:
                tiny = i["max"] is not None and i["max"] < 0.01
                st.number_input(f"{i['short']}  (usual {fmt(i['min'])}–{fmt(i['max'])}%{' q.s.' if i['qs'] else ''})",
                                min_value=0.0, step=0.0001 if tiny else 0.1, format="%.4f" if tiny else "%.2f",
                                key=pct_key(slot, i["id"]))

    with row_check[n]:
        st.markdown("**Stability**")
        if f["score"] is not None:
            label = "Low predicted risk" if f["score"] >= 80 else "Moderate risk" if f["score"] >= 55 else "High risk"
            st.metric("Stability score (theory-based, out of 100)", f"{f['score']}", label,
                      delta_color="normal" if f["score"] >= 80 else "off" if f["score"] >= 55 else "inverse")
        order = {"high": 0, "warn": 1, "info": 2, "ok": 3}
        show = {"high": st.error, "warn": st.warning, "info": st.info, "ok": st.success}
        passed = [c for c in f["checks"] if c[0] == "ok"]
        for level, title, detail in sorted([c for c in f["checks"] if c[0] != "ok"], key=lambda c: order[c[0]]):
            show[level](f"**{title}** — {detail}")
        if passed:
            with st.expander(f"Passed checks ({len(passed)})"):
                for level, title, detail in passed:
                    st.success(f"**{title}** — {detail}")

# ---- Compliance ----
st.divider()
st.subheader("Compliance")
st.caption("Checks each formula against the ingredient rules on file for the countries you plan to sell in "
           "(regulations.csv). It covers only the ingredients and rules in that file, so it is a first screen and "
           "not legal advice.")
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
            for n, (slot, col) in enumerate(zip(SLOTS, st.columns(2, gap="large"))):
                overall, rows = results[country][slot]
                col.markdown(f"{tag(slot)} {pill(overall)}", unsafe_allow_html=True)
                order = {"high": 0, "info": 1, "ok": 2}
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
