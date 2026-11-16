"""Studio page: the interactive bottle.

The page itself is studio.html (plain HTML, CSS and JavaScript, with fx_shared.js). This file:
  1. shows it full-screen under the menu, with the data from the CSV files,
  2. receives "Send to Formula A" or "Send to Formula B" and puts the formula on the Formulation page,
  3. receives "Ask Claude" questions and answers them with the Claude API.
The studio sends its messages through a hidden text box and reads the replies from a hidden element.
The shared code for this, the Claude API key and the fonts are explained in parts H and I of core.py.
"""
import streamlit as st
import streamlit.components.v1 as components

from core import answer, claude_ready, inbox_event, interactive_page, outbox, set_formula

chat = st.session_state.setdefault("fx_chat", [])

# Each button press in the studio arrives here once.
event = inbox_event("studio_inbox")
if event:
    if event.get("type") == "send":
        slot = "B" if event.get("slot") == "B" else "A"
        formula = event.get("formula") or {}
        set_formula(slot, formula.get("amounts"), name="Studio formula", ptype=formula.get("ptype"))
        st.session_state["studio_ack"] = {"id": event.get("id"), "msg": f"Sent to Formula {slot}. Open the Formulation page to see it."}
    elif event.get("type") == "ask":
        answer(event.get("question", ""), event.get("context", ""), q=event.get("q"))

# show the studio edge to edge, directly under the menu, and hide the text box and the reply element
st.markdown("""<style>
[data-testid="stMainBlockContainer"]{padding:0!important;max-width:none!important}
[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#02070A}
[data-testid="stMain"] [data-testid="stTextInput"]{display:none}
[data-testid="stMain"] iframe{position:fixed;left:0;top:3.75rem;width:100vw!important;height:calc(100vh - 3.75rem)!important;border:0;display:block}
</style>""", unsafe_allow_html=True)
st.text_input("studio-inbox", key="studio_inbox", label_visibility="collapsed")
outbox("fx-outbox", {"chat": chat, "ack": st.session_state.get("studio_ack"), "claude": claude_ready()})
components.html(interactive_page("studio.html"), height=800, scrolling=True)
