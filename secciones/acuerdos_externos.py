# FILE: secciones/acuerdos_externos.py
import streamlit as st
import pandas as pd
from data.google import cargar_datos

# Paleta AUCCA
PALETTE = ["#FF37D5", "#112E4D", "#6FA7A6", "#9EAD6E", "#C46A3A", "#BCA27F", "#8C6F5C"]

def _tema_color(text: str) -> str:
    return PALETTE[abs(hash(text)) % len(PALETTE)]

def render():
    st.markdown("## 📣 Acuerdos de Comunicación Externa")

    # --- Cargar base ---
    try:
        df = cargar_datos("actuerdos_externos").rename(columns={
            "Acuerdo": "Tipo de acuerdo",
            "Aspecto": "Aspecto específico",
            "Detalle": "Detalle del acuerdo"
        })
    except Exception as e:
        st.error("No se pudo cargar la hoja 'acuerdos_externos'.")
        st.exception(e)
        return

    if df.empty:
        st.info("No hay acuerdos externos registrados.")
        return

    # --- Filtros en fila ---
    col1, col2 = st.columns([2, 3])
    with col1:
        tipos = sorted(df["Tipo de acuerdo"].dropna().unique().tolist())
        tipo = st.selectbox("Tipo de acuerdo", [""] + tipos)
    with col2:
        q = st.text_input("Buscar", placeholder="Palabra clave...")

    # --- Filtrado ---
    if tipo:
        subset = df[df["Tipo de acuerdo"] == tipo].copy()
    else:
        subset = df.copy()

    if q:
        q_low = q.lower()
        subset = subset[
            subset.apply(lambda r: q_low in f"{r['Aspecto específico']} {r['Detalle del acuerdo']}".lower(), axis=1)
        ]

    if subset.empty:
        st.warning("⚠️ No se encuentra nada con esos criterios.")
        return

    # --- Render ---
    if tipo:
        # Solo ese tipo (listado simple)
        for _, row in subset.iterrows():
            color = _tema_color(row["Tipo de acuerdo"])
            st.markdown(
                f"""
                <div style="background:#FAFAFA;
                            border-left:4px solid {color};
                            padding:6px 10px;
                            margin:4px 0;
                            border-radius:4px">
                    <div style="font-weight:600;font-size:0.95rem;color:#112E4D;">
                        {row['Aspecto específico']}
                    </div>
                    <div style="font-size:0.9rem;line-height:1.3;color:#333;">
                        {row['Detalle del acuerdo']}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        # Agrupado por tipo
        for t in tipos:
            dft = subset[subset["Tipo de acuerdo"] == t]
            if dft.empty:
                continue
            color = _tema_color(t)
            with st.expander(f"**{t}** ({len(dft)})", expanded=True):
                for _, row in dft.iterrows():
                    st.markdown(
                        f"""
                        <div style="background:#FAFAFA;
                                    border-left:4px solid {color};
                                    padding:6px 10px;
                                    margin:4px 0;
                                    border-radius:4px">
                            <div style="font-weight:600;font-size:0.95rem;color:#112E4D;">
                                {row['Aspecto específico']}
                            </div>
                            <div style="font-size:0.9rem;line-height:1.3;color:#333;">
                                {row['Detalle del acuerdo']}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
