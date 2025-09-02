import streamlit as st

ECO_CSS = """
<style>
body { background-color: #FAF9F6; color: #3E4E2C; font-family: "Georgia", serif; }
[data-testid="stAppViewContainer"] > .main { background-color: #FAF9F6; padding: 2rem; max-width: 900px; margin: auto; }
.stSelectbox > div, .stMarkdown, .stCaption { color: #3E4E2C; }
h3 { margin-bottom: 0.2rem; font-size: 0.95rem; color: #4C3D29; }
p, .markdown-text-container { margin-top: 0.05rem; margin-bottom: 0.5rem; line-height: 1.2; }
hr { margin: 0.6rem 0; border: none; border-top: 1px solid #ccc; }
</style>
"""

def aplicar_estilos():
    st.markdown(ECO_CSS, unsafe_allow_html=True)