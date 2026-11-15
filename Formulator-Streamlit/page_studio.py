"""Studio page: the interactive bottle.

The page itself is studio/index.html (plain HTML, CSS and JavaScript). This file:
  1. hands it the data from the CSV files and shows it full-screen under the menu,
  2. receives "Send to Formula A" and puts the formula on the Formulation page,
  3. receives "Ask Claude" questions and answers them with the Claude API.
It uses only Python's standard library plus streamlit and anthropic.
The studio sends its messages through a hidden text box and reads the replies from a hidden element.

Ask Claude needs an API key. Never put the key in a file you upload to GitHub. Instead:
  on Streamlit Community Cloud:  app menu > Settings > Secrets, and add the line
                                 ANTHROPIC_API_KEY = "sk-ant-..."
  on your own computer:          put the same line in .streamlit/secrets.toml (this file is in .gitignore)
Without a key everything else still works and the Ask section says Claude is not connected.

Fonts: put the PP Editorial New and PP Neue Montreal files (.woff2 or .otf, named PPEditorialNew-Regular,
PPEditorialNew-Italic, PPNeueMontreal-Book, PPNeueMontreal-Medium) in studio/fonts/ and they are used
automatically. Without them the page falls back to Instrument Serif and Inter Tight.
"""
import base64
import csv
import json
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
MODEL = "claude-opus-5-5"
MAX_QUESTIONS = 40          # per visitor session, so one visitor cannot run up the bill
WEIGHTS = {"thin": 100, "ultralight": 200, "light": 300, "book": 400, "regular": 400, "medium": 500,
           "semibold": 600, "ultrabold": 800, "bold": 700}


def rows(name):
    with open(HERE / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def font_faces():
    """@font-face rules for every licensed font file found in studio/fonts/, embedded in the page."""
    css = ""
    for f in sorted((HERE / "studio" / "fonts").glob("*")):
        low, ext = f.stem.lower().replace(" ", "").replace("-", ""), f.suffix.lower()
        family = "PP Editorial New" if "editorialnew" in low else "PP Neue Montreal" if "neuemontreal" in low else None
        if family is None or ext not in (".woff2", ".woff", ".otf", ".ttf"):
            continue
        weight = next((w for k, w in WEIGHTS.items() if k in low), 400)
        style = "italic" if "italic" in low else "normal"
        kind = {".woff2": "woff2", ".woff": "woff", ".otf": "opentype", ".ttf": "truetype"}[ext]
        data = base64.b64encode(f.read_bytes()).decode()
        css += (f'@font-face{{font-family:"{family}";font-weight:{weight};font-style:{style};font-display:swap;'
                f'src:url(data:font/{ext[1:]};base64,{data}) format("{kind}")}}\n')
    return css


@st.cache_data
def load(stamp):  # stamp changes when a file changes, which makes Streamlit load again
    """The data from the CSV files, and the studio page with that data written into it."""
    data = {"ingredients": rows("ingredients.csv"), "products": rows("products.csv"), "regulations": rows("regulations.csv")}
    html = (HERE / "studio" / "index.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(data).replace("</", "<\\/"))
    return data, html.replace("/*__FONTS__*/", font_faces())


def secret(name):
    try:
        value = st.secrets.get(name)
    except Exception:  # no secrets file at all
        value = None
    return value or os.environ.get(name)


def claude_ready():
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(secret("ANTHROPIC_API_KEY"))


# ---- Send to Formula A: write the same session keys the Formulation page reads ----
def send_to_formula(slot, formula, ingredients):
    amounts = {k: float(v) for k, v in formula.get("amounts", {}).items()}
    for i in ingredients:
        st.session_state[f"{slot}_sel_{i['id']}"] = i["id"] in amounts
    for ing_id, pct in amounts.items():
        st.session_state[f"{slot}_pct_{ing_id}"] = pct
    st.session_state[f"{slot}_name"] = "Studio formula"
    st.session_state[f"{slot}_ptype"] = formula.get("ptype", "Leave-on")
    st.session_state[f"{slot}_ph"] = float(formula.get("ph", 5.5))


# ---- Ask Claude ----
def system_prompt(ingredients):
    library = "\n".join(
        f"- {i['inci']} ({i['short']}): {i['cat']}, {i['phase']} phase, usual {i['min'] or '?'}-{i['max'] or '?'}%. {i['notes']}"
        for i in ingredients)
    return (
        "You are the formulation assistant inside Formulator Studio, a tool for building oil-in-water cosmetic "
        "emulsions such as body lotions and creams. The person asking is working on the formulation shown in the "
        "<current_formula> block of their latest message. It lists the ingredients by phase with % w/w, the tool's "
        "theory-based stability checks, and its predicted feel.\n\n"
        "Answer the question about that formulation directly and practically: say what to change, by how much, and "
        "why. Prefer ingredients from the library below, because those are the ones the person can add in the tool; "
        "if something outside the library would clearly work better, say so and name it. The stability score and "
        "feel numbers are predictions from formulation theory, not measurements, so treat them as indications. "
        "Legal limits vary by country and change over time; when one matters, give what you know and tell the "
        "person to confirm it against the current official text. A formula is only proven by making a batch and "
        "running stability and preservative challenge tests; mention this when it bears on the question, without "
        "repeating it in every answer.\n\n"
        "The answer is shown in a small chat panel that displays plain text only. Write short paragraphs in plain "
        "sentences, with no Markdown symbols such as asterisks, pound signs or tables. Keep most answers under "
        "150 words unless the question needs more.\n\n"
        f"Ingredient library:\n{library}")


def ask_claude(history, question, context, ingredients):
    """Returns (role, text): role is "assistant" for an answer or "error" for a message to show instead."""
    try:
        import anthropic
    except ImportError:
        return "error", "Claude is not installed on the server. Add the line anthropic to requirements.txt and redeploy."
    key = secret("ANTHROPIC_API_KEY")
    if not key:
        return "error", "Claude is not connected yet. Add ANTHROPIC_API_KEY to the app's secrets, then reload."
    messages = [{"role": m["role"], "content": m["text"]} for m in history if m["role"] in ("user", "assistant")]
    messages.append({"role": "user", "content": f"<current_formula>\n{context}\n</current_formula>\n\n{question}"})
    request = dict(model=MODEL, max_tokens=16000, system=system_prompt(ingredients), messages=messages,
                   output_config={"effort": "medium"})
    client = anthropic.Anthropic(api_key=key)
    try:
        try:
            # if the safety system declines a question, let the API hand it to a fallback model
            reply = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request)
        except TypeError:  # an older anthropic package without the fallbacks option
            reply = client.messages.create(**request)
    except anthropic.AuthenticationError:
        return "error", "The Claude API key was rejected. Check ANTHROPIC_API_KEY in the app's secrets."
    except anthropic.RateLimitError:
        return "error", "Claude is busy right now. Wait a moment and ask again."
    except anthropic.APIStatusError as e:
        return "error", f"Claude returned an error ({e.status_code}). Try again in a moment."
    except anthropic.APIConnectionError:
        return "error", "Could not reach Claude. Check the internet connection and try again."
    if reply.stop_reason == "refusal":
        return "error", "Claude declined to answer that question. Try asking it differently."
    text = "".join(b.text for b in reply.content if b.type == "text").strip()
    return ("assistant", text) if text else ("error", "Claude sent back an empty answer. Try again.")


# ---- the page ----
watched = [HERE / "studio" / "index.html", HERE / "ingredients.csv", HERE / "products.csv", HERE / "regulations.csv",
           *(HERE / "studio" / "fonts").glob("*")]
data, html = load(tuple(p.stat().st_mtime for p in watched if p.is_file()))
chat = st.session_state.setdefault("studio_chat", [])

# The studio talks to this file through a hidden text box. Each button press there arrives once, with its own id.
try:
    event = json.loads(st.session_state.get("studio_inbox") or "null")
except ValueError:
    event = None
if isinstance(event, dict) and event.get("id") != st.session_state.get("studio_done"):
    st.session_state["studio_done"] = event.get("id")
    if event.get("type") == "send":
        send_to_formula("A", event.get("formula", {}), data["ingredients"])
        st.session_state["studio_ack"] = {"id": event.get("id"), "msg": "Sent to Formula A. Open the Formulation page to see it."}
    elif event.get("type") == "ask":
        question = str(event.get("question", ""))[:2000]
        if sum(m["role"] == "user" for m in chat) >= MAX_QUESTIONS:
            role, text = "error", "You have reached the question limit for this visit. Reload the page to start again."
        else:
            role, text = ask_claude(chat, question, str(event.get("context", ""))[:8000], data["ingredients"])
        chat.append({"role": "user", "text": question, "q": event.get("q")})
        chat.append({"role": role, "text": text})

# show the studio edge to edge, directly under the menu, and hide the text box and the reply element
st.markdown("""<style>
[data-testid="stMainBlockContainer"]{padding:0!important;max-width:none!important}
[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#02070A}
[data-testid="stMain"] [data-testid="stTextInput"]{display:none}
[data-testid="stMain"] iframe{position:fixed;left:0;top:3.75rem;width:100vw!important;height:calc(100vh - 3.75rem)!important;border:0;display:block}
</style>""", unsafe_allow_html=True)
st.text_input("studio-inbox", key="studio_inbox", label_visibility="collapsed")
reply = {"chat": chat, "ack": st.session_state.get("studio_ack"), "claude": claude_ready()}
st.markdown(f'<div id="fx-outbox" hidden>{base64.b64encode(json.dumps(reply).encode()).decode()}</div>', unsafe_allow_html=True)
components.html(html, height=800, scrolling=True)
