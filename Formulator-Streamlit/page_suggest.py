"""Suggest page: a free optimiser that searches for formulas that meet a sensory goal and the rules of your countries."""
import streamlit as st

from core import (COUNTRIES, GOALS, ING, ROLE_GROUPS, SENSES, SLOTS, eligible, has_core, load_suggestion, optimise,
                  page_header, ph_text, pill, pool_key, product_form, recipe_rows, roles_of, section_header, table_html)

page_header("03", "Suggest", "Find a", "starting point",
            "Finds starting formulas from the ingredients you allow. It tries thousands of combinations, scores each "
            "with the stability, compliance and sensory theory used on the Formulation page, and shows the best ones. "
            "It runs inside this app, so there is no account and no cost.")

c1, c2, c3 = st.columns([1, 1.3, 2], gap="large")
ptype = c1.radio("Product type", ["Leave-on", "Rinse-off"], horizontal=True, key="sg_ptype")
ph = c2.slider("Target pH range", min_value=3.0, max_value=9.0, step=0.1, key="sg_ph",
               help="The finished product may land anywhere in this range, so every ingredient should work across it.")
countries = c3.multiselect("Selling in (suggestions must pass these rules)", COUNTRIES, key="countries")

g1, g2 = st.columns([2.3, 2], gap="large")
goal = g1.selectbox("Feel you want", [*GOALS, "Custom"], key="sg_goal")
count = g2.slider("How many suggestions to show", min_value=1, max_value=6, key="sg_count")
if goal == "Custom":
    cols = st.columns(len(SENSES))
    target = {k: cols[n].slider(label.split(",")[0], 0, 10, key=f"sg_t_{k}") for n, (k, (label, _, _)) in enumerate(SENSES.items())}
else:
    target = GOALS[goal]

# ---- Ingredients it may use, grouped by the job they do ----
section_header("", "Ingredients it may use", "Pick the", "palette",
               "Grouped by the main job each ingredient does. A second job is shown after the name. "
               "Press an ingredient to allow it or leave it out.")


def label(ing_id):
    also = roles_of(ING[ing_id])[1:]
    return ING[ing_id]["short"] + (f" (+ {', '.join(also).lower()})" if also else "")


pool = []
cols = st.columns(2, gap="large")
for n, (role, ids) in enumerate(ROLE_GROUPS.items()):
    key = pool_key(role)
    if key in st.session_state:  # ingredients.csv may have changed since this was saved
        st.session_state[key] = [i for i in st.session_state[key] if i in ids]
    pool += cols[n % 2].pills(role, ids, selection_mode="multi", key=key, format_func=label) or []

usable = eligible(pool, ptype)
left_out = [ING[i]["short"] for i in pool if i not in usable]
if left_out:
    st.caption("Left out automatically: " + ", ".join(left_out) + ". Reasons: no sensory scores yet, pH adjusters need a "
               "measured pH, a duplicate fatty alcohol, or MIT in a leave-on product.")


def run(seed):
    with st.spinner("Searching…"):
        st.session_state["sg_results"] = optimise(pool, ptype, ph, countries, target, seed=seed, count=count)
    st.session_state["sg_seed"] = seed
    st.session_state["sg_used"] = (ptype, ph, countries, goal)
    st.session_state.pop("sg_loaded", None)


st.write("")
b1, b2, _ = st.columns([1, 1, 3])
disabled = not has_core(usable)
if disabled:
    st.warning("Allow at least one oil (emollient or butter), one fatty alcohol and one emulsifier, or no emulsion can be built.")
if b1.button("Find formulations", type="primary", disabled=disabled, key="btn_sg_find"):
    run(0)
if b2.button("Show different options", disabled=disabled or "sg_results" not in st.session_state, key="btn_sg_more"):
    run(st.session_state.get("sg_seed", 0) + 1)

if "sg_loaded" in st.session_state:
    st.success(f"Loaded into formula {st.session_state['sg_loaded']}.")
    st.page_link("page_formulation.py", label="Open the Formulation page to see it")

results = st.session_state.get("sg_results")
if results is None:
    st.stop()
if not results:
    st.error("No formula passed the rules for the countries you chose with these ingredients. "
             "Allow more ingredients or remove a country.")
    st.stop()

used_ptype, used_ph, used_countries, used_goal = st.session_state["sg_used"]
section_header("", "Results", "The best option" if len(results) == 1 else f"The best {len(results)}", "" if len(results) == 1 else "options",
               f"{used_goal} · {used_ptype.lower()} · pH {ph_text(used_ph)} · "
               f"{', '.join(used_countries) if used_countries else 'no country rules applied'}")

for start in range(0, len(results), 3):  # three options to a row
    for n, (res, col) in enumerate(zip(results[start:start + 3], st.columns(3, gap="large")), start=start + 1):
        with col:
            st.markdown(f"#### Option {n}")
            match = max(0, 100 - 10 * res["dist"])
            st.markdown(f'<p class="fx-note"><b>{product_form(res["sense"])}</b>'
                        f'<small>Stability score {res["stability"]} · Goal match {match:.0f}%</small></p>', unsafe_allow_html=True)
            if used_countries:
                st.markdown(f'{pill("ok")} <span class="fx-muted">in {len(used_countries)} '
                            f'{"country" if len(used_countries) == 1 else "countries"}</span>', unsafe_allow_html=True)
            st.markdown(table_html(["", "%"], recipe_rows(res["items"])), unsafe_allow_html=True)
            st.write("")
            name = f"Suggested option {n}"
            for slot, bc in zip(SLOTS, st.columns(2)):
                bc.button(f"Load into {slot}", key=f"btn_sg_load_{n}_{slot}", on_click=load_suggestion,
                          args=(res, slot, name), width="stretch")

st.write("")
st.markdown("**How each option feels against your goal**")
head = ["", "Goal", *[f"Option {n}" for n in range(1, len(results) + 1)]]
rows = [[label, f"{target[k]:g}", *[("–" if r["sense"][k] is None else f"{r['sense'][k]:.1f}") for r in results]]
        for k, (label, _, _) in SENSES.items()]
st.markdown(table_html(head, rows), unsafe_allow_html=True)
st.caption("These are theory-based starting points, not tested formulas. Load one into formula A or B to read its full "
           "stability checks and compliance details, then make a real batch and test it.")
