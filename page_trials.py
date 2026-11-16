"""Trial log and machine-learning prediction.

How it works, in short:
  1. Each row of the log is one batch you made: the % of every ingredient, and what happened to it in the lab.
  2. Once 8 or more rows have a lab result, with at least one pass and one fail, a random forest model learns
     which amounts went with passes and which with fails.
  3. The model then estimates the chance that formulas A and B pass, from their own amounts.
The sample trials (part J of core.py, also in sample_trial_log.csv) let you try all of this before you have data.
"""
from datetime import date

import pandas as pd
import streamlit as st

from core import (LOG_COLS, RESULTS, SLOTS, TRIAL_FEATURES, build_formulas, page_header, ph_text, sample_trial_rows,
                  section_header)

page_header("06", "Trial log", "From the", "lab bench",
            "Record what happened to each batch in the lab. Once enough trials are logged, a machine-learning model "
            "learns from them and estimates the chance that formulas A and B will pass.")

st.markdown("""<div class="fx-steps">
<div class="fx-step"><span>STEP 1</span><b>Log each batch</b><p>Save formula A or B with what happened in the lab: stable, separated, grainy and so on. Each batch becomes one row.</p></div>
<div class="fx-step"><span>STEP 2</span><b>The model learns</b><p>After 8 tested batches, with at least one pass and one fail, it looks for the amounts that went with passes and with fails.</p></div>
<div class="fx-step"><span>STEP 3</span><b>Read the prediction</b><p>It estimates the chance that formulas A and B pass, and shows which ingredients it relies on most.</p></div>
</div>""", unsafe_allow_html=True)

F = build_formulas()
if "log" not in st.session_state:
    st.session_state.log = pd.DataFrame(columns=LOG_COLS)


def tidy(df):
    """Make a sheet fit the log: add any missing column, read the amounts as numbers, keep the known columns in order."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for c in LOG_COLS:
        if c not in df.columns:
            df[c] = 0.0 if c in TRIAL_FEATURES else ""
    df[TRIAL_FEATURES] = df[TRIAL_FEATURES].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    for c in ("name", "product_type", "target_pH", "lab_result", "notes", "date"):
        df[c] = df[c].fillna("").astype(str).str.strip()
    df.loc[df["lab_result"] == "", "lab_result"] = "Not tested yet"
    return df[LOG_COLS].reset_index(drop=True)


sample = tidy(pd.DataFrame(sample_trial_rows()))

# ---- Try it, or load your own ----
section_header("", "Start", "Try it with", "sample data",
               "New here? Load 15 made-up trials to see how the page works, or download them to see the layout of the "
               "sheet. It opens in Excel: one row per batch, one column per ingredient.")
t1, t2, _ = st.columns([1, 1, 2])
if t1.button("Load the sample trials", type="primary", key="btn_log_sample", width="stretch"):
    st.session_state.log = sample.copy()
    st.toast("15 sample trials loaded. Scroll down to see the prediction.")
t2.download_button("Download the sample sheet", sample.to_csv(index=False).encode("utf-8-sig"), "sample_trial_log.csv",
                   "text/csv", key="btn_log_sample_dl", width="stretch")

up = st.file_uploader("Or load your own trial log (CSV or Excel)", type=["csv", "xlsx"],
                      help="Use the layout of the sample sheet. Streamlit Cloud does not keep files between visits, "
                           "so download your log after each session and load it again next time.")
if up is not None and st.session_state.get("loaded_file") != (up.name, up.size):
    try:
        raw = pd.read_excel(up) if up.name.lower().endswith(".xlsx") else pd.read_csv(up)
        st.session_state.log = tidy(raw)
        st.session_state.loaded_file = (up.name, up.size)
    except Exception as e:  # a sheet that is not a table, or an Excel reader that is not installed
        st.error(f"That file could not be read ({type(e).__name__}). Save it as CSV with the columns of the sample sheet "
                 "and try again.")

# ---- Add a trial ----
section_header("", "Log", "Add a", "trial",
               "Saves formula A or B from the Formulation page as a new row, with its lab result.")
c0, c1, c2 = st.columns([1, 1, 2])
save_slot = c0.radio("Formula to save", SLOTS, horizontal=True, format_func=lambda s: f"Formula {s}", key="save_slot")
result = c1.selectbox("Lab result", RESULTS)
notes = c2.text_input("Notes", placeholder="e.g. 4 weeks at 45 °C, slight oil ring")
if st.button("Save formula to log", type="primary", key="btn_log_save"):
    f = F[save_slot]
    row = {"date": str(date.today()), "name": f["name"], "product_type": f["ptype"], "target_pH": ph_text(f["ph"]),
           **{c: 0.0 for c in TRIAL_FEATURES}, "predicted_score": f["score"], "lab_result": result, "notes": notes}
    for i in f["items"]:
        row[i["inci"]] = round(i["pct"], 4)
    new = pd.DataFrame([row])[LOG_COLS]
    st.session_state.log = new if st.session_state.log.empty else pd.concat([st.session_state.log, new], ignore_index=True)

log = st.session_state.log
tested = log[log["lab_result"] != "Not tested yet"]
passed = (tested["lab_result"] == "Stable (passed)").astype(int)
st.caption(f"{len(log)} trial(s) in the log: {int(passed.sum())} passed, {int(len(tested) - passed.sum())} failed, "
           f"{len(log) - len(tested)} not tested yet.")
st.dataframe(log, width="stretch", hide_index=True)
d1, d2, _ = st.columns([1, 1, 2])
d1.download_button("Download trial log (CSV)", log.to_csv(index=False).encode("utf-8-sig"), "formulator_trials.csv",
                   "text/csv", key="btn_log_dl", width="stretch")
if d2.button("Empty the log", key="btn_log_clear", width="stretch", disabled=log.empty):
    st.session_state.log = pd.DataFrame(columns=LOG_COLS)
    st.rerun()

# ---- Prediction ----
section_header("", "Machine learning", "Will it", "pass?",
               "Learned from your own lab results, not from theory. Compare it with the theory-based stability score "
               "on the Formulation page.")
if len(tested) < 8 or passed.nunique() < 2:
    need = []
    if len(tested) < 8:
        need.append(f"{8 - len(tested)} more tested trial(s)")
    if passed.nunique() < 2:
        need.append("at least one pass and one fail")
    st.info(f"The model needs 8 tested trials, including both passes and fails. You have {len(tested)} tested so far, "
            f"so it still needs {' and '.join(need)}. Load the sample trials above to see it working.")
else:
    from sklearn.ensemble import RandomForestClassifier

    X = tested[TRIAL_FEATURES].astype(float)
    model = RandomForestClassifier(n_estimators=200, random_state=0).fit(X, passed)
    for slot, col in zip(SLOTS, st.columns(2)):
        now = pd.DataFrame([{c: 0.0 for c in TRIAL_FEATURES}])
        for i in F[slot]["items"]:
            now.loc[0, i["inci"]] = i["pct"]
        p_pass = model.predict_proba(now[TRIAL_FEATURES])[0][list(model.classes_).index(1)]
        col.metric(f"Formula {slot}: predicted chance of passing", f"{p_pass:.0%}",
                   f"theory score {F[slot]['score']}" if F[slot]["score"] is not None else None, delta_color="off")
    st.caption(f"Trained on {len(tested)} tested trials ({int(passed.sum())} passed, {int(len(tested) - passed.sum())} failed). "
               "With this little data it is a rough guide. It gets better with every trial you log.")
    imp = pd.Series(model.feature_importances_, index=TRIAL_FEATURES).sort_values(ascending=False).head(6)
    imp = imp[imp > 0]
    if not imp.empty:
        st.markdown("**Ingredients the model relies on most**")
        st.bar_chart(imp, horizontal=True)
        st.caption("A long bar means the amount of that ingredient separated passes from fails in your trials. "
                   "It does not say whether more of it is good or bad.")

with st.expander("How the prediction works"):
    st.markdown(
        "- **What it learns from.** Every tested trial is one example: the % of each ingredient, and whether the batch "
        "passed (“Stable”) or failed (any other result).\n"
        "- **The model.** A random forest builds 200 small decision trees. Each tree finds simple rules in your examples, "
        "such as “when the emulsifier is under 1.5% and the oils are over 12%, the batch separated”.\n"
        "- **The prediction.** For formula A or B, every tree votes pass or fail from that formula's amounts. "
        "The share of pass votes is the chance shown.\n"
        "- **Its limits.** It only knows what your trials show it. A formula unlike anything you have tested gets an "
        "unreliable answer, and 8 trials is the bare minimum: 30 or more gives a steadier result. It looks only at "
        "ingredient amounts, not at how the batch was made.\n"
        "- **Theory score or prediction?** The stability score on the Formulation page comes from formulation rules and "
        "works from the first formula. This prediction comes from your own lab results, so trust it more as the log grows.")

st.divider()
st.caption("Prototype for a Temasek Polytechnic project. Use levels, HLB, pH and sensory values are estimates for "
           "learning purposes: check them against supplier technical data sheets. A good score means lower predicted "
           "risk, not guaranteed stability, and predicted feel is no substitute for a sensory panel. Compliance rules "
           "are a first screen and not legal advice. Always run stability tests.")
