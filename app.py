"""
Formulator Builder — Streamlit version
=====================================
Run on your own computer:   streamlit run app.py

This file is the front door: it sets up the page, keeps your formulas while you move
between pages, and shows the menu. Each page is its own file next to this one:
  page_studio.py       the front page: the interactive bottle (the page itself is studio.html)
  page_formulation.py  build formulas A and B side by side (bench.html), stability, predicted feel, compliance
  page_suggest.py      free optimiser: suggests formulas for a goal and your countries
  page_ingredients.py  ingredient library and market products
  page_regulations.py  country guide: rules on your ingredients and materials that need care
  page_trials.py       trial log and machine-learning prediction

Shared code is in core.py, and fx_shared.js for the two interactive pages. The Ask Claude button in the corner
is in part I of core.py, which also says where the API key goes (never in a file on GitHub).
Data lives in CSV files you can open in Excel:
  ingredients.csv  one row per ingredient (add new rows here; "roles" lists the jobs it does, separated by ;)
  products.csv     market products (code, name, type, link)
  regulations.csv  ingredient rules per country (used by the compliance check)
  watchlist.csv    materials that need careful use, per country (Country guide page)
  obligations.csv  what to do before selling in each country
Colours and fonts live in .streamlit/config.toml and TOKENS in core.py.
"""
from pathlib import Path

import streamlit as st
from streamlit import config as _config

# The midnight theme, set here as well as in .streamlit/config.toml, because that hidden folder is easy to miss
# when uploading to GitHub. Colours: midnight black, electric blue, cantaloupe orange.
THEME = {"base": "dark", "backgroundColor": "#02070A", "secondaryBackgroundColor": "#0A1820", "textColor": "#EAF4FA",
         "primaryColor": "#0297DE", "borderColor": "#1B2B36", "linkColor": "#0297DE"}
for _name, _value in THEME.items():
    try:
        _config.set_option(f"theme.{_name}", _value)
    except Exception:  # an older Streamlit that does not know this setting: the stylesheet in core.py still applies
        pass

st.set_page_config(page_title="Formulator Builder", page_icon="🧴", layout="wide")

# Every file the app needs. If one did not get uploaded, say which, instead of crashing.
HERE = Path(__file__).parent
NEEDED = ["core.py", "ingredients.csv", "products.csv", "regulations.csv", "obligations.csv", "watchlist.csv",
          "fx_shared.js", "page_studio.py", "studio.html", "page_formulation.py", "bench.html", "page_suggest.py",
          "page_ingredients.py", "page_regulations.py", "page_trials.py"]
missing = [f for f in NEEDED if not (HERE / f).is_file()]
if missing:
    st.error("These files are missing next to app.py. Upload them and reload.")
    st.code("\n".join(missing))
    st.stop()

from core import (COUNTRIES, EXAMPLES, GOALS, PH_DEFAULT, ROLE_GROUPS, SENSES, claude_corner, inject_css,  # noqa: E402
                  persistent_keys, pool_key, sel_key, suggest)

# Streamlit forgets a widget's value when its page is not on screen. Saving the value
# again on every run keeps formulas A and B intact while you visit other pages.
for key in persistent_keys():
    st.session_state[key] = st.session_state[key]

if "seeded" not in st.session_state:
    st.session_state.seeded = True
    st.session_state["countries"] = [COUNTRIES[0]]
    # starting values of the Suggest page's widgets
    st.session_state.update({"sg_ptype": "Leave-on", "sg_ph": PH_DEFAULT, "sg_goal": next(iter(GOALS)), "sg_count": 3,
                             **{pool_key(role): [i for i in ids if i != "cetstear"] for role, ids in ROLE_GROUPS.items()},
                             **{f"sg_t_{k}": 5 for k in SENSES}})
    for slot, (name, ids) in EXAMPLES.items():
        st.session_state[f"{slot}_name"] = name
        st.session_state[f"{slot}_ptype"] = "Leave-on"
        st.session_state[f"{slot}_ph"] = PH_DEFAULT
        for ing_id in ids:
            st.session_state[sel_key(slot, ing_id)] = True
        suggest(slot)

inject_css()

pages = [
    st.Page(HERE / "page_studio.py", title="Studio", default=True),
    st.Page(HERE / "page_formulation.py", title="Formulation", url_path="formulation"),
    st.Page(HERE / "page_suggest.py", title="Suggest", url_path="suggest"),
    st.Page(HERE / "page_ingredients.py", title="Ingredients", url_path="ingredients"),
    st.Page(HERE / "page_regulations.py", title="Country guide", url_path="guide"),
    st.Page(HERE / "page_trials.py", title="Trial log", url_path="trials"),
]
page = st.navigation(pages, position="top")
if page.title != "Formulation":
    st.session_state["sn_fresh"] = True  # the next visit to the Formulation page compares its feel against that moment
if page.title != "Studio":  # the Studio has its own Ask Claude button, which sees the bottle
    claude_corner()
page.run()
