import uuid
import re
import streamlit as st
import pandas as pd
import datetime as dt
from zoneinfo import ZoneInfo
import gspread
from google.oauth2.service_account import Credentials

# =========================
# Configuración general
# =========================
STGO = ZoneInfo("America/Santiago")
SPREADSHEET_KEY = "1C8njkp0RQMdXnxuJvPvfK_pNZHQSi7q7dUPeUg-2624"
HOJA = "finanzas"

AUCCANES = ["🚴🏻Chalo", "🌿Camilú", "⚽Niko", "🍃Diego", "🪈Francis", "🌌Tais", "🌊Cala"]

# =========================
# Helpers de conexión
# =========================
def _a1_range_row(row: int, ncols: int) -> str:
    last_cell = gspread.utils.rowcol_to_a1(row, ncols)
    last_col = re.sub(r"\d+", "", last_cell)
    return f"A{row}:{last_col}{row}"

def _open_ws(sheet_name=HOJA):
    creds = Credentials.from_service_account_info(
        st.secrets["gspread"],
        scopes=["https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"],
    )
    client = gspread.authorize(creds)
    sh = client.open_by_key(SPREADSHEET_KEY)
    return sh.worksheet(sheet_name)

EXPECTED_HEADERS = [
    "ID","Tipo","Detalle","Categoría","Fecha","Persona",
    "Persona_Origen","Persona_Destino","Monto",
    "Created_At","Created_By","Last_Modified_At","Last_Modified_By","Anulado"
]

def _ensure_sheet_headers(ws) -> list[str]:
    headers_raw = ws.row_values(1)
    headers = [h.strip() for h in headers_raw]
    missing = [h for h in EXPECTED_HEADERS if h not in headers]
    if missing:
        new_headers = headers + missing
        ws.update(_a1_range_row(1, len(new_headers)), [new_headers])
        return new_headers
    return headers

# =========================
# Normalización de datos
# =========================
def _parse_monto_raw(x) -> int:
    if pd.isna(x): return 0
    s = str(x).replace("$", "").replace(".", "").replace(",", "").strip()
    return abs(int(float(s))) if s else 0

def _parse_fecha_any(s) -> pd.Timestamp:
    s = str(s).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    return pd.to_datetime(s, dayfirst=True, errors="coerce")

def _load_finanzas_df() -> pd.DataFrame:
    try:
        ws = _open_ws(HOJA)
        headers = _ensure_sheet_headers(ws)
        values = ws.get_all_values()
    except Exception as e:
        st.error(f"No se pudo leer la hoja '{HOJA}': {e}")
        return pd.DataFrame(columns=EXPECTED_HEADERS)
    if not values: return pd.DataFrame(columns=EXPECTED_HEADERS)
    rows = values[1:]
    norm_rows = [r[:len(headers)] + [""] * max(0, len(headers)-len(r)) for r in rows]
    df = pd.DataFrame(norm_rows, columns=headers)
    return df

def _normalize_finanzas(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw is None or df_raw.empty:
        return pd.DataFrame(columns=EXPECTED_HEADERS)

    df = df_raw.copy()
    for c in ["Tipo","Detalle","Categoría","Persona","Persona_Origen","Persona_Destino"]:
        df[c] = df[c].astype(str).str.strip()

    df["Fecha_dt"] = df["Fecha"].apply(_parse_fecha_any)
    df["Monto_int"] = df["Monto"].apply(_parse_monto_raw)
    df["Anulado_bool"] = df["Anulado"].astype(str).str.lower().isin(["true","1","sí","si","yes","y"])
    if "_row" not in df.columns:
        df["_row"] = range(2, 2+len(df))
    return df

# =========================
# Lógica log1
# =========================
def _calc_saldos_por_persona(df: pd.DataFrame) -> pd.DataFrame:
    df_ok = df[~df["Anulado_bool"]].copy()
    saldos = []
    for persona in AUCCANES:
        ingresos = df_ok[(df_ok["Tipo"]=="Ingreso") & (df_ok["Persona"]==persona)]["Monto_int"].sum()
        gastos = df_ok[(df_ok["Tipo"]=="Gasto") & (df_ok["Persona"]==persona)]["Monto_int"].sum()
        t_recib = df_ok[(df_ok["Tipo"]=="Traspaso") & (df_ok["Persona_Destino"]==persona)]["Monto_int"].sum()
        t_entreg = df_ok[(df_ok["Tipo"]=="Traspaso") & (df_ok["Persona_Origen"]==persona)]["Monto_int"].sum()
        saldo = ingresos + t_recib - gastos - t_entreg
        saldos.append({"Persona": persona, "Saldo": saldo,
                       "Ingresos": ingresos, "Gastos": gastos,
                       "Traspasos_Recibidos": t_recib, "Traspasos_Entregados": t_entreg})
    return pd.DataFrame(saldos)

def _calc_total_aucca(df: pd.DataFrame) -> int:
    saldos = _calc_saldos_por_persona(df)
    return int(saldos["Saldo"].sum())


# =========================
# Helpers de formato
# =========================

MESES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

MESES_CORTO_ES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"
}

def _clp(val: int) -> str:
    try:
        return f"$ {int(val):,}".replace(",", ".")
    except:
        return str(val)

def _mes_options() -> list[str]:
    """Genera lista de los últimos 24 meses como strings 'YYYY-MM', más reciente primero."""
    hoy = dt.date.today()
    anio, mes = hoy.year, hoy.month
    meses = []
    for _ in range(24):
        meses.append(f"{anio:04d}-{mes:02d}")
        mes -= 1
        if mes == 0:
            mes = 12
            anio -= 1
    return meses

def _mes_match(fecha_dt_series, mes_ym: str):
    """Filtra Timestamps por año-mes. Robusto frente a NaT (no usa strftime)."""
    try:
        anio, mes = int(mes_ym[:4]), int(mes_ym[5:7])
        validos = fecha_dt_series.notna()
        return validos & (fecha_dt_series.dt.year == anio) & (fecha_dt_series.dt.month == mes)
    except Exception:
        import pandas as pd
        return pd.Series(False, index=fecha_dt_series.index)

def _label_mes(ym: str) -> str:
    try:
        anio, mes = int(ym[:4]), int(ym[5:7])
        label = f"{MESES_ES[mes]} {anio}"
        if ym == dt.date.today().strftime("%Y-%m"):
            label += " (actual)"
        return label
    except:
        return ym


# =========================
# Estadísticas — Estado Actual
# =========================
def _render_estado_actual(df: pd.DataFrame):
    hoy = dt.date.today()
    mes_actual_str = hoy.strftime("%Y-%m")

    df_ok = df[~df["Anulado_bool"]].copy()

    # Selector de mes con label legible
    meses_raw = _mes_options()
    meses_labels = [_label_mes(m) for m in meses_raw]
    idx_actual = meses_raw.index(mes_actual_str) if mes_actual_str in meses_raw else 0

    col_sel, _ = st.columns([2, 3])
    with col_sel:
        mes_sel_label = st.selectbox(
            "📅 Ver métricas del mes",
            meses_labels,
            index=idx_actual,
            key="mes_sel_estado"
        )
    mes_sel = meses_raw[meses_labels.index(mes_sel_label)]

    # Filtrar por mes seleccionado — usar apply explícito, el más robusto frente a NaT
    def _to_ym(ts):
        try:
            if pd.isna(ts): return ""
            return f"{ts.year:04d}-{ts.month:02d}"
        except: return ""
    df_ok["_ym"] = df_ok["Fecha_dt"].apply(_to_ym)
    df_mes = df_ok[df_ok["_ym"] == mes_sel]

    # Calcular valores
    total_aucca     = _calc_total_aucca(df)
    ing_total       = df_ok[df_ok["Tipo"] == "Ingreso"]["Monto_int"].sum()
    gasto_total     = df_ok[df_ok["Tipo"] == "Gasto"]["Monto_int"].sum()
    tras_total      = len(df_ok[df_ok["Tipo"] == "Traspaso"])

    ing_mes         = df_mes[df_mes["Tipo"] == "Ingreso"]["Monto_int"].sum()
    gasto_mes       = df_mes[df_mes["Tipo"] == "Gasto"]["Monto_int"].sum()
    tras_mes        = len(df_mes[df_mes["Tipo"] == "Traspaso"])

    # ── Métrica principal ──
    st.markdown("---")
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #9D7FEA 0%, #7B4F9E 100%);
            border: 1px solid #CDB4FF;
            border-radius: 16px;
            padding: 24px 32px;
            text-align: center;
            margin-bottom: 20px;
            box-shadow: 0 8px 24px rgba(123, 79, 158, 0.2);
        ">
            <div style="color:#E6D9FF; font-size:13px; font-weight:600; letter-spacing:2px; text-transform:uppercase; margin-bottom:6px;">
                DINERO TOTAL DISPONIBLE
            </div>
            <div style="color:#FFFFFF; font-size:42px; font-weight:800; letter-spacing:-1px;">
                {_clp(total_aucca)}
            </div>
            <div style="color:#E6D9FF; font-size:12px; margin-top:6px; font-weight: 500;">¡VAMOS QUE SE PUEDE!</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # ── Métricas por sección ──
    st.markdown(f"##### 📊 Período: {_label_mes(mes_sel)}")

    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.markdown("**Ingresos**")
            st.metric("Total histórico", _clp(ing_total))
            st.metric(f"Mes seleccionado", _clp(ing_mes))
    with c2:
        with st.container(border=True):
            st.markdown("**Gastos**")
            st.metric("Total histórico", _clp(gasto_total))
            st.metric(f"Mes seleccionado", _clp(gasto_mes))
    with c3:
        with st.container(border=True):
            st.markdown("**🔄 Traspasos**")
            st.metric("Total histórico", tras_total)
            st.metric(f"Mes seleccionado", tras_mes)

    # ── Saldos por persona ──
    st.markdown("---")
    st.markdown("#### 👥 Saldos por persona")
    saldos = _calc_saldos_por_persona(df)
    saldos_view = saldos.copy().set_index("Persona")
    for col in saldos_view.columns:
        saldos_view[col] = saldos_view[col].apply(_clp)
    st.dataframe(saldos_view, use_container_width=True)

    # ── Tabla de registros ──
    st.markdown("---")
    st.markdown("#### 📋 Detalle de registros")
    st.info(
        "**Fecha del movimiento** → la fecha real del ingreso o gasto (ej: cuándo se pagó algo). "
        "**Fecha de registro** → cuándo se ingresó ese dato al sistema. "
        "La tabla está ordenada por fecha de registro más reciente, "
        "así los últimos movimientos anotados aparecen siempre primero, "
        "independiente de cuándo ocurrieron.",
        icon="ℹ️"
    )

    with st.expander("🔍 Filtros", expanded=False):
        cf1, cf2, cf3, cf4 = st.columns(4)
        with cf1:
            filtro_persona = st.selectbox("Persona", ["Todos"] + AUCCANES, key="det_persona")
        with cf2:
            filtro_tipo = st.selectbox("Tipo", ["Todos", "Ingreso", "Gasto", "Traspaso"], key="det_tipo")
        with cf3:
            filtro_mes_det = st.selectbox(
                "Mes (fecha del mov.)",
                ["Todos"] + [_label_mes(m) for m in _mes_options()],
                key="det_mes"
            )
        with cf4:
            mostrar_anulados = st.toggle("Mostrar anulados", value=False, key="det_anulados")

    # Parsear Created_At y Last_Modified_At para ordenar
    df_det = df.copy()
    df_det["_created_dt"] = pd.to_datetime(df_det["Created_At"], errors="coerce")
    df_det["_modified_dt"] = pd.to_datetime(df_det["Last_Modified_At"], errors="coerce")
    # Fecha de última actividad = la más reciente entre created y modified
    df_det["_actividad_dt"] = df_det[["_created_dt", "_modified_dt"]].max(axis=1)

    if not mostrar_anulados:
        df_det = df_det[~df_det["Anulado_bool"]]
    if filtro_persona != "Todos":
        df_det = df_det[
            (df_det["Persona"] == filtro_persona) |
            (df_det["Persona_Origen"] == filtro_persona) |
            (df_det["Persona_Destino"] == filtro_persona)
        ]
    if filtro_tipo != "Todos":
        df_det = df_det[df_det["Tipo"] == filtro_tipo]
    if filtro_mes_det != "Todos":
        meses_raw_det = _mes_options()
        meses_labels_det = [_label_mes(m) for m in meses_raw_det]
        if filtro_mes_det in meses_labels_det:
            mes_key = meses_raw_det[meses_labels_det.index(filtro_mes_det)]
            def _to_ym2(ts):
                try:
                    if pd.isna(ts): return ""
                    return f"{ts.year:04d}-{ts.month:02d}"
                except: return ""
            df_det["_ym2"] = df_det["Fecha_dt"].apply(_to_ym2)
            df_det = df_det[df_det["_ym2"] == mes_key]

    # Ordenar: primero los que tienen _actividad_dt más reciente (nulls al final)
    df_det = df_det.sort_values("_actividad_dt", ascending=False, na_position="last")

    def _quien(row):
        if row["Tipo"] == "Traspaso":
            return f"{row['Persona_Origen']} → {row['Persona_Destino']}"
        return row["Persona"]

    df_show = df_det.copy()
    df_show["Quién"] = df_show.apply(_quien, axis=1)
    df_show["Monto"] = df_show["Monto_int"].apply(_clp)
    # Columnas de fechas con nombres claros
    def _fmt_ts(ts):
        try:
            if pd.isna(ts): return "—"
            return ts.strftime("%d/%m/%Y %H:%M")
        except: return "—"

    df_show["F. del Movimiento"] = df_show["Fecha"]
    df_show["F. de Registro"] = df_show["_created_dt"].apply(_fmt_ts)
    df_show["Ult. Modificacion"] = df_show["_modified_dt"].apply(_fmt_ts)
    df_show["Anulado"] = df_show["Anulado_bool"]

    columnas_show = [
        "F. de Registro",
        "F. del Movimiento",
        "Tipo", "Quien", "Categoria", "Monto", "Detalle",
        "Ult. Modificacion",
        "Anulado",
    ]
    # Renombrar columnas sin tildes para evitar problemas de encoding en dataframe
    df_show = df_show.rename(columns={"Quién": "Quien", "Categoría": "Categoria"})
    st.dataframe(
        df_show[columnas_show],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Anulado": st.column_config.CheckboxColumn("Anulado", width="small"),
            "F. de Registro": st.column_config.TextColumn("📥 F. de Registro", width="medium"),
            "F. del Movimiento": st.column_config.TextColumn("📅 F. del Movimiento", width="medium"),
            "Ult. Modificacion": st.column_config.TextColumn("✏️ Modificado", width="medium"),
            "Monto": st.column_config.TextColumn("Monto", width="medium"),
            "Quien": st.column_config.TextColumn("Quién"),
            "Categoria": st.column_config.TextColumn("Categoría"),
        }
    )


# =========================
# Estadísticas — Histórico (gráficos)
# =========================
def _render_historico(df: pd.DataFrame):
    import altair as alt
    from itertools import product as iproduct

    hoy = pd.Timestamp.now()
    inicio = (hoy - pd.DateOffset(months=11)).replace(day=1)
    
    todos_meses = pd.date_range(start=inicio, periods=12, freq="MS")
    orden_meses = [f"{MESES_CORTO_ES[m.month]} {m.year}" for m in todos_meses]

    df_ok = df[~df["Anulado_bool"] & df["Tipo"].isin(["Ingreso", "Gasto"])].copy()
    df_ok = df_ok[df_ok["Fecha_dt"].notna() & (df_ok["Fecha_dt"] >= inicio)]
    
    def _get_mes_str(d):
        try: return f"{MESES_CORTO_ES[d.month]} {d.year}"
        except: return ""

    df_ok["mes_str"] = df_ok["Fecha_dt"].apply(_get_mes_str)

    # ── Gráfico 1: Ingresos vs Gastos ──
    st.markdown("#### 📊 Ingresos vs Gastos — últimos 12 meses")

    resumen = df_ok.groupby(["mes_str", "Tipo"])["Monto_int"].sum().reset_index()
    base_ig = pd.DataFrame(list(iproduct(orden_meses, ["Ingreso", "Gasto"])), columns=["mes_str", "Tipo"])
    resumen_full = base_ig.merge(resumen, on=["mes_str", "Tipo"], how="left").fillna(0)

    chart1 = (
        alt.Chart(resumen_full)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("mes_str:O", sort=orden_meses, title=None, axis=alt.Axis(labelAngle=-40)),
            y=alt.Y("Monto_int:Q", title="CLP", axis=alt.Axis(format="~s")),
            color=alt.Color(
                "Tipo:N",
                scale=alt.Scale(domain=["Ingreso", "Gasto"], range=["#48bb78", "#fc8181"]),
                legend=alt.Legend(title=None, orient="top")
            ),
            xOffset="Tipo:N",
            tooltip=[
                alt.Tooltip("mes_str:O", title="Mes"),
                alt.Tooltip("Tipo:N"),
                alt.Tooltip("Monto_int:Q", title="Monto (CLP)", format=","),
            ],
        )
        .properties(height=300)
    )
    st.altair_chart(chart1, use_container_width=True)

    # ── Gráfico 2: Balance mensual (neto) ──
    st.markdown("#### 💹 Balance neto mensual")

    pivot = resumen_full.pivot(index="mes_str", columns="Tipo", values="Monto_int").reset_index()
    pivot.columns.name = None
    for c in ["Ingreso", "Gasto"]:
        if c not in pivot.columns: pivot[c] = 0
    pivot["Neto"] = pivot["Ingreso"] - pivot["Gasto"]
    pivot["Color"] = pivot["Neto"].apply(lambda v: "Superávit" if v >= 0 else "Déficit")
    # mantener orden
    pivot["_orden"] = pivot["mes_str"].apply(lambda m: orden_meses.index(m) if m in orden_meses else 99)
    pivot = pivot.sort_values("_orden")

    chart2 = (
        alt.Chart(pivot)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("mes_str:O", sort=orden_meses, title=None, axis=alt.Axis(labelAngle=-40)),
            y=alt.Y("Neto:Q", title="CLP", axis=alt.Axis(format="~s")),
            color=alt.Color(
                "Color:N",
                scale=alt.Scale(domain=["Superávit", "Déficit"], range=["#63b3ed", "#fc8181"]),
                legend=alt.Legend(title=None, orient="top")
            ),
            tooltip=[
                alt.Tooltip("mes_str:O", title="Mes"),
                alt.Tooltip("Neto:Q", title="Balance (CLP)", format=","),
            ],
        )
        .properties(height=260)
    )
    st.altair_chart(chart2, use_container_width=True)

    # ── Gráfico 3: Gastos por categoría ──
    st.markdown("#### 🏷️ Gastos por categoría — últimos 12 meses")

    df_cat = df_ok[df_ok["Tipo"] == "Gasto"].copy()
    df_cat = df_cat[df_cat["Categoría"].str.strip() != ""]

    if df_cat.empty:
        st.info("Sin gastos con categoría en los últimos 12 meses.")
        return

    top_cats = df_cat.groupby("Categoría")["Monto_int"].sum().nlargest(10).index.tolist()
    df_cat_top = df_cat[df_cat["Categoría"].isin(top_cats)].copy()
    resumen_cat = df_cat_top.groupby(["mes_str", "Categoría"])["Monto_int"].sum().reset_index()
    base_cat = pd.DataFrame(list(iproduct(orden_meses, top_cats)), columns=["mes_str", "Categoría"])
    resumen_cat_full = base_cat.merge(resumen_cat, on=["mes_str", "Categoría"], how="left").fillna(0)

    chart3 = (
        alt.Chart(resumen_cat_full)
        .mark_bar()
        .encode(
            x=alt.X("mes_str:O", sort=orden_meses, title=None, axis=alt.Axis(labelAngle=-40)),
            y=alt.Y("Monto_int:Q", title="CLP", axis=alt.Axis(format="~s")),
            color=alt.Color("Categoría:N", legend=alt.Legend(title=None, orient="top")),
            order=alt.Order("Monto_int:Q", sort="descending"),
            tooltip=[
                alt.Tooltip("mes_str:O", title="Mes"),
                alt.Tooltip("Categoría:N"),
                alt.Tooltip("Monto_int:Q", title="Monto (CLP)", format=","),
            ],
        )
        .properties(height=300)
    )
    st.altair_chart(chart3, use_container_width=True)


# =========================
# Formularios
# =========================

def _form_traspaso():
    """Formulario para registrar traspasos"""
    with st.container(border=True):
        st.markdown("#### 🔄 Detalles de la Transferencia")
        with st.form("form_traspaso", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                origen = st.selectbox("📤 Persona que entrega", [""]+AUCCANES)
                monto = st.number_input("💰 Monto (CLP)", min_value=0, step=100)
            with col2:
                destino = st.selectbox("📥 Persona que recibe", [""]+AUCCANES)
                fecha = st.date_input("🗓️ Fecha", value=dt.date.today(), max_value=dt.date.today())
            
            detalle = st.text_input("📝 Motivo o Detalle (obligatorio)", "")
            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button("🚀 Registrar traspaso", type="primary", use_container_width=True)

            if submit and origen and destino and monto>0 and len(detalle.strip())>=5 and origen!=destino:
                now = pd.Timestamp.now(tz=STGO)
                record = {
                    "ID": str(uuid.uuid4()),
                    "Tipo": "Traspaso",
                    "Detalle": detalle.strip(),
                    "Categoría": "",
                    "Fecha": fecha.strftime("%Y-%m-%d"),
                    "Persona": "",
                    "Persona_Origen": origen,
                    "Persona_Destino": destino,
                    "Monto": str(int(monto)),
                    "Created_At": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "Created_By": origen,
                    "Last_Modified_At": "",
                    "Last_Modified_By": "",
                    "Anulado": ""
                }
                ws = _open_ws(HOJA)
                headers = _ensure_sheet_headers(ws)
                row_out = [record.get(h,"") for h in headers]
                ws.append_row(row_out, value_input_option="USER_ENTERED")
                st.success(f"🔄 Traspaso {origen} → {destino} registrado")
           

def _form_registro(cats_existentes: list[str]):
    """Selector de tipo y despliegue del formulario correspondiente"""
    st.markdown("### ➕ Registrar Nuevo Movimiento")
    try:
        tipo_sel = st.pills("Selecciona tipo de movimiento", ["Ingreso","Gasto","Traspaso"], default="Ingreso")
        if not tipo_sel: tipo_sel = "Ingreso"
    except AttributeError:
        tipo_sel = st.radio("Selecciona tipo de movimiento", ["Ingreso","Gasto","Traspaso"], horizontal=True)

    if tipo_sel in ["Ingreso","Gasto"]:
        _form_ingreso_gasto(tipo_sel, cats_existentes)
    elif tipo_sel=="Traspaso":
        _form_traspaso()


def _form_editar_anular(df: pd.DataFrame):
    st.markdown("### ✏️ Selector para Edición")
    if df.empty:
        st.caption("No hay movimientos para editar o anular.")
        return

    with st.container(border=True):
        incluir_anulados = st.toggle("🔍 Mostrar movimientos anulados", value=False)
        df_view = df if incluir_anulados else df[~df["Anulado_bool"]]
        df_view = df_view.sort_values("Fecha_dt", ascending=False).copy()

        if df_view.empty:
            st.caption("No hay movimientos disponibles con el filtro actual.")
            return

        df_view["Opción"] = df_view.apply(
            lambda r: f"{r['Fecha']} | {r['Tipo']} | "
                      f"{r['Persona'] or (r['Persona_Origen']+'→'+r['Persona_Destino'])} | "
                      f"{r['Monto_int']} | {r['Detalle'][:30]}"
                      + (" (ANULADO)" if r["Anulado_bool"] else ""),
            axis=1
        )

        opcion = st.selectbox("Movimiento histórico", [""] + df_view["Opción"].tolist())
        if not opcion:
            return

        row = df_view[df_view["Opción"] == opcion].iloc[0]
        tipo = row["Tipo"]

        # Inicializar categoria_activa_edit en session_state
        if "categoria_activa_edit" not in st.session_state:
            st.session_state["categoria_activa_edit"] = row["Categoría"]

        def _on_edit_cat_sel():
            val = st.session_state.get("edit_cat_exist", "")
            if val:
                st.session_state["categoria_activa_edit"] = val

        def _on_edit_cat_nueva():
            val = st.session_state.get("edit_txt_new_cat", "").strip()
            if val:
                st.session_state["categoria_activa_edit"] = val

        st.markdown("---")
        st.markdown(f"#### 🛠️ Editando registro actual")

        # --- Selector de categoría (solo para Ingreso/Gasto) ---
        if tipo in ["Ingreso","Gasto"]:
            col1, col2 = st.columns([3,1])
            with col1:
                cats_existentes = sorted({c for c in df["Categoría"].unique() if str(c).strip()})
                idx_edit = (cats_existentes.index(row["Categoría"]) + 1) if row["Categoría"] in cats_existentes else 0
                st.selectbox(
                    "📂 Categoría",
                    [""] + cats_existentes,
                    index=idx_edit,
                    key="edit_cat_exist",
                    on_change=_on_edit_cat_sel,
                )
            with col2:
                st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
                try:
                    with st.popover("➕ Nueva", use_container_width=True):
                        st.text_input("Nombre de etiqueta rápida", key="edit_txt_new_cat", on_change=_on_edit_cat_nueva)
                except AttributeError:
                    st.text_input("➕ Nueva etiqueta", key="edit_txt_new_cat", on_change=_on_edit_cat_nueva)

            # Mostrar categoría activa actual
            if st.session_state.get("categoria_activa_edit"):
                st.info(f"📌 Categoría asignada: **{st.session_state['categoria_activa_edit']}**")

        # --- Formulario principal ---
        with st.form("form_editar"):
            fecha_val = row["Fecha_dt"].date() if pd.notnull(row["Fecha_dt"]) else dt.date.today()
            
            # Tipo editable solo para ingresos/gastos
            if tipo in ["Ingreso","Gasto"]:
                tipo_editado = st.selectbox("📄 Tipo", ["Ingreso","Gasto"], index=0 if tipo=="Ingreso" else 1, key="edit_tipo")
                colA, colB = st.columns(2)
                with colA:
                    fecha = st.date_input("🗓️ Fecha", value=fecha_val, max_value=max(fecha_val, dt.date.today()))
                    persona = st.selectbox("👤 Persona", AUCCANES, index=AUCCANES.index(row["Persona"]) if row["Persona"] in AUCCANES else 0, key="edit_persona")
                with colB:
                    monto = st.number_input("💰 Monto (CLP)", min_value=0, step=100, value=int(row["Monto_int"]), key="edit_monto")
                    detalle = st.text_input("📝 Detalle", row["Detalle"], key="edit_detalle")

            elif tipo == "Traspaso":
                st.caption("Tipo: Traspaso (no editable en tipo)")
                tipo_editado = "Traspaso"
                col1, col2 = st.columns(2)
                with col1:
                    origen = st.selectbox("📤 Entrega", AUCCANES, index=AUCCANES.index(row["Persona_Origen"]) if row["Persona_Origen"] in AUCCANES else 0, key="edit_origen")
                    monto = st.number_input("💰 Monto (CLP)", min_value=0, step=100, value=int(row["Monto_int"]), key="edit_monto_t")
                with col2:
                    destino = st.selectbox("📥 Recibe", AUCCANES, index=AUCCANES.index(row["Persona_Destino"]) if row["Persona_Destino"] in AUCCANES else 0, key="edit_destino")
                    fecha = st.date_input("🗓️ Fecha", value=fecha_val, max_value=max(fecha_val, dt.date.today()))
                
                detalle = st.text_input("📝 Detalle", row["Detalle"], key="edit_detalle_t")

            st.markdown("---")
            editor = st.selectbox("🕵️‍♂️ ¿Quién autoriza los cambios?", [""] + AUCCANES, key="edit_editor")
            
            st.markdown("<br>", unsafe_allow_html=True)
            colX, colY = st.columns(2)
            with colX:
                guardar = st.form_submit_button("💾 Guardar edición", type="primary", use_container_width=True)
            with colY:
                anular = st.form_submit_button("🗑️ Anular acción", use_container_width=True)

    # --- Guardar / Anular ---
    if (guardar or anular) and not editor:
        st.error("Debes indicar quién realiza la edición/anulación.")
        return

    if guardar or anular:
        ws = _open_ws(HOJA)
        headers = _ensure_sheet_headers(ws)
        rownum = int(row["_row"])
        valores = row.to_dict()

        if anular:
            valores["Anulado"] = "TRUE"
        else:
            valores["Fecha"] = fecha.strftime("%Y-%m-%d")
            valores["Detalle"] = detalle.strip()
            valores["Monto"] = str(int(monto))

            if tipo_editado in ["Ingreso","Gasto"]:
                valores["Tipo"] = tipo_editado
                valores["Persona"] = persona
                valores["Categoría"] = st.session_state["categoria_activa_edit"].strip()
            elif tipo_editado == "Traspaso":
                valores["Persona_Origen"] = origen
                valores["Persona_Destino"] = destino

            now = pd.Timestamp.now(tz=STGO)
            valores["Last_Modified_At"] = now.strftime("%Y-%m-%d %H:%M:%S")
            valores["Last_Modified_By"] = editor

        row_out = [valores.get(h,"") for h in headers]
        ws.update(_a1_range_row(rownum, len(headers)), [row_out], value_input_option="USER_ENTERED")

        if anular:
            st.success(f"🗑️ Movimiento anulado por {editor}.")
        else:
            st.success(f"✅ Cambios guardados por {editor}.")
        st.rerun()
       

def _form_ingreso_gasto(tipo: str, cats_existentes: list[str]):
    """Formulario para registrar ingresos o gastos"""
    key_cat = f"categoria_activa_{tipo}"
    if key_cat not in st.session_state:
        st.session_state[key_cat] = ""

    def _on_cat_sel():
        val = st.session_state.get(f"cat_exist_{tipo}", "")
        if val:
            st.session_state[key_cat] = val

    def _on_cat_nueva():
        val = st.session_state.get(f"txt_new_cat_{tipo}", "").strip()
        if val:
            st.session_state[key_cat] = val

    with st.container(border=True):
        st.markdown(f"#### 📂 Etiquetado de {tipo}")

        col1, col2 = st.columns([3,1])
        with col1:
            st.selectbox(
                "Tópico general",
                [""] + sorted({c for c in cats_existentes if c}),
                index=0,
                key=f"cat_exist_{tipo}",
                on_change=_on_cat_sel,
            )
        with col2:
            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
            try:
                with st.popover("➕ Crear", use_container_width=True):
                    st.text_input("Nombre descriptivo", key=f"txt_new_cat_{tipo}", on_change=_on_cat_nueva)
            except AttributeError:
                st.text_input("➕ Nueva", key=f"txt_new_cat_{tipo}", on_change=_on_cat_nueva)

        # Mostrar categoría activa actual
        if st.session_state[key_cat]:
            st.success(f"📌 Etiqueta activa: **{st.session_state[key_cat]}**")

        st.markdown("---")

        # Formulario principal
        with st.form(f"form_{tipo.lower()}", clear_on_submit=True):
            colA, colB = st.columns(2)
            with colA:
                fecha = st.date_input("🗓️ Fecha de caja", value=dt.date.today(), max_value=dt.date.today())
                persona = st.selectbox("👤 Persona responsable", [""]+AUCCANES, key=f"persona_{tipo}")
            with colB:
                monto = st.number_input("💰 Monto (CLP)", min_value=0, step=100, key=f"monto_{tipo}")
                detalle = st.text_input("📝 Comentario (Mín. 5 letras)", "", key=f"detalle_{tipo}")

            st.markdown("<br>", unsafe_allow_html=True)
            submit = st.form_submit_button(f"🚀 Procesar {tipo}", type="primary", use_container_width=True)
            
            if submit:
                categoria_final = st.session_state.get(key_cat, "").strip()
                if persona and categoria_final and monto > 0 and len(detalle.strip()) >= 5:
                    now = pd.Timestamp.now(tz=STGO)
                    record = {
                        "ID": str(uuid.uuid4()),
                        "Tipo": tipo,
                        "Detalle": detalle.strip(),
                        "Categoría": categoria_final,
                        "Fecha": fecha.strftime("%Y-%m-%d"),
                        "Persona": persona,
                        "Persona_Origen": "",
                        "Persona_Destino": "",
                        "Monto": str(int(monto)),
                        "Created_At": now.strftime("%Y-%m-%d %H:%M:%S"),
                        "Created_By": persona,
                        "Last_Modified_At": "",
                        "Last_Modified_By": "",
                        "Anulado": ""
                    }
                    ws = _open_ws(HOJA)
                    headers = _ensure_sheet_headers(ws)
                    row_out = [record.get(h,"") for h in headers]
                    ws.append_row(row_out, value_input_option="USER_ENTERED")
                    st.success(f"✅ {tipo} registrado correctamente.")
                    st.session_state[key_cat] = ""  # reset después de guardar
                else:
                    st.error("⚠️ Debes completar todos los campos obligatorios y asignar una etiqueta.")


# =========================
# Render principal
# =========================
def render():
    col1, col2 = st.columns([3,1])
    with col1:
        st.markdown("## Finanzas")
    with col2:
        if st.button("🔄 Actualizar BD", key="actualizardb"):
            st.cache_data.clear()
            try: st.cache_resource.clear()
            except: pass
            st.success("BD actualizada ✅")
            st.rerun()

    df_raw = _load_finanzas_df()
    df = _normalize_finanzas(df_raw)
    cats_existentes = sorted(df["Categoría"].dropna().unique().tolist())

    tab_stats, tab_form = st.tabs(["📊 Estadísticas", "➕ Registrar / Editar"])

    # ── Tab Estadísticas ──
    with tab_stats:
        sub_actual, sub_historico = st.tabs(["📌 Estado Actual", "📈 Histórico"])

        with sub_actual:
            _render_estado_actual(df)

        with sub_historico:
            _render_historico(df)

    # ── Tab Registrar / Editar ──
    with tab_form:
        st.markdown("<br>", unsafe_allow_html=True)
        try:
            modo = st.pills("Selecciona modo de panel", ["Registrar", "Editar / Anular"], default="Registrar")
            if not modo: modo = "Registrar"
        except AttributeError:
            modo = st.radio("Selecciona modo", ["Registrar", "Editar / Anular"], horizontal=True)

        if modo == "Registrar":
            _form_registro(cats_existentes)
            if st.button("Agregar nuevo registro", key="actualizardb2"):
                st.cache_data.clear()
                try: st.cache_resource.clear()
                except: pass
                st.success("Ya puede proceder ✅")
                st.rerun()
        else:
            _form_editar_anular(df)
