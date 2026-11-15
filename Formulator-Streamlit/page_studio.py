"""Studio page: the interactive bottle. Scroll through the phases, then drag ingredients in and out.

The page itself is studio/index.html (plain HTML, CSS and JavaScript). This file only hands it the data
from the CSV files and shows it full-screen under the menu. It uses nothing but Python's standard library,
so it opens even if the other pages cannot.

Fonts: put the PP Editorial New and PP Neue Montreal files (.woff2 or .otf, e.g. PPEditorialNew-Regular.otf,
PPEditorialNew-Italic.otf, PPNeueMontreal-Book.otf, PPNeueMontreal-Medium.otf) in studio/fonts/ and they are
used automatically. Without them the page falls back to Instrument Serif and Inter Tight.
"""
import base64
import csv
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HERE = Path(__file__).parent
WEIGHTS = {"thin": 100, "ultralight": 200, "light": 300, "book": 400, "regular": 400, "medium": 500,
           "semibold": 600, "ultrabold": 800, "bold": 700}


def rows(name):
    with open(HERE / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def font_faces():
    """@font-face rules for every licensed font file found in studio/fonts/, embedded in the page."""
    css = ""
    for f in sorted((HERE / "studio" / "fonts").glob("*")):
        low, ext = f.stem.lower(), f.suffix.lower()
        family = ("PP Editorial New" if "editorialnew" in low.replace(" ", "").replace("-", "") else
                  "PP Neue Montreal" if "neuemontreal" in low.replace(" ", "").replace("-", "") else None)
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
def studio_html(_stamp):
    data = {"ingredients": rows("ingredients.csv"), "products": rows("products.csv"), "regulations": rows("regulations.csv")}
    html = (HERE / "studio" / "index.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(data).replace("</", "<\\/"))
    return html.replace("/*__FONTS__*/", font_faces())


# rebuild the page whenever one of its files changes
watched = [HERE / "studio" / "index.html", HERE / "ingredients.csv", HERE / "products.csv", HERE / "regulations.csv",
           *(HERE / "studio" / "fonts").glob("*")]
stamp = tuple(p.stat().st_mtime for p in watched if p.is_file())

# show the studio edge to edge, directly under the menu
st.markdown("""<style>
[data-testid="stMainBlockContainer"]{padding:0!important;max-width:none!important}
[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#02070A}
[data-testid="stMain"] iframe{position:fixed;left:0;top:3.75rem;width:100vw;height:calc(100vh - 3.75rem);border:0;display:block}
</style>""", unsafe_allow_html=True)
components.html(studio_html(stamp), height=800, scrolling=True)
