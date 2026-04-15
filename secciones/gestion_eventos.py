import streamlit as st
import pandas as pd
import uuid
import datetime as dt
from zoneinfo import ZoneInfo
import gspread  # Importación global — NO repetir con import gspread local

# Importar constantes y utilidades desde el módulo general de finanzas
from secciones.finanzas_aucca import AUCCANES, _open_ws, _ensure_sheet_headers, _a1_range_row, EXPECTED_HEADERS, HOJA, STGO

# ==========================================
# Constantes y Estructuras de Datos
# ==========================================
SHEETS_CONFIG = {
    "evt_eventos":    ["ID", "Nombre", "Tipo", "Fecha", "Estado", "Modo", "Asistentes", "Mujeres_Pct", "TerceraEdad_Pct", "Ninos_Pct", "CreatedBy", "CreatedAt", "ClosedAt", "Detalles_Ficha"],
    "evt_productos":  ["EventID", "Nombre", "Precio_Base", "Descripcion", "CreatedBy", "Anulado"],
    "evt_inventario": ["ID", "EventID", "Producto", "Cantidad", "Gasto_Materiales", "Persona_Gasto", "Persona_Registro", "CreatedAt", "Anulado"],
    "evt_ventas":     ["ID", "EventID", "Mesa", "Descripcion_Cuenta", "Producto", "Cantidad", "Precio_Unitario", "Total", "Persona_Registro", "Persona_Cobro", "Estado_Entrega", "Estado_Pago", "Medio_Pago", "CreatedAt", "Anulado"],
    "evt_notas":      ["ID", "EventID", "Persona", "Aprendizaje", "CreatedAt"]
}

def _ensure_evt_sheet(sheet_name: str) -> list[str]:
    """Asegura que la hoja de eventos exista y tenga los headers correctos."""
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_info(
        st.secrets["gspread"],
        scopes=["https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"],
    )
    client = gspread.authorize(creds)
    SPREADSHEET_KEY = "1C8njkp0RQMdXnxuJvPvfK_pNZHQSi7q7dUPeUg-2624"
    sh = client.open_by_key(SPREADSHEET_KEY)

    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=25)
        expected = SHEETS_CONFIG.get(sheet_name, [])
        if expected:
            ws.update("A1", [expected])
        return expected

    headers_raw = ws.row_values(1)
    headers = [h.strip() for h in headers_raw]
    expected = SHEETS_CONFIG.get(sheet_name, [])
    missing = [h for h in expected if h not in headers]
    if missing:
        new_headers = headers + missing
        ws.update(_a1_range_row(1, len(new_headers)), [new_headers])
        return new_headers
    return headers

@st.cache_data(ttl=30)
def _load_evt_df(sheet_name: str) -> pd.DataFrame:
    """Carga los datos de una hoja como dataframe."""
    try:
        ws = _open_ws(sheet_name)
        headers = _ensure_evt_sheet(sheet_name)
        values = ws.get_all_values()
    except Exception:
        return pd.DataFrame(columns=SHEETS_CONFIG.get(sheet_name, []))

    if not values:
        return pd.DataFrame(columns=headers)
    rows = values[1:]
    norm_rows = [r[:len(headers)] + [""] * max(0, len(headers)-len(r)) for r in rows]
    df = pd.DataFrame(norm_rows, columns=headers)
    if not df.empty and "CreatedAt" in df.columns:
        df["_dt"] = pd.to_datetime(df["CreatedAt"], errors="coerce")
        df = df.sort_values("_dt", ascending=False).drop(columns=["_dt"])
    return df

def _save_evt_row(sheet_name: str, row_dict: dict):
    ws = _open_ws(sheet_name)
    headers = _ensure_evt_sheet(sheet_name)
    row_out = [str(row_dict.get(h, "")) for h in headers]
    ws.append_row(row_out, value_input_option="USER_ENTERED")
    _load_evt_df.clear()

# ==========================================
# Lógica Principal del Panel
# ==========================================
def render():
    st.markdown("## 🎉 Gestión de Eventos y Actividades")

    usuario_actual = st.session_state.get("current_user", "Administrador")

    # 1. Cargar lista de eventos
    df_eventos = _load_evt_df("evt_eventos")
    eventos_abiertos = df_eventos[df_eventos["Estado"] == "Abierto"] if not df_eventos.empty else pd.DataFrame()

    with st.sidebar:
        st.markdown("---")
        with st.expander("➕ Crear Nuevo Evento", expanded=False):
            with st.form("form_nuevo_evento"):
                nombre_ev   = st.text_input("Nombre del Evento (ej. Fiesta Agosto)")
                tipo_ev     = st.selectbox("Tipo", ["Evento / Fiesta", "Almuerzo / Cena", "Visita", "Taller"])
                fecha_ev    = st.date_input("Fecha de Realización", dt.date.today())
                detalles_ev = st.text_area("Ficha del Evento (Horarios, Acuerdos, Modalidad, etc.)", height=80)
                modo_ev     = st.radio("Modo del Evento", ["pro", "simple"], horizontal=True,
                                       help="Pro: incluye sección de Entregas. Simple: sin entregas.")

                if st.form_submit_button("Crear Evento", type="primary", use_container_width=True):
                    if nombre_ev.strip() != "":
                        now = pd.Timestamp.now(tz=STGO)
                        nuevo_id = str(uuid.uuid4())
                        rec = {
                            "ID":            nuevo_id,
                            "Nombre":        nombre_ev.strip(),
                            "Tipo":          tipo_ev,
                            "Fecha":         fecha_ev.strftime("%Y-%m-%d"),
                            "Estado":        "Abierto",
                            "Modo":          modo_ev,
                            "CreatedBy":     usuario_actual,
                            "CreatedAt":     now.strftime("%Y-%m-%d %H:%M:%S"),
                            "Detalles_Ficha": detalles_ev.strip()
                        }
                        _save_evt_row("evt_eventos", rec)
                        st.session_state["evento_activo_id"] = nuevo_id
                        st.success("Evento creado")
                        st.rerun()

    event_options = {"": "Selecciona un evento activo..."}
    if not eventos_abiertos.empty:
        for _, row in eventos_abiertos.iterrows():
            event_options[row["ID"]] = f"🟢 {row['Nombre']} ({row['Fecha']})"

    eventos_cerrados = df_eventos[df_eventos["Estado"] == "Cerrado"] if not df_eventos.empty else pd.DataFrame()
    if not eventos_cerrados.empty:
        for _, row in eventos_cerrados.iterrows():
            event_options[row["ID"]] = f"🔒 {row['Nombre']} ({row['Fecha']})"

    current_idx = 0
    keys_list   = list(event_options.keys())
    saved_id    = st.session_state.get("evento_activo_id", "")
    if saved_id in keys_list:
        current_idx = keys_list.index(saved_id)

    seleccion = st.selectbox(
        "Evento Activo",
        options=keys_list,
        format_func=lambda x: event_options[x],
        index=current_idx
    )
    if seleccion != saved_id:
        st.session_state["evento_activo_id"] = seleccion
        st.rerun()

    if not seleccion:
        st.info("👈 Selecciona o crea un evento para comenzar.")
        return

    evento_sel_data = df_eventos[df_eventos["ID"] == seleccion].iloc[0]
    es_cerrado      = evento_sel_data["Estado"] == "Cerrado"
    modo_evento     = str(evento_sel_data.get("Modo", "pro")).strip().lower()
    if modo_evento not in ("simple", "pro"):
        modo_evento = "pro"

    if es_cerrado:
        st.warning("🔒 **Este evento está CERRADO.** Solo puedes visualizar la información.")

    st.markdown("---")

    # -----------------------------------------------------
    # Cargar Data del Evento Seleccionado
    # -----------------------------------------------------
    df_inv  = _load_evt_df("evt_inventario")
    df_ven  = _load_evt_df("evt_ventas")
    df_prod = _load_evt_df("evt_productos")

    # Filtrar anulados
    df_inv_act  = df_inv[(df_inv["EventID"] == seleccion) & (df_inv["Anulado"] != "TRUE")]   if not df_inv.empty  else pd.DataFrame(columns=SHEETS_CONFIG["evt_inventario"])
    df_ven_act  = df_ven[(df_ven["EventID"] == seleccion) & (df_ven["Anulado"] != "TRUE")]   if not df_ven.empty  else pd.DataFrame(columns=SHEETS_CONFIG["evt_ventas"])
    df_prod_act = df_prod[(df_prod["EventID"] == seleccion) & (df_prod.get("Anulado", pd.Series([""] * len(df_prod))) != "TRUE")] if not df_prod.empty else pd.DataFrame(columns=SHEETS_CONFIG["evt_productos"])

    # Stock Actual
    def _calcular_stock():
        res = {}
        if not df_inv_act.empty:
            inv_copy = df_inv_act.copy()
            inv_copy["Cantidad"] = pd.to_numeric(inv_copy["Cantidad"], errors='coerce').fillna(0)
            res = inv_copy.groupby("Producto")["Cantidad"].sum().to_dict()
        if not df_ven_act.empty:
            ven_copy = df_ven_act.copy()
            ven_copy["Cantidad"] = pd.to_numeric(ven_copy["Cantidad"], errors='coerce').fillna(0)
            ventas_group = ven_copy.groupby("Producto")["Cantidad"].sum().to_dict()
            for prod, q_vendida in ventas_group.items():
                res[prod] = res.get(prod, 0) - q_vendida
        return res

    stock_actual = _calcular_stock()

    # Mapa de precios
    price_map = {}
    if not df_prod_act.empty:
        for _, r in df_prod_act.iterrows():
            try:
                price_map[r["Nombre"]] = int(r["Precio_Base"])
            except Exception:
                price_map[r["Nombre"]] = 0

    # -----------------------------------------------------
    # Sub-Rutas (Pestañas del Evento)
    # -----------------------------------------------------
    if modo_evento == "simple":
        tab_options = ["⚙️ Información General", "🛒 Punto de Venta (Caja)", "🍳 Gasto y Producción", "🧠 Aprendizajes", "🏁 Transacciones / Cierre"]
    else:
        tab_options = ["⚙️ Información General", "🛒 Punto de Venta (Caja)", "🍳 Gasto y Producción", "🏃 Entregas", "🧠 Aprendizajes", "🏁 Transacciones / Cierre"]

    active_tab = st.radio("Sección del Evento", tab_options, horizontal=True, label_visibility="collapsed", key=f"tab_evt_{seleccion}")

    # ==========================================
    # 0. Información General y Configuración
    # ==========================================
    if active_tab == tab_options[0]:
        st.markdown(f"### ⚙️ {evento_sel_data['Nombre']}")

        c_i1, c_i2, c_i3 = st.columns(3)
        c_i1.metric("Fecha Registro",    str(evento_sel_data["CreatedAt"]).split(" ")[0])
        c_i2.metric("Fecha Realización", str(evento_sel_data["Fecha"]))
        c_i3.metric("Fecha Cierre",      str(evento_sel_data.get("ClosedAt", "")) if pd.notna(evento_sel_data.get("ClosedAt")) and evento_sel_data.get("ClosedAt") else "Activo")

        modo_badge = "🟢 Modo Pro (con Entregas)" if modo_evento == "pro" else "🟡 Modo Simple (sin Entregas)"
        st.markdown(f"**Modo:** {modo_badge}")

        detalles_texto = str(evento_sel_data.get("Detalles_Ficha", ""))
        if detalles_texto and detalles_texto != "nan":
            st.info(f"**📖 Ficha del Evento / Acuerdos Previos:**\n\n{detalles_texto}")

        # ----- Edición completa del evento -----
        with st.expander("✏️ Editar Configuración del Evento", expanded=False):
            with st.form("form_edit_evento"):
                nuevo_nombre   = st.text_input("Nombre del Evento",    value=evento_sel_data["Nombre"])
                nueva_desc     = st.text_area("Descripción / Ficha",   value=str(evento_sel_data.get("Detalles_Ficha", "")), height=100)
                tipo_opts      = ["Evento / Fiesta", "Almuerzo / Cena", "Visita", "Taller"]
                tipo_actual    = str(evento_sel_data.get("Tipo", "Evento / Fiesta"))
                tipo_idx       = tipo_opts.index(tipo_actual) if tipo_actual in tipo_opts else 0
                nuevo_tipo     = st.selectbox("Tipo", tipo_opts, index=tipo_idx)
                nueva_fecha    = st.date_input("Fecha de Realización",
                                               value=pd.to_datetime(evento_sel_data["Fecha"]).date() if evento_sel_data.get("Fecha") else dt.date.today())
                modo_idx       = 0 if modo_evento == "pro" else 1
                nuevo_modo     = st.radio("Modo del Evento", ["pro", "simple"], index=modo_idx, horizontal=True,
                                          help="Pro: incluye sección Entregas. Simple: sin entregas (más rápido).")

                if st.form_submit_button("💾 Guardar Configuración", type="primary", use_container_width=True):
                    _actualizar_evento(seleccion, nuevo_nombre.strip(), nueva_desc.strip(), nuevo_tipo,
                                       nueva_fecha.strftime("%Y-%m-%d"), nuevo_modo)
                    st.success("Configuración actualizada.")
                    st.rerun()

        # ----- Ajustes destructivos (eliminar/anular) -----
        with st.expander("⚠️ Acciones de Eliminación", expanded=False):
            if es_cerrado:
                st.warning("⚠️ Este evento ya fue inyectado a Finanzas. Al anularlo se ANULARÁN sus transacciones en Finanzas.")
                if st.button("🚫 Anular Evento y Registros en Finanzas", type="primary"):
                    _anular_evento_y_finanzas(seleccion, evento_sel_data["Nombre"])
                    st.session_state["evento_activo_id"] = ""
                    st.success("Evento anulado.")
                    st.rerun()
            else:
                st.info("Eliminar borrará este evento y lo dejará inaccesible.")
                if st.button("🗑️ Eliminar Evento Permanentemente", type="primary"):
                    _marcar_borrado(seleccion)
                    st.session_state["evento_activo_id"] = ""
                    st.success("Evento borrado.")
                    st.rerun()

        st.markdown("---")
        st.markdown("#### 📋 Catálogo de Productos y Precios")
        st.caption("Añade productos, fija precios y descripción para la caja.")

        if not es_cerrado:
            # Crear producto
            with st.container(border=True):
                st.markdown("##### ➕ Crear Nuevo Producto")
                with st.form("form_crear_producto", clear_on_submit=True):
                    col_n1, col_n2 = st.columns([2, 1])
                    nuevo_p     = col_n1.text_input("Nombre del Producto", placeholder="Ej: Pizza Napolitana")
                    nuevo_v     = col_n2.number_input("Precio Venta (CLP)", min_value=0, step=100)
                    nuevo_desc_p = st.text_input("Descripción / Comentario (opcional)", placeholder="Ej: Sin gluten, grande")
                    if st.form_submit_button("Añadir al Menú", use_container_width=True):
                        if nuevo_p.strip():
                            if nuevo_p.strip() not in price_map:
                                _save_evt_row("evt_productos", {
                                    "EventID":     seleccion,
                                    "Nombre":      nuevo_p.strip(),
                                    "Precio_Base": str(int(nuevo_v)),
                                    "Descripcion": nuevo_desc_p.strip(),
                                    "CreatedBy":   usuario_actual,
                                    "Anulado":     ""
                                })
                                st.success("Producto creado.")
                                _load_evt_df.clear()
                                st.rerun()
                            else:
                                st.error("Este producto ya existe en el menú.")

            # Editar productos existentes (precio, descripción, nombre, eliminar)
            st.markdown("##### ✏️ Editar / Eliminar Productos Existentes")
            if not df_prod_act.empty:
                df_to_edit = pd.DataFrame([{
                    "Nombre":      r["Nombre"],
                    "Precio":      int(price_map.get(r["Nombre"], 0)),
                    "Descripcion": str(r.get("Descripcion", "")),
                    "Eliminar":    False
                } for _, r in df_prod_act.iterrows()])

                with st.form("form_edit_productos"):
                    st.caption("Edita nombre, precio o descripción. Marca 'Eliminar' para quitar el producto. Presiona Guardar para confirmar.")
                    edited_df = st.data_editor(
                        df_to_edit,
                        column_config={
                            "Nombre":      st.column_config.TextColumn("Producto", disabled=False),
                            "Precio":      st.column_config.NumberColumn("Precio ($)", min_value=0, step=100),
                            "Descripcion": st.column_config.TextColumn("Descripción"),
                            "Eliminar":    st.column_config.CheckboxColumn("🗑️ Eliminar", default=False)
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                    if st.form_submit_button("💾 Guardar Cambios en Productos", type="primary", use_container_width=True):
                        ws_prod    = _open_ws("evt_productos")
                        records    = ws_prod.get_all_records()
                        hdrs_prod  = SHEETS_CONFIG["evt_productos"]
                        idx_precio = hdrs_prod.index("Precio_Base") + 1
                        idx_desc   = hdrs_prod.index("Descripcion") + 1
                        idx_nombre = hdrs_prod.index("Nombre") + 1
                        idx_anu    = hdrs_prod.index("Anulado") + 1
                        updates    = []

                        original_names = list(df_to_edit["Nombre"])
                        for row_idx, (orig_name, new_row) in enumerate(zip(original_names, edited_df.itertuples())):
                            for i, rec in enumerate(records):
                                if str(rec.get("EventID")) == seleccion and str(rec.get("Nombre")) == orig_name:
                                    excel_row = i + 2
                                    if new_row.Eliminar:
                                        updates.append(gspread.Cell(row=excel_row, col=idx_anu, value="TRUE"))
                                    else:
                                        if str(new_row.Nombre) != orig_name:
                                            updates.append(gspread.Cell(row=excel_row, col=idx_nombre, value=str(new_row.Nombre)))
                                        if str(int(new_row.Precio)) != str(rec.get("Precio_Base", "")):
                                            updates.append(gspread.Cell(row=excel_row, col=idx_precio, value=str(int(new_row.Precio))))
                                        if str(new_row.Descripcion) != str(rec.get("Descripcion", "")):
                                            updates.append(gspread.Cell(row=excel_row, col=idx_desc, value=str(new_row.Descripcion)))
                                    break

                        if updates:
                            ws_prod.update_cells(updates)
                            _load_evt_df.clear()
                            st.success("Productos actualizados correctamente.")
                            st.rerun()
                        else:
                            st.info("No detecté cambios para guardar.")
            else:
                st.info("No hay productos registrados aún.")

    # ==========================================
    # 1. Punto de Venta (Caja)
    # ==========================================
    if active_tab == tab_options[1]:
        st.markdown(f"### 🛒 Administrar Cuentas / Mesas — {evento_sel_data['Nombre']}")

        if not es_cerrado:
            with st.expander("➕ Abrir Nueva Cuenta", expanded=False):
                with st.form("form_nueva_cuenta", clear_on_submit=True):
                    nueva_mesa      = st.text_input("Nombre de la cuenta / Mesa", placeholder="Ej: Mesa Juan, Grupo 1")
                    nueva_mesa_desc = st.text_input("Descripción / Comentario (opcional)", placeholder="Ej: Llegó con 5 personas")
                    if st.form_submit_button("Iniciar Cuenta", type="primary"):
                        if nueva_mesa.strip():
                            st.success("Cuenta lista para usar.")
                            st.session_state["ultima_mesa"]       = nueva_mesa.strip()
                            st.session_state["ultima_mesa_desc"]  = nueva_mesa_desc.strip()

            with st.expander("📦 Visor de Inventario (Stock Disponible)", expanded=False):
                if stock_actual:
                    df_s = pd.DataFrame([{"Producto": p, "Precio Unitario": f"${price_map.get(p, 0):,.0f}", "Stock": s}
                                         for p, s in stock_actual.items() if s > 0])
                    st.dataframe(df_s, use_container_width=True, hide_index=True)
                else:
                    st.info("No hay productos con stock actualmente.")

            c1, c2 = st.columns([1, 1])
            with c1:
                with st.container(border=True):
                    st.markdown("#### 🍔 Añadir Producto a Cuenta")
                    mesas_existentes = []
                    if not df_ven_act.empty:
                        mesas_existentes = sorted(list(df_ven_act["Mesa"].unique()))
                    ult_mesa = st.session_state.get("ultima_mesa", "")
                    if ult_mesa and ult_mesa not in mesas_existentes:
                        mesas_existentes.insert(0, ult_mesa)

                    with st.form("form_add_prod_cuenta", clear_on_submit=True):
                        if not mesas_existentes:
                            st.info("No hay mesas abiertas. Escribe una nueva:")
                            sel_mesa = st.text_input("Nombre Mesa")
                        else:
                            sel_mesa = st.selectbox("Seleccionar Cuenta/Mesa", mesas_existentes)

                        prods_disp = [p for p, stk in stock_actual.items() if stk > 0]
                        if not prods_disp:
                            st.warning("No hay productos con stock disponibles aún.")
                            sel_prod = ""
                            cant     = 0
                            precio_ingresado = 0
                        else:
                            sel_prod = st.selectbox("Producto Disp.", [f"{p} (Stock: {stock_actual[p]:.0f})" for p in prods_disp])
                            cant     = st.number_input("Cantidad", min_value=1, step=1)
                            st.caption("Precio especial solo si difiere del catálogo. Dejar en 0 para usar catálogo.")
                            precio_ingresado = st.number_input("Precio Especial (CLP) - Opcional", min_value=0, step=100, value=0)

                        if st.form_submit_button("Añadir a la Cuenta", type="primary", use_container_width=True):
                            prod_clean   = sel_prod.split(" (Stock:")[0] if sel_prod else ""
                            precio_final = precio_ingresado if precio_ingresado > 0 else price_map.get(prod_clean, 0)
                            if sel_mesa and prod_clean and cant > 0:
                                if stock_actual.get(prod_clean, 0) < cant:
                                    st.error(f"⚠️ Stock insuficiente. Solo quedan {stock_actual.get(prod_clean, 0)}.")
                                else:
                                    now = pd.Timestamp.now(tz=STGO)
                                    rec_venta = {
                                        "ID":                str(uuid.uuid4()),
                                        "EventID":           seleccion,
                                        "Mesa":              sel_mesa.strip(),
                                        "Descripcion_Cuenta": st.session_state.get("ultima_mesa_desc", ""),
                                        "Producto":          prod_clean,
                                        "Cantidad":          str(int(cant)),
                                        "Precio_Unitario":   str(int(precio_final)),
                                        "Total":             str(int(cant * precio_final)),
                                        "Persona_Registro":  usuario_actual,
                                        "Persona_Cobro":     "",
                                        "Estado_Entrega":    "Pendiente",
                                        "Estado_Pago":       "Pendiente",
                                        "Medio_Pago":        "",
                                        "CreatedAt":         now.strftime("%Y-%m-%d %H:%M:%S"),
                                        "Anulado":           ""
                                    }
                                    _save_evt_row("evt_ventas", rec_venta)
                                    st.session_state["ultima_mesa"] = sel_mesa.strip()
                                    st.success(f"Añadido a {sel_mesa}")
                                    st.rerun()

            with c2:
                st.markdown("#### 💳 Resumen y Cobro de Mesas")
                if not df_ven_act.empty:
                    df_ven_act["Total_Num"] = pd.to_numeric(df_ven_act["Total"], errors='coerce').fillna(0)
                    df_ven_no_pagadas = df_ven_act[df_ven_act["Estado_Pago"] == "Pendiente"]
                    agrupado_pagar    = df_ven_no_pagadas.groupby("Mesa")["Total_Num"].sum().reset_index()

                    if agrupado_pagar.empty:
                        st.info("Todas las cuentas registradas están pagadas 😊.")
                    else:
                        for _, rmesa in agrupado_pagar.iterrows():
                            mesa  = rmesa["Mesa"]
                            total = rmesa["Total_Num"]
                            with st.expander(f"🧾 Cuenta Pendiente: **{mesa}** — Total: ${total:,.0f}"):
                                det_mesa   = df_ven_no_pagadas[df_ven_no_pagadas["Mesa"] == mesa]
                                df_to_edit = det_mesa[["ID", "Producto", "Precio_Unitario", "Cantidad"]].copy()
                                df_to_edit["Cantidad"]       = pd.to_numeric(df_to_edit["Cantidad"], errors="coerce").fillna(1).astype(int)
                                df_to_edit["Precio_Unitario"] = pd.to_numeric(df_to_edit["Precio_Unitario"], errors="coerce").fillna(0).astype(int)
                                df_to_edit["Eliminar"]       = False

                                st.caption("Modifica y presiona Guardar. Los cambios no se aplican hasta que presiones el botón.")
                                with st.form(f"form_editor_{mesa}"):
                                    edited_mesa_df = st.data_editor(
                                        df_to_edit,
                                        column_config={
                                            "ID":              None,
                                            "Producto":        st.column_config.TextColumn("Ítem", disabled=True),
                                            "Precio_Unitario": st.column_config.NumberColumn("P. Unitario ($)", disabled=True),
                                            "Cantidad":        st.column_config.NumberColumn("Cantidad", min_value=1, step=1),
                                            "Eliminar":        st.column_config.CheckboxColumn("🗑️ Quitar", default=False)
                                        },
                                        hide_index=True,
                                        use_container_width=True
                                    )
                                    current_total_edited = sum([
                                        row["Cantidad"] * row["Precio_Unitario"]
                                        for _, row in edited_mesa_df.iterrows() if not row["Eliminar"]
                                    ])
                                    st.markdown(f"**Total Proyectado: ${current_total_edited:,.0f}**")

                                    if st.form_submit_button("💾 Guardar Ajustes de Facturación", type="primary"):
                                        ws_ven   = _open_ws("evt_ventas")
                                        records  = ws_ven.get_all_records()
                                        idx_cant = SHEETS_CONFIG["evt_ventas"].index("Cantidad") + 1
                                        idx_tot  = SHEETS_CONFIG["evt_ventas"].index("Total") + 1
                                        idx_anu  = SHEETS_CONFIG["evt_ventas"].index("Anulado") + 1
                                        updates  = []

                                        for _, changed_row in edited_mesa_df.iterrows():
                                            c_id  = changed_row["ID"]
                                            c_qty = int(changed_row["Cantidad"])
                                            c_del = bool(changed_row["Eliminar"])

                                            for i, r_g in enumerate(records):
                                                if str(r_g.get("ID")) == c_id:
                                                    row_excel = i + 2
                                                    if c_del:
                                                        updates.append(gspread.Cell(row=row_excel, col=idx_anu, value="TRUE"))
                                                    else:
                                                        orig_qty = int(r_g.get("Cantidad", 0) or 0)
                                                        if orig_qty != c_qty:
                                                            new_tot = c_qty * changed_row["Precio_Unitario"]
                                                            updates.append(gspread.Cell(row=row_excel, col=idx_cant, value=str(int(c_qty))))
                                                            updates.append(gspread.Cell(row=row_excel, col=idx_tot,  value=str(int(new_tot))))
                                                    break

                                        if updates:
                                            ws_ven.update_cells(updates)
                                            _load_evt_df.clear()
                                            st.success("Cambios aplicados.")
                                            st.rerun()
                                        else:
                                            st.info("Sin cambios.")

                                st.markdown("---")

                                with st.form(f"form_cobro_{mesa}"):
                                    medio_pago  = st.selectbox("Medio de Pago", ["Transferencia", "Efectivo"])
                                    quien_cobra = st.selectbox("¿Hacia quién fue la plata / depósito?", AUCCANES,
                                                               index=AUCCANES.index(usuario_actual) if usuario_actual in AUCCANES else 0)

                                    # Modo simple: no bloquear por entregas
                                    if modo_evento == "pro":
                                        todo_entregado = all(estado == "Entregado" for estado in det_mesa["Estado_Entrega"])
                                        if not todo_entregado:
                                            st.warning("⚠️ Hay productos pendientes de entrega. Ve a 'Entregas' antes de confirmar pago.")
                                            st.form_submit_button("Confirmar Pago (Bloqueado)", disabled=True)
                                            continue_cobro = False
                                        else:
                                            continue_cobro = True
                                    else:
                                        continue_cobro = True  # Modo simple: sin bloqueo

                                    if continue_cobro:
                                        if st.form_submit_button(f"💸 Confirmar Pago {mesa}", type="primary"):
                                            ws_ven   = _open_ws("evt_ventas")
                                            records  = ws_ven.get_all_records()
                                            cell_updates = []
                                            estado_pago_idx   = SHEETS_CONFIG["evt_ventas"].index("Estado_Pago") + 1
                                            medio_pago_idx    = SHEETS_CONFIG["evt_ventas"].index("Medio_Pago") + 1
                                            persona_cobro_idx = SHEETS_CONFIG["evt_ventas"].index("Persona_Cobro") + 1
                                            estado_ent_idx    = SHEETS_CONFIG["evt_ventas"].index("Estado_Entrega") + 1

                                            for i, r_g in enumerate(records):
                                                if (str(r_g.get("EventID")) == seleccion and
                                                        str(r_g.get("Mesa")) == mesa and
                                                        str(r_g.get("Estado_Pago")) == "Pendiente"):
                                                    row_excel = i + 2
                                                    cell_updates.append(gspread.Cell(row=row_excel, col=estado_pago_idx,   value="Pagado"))
                                                    cell_updates.append(gspread.Cell(row=row_excel, col=medio_pago_idx,    value=medio_pago))
                                                    cell_updates.append(gspread.Cell(row=row_excel, col=persona_cobro_idx, value=quien_cobra))
                                                    if modo_evento == "simple":
                                                        cell_updates.append(gspread.Cell(row=row_excel, col=estado_ent_idx, value="Entregado"))

                                            if cell_updates:
                                                ws_ven.update_cells(cell_updates)
                                                st.success(f"Cuenta de {mesa} pagada vía {medio_pago} — cobrado por {quien_cobra}")
                                                _load_evt_df.clear()
                                                st.rerun()
                else:
                    st.info("Aún no hay ventas registradas para este evento.")

        # Historial general
        if not df_ven_act.empty:
            st.markdown("---")
            st.markdown("##### 📜 Historial de Operaciones de Caja")
            df_ven_act["Total_Num"]  = pd.to_numeric(df_ven_act["Total"], errors='coerce').fillna(0)
            cols_view = ["CreatedAt", "Mesa", "Producto", "Cantidad", "Total_Num", "Estado_Pago", "Persona_Registro"]
            if "Estado_Entrega" in df_ven_act.columns and modo_evento == "pro":
                cols_view.insert(-1, "Estado_Entrega")
            df_ven_view = df_ven_act[cols_view].copy()
            df_ven_view = df_ven_view.rename(columns={"Total_Num": "Total CLP", "Persona_Registro": "Vendedor"})
            st.dataframe(df_ven_view, use_container_width=True)

    # ==========================================
    # 2. Aportes / Cocina / Producción
    # ==========================================
    if active_tab == tab_options[2]:
        st.markdown(f"### 🍳 Gastos y Producción — {evento_sel_data['Nombre']}")
        st.caption("Anota cuánto dinero se gastó en compras y cuántos productos reales se generaron para la venta.")

        if not es_cerrado:
            col_l, col_r = st.columns(2)

            with col_l:
                with st.expander("💸 1. Reportar Gastos de Bolsillo", expanded=True):
                    st.caption("Para gas, insumos generales, harina, etc.")
                    with st.form("form_gastos", clear_on_submit=True):
                        motivo_gasto  = st.text_input("¿Qué se compró?", placeholder="Ej: Supermercado, Bebidas, Gas")
                        gasto_valor   = st.number_input("💰 Valor Costo (CLP)", min_value=100, step=100)
                        persona_gasto = st.selectbox("¿Quién pagó de su bolsillo?", [""] + AUCCANES,
                                                     index=AUCCANES.index(usuario_actual) if usuario_actual in AUCCANES else 0)
                        if st.form_submit_button("Registrar Gasto", type="primary", use_container_width=True):
                            if motivo_gasto.strip() and persona_gasto:
                                now    = pd.Timestamp.now(tz=STGO)
                                rec_in = {
                                    "ID":               str(uuid.uuid4()),
                                    "EventID":          seleccion,
                                    "Producto":         f"[Gasto] {motivo_gasto.strip()}",
                                    "Cantidad":         "0",
                                    "Gasto_Materiales": str(int(gasto_valor)),
                                    "Persona_Gasto":    persona_gasto,
                                    "Persona_Registro": usuario_actual,
                                    "CreatedAt":        now.strftime("%Y-%m-%d %H:%M:%S")
                                }
                                _save_evt_row("evt_inventario", rec_in)
                                st.success("Gasto registrado.")
                                st.rerun()
                            else:
                                st.error("Ingresa qué se compró y quién lo pagó.")

            with col_r:
                with st.expander("🍔 2. Reportar Elaboración de Oferta", expanded=True):
                    st.caption("Para sumar stock real que la gente te podrá comprar.")
                    with st.form("form_inventario", clear_on_submit=True):
                        lista_prod_sug = sorted(df_prod_act["Nombre"].unique()) if not df_prod_act.empty else []
                        sel_cat_prod   = st.selectbox("Producto a Fabricar", [""] + lista_prod_sug)
                        nuevo_prod     = st.text_input("O Crear Nuevo Producto", placeholder="Ej: Muffin Vegano")
                        cantidad       = st.number_input("📦 Cantidad Elaborada", min_value=1, step=1)

                        if st.form_submit_button("Sumar al Inventario", type="primary", use_container_width=True):
                            prod_final = nuevo_prod.strip() if nuevo_prod.strip() else sel_cat_prod
                            if prod_final and cantidad > 0:
                                if prod_final not in lista_prod_sug:
                                    _save_evt_row("evt_productos", {
                                        "EventID":     seleccion, "Nombre": prod_final,
                                        "Precio_Base": "0",      "CreatedBy": usuario_actual, "Anulado": ""
                                    })
                                now    = pd.Timestamp.now(tz=STGO)
                                rec_in = {
                                    "ID":               str(uuid.uuid4()),
                                    "EventID":          seleccion,
                                    "Producto":         prod_final,
                                    "Cantidad":         str(int(cantidad)),
                                    "Gasto_Materiales": "0",
                                    "Persona_Gasto":    "",
                                    "Persona_Registro": usuario_actual,
                                    "CreatedAt":        now.strftime("%Y-%m-%d %H:%M:%S")
                                }
                                _save_evt_row("evt_inventario", rec_in)
                                st.success(f"Se sumaron {cantidad}x {prod_final} al stock.")
                                st.rerun()
                            else:
                                st.error("Debes indicar un producto válido y una cantidad elaborada.")

        if not df_inv_act.empty:
            st.markdown("#### 📋 Histórico de Operaciones")
            df_inv_view = df_inv_act[["CreatedAt", "Persona_Registro", "Producto", "Cantidad", "Gasto_Materiales", "Persona_Gasto"]].copy()
            df_inv_view["Gasto_Materiales"] = pd.to_numeric(df_inv_view["Gasto_Materiales"], errors='coerce').fillna(0)
            st.dataframe(df_inv_view, use_container_width=True, hide_index=True)

    # ==========================================
    # 3. Entregas (solo Modo Pro)
    # ==========================================
    tab_entregas_label = "🏃 Entregas"
    if modo_evento == "pro" and active_tab == tab_entregas_label:
        st.markdown("### 🏃 Entregas Pendientes a Clientes")
        if df_ven_act.empty:
            st.info("Aún no hay ventas anotadas.")
        else:
            df_pend = df_ven_act[df_ven_act["Estado_Entrega"] == "Pendiente"]
            if df_pend.empty:
                st.success("¡Todo está entregado! Excelente trabajo en cocina y sala.")
            else:
                for _, rpend in df_pend.iterrows():
                    m  = rpend["Mesa"]
                    p  = rpend["Producto"]
                    c  = rpend["Cantidad"]
                    vp = rpend["Estado_Pago"]

                    bg_color = "#f9f9f9" if vp == "Pagado" else "#fff4e5"
                    with st.container():
                        st.markdown(f"""
                        <div style="background:{bg_color}; padding:10px; border-left:4px solid {'#48bb78' if vp=='Pagado' else '#ed8936'}; margin-bottom:10px; border-radius:4px;">
                            <strong>{c}x {p}</strong> para <em>{m}</em> (Pago: {vp})
                        </div>
                        """, unsafe_allow_html=True)
                        if not es_cerrado and st.button("✅ Marcar como Entregado", key=f"entrega_{rpend['ID']}", use_container_width=True):
                            ws_ven          = _open_ws("evt_ventas")
                            records         = ws_ven.get_all_records()
                            estado_ent_idx  = SHEETS_CONFIG["evt_ventas"].index("Estado_Entrega") + 1
                            for i, r_g in enumerate(records):
                                if str(r_g.get("ID")) == rpend["ID"]:
                                    row_excel = i + 2
                                    ws_ven.update_cell(row_excel, estado_ent_idx, "Entregado")
                                    st.success(f"{p} marcado como entregado a {m}")
                                    _load_evt_df.clear()
                                    st.rerun()
                                    break

    # ==========================================
    # Aprendizajes (índice dinámico)
    # ==========================================
    tab_notas_label = "🧠 Aprendizajes"
    if active_tab == tab_notas_label:
        st.markdown("### 🧠 Registro de Aprendizajes de la Jornada")
        st.caption("Anota lo que salió bien, lo que salió mal, o ideas para el próximo evento.")

        df_not     = _load_evt_df("evt_notas")
        df_not_act = df_not[df_not["EventID"] == seleccion] if not df_not.empty else pd.DataFrame(columns=SHEETS_CONFIG["evt_notas"])

        if not es_cerrado:
            with st.form("form_notas", clear_on_submit=True):
                nota = st.text_area("Cuéntame...", height=100)
                if st.form_submit_button("Guardar Reflexión", type="primary"):
                    if nota.strip():
                        now = pd.Timestamp.now(tz=STGO)
                        rn  = {
                            "ID": str(uuid.uuid4()), "EventID": seleccion,
                            "Persona": usuario_actual, "Aprendizaje": nota.strip(),
                            "CreatedAt": now.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        _save_evt_row("evt_notas", rn)
                        st.success("Guardado.")
                        st.rerun()

        if not df_not_act.empty:
            for _, rnota in df_not_act.iterrows():
                st.info(f"**{rnota['Persona']}** ({rnota['CreatedAt']}):\n\n{rnota['Aprendizaje']}")

    # ==========================================
    # Cierre de Evento / Integración Finanzas
    # ==========================================
    tab_cierre_label = "🏁 Transacciones / Cierre"
    if active_tab == tab_cierre_label:
        st.markdown("### 🏁 Cierre del Evento y Cuadratura")
        st.info("Resumen del dinero obtenido, cálculo de reembolsos y exportación a Finanzas.")

        if df_inv_act.empty and df_ven_act.empty:
            st.warning("No hay transacciones registradas.")
            if not es_cerrado:
                if st.button("Cerrar Evento (Vacío)", type="secondary"):
                    _marcar_cerrado(seleccion, 0, 0, 0)
                    st.rerun()
            return

        # Analítica de cierre
        df_ven_act["Total_Num"] = pd.to_numeric(df_ven_act["Total"], errors='coerce').fillna(0)
        df_inv_act["Gasto_Num"] = pd.to_numeric(df_inv_act["Gasto_Materiales"], errors='coerce').fillna(0)

        df_pagadas    = df_ven_act[df_ven_act["Estado_Pago"] == "Pagado"]
        df_no_pagadas = df_ven_act[df_ven_act["Estado_Pago"] == "Pendiente"]

        total_deudas_venta = df_no_pagadas["Total_Num"].sum()
        total_todas_ventas = df_ven_act["Total_Num"].sum()  # Suma total incluyendo pendientes

        # Ingresos cobrados: agrupar por Persona_Cobro (incluyendo vacíos como "Sin asignar")
        if not df_pagadas.empty:
            df_pagadas_copy = df_pagadas.copy()
            df_pagadas_copy["Persona_Cobro"] = df_pagadas_copy["Persona_Cobro"].replace("", "Sin asignar").fillna("Sin asignar")
            pagos_por_persona = df_pagadas_copy.groupby("Persona_Cobro")["Total_Num"].sum().to_dict()
        else:
            pagos_por_persona = {}
        total_recaudado = sum(pagos_por_persona.values())

        # Gastos de materiales
        df_gastos_reales = df_inv_act[df_inv_act["Gasto_Num"] > 0]
        if not df_gastos_reales.empty:
            df_gastos_copy = df_gastos_reales.copy()
            df_gastos_copy["Persona_Gasto"] = df_gastos_copy["Persona_Gasto"].replace("", "Sin asignar").fillna("Sin asignar")
            gastos_por_persona = df_gastos_copy.groupby("Persona_Gasto")["Gasto_Num"].sum().to_dict()
        else:
            gastos_por_persona = {}
        total_gastado = sum(gastos_por_persona.values())

        utilidad_neta = total_recaudado - total_gastado

        # Métricas principales
        col_res1, col_res2, col_res3 = st.columns(3)
        col_res1.metric("Total Ventas Registradas",    f"${int(total_todas_ventas):,}".replace(",", "."))
        col_res2.metric("Ingresos Cobrados",           f"${int(total_recaudado):,}".replace(",", "."))
        col_res3.metric("Gastos Totales Insumos",      f"${int(total_gastado):,}".replace(",", "."))

        col_res4, col_res5 = st.columns(2)
        col_res4.metric("Utilidad Neta (Cobrado − Gastos)", f"${int(utilidad_neta):,}".replace(",", "."), delta=f"${int(utilidad_neta):,}".replace(",", "."))
        col_res5.metric("Pendiente de Cobro",               f"${int(total_deudas_venta):,}".replace(",", "."))

        # Detalle de quién tiene qué
        if pagos_por_persona:
            st.markdown("##### 💰 Detalle por Cobrador")
            df_cobros = pd.DataFrame([{"Persona": p, "Monto Cobrado": f"${int(v):,}".replace(",", ".")}
                                       for p, v in pagos_por_persona.items()])
            st.dataframe(df_cobros, use_container_width=True, hide_index=True)

        st.markdown("---")
        if total_deudas_venta > 0:
            st.error(f"⚠️ ¡ATENCIÓN! Hay **${int(total_deudas_venta):,}** en cuentas sin cobrar.".replace(",", "."))

        # Liquidación P2P
        st.markdown("#### 🔄 Liquidación de Cuentas (Traspasos Cruzados)")
        st.caption("Calcula quién le debe plata a quién para cuadrar todo.")

        todas_las_personas = set(list(pagos_por_persona.keys()) + list(gastos_por_persona.keys()))
        saldos = {}
        for p in todas_las_personas:
            if not p or p == "Sin asignar":
                continue
            saldos[p] = pagos_por_persona.get(p, 0) - gastos_por_persona.get(p, 0)

        deudores   = [{"persona": p, "monto": saldo}   for p, saldo in saldos.items() if saldo > 0]
        acreedores = [{"persona": p, "monto": abs(saldo)} for p, saldo in saldos.items() if saldo < 0]

        if utilidad_neta > 0:
            acreedores.append({"persona": "🏦 Caja Central Aucca", "monto": utilidad_neta})

        deudores   = sorted(deudores,   key=lambda x: x["monto"], reverse=True)
        acreedores = sorted(acreedores, key=lambda x: x["monto"], reverse=True)

        traspasos = []
        d_idx, a_idx = 0, 0
        while d_idx < len(deudores) and a_idx < len(acreedores):
            deudor   = deudores[d_idx]
            acreedor = acreedores[a_idx]
            monto_transar = min(deudor["monto"], acreedor["monto"])
            if monto_transar > 0:
                traspasos.append({"de": deudor["persona"], "a": acreedor["persona"], "monto": int(monto_transar)})
            deudor["monto"]   -= monto_transar
            acreedor["monto"] -= monto_transar
            if deudor["monto"] == 0:
                d_idx += 1
            if acreedor["monto"] == 0:
                a_idx += 1

        with st.container(border=True):
            for t in traspasos:
                st.info(f"➡️ **{t['de']}** debe transferirle **${int(t['monto']):,}** a **{t['a']}**".replace(",", "."))
            if not traspasos:
                st.success("Cuentas saldadas. Nadie debe transferir nada.")

        # Acciones de cierre
        es_demo = "demo" in evento_sel_data["Nombre"].lower()

        if not es_cerrado:
            st.markdown("---")
            if es_demo:
                st.info("💡 **Este es un Evento DEMO.** No se inyectará data ficticia en Finanzas reales.")
                col_d1, col_d2 = st.columns(2)
                if col_d1.button("🗑️ Borrar este Demo", use_container_width=True):
                    _marcar_borrado(seleccion)
                    st.session_state["evento_activo_id"] = ""
                    st.rerun()
                if col_d2.button("🔄 Borrar Demo y Crear Uno Nuevo", type="primary", use_container_width=True):
                    _marcar_borrado(seleccion)
                    import scratch_insert_demo
                    nuevo_id = scratch_insert_demo.poblar_datos_demo()
                    st.session_state["evento_activo_id"] = nuevo_id
                    _load_evt_df.clear()
                    st.success("Limpiado y Recreado con Éxito.")
                    st.rerun()
            else:
                st.markdown("##### ⚙️ Formulario Oficial de Cierre")
                with st.form("form_cierre_oficial"):
                    st.caption("Ingresa los estadísticos del evento antes de cerrar.")
                    asistentes = st.number_input("Número estimado de asistentes", min_value=0, step=1)
                    col_e1, col_e2, col_e3 = st.columns(3)
                    mujeres  = col_e1.number_input("% Mujeres est.", min_value=0, max_value=100, step=1)
                    tercera  = col_e2.number_input("% 3ra edad est.", min_value=0, max_value=100, step=1)
                    ninos    = col_e3.number_input("% Niños est.",    min_value=0, max_value=100, step=1)

                    caja_central   = st.selectbox("¿Quién administra la 🏦 Caja Central Aucca para este evento?", AUCCANES)
                    check_confirmo = st.checkbox("Confirmo que revisé las cuentas, saldos, y que realizaré las inyecciones a Finanzas", value=False)

                    if st.form_submit_button("☠️ CERRAR EVENTO E INYECTAR A FINANZAS", type="primary", use_container_width=True):
                        if not check_confirmo:
                            st.error("Debes marcar la casilla de confirmación.")
                        else:
                            _marcar_cerrado(seleccion, asistentes, mujeres, tercera, ninos)
                            _ejecutar_cierre(
                                seleccion, evento_sel_data["Nombre"],
                                pagos_por_persona, gastos_por_persona, traspasos,
                                asistentes, mujeres, tercera, ninos,
                                caja_central, usuario_actual
                            )
                            st.rerun()


# ==========================================
# Funciones de Modificación en GSheets
# ==========================================

def _marcar_borrado(event_id):
    ws      = _open_ws("evt_eventos")
    records = ws.get_all_records()
    for i, r in enumerate(records):
        if str(r.get("ID")) == event_id:
            idx_estado = SHEETS_CONFIG["evt_eventos"].index("Estado") + 1
            ws.update_cell(i + 2, idx_estado, "Borrado")
            _load_evt_df.clear()
            return

def _actualizar_evento(event_id, nombre, desc, tipo, fecha, modo):
    ws      = _open_ws("evt_eventos")
    records = ws.get_all_records()
    hdrs    = SHEETS_CONFIG["evt_eventos"]
    for i, r in enumerate(records):
        if str(r.get("ID")) == event_id:
            row_excel = i + 2
            updates = [
                gspread.Cell(row=row_excel, col=hdrs.index("Nombre") + 1,        value=nombre),
                gspread.Cell(row=row_excel, col=hdrs.index("Detalles_Ficha") + 1, value=desc),
                gspread.Cell(row=row_excel, col=hdrs.index("Tipo") + 1,          value=tipo),
                gspread.Cell(row=row_excel, col=hdrs.index("Fecha") + 1,         value=fecha),
                gspread.Cell(row=row_excel, col=hdrs.index("Modo") + 1,          value=modo),
            ]
            ws.update_cells(updates)
            _load_evt_df.clear()
            return

def _renombrar_evento(event_id, nuevo_nombre):
    """Retrocompatibilidad — usa _actualizar_evento en su lugar."""
    ws      = _open_ws("evt_eventos")
    records = ws.get_all_records()
    for i, r in enumerate(records):
        if str(r.get("ID")) == event_id:
            idx_nombre = SHEETS_CONFIG["evt_eventos"].index("Nombre") + 1
            ws.update_cell(i + 2, idx_nombre, nuevo_nombre)
            _load_evt_df.clear()
            return

def _anular_evento_y_finanzas(event_id, event_name):
    ws_evt = _open_ws("evt_eventos")
    for i, r in enumerate(ws_evt.get_all_records()):
        if str(r.get("ID")) == event_id:
            idx_estado = SHEETS_CONFIG["evt_eventos"].index("Estado") + 1
            ws_evt.update_cell(i + 2, idx_estado, "Anulado")
            _load_evt_df.clear()
            break

    try:
        ws_fin      = _open_ws(HOJA)
        headers_fin = ws_fin.row_values(1)
        if "Anulado" in headers_fin:
            idx_anu     = headers_fin.index("Anulado") + 1
            records_fin = ws_fin.get_all_records()
            updates     = []
            for i, r in enumerate(records_fin):
                detalle = str(r.get("Detalle", ""))
                if event_name in detalle and (detalle.startswith("Ventas en") or
                                               detalle.startswith("Insumo en") or
                                               detalle.startswith("Liquidación x")):
                    updates.append(gspread.Cell(row=i + 2, col=idx_anu, value="TRUE"))
            if updates:
                ws_fin.update_cells(updates)
    except Exception as e:
        st.error(f"Error al intentar anular en Finanzas: {e}")

def _marcar_cerrado(event_id, a, m, t, n=0):
    ws      = _open_ws("evt_eventos")
    records = ws.get_all_records()
    hdrs    = SHEETS_CONFIG["evt_eventos"]
    for i, r in enumerate(records):
        if str(r.get("ID")) == event_id:
            row_excel = i + 2
            now_str   = pd.Timestamp.now(tz=STGO).strftime("%Y-%m-%d %H:%M:%S")
            updates   = [
                gspread.Cell(row=row_excel, col=hdrs.index("Estado") + 1,          value="Cerrado"),
                gspread.Cell(row=row_excel, col=hdrs.index("Asistentes") + 1,      value=a),
                gspread.Cell(row=row_excel, col=hdrs.index("Mujeres_Pct") + 1,     value=m),
                gspread.Cell(row=row_excel, col=hdrs.index("TerceraEdad_Pct") + 1, value=t),
                gspread.Cell(row=row_excel, col=hdrs.index("Ninos_Pct") + 1,       value=n),
                gspread.Cell(row=row_excel, col=hdrs.index("ClosedAt") + 1,        value=now_str),
            ]
            ws.update_cells(updates)
            _load_evt_df.clear()
            return

def _ejecutar_cierre(event_id, event_name, pagos_por_persona, gastos_por_persona, traspasos,
                     asis, muj, terc, nin, caja_central, closed_by):
    """Inyección maestra a Finanzas."""
    try:
        ws_fin   = _open_ws(HOJA)
        hdrs_fin = _ensure_sheet_headers(ws_fin)
    except Exception as e:
        st.error(f"Falla conexión finanzas: {e}")
        return

    now            = pd.Timestamp.now(tz=STGO)
    date_str_mov   = now.strftime("%Y-%m-%d")
    date_str_record = now.strftime("%Y-%m-%d %H:%M:%S")
    filas_a_insertar = []

    # 1. Ingresos por Ventas
    for persona, rec in pagos_por_persona.items():
        p_real = persona if persona != "Sin asignar" else caja_central
        if rec > 0 and p_real:
            filas_a_insertar.append([str({
                "ID":              str(uuid.uuid4()), "Tipo": "Ingreso",
                "Detalle":         f"Ventas en {event_name}",
                "Categoría":       "Venta Evento",   "Fecha": date_str_mov,
                "Persona":         p_real,            "Persona_Origen": "",
                "Persona_Destino": "",                "Monto": str(int(rec)),
                "Created_At":      date_str_record,   "Created_By": closed_by, "Anulado": ""
            }.get(h, "")) for h in hdrs_fin])

    # 2. Gastos por Insumos
    for persona, deuda in gastos_por_persona.items():
        p_real = persona if persona != "Sin asignar" else ""
        if deuda > 0:
            filas_a_insertar.append([str({
                "ID":              str(uuid.uuid4()), "Tipo": "Gasto",
                "Detalle":         f"Insumo en {event_name}",
                "Categoría":       "Gasto Insumos",  "Fecha": date_str_mov,
                "Persona":         p_real,            "Persona_Origen": "",
                "Persona_Destino": "",                "Monto": str(int(deuda)),
                "Created_At":      date_str_record,   "Created_By": closed_by, "Anulado": ""
            }.get(h, "")) for h in hdrs_fin])

    # 3. Traspasos P2P
    for t in traspasos:
        dest = caja_central if t["a"] == "🏦 Caja Central Aucca" else t["a"]
        ori  = caja_central if t["de"] == "🏦 Caja Central Aucca" else t["de"]
        if t["monto"] > 0 and ori and dest and ori != dest:
            filas_a_insertar.append([str({
                "ID":              str(uuid.uuid4()), "Tipo": "Traspaso",
                "Detalle":         f"Liquidación x {event_name}",
                "Categoría":       "",               "Fecha": date_str_mov,
                "Persona":         "",               "Persona_Origen": ori,
                "Persona_Destino": dest,             "Monto": str(int(t["monto"])),
                "Created_At":      date_str_record,  "Created_By": closed_by, "Anulado": ""
            }.get(h, "")) for h in hdrs_fin])

    if filas_a_insertar:
        ws_fin.append_rows(filas_a_insertar, value_input_option="USER_ENTERED")
        st.success("Toda la data de liquidación se inyectó a la Bóveda de Aucca.")

    st.balloons()
