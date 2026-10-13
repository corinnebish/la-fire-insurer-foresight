"""Streamlit host for the interactive page in site/.

The page itself (3D map, charts, findings) is plain HTML + three.js + D3. Streamlit serves
it full-screen so it can be deployed for free on Streamlit Community Cloud.

Run locally:  streamlit run app/streamlit_app.py
"""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

SITE = Path(__file__).resolve().parents[1] / "site"

st.set_page_config(page_title="Insurers and the 2025 LA Fires", page_icon="🔥", layout="wide",
                   initial_sidebar_state="collapsed")

# hide Streamlit's own chrome and padding so the page fills the browser window
st.markdown("""
<style>
  header[data-testid="stHeader"], footer, #MainMenu, [data-testid="stToolbar"] {display: none !important;}
  .block-container, [data-testid="stMainBlockContainer"] {padding: 0 !important; max-width: 100% !important;}
  [data-testid="stAppViewContainer"] > .main, section.main {padding: 0 !important;}
  iframe {display: block; width: 100% !important; height: 100vh !important; border: 0;}
  body {overflow: hidden;}
</style>
""", unsafe_allow_html=True)


@st.cache_data
def page_html() -> str:
    """Inline data.js so the page is a single self-contained document."""
    html = (SITE / "index.html").read_text(encoding="utf-8")
    data = (SITE / "data.js").read_text(encoding="utf-8")
    return html.replace('<script src="data.js"></script>', f"<script>{data}</script>")


components.html(page_html(), height=900, scrolling=True)
