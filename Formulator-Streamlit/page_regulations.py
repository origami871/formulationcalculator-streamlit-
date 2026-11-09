"""Country guide: what the rules say about your ingredients, and which materials need careful use."""
from html import escape

import streamlit as st

from core import (COUNTRIES, INGREDIENTS, OBLIGATIONS, PHASES, SLOTS, WATCHLIST, build_formulas, phase_of, rule_text, tag)

st.title("Country guide")
st.caption("Pick a country to see how its rules treat the ingredients in this app, and which materials need careful "
           "use there. It is a first screen from the rules on file in regulations.csv and watchlist.csv, not legal advice.")

country = st.selectbox("Country or region", COUNTRIES, key="guide_country")
F = build_formulas()
used_in = lambda ing_id: [s for s in SLOTS if ing_id and any(i["id"] == ing_id and i["pct"] > 0 for i in F[s]["items"])]


def source_line(source, confidence):
    text = f" [Source]({source})" if source else ""
    return text + (" *Confirm against the current official text.*" if confidence == "confirm" else "")


# ---- Materials that need careful use ----
watch = [w for w in WATCHLIST if w["country"] == country]
hits = [(w, used_in(w["ingredient"])) for w in watch if used_in(w["ingredient"])]
if hits:
    st.warning("**In your formulas:** " + "; ".join(f"{w['material']} (formula {', '.join(slots)})" for w, slots in hits)
               + ". See the notes below.")

st.subheader("Materials that need careful use")
for group, meaning in (("Prohibited", "Cannot be used in a cosmetic here."),
                       ("Restricted", "Allowed only within a limit or under a condition."),
                       ("Handle with care", "Allowed, but needs attention when you formulate.")):
    members = [w for w in watch if w["group"] == group]
    if not members:
        continue
    st.markdown(f"**{group}.** {meaning}")
    for w in members:
        tags = " ".join(tag(s) for s in used_in(w["ingredient"]))
        why = f" *Why it needs care:* {w['why']}" if w["why"] else ""
        st.markdown(f"- **{escape(w['material'])}** {tags} — {w['rule']}{why}{source_line(w['source'], w['confidence'])}",
                    unsafe_allow_html=True)
if not watch:
    st.info("No materials are on the watch list for this country yet. Add rows to watchlist.csv.")

# ---- The ingredients this app uses ----
st.subheader("The ingredients in this app")
st.caption("What the rules on file say about each ingredient here. “No rule on file” is not the same as allowed: check the "
           "country's own lists, and add anything you find to regulations.csv.")
rows = []
for i in INGREDIENTS:
    if i["id"] == "aqua":
        continue
    rows.append({"Ingredient": i["short"], "Phase": PHASES[phase_of(i)][0],
                 "Rule on file": rule_text(country, i["id"]) or "No rule on file",
                 "Formula A": "Yes" if "A" in used_in(i["id"]) else "–",
                 "Formula B": "Yes" if "B" in used_in(i["id"]) else "–"})
rows.sort(key=lambda r: r["Rule on file"] == "No rule on file")
st.dataframe(rows, hide_index=True, width="stretch")

# ---- Before selling ----
st.subheader("Before you sell here")
for r in (o for o in OBLIGATIONS if o["country"] == country):
    st.markdown(f"- **{r['item']}.** {r['detail']}{source_line(r['source'], r['confidence'])}")
