# FILE: secciones/acuerdos_internos.py
import re
from difflib import SequenceMatcher
import streamlit as st
import pandas as pd
from data.google import cargar_datos


# -------------------------- Utilidades --------------------------

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Tema", "Número de orden", "Acuerdo"])
    df = df.rename(columns={
        "Tema": "Tema",
        "Orden": "Número de orden",
        "Número de orden": "Número de orden",
        "Acuerdo": "Acuerdo",
    })
    for c in ["Tema", "Número de orden", "Acuerdo"]:
        if c not in df.columns:
            df[c] = ""
    df["Tema"] = df["Tema"].astype(str).str.strip()
    df["Acuerdo"] = df["Acuerdo"].astype(str).str.strip()

    def _to_int(x):
        try:
            return int(float(str(x).strip()))
        except:
            return 10**9
    df["Número de orden"] = df["Número de orden"].apply(_to_int)
    return df


def _approx_contains(text: str, q: str, thr: float = 0.78) -> bool:
    if not q:
        return True
    s = (text or "").lower()
    ql = q.lower().strip()
    if ql in s:
        return True
    tokens = re.findall(r"\w+", s)
    for t in tokens:
        if SequenceMatcher(None, ql, t).ratio() >= thr:
            return True
    L = len(ql)
    if L >= 4 and len(s) >= L:
        for i in range(len(s) - L + 1):
            frag = s[i:i+L]
            if SequenceMatcher(None, ql, frag).ratio() >= thr:
                return True
    return False


def _highlight_html(text: str, query: str) -> str:
    if not query:
        return _emphasize_first_word_html(text)
    txt = text or ""
    txt_html = _emphasize_first_word_html(txt)
    toks = [t for t in re.findall(r"\w+", query, flags=re.I) if len(t) >= 3]
    for t in sorted(set(toks), key=len, reverse=True):
        pat = re.compile(rf"({re.escape(t)})", flags=re.I)
        txt_html = pat.sub(
            r'<span style="background:#FFF7CC;padding:0 2px;border-radius:3px">\1</span>',
            txt_html,
        )
    return txt_html


def _emphasize_first_word_html(text: str) -> str:
    if not text:
        return ""
    m = re.match(r"^\s*([^\s.,;:—\-]+)(.*)$", text, flags=re.UNICODE)
    if not m:
        return text
    first, rest = m.group(1), m.group(2)
    return f"<strong>{first}</strong>{rest}"


PALETTE = [
    "#FF37D5", "#112E4D", "#6FA7A6", "#9EAD6E", "#C46A3A", "#BCA27F", "#8C6F5C"
]

def _tema_color(tema: str) -> str:
    idx = abs(hash(tema)) % len(PALETTE)
    return PALETTE[idx]


# -------------------------- Render principal --------------------------

def render():
    st.markdown("## 🤝 Acuerdos de convivencia (internos)")

    try:
        df_raw = cargar_datos("acuerdos_internos")
    except Exception as e:
        st.error("No se pudo cargar la hoja 'acuerdos_internos'.")
        st.exception(e)
        return

    df = _normalize_df(df_raw)
    if df.empty:
        st.info("No hay acuerdos para mostrar.")
        return

    # --- Filtros ---
    st.markdown("### 🔍 Buscar y filtrar")
    q = st.text_input("Buscar", placeholder="Palabra o frase (tolerante a errores)")

    temas_all = sorted([t for t in df["Tema"].unique() if str(t).strip() != ""])
    sel = st.multiselect("Filtrar por tema", temas_all)
    temas_sel = sel if sel else temas_all

    # Aplicar búsqueda
    df["match"] = df.apply(
        lambda r: _approx_contains(f"{r['Tema']} {r['Acuerdo']}", q) if q else True,
        axis=1
    )

    # Filtrar global
    df_filtered = df[(df["Tema"].isin(temas_sel)) & (df["match"])]

    if df_filtered.empty:
        st.warning("⚠️ No se encuentra nada con esos criterios de búsqueda y filtro.")
        return

    # --- Render de temas ---
    for tema in temas_sel:
        dft = df_filtered[df_filtered["Tema"] == tema].sort_values("Número de orden")
        if dft.empty:
            st.caption(f"Sin coincidencias en el tema **{tema}**.")
            continue

        color = _tema_color(tema)
        with st.expander(f"**{tema}** ({len(dft)} acuerdos)", expanded=True):
            for _, r in dft.iterrows():
                st.markdown(
                    f"""
                    <div style="background:#FAFAFA;
                                border-left:6px solid {color};
                                padding:6px 10px;
                                margin:6px 0;
                                border-radius:6px">
                        {_highlight_html(r['Acuerdo'], q)}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
