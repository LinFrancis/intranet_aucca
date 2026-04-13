import sys
import os
import uuid
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from secciones.gestion_eventos import _ensure_evt_sheet, SHEETS_CONFIG, STGO

def poblar_datos_demo():
    print("Iniciando inyección de datos DEMO diversos...")
    
    creds = Credentials.from_service_account_info(
        st.secrets["gspread"],
        scopes=["https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"],
    )
    client = gspread.authorize(creds)
    SPREADSHEET_KEY = "1C8njkp0RQMdXnxuJvPvfK_pNZHQSi7q7dUPeUg-2624"
    sh = client.open_by_key(SPREADSHEET_KEY)

    event_id = str(uuid.uuid4())
    now = pd.Timestamp.now(tz=STGO)
    date_d = now.strftime("%Y-%m-%d")
    date_t = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # Asegurar que todas las hojas existen
    for s_name in ["evt_eventos", "evt_productos", "evt_inventario", "evt_ventas", "evt_notas"]:
        _ensure_evt_sheet(s_name)

    def format_row(s_name, rec):
        return [str(rec.get(h, "")) for h in SHEETS_CONFIG[s_name]]

    # 1. Crear el Evento Demo
    detalles_ficha = "📋 *Instrucciones:* Esta es una sesión de prueba inofensiva.\n\nContiene:\n- 1 Mesa ya Pagada y entregada.\n- 1 Mesa Pendiente de Cobro y de Entrega.\n- Diferentes saldos negativos y positivos entre los participantes."
    
    rec_evento = {
        "ID": event_id, "Nombre": "🍕 DEMO: Pizza + Karaoke v2", "Tipo": "Evento / Fiesta",
        "Fecha": date_d, "Estado": "Abierto", "CreatedBy": "Sistema DEMO", "CreatedAt": date_t,
        "Detalles_Ficha": detalles_ficha
    }
    sh.worksheet("evt_eventos").append_row(format_row("evt_eventos", rec_evento), value_input_option="USER_ENTERED")

    # 2. Add Products con Sus Precios
    productos = [
        {"Nombre": "Pizza Margarita", "P": "4500"},
        {"Nombre": "Pizza Pepperoni", "P": "5000"},
        {"Nombre": "Cerveza Artesanal", "P": "2500"},
        {"Nombre": "Pisco Sour", "P": "3000"},
        {"Nombre": "Entrada Karaoke", "P": "1000"}
    ]
    prods_batch = [format_row("evt_productos", {"EventID": event_id, "Nombre": p["Nombre"], "Precio_Base": p["P"], "CreatedBy": "Sistema"}) for p in productos]
    sh.worksheet("evt_productos").append_rows(prods_batch, value_input_option="USER_ENTERED")

    # 3. Add Inventory (Produccion y Gastos de Bolsillo)
    inventario = [
        {"Prod": "Pizza Margarita", "Cant": "15", "Gsto": "0", "Pers": ""},           # Se elaboraron pizzas
        {"Prod": "[Gasto] Harina y Queso", "Cant": "0", "Gsto": "15000", "Pers": "🌿Camilú"}, # Camilú compró
        {"Prod": "Cerveza Artesanal", "Cant": "30", "Gsto": "0", "Pers": ""},
        {"Prod": "[Gasto] Pack de Cervezas", "Cant": "0", "Gsto": "20000", "Pers": "🪈Francis"},
        {"Prod": "Pisco Sour", "Cant": "20", "Gsto": "0", "Pers": ""},
        {"Prod": "[Gasto] Pisco y Limones", "Cant": "0", "Gsto": "18000", "Pers": "🍃Diego"}
    ]
    inv_batch = [format_row("evt_inventario", {
        "ID": str(uuid.uuid4()), "EventID": event_id, "Producto": i["Prod"],
        "Cantidad": i["Cant"], "Gasto_Materiales": i["Gsto"], "Persona_Gasto": i["Pers"],
        "Persona_Registro": "Sistema", "CreatedAt": date_t
    }) for i in inventario]
    sh.worksheet("evt_inventario").append_rows(inv_batch, value_input_option="USER_ENTERED")
    
    # 4. Add Ventas Mixtas
    ventas = [
        # Pagada Completa y Entregada (por Transferencia a Diego)
        {"Mesa": "Familia Miranda", "Prod": "Pizza Margarita", "Cant": "2", "Prc": "4500", "Tot": "9000", "EstEnt": "Entregado", "EstPago": "Pagado", "Medio": "Transferencia", "Quien": "🍃Diego"},
        {"Mesa": "Familia Miranda", "Prod": "Cerveza Artesanal", "Cant": "2", "Prc": "2500", "Tot": "5000", "EstEnt": "Entregado", "EstPago": "Pagado", "Medio": "Transferencia", "Quien": "🍃Diego"},
        
        # Pagada Efectivo, No Entregada aún
        {"Mesa": "Los Vip", "Prod": "Pisco Sour", "Cant": "4", "Prc": "3000", "Tot": "12000", "EstEnt": "Pendiente", "EstPago": "Pagado", "Medio": "Efectivo", "Quien": "🌿Camilú"},
        
        # Por Pagar y Por Entregar (Totalmente Abierta)
        {"Mesa": "Mesa Solitaria", "Prod": "Pizza Pepperoni", "Cant": "1", "Prc": "5000", "Tot": "5000", "EstEnt": "Pendiente", "EstPago": "Pendiente", "Medio": "", "Quien": ""},
    ]
    
    v_batch = [format_row("evt_ventas", {
        "ID": str(uuid.uuid4()), "EventID": event_id, "Mesa": v["Mesa"],
        "Producto": v["Prod"], "Cantidad": v["Cant"], "Precio_Unitario": v["Prc"],
        "Total": v["Tot"], "Persona_Registro": "Sistema", "Persona_Cobro": v["Quien"],
        "Estado_Entrega": v["EstEnt"], "Estado_Pago": v["EstPago"], "Medio_Pago": v["Medio"], 
        "CreatedAt": date_t
    }) for v in ventas]
    sh.worksheet("evt_ventas").append_rows(v_batch, value_input_option="USER_ENTERED")
    
    print(f"Todo listo! Event ID del Demo: {event_id}")
    return event_id

if __name__ == "__main__":
    poblar_datos_demo()
