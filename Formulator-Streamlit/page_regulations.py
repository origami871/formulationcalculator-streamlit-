"""Country guide: what the rules say about your ingredients, and which materials need careful use."""
from html import escape

import streamlit as st

from core import (COUNTRIES, INGREDIENTS, OBLIGATIONS, PHASES, SLOTS, WATCHLIST, build_formulas, page_header, phase_of,
                  rule_text, section_header, tag, text_table)

page_header("05", "Country guide", "Rules,", "country by country",
            "Pick a country to see how its rules treat the ingredients in this app, and which materials need careful "
            "use there. It is a first screen from the rules on file in regulations.csv and watchlist.csv, not legal advice.")

if not COUNTRIES:
    st.info("No countries are on file yet. Add rows to obligations.csv.")
    st.stop()
if st.session_state.get("guide_country") not in COUNTRIES:  # the country list may have changed since this was saved
    st.session_state.pop("guide_country", None)
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

section_header("", "Watch list", "Materials that need", "care")
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
        st.markdown(f"- **{escape(str(w['material'] or 'Unnamed material'))}** {tags} — {w['rule'] or ''}{why}"
                    f"{source_line(w['source'], w['confidence'])}", unsafe_allow_html=True)
if not watch:
    st.info("No materials are on the watch list for this country yet. Add rows to watchlist.csv.")

# ---- The ingredients this app uses ----
section_header("", "Your library", "The ingredients", "in this app",
               "What the rules on file say about each ingredient here. “No rule on file” is not the same as allowed: "
               "check the country's own lists, and add anything you find to regulations.csv.")
rows = []
for i in INGREDIENTS:
    if i["id"] == "aqua":
        continue
    slots = used_in(i["id"])
    rows.append([escape(i["short"]), PHASES[phase_of(i)][0], escape(rule_text(country, i["id"]) or "No rule on file"),
                 " ".join(tag(s) for s in slots) or "–"])
rows.sort(key=lambda r: r[2] == "No rule on file")
st.markdown(text_table(["Ingredient", "Phase", "Rule on file", "In your formulas"], rows), unsafe_allow_html=True)

# ---- Before selling ----
section_header("", "Checklist", "Before you", "sell here")
duties = [o for o in OBLIGATIONS if o["country"] == country]
for r in duties:
    st.markdown(f"- **{r['item']}.** {r['detail']}{source_line(r['source'], r['confidence'])}")
if not duties:
    st.info("No steps are on file for this country yet. Add rows to obligations.csv.")
