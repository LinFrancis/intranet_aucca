# acuerdos.py — versión modernizada con tabs + deep link + header sticky (light-only)

import streamlit as st
import datetime as dt

# ----------------------------
# Config básica de la app
# ----------------------------
st.set_page_config(page_title="Plataforma Aucca", layout="wide")

# ----------------------------
# Estilos UI Premium (Montserrat + Clean Design)
# ----------------------------
ECO_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700&display=swap');

:root {
  color-scheme: only light;
}

/* Tipografía global - Aplicada selectivamente para no romper iconos */
html, body, .main, .stMarkdown, p, span, div, label, li, .st-emotion-cache-16idsys p {
  font-family: 'Montserrat', sans-serif !important;
}

/* Preservar iconos (Material Icons / Font Awesome / Streamlit Icons) */
.material-icons, [class*="Icon"], [data-testid="stIconMaterial"], [data-testid="stExpander"] svg {
  font-family: inherit !important; /* Permitir que hereden su propia fuente si está definida inline o por Streamlit */
}

/* Fondos */
[data-testid="stAppViewContainer"] > .main {
  background-color: #F3ECFF !important;
}
[data-testid="stSidebar"] {
  background-color: #E6D9FF !important;
}

/* Encabezados y tipografía */
h1, h2, h3, h4, h5, h6 {
  font-family: 'Montserrat', sans-serif !important;
  font-weight: 600 !important;
  color: #7B4F9E !important;
  letter-spacing: -0.02em;
}

/* Tabs UI */
[data-baseweb="tab"] p {
  font-family: 'Montserrat', sans-serif !important;
  font-weight: 600;
  font-size: 1rem;
  letter-spacing: 0.01em;
}
[data-baseweb="tab-highlight"] {
  background-color: #9D7FEA !important;
}

/* Estilo de Tarjetas Expandibles y Contenedores */
[data-testid="stExpander"] {
  border: 1px solid #E6D9FF !important;
  border-radius: 12px !important;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  background-color: #FFFFFF !important;
  overflow: visible !important; /* Permitir que la flecha se vea correctamente */
}

/* Limpiar flechas extra y corregir alineación del expander */
[data-testid="stExpander"] summary::before,
[data-testid="stExpander"] summary p::before {
  content: none !important;
  display: none !important;
}

[data-testid="stExpander"] summary svg {
  color: #7B4F9E !important;
  transition: transform 0.2s ease;
}

[data-testid="stExpander"] summary p {
  color: #7B4F9E !important;
  font-weight: 600 !important;
  margin: 0 !important;
  line-height: inherit !important;
}

/* Evitar que aparezca el nombre del icono como texto (ligaduras) */
[data-testid="stExpander"] summary [data-testid="stIconMaterial"], 
[data-testid="stExpander"] summary span {
    font-family: 'Material Icons', 'Material Symbols Outlined' !important;
}

/* Formularios y Cajas de Inputs */
input, select, textarea, [data-baseweb="select"] {
  border-radius: 8px !important;
  background-color: #FFFFFF !important;
  border: 1px solid #CDB4FF !important;
  transition: all 0.2s ease-in-out;
}
input:focus, select:focus, textarea:focus {
  border-color: #B497E7 !important;
  box-shadow: 0 0 0 1px #B497E7 !important;
}

/* Arreglo específico para Multiselect (evitar borde izquierdo doble) */
[data-testid="stMultiSelect"] > div {
    border-left: 1px solid #CDB4FF !important;
}
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    border: none !important;
}

/* Botones Primary */
[data-testid="baseButton-primary"] {
  background-color: #B497E7 !important;
  color: #FFFFFF !important;
  border-radius: 8px !important;
  border: none !important;
  font-family: 'Montserrat', sans-serif !important;
  font-weight: 600 !important;
  padding: 0.5rem 1rem !important;
  transition: all 0.2s ease;
  box-shadow: 0 4px 6px rgba(180, 151, 231, 0.2) !important;
}
[data-testid="baseButton-primary"]:hover {
  background-color: #9D7FEA !important;
  box-shadow: 0 6px 10px rgba(157, 127, 234, 0.3) !important;
  transform: translateY(-1px);
}

/* Botones Secundarios */
[data-testid="baseButton-secondary"] {
  border-radius: 8px !important;
  border: 1px solid #CDB4FF !important;
  background-color: #FFFFFF !important;
  font-weight: 600 !important;
  font-family: 'Montserrat', sans-serif !important;
  color: #7B4F9E !important;
  transition: all 0.2s ease;
}
[data-testid="baseButton-secondary"]:hover {
  border-color: #9D7FEA !important;
  background-color: #F3ECFF !important;
}

/* Tablas Dataframe */
[data-testid="stDataFrame"] {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  border: 1px solid #CDB4FF;
}

/* Diseño Banner principal */
.aucca-banner {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    margin-top: 1rem;
    margin-bottom: 2.5rem;
    padding: 1.5rem;
    background: linear-gradient(135deg, #FFFFFF 0%, #F3ECFF 100%);
    border-radius: 16px;
    box-shadow: 0 4px 16px rgba(123, 79, 158, 0.06);
    border: 1px solid #E6D9FF;
}
.aucca-banner img {
    width: 75px;
    height: 75px;
    border-radius: 50%;
    object-fit: cover;
    box-shadow: 0 4px 10px rgba(0,0,0,0.1);
    border: 3px solid #FFFFFF;
}
.aucca-banner h1 {
    font-size: 2.2rem !important;
    font-weight: 700 !important;
    margin: 0 !important;
    color: #7B4F9E !important;
    letter-spacing: -0.03em !important;
}

/* Detalles menores y layout */
hr { border-color: #E6D9FF !important; }
.block-container { padding-top: 2rem !important; max-width: 1200px; }

/* Métricas en Finanzas */
[data-testid="stMetricValue"] {
  font-family: 'Montserrat', sans-serif !important;
  font-weight: 700 !important;
  color: #7B4F9E !important;
}
</style>
"""
st.markdown(ECO_CSS, unsafe_allow_html=True)

# ----------------------------
# Header sticky / Banner Logo
# ----------------------------
import base64

def load_logo(path):
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("utf-8")

logo_base64 = load_logo("images/logo_aucca.png")

st.markdown(
    f"""
    <div class="aucca-banner">
        <img src="data:image/png;base64,{logo_base64}" alt="AUCCA logo">
        <h1>Plataforma Gestión Interna</h1>
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
    {"slug": "bienvenida", "label": "Bienvenida"},
    {"slug": "checklist", "label": "Semanerx"},
    {"slug": "finanzas",  "label": "Finanzas"},
    {"slug": "links",     "label": "Links claves"},
    {"slug": "acuerdos",  "label": "Acuerdos"},
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
    "bienvenida": """<svg viewBox="0 0 24 24" fill="none"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" stroke="#3E4E2C" stroke-width="2"/><polyline points="9 22 9 12 15 12 15 22" stroke="#3E4E2C" stroke-width="2"/></svg>""",
    "checklist": """<svg viewBox="0 0 24 24" fill="none"><path d="M9 11l3 3L22 4" stroke="#3E4E2C" stroke-width="2" fill="none"/><rect x="2" y="7" width="12" height="12" rx="2" stroke="#3E4E2C" stroke-width="2"/></svg>""",
    "acuerdos":  """<svg viewBox="0 0 24 24" fill="none"><path d="M3 10l9-7 9 7v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9z" stroke="#3E4E2C" stroke-width="2"/></svg>""",
    "links":     """<svg viewBox="0 0 24 24" fill="none"><path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 1 0-7-7l-1 1m4 6-1 1a5 5 0 1 1-7-7l2-2" stroke="#3E4E2C" stroke-width="2"/></svg>""",
    "finanzas":  """<svg viewBox="0 0 24 24" fill="none"><circle cx="8" cy="8" r="3" stroke="#3E4E2C" stroke-width="2"/><path d="M3 21a9 9 0 0 1 18 0" stroke="#3E4E2C" stroke-width="2"/></svg>""",
}

# ----------------------------
# Capa de render seguro (diagnóstico si falla)
# ----------------------------
def _safe_render(section_slug: str):
    try:
        if section_slug == "bienvenida":
            try:
                from secciones.bienvenida import render as render_bienvenida
                render_bienvenida()
            except Exception:
                st.info("Módulo bienvenida no disponible.")
                
        elif section_slug == "checklist":
            from secciones.checklist import render as render_checklist
            #st.markdown(f'<div class="section-title">{ICONS["checklist"]}<h3>Checklist de semanerx</h3></div>', unsafe_allow_html=True)
            render_checklist()

        elif section_slug == "acuerdos":
            st.markdown("### Repositorio de Acuerdos")
            tab_int, tab_ext = st.tabs(["Acuerdos Internos", "Acuerdos Externos"])
            with tab_int:
                try:
                    from secciones.acuerdos_internos import render as render_internos
                except Exception:
                    st.info("Sección de acuerdos internos no disponible.")
                    render_internos = lambda: None
                render_internos()
            with tab_ext:
                try:
                    from secciones.acuerdos_externos import render as render_externos
                except Exception:
                    st.info("Sección de acuerdos externos no disponible.")
                    render_externos = lambda: None
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
