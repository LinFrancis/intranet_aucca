import streamlit as st
import pandas as pd
import uuid
import datetime as dt
from zoneinfo import ZoneInfo
import gspread

# Importar constantes y utilidades desde el módulo general de finanzas
from secciones.finanzas_aucca import AUCCANES, _open_ws, _ensure_sheet_headers, _a1_range_row, EXPECTED_HEADERS, HOJA, STGO

# ==========================================
# Constantes y Estructuras de Datos
# ==========================================
SHEETS_CONFIG = {
    "evt_eventos": ["ID", "Nombre", "Tipo", "Fecha", "Estado", "Asistentes", "Mujeres_Pct", "TerceraEdad_Pct", "Ninos_Pct", "CreatedBy", "CreatedAt", "ClosedAt", "Detalles_Ficha"],
    "evt_productos": ["EventID", "Nombre", "Precio_Base", "CreatedBy"],
    "evt_inventario": ["ID", "EventID", "Producto", "Cantidad", "Gasto_Materiales", "Persona_Gasto", "Persona_Registro", "CreatedAt", "Anulado"],
    "evt_ventas": ["ID", "EventID", "Mesa", "Producto", "Cantidad", "Precio_Unitario", "Total", "Persona_Registro", "Persona_Cobro", "Estado_Entrega", "Estado_Pago", "Medio_Pago", "CreatedAt", "Anulado"],
    "evt_notas": ["ID", "EventID", "Persona", "Aprendizaje", "CreatedAt"]
}

def _ensure_evt_sheet(sheet_name: str) -> list[str]:
    """Asegura que la hoja de eventos exista y tenga los headers correctos."""
    import gspread
    from google.oauth2.service_account import Credentials
    # Re-authentication needed to get spreadsheet object to call add_worksheet
    creds = Credentials.from_service_account_info(
        st.secrets["gspread"],
        scopes=["https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"],
    )
    client = gspread.authorize(creds)
    # The key is from google.py or finanzas_aucca.py. Reusing the one from finanzas.
    SPREADSHEET_KEY = "1C8njkp0RQMdXnxuJvPvfK_pNZHQSi7q7dUPeUg-2624"
    sh = client.open_by_key(SPREADSHEET_KEY)
    
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # Create it if it doesn't exist
        ws = sh.add_worksheet(title=sheet_name, rows=1000, cols=20)
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

@st.cache_data(ttl=60)
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
                nombre_ev = st.text_input("Nombre del Evento (ej. Fiesta Agosto)")
                tipo_ev = st.selectbox("Tipo", ["Evento / Fiesta", "Almuerzo / Cena", "Visita", "Taller"])
                fecha_ev = st.date_input("Fecha de Realización", dt.date.today())
                detalles_ev = st.text_area("Ficha del Evento (Horarios, Acuerdos, Modalidad, etc.)", height=100)
                
                if st.form_submit_button("Crear Evento", type="primary", use_container_width=True):
                    if nombre_ev.strip() != "":
                        now = pd.Timestamp.now(tz=STGO)
                        nuevo_id = str(uuid.uuid4())
                        rec = {
                            "ID": nuevo_id,
                            "Nombre": nombre_ev.strip(),
                            "Tipo": tipo_ev,
                            "Fecha": fecha_ev.strftime("%Y-%m-%d"),
                            "Estado": "Abierto",
                            "CreatedBy": usuario_actual,
                            "CreatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
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
            
    # Además de los abiertos, mostramos los cerrados por si se quiere ver el historial
    eventos_cerrados = df_eventos[df_eventos["Estado"] == "Cerrado"] if not df_eventos.empty else pd.DataFrame()
    if not eventos_cerrados.empty:
        for _, row in eventos_cerrados.iterrows():
            event_options[row["ID"]] = f"🔒 {row['Nombre']} ({row['Fecha']})"

    # Mantener seleccionado el evento guardado en sesion
    current_idx = 0
    keys_list = list(event_options.keys())
    saved_id = st.session_state.get("evento_activo_id", "")
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

    # Verificar si está cerrado
    evento_sel_data = df_eventos[df_eventos["ID"] == seleccion].iloc[0]
    es_cerrado = evento_sel_data["Estado"] == "Cerrado"
    
    if es_cerrado:
        st.warning("🔒 **Este evento está CERRADO.** Solo puedes visualizar la información. No es posible editar ni agregar registros.")

    st.markdown("---")
    
    # -----------------------------------------------------
    # Cargar Data del Evento Seleccionado
    # -----------------------------------------------------
    df_inv = _load_evt_df("evt_inventario")
    df_ven = _load_evt_df("evt_ventas")
    df_prod = _load_evt_df("evt_productos")
    
    df_inv_act = df_inv[(df_inv["EventID"] == seleccion) & (df_inv["Anulado"] != "TRUE")] if not df_inv.empty else pd.DataFrame(columns=SHEETS_CONFIG["evt_inventario"])
    df_ven_act = df_ven[(df_ven["EventID"] == seleccion) & (df_ven["Anulado"] != "TRUE")] if not df_ven.empty else pd.DataFrame(columns=SHEETS_CONFIG["evt_ventas"])
    df_prod_act = df_prod[df_prod["EventID"] == seleccion] if not df_prod.empty else pd.DataFrame(columns=SHEETS_CONFIG["evt_productos"])

    # Calcular Stock Actual: Producción - Venta
    # Stock es algo dinámico
    def _calcular_stock():
        res = {}
        if not df_inv_act.empty:
            df_inv_act["Cantidad"] = pd.to_numeric(df_inv_act["Cantidad"], errors='coerce').fillna(0)
            res = df_inv_act.groupby("Producto")["Cantidad"].sum().to_dict()
        if not df_ven_act.empty:
            df_ven_act["Cantidad"] = pd.to_numeric(df_ven_act["Cantidad"], errors='coerce').fillna(0)
            ventas_group = df_ven_act.groupby("Producto")["Cantidad"].sum().to_dict()
            for prod, q_vendida in ventas_group.items():
                if prod in res:
                    res[prod] -= q_vendida
                else:
                    res[prod] = -q_vendida
        return res
    
    stock_actual = _calcular_stock()

    # -----------------------------------------------------
    # Sub-Rutas (Pestañas del Evento)
    # -----------------------------------------------------
    tab_options = ["⚙️ Información General", "🛒 Punto de Venta (Caja)", "🍳 Gasto y Producción", "🏃 Entregas", "🧠 Aprendizajes", "🏁 Transacciones / Cierre"]
    active_tab = st.radio("Sección del Evento", tab_options, horizontal=True, label_visibility="collapsed", key=f"tab_evt_{seleccion}")
    
    # ==========================================
    # 0. Información General y Precios
    # ==========================================
    # Mapa de precios por defecto general
    price_map = {}
    if not df_prod_act.empty:
         for _, r in df_prod_act.iterrows():
              try:
                   price_map[r["Nombre"]] = int(r["Precio_Base"])
              except:
                   price_map[r["Nombre"]] = 0

    if active_tab == tab_options[0]:
        st.markdown(f"### ⚙️ {evento_sel_data['Nombre']}")
        st.caption(f"Visión general e inventario permanente del evento.")
        
        c_i1, c_i2, c_i3 = st.columns(3)
        c_i1.metric("Fecha Registro", str(evento_sel_data["CreatedAt"]).split(" ")[0])
        c_i2.metric("Fecha Realización", str(evento_sel_data["Fecha"]))
        c_i3.metric("Fecha Cierre", str(evento_sel_data.get("ClosedAt", "")) if pd.notna(evento_sel_data.get("ClosedAt")) and evento_sel_data.get("ClosedAt") else "Activo")
        
        detalles_texto = str(evento_sel_data.get("Detalles_Ficha", ""))
        if detalles_texto and detalles_texto != "nan":
            st.info(f"**📖 Ficha del Evento / Acuerdos Previos:**\n\n{detalles_texto}")
            
        with st.expander("⚙️ Ajustes del Evento (Renombrar / Eliminar)", expanded=False):
            with st.form("form_edit_nombre"):
                nuevo_nombre = st.text_input("Renombrar Evento", value=evento_sel_data['Nombre'])
                if st.form_submit_button("💾 Actualizar Nombre"):
                    if nuevo_nombre.strip() and nuevo_nombre.strip() != evento_sel_data['Nombre']:
                        _renombrar_evento(seleccion, nuevo_nombre.strip())
                        st.session_state["evento_activo_id"] = seleccion
                        st.success("Nombre actualizado.")
                        st.rerun()

            st.markdown("---")
            if es_cerrado:
                st.warning("⚠️ Este evento ya fue inyectado a Finanzas.\nAl eliminarlo, **se ANULARÁN** todas sus transacciones en la Bóveda maestra de Finanzas.")
                if st.button("🚫 Anular Evento y Registros en Finanzas", type="primary"):
                    _anular_evento_y_finanzas(seleccion, evento_sel_data['Nombre'])
                    st.session_state["evento_activo_id"] = ""
                    st.success("Evento anulado aquí y en Finanzas.")
                    st.rerun()
            else:
                st.info("Eliminar borrará este evento y lo dejará inaccesible para siempre.")
                if st.button("🗑️ Eliminar Evento Permanentemente", type="primary"):
                    _marcar_borrado(seleccion)
                    st.session_state["evento_activo_id"] = ""
                    st.success("Evento borrado.")
                    st.rerun()
            
        st.markdown("---")
        st.markdown("#### 📋 Catálogo de Productos y Precios")
        st.caption("Añade productos que vas a vender y fija su precio predeterminado para la caja.")
        
        if not es_cerrado:
            # Crear producto
            with st.container(border=True):
                st.markdown("##### ➕ Crear Nuevo Producto")
                with st.form("form_crear_producto", clear_on_submit=True):
                    col_n1, col_n2, col_n3 = st.columns([2, 1, 1])
                    nuevo_p = col_n1.text_input("Nombre del Producto", key="new_p_name", label_visibility="collapsed", placeholder="Ej: Pizza Napolitana")
                    nuevo_v = col_n2.number_input("Precio Venta", min_value=0, step=100, key="new_p_val", label_visibility="collapsed")
                    if col_n3.form_submit_button("Añadir al Menú", use_container_width=True):
                    if nuevo_p.strip():
                        if nuevo_p.strip() not in price_map:
                            _save_evt_row("evt_productos", {"EventID": seleccion, "Nombre": nuevo_p.strip(), "Precio_Base": str(int(nuevo_v)), "CreatedBy": usuario_actual})
                            st.success("Producto creado.")
                            _load_evt_df.clear()
                            st.rerun()
                        else:
                            st.error("Este producto ya existe en el menú.")

            st.markdown("##### ✏️ Editar Precios Existentes")
            if not df_prod_act.empty:
                df_to_edit = pd.DataFrame([{"Producto": pn, "Precio": int(price_map.get(pn, 0))} for pn in df_prod_act["Nombre"].unique()])
                with st.form("form_edit_precios"):
                    st.caption("Escribe los nuevos precios abajo y luego presiona Guardar Todo. El sistema no guardará cambios hasta que presiones el botón.")
                    edited_df = st.data_editor(
                        df_to_edit, 
                        column_config={
                            "Producto": st.column_config.TextColumn("Producto", disabled=True),
                            "Precio": st.column_config.NumberColumn("Precio ($)", min_value=0, step=100)
                        }, 
                        hide_index=True, 
                        use_container_width=True
                    )
                    
                    if st.form_submit_button("💾 Guardar Todos los Precios", type="primary", use_container_width=True):
                        import gspread
                        ws_prod = _open_ws("evt_productos")
                        records = ws_prod.get_all_records()
                        idx_precio = SHEETS_CONFIG["evt_productos"].index("Precio_Base") + 1
                        updates = []
                        
                        new_prices = {r["Producto"]: r["Precio"] for _, r in edited_df.iterrows()}
                        
                        for i, rec in enumerate(records):
                            pn = str(rec.get("Nombre"))
                            if str(rec.get("EventID")) == seleccion and pn in new_prices:
                                if str(int(new_prices[pn])) != str(rec.get("Precio_Base", "")):
                                    updates.append(gspread.Cell(row=i + 2, col=idx_precio, value=str(int(new_prices[pn]))))
                                    
                        if updates:
                             ws_prod.update_cells(updates)
                             _load_evt_df.clear()
                             st.success("Todos los precios han sido actualizados.")
                             st.rerun()
                        else:
                             st.info("No detecté cambios en los precios para guardar.")
            else:
                st.info("No hay productos registrados aún.")

    # ==========================================
    # 1. Punto de Venta (Caja)
    # ==========================================
    if active_tab == tab_options[1]:
        st.markdown(f"### 🛒 Administrar Cuentas / Mesas - {evento_sel_data['Nombre']}")
        
        # Filtro cajas abiertas vs pagadas
        if not es_cerrado:
            # Crear cuenta
            with st.expander("➕ Abrir Nueva Cuenta", expanded=False):
                with st.form("form_nueva_cuenta", clear_on_submit=True):
                    nueva_mesa = st.text_input("Nombre de la cuenta / Mesa", placeholder="Ej: Mesa Juan, Grupo 1, Entradas...")
                    if st.form_submit_button("Iniciar Cuenta", type="primary"):
                        if nueva_mesa.strip() != "":
                            st.success("Cuenta lista para usar en el menú 'Añadir Producto a una Cuenta'.")
                            st.session_state["ultima_mesa"] = nueva_mesa.strip()


            with st.expander("📦 Visor de Inventario (Stock Disponible)", expanded=False):
                if stock_actual:
                    df_s = pd.DataFrame([{"Producto": p, "Precio Unitario": f"${price_map.get(p, 0):,.0f}", "Stock": s} for p, s in stock_actual.items() if s > 0])
                    st.dataframe(df_s, use_container_width=True, hide_index=True)
                else:
                    st.info("No hay productos con stock actualmente.")

            c1, c2 = st.columns([1,1])
            with c1:
                with st.container(border=True):
                    st.markdown("#### 🍔 Añadir Producto a Cuenta")
                    
                    # Identificar mesas existentes
                    mesas_existentes = []
                    if not df_ven_act.empty:
                        mesas_existentes = sorted(list(df_ven_act["Mesa"].unique()))
                    # Agregamos la última creada si no está
                    ult_mesa = st.session_state.get("ultima_mesa", "")
                    if ult_mesa and ult_mesa not in mesas_existentes:
                        mesas_existentes.insert(0, ult_mesa)
                        
                        
                    with st.form("form_add_prod_cuenta", clear_on_submit=True):
                        if not mesas_existentes:
                            st.info("No hay mesas abiertas. Escribe una nueva:")
                            sel_mesa = st.text_input("Nombre Mesa")
                        else:
                            sel_mesa = st.selectbox("Seleccionar Cuenta/Mesa", mesas_existentes)
                            
                        # Selección de prod
                        prods_disp = [p for p, stk in stock_actual.items() if stk > 0]
                        if not prods_disp:
                            st.warning("No hay productos con stock disponibles aún.")
                            sel_prod = ""
                            cant = 0
                            precio_ingresado = 0
                        else:
                            sel_prod = st.selectbox("Producto Disp.", [f"{p} (Stock: {stock_actual[p]:.0f})" for p in prods_disp])
                            cant = st.number_input("Cantidad", min_value=1, step=1)
                            st.caption("Escribe un precio diferente SÓLO si necesitas cobrar un monto especial. De lo contrario, deja 0 para usar el catálogo.")
                            precio_ingresado = st.number_input("Precio Especial (CLP) - Opcional", min_value=0, step=100, value=0)
                        
                        if st.form_submit_button("Añadir a la Cuenta", type="primary", use_container_width=True):
                                prod_clean = sel_prod.split(" (Stock:")[0] if sel_prod else ""
                                precio_final = precio_ingresado if precio_ingresado > 0 else price_map.get(prod_clean, 0)
                                if sel_mesa and prod_clean and cant > 0:
                                    # Validación Stock último minuto
                                    if stock_actual.get(prod_clean, 0) < cant:
                                        st.error(f"⚠️ Stock insuficiente. Solo quedan {stock_actual.get(prod_clean, 0)}.")
                                    else:
                                        now = pd.Timestamp.now(tz=STGO)
                                        rec_venta = {
                                            "ID": str(uuid.uuid4()),
                                            "EventID": seleccion,
                                            "Mesa": sel_mesa.strip(),
                                            "Producto": prod_clean,
                                            "Cantidad": str(int(cant)),
                                            "Precio_Unitario": str(int(precio_final)),
                                        "Total": str(int(cant * precio_final)),
                                        "Persona_Registro": usuario_actual,
                                        "Persona_Cobro": "",
                                        "Estado_Entrega": "Pendiente",
                                        "Estado_Pago": "Pendiente",
                                        "Medio_Pago": "",
                                        "CreatedAt": now.strftime("%Y-%m-%d %H:%M:%S"),
                                        "Anulado": ""
                                    }
                                    _save_evt_row("evt_ventas", rec_venta)
                                    st.session_state["ultima_mesa"] = sel_mesa.strip()
                                    st.success(f"Añadido a {sel_mesa}")
                                    st.rerun()

            with c2:
                st.markdown("#### 💳 Resumen y Cobro de Mesas")
                if not df_ven_act.empty:
                    # Agrupar por Mesa
                    df_ven_act["Total_Num"] = pd.to_numeric(df_ven_act["Total"], errors='coerce').fillna(0)
                    df_ven_no_pagadas = df_ven_act[df_ven_act["Estado_Pago"] == "Pendiente"]
                    agrupado_pagar = df_ven_no_pagadas.groupby("Mesa")["Total_Num"].sum().reset_index()
                    
                    if agrupado_pagar.empty:
                        st.info("Todas las cuentas registradas están pagadas 😊.")
                    else:
                        for _, rmesa in agrupado_pagar.iterrows():
                            mesa = rmesa["Mesa"]
                            total = rmesa["Total_Num"]
                            with st.expander(f"🧾 Cuenta Pendiente: **{mesa}** — Total: ${total:,.0f}"):
                                det_mesa = df_ven_no_pagadas[df_ven_no_pagadas["Mesa"] == mesa]
                                
                                df_to_edit = det_mesa[["ID", "Producto", "Precio_Unitario", "Cantidad"]].copy()
                                df_to_edit["Cantidad"] = pd.to_numeric(df_to_edit["Cantidad"], errors="coerce").fillna(1).astype(int)
                                df_to_edit["Precio_Unitario"] = pd.to_numeric(df_to_edit["Precio_Unitario"], errors="coerce").fillna(0).astype(int)
                                df_to_edit["Eliminar"] = False
                                
                                
                                st.caption("Para no recargar la app por cada clic, debes presionar Guardar una vez modifiques esta tabla o elimines cosas.")
                                with st.form(f"form_editor_{mesa}"):
                                    edited_mesa_df = st.data_editor(
                                        df_to_edit,
                                        column_config={
                                            "ID": None, # ocultar
                                            "Producto": st.column_config.TextColumn("Ítem", disabled=True),
                                            "Precio_Unitario": st.column_config.NumberColumn("P. Unitario ($)", disabled=True),
                                            "Cantidad": st.column_config.NumberColumn("Cantidad", min_value=1, step=1),
                                            "Eliminar": st.column_config.CheckboxColumn("🗑️ Quitar", default=False)
                                        },
                                        hide_index=True,
                                        use_container_width=True
                                    )
                                    
                                    current_total_edited = sum([row["Cantidad"] * row["Precio_Unitario"] for _, row in edited_mesa_df.iterrows() if not row["Eliminar"]])
                                    st.markdown(f"**Total Proyectado: ${current_total_edited:,.0f}**")
                                    
                                    if st.form_submit_button("💾 Guardar Ajustes de Facturación", type="primary"):
                                        ws = _open_ws("evt_ventas")
                                        records = ws.get_all_records()
                                        idx_cant = SHEETS_CONFIG["evt_ventas"].index("Cantidad") + 1
                                        idx_tot = SHEETS_CONFIG["evt_ventas"].index("Total") + 1
                                        idx_anu = SHEETS_CONFIG["evt_ventas"].index("Anulado") + 1
                                        updates = []
                                        
                                        for _, changed_row in edited_mesa_df.iterrows():
                                            c_id = changed_row["ID"]
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
                                                            updates.append(gspread.Cell(row=row_excel, col=idx_tot, value=str(int(new_tot))))
                                                    break
                                        if updates:
                                            ws.update_cells(updates)
                                            _load_evt_df.clear()
                                            st.success("Cambios aplicados.")
                                            st.rerun()
                                        else:
                                            st.info("Sin cambios.")
                                
                                st.markdown("---")
                                
                                with st.form(f"form_cobro_{mesa}"):
                                    medio_pago = st.selectbox("Medio de Pago", ["Transferencia", "Efectivo"])
                                    quien_cobra = st.selectbox("¿Hacia quién fue la plata / depósito?", AUCCANES, index=AUCCANES.index(usuario_actual) if usuario_actual in AUCCANES else 0)
                                    
                                    todo_entregado = all(estado == "Entregado" for estado in det_mesa["Estado_Entrega"])
                                    if not todo_entregado:
                                        st.warning("⚠️ Hay productos pendientes de entrega en esta cuenta. Debes entregar todo (pestaña 'Entregas') antes de poder confirmar el pago.")
                                        st.form_submit_button("Confirmar Pago Bloqueado (Entregas Pendientes)", disabled=True)
                                    else:
                                        if st.form_submit_button(f"💸 Confirmar Pago {mesa}", type="primary"):
                                        # Hay que actualizar filas a Pagadas y registrar Quien Cobra
                                        import gspread
                                        ws = _open_ws("evt_ventas")
                                        records = ws.get_all_records()
                                        cell_updates = []
                                        estado_pago_idx = SHEETS_CONFIG["evt_ventas"].index("Estado_Pago") + 1
                                        medio_pago_idx = SHEETS_CONFIG["evt_ventas"].index("Medio_Pago") + 1
                                        persona_cobro_idx = SHEETS_CONFIG["evt_ventas"].index("Persona_Cobro") + 1
                                        
                                        # Buscar la mesa pendiente y actualizar.
                                        for i, r_g in enumerate(records):
                                            if str(r_g.get("EventID")) == seleccion and str(r_g.get("Mesa")) == mesa and str(r_g.get("Estado_Pago")) == "Pendiente":
                                                row_excel = i + 2  # +1 por indexado en 0, +1 por headers
                                                cell_updates.append(gspread.Cell(row=row_excel, col=estado_pago_idx, value="Pagado"))
                                                cell_updates.append(gspread.Cell(row=row_excel, col=medio_pago_idx, value=medio_pago))
                                                cell_updates.append(gspread.Cell(row=row_excel, col=persona_cobro_idx, value=quien_cobra))
                                                
                                        if cell_updates:
                                            ws.update_cells(cell_updates)
                                            st.success(f"Cuenta de {mesa} pagada por {medio_pago}")
                                            _load_evt_df.clear()
                                            st.rerun()

        # Resumen general de estado
        if not df_ven_act.empty:
            st.markdown("---")
            st.markdown("##### 📜 Historial de Operaciones de Caja")
            df_ven_act["Total_Num"] = pd.to_numeric(df_ven_act["Total"], errors='coerce').fillna(0)
            df_ven_view = df_ven_act[["CreatedAt", "Mesa", "Producto", "Cantidad", "Total_Num", "Estado_Pago", "Estado_Entrega", "Persona_Registro"]].copy()
            df_ven_view = df_ven_view.rename(columns={"Total_Num": "Total CLP", "Persona_Registro": "Vendedor"})
            st.dataframe(df_ven_view, use_container_width=True)

    # ==========================================
    # 2. Aportes / Cocina / Producción
    # ==========================================
    if active_tab == tab_options[2]:
        st.markdown(f"### 🍳 Gastos y Producción - {evento_sel_data['Nombre']}")
        st.caption("Anota de manera separada cuánto dinero se gastó en compras y cuántos productos reales se generaron para la venta.")
        
        if not es_cerrado:
            col_l, col_r = st.columns(2)
            
            with col_l:
                with st.expander("💸 1. Reportar Gastos de Bolsillo", expanded=True):
                    st.caption("Ideal para gas, insumos generales, harina, etc.")
                    with st.form("form_gastos", clear_on_submit=True):
                        motivo_gasto = st.text_input("¿Qué se compró?", placeholder="Ej: Supermercado, Bebidas, Gas")
                        gasto_valor = st.number_input("💰 Valor Costo (CLP)", min_value=100, step=100)
                        persona_gasto = st.selectbox("¿Quién pagó de su bolsillo?", [""] + AUCCANES, index=AUCCANES.index(usuario_actual) if usuario_actual in AUCCANES else 0)
                        
                        if st.form_submit_button("Registrar Gasto", type="primary", use_container_width=True):
                            if motivo_gasto.strip() and persona_gasto:
                                now = pd.Timestamp.now(tz=STGO)
                                rec_in = {
                                    "ID": str(uuid.uuid4()),
                                    "EventID": seleccion,
                                    "Producto": f"[Gasto] {motivo_gasto.strip()}",
                                    "Cantidad": "0",  # No influye en stock
                                    "Gasto_Materiales": str(int(gasto_valor)),
                                    "Persona_Gasto": persona_gasto,
                                    "Persona_Registro": usuario_actual,
                                    "CreatedAt": now.strftime("%Y-%m-%d %H:%M:%S")
                                }
                                _save_evt_row("evt_inventario", rec_in)
                                st.success("Gasto registrado. Se sumará a tu reembolso final.")
                                st.rerun()
                            else:
                                st.error("Ingresa qué se compró y quién lo pagó.")
            
            with col_r:
                with st.expander("🍔 2. Reportar Elaboración de Oferta", expanded=True):
                    st.caption("Para sumar stock real que la gente te podrá comprar.")
                    with st.form("form_inventario", clear_on_submit=True):
                        lista_prod_sug = sorted(df_prod_act["Nombre"].unique()) if not df_prod_act.empty else []
                        sel_cat_prod = st.selectbox("Producto a Fabricar", [""] + lista_prod_sug)
                        nuevo_prod = st.text_input("O Crear Nuevo Producto", placeholder="Ej: Muffin Vegano")
                        cantidad = st.number_input("📦 Cantidad Elaborada", min_value=1, step=1)
                        
                        if st.form_submit_button("Sumar al Inventario", type="primary", use_container_width=True):
                            prod_final = nuevo_prod.strip() if nuevo_prod.strip() else sel_cat_prod
                            if prod_final and cantidad > 0:
                                if prod_final not in lista_prod_sug:
                                    _save_evt_row("evt_productos", {"EventID": seleccion, "Nombre": prod_final, "Precio_Base": "0", "CreatedBy": usuario_actual})
                                
                                now = pd.Timestamp.now(tz=STGO)
                                rec_in = {
                                    "ID": str(uuid.uuid4()),
                                    "EventID": seleccion,
                                    "Producto": prod_final,
                                    "Cantidad": str(int(cantidad)),
                                    "Gasto_Materiales": "0",
                                    "Persona_Gasto": "",
                                    "Persona_Registro": usuario_actual,
                                    "CreatedAt": now.strftime("%Y-%m-%d %H:%M:%S")
                                }
                                _save_evt_row("evt_inventario", rec_in)
                                st.success(f"Se sumaron {cantidad}x {prod_final} al stock disponible.")
                                st.rerun()
                            else:
                                st.error("Debes indicar un producto válido y una cantidad elaborada.")

        if not df_inv_act.empty:
            st.markdown("#### 📋 Histórico de Operaciones (Aportes y Creaciones)")
            df_inv_view = df_inv_act[["CreatedAt", "Persona_Registro", "Producto", "Cantidad", "Gasto_Materiales", "Persona_Gasto"]].copy()
            df_inv_view["Gasto_Materiales"] = pd.to_numeric(df_inv_view["Gasto_Materiales"], errors='coerce').fillna(0)
            st.dataframe(df_inv_view, use_container_width=True, hide_index=True)

    # ==========================================
    # 3. Entregas Totales
    # ==========================================
    if active_tab == tab_options[3]:
        st.markdown("### 🏃 Entregas Pendientes a Clientes")
        if df_ven_act.empty:
            st.info("Aún no hay ventas anotadas.")
        else:
            df_pend = df_ven_act[df_ven_act["Estado_Entrega"] == "Pendiente"]
            if df_pend.empty:
                st.success("¡Todo está entregado! Excelente trabajo en cocina y sala.")
            else:
                for _, rpend in df_pend.iterrows():
                    m = rpend["Mesa"]
                    p = rpend["Producto"]
                    c = rpend["Cantidad"]
                    vp = rpend["Estado_Pago"]
                    
                    bg_color = "#f9f9f9" if vp == "Pagado" else "#fff4e5"
                    with st.container():
                        st.markdown(f"""
                        <div style="background:{bg_color}; padding:10px; border-left:4px solid {'#48bb78' if vp=='Pagado' else '#ed8936'}; margin-bottom:10px; border-radius:4px;">
                            <strong>{c}x {p}</strong> para <em>{m}</em> (Pago: {vp})
                        </div>
                        """, unsafe_allow_html=True)
                        if not es_cerrado and st.button(f"Entregado", key=f"entrega_{rpend['ID']}", use_container_width=True):
                            # Actualizar entrega
                            import gspread
                            ws = _open_ws("evt_ventas")
                            records = ws.get_all_records()
                            estado_ent_idx = SHEETS_CONFIG["evt_ventas"].index("Estado_Entrega") + 1
                            for i, r_g in enumerate(records):
                                if str(r_g.get("ID")) == rpend["ID"]:
                                    row_excel = i + 2
                                    ws.update_cell(row_excel, estado_ent_idx, "Entregado")
                                    st.success(f"{p} marcado como entregado a {m}")
                                    _load_evt_df.clear()
                                    st.rerun()

    # ==========================================
    # 4. Aprendizajes
    # ==========================================
    if active_tab == tab_options[4]:
        st.markdown("### 🧠 Registro de Aprendizajes de la Jornada")
        st.caption("Anota aquí lo que salió bien, lo que salió mal, o ideas para el próximo evento de este tipo.")
        
        df_not = _load_evt_df("evt_notas")
        df_not_act = df_not[df_not["EventID"] == seleccion] if not df_not.empty else pd.DataFrame(columns=SHEETS_CONFIG["evt_notas"])
        
        if not es_cerrado:
            with st.form("form_notas", clear_on_submit=True):
                nota = st.text_area("Cuéntame...", height=100)
                if st.form_submit_button("Guardar Reflexión", type="primary"):
                    if nota.strip():
                        now = pd.Timestamp.now(tz=STGO)
                        rn = {
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
    # 5. Cierre de Evento / Integración Finanzas
    # ==========================================
    if active_tab == tab_options[5]:
        st.markdown("### 🏁 Cierre del Evento y Cuadratura")
        st.info("Esta sección resume el dinero obtenido, calcula cuánto se le adeuda a cada persona que pagó de su bolsillo por los insumos, y exporta el resultado final a la pestaña maestra de Finanzas.")
        
        if df_inv_act.empty and df_ven_act.empty:
            st.warning("No hay transacciones registradas.")
            if not es_cerrado:
                if st.button("Cerrar Evento (Vacío)", type="secondary"):
                    _marcar_cerrado(seleccion, 0, 0, 0)
                    st.rerun()
            return
            
        # Analitica de cierre y Liquidación Peer-to-Peer
        df_ven_act["Total_Num"] = pd.to_numeric(df_ven_act["Total"], errors='coerce').fillna(0)
        df_inv_act["Gasto_Num"] = pd.to_numeric(df_inv_act["Gasto_Materiales"], errors='coerce').fillna(0)
        
        df_pagadas = df_ven_act[df_ven_act["Estado_Pago"] == "Pagado"]
        df_no_pagadas = df_ven_act[df_ven_act["Estado_Pago"] == "Pendiente"]
        total_deudas_venta = df_no_pagadas["Total_Num"].sum()
        
        # 1. ¿Quién tiene la plata de las ventas? (Ingresos Brutos por Persona)
        pagos_por_persona = df_pagadas.groupby("Persona_Cobro")["Total_Num"].sum().to_dict()
        total_recaudado = sum(pagos_por_persona.values())
        
        # 2. ¿Quién gastó plata de su bolsillo? (Gastos por Persona)
        df_gastos_reales = df_inv_act[df_inv_act["Gasto_Num"] > 0]
        gastos_por_persona = df_gastos_reales.groupby("Persona_Gasto")["Gasto_Num"].sum().to_dict()
        total_gastado = sum(gastos_por_persona.values())
        
        utilidad_neta = total_recaudado - total_gastado
        
        col_res1, col_res2, col_res3 = st.columns(3)
        col_res1.metric("Ingresos Por Ventas", f"${int(total_recaudado):,}".replace(",", "."))
        col_res2.metric("Gastos Totales Insumos", f"${int(total_gastado):,}".replace(",", "."))
        col_res3.metric("Utilidad Neta Pura Aucca", f"${int(utilidad_neta):,}".replace(",", "."), delta=f"${int(utilidad_neta):,}")

        st.markdown("---")
        if total_deudas_venta > 0:
            st.error(f"⚠️ ¡ATENCIÓN! Hay **${int(total_deudas_venta):,}** en cuentas sin pagar anotadas. No se sugiere cerrar el evento hasta cobrar.")
            
        st.markdown("#### 🔄 Liquidación de Cuentas (Traspasos Cruzados)")
        st.caption("Como distintas personas pueden haber cobrado y otras tantas gastado dinero propio en insumos, calculamos el 'Saldo Neto' de cada uno. Aquellos que tienen números azules reteniendo dinero de las ventas deben transferir su exceso a quienes están en rojo y a la cuenta madre de Aucca.")
        
        # Personas Involucradas
        todas_las_personas = set(list(pagos_por_persona.keys()) + list(gastos_por_persona.keys()))
        saldos = {}
        for p in todas_las_personas:
            if not p: continue
            ingresado = pagos_por_persona.get(p, 0)
            gastado = gastos_por_persona.get(p, 0)
            saldos[p] = ingresado - gastado
            
        deudores = [] # Gente que se quedó con más plata de la que gastó (Tienen que pagar)
        acreedores = [] # Gente que gastó más de lo que recaudó (Auccanes que recibirán reembolso)
        
        for p, saldo in saldos.items():
            if saldo > 0:
                deudores.append({"persona": p, "monto": saldo})
            elif saldo < 0:
                acreedores.append({"persona": p, "monto": abs(saldo)})
                
        # Acreedor Central: La Caja de Aucca, que espera recibir la utilidad
        if utilidad_neta > 0:
            acreedores.append({"persona": "🏦 Caja Central Aucca", "monto": utilidad_neta})
            
        # Ordenar de mayor a menor para cuadrar
        deudores = sorted(deudores, key=lambda x: x["monto"], reverse=True)
        acreedores = sorted(acreedores, key=lambda x: x["monto"], reverse=True)
        
        traspasos = []
        d_idx = 0
        a_idx = 0
        
        # Resolver deudas (Greedy)
        while d_idx < len(deudores) and a_idx < len(acreedores):
            deudor = deudores[d_idx]
            acreedor = acreedores[a_idx]
            
            monto_transar = min(deudor["monto"], acreedor["monto"])
            
            if monto_transar > 0:
                traspasos.append({
                    "de": deudor["persona"],
                    "a": acreedor["persona"],
                    "monto": int(monto_transar)
                })
            
            deudor["monto"] -= monto_transar
            acreedor["monto"] -= monto_transar
            
            if deudor["monto"] == 0:
                d_idx += 1
            if acreedor["monto"] == 0:
                a_idx += 1
                
        # Renderizar resumen visual general
        with st.container(border=True):
             for t in traspasos:
                 st.info(f"➡️ **{t['de']}** debe transferirle **${int(t['monto']):,}** a **{t['a']}**".replace(",", "."))
             if not traspasos:
                 st.success("Cuentas saldadas. Nadie debe transferir nada.")

        # Acciones de Cierre
        es_demo = "demo" in evento_sel_data["Nombre"].lower()
        
        if not es_cerrado:
            st.markdown("---")
            if es_demo:
                 st.info("💡 **Este es un Evento DEMO.** En lugar de inyectar dinero ficticio en las finanzas reales, dispones del simulador para recrear o borrar estos datos y no interferir la historia de Aucca.")
                 col_d1, col_d2 = st.columns(2)
                 if col_d1.button("🗑️ Borrar este Demo (Ocultar)", use_container_width=True):
                     _marcar_borrado(seleccion)
                     st.session_state["evento_activo_id"] = ""
                     st.rerun()
                     
                 if col_d2.button("🔄 Borrar este Demo y Crear Uno Nuevo", type="primary", use_container_width=True):
                     _marcar_borrado(seleccion)
                     import scratch_insert_demo
                     nuevo_id = scratch_insert_demo.poblar_datos_demo()
                     st.session_state["evento_activo_id"] = nuevo_id
                     _load_evt_df.clear()
                     st.success("Limpiado y Recreado con Exito.")
                     st.rerun()
            else:
                st.markdown("##### ⚙️ Formulario Oficial de Cierre")
                with st.form("form_cierre_oficial"):
                    st.caption("Antes de cerrar, aprovecha e ingresa los estadísticos si los conoces.")
                    asistentes = st.number_input("Número estimado de asistenes", min_value=0, step=1)
                    col_e1, col_e2, col_e3 = st.columns(3)
                    mujeres = col_e1.number_input("% Mujeres est.", min_value=0, max_value=100, step=1)
                    tercera = col_e2.number_input("% 3ra edad est.", min_value=0, max_value=100, step=1)
                    ninos = col_e3.number_input("% Niños est.", min_value=0, max_value=100, step=1)
                    
                    # Quien recibe los fondos utilitarios (Caja Central)
                    caja_central = st.selectbox("¿Quién es/administra la 🏦 Caja Central Aucca para este evento?", AUCCANES)
                    
                    check_confirmo = st.checkbox("Confirmo que revisé las cuentas, saldos, y que realizaré las inyecciones de datos a Finanzas maestro", value=False)
                    
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
                            
def _marcar_borrado(event_id):
    ws = _open_ws("evt_eventos")
    records = ws.get_all_records()
    row_excel = None
    for i, r in enumerate(records):
        if str(r.get("ID")) == event_id:
            row_excel = i + 2
            break
            
    if row_excel is not None:
        idx_estado = SHEETS_CONFIG["evt_eventos"].index("Estado") + 1
        ws.update_cell(row_excel, idx_estado, "Borrado")
        _load_evt_df.clear()

def _renombrar_evento(event_id, nuevo_nombre):
    ws = _open_ws("evt_eventos")
    records = ws.get_all_records()
    row_excel = None
    for i, r in enumerate(records):
        if str(r.get("ID")) == event_id:
            row_excel = i + 2
            break
            
    if row_excel is not None:
        idx_nombre = SHEETS_CONFIG["evt_eventos"].index("Nombre") + 1
        ws.update_cell(row_excel, idx_nombre, nuevo_nombre)
        _load_evt_df.clear()

def _anular_evento_y_finanzas(event_id, event_name):
    import gspread
    # 1. Anular en eventos
    ws_evt = _open_ws("evt_eventos")
    records_evt = ws_evt.get_all_records()
    row_excel = None
    for i, r in enumerate(records_evt):
        if str(r.get("ID")) == event_id:
            row_excel = i + 2
            break
            
    if row_excel is not None:
        idx_estado = SHEETS_CONFIG["evt_eventos"].index("Estado") + 1
        ws_evt.update_cell(row_excel, idx_estado, "Anulado")
        _load_evt_df.clear()

    # 2. Anular en finanzas
    try:
        from secciones.finanzas_aucca import HOJA
        ws_fin = _open_ws(HOJA)
        headers_fin = ws_fin.row_values(1)
        if "Anulado" in headers_fin:
            idx_anu = headers_fin.index("Anulado") + 1
            records_fin = ws_fin.get_all_records()
            updates = []
            for i, r in enumerate(records_fin):
                detalle = str(r.get("Detalle", ""))
                # Búsqueda por Detalle
                if event_name in detalle and (detalle.startswith("Ventas en") or detalle.startswith("Insumo en") or detalle.startswith("Liquidación x")):
                    updates.append(gspread.Cell(row=i+2, col=idx_anu, value="TRUE"))

            if updates:
                ws_fin.update_cells(updates)
    except Exception as e:
        import streamlit as st
        st.error(f"Error al intentar anular en Finanzas: {e}")

def _marcar_cerrado(event_id, a, m, t, n=0):
    ws = _open_ws("evt_eventos")
    records = ws.get_all_records()
    row_excel = None
    for i, r in enumerate(records):
        if str(r.get("ID")) == event_id:
            row_excel = i + 2
            break
            
    if row_excel is not None:
        idx_estado = SHEETS_CONFIG["evt_eventos"].index("Estado") + 1
        idx_asist = SHEETS_CONFIG["evt_eventos"].index("Asistentes") + 1
        idx_muj = SHEETS_CONFIG["evt_eventos"].index("Mujeres_Pct") + 1
        idx_terc = SHEETS_CONFIG["evt_eventos"].index("TerceraEdad_Pct") + 1
        idx_nin = SHEETS_CONFIG["evt_eventos"].index("Ninos_Pct") + 1
        idx_closed = SHEETS_CONFIG["evt_eventos"].index("ClosedAt") + 1
        
        now_str = pd.Timestamp.now(tz=STGO).strftime("%Y-%m-%d %H:%M:%S")
        
        import gspread
        updates = [
            gspread.Cell(row=row_excel, col=idx_estado, value="Cerrado"),
            gspread.Cell(row=row_excel, col=idx_asist, value=a),
            gspread.Cell(row=row_excel, col=idx_muj, value=m),
            gspread.Cell(row=row_excel, col=idx_terc, value=t),
            gspread.Cell(row=row_excel, col=idx_nin, value=n),
            gspread.Cell(row=row_excel, col=idx_closed, value=now_str)
        ]
        ws.update_cells(updates)
        _load_evt_df.clear()


def _ejecutar_cierre(event_id, event_name, pagos_por_persona, gastos_por_persona, traspasos, asis, muj, terc, nin, caja_central, closed_by):
    """
    Función de inyección maestra a Finanzas.
    1. Agrega 1 Ingreso en Finanzas por cada persona que cobró una caja.
    2. Agrega 1 Gasto por cada persona que gastó en Insumos.
    3. Agrega 1 Traspaso sugerido por cada liquidación calculada (Traspasos Peer-to-Peer).
    """
    try:
        from secciones.finanzas_aucca import HOJA, _ensure_sheet_headers
        ws_fin = _open_ws(HOJA)
        hdrs_fin = _ensure_sheet_headers(ws_fin)
    except Exception as e:
        st.error(f"Falla conexión finanzas: {e}")
        return
        
    now = pd.Timestamp.now(tz=STGO)
    date_str_mov = now.strftime("%Y-%m-%d")
    date_str_record = now.strftime("%Y-%m-%d %H:%M:%S")

    filas_a_insertar = []

    # 1. Ingresos por Ventas (a quien haya cobrado)
    for persona, rec in pagos_por_persona.items():
        if rec > 0 and persona:
            rec_ingreso = {
                "ID": str(uuid.uuid4()),"Tipo": "Ingreso","Detalle": f"Ventas en {event_name}",
                "Categoría": "Venta Evento", "Fecha": date_str_mov,"Persona": persona,
                "Persona_Origen": "","Persona_Destino": "",
                "Monto": str(int(rec)), "Created_At": date_str_record,"Created_By": closed_by,"Anulado": ""
            }
            filas_a_insertar.append([str(rec_ingreso.get(h, "")) for h in hdrs_fin])

    # 2. Gastos por Insumos
    for persona, deuda in gastos_por_persona.items():
        if deuda > 0 and persona:
            rec_gasto = {
                "ID": str(uuid.uuid4()),"Tipo": "Gasto","Detalle": f"Insumo en {event_name}",
                "Categoría": "Gasto Insumos", "Fecha": date_str_mov,"Persona": persona,
                "Persona_Origen": "","Persona_Destino": "",
                "Monto": str(int(deuda)),"Created_At": date_str_record,"Created_By": closed_by,"Anulado": ""
            }
            filas_a_insertar.append([str(rec_gasto.get(h, "")) for h in hdrs_fin])

    # 3. Traspasos automáticos de Liquidación P2P
    for t in traspasos:
        deudor = t["de"]
        acreedor = t["a"]
        monto = t["monto"]
        
        # Mapeo a la persona física que recibe dinero institucional
        dest = caja_central if acreedor == "🏦 Caja Central Aucca" else acreedor
        ori = caja_central if deudor == "🏦 Caja Central Aucca" else deudor
        
        if monto > 0 and ori and dest and ori != dest:
            rec_traspaso = {
                "ID": str(uuid.uuid4()),"Tipo": "Traspaso","Detalle": f"Liquidación x {event_name}",
                "Categoría": "","Fecha": date_str_mov,"Persona": "",
                "Persona_Origen": ori,"Persona_Destino": dest,
                "Monto": str(int(monto)),"Created_At": date_str_record,"Created_By": closed_by,"Anulado": ""
            }
            filas_a_insertar.append([str(rec_traspaso.get(h, "")) for h in hdrs_fin])

    if filas_a_insertar:
        ws_fin.append_rows(filas_a_insertar, value_input_option="USER_ENTERED")
        st.success("Toda la data de liquidación cruzada se inyectó sincronizadamente a la Bóveda de Aucca.")

    st.balloons()
