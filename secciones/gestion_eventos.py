import streamlit as st
import pandas as pd
import uuid
import datetime as dt
from zoneinfo import ZoneInfo
import gspread  # Importación global — NO duplicar localmente

from secciones.finanzas_aucca import AUCCANES, _open_ws, _ensure_sheet_headers, _a1_range_row, EXPECTED_HEADERS, HOJA, STGO

# ==========================================
# Constantes
# ==========================================
SHEETS_CONFIG = {
    "evt_eventos":    ["ID", "Nombre", "Tipo", "Fecha", "Estado", "Modo", "Asistentes", "Mujeres_Pct", "TerceraEdad_Pct", "Ninos_Pct", "CreatedBy", "CreatedAt", "ClosedAt", "Detalles_Ficha"],
    "evt_productos":  ["EventID", "Nombre", "Precio_Base", "Descripcion", "CreatedBy", "Anulado"],
    "evt_inventario": ["ID", "EventID", "Producto", "Cantidad", "Gasto_Materiales", "Persona_Gasto", "Persona_Registro", "CreatedAt", "Anulado"],
    "evt_ventas":     ["ID", "EventID", "Mesa", "Descripcion_Cuenta", "Producto", "Cantidad", "Precio_Unitario", "Total", "Persona_Registro", "Persona_Cobro", "Estado_Entrega", "Estado_Pago", "Medio_Pago", "CreatedAt", "Anulado"],
    "evt_notas":      ["ID", "EventID", "Persona", "Aprendizaje", "CreatedAt"]
}

SPREADSHEET_KEY = "1C8njkp0RQMdXnxuJvPvfK_pNZHQSi7q7dUPeUg-2624"

# ==========================================
# Helpers de conexión robusta
# ==========================================
def _get_sheet_client():
    """Retorna cliente gspread fresco. Siempre crea nueva auth para evitar tokens vencidos."""
    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_info(
        st.secrets["gspread"],
        scopes=["https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"],
    )
    return gspread.authorize(creds)

def _open_ws_evt(sheet_name: str):
    """Abre worksheet con reconexión automática. Reintenta 2 veces si falla."""
    for intento in range(3):
        try:
            client = _get_sheet_client()
            sh = client.open_by_key(SPREADSHEET_KEY)
            return sh.worksheet(sheet_name)
        except Exception as e:
            if intento == 2:
                raise e

def _get_real_headers(sheet_name: str) -> list[str]:
    """Obtiene los headers REALES del sheet (no los de SHEETS_CONFIG) y agrega los faltantes."""
    ws = _open_ws_evt(sheet_name)
    headers_raw = ws.row_values(1)
    headers = [h.strip() for h in headers_raw]
    expected = SHEETS_CONFIG.get(sheet_name, [])
    missing = [h for h in expected if h not in headers]
    if missing:
        new_headers = headers + missing
        ws.update(_a1_range_row(1, len(new_headers)), [new_headers])
        return new_headers
    return headers

def _col_idx(headers: list[str], col_name: str) -> int:
    """Retorna el índice 1-based de una columna según los headers REALES del sheet."""
    return headers.index(col_name) + 1

# ==========================================
# Cache de datos (TTL 30s)
# ==========================================
@st.cache_data(ttl=30)
def _load_evt_df(sheet_name: str) -> pd.DataFrame:
    """Carga los datos de una hoja como dataframe. Reconecta si hay error."""
    try:
        ws      = _open_ws_evt(sheet_name)
        headers = _get_real_headers(sheet_name)
        values  = ws.get_all_values()
    except Exception as e:
        st.warning(f"⚠️ Error al leer '{sheet_name}': {e}. Usa el botón 🔄 para reconectar.")
        return pd.DataFrame(columns=SHEETS_CONFIG.get(sheet_name, []))

    if not values:
        return pd.DataFrame(columns=headers)
    rows = values[1:]
    norm_rows = [r[:len(headers)] + [""] * max(0, len(headers) - len(r)) for r in rows]
    df = pd.DataFrame(norm_rows, columns=headers)
    if not df.empty and "CreatedAt" in df.columns:
        df["_dt"] = pd.to_datetime(df["CreatedAt"], errors="coerce")
        df = df.sort_values("_dt", ascending=False).drop(columns=["_dt"])
    return df

def _save_evt_row(sheet_name: str, row_dict: dict):
    ws      = _open_ws_evt(sheet_name)
    headers = _get_real_headers(sheet_name)
    row_out = [str(row_dict.get(h, "")) for h in headers]
    ws.append_row(row_out, value_input_option="USER_ENTERED")
    _load_evt_df.clear()

def _batch_update(sheet_name: str, updates: list):
    """Ejecuta update_cells con reconexión si el token expiró."""
    ws = _open_ws_evt(sheet_name)
    ws.update_cells(updates)
    _load_evt_df.clear()

# ==========================================
# Render Principal
# ==========================================
def render():
    col_t, col_btn = st.columns([5, 1])
    with col_t:
        st.markdown("## 🎉 Gestión de Eventos y Actividades")
    with col_btn:
        if st.button("🔄 Reconectar BD", help="Fuerza reconexión y limpia el caché si la app quedó sin datos", use_container_width=True):
            _load_evt_df.clear()
            st.cache_data.clear()
            st.success("Caché limpiado. Recargando...")
            st.rerun()

    usuario_actual = st.session_state.get("current_user", "Administrador")

    df_eventos = _load_evt_df("evt_eventos")
    eventos_abiertos = df_eventos[df_eventos["Estado"] == "Abierto"] if not df_eventos.empty else pd.DataFrame()

    with st.sidebar:
        st.markdown("---")
        with st.expander("➕ Crear Nuevo Evento", expanded=False):
            with st.form("form_nuevo_evento"):
                nombre_ev   = st.text_input("Nombre del Evento")
                tipo_ev     = st.selectbox("Tipo", ["Evento / Fiesta", "Almuerzo / Cena", "Visita", "Taller"])
                fecha_ev    = st.date_input("Fecha de Realización", dt.date.today())
                detalles_ev = st.text_area("Ficha del Evento", height=80)
                modo_ev     = st.radio("Modo", ["pro", "simple"], horizontal=True,
                                       help="Pro: con sección Entregas. Simple: sin entregas.")
                if st.form_submit_button("Crear Evento", type="primary", use_container_width=True):
                    if nombre_ev.strip():
                        now      = pd.Timestamp.now(tz=STGO)
                        nuevo_id = str(uuid.uuid4())
                        _save_evt_row("evt_eventos", {
                            "ID": nuevo_id, "Nombre": nombre_ev.strip(), "Tipo": tipo_ev,
                            "Fecha": fecha_ev.strftime("%Y-%m-%d"), "Estado": "Abierto", "Modo": modo_ev,
                            "CreatedBy": usuario_actual, "CreatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
                            "Detalles_Ficha": detalles_ev.strip()
                        })
                        st.session_state["evento_activo_id"] = nuevo_id
                        st.success("Evento creado")
                        st.rerun()

    # Selector de evento
    event_options = {"": "Selecciona un evento activo..."}
    if not eventos_abiertos.empty:
        for _, row in eventos_abiertos.iterrows():
            event_options[row["ID"]] = f"🟢 {row['Nombre']} ({row['Fecha']})"
    eventos_cerrados = df_eventos[df_eventos["Estado"] == "Cerrado"] if not df_eventos.empty else pd.DataFrame()
    if not eventos_cerrados.empty:
        for _, row in eventos_cerrados.iterrows():
            event_options[row["ID"]] = f"🔒 {row['Nombre']} ({row['Fecha']})"

    keys_list   = list(event_options.keys())
    saved_id    = st.session_state.get("evento_activo_id", "")
    current_idx = keys_list.index(saved_id) if saved_id in keys_list else 0

    seleccion = st.selectbox("Evento Activo", options=keys_list,
                             format_func=lambda x: event_options[x], index=current_idx)
    if seleccion != saved_id:
        st.session_state["evento_activo_id"] = seleccion
        st.rerun()
    if not seleccion:
        st.info("👈 Selecciona o crea un evento para comenzar.")
        return

    evento_sel_data = df_eventos[df_eventos["ID"] == seleccion].iloc[0]
    es_cerrado      = evento_sel_data["Estado"] == "Cerrado"

    # modo_evento: leer desde session_state (se actualiza inmediatamente al guardar)
    # con el valor del sheet como referencia inicial.
    modo_sheet = str(evento_sel_data.get("Modo", "")).strip().lower()
    if modo_sheet not in ("simple", "pro"):
        modo_sheet = "pro"  # default si la columna no existe aún o está vacía
    # session_state tiene prioridad si el usuario acaba de cambiar el modo en esta sesión
    modo_evento = st.session_state.get(f"modo_evento_{seleccion}", modo_sheet)
    if modo_evento not in ("simple", "pro"):
        modo_evento = "pro"

    if es_cerrado:
        st.warning("🔒 **Este evento está CERRADO.** Solo puedes visualizar la información.")

    st.markdown("---")

    # Cargar datos del evento — usar .copy() para evitar SettingWithCopyWarning
    df_inv  = _load_evt_df("evt_inventario")
    df_ven  = _load_evt_df("evt_ventas")
    df_prod = _load_evt_df("evt_productos")

    # Filtrar y crear copias independientes (CRÍTICO: sin .copy() las asignaciones de columnas fallan)
    def _safe_filter(df, cond_cols: dict, schema_key: str) -> pd.DataFrame:
        """Filtra un df por condiciones, retorna copia segura o DataFrame vacío."""
        if df.empty:
            return pd.DataFrame(columns=SHEETS_CONFIG[schema_key])
        mask = pd.Series(True, index=df.index)
        for col, val in cond_cols.items():
            if col in df.columns:
                mask &= (df[col] == val)
        return df[mask].copy()

    df_inv_act  = _safe_filter(df_inv,  {"EventID": seleccion, "Anulado": ""}, "evt_inventario")
    # Para Anulado: excluir filas marcadas TRUE (puede ser "", "False", None — solo excluir "TRUE")
    if not df_inv.empty:
        mask_inv = (df_inv["EventID"] == seleccion) & (df_inv["Anulado"].astype(str).str.upper() != "TRUE")
        df_inv_act = df_inv[mask_inv].copy()
    else:
        df_inv_act = pd.DataFrame(columns=SHEETS_CONFIG["evt_inventario"])

    if not df_ven.empty:
        mask_ven = (df_ven["EventID"] == seleccion) & (df_ven["Anulado"].astype(str).str.upper() != "TRUE")
        df_ven_act = df_ven[mask_ven].copy()
    else:
        df_ven_act = pd.DataFrame(columns=SHEETS_CONFIG["evt_ventas"])

    if not df_prod.empty:
        mask_prod = (df_prod["EventID"] == seleccion) & (df_prod["Anulado"].astype(str).str.upper() != "TRUE")
        df_prod_act = df_prod[mask_prod].copy()
    else:
        df_prod_act = pd.DataFrame(columns=SHEETS_CONFIG["evt_productos"])

    # Pre-calcular columnas numéricas UNA SOLA VEZ (evita asignaciones en slices)
    df_ven_act["Total_Num"] = pd.to_numeric(df_ven_act.get("Total", pd.Series(dtype=float)), errors="coerce").fillna(0)
    df_inv_act["Gasto_Num"] = pd.to_numeric(df_inv_act.get("Gasto_Materiales", pd.Series(dtype=float)), errors="coerce").fillna(0)

    # Mapa de precios (desde evt_productos — fuente de verdad)
    price_map = {}
    if not df_prod_act.empty:
        for _, r in df_prod_act.iterrows():
            try:    price_map[r["Nombre"]] = int(r["Precio_Base"])
            except: price_map[r["Nombre"]] = 0

    # Stock
    def _calcular_stock():
        res = {}
        if not df_inv_act.empty:
            inv = df_inv_act.copy()
            inv["Cantidad"] = pd.to_numeric(inv["Cantidad"], errors="coerce").fillna(0)
            res = inv.groupby("Producto")["Cantidad"].sum().to_dict()
        if not df_ven_act.empty:
            ven = df_ven_act.copy()
            ven["Cantidad"] = pd.to_numeric(ven["Cantidad"], errors="coerce").fillna(0)
            for prod, q in ven.groupby("Producto")["Cantidad"].sum().items():
                res[prod] = res.get(prod, 0) - q
        return res

    stock_actual = _calcular_stock()

    # Tabs — construir según modo. Forzar reset si el modo cambió
    if modo_evento == "simple":
        tab_options = ["⚙️ Información General", "🛒 Punto de Venta (Caja)", "🍳 Gasto y Producción", "🧠 Aprendizajes", "🏁 Transacciones / Cierre"]
    else:
        tab_options = ["⚙️ Información General", "🛒 Punto de Venta (Caja)", "🍳 Gasto y Producción", "🏃 Entregas", "🧠 Aprendizajes", "🏁 Transacciones / Cierre"]

    # Si el tab activo no está en las opciones disponibles (ej: modo cambió de pro a simple),
    # eliminarlo del estado para que st.radio use su valor por defecto (el primero).
    tab_key = f"tab_evt_{seleccion}"
    if tab_key in st.session_state and st.session_state[tab_key] not in tab_options:
        del st.session_state[tab_key]

    active_tab = st.radio("Sección del Evento", tab_options, horizontal=True,
                          label_visibility="collapsed", key=tab_key)

    # ==========================================
    # TAB 0: Información General
    # ==========================================
    if active_tab == tab_options[0]:
        st.markdown(f"### ⚙️ {evento_sel_data['Nombre']}")
        c_i1, c_i2, c_i3 = st.columns(3)
        c_i1.metric("Fecha Registro",    str(evento_sel_data["CreatedAt"]).split(" ")[0])
        c_i2.metric("Fecha Realización", str(evento_sel_data["Fecha"]))
        c_i3.metric("Fecha Cierre",
                    str(evento_sel_data.get("ClosedAt", "")) if pd.notna(evento_sel_data.get("ClosedAt")) and evento_sel_data.get("ClosedAt") else "Activo")

        modo_badge = "🟢 Modo Pro (con Entregas)" if modo_evento == "pro" else "🟡 Modo Simple (sin Entregas)"
        st.markdown(f"**Modo actual:** {modo_badge}")

        detalles_texto = str(evento_sel_data.get("Detalles_Ficha", ""))
        if detalles_texto and detalles_texto != "nan":
            st.info(f"**📖 Ficha del Evento:**\n\n{detalles_texto}")

        # Edición completa del evento
        with st.expander("✏️ Editar Configuración del Evento", expanded=False):
            with st.form("form_edit_evento"):
                nuevo_nombre = st.text_input("Nombre del Evento", value=str(evento_sel_data["Nombre"]))
                nueva_desc   = st.text_area("Descripción / Ficha", value=str(evento_sel_data.get("Detalles_Ficha", "")), height=100)
                tipo_opts    = ["Evento / Fiesta", "Almuerzo / Cena", "Visita", "Taller"]
                tipo_actual  = str(evento_sel_data.get("Tipo", "Evento / Fiesta"))
                tipo_idx     = tipo_opts.index(tipo_actual) if tipo_actual in tipo_opts else 0
                nuevo_tipo   = st.selectbox("Tipo", tipo_opts, index=tipo_idx)
                try:
                    fecha_val  = pd.to_datetime(evento_sel_data["Fecha"]).date()
                except Exception:
                    fecha_val  = dt.date.today()
                nueva_fecha  = st.date_input("Fecha de Realización", value=fecha_val)
                modo_idx     = 0 if modo_evento == "pro" else 1
                nuevo_modo   = st.radio("Modo del Evento", ["pro", "simple"], index=modo_idx, horizontal=True,
                                        help="Pro: incluye sección Entregas. Simple: sin entregas (POS rápido).")

                if st.form_submit_button("💾 Guardar Configuración", type="primary", use_container_width=True):
                    _actualizar_evento(seleccion, nuevo_nombre.strip(), nueva_desc.strip(),
                                       nuevo_tipo, nueva_fecha.strftime("%Y-%m-%d"), nuevo_modo)
                    # Actualizar session_state inmediatamente para que la UI refleje el nuevo modo
                    st.session_state[f"modo_evento_{seleccion}"] = nuevo_modo
                    # Resetear tab activo usando 'del' para evitar StreamlitAPIException
                    tab_key = f"tab_evt_{seleccion}"
                    if tab_key in st.session_state:
                        del st.session_state[tab_key]
                    st.success("✅ Configuración guardada correctamente.")
                    st.rerun()

        # Acciones destructivas
        with st.expander("⚠️ Acciones de Eliminación", expanded=False):
            if es_cerrado:
                st.warning("⚠️ Este evento ya fue inyectado a Finanzas. Al anularlo se anularán sus transacciones.")
                if st.button("🚫 Anular Evento y Registros en Finanzas", type="primary"):
                    _anular_evento_y_finanzas(seleccion, str(evento_sel_data["Nombre"]))
                    st.session_state["evento_activo_id"] = ""
                    st.success("Evento anulado.")
                    st.rerun()
            else:
                st.info("Eliminar borrará este evento permanentemente.")
                if st.button("🗑️ Eliminar Evento", type="primary"):
                    _marcar_borrado(seleccion)
                    st.session_state["evento_activo_id"] = ""
                    st.success("Evento borrado.")
                    st.rerun()

        st.markdown("---")
        st.markdown("#### 📋 Catálogo de Productos y Precios")
        st.caption("Añade productos, fija precios y descripción. **El nombre del producto es la llave única** — si lo renombras aquí, se actualizará en todas las tablas (ventas, inventario).")

        if not es_cerrado:
            with st.container(border=True):
                st.markdown("##### ➕ Agregar Nuevo Producto")
                with st.form("form_crear_producto", clear_on_submit=True):
                    col_n1, col_n2 = st.columns([2, 1])
                    nuevo_p      = col_n1.text_input("Nombre del Producto", placeholder="Ej: Pizza Napolitana")
                    nuevo_v      = col_n2.number_input("Precio Venta (CLP)", min_value=0, step=100)
                    nuevo_desc_p = st.text_input("Descripción / Comentario (opcional)", placeholder="Ej: Sin gluten, grande")
                    if st.form_submit_button("Añadir al Menú", use_container_width=True):
                        if nuevo_p.strip():
                            if nuevo_p.strip() not in price_map:
                                _save_evt_row("evt_productos", {
                                    "EventID": seleccion, "Nombre": nuevo_p.strip(),
                                    "Precio_Base": str(int(nuevo_v)), "Descripcion": nuevo_desc_p.strip(),
                                    "CreatedBy": usuario_actual, "Anulado": ""
                                })
                                st.success("Producto creado.")
                                st.rerun()
                            else:
                                st.error("Este producto ya existe.")

            st.markdown("##### ✏️ Editar / Eliminar Productos")
            if not df_prod_act.empty:
                df_edit_prod = pd.DataFrame([{
                    "_orig_nombre": r["Nombre"],
                    "Nombre":       r["Nombre"],
                    "Precio":       int(price_map.get(r["Nombre"], 0)),
                    "Descripcion":  str(r.get("Descripcion", "")),
                    "Eliminar":     False
                } for _, r in df_prod_act.iterrows()])

                with st.form("form_edit_productos"):
                    st.caption("Edita directamente en la tabla. ⚠️ Si renombras un producto, **se actualizará en todas las cuentas y el inventario** para mantener coherencia.")
                    edited_prod = st.data_editor(
                        df_edit_prod.drop(columns=["_orig_nombre"]),
                        column_config={
                            "Nombre":      st.column_config.TextColumn("Producto", disabled=False),
                            "Precio":      st.column_config.NumberColumn("Precio ($)", min_value=0, step=100),
                            "Descripcion": st.column_config.TextColumn("Descripción"),
                            "Eliminar":    st.column_config.CheckboxColumn("🗑️ Eliminar", default=False)
                        },
                        hide_index=True, use_container_width=True
                    )

                    if st.form_submit_button("💾 Guardar Cambios en Productos", type="primary", use_container_width=True):
                        orig_names = list(df_edit_prod["_orig_nombre"])
                        _actualizar_productos(seleccion, orig_names, edited_prod)
                        st.rerun()
            else:
                st.info("No hay productos registrados aún.")



    # ==========================================
    # TAB 1: Punto de Venta
    # ==========================================
    if active_tab == tab_options[1]:
        st.markdown(f"### 🛒 Administrar Cuentas / Mesas — {evento_sel_data['Nombre']}")

        if not es_cerrado:
            with st.expander("➕ Abrir Nueva Cuenta", expanded=False):
                with st.form("form_nueva_cuenta", clear_on_submit=True):
                    nueva_mesa      = st.text_input("Nombre de la cuenta / Mesa", placeholder="Ej: Mesa Juan")
                    nueva_mesa_desc = st.text_input("Descripción / Comentario (opcional)")
                    if st.form_submit_button("Iniciar Cuenta", type="primary"):
                        if nueva_mesa.strip():
                            st.session_state["ultima_mesa"]      = nueva_mesa.strip()
                            st.session_state["ultima_mesa_desc"] = nueva_mesa_desc.strip()
                            st.success("Cuenta lista para usar.")

            with st.expander("📦 Visor de Stock Disponible", expanded=False):
                if stock_actual:
                    df_s = pd.DataFrame([{"Producto": p, "Precio": f"${price_map.get(p, 0):,.0f}", "Stock": s}
                                         for p, s in stock_actual.items() if s > 0])
                    st.dataframe(df_s, use_container_width=True, hide_index=True)
                else:
                    st.info("No hay stock disponible aún.")

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
                            st.warning("No hay productos con stock disponibles.")
                            sel_prod = ""; cant = 0; precio_ingresado = 0
                        else:
                            sel_prod         = st.selectbox("Producto", [f"{p} (Stock: {stock_actual[p]:.0f})" for p in prods_disp])
                            cant             = st.number_input("Cantidad", min_value=1, step=1)
                            precio_ingresado = st.number_input("Precio Especial (CLP, 0 = catálogo)", min_value=0, step=100, value=0)

                        if st.form_submit_button("Añadir a la Cuenta", type="primary", use_container_width=True):
                            prod_clean   = sel_prod.split(" (Stock:")[0] if sel_prod else ""
                            precio_final = precio_ingresado if precio_ingresado > 0 else price_map.get(prod_clean, 0)
                            if sel_mesa and prod_clean and cant > 0:
                                if stock_actual.get(prod_clean, 0) < cant:
                                    st.error(f"⚠️ Stock insuficiente. Quedan {stock_actual.get(prod_clean, 0)}.")
                                else:
                                    now = pd.Timestamp.now(tz=STGO)
                                    _save_evt_row("evt_ventas", {
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
                                    })
                                    st.session_state["ultima_mesa"] = sel_mesa.strip()
                                    st.success(f"✅ Añadido a {sel_mesa}")
                                    st.rerun()

            with c2:
                st.markdown("#### 💳 Resumen y Cobro de Mesas")
                if not df_ven_act.empty:
                    df_ven_act["Total_Num"] = pd.to_numeric(df_ven_act["Total"], errors="coerce").fillna(0)
                    df_pendientes = df_ven_act[df_ven_act["Estado_Pago"] == "Pendiente"]
                    agrupado_pagar = df_pendientes.groupby("Mesa")["Total_Num"].sum().reset_index()

                    if agrupado_pagar.empty:
                        st.info("Todas las cuentas están pagadas 😊.")
                    else:
                        for _, rmesa in agrupado_pagar.iterrows():
                            mesa  = rmesa["Mesa"]
                            total = rmesa["Total_Num"]
                            with st.expander(f"🧾 **{mesa}** — ${total:,.0f}"):
                                det_mesa   = df_pendientes[df_pendientes["Mesa"] == mesa].copy()
                                df_to_edit = det_mesa[["ID", "Producto", "Precio_Unitario", "Cantidad"]].copy()
                                df_to_edit["Cantidad"]       = pd.to_numeric(df_to_edit["Cantidad"],       errors="coerce").fillna(1).astype(int)
                                df_to_edit["Precio_Unitario"] = pd.to_numeric(df_to_edit["Precio_Unitario"], errors="coerce").fillna(0).astype(int)
                                df_to_edit["Eliminar"]       = False

                                st.caption("Modifica cantidades o elimina ítems. Presiona Guardar para confirmar.")
                                with st.form(f"form_editor_{mesa}"):
                                    edited_mesa_df = st.data_editor(
                                        df_to_edit,
                                        column_config={
                                            "ID":              None,
                                            "Producto":        st.column_config.TextColumn("Ítem", disabled=True),
                                            "Precio_Unitario": st.column_config.NumberColumn("P. Unit ($)", disabled=True),
                                            "Cantidad":        st.column_config.NumberColumn("Cant.", min_value=1, step=1),
                                            "Eliminar":        st.column_config.CheckboxColumn("🗑️ Quitar", default=False)
                                        },
                                        hide_index=True, use_container_width=True
                                    )
                                    tot_proyectado = sum([r["Cantidad"] * r["Precio_Unitario"]
                                                         for _, r in edited_mesa_df.iterrows() if not r["Eliminar"]])
                                    st.markdown(f"**Total Proyectado: ${tot_proyectado:,.0f}**")

                                    if st.form_submit_button("💾 Guardar Ajustes", type="primary"):
                                        _actualizar_ventas_mesa(edited_mesa_df)
                                        st.rerun()

                                st.markdown("---")
                                with st.form(f"form_cobro_{mesa}"):
                                    medio_pago  = st.selectbox("Medio de Pago", ["Transferencia", "Efectivo"])
                                    quien_cobra = st.selectbox("¿Hacia quién fue la plata?", AUCCANES,
                                                               index=AUCCANES.index(usuario_actual) if usuario_actual in AUCCANES else 0)

                                    if modo_evento == "pro":
                                        todo_entregado = all(str(e) == "Entregado" for e in det_mesa["Estado_Entrega"])
                                        if not todo_entregado:
                                            st.warning("⚠️ Hay productos sin entregar. Ve a 'Entregas' primero.")
                                            st.form_submit_button("Pago bloqueado", disabled=True)
                                            puede_cobrar = False
                                        else:
                                            puede_cobrar = True
                                    else:
                                        puede_cobrar = True

                                    if puede_cobrar:
                                        if st.form_submit_button(f"💸 Confirmar Pago — {mesa}", type="primary"):
                                            _confirmar_pago_mesa(seleccion, mesa, medio_pago, quien_cobra, modo_evento)
                                            st.rerun()
                else:
                    st.info("Aún no hay ventas registradas.")

        if not df_ven_act.empty:
            st.markdown("---")
            st.markdown("##### 📜 Historial de Caja")
            df_ven_act["Total_Num"] = pd.to_numeric(df_ven_act["Total"], errors="coerce").fillna(0)
            cols_view = ["CreatedAt", "Mesa", "Producto", "Cantidad", "Total_Num", "Estado_Pago", "Persona_Registro"]
            if modo_evento == "pro":
                cols_view.insert(-1, "Estado_Entrega")
            df_hist = df_ven_act[cols_view].rename(columns={"Total_Num": "Total CLP", "Persona_Registro": "Vendedor"})
            st.dataframe(df_hist, use_container_width=True)

    # ==========================================
    # TAB 2: Gasto y Producción
    # ==========================================
    if active_tab == tab_options[2]:
        st.markdown(f"### 🍳 Gastos y Producción — {evento_sel_data['Nombre']}")

        if not es_cerrado:
            col_l, col_r = st.columns(2)
            with col_l:
                with st.expander("💸 1. Reportar Gasto de Bolsillo", expanded=True):
                    with st.form("form_gastos", clear_on_submit=True):
                        motivo_gasto  = st.text_input("¿Qué se compró?", placeholder="Ej: Supermercado, Gas")
                        gasto_valor   = st.number_input("💰 Valor Costo (CLP)", min_value=100, step=100)
                        persona_gasto = st.selectbox("¿Quién pagó?", [""] + AUCCANES,
                                                     index=AUCCANES.index(usuario_actual) + 1 if usuario_actual in AUCCANES else 0)
                        if st.form_submit_button("Registrar Gasto", type="primary", use_container_width=True):
                            if motivo_gasto.strip() and persona_gasto:
                                now = pd.Timestamp.now(tz=STGO)
                                _save_evt_row("evt_inventario", {
                                    "ID":               str(uuid.uuid4()), "EventID": seleccion,
                                    "Producto":         f"[Gasto] {motivo_gasto.strip()}",
                                    "Cantidad":         "0", "Gasto_Materiales": str(int(gasto_valor)),
                                    "Persona_Gasto":    persona_gasto, "Persona_Registro": usuario_actual,
                                    "CreatedAt":        now.strftime("%Y-%m-%d %H:%M:%S"), "Anulado": ""
                                })
                                st.success("Gasto registrado.")
                                st.rerun()
                            else:
                                st.error("Indica qué se compró y quién pagó.")

            with col_r:
                with st.expander("🍔 2. Reportar Elaboración de Oferta", expanded=True):
                    with st.form("form_inventario", clear_on_submit=True):
                        lista_prod = sorted(df_prod_act["Nombre"].unique()) if not df_prod_act.empty else []
                        sel_cat    = st.selectbox("Producto a Fabricar", [""] + lista_prod)
                        nuevo_prod = st.text_input("O Crear Nuevo Producto", placeholder="Ej: Muffin")
                        cantidad   = st.number_input("📦 Cantidad Elaborada", min_value=1, step=1)
                        if st.form_submit_button("Sumar al Inventario", type="primary", use_container_width=True):
                            prod_final = nuevo_prod.strip() if nuevo_prod.strip() else sel_cat
                            if prod_final and cantidad > 0:
                                if prod_final not in lista_prod:
                                    _save_evt_row("evt_productos", {
                                        "EventID": seleccion, "Nombre": prod_final,
                                        "Precio_Base": "0", "CreatedBy": usuario_actual, "Anulado": ""
                                    })
                                now = pd.Timestamp.now(tz=STGO)
                                _save_evt_row("evt_inventario", {
                                    "ID":               str(uuid.uuid4()), "EventID": seleccion,
                                    "Producto":         prod_final, "Cantidad": str(int(cantidad)),
                                    "Gasto_Materiales": "0", "Persona_Gasto": "",
                                    "Persona_Registro": usuario_actual,
                                    "CreatedAt":        now.strftime("%Y-%m-%d %H:%M:%S"), "Anulado": ""
                                })
                                st.success(f"✅ {cantidad}x {prod_final} sumados al stock.")
                                st.rerun()
                            else:
                                st.error("Indica un producto válido y cantidad.")

        if not df_inv_act.empty:
            st.markdown("#### 📋 Histórico de Operaciones")
            df_inv_view = df_inv_act[["CreatedAt", "Persona_Registro", "Producto", "Cantidad", "Gasto_Materiales", "Persona_Gasto"]].copy()
            df_inv_view["Gasto_Materiales"] = pd.to_numeric(df_inv_view["Gasto_Materiales"], errors="coerce").fillna(0)
            st.dataframe(df_inv_view, use_container_width=True, hide_index=True)

        # Editar Stock disponible (Movido de Tab 0 a Tab 2)
        st.markdown("---")
        st.markdown("#### 📦 Editar Stock Disponible (Inventario)")
        st.caption("¿Anotaste mal una cantidad producida? Puedes corregirla aquí abajo:")
        if not df_inv_act.empty:
            # Filtrar los que tienen cantidad > 0 (producción real, no gastos)
            df_inv_stock = df_inv_act[pd.to_numeric(df_inv_act["Cantidad"], errors="coerce").fillna(0) > 0].copy()
            if not df_inv_stock.empty:
                df_stock_edit = df_inv_stock[["ID", "Producto", "Cantidad", "Persona_Registro", "CreatedAt"]].copy()
                df_stock_edit["Cantidad"] = pd.to_numeric(df_stock_edit["Cantidad"], errors="coerce").fillna(0).astype(int)
                with st.form("form_edit_stock"):
                    edited_stock = st.data_editor(
                        df_stock_edit,
                        column_config={
                            "ID":               None,
                            "Producto":         st.column_config.TextColumn("Producto", disabled=True),
                            "Cantidad":         st.column_config.NumberColumn("Cantidad", min_value=0, step=1),
                            "Persona_Registro": st.column_config.TextColumn("Registrado por", disabled=True),
                            "CreatedAt":        st.column_config.TextColumn("Fecha", disabled=True),
                        },
                        hide_index=True, use_container_width=True
                    )
                    if st.form_submit_button("💾 Guardar Cambios de Stock", type="primary", use_container_width=True):
                        _actualizar_stock(df_stock_edit, edited_stock)
                        st.rerun()
            else:
                st.info("No hay entradas de producción para editar.")
        else:
            st.info("No hay inventario registrado aún.")

    # ==========================================
    # TAB 3: Entregas (solo Modo Pro)
    # ==========================================
    if modo_evento == "pro" and active_tab == "🏃 Entregas":
        st.markdown("### 🏃 Entregas Pendientes a Clientes")
        if df_ven_act.empty:
            st.info("Aún no hay ventas anotadas.")
        else:
            df_pend = df_ven_act[df_ven_act["Estado_Entrega"] == "Pendiente"]
            if df_pend.empty:
                st.success("¡Todo está entregado!")
            else:
                for _, rpend in df_pend.iterrows():
                    m = rpend["Mesa"]; p = rpend["Producto"]
                    c = rpend["Cantidad"]; vp = rpend["Estado_Pago"]
                    bg = "#f9f9f9" if vp == "Pagado" else "#fff4e5"
                    border = "#48bb78" if vp == "Pagado" else "#ed8936"
                    st.markdown(f"""
                    <div style="background:{bg};padding:10px;border-left:4px solid {border};margin-bottom:10px;border-radius:4px;">
                        <strong>{c}x {p}</strong> para <em>{m}</em> (Pago: {vp})
                    </div>
                    """, unsafe_allow_html=True)
                    if not es_cerrado and st.button("✅ Marcar Entregado", key=f"entrega_{rpend['ID']}", use_container_width=True):
                        _marcar_entregado(rpend["ID"])
                        st.rerun()

    # ==========================================
    # TAB Aprendizajes
    # ==========================================
    if active_tab == "🧠 Aprendizajes":
        st.markdown("### 🧠 Aprendizajes de la Jornada")
        df_not     = _load_evt_df("evt_notas")
        df_not_act = df_not[df_not["EventID"] == seleccion] if not df_not.empty else pd.DataFrame(columns=SHEETS_CONFIG["evt_notas"])

        if not es_cerrado:
            with st.form("form_notas", clear_on_submit=True):
                nota = st.text_area("Cuéntame...", height=100)
                if st.form_submit_button("Guardar Reflexión", type="primary"):
                    if nota.strip():
                        now = pd.Timestamp.now(tz=STGO)
                        _save_evt_row("evt_notas", {
                            "ID": str(uuid.uuid4()), "EventID": seleccion,
                            "Persona": usuario_actual, "Aprendizaje": nota.strip(),
                            "CreatedAt": now.strftime("%Y-%m-%d %H:%M:%S")
                        })
                        st.success("Guardado.")
                        st.rerun()

        if not df_not_act.empty:
            for _, rn in df_not_act.iterrows():
                st.info(f"**{rn['Persona']}** ({rn['CreatedAt']}):\n\n{rn['Aprendizaje']}")

    # ==========================================
    # TAB Cierre
    # ==========================================
    if active_tab == "🏁 Transacciones / Cierre":
        st.markdown("### 🏁 Cierre del Evento y Cuadratura")
        st.info("Resumen del dinero obtenido, reembolsos y exportación a Finanzas.")

        if df_inv_act.empty and df_ven_act.empty:
            st.warning("No hay transacciones registradas.")
            if not es_cerrado:
                if st.button("Cerrar Evento (Vacío)", type="secondary"):
                    _marcar_cerrado(seleccion, 0, 0, 0)
                    st.rerun()
            return

        # Total_Num y Gasto_Num ya están pre-calculados en la sección de carga de datos
        # (se calculan una sola vez en copias independientes para evitar SettingWithCopyWarning)

        # Filtrar pagadas — asumiremos que cualquier cosa que NO sea "pendiente" ni esté vacía, es plata que entró / se confirmó
        estado_pago_norm = df_ven_act["Estado_Pago"].astype(str).str.strip().str.lower()
        es_pendiente     = estado_pago_norm.isin(["pendiente", ""])
        df_pagadas       = df_ven_act[~es_pendiente].copy()
        df_no_pagadas    = df_ven_act[es_pendiente]
        total_deudas  = df_no_pagadas["Total_Num"].sum()
        total_ventas  = df_ven_act["Total_Num"].sum()

        if not df_pagadas.empty:
            df_pagadas["Persona_Cobro"] = df_pagadas["Persona_Cobro"].astype(str).replace("", "Sin asignar").fillna("Sin asignar")
            pagos_por_persona = df_pagadas.groupby("Persona_Cobro")["Total_Num"].sum().to_dict()
        else:
            pagos_por_persona = {}
        total_recaudado = sum(pagos_por_persona.values())

        df_gastos_reales = df_inv_act[df_inv_act["Gasto_Num"] > 0].copy()
        if not df_gastos_reales.empty:
            df_gastos_reales["Persona_Gasto"] = df_gastos_reales["Persona_Gasto"].astype(str).replace("", "Sin asignar").fillna("Sin asignar")
            gastos_por_persona = df_gastos_reales.groupby("Persona_Gasto")["Gasto_Num"].sum().to_dict()
        else:
            gastos_por_persona = {}
        total_gastado = sum(gastos_por_persona.values())
        utilidad_neta = total_recaudado - total_gastado


        col1, col2, col3 = st.columns(3)
        col1.metric("Total Ventas Registradas",       f"${int(total_ventas):,}".replace(",", "."))
        col2.metric("Ingresos Cobrados",              f"${int(total_recaudado):,}".replace(",", "."))
        col3.metric("Gastos Totales",                 f"${int(total_gastado):,}".replace(",", "."))
        col4, col5 = st.columns(2)
        col4.metric("Utilidad Neta (cobrado − gastos)", f"${int(utilidad_neta):,}".replace(",", "."),
                    delta=f"${int(utilidad_neta):,}".replace(",", "."))
        col5.metric("Pendiente de Cobro",              f"${int(total_deudas):,}".replace(",", "."))

        if pagos_por_persona:
            st.markdown("##### 💰 Detalle por Cobrador")
            st.dataframe(pd.DataFrame([{"Persona": p, "Monto Cobrado": f"${int(v):,}".replace(",", ".")}
                                        for p, v in pagos_por_persona.items()]),
                         use_container_width=True, hide_index=True)

        st.markdown("---")
        if total_deudas > 0:
            st.error(f"⚠️ Hay **${int(total_deudas):,}** en cuentas sin cobrar.".replace(",", "."))

        # Liquidación P2P
        st.markdown("#### 🔄 Liquidación (Traspasos Cruzados)")
        personas = set(list(pagos_por_persona.keys()) + list(gastos_por_persona.keys())) - {"Sin asignar", ""}
        saldos   = {p: pagos_por_persona.get(p, 0) - gastos_por_persona.get(p, 0) for p in personas}
        deudores   = sorted([{"persona": p, "monto": s}     for p, s in saldos.items() if s > 0],  key=lambda x: x["monto"], reverse=True)
        acreedores = sorted([{"persona": p, "monto": abs(s)} for p, s in saldos.items() if s < 0], key=lambda x: x["monto"], reverse=True)
        if utilidad_neta > 0:
            acreedores.append({"persona": "🏦 Caja Central Aucca", "monto": utilidad_neta})

        traspasos = []
        d_i = a_i = 0
        while d_i < len(deudores) and a_i < len(acreedores):
            m = min(deudores[d_i]["monto"], acreedores[a_i]["monto"])
            if m > 0:
                traspasos.append({"de": deudores[d_i]["persona"], "a": acreedores[a_i]["persona"], "monto": int(m)})
            deudores[d_i]["monto"]   -= m
            acreedores[a_i]["monto"] -= m
            if deudores[d_i]["monto"] == 0:   d_i += 1
            if acreedores[a_i]["monto"] == 0: a_i += 1

        with st.container(border=True):
            for t in traspasos:
                st.info(f"➡️ **{t['de']}** debe transferir **${int(t['monto']):,}** a **{t['a']}**".replace(",", "."))
            if not traspasos:
                st.success("Cuentas saldadas.")

        if not es_cerrado:
            st.markdown("---")
            es_demo = "demo" in str(evento_sel_data["Nombre"]).lower()
            if es_demo:
                st.info("💡 **Evento DEMO** — no se inyectará data ficticia en Finanzas.")
                col_d1, col_d2 = st.columns(2)
                if col_d1.button("🗑️ Borrar Demo", use_container_width=True):
                    _marcar_borrado(seleccion)
                    st.session_state["evento_activo_id"] = ""
                    st.rerun()
                if col_d2.button("🔄 Borrar y Crear Nuevo Demo", type="primary", use_container_width=True):
                    _marcar_borrado(seleccion)
                    import scratch_insert_demo
                    nuevo_id = scratch_insert_demo.poblar_datos_demo()
                    st.session_state["evento_activo_id"] = nuevo_id
                    _load_evt_df.clear()
                    st.rerun()
            else:
                st.markdown("##### ⚙️ Formulario Oficial de Cierre")
                with st.form("form_cierre_oficial"):
                    asistentes = st.number_input("Número estimado de asistentes", min_value=0, step=1)
                    e1, e2, e3 = st.columns(3)
                    mujeres = e1.number_input("% Mujeres",   min_value=0, max_value=100, step=1)
                    tercera = e2.number_input("% 3ra edad",  min_value=0, max_value=100, step=1)
                    ninos   = e3.number_input("% Niños",     min_value=0, max_value=100, step=1)
                    caja_central   = st.selectbox("¿Quién administra la 🏦 Caja Central Aucca?", AUCCANES)
                    check_confirmo = st.checkbox("Confirmo que revisé los saldos y ejecutaré las inyecciones a Finanzas", value=False)
                    if st.form_submit_button("☠️ CERRAR EVENTO E INYECTAR A FINANZAS", type="primary", use_container_width=True):
                        if not check_confirmo:
                            st.error("Debes marcar la casilla de confirmación.")
                        else:
                            _marcar_cerrado(seleccion, asistentes, mujeres, tercera, ninos)
                            _ejecutar_cierre(seleccion, str(evento_sel_data["Nombre"]),
                                             pagos_por_persona, gastos_por_persona, traspasos,
                                             asistentes, mujeres, tercera, ninos, caja_central, usuario_actual)
                            st.rerun()


# ==========================================
# Funciones de escritura en Google Sheets
# ==========================================

def _get_records_with_row(ws, hdrs):
    """
    Retorna un iterador de tuplas (row_excel_index, dict_record) 
    usando get_all_values() en lugar de get_all_records(). 
    Evita el salto de filas vacías que rompe el mapeo i+2.
    """
    values = ws.get_all_values()
    res = []
    if len(values) < 2:
        return res
    for i, row_arr in enumerate(values[1:]):
        row_excel = i + 2
        rec = {hdrs[j]: (row_arr[j] if j < len(row_arr) else "") for j in range(len(hdrs))}
        res.append((row_excel, rec))
    return res

def _actualizar_evento(event_id, nombre, desc, tipo, fecha, modo):
    """Actualiza la configuración de un evento usando headers reales del sheet."""
    ws      = _open_ws_evt("evt_eventos")
    hdrs    = ws.row_values(1)  # headers reales
    records = ws.get_all_records(head=1)
    nombre  = nombre.strip() or "Sin nombre"

    # Asegurar que la columna Modo existe
    if "Modo" not in hdrs:
        col_new = len(hdrs) + 1
        hdrs.append("Modo")
        ws.update_cell(1, col_new, "Modo")

    for row_excel, r in _get_records_with_row(ws, hdrs):
        if str(r.get("ID")) == event_id:
            updates   = []
            for field, val in [("Nombre", nombre), ("Detalles_Ficha", desc),
                                ("Tipo", tipo), ("Fecha", fecha), ("Modo", modo)]:
                if field in hdrs:
                    updates.append(gspread.Cell(row=row_excel, col=hdrs.index(field) + 1, value=val))
                else:
                    # Agregar la columna si no existe
                    new_col = len(hdrs) + 1
                    hdrs.append(field)
                    ws.update_cell(1, new_col, field)
                    updates.append(gspread.Cell(row=row_excel, col=new_col, value=val))
            if updates:
                ws.update_cells(updates)
            _load_evt_df.clear()
            return

def _actualizar_productos(event_id, orig_names, edited_df):
    """
    Guarda cambios en productos.
    Si el nombre cambia, cascadea el rename a evt_ventas y evt_inventario.
    """
    ws_prod    = _open_ws_evt("evt_productos")
    hdrs_prod  = ws_prod.row_values(1)
    
    # Índices reales
    def _idx(hdrs, col):
        return hdrs.index(col) + 1 if col in hdrs else None

    idx_nombre = _idx(hdrs_prod, "Nombre")
    idx_precio = _idx(hdrs_prod, "Precio_Base")
    idx_desc   = _idx(hdrs_prod, "Descripcion")
    idx_anu    = _idx(hdrs_prod, "Anulado")

    # Si Descripcion no existe aún, añadirla
    if idx_desc is None:
        new_col = len(hdrs_prod) + 1
        ws_prod.update_cell(1, new_col, "Descripcion")
    idx_desc = _idx(hdrs_prod, "Descripcion")
    
    updates    = []
    renames    = {}

    rows_by_name = {str(r.get("Nombre")): (row_excel, r) for row_excel, r in _get_records_with_row(ws_prod, hdrs_prod)
                    if str(r.get("EventID")) == event_id}

    for orig_name, new_row in zip(orig_names, edited_df.itertuples(index=False)):
        if orig_name not in rows_by_name:
            continue
        excel_row, rec = rows_by_name[orig_name]
        new_nombre    = str(new_row.Nombre).strip()
        new_precio    = int(new_row.Precio) if str(new_row.Precio).strip() else 0
        new_desc      = str(new_row.Descripcion) if hasattr(new_row, "Descripcion") else ""
        eliminar      = bool(new_row.Eliminar)

        if eliminar:
            if idx_anu:
                updates.append(gspread.Cell(row=excel_row, col=idx_anu, value="TRUE"))
        else:
            if new_nombre != orig_name and idx_nombre:
                updates.append(gspread.Cell(row=excel_row, col=idx_nombre, value=new_nombre))
                renames[orig_name] = new_nombre
            cur_precio = str(rec.get("Precio_Base", ""))
            if str(new_precio) != cur_precio and idx_precio:
                updates.append(gspread.Cell(row=excel_row, col=idx_precio, value=str(new_precio)))
            cur_desc = str(rec.get("Descripcion", ""))
            if new_desc != cur_desc and idx_desc:
                updates.append(gspread.Cell(row=excel_row, col=idx_desc, value=new_desc))

    if updates:
        ws_prod.update_cells(updates)
        st.success("✅ Productos actualizados.")

    # Cascadear renombres a evt_ventas y evt_inventario
    if renames:
        _cascadear_renombre(event_id, renames)

    _load_evt_df.clear()

def _cascadear_renombre(event_id, renames: dict):
    """Actualiza el nombre del producto en evt_ventas y evt_inventario."""
    for sheet_name in ("evt_ventas", "evt_inventario"):
        try:
            ws      = _open_ws_evt(sheet_name)
            hdrs    = ws.row_values(1)
            updates = []
            col_prod = hdrs.index("Producto") + 1 if "Producto" in hdrs else None
            if col_prod is None:
                continue
            for row_excel, r in _get_records_with_row(ws, hdrs):
                if str(r.get("EventID")) != event_id:
                    continue
                prod_actual = str(r.get("Producto", ""))
                if prod_actual in renames:
                    updates.append(gspread.Cell(row=row_excel, col=col_prod, value=renames[prod_actual]))
            if updates:
                ws.update_cells(updates)
        except Exception as e:
            st.warning(f"No se pudo cascadear nombre en {sheet_name}: {e}")

def _actualizar_stock(df_orig, df_edited):
    """Actualiza cantidades en evt_inventario según cambios editados."""
    ws      = _open_ws_evt("evt_inventario")
    hdrs    = ws.row_values(1)
    col_cant = hdrs.index("Cantidad") + 1 if "Cantidad" in hdrs else None
    if col_cant is None:
        st.error("No se encontró la columna Cantidad.")
        return
    updates = []
    id_to_row = {str(r.get("ID")): row_excel for row_excel, r in _get_records_with_row(ws, hdrs)}
    for orig_row, new_row in zip(df_orig.itertuples(index=False), df_edited.itertuples(index=False)):
        if str(orig_row.Cantidad) != str(new_row.Cantidad):
            row_excel = id_to_row.get(str(orig_row.ID))
            if row_excel:
                updates.append(gspread.Cell(row=row_excel, col=col_cant, value=str(int(new_row.Cantidad))))
    if updates:
        ws.update_cells(updates)
        _load_evt_df.clear()
        st.success("✅ Stock actualizado.")
    else:
        st.info("No hay cambios de stock para guardar.")

def _actualizar_ventas_mesa(edited_df):
    """Guarda cambios en cantidades/eliminar de una mesa."""
    ws      = _open_ws_evt("evt_ventas")
    hdrs    = ws.row_values(1)
    idx_cant = hdrs.index("Cantidad") + 1 if "Cantidad" in hdrs else None
    idx_tot  = hdrs.index("Total") + 1    if "Total"    in hdrs else None
    idx_anu  = hdrs.index("Anulado") + 1  if "Anulado"  in hdrs else None
    updates  = []
    id_to_row = {str(r.get("ID")): (row_excel, r) for row_excel, r in _get_records_with_row(ws, hdrs)}

    for _, changed in edited_df.iterrows():
        c_id  = str(changed["ID"])
        c_qty = int(changed["Cantidad"])
        c_del = bool(changed["Eliminar"])
        if c_id not in id_to_row:
            continue
        row_excel, rec = id_to_row[c_id]
        if c_del:
            if idx_anu:
                updates.append(gspread.Cell(row=row_excel, col=idx_anu, value="TRUE"))
        else:
            orig_qty = int(rec.get("Cantidad", 0) or 0)
            if orig_qty != c_qty:
                new_tot = c_qty * int(changed["Precio_Unitario"])
                if idx_cant: updates.append(gspread.Cell(row=row_excel, col=idx_cant, value=str(c_qty)))
                if idx_tot:  updates.append(gspread.Cell(row=row_excel, col=idx_tot,  value=str(new_tot)))

    if updates:
        ws.update_cells(updates)
        _load_evt_df.clear()
        st.success("✅ Cambios aplicados.")
    else:
        st.info("Sin cambios detectados.")

def _confirmar_pago_mesa(event_id, mesa, medio_pago, quien_cobra, modo_evento):
    ws      = _open_ws_evt("evt_ventas")
    hdrs    = ws.row_values(1)
    idx_ep  = hdrs.index("Estado_Pago") + 1   if "Estado_Pago"   in hdrs else None
    idx_mp  = hdrs.index("Medio_Pago") + 1    if "Medio_Pago"    in hdrs else None
    idx_pc  = hdrs.index("Persona_Cobro") + 1 if "Persona_Cobro" in hdrs else None
    idx_ee  = hdrs.index("Estado_Entrega") + 1 if "Estado_Entrega" in hdrs else None
    updates = []
    
    for row_excel, r in _get_records_with_row(ws, hdrs):
        if (str(r.get("EventID")) == event_id and
                str(r.get("Mesa")) == mesa and
                str(r.get("Estado_Pago")).lower() in ["pendiente", ""]):
            if idx_ep: updates.append(gspread.Cell(row=row_excel, col=idx_ep, value="Pagado"))
            if idx_mp: updates.append(gspread.Cell(row=row_excel, col=idx_mp, value=medio_pago))
            if idx_pc: updates.append(gspread.Cell(row=row_excel, col=idx_pc, value=quien_cobra))
            if modo_evento == "simple" and idx_ee:
                updates.append(gspread.Cell(row=row_excel, col=idx_ee, value="Entregado"))
    if updates:
        ws.update_cells(updates)
        _load_evt_df.clear()
        st.success(f"✅ Cuenta de {mesa} pagada — {medio_pago} → {quien_cobra}")

def _marcar_entregado(venta_id: str):
    ws      = _open_ws_evt("evt_ventas")
    hdrs    = ws.row_values(1)
    col_ee  = hdrs.index("Estado_Entrega") + 1 if "Estado_Entrega" in hdrs else None
    if not col_ee:
        return
    for row_excel, r in _get_records_with_row(ws, hdrs):
        if str(r.get("ID")) == venta_id:
            ws.update_cell(row_excel, col_ee, "Entregado")
            _load_evt_df.clear()
            return

def _marcar_borrado(event_id):
    ws      = _open_ws_evt("evt_eventos")
    hdrs    = ws.row_values(1)
    col_e   = hdrs.index("Estado") + 1 if "Estado" in hdrs else None
    if not col_e: return
    for row_excel, r in _get_records_with_row(ws, hdrs):
        if str(r.get("ID")) == event_id:
            ws.update_cell(row_excel, col_e, "Borrado")
            _load_evt_df.clear()
            return

def _anular_evento_y_finanzas(event_id, event_name):
    ws_evt = _open_ws_evt("evt_eventos")
    hdrs   = ws_evt.row_values(1)
    col_e  = hdrs.index("Estado") + 1 if "Estado" in hdrs else None
    
    for row_excel, r in _get_records_with_row(ws_evt, hdrs):
        if str(r.get("ID")) == event_id and col_e:
            ws_evt.update_cell(row_excel, col_e, "Anulado")
            _load_evt_df.clear()
            break
    try:
        ws_fin      = _open_ws(HOJA)
        headers_fin = ws_fin.row_values(1)
        if "Anulado" in headers_fin:
            idx_anu = headers_fin.index("Anulado") + 1
            updates = []
            
            # Replicar lógica de "get_records_with_row" para finanzas que tiene la misma vulnerabilidad
            values = ws_fin.get_all_values()
            if len(values) >= 2:
                for idx_arr, row_arr in enumerate(values[1:]):
                    row_excel = idx_arr + 2
                    rec = {headers_fin[j]: (row_arr[j] if j < len(row_arr) else "") for j in range(len(headers_fin))}
                    det = str(rec.get("Detalle", ""))
                    if event_name in det and any(det.startswith(p) for p in ["Ventas en", "Insumo en", "Liquidación x"]):
                        updates.append(gspread.Cell(row=row_excel, col=idx_anu, value="TRUE"))

            if updates:
                ws_fin.update_cells(updates)
    except Exception as e:
        st.error(f"Error al anular en Finanzas: {e}")

def _marcar_cerrado(event_id, a, m, t, n=0):
    ws      = _open_ws_evt("evt_eventos")
    hdrs    = ws.row_values(1)
    for row_excel, r in _get_records_with_row(ws, hdrs):
        if str(r.get("ID")) == event_id:
            now_str   = pd.Timestamp.now(tz=STGO).strftime("%Y-%m-%d %H:%M:%S")
            updates   = []
            for field, val in [("Estado", "Cerrado"), ("Asistentes", a), ("Mujeres_Pct", m),
                                ("TerceraEdad_Pct", t), ("Ninos_Pct", n), ("ClosedAt", now_str)]:
                if field in hdrs:
                    updates.append(gspread.Cell(row=row_excel, col=hdrs.index(field) + 1, value=val))
            ws.update_cells(updates)
            _load_evt_df.clear()
            return

def _ejecutar_cierre(event_id, event_name, pagos_por_persona, gastos_por_persona, traspasos,
                     asis, muj, terc, nin, caja_central, closed_by):
    try:
        ws_fin   = _open_ws(HOJA)
        hdrs_fin = _ensure_sheet_headers(ws_fin)
    except Exception as e:
        st.error(f"Falla conexión finanzas: {e}")
        return

    now            = pd.Timestamp.now(tz=STGO)
    date_mov       = now.strftime("%Y-%m-%d")
    date_rec       = now.strftime("%Y-%m-%d %H:%M:%S")
    filas          = []

    for persona, rec in pagos_por_persona.items():
        p = persona if persona != "Sin asignar" else caja_central
        if rec > 0 and p:
            d = {"ID": str(uuid.uuid4()), "Tipo": "Ingreso", "Detalle": f"Ventas en {event_name}",
                 "Categoría": "Venta Evento", "Fecha": date_mov, "Persona": p,
                 "Persona_Origen": "", "Persona_Destino": "", "Monto": str(int(rec)),
                 "Created_At": date_rec, "Created_By": closed_by, "Anulado": ""}
            filas.append([str(d.get(h, "")) for h in hdrs_fin])

    for persona, deuda in gastos_por_persona.items():
        p = persona if persona != "Sin asignar" else ""
        if deuda > 0:
            d = {"ID": str(uuid.uuid4()), "Tipo": "Gasto", "Detalle": f"Insumo en {event_name}",
                 "Categoría": "Gasto Insumos", "Fecha": date_mov, "Persona": p,
                 "Persona_Origen": "", "Persona_Destino": "", "Monto": str(int(deuda)),
                 "Created_At": date_rec, "Created_By": closed_by, "Anulado": ""}
            filas.append([str(d.get(h, "")) for h in hdrs_fin])

    for t in traspasos:
        dest = caja_central if t["a"] == "🏦 Caja Central Aucca" else t["a"]
        ori  = caja_central if t["de"] == "🏦 Caja Central Aucca" else t["de"]
        if t["monto"] > 0 and ori and dest and ori != dest:
            d = {"ID": str(uuid.uuid4()), "Tipo": "Traspaso", "Detalle": f"Liquidación x {event_name}",
                 "Categoría": "", "Fecha": date_mov, "Persona": "",
                 "Persona_Origen": ori, "Persona_Destino": dest, "Monto": str(int(t["monto"])),
                 "Created_At": date_rec, "Created_By": closed_by, "Anulado": ""}
            filas.append([str(d.get(h, "")) for h in hdrs_fin])

    if filas:
        ws_fin.append_rows(filas, value_input_option="USER_ENTERED")
        st.success("✅ Data inyectada a la Bóveda de Aucca.")
    st.balloons()
