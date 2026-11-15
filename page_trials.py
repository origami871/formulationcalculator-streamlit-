"""Trial log and machine-learning prediction."""
from datetime import date

import pandas as pd
import streamlit as st

from core import INGREDIENTS, SLOTS, build_formulas

st.title("Trial log")
st.caption("Your lab results are the training data for the machine-learning model. Streamlit Cloud does not keep "
           "files between visits, so download the CSV after each session and upload it again next time.")

F = build_formulas()
FEATURES = [i["inci"] for i in INGREDIENTS]
LOG_COLS = ["date", "name", "product_type", "target_pH", *FEATURES, "predicted_score", "lab_result", "notes"]
if "log" not in st.session_state:
    st.session_state.log = pd.DataFrame(columns=LOG_COLS)

up = st.file_uploader("Load a saved trial log (CSV)", type="csv")
if up is not None and st.session_state.get("loaded_file") != up.name:
    df = pd.read_csv(up)
    for c in LOG_COLS:
        if c not in df.columns:
            df[c] = 0 if c in FEATURES else ""
    st.session_state.log = df[LOG_COLS]
    st.session_state.loaded_file = up.name

c0, c1, c2 = st.columns([1, 1, 2])
save_slot = c0.radio("Formula to save", SLOTS, horizontal=True, format_func=lambda s: f"Formula {s}", key="save_slot")
result = c1.selectbox("Lab result", ["Not tested yet", "Stable (passed)", "Separation / creaming", "Grainy / crystals",
                                     "Viscosity drift", "pH drift", "Microbial fail", "Other"])
notes = c2.text_input("Notes", placeholder="e.g. 4 weeks at 45 °C, slight oil ring")
if st.button("Save formula to log", type="primary"):
    f = F[save_slot]
    row = {"date": str(date.today()), "name": f["name"], "product_type": f["ptype"], "target_pH": f["ph"],
           **{c: 0.0 for c in FEATURES}, "predicted_score": f["score"], "lab_result": result, "notes": notes}
    for i in f["items"]:
        row[i["inci"]] = round(i["pct"], 4)
    st.session_state.log = pd.concat([st.session_state.log, pd.DataFrame([row])], ignore_index=True)

log = st.session_state.log
st.dataframe(log, width="stretch", hide_index=True)
st.download_button("Download trial log (CSV)", log.to_csv(index=False), "formulator_trials.csv", "text/csv")

st.subheader("Machine-learning prediction")
tested = log[log["lab_result"] != "Not tested yet"]
passed = (tested["lab_result"] == "Stable (passed)").astype(int)
if len(tested) < 8 or passed.nunique() < 2:
    st.info(f"The model needs at least 8 lab-tested trials, including both passes and fails. "
            f"You have {len(tested)} tested trial(s) so far. Until then, use the theory-based score on the Formulation page.")
else:
    from sklearn.ensemble import RandomForestClassifier

    X = tested[FEATURES].astype(float)
    model = RandomForestClassifier(n_estimators=200, random_state=0).fit(X, passed)
    for slot, col in zip(SLOTS, st.columns(2)):
        now = pd.DataFrame([{c: 0.0 for c in FEATURES}])
        for i in F[slot]["items"]:
            now.loc[0, i["inci"]] = i["pct"]
        p_pass = model.predict_proba(now[FEATURES])[0][list(model.classes_).index(1)]
        col.metric(f"Formula {slot}: predicted chance of passing stability", f"{p_pass:.0%}")
    st.caption(f"Random forest trained on {len(tested)} of your lab trials. With small data this is a rough "
               "guide; it gets better with every trial you log.")
    imp = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False).head(6)
    imp = imp[imp > 0]
    st.bar_chart(imp, horizontal=True)
    st.caption("Ingredients the model relies on most when predicting a pass or fail.")

st.divider()
st.caption("Prototype for a Temasek Polytechnic project. Use levels, HLB, pH and sensory values are estimates for "
           "learning purposes: check them against supplier technical data sheets. A good score means lower predicted "
           "risk, not guaranteed stability, and predicted feel is no substitute for a sensory panel. Compliance rules "
           "are a first screen and not legal advice. Always run stability tests.")
