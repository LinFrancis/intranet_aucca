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
# Formularios
# =========================

def _form_traspaso():
    """Formulario para registrar traspasos"""
    with st.form("form_traspaso", clear_on_submit=True):
        fecha = st.date_input("Fecha", value=dt.date.today(), max_value=dt.date.today())
        col1,col2,col3 = st.columns(3)
        with col1: origen = st.selectbox("Persona que entrega", [""]+AUCCANES)
        with col2: destino = st.selectbox("Persona que recibe", [""]+AUCCANES)
        with col3: monto = st.number_input("Monto (CLP)", min_value=0, step=100)
        detalle = st.text_input("Detalle (obligatorio)", "")

        submit = st.form_submit_button("Registrar traspaso")
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
    st.markdown("### ➕ Registrar movimiento")
    tipo_sel = st.radio("Selecciona tipo de movimiento", ["Ingreso","Gasto","Traspaso"], horizontal=True)

    if tipo_sel in ["Ingreso","Gasto"]:
        _form_ingreso_gasto(tipo_sel, cats_existentes)
    elif tipo_sel=="Traspaso":
        _form_traspaso()


def _form_editar_anular(df: pd.DataFrame):
    st.markdown("### ✏️ Editar / Anular movimiento")
    if df.empty:
        st.caption("No hay movimientos para editar o anular.")
        return

    incluir_anulados = st.checkbox("🔍 Mostrar también movimientos anulados", value=False)
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

    opcion = st.selectbox("Selecciona un movimiento", [""] + df_view["Opción"].tolist())
    if not opcion:
        return

    row = df_view[df_view["Opción"] == opcion].iloc[0]
    tipo = row["Tipo"]

    # Inicializar categoria_activa_edit en session_state
    if "categoria_activa_edit" not in st.session_state:
        st.session_state["categoria_activa_edit"] = row["Categoría"]

    # --- Selector de categoría (solo para Ingreso/Gasto) ---
    if tipo in ["Ingreso","Gasto"]:
        st.markdown("#### Selección de categoría")
        col1, col2 = st.columns([2,1])
        with col1:
            cats_existentes = sorted({c for c in df["Categoría"].unique() if str(c).strip()})
            cat_sel = st.selectbox(
                "Categoría existente",
                [""] + cats_existentes,
                index=cats_existentes.index(row["Categoría"]) if row["Categoría"] in cats_existentes else 0,
                key="edit_cat_exist"
            )
            if cat_sel:
                st.session_state["categoria_activa_edit"] = cat_sel
        with col2:
            nueva_cat_btn = st.checkbox("➕ Nueva categoría", key="edit_btn_new_cat")

        if nueva_cat_btn:
            nueva = st.text_input(
                "Nombre nueva categoría",
                value=st.session_state.get("categoria_activa_edit", ""),
                key="edit_txt_new_cat"
            )
            if nueva:
                st.session_state["categoria_activa_edit"] = nueva

        # Mostrar categoría activa actual
        if st.session_state["categoria_activa_edit"]:
            st.info(f"📌 Categoría activa: **{st.session_state['categoria_activa_edit']}**")

    # --- Formulario principal ---
    with st.form("form_editar"):
        fecha = st.date_input("Fecha", value=row["Fecha_dt"].date(), max_value=dt.date.today())

        # Tipo editable solo para ingresos/gastos
        if tipo in ["Ingreso","Gasto"]:
            tipo_editado = st.selectbox("Tipo de movimiento", ["Ingreso","Gasto"],
                                        index=0 if tipo=="Ingreso" else 1, key="edit_tipo")
            persona = st.selectbox(
                "Persona", AUCCANES,
                index=AUCCANES.index(row["Persona"]) if row["Persona"] in AUCCANES else 0,
                key="edit_persona"
            )
            monto = st.number_input("Monto (CLP)", min_value=0, step=100,
                                    value=int(row["Monto_int"]), key="edit_monto")
            detalle = st.text_input("Detalle", row["Detalle"], key="edit_detalle")

        elif tipo == "Traspaso":
            st.caption("Tipo: Traspaso (no editable)")
            tipo_editado = "Traspaso"
            col1, col2, col3 = st.columns(3)
            with col1:
                origen = st.selectbox("Persona que entrega", AUCCANES,
                                      index=AUCCANES.index(row["Persona_Origen"]) if row["Persona_Origen"] in AUCCANES else 0,
                                      key="edit_origen")
            with col2:
                destino = st.selectbox("Persona que recibe", AUCCANES,
                                       index=AUCCANES.index(row["Persona_Destino"]) if row["Persona_Destino"] in AUCCANES else 0,
                                       key="edit_destino")
            with col3:
                monto = st.number_input("Monto (CLP)", min_value=0, step=100,
                                        value=int(row["Monto_int"]), key="edit_monto_t")
            detalle = st.text_input("Detalle", row["Detalle"], key="edit_detalle_t")

        editor = st.selectbox("¿Quién edita/anula?", [""] + AUCCANES, key="edit_editor")
        colA, colB = st.columns(2)
        with colA:
            guardar = st.form_submit_button("💾 Guardar cambios")
        with colB:
            anular = st.form_submit_button("🗑️ Anular movimiento")

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
    if "categoria_activa" not in st.session_state:
        st.session_state["categoria_activa"] = ""

    st.markdown("#### Selección de categoría")

    # Mostrar categoría activa actual
    if st.session_state["categoria_activa"]:
        st.info(f"📌 Categoría activa: **{st.session_state['categoria_activa']}**")

    col1, col2 = st.columns([2,1])
    with col1:
        cat_sel = st.selectbox("Categoría existente", [""]+sorted({c for c in cats_existentes if c}), 
                               index=0, key=f"cat_exist_{tipo}")
        if cat_sel:
            st.session_state["categoria_activa"] = cat_sel
    with col2:
        nueva_cat_btn = st.button("➕ Nueva categoría", key=f"btn_new_cat_{tipo}")

    if nueva_cat_btn or (st.session_state.get("modo_nueva_categoria") and tipo == st.session_state.get("modo_nueva_categoria")):
        st.session_state["modo_nueva_categoria"] = tipo
        nueva = st.text_input("Nombre nueva categoría", 
                              value=st.session_state.get("categoria_activa",""), 
                              key=f"txt_new_cat_{tipo}")
        if nueva:
            st.session_state["categoria_activa"] = nueva

    # Formulario principal
    with st.form(f"form_{tipo.lower()}", clear_on_submit=True):
        fecha = st.date_input("Fecha", value=dt.date.today(), max_value=dt.date.today())
        persona = st.selectbox("Persona", [""]+AUCCANES, key=f"persona_{tipo}")
        monto = st.number_input("Monto (CLP)", min_value=0, step=100, key=f"monto_{tipo}")
        detalle = st.text_input("Detalle", "", key=f"detalle_{tipo}")

        submit = st.form_submit_button(f"Registrar {tipo}")
        if submit:
            categoria_final = st.session_state["categoria_activa"].strip()
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
                st.success(f"✅ {tipo} registrado")
                st.session_state["categoria_activa"] = ""  # reset después de guardar
            else:
                st.error("⚠️ Debes completar todos los campos obligatorios.")


# =========================
# Render principal
# =========================
def render():
    col1,col2 = st.columns([3,1])
    with col1: st.markdown("## 💰 Finanzas AUCCA")
    with col2:
        if st.button("Actualizar base de datos", key = "actualizardb"):
            st.cache_data.clear()
            try: st.cache_resource.clear()
            except: pass
            st.success("BD actualizada ✅")
            st.rerun()

    df_raw = _load_finanzas_df()
    df = _normalize_finanzas(df_raw)
    cats_existentes = sorted(df["Categoría"].dropna().unique().tolist())

    tab_resumen, tab_form = st.tabs(["📊 Resumen","➕ Registrar / Editar"])

    with tab_resumen:
        total = _calc_total_aucca(df)
        ingresos = df[(df["Tipo"]=="Ingreso") & (~df["Anulado_bool"])]["Monto_int"].sum()
        gastos = df[(df["Tipo"]=="Gasto") & (~df["Anulado_bool"])]["Monto_int"].sum()
        n_traspasos = len(df[(df["Tipo"]=="Traspaso") & (~df["Anulado_bool"])])

        c1,c2,c3,c4 = st.columns(4)
        with c1: st.metric("Total AUCCA", f"$ {total:,}".replace(",",".")) 
        with c2: st.metric("Ingresos", f"$ {ingresos:,}".replace(",",".")) 
        with c3: st.metric("Gastos", f"$ {gastos:,}".replace(",",".")) 
        with c4: st.metric("Traspasos", f"{n_traspasos}")


        saldos = _calc_saldos_por_persona(df)
        
        st.markdown("#### Saldos actuales")
        st.dataframe(saldos.set_index("Persona"))

        st.markdown("#### Detalle Registros")
        # Filtros
        col1, col2, col3 = st.columns(3)
        with col1:
            persona_filtro = st.selectbox("Filtrar por persona", ["Todos"] + AUCCANES, key="filtro_persona")
        with col2:
            tipo_filtro = st.selectbox("Filtrar por tipo", ["Todos", "Ingreso", "Gasto", "Traspaso"], key="filtro_tipo")
        with col3:
            incluir_anulados = st.checkbox("Mostrar anulados", value=False, key="filtro_anulados")

        # Ordenar y limpiar columnas
        if "Fecha_dt" in df.columns:
            df = df.sort_values(by="Fecha_dt", ascending=False)

        # Aplicar filtros
        df_filtrado = df.copy()
        if persona_filtro != "Todos":
            df_filtrado = df_filtrado[
                (df_filtrado["Persona"] == persona_filtro) |
                (df_filtrado["Persona_Origen"] == persona_filtro) |
                (df_filtrado["Persona_Destino"] == persona_filtro)
            ]
        if tipo_filtro != "Todos":
            df_filtrado = df_filtrado[df_filtrado["Tipo"] == tipo_filtro]
        if not incluir_anulados:
            df_filtrado = df_filtrado[~df_filtrado["Anulado_bool"]]

        # Preparar vista clara
        df_view = df_filtrado[[
            "Fecha", "Tipo", "Persona", "Persona_Origen", "Persona_Destino",
            "Categoría", "Monto_int", "Detalle", "Anulado"
        ]].copy()

        # Formato persona para traspasos
        def mostrar_persona(row):
            if row["Tipo"] == "Traspaso":
                return f"{row['Persona_Origen']} → {row['Persona_Destino']}"
            return row["Persona"]

        df_view["Quién"] = df_view.apply(mostrar_persona, axis=1)

        # Reordenar columnas
        df_view = df_view[["Fecha", "Tipo", "Quién", "Categoría", "Monto_int", "Detalle", "Anulado"]]

        # Mostrar
        st.dataframe(df_view, use_container_width=True)



    with tab_form:
        modo = st.radio("Selecciona modo", ["Registrar","Editar / Anular"], horizontal=True)
        if modo=="Registrar":
            _form_registro(cats_existentes)
            if st.button("Agregar nuevo registro", key = "actualizardb2"):
                st.cache_data.clear()
                try: st.cache_resource.clear()
                except: pass
                st.success("Ya puede proceder ✅")
                st.rerun()
        else:
            _form_editar_anular(df)
          