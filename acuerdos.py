# acuerdos.py — versión modernizada con tabs + deep link + header sticky (light-only)

import streamlit as st
import datetime as dt

# ----------------------------
# Config básica de la app
# ----------------------------
st.set_page_config(page_title="Acuerdos Aucca", layout="wide")

# ----------------------------
# Estilos (light-only + compact)
# ----------------------------
ECO_CSS = """
<style>
:root {
  color-scheme: only light; /* fuerza light */
}
html, body, [data-testid="stAppViewContainer"] > .main {
  background-color: #FAF9F6 !important;
  color: #3E4E2C !important;
  font-family: "Georgia", serif;
}
[data-testid="stSidebar"] { background-color: #FAF9F6 !important; }

/* Compacta paddings generales */
.block-container { padding-top: 0.8rem !important; }

/* Header sticky */
.aucca-header {
  position: sticky; top: 0; z-index: 998;
  background: #FAF9F6;
  border-bottom: 1px solid #e7e1d6;
  margin: 0 -1rem 1rem -1rem; padding: 0.6rem 1rem;
}
.aucca-header .wrap {
  display: flex; align-items: center; gap: 12px;
}
.aucca-header h1 {
  font-size: 1.35rem; margin: 0; color: #2E2A27;
}

/* Títulos de sección con icono SVG pequeño */
.section-title {
  display: flex; align-items: center; gap: 8px; margin: 0.2rem 0 0.8rem;
}
.section-title svg { width: 18px; height: 18px; display: inline-block; }

/* Tarjetas KPI genéricas */
.kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 6px 0 16px; }
.kpi { background: #F7F3E9; border: 1px solid #E7DDC6; border-radius: 14px; padding: 10px 12px; }
.kpi .label { font-size: 0.9rem; color: #6B6B6B; }
.kpi .value { font-size: 1.4rem; font-weight: 700; color: #2E2A27; }

/* Tabs sin emojis (ya vienen del label) */
[data-baseweb="tab"] { font-weight: 500; }

/* En móviles, compactar más */
@media (max-width: 640px) {
  .kpi-row { grid-template-columns: 1fr 1fr; }
}
</style>
"""
st.markdown(ECO_CSS, unsafe_allow_html=True)

# ----------------------------
# Header sticky
# ----------------------------

import base64

def load_logo(path):
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("utf-8")

logo_base64 = load_logo("images/logo_aucca.png")

st.markdown(
    f"""
    <style>
    .aucca-banner {{
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-top: 2rem;
    }}
    .aucca-banner img {{
        width: 70px;
        height: 70px;
        border-radius: 50%;
        object-fit: cover;
        box-shadow: 0 2px 6px rgba(0,0,0,0.2);
    }}
    .aucca-banner h1 {{
        font-size: 2rem;
        font-weight: 700;
        margin: 0;
    }}
    </style>
    <div class="aucca-banner">
        <img src="data:image/png;base64,{logo_base64}" alt="AUCCA logo">
        <h1>Acuerdos</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

# col_logo, col_title = st.columns([1, 8])
# with col_logo:
#     try:
#         st.image("images/logo_aucca.png", width=80)
#     except Exception:
#         st.write("")  
# with col_title:
#     st.markdown('<div class="aucca-header"><h1>Acuerdos</h1></div>', unsafe_allow_html=True)

# ----------------------------
# Definición de secciones (orden y slugs para deep link)
# ----------------------------
SECTIONS = [
    {"slug": "internos",  "label": "Acuerdos de convivencia (internos)"},
    {"slug": "externos",  "label": "Acuerdos Comunicación Externa"},
    {"slug": "checklist", "label": "Checklist de semanerx"},
    {"slug": "finanzas",  "label": "Finanzas"},
    {"slug": "links",     "label": "Links claves"},
]

# ----------------------------
# Deep link: ?section=slug
# - Reordenamos las tabs para que la solicitada quede primera (aparece seleccionada)
# ----------------------------
def _get_query_section():
    # Streamlit recientes: st.query_params (>=1.30); fallback a experimental
    try:
        qp = st.query_params
        sec = qp.get("section", [None])
        if isinstance(sec, list):
            sec = sec[0]
    except Exception:
        qp = st.experimental_get_query_params()
        sec = (qp.get("section", [None]) or [None])[0]
    return sec

section_q = _get_query_section()
if section_q and any(s["slug"] == section_q for s in SECTIONS):
    SECTIONS = sorted(SECTIONS, key=lambda s: 0 if s["slug"] == section_q else 1)

# ----------------------------
# Tabs
# ----------------------------
tabs = st.tabs([s["label"] for s in SECTIONS])

# ----------------------------
# Inline SVG íconos por sección (no emojis)
# ----------------------------
ICONS = {
    "checklist": """<svg viewBox="0 0 24 24" fill="none"><path d="M9 11l3 3L22 4" stroke="#3E4E2C" stroke-width="2" fill="none"/><rect x="2" y="7" width="12" height="12" rx="2" stroke="#3E4E2C" stroke-width="2"/></svg>""",
    "internos":  """<svg viewBox="0 0 24 24" fill="none"><path d="M3 10l9-7 9 7v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9z" stroke="#3E4E2C" stroke-width="2"/></svg>""",
    "externos":  """<svg viewBox="0 0 24 24" fill="none"><path d="M4 4h16v6H4zM4 14h10m-6 4h6" stroke="#3E4E2C" stroke-width="2"/></svg>""",
    "links":     """<svg viewBox="0 0 24 24" fill="none"><path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 1 0-7-7l-1 1m4 6-1 1a5 5 0 1 1-7-7l2-2" stroke="#3E4E2C" stroke-width="2"/></svg>""",
    "finanzas":  """<svg viewBox="0 0 24 24" fill="none"><circle cx="8" cy="8" r="3" stroke="#3E4E2C" stroke-width="2"/><path d="M3 21a9 9 0 0 1 18 0" stroke="#3E4E2C" stroke-width="2"/></svg>""",
}

# ----------------------------
# Capa de render seguro (diagnóstico si falla)
# ----------------------------
def _safe_render(section_slug: str):
    try:
        if section_slug == "checklist":
            from secciones.checklist import render as render_checklist
            #st.markdown(f'<div class="section-title">{ICONS["checklist"]}<h3>Checklist de semanerx</h3></div>', unsafe_allow_html=True)
            render_checklist()

        elif section_slug == "internos":
            try:
                from secciones.acuerdos_internos import render as render_internos
            except Exception:
                st.info("Esta sección aún no está modularizada como `secciones/acuerdos_internos.py` con una función `render()`.")
                return
            #st.markdown(f'<div class="section-title">{ICONS["internos"]}<h3>Acuerdos de convivencia (internos)</h3></div>', unsafe_allow_html=True)
            render_internos()

        elif section_slug == "externos":
            try:
                from secciones.acuerdos_externos import render as render_externos
            except Exception:
                st.info("Esta sección aún no está modularizada como `secciones/acuerdos_externos.py` con una función `render()`.")
                return
            #st.markdown(f'<div class="section-title">{ICONS["externos"]}<h3>Acuerdos Comunicación Externa</h3></div>', unsafe_allow_html=True)
            render_externos()

        elif section_slug == "links":
            try:
                from secciones.links_claves import render as render_links
            except Exception:
                st.info("Esta sección aún no está modularizada como `secciones/links_claves.py` con una función `render()`.")
                return
            #st.markdown(f'<div class="section-title">{ICONS["links"]}<h3>Links claves</h3></div>', unsafe_allow_html=True)
            render_links()

        elif section_slug == "finanzas":
            from secciones.finanzas_aucca import render as render_finanzas
            #st.markdown(f'<div class="section-title">{ICONS["finanzas"]}<h3>Finanzas</h3></div>', unsafe_allow_html=True)
            render_finanzas()

        else:
            st.warning("Sección no reconocida.")
    except Exception as e:
        # Panel de diagnóstico: no rompe toda la app
        st.error("No se pudo renderizar esta sección. Revisa el detalle abajo.")
        st.exception(e)

# ----------------------------
# Colocar contenido en cada tab (en el orden actual)
# Nota: el deep link solo define la tab que aparece seleccionada al cargar.
# ----------------------------
for tab, sec in zip(tabs, SECTIONS):
    with tab:
        _safe_render(sec["slug"])
