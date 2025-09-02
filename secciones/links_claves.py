import streamlit as st
import datetime
from urllib.parse import urlparse
import pandas as pd

from data.google import cargar_datos
from utils.busqueda import approx_contains_text

def _parse_anio(x):
    try: return int(float(str(x).strip()))
    except: return None

MESES = {"enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
         "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,
         "noviembre":11,"diciembre":12}

def _parse_fecha_es(s):
    s = str(s).strip().lower()
    if not s: return None
    parts = s.replace("de ", "").split()
    try:
        if len(parts) >= 3:
            d = int(parts[0]); m = MESES.get(parts[1]); y = int(parts[2])
            if m: return datetime.datetime(y, m, d)
    except: pass
    return None

def _domain(u):
    try:
        d = urlparse(u).netloc
        return d.replace("www.", "")
    except:
        return ""

def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        "Petalo": "Pétalo", "Pétalo": "Pétalo",
        "Tema": "Tema",
        "Detalle": "Detalle",
        "Tipo": "Tipo",
        "Fecha creación": "Fecha creación", "Fecha creacion": "Fecha creación",
        "Año": "Año", "Anio": "Año",
        "Nombre": "Nombre",
        "Descripción": "Descripción", "Descripcion": "Descripción",
        "url": "URL", "Url": "URL", "URL": "URL",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    expected = ["Pétalo","Tema","Detalle","Tipo","Fecha creación","Año","Nombre","Descripción","URL"]
    for c in expected:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str).str.strip()
    df["Pétalo"] = df["Pétalo"].str.title()
    df["Año_int"] = df["Año"].apply(_parse_anio)
    df["Fecha_dt"] = df["Fecha creación"].apply(_parse_fecha_es)
    falta_fecha = df["Fecha_dt"].isna() & df["Año_int"].notna()
    df.loc[falta_fecha, "Fecha_dt"] = df.loc[falta_fecha, "Año_int"].apply(lambda y: datetime.datetime(y,1,1))
    df["Dominio"] = df["URL"].apply(_domain)
    return df

def _link_button(label, url):
    try:
        st.link_button(label, url, use_container_width=True)
    except Exception:
        st.markdown(f"[{label}]({url})")

def _render_card(row):
    nombre = row["Nombre"] or "(Sin nombre)"
    petalo = row["Pétalo"] or "—"
    tema = row["Tema"] or "—"
    detalle = row["Detalle"] or "—"
    tipo = row["Tipo"] or "—"
    anio = row["Año"] or ""
    dominio = row["Dominio"] or ""
    fecha_txt = ""
    if isinstance(row["Fecha_dt"], datetime.datetime):
        fecha_txt = row["Fecha_dt"].strftime("Creado el %d-%m-%Y")

    st.markdown(f"#### {nombre}")
    st.caption(f"{petalo} · {tema} · {detalle} · {tipo} · {anio}")
    if fecha_txt: st.caption(fecha_txt)
    if row["Descripción"]: st.markdown(row["Descripción"])
    if row["URL"]:
        _link_button("Abrir enlace", row["URL"])
        if dominio: st.caption(f"🌐 {dominio}")
    else:
        st.button("Sin URL", disabled=True, use_container_width=True)

def _render_cards_grid(df):
    df = df.reset_index(drop=True)
    for i in range(0, len(df), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j >= len(df): break
            with col: _render_card(df.iloc[i + j])

def render():
    st.subheader("🔗 Links claves")
    df = _normalize(cargar_datos("links"))

    c0, c1, c2, c3, c4 = st.columns([2, 2, 2, 2, 2])
    with c0:
        q = st.text_input("Buscar", placeholder="Nombre o descripción...")
    with c1:
        petalos = ["(Todos)"] + sorted([x for x in df["Pétalo"].unique() if x])
        f_petalo = st.selectbox("Pétalo", petalos, index=0)
    with c2:
        if f_petalo != "(Todos)":
            temas_opts = ["(Todos)"] + sorted([x for x in df.loc[df["Pétalo"] == f_petalo, "Tema"].unique() if x])
        else:
            temas_opts = ["(Todos)"] + sorted([x for x in df["Tema"].unique() if x])
        f_tema = st.selectbox("Tema", temas_opts, index=0)
    with c3:
        tipos_opts = sorted([x for x in df["Tipo"].unique() if x])
        f_tipos = st.multiselect("Tipo", tipos_opts, default=[])
    with c4:
        anos_opts = sorted([int(x) for x in df["Año_int"].dropna().unique()], reverse=True)
        f_anos = st.multiselect("Año", anos_opts, default=[])

    # filtros
    dff = df.copy()
    if q:
        ql = q.strip().lower()
        mask = dff.apply(lambda row: any(approx_contains_text(v, ql) for v in row.values), axis=1)
        dff = dff[mask]
    if f_petalo != "(Todos)":
        dff = dff[dff["Pétalo"] == f_petalo]
    if f_tema != "(Todos)":
        dff = dff[dff["Tema"] == f_tema]
    if f_tipos:
        dff = dff[dff["Tipo"].isin(f_tipos)]
    if f_anos:
        dff = dff[dff["Año_int"].isin(f_anos)]

    dff = dff.sort_values(["Fecha_dt", "Año_int", "Nombre"], ascending=[False, False, True], na_position="last")
    ver_todo = st.checkbox("📋 Ver todos (agrupados por Tema)", value=False)

    if dff.empty:
        st.info("No hay enlaces que coincidan con los filtros.")
    else:
        if ver_todo:
            for tema_val, grupo in dff.groupby("Tema"):
                st.subheader(f"🔸 {tema_val or '(Sin tema)'}")
                _render_cards_grid(grupo)
        else:
            _render_cards_grid(dff.head(60))