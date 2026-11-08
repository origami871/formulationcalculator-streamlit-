"""
Formulator Builder — Streamlit version
=====================================
Run on your own computer:   streamlit run app.py

This file is the front door: it sets up the page, keeps your formulas while you move
between pages, and shows the menu. Each page is its own file in views/:
  views/formulation.py  the main page: build formulas A and B, stability, compliance
  views/sensory.py      predicted feel of A and B
  views/ingredients.py  ingredient library and market products
  views/trials.py       trial log and machine-learning prediction

Shared code is in core.py. Data lives in CSV files you can open in Excel:
  ingredients.csv  one row per ingredient (add new rows here)
  products.csv     market products (code, name, type, link)
  regulations.csv  ingredient rules per country
  obligations.csv  what to do before selling in each country
Colours and fonts live in .streamlit/config.toml and TOKENS in core.py.
"""
import streamlit as st

from core import COUNTRIES, EXAMPLES, inject_css, persistent_keys, sel_key, suggest

st.set_page_config(page_title="Formulator Builder", page_icon="🧴", layout="wide")

# Streamlit forgets a widget's value when its page is not on screen. Saving the value
# again on every run keeps formulas A and B intact while you visit other pages.
for key in persistent_keys():
    st.session_state[key] = st.session_state[key]

if "seeded" not in st.session_state:
    st.session_state.seeded = True
    st.session_state["countries"] = [COUNTRIES[0]]
    for slot, (name, ids) in EXAMPLES.items():
        st.session_state[f"{slot}_name"] = name
        st.session_state[f"{slot}_ptype"] = "Leave-on"
        st.session_state[f"{slot}_ph"] = 5.5
        for ing_id in ids:
            st.session_state[sel_key(slot, ing_id)] = True
        suggest(slot)

inject_css()

pages = [
    st.Page("views/formulation.py", title="Formulation", default=True),
    st.Page("views/sensory.py", title="Sensory"),
    st.Page("views/ingredients.py", title="Ingredients"),
    st.Page("views/trials.py", title="Trial log"),
]
st.navigation(pages, position="top").run()
