"""
Formulator Builder — Streamlit version
=====================================
Run on your own computer:   streamlit run app.py

This file is the front door: it sets up the page, keeps your formulas while you move
between pages, and shows the menu. Each page is its own file next to this one:
  page_formulation.py  the main page: build formulas A and B, stability, compliance
  page_sensory.py      predicted feel of A and B
  page_ingredients.py  ingredient library and market products
  page_trials.py       trial log and machine-learning prediction

Shared code is in core.py. Data lives in CSV files you can open in Excel:
  ingredients.csv  one row per ingredient (add new rows here)
  products.csv     market products (code, name, type, link)
  regulations.csv  ingredient rules per country
  obligations.csv  what to do before selling in each country
Colours and fonts live in .streamlit/config.toml and TOKENS in core.py.
"""
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Formulator Builder", page_icon="🧴", layout="wide")

# Every file the app needs. If one did not get uploaded, say which, instead of crashing.
HERE = Path(__file__).parent
NEEDED = ["core.py", "ingredients.csv", "products.csv", "regulations.csv", "obligations.csv",
          "page_formulation.py", "page_sensory.py", "page_ingredients.py", "page_trials.py"]
missing = [f for f in NEEDED if not (HERE / f).is_file()]
if missing:
    st.error("These files are missing next to app.py. Upload them and reload.")
    st.code("\n".join(missing))
    st.stop()

from core import COUNTRIES, EXAMPLES, inject_css, persistent_keys, sel_key, suggest  # noqa: E402

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
    st.Page(HERE / "page_formulation.py", title="Formulation", default=True),
    st.Page(HERE / "page_sensory.py", title="Sensory"),
    st.Page(HERE / "page_ingredients.py", title="Ingredients"),
    st.Page(HERE / "page_trials.py", title="Trial log"),
]
st.navigation(pages, position="top").run()
