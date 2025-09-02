# secciones/checklist.py

import streamlit as st
import pandas as pd
import datetime as dt
from zoneinfo import ZoneInfo
import plotly.express as px
import re  

from data.google import cargar_datos, append_row

# =========================
# Config y constantes
# =========================
STGO = ZoneInfo("America/Santiago")

SEMANEROS = ["🚴🏻Chalo", "🌿Camilú", "⚽Niko", "🍃Diego", "🪈Francis", "🌌Tais", "🌊Cala"]
# SEMANEROS = ["Chalo", "Camilú", "Niko", "Diego", "Cala"]

# Paleta (inspirada en tu imagen, evitando el morado)
VERDE_COMPLETADAS = "#3E7A3C"
TERRACOTA_PROCESO = "#C46A3A"
CREMA_PENDIENTES = "#E8E0D2"
CARBONO_TEXTO = "#2E2A27"
FONDO_SUAVE = "#F7F3E9"

# =========================
# Utilidades de semana/fechas
# =========================
def semana_bounds(fecha: dt.date):
    """Devuelve (inicio_semana_00:00, fin_semana_23:59:59) con TZ Chile."""
    lunes = fecha - dt.timedelta(days=fecha.weekday())
    inicio = dt.datetime.combine(lunes, dt.time.min).replace(tzinfo=STGO)
    fin = inicio + dt.timedelta(days=6, hours=23, minutes=59, seconds=59)
    return inicio, fin

def etiqueta_semana(inicio: dt.datetime, fin: dt.datetime):
    """Sem. ISO YYYY-Wxx · dd–dd Mes (en español corto)"""
    semanastr = f"Sem. ISO {inicio.strftime('%G')}-W{inicio.strftime('%V')}"
    meses = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    lab = f"{semanastr} · {inicio.day:02d}–{fin.day:02d} {meses[fin.month-1]}"
    return lab

def es_semana_actual(inicio: dt.datetime):
    hoy = dt.datetime.now(tz=STGO)
    return (hoy.isocalendar().year, hoy.isocalendar().week) == (inicio.isocalendar().year, inicio.isocalendar().week)

def _to_naive_ts(x, tz=STGO):
    """
    Devuelve un pandas.Timestamp sin tz (tz-naive) para poder restar/ comparar
    sin errores, convirtiendo a la zona tz indicada si venía con tz.
    Acepta datetime, date, str, Timestamp.
    """
    t = pd.to_datetime(x)
    # Si viene con tz, lo convertimos a la zona deseada y luego quitamos la tz
    if getattr(t, "tzinfo", None) is not None:
        try:
            t = t.tz_convert(tz)
        except Exception:
            # si estaba naive pero envuelto por pandas, tz_convert falla: ignoramos
            pass
        try:
            t = t.tz_localize(None)
        except TypeError:
            # ya era naive
            pass
    else:
        # Ya es naive, nada que quitar
        pass
    return t

def _notes_for_form(dfe_all, tema, zona, tarea, ini_sel, fin_sel, n_actuales=3, n_hist=10):
    df_task = dfe_all[(dfe_all["Tema"] == tema) &
                      (dfe_all["Zona"] == zona) &
                      (dfe_all["Tarea"] == tarea)].copy()
    if df_task.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Solo observaciones con texto real
    df_task = df_task[df_task["Observaciones"].astype(str).str.strip() != ""].copy()

    # Semana actual
    cur = df_task[(df_task["Fecha_dt"] >= ini_sel) & (df_task["Fecha_dt"] <= fin_sel)].copy()
    cur = cur.sort_values("Fecha_dt")
    if not cur.empty:
        cur["acum_tr"] = cur["Porcentaje"].clip(lower=0).cumsum().clip(upper=100)
        cur_view = cur.sort_values("Fecha_dt", ascending=False).head(n_actuales).copy()
    else:
        cur_view = pd.DataFrame(columns=list(df_task.columns) + ["acum_tr"])

    # Historial (anteriores)
    hist = df_task[df_task["Fecha_dt"] < ini_sel].sort_values("Fecha_dt", ascending=False).head(n_hist).copy()

    return cur_view, hist

def init_mensajes_general():
    """
    Asegura que la hoja 'mensajes_general' exista y tenga las columnas correctas.
    Si no existe, la crea vacía con las columnas requeridas.
    """
    try:
        df = cargar_datos("mensajes_general")
    except Exception:
        df = pd.DataFrame()

    required_cols = ["ID","ThreadID","Fecha","Usuario","Mensaje"]

    # Si faltan columnas o está vacío → recrear
    if df.empty or not all(c in df.columns for c in required_cols):
        df = pd.DataFrame(columns=required_cols)
        # Guardar encabezados como primera fila vacía
        append_row("mensajes_general", required_cols)

    return df



# =========================
# Cálculos de avance
# =========================
def normalizar_estado(df_estado: pd.DataFrame) -> pd.DataFrame:
    if df_estado is None or df_estado.empty:
        return pd.DataFrame(columns=["Fecha","Usuario","Tema","Zona","Tarea","Completada","Porcentaje","Observaciones","Fecha_dt"])
    dfe = df_estado.copy()
    dfe.columns = [c.strip() for c in dfe.columns]
    dfe["Porcentaje"] = pd.to_numeric(dfe.get("Porcentaje", 0), errors="coerce").fillna(0).astype(int)
    dfe["Fecha_dt"] = pd.to_datetime(dfe["Fecha"], errors="coerce")
    # asumimos hora local
    try:
        dfe["Fecha_dt"] = dfe["Fecha_dt"].dt.tz_localize(STGO, nonexistent="NaT", ambiguous="NaT")
    except Exception:
        # si ya viene tz-aware, solo convertimos
        dfe["Fecha_dt"] = dfe["Fecha_dt"].dt.tz_convert(STGO)
    for col in ["Usuario","Tema","Zona","Tarea","Observaciones"]:
        if col in dfe.columns:
            dfe[col] = dfe[col].astype(str).fillna("").str.strip()
    return dfe

def acumulado_por_tarea_semana(dfe_week: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve DF con índice (Tema, Zona, Tarea) y columnas:
    - acumulado (cap 100)
    - estado (Pendiente/En proceso/Completada)
    """
    if dfe_week.empty:
        return pd.DataFrame(columns=["Tema","Zona","Tarea","acumulado","estado"]).set_index(["Tema","Zona","Tarea"])

    agg = (
        dfe_week.groupby(["Tema","Zona","Tarea"], dropna=False)["Porcentaje"]
        .sum()
        .clip(upper=100)
        .rename("acumulado")
        .reset_index()
        .set_index(["Tema","Zona","Tarea"])
    )
    def _estado(x):
        if x >= 100: return "Completada"
        if x > 0:    return "En proceso"
        return "Pendiente"
    agg["estado"] = agg["acumulado"].apply(_estado)
    return agg

def merge_catalogo_estado(df_tareas: pd.DataFrame, agg: pd.DataFrame) -> pd.DataFrame:
    """
    Une catálogo (todas las tareas) con acumulados de la semana.
    A las tareas sin registros les pone acumulado=0 (Pendiente).
    """
    base = df_tareas[["Tema","Zona","Tarea"]].drop_duplicates().copy()
    base = base.merge(agg.reset_index(), on=["Tema","Zona","Tarea"], how="left")
    base["acumulado"] = base["acumulado"].fillna(0).astype(int)
    def _estado(x):
        if x >= 100: return "Completada"
        if x > 0:    return "En proceso"
        return "Pendiente"
    base["estado"] = base["acumulado"].apply(_estado)
    return base

def porcentaje_por_tema(df_base: pd.DataFrame) -> pd.DataFrame:
    """% por Tema = suma(acumulado tareas) / (100 * N tareas del Tema)"""
    if df_base.empty:
        return pd.DataFrame(columns=["Tema","n_tareas","suma_acum","pct"])
    by = df_base.groupby("Tema")
    out = by.agg(
        n_tareas=("Tarea","nunique"),
        suma_acum=("acumulado","sum")
    ).reset_index()
    out["pct"] = (out["suma_acum"] / (100 * out["n_tareas"])).fillna(0) * 100
    return out

def calcular_acumulado_semana_a_semana(df_task, fecha_inicio, fecha_hoy, tz=STGO):
    """
    Calcula el pendiente acumulado de una tarea semana a semana.

    Reglas:
    - Semana sin avances → +100%.
    - Semana con avance parcial (<100) → + (100 - avance).
    - Semana con >=100 → acumulado se reinicia a 0.
    - Si en la semana actual hubo algún avance (>0) → se borra el histórico y queda (100 - avance actual).
    """
    ini_sel = pd.to_datetime(fecha_inicio)
    hoy = pd.to_datetime(fecha_hoy)

    # Asegurar TZ
    if ini_sel.tzinfo is None:
        ini_sel = ini_sel.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
    else:
        ini_sel = ini_sel.tz_convert(tz)
    if hoy.tzinfo is None:
        hoy = hoy.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
    else:
        hoy = hoy.tz_convert(tz)

    # Sin registros: acumula desde ini_sel
    if df_task.empty:
        semanas_transcurridas = ((hoy - ini_sel).days // 7) + 1
        return semanas_transcurridas * 100, None, "Nunca"

    # Normalizar DF
    d = df_task.copy().sort_values("Fecha_dt")
    try:
        d["Fecha_dt"] = d["Fecha_dt"].dt.tz_convert(tz)
    except Exception:
        if getattr(d["Fecha_dt"].dt, "tz", None) is None:
            d["Fecha_dt"] = d["Fecha_dt"].dt.tz_localize(
                tz, nonexistent="shift_forward", ambiguous="NaT"
            )

    # Semana (lunes) por fila
    d["week_start_date"] = d["Fecha_dt"].dt.normalize() - pd.to_timedelta(
        d["Fecha_dt"].dt.weekday, unit="D"
    )

    # Suma semanal de % (sin clip aquí; la regla decide)
    weekly_sum = (
        d.groupby("week_start_date", dropna=False)["Porcentaje"]
         .sum()
         .astype(float)
    )

    # Lunes de ini y de hoy
    ini_monday = ini_sel.normalize() - pd.to_timedelta(ini_sel.weekday(), unit="D")
    hoy_monday = hoy.normalize() - pd.to_timedelta(hoy.weekday(), unit="D")

    # (FIX) arrancar desde la semana más antigua disponible, no solo desde ini_sel
    if not d.empty:
        min_ts = d["Fecha_dt"].min()
        min_monday = min_ts.normalize() - pd.to_timedelta(min_ts.weekday(), unit="D")
        if min_monday < ini_monday:
            ini_monday = min_monday

    # Acumulado histórico semana a semana
    acumulado = 0
    cur = ini_monday
    while cur <= hoy_monday:
        total_semana = float(weekly_sum.get(cur, 0.0))
        if total_semana >= 100:
            acumulado = 0
        elif total_semana > 0:
            acumulado += (100 - total_semana)
        else:
            acumulado += 100
        cur += dt.timedelta(days=7)

    # Semana actual: si hubo avance, borra histórico y deja solo el pendiente de esta semana
    total_actual = float(weekly_sum.get(hoy_monday, 0.0))
    if total_actual > 0:
        acumulado = max(0, 100 - min(total_actual, 100))

    # Última fila (para mostrar "última vez")
    ultima_fila = d.iloc[-1] if not d.empty else None

    # Días desde la última vez usando la columna "Fecha"
    if ultima_fila is not None:
        fecha_raw = ultima_fila.get("Fecha")
        fecha_ultima = pd.to_datetime(fecha_raw, errors="coerce")
        if pd.notna(fecha_ultima):
            if fecha_ultima.tzinfo is None:
                fecha_ultima = fecha_ultima.tz_localize(
                    tz, nonexistent="shift_forward", ambiguous="NaT"
                )
            else:
                fecha_ultima = fecha_ultima.tz_convert(tz)
            dias = (hoy.date() - fecha_ultima.date()).days
            if dias == 0:
                dias_sin_hacer = "Hoy"
            elif dias == 1:
                dias_sin_hacer = "hace 1 día"
            else:
                dias_sin_hacer = f"hace {dias} días"
        else:
            dias_sin_hacer = "Nunca"
    else:
        dias_sin_hacer = "Nunca"

    return acumulado, ultima_fila, dias_sin_hacer

# =========================
# UI helpers
# =========================
def kpi_card(label, value, help_text=None):
    st.markdown(
        f"""
        <div style="background:{FONDO_SUAVE};border:1px solid #e7ddc6;border-radius:14px;padding:10px 14px;margin-bottom:8px;">
          <div style="font-size:0.9rem;color:{CARBONO_TEXTO};opacity:0.8;">{label}</div>
          <div style="font-size:1.4rem;font-weight:600;color:{CARBONO_TEXTO};">{value}</div>
          {f'<div style="font-size:0.8rem;opacity:0.7;">{help_text}</div>' if help_text else ''}
        </div>
        """,
        unsafe_allow_html=True
    )

def chips(items):
    if not items: 
        st.write("—")
        return
    s = "".join([f'<span style="display:inline-block;border:1px solid #cfcfcf;border-radius:999px;padding:2px 8px;margin:2px;background:white;">{x}</span>' for x in items])
    st.markdown(s, unsafe_allow_html=True)

def obs_card(row):
    # Observación en tarjeta
    fecha_s = "—"
    if pd.notna(row.get("Fecha_dt")):
        fecha_s = row["Fecha_dt"].strftime("%d-%m-%Y %H:%M")
    st.markdown(
        f"""
        <div style="background:#FFFDF6;border:1px solid #E7DDC6;border-radius:12px;padding:10px 12px;margin-bottom:8px;">
          <div style="font-size:0.85rem;color:#5a5a5a;margin-bottom:6px;">
            <span style="border:1px solid #cfcfcf;border-radius:999px;padding:2px 8px;margin-right:6px;">{row.get('Tema','—')}</span>
            <span style="border:1px solid #cfcfcf;border-radius:999px;padding:2px 8px;margin-right:6px;">{row.get('Zona','—')}</span>
            <span style="border:1px solid #cfcfcf;border-radius:999px;padding:2px 8px;margin-right:6px;">{row.get('Tarea','—')}</span>
            <span style="border:1px solid #cfcfcf;border-radius:999px;padding:2px 8px;margin-right:6px;"> {row.get('Usuario','—')}</span>
            <span style="border:1px solid #cfcfcf;border-radius:999px;padding:2px 8px;margin-right:6px;">🗓️ {fecha_s}</span>
            <span style="border:1px solid #cfcfcf;border-radius:999px;padding:2px 8px;margin-right:6px;">✅ {int(pd.to_numeric(row.get('Porcentaje',0), errors='coerce') or 0)}%</span>
          </div>
          <div style="white-space:pre-wrap; line-height:1.25; color:{CARBONO_TEXTO};">{(row.get('Observaciones') or '').replace('<','&lt;').replace('>','&gt;')}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

# =========================
# Render principal
# =========================

dias_semana = {
    "Monday": "Lunes",
    "Tuesday": "Martes",
    "Wednesday": "Miércoles",
    "Thursday": "Jueves",
    "Friday": "Viernes",
    "Saturday": "Sábado",
    "Sunday": "Domingo"
}



def render():
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("## 📋 Checklist de semanerx")
    with col2:
        # -------------------------
        # Botón para borrar caché
        # -------------------------
        if st.button("Actualizar base de datos"):
            st.cache_data.clear()
            try:
                st.cache_resource.clear()
            except Exception:
                pass
            st.success("Base de datos actualizada ✅")
            st.rerun()
        
    # -------------------------
    # Definir fechas base
    # -------------------------
    
    ahora = dt.datetime.now(tz=STGO)      # datetime actual (con hora y tz)
    hoy = ahora.date()                    # solo fecha (naive)
    lunes_hoy = hoy - dt.timedelta(days=hoy.weekday())
    n_semana = hoy.isocalendar()[1]

    dia = dias_semana[ahora.strftime("%A")]
    st.caption(f"#### Hoy: {dia} {ahora.strftime('%d-%m-%Y')}. Semana:  {n_semana}")
    
    # -------------------------
    # Inicializar semana en session_state
    # -------------------------
    if "week_start" not in st.session_state:
        st.session_state.week_start = lunes_hoy
    if "week_end" not in st.session_state:
        st.session_state.week_end = st.session_state.week_start + dt.timedelta(days=6)
    if "date_anchor" not in st.session_state:
        st.session_state.date_anchor = st.session_state.week_start

    # -------------------------
    # Calcular rango de la semana seleccionada
    # -------------------------
    
    ini_sel = dt.datetime.combine(st.session_state.week_start, dt.time.min).replace(tzinfo=STGO)
    fin_sel = dt.datetime.combine(st.session_state.week_end, dt.time.max).replace(tzinfo=STGO)

    

    # -------------------------
    # Cargar dataframes iniciales
    # -------------------------
    df_tareas = cargar_datos("tareas_semaneros")
    try:
        dfe_raw = cargar_datos("estado_tareas")
    except Exception:
        dfe_raw = pd.DataFrame(columns=["Fecha","Usuario","Tema","Zona","Tarea",
                                        "Completada","Porcentaje","Observaciones"])
    dfe_all = normalizar_estado(dfe_raw)

    # -------------------------
    # Tabs principales
    # -------------------------
    TAB_LABELS = ["📝 Mensajes","✅ Registrar avance", "📊 Explorar avances",]

    default_idx = st.session_state.get("tab_idx", 0)
    tab_label = st.radio(
        "Navegación",
        TAB_LABELS,
        index=default_idx,
        horizontal=True,
        key="tab_selector"
    )
    st.session_state["tab_idx"] = TAB_LABELS.index(tab_label)


    # ------------------------
    # TAB 1: Explorar avances
    # ------------------------
    if tab_label == "📊 Explorar avances":
        
        # ======================
        # Funciones auxiliares
        # ======================

        def init_week_state():
            hoy = dt.datetime.now(tz=STGO).date()
            lunes_hoy = hoy - dt.timedelta(days=hoy.weekday())
            if "week_start" not in st.session_state:
                st.session_state.week_start = lunes_hoy
            if "week_end" not in st.session_state:
                st.session_state.week_end = st.session_state.week_start + dt.timedelta(days=6)
            if "date_anchor" not in st.session_state:
                st.session_state.date_anchor = st.session_state.week_start
            return lunes_hoy

        def week_navigation(lunes_hoy):
            def _jump_week():
                d = st.session_state.date_anchor
                ws, we = semana_bounds(d)
                st.session_state.week_start = ws.date()
                st.session_state.week_end = we.date()

            cprev, cnext, cdate = st.columns([1.2, 1.5, 3.3])
            with cprev:
                if st.button("◀︎ Semana anterior"):
                    st.session_state.week_start -= dt.timedelta(days=7)
                    st.session_state.week_end = st.session_state.week_start + dt.timedelta(days=6)
                    st.session_state.date_anchor = st.session_state.week_start
            with cnext:
                disable_next = st.session_state.week_start >= lunes_hoy
                if st.button("Semana siguiente ▶︎", disabled=disable_next):
                    st.session_state.week_start += dt.timedelta(days=7)
                    st.session_state.week_end = st.session_state.week_start + dt.timedelta(days=6)
                    st.session_state.date_anchor = st.session_state.week_start
            with cdate:
                st.date_input("Ir a semana de…",
                            value=st.session_state.date_anchor,
                            key="date_anchor",
                            on_change=_jump_week)

            ini_sel = dt.datetime.combine(st.session_state.week_start, dt.time.min).replace(tzinfo=STGO)
            fin_sel = dt.datetime.combine(st.session_state.week_end, dt.time.max).replace(tzinfo=STGO)
            return ini_sel, fin_sel

        def load_dataframes(ini_sel, fin_sel):
            df_tareas = cargar_datos("tareas_semaneros")
            try:
                dfe_raw = cargar_datos("estado_tareas")
            except Exception:
                dfe_raw = pd.DataFrame(columns=["Fecha","Usuario","Tema","Zona","Tarea",
                                                "Completada","Porcentaje","Observaciones"])
            dfe_all = normalizar_estado(dfe_raw)
            in_week = (dfe_all["Fecha_dt"] >= ini_sel) & (dfe_all["Fecha_dt"] <= fin_sel)
            dfe_week = dfe_all[in_week].copy()
            agg_week = acumulado_por_tarea_semana(dfe_week)
            base = merge_catalogo_estado(df_tareas, agg_week)
            return df_tareas, dfe_all, dfe_week, base

        def render_kpis(base):
            total_tareas   = int(base["Tarea"].nunique())
            n_completadas  = int((base["estado"] == "Completada").sum())
            n_proceso      = int((base["estado"] == "En proceso").sum())
            n_pendientes   = int((base["estado"] == "Pendiente").sum())
            pct_global     = (base["acumulado"].sum() / (100 * total_tareas) * 100) if total_tareas > 0 else 0.0

            st.markdown("""
            <style>
            div[data-testid="stMetric"] {
                background: #F7F3E9;
                border: 1px solid #E7DDC6;
                border-radius: 14px;
                padding: 10px 12px;
            }
            div[data-testid="stMetricLabel"] > p {
                color: #2E2A27;
                opacity: 0.75;
                font-size: 0.92rem;
                margin-bottom: 4px;
            }
            div[data-testid="stMetricValue"] > div {
                color: #2E2A27;
                font-weight: 700;
                font-size: 1.35rem;
            }
            </style>
            """, unsafe_allow_html=True)

            c1, c2, c3, c4, c5 = st.columns(5)
            with c1: st.metric("% global", f"{pct_global:.1f}%")
            with c2: st.metric("Completadas", f"{n_completadas}")
            with c3: st.metric("En proceso", f"{n_proceso}")
            with c4: st.metric("Pendientes", f"{n_pendientes}")
            with c5: st.metric("Total tareas", f"{total_tareas}")
            return pct_global, n_completadas, n_proceso, n_pendientes

        # -------------------
        # GRÁFICOS
        # -------------------

        def chart_pct_tema(base):
            metatema = porcentaje_por_tema(base).sort_values("pct", ascending=False)
            st.markdown("### Avances por Tema (%)")
            if metatema.empty:
                st.info("Sin datos para esta semana.")
            else:
                fig = px.bar(
                    metatema,
                    x="Tema",
                    y="pct",
                    text=metatema["pct"].round(1).astype(str) + "%",
                    color_discrete_sequence=[VERDE_COMPLETADAS],
                    labels={"pct":"% completado"},
                )
                fig.update_traces(textposition="outside")
                fig.update_layout(yaxis_range=[0, 100],
                                xaxis={'categoryorder':'array','categoryarray':metatema["Tema"].tolist()})
                st.plotly_chart(fig, use_container_width=True)

        def chart_donut_global(pct_global, n_completadas, n_proceso, n_pendientes):
            st.markdown("##### Global semanal")
            donut_df = pd.DataFrame({
                "estado": ["Completadas","En proceso","Pendientes"],
                "conteo": [n_completadas, n_proceso, n_pendientes],
            })
            fig = px.pie(
                donut_df,
                names="estado",
                values="conteo",
                hole=0.55,
                color="estado",
                color_discrete_map={
                    "Completadas": VERDE_COMPLETADAS,
                    "En proceso": TERRACOTA_PROCESO,
                    "Pendientes": CREMA_PENDIENTES
                }
            )
            fig.update_layout(annotations=[dict(text=f"{pct_global:.1f}%", x=0.5, y=0.5, font_size=18, showarrow=False)])
            st.plotly_chart(fig, use_container_width=True)

        def chart_line_global(dfe_all, df_tareas, ini_sel, weeks_back=8):
            st.markdown("##### Tendencia global por estado")

            end_week_start_date = ini_sel.date()
            week_starts = [end_week_start_date - dt.timedelta(weeks=i) for i in reversed(range(weeks_back))]

            hist_rows = []
            for ws_date in week_starts:
                ws = dt.datetime.combine(ws_date, dt.time.min).replace(tzinfo=STGO)
                we = ws + dt.timedelta(days=6, hours=23, minutes=59, seconds=59)

                in_w = (dfe_all["Fecha_dt"] >= ws) & (dfe_all["Fecha_dt"] <= we)
                dfe_w = dfe_all[in_w].copy()

                # acumulados por tarea y merge
                agg_w = acumulado_por_tarea_semana(dfe_w)
                base_w = merge_catalogo_estado(df_tareas, agg_w)

                if base_w.empty:
                    total = 0
                    comp = proc = pend = 0
                    pct_global = 0
                else:
                    total = base_w["Tarea"].nunique()
                    comp = (base_w["estado"] == "Completada").sum()
                    proc = (base_w["estado"] == "En proceso").sum()
                    pend = (base_w["estado"] == "Pendiente").sum()

                    if total > 0:
                        pct_comp = comp / total * 100
                        pct_proc = proc / total * 100
                        pct_pend = pend / total * 100
                        pct_global = base_w["acumulado"].sum() / (100 * total) * 100
                    else:
                        pct_comp = pct_proc = pct_pend = pct_global = 0

                hist_rows.append({
                    "semana_iso": f"{ws.isocalendar().year}-W{ws.isocalendar().week:02d}",
                    "Completadas": pct_comp,
                    "En proceso": pct_proc,
                    "Pendientes": pct_pend,
                    "Global": pct_global,
                })

            hist_df = pd.DataFrame(hist_rows)

            if hist_df.empty:
                st.info("No hay datos suficientes para construir la tendencia global.")
                return

            semana_order = hist_df["semana_iso"].tolist()

            # Pasar a formato largo para plotly
            df_long = hist_df.melt(
                id_vars="semana_iso",
                value_vars=["Completadas","En proceso","Pendientes","Global"],
                var_name="Estado", value_name="pct"
            )

            fig = px.line(
                df_long,
                x="semana_iso", y="pct", color="Estado",
                markers=True,
                category_orders={"semana_iso": semana_order},
                color_discrete_map={
                    "Completadas": VERDE_COMPLETADAS,
                    "En proceso": TERRACOTA_PROCESO,
                    "Pendientes": CREMA_PENDIENTES,
                    "Global": "#9112BC"  # Negro para destacar la línea global
                },
                labels={"pct": "% de tareas", "semana_iso": "Semana ISO"}
            )
            fig.update_yaxes(range=[0,100], ticksuffix="%")
            st.plotly_chart(fig, use_container_width=True)

        def chart_descomposicion_tema(base, metatema=None):
            st.markdown("##### Descomposición por Tema (% de tareas)")
            if base.empty:
                st.info("Sin datos.")
                return

            counts = (
                base.pivot_table(index="Tema", columns="estado", values="Tarea",
                                aggfunc="nunique", fill_value=0)
                .reset_index()
            )
            
            # Asegurar columnas faltantes
            for c in ["Pendiente", "En proceso", "Completada"]:
                if c not in counts.columns:
                    counts[c] = 0

            counts["total"] = counts[["Pendiente", "En proceso", "Completada"]].sum(axis=1)
                        
            
            # counts["total"] = counts[["Pendiente", "En proceso", "Completada"]].sum(axis=1)
            # counts = counts[counts["total"] > 0].copy()

            df_long = counts.melt(
                id_vars=["Tema", "total"],
                value_vars=["Pendiente", "En proceso", "Completada"],
                var_name="Estado",
                value_name="count"
            )
            df_long["pct"] = (df_long["count"] / df_long["total"] * 100).fillna(0)

            order_temas = metatema["Tema"].tolist() if metatema is not None and not metatema.empty else counts["Tema"].tolist()
            colormap = {"Completada": VERDE_COMPLETADAS,
                        "En proceso": TERRACOTA_PROCESO,
                        "Pendiente": CREMA_PENDIENTES}

            fig = px.bar(
                df_long,
                x="Tema",
                y="pct",
                color="Estado",
                barmode="stack",
                category_orders={"Tema": order_temas, "Estado": ["Pendiente","En proceso","Completada"]},
                color_discrete_map=colormap,
                labels={"pct": "% de tareas"},
                custom_data=["count","total"]
            )
            fig.update_traces(texttemplate="%{y:.0f}%",
                            textposition="inside",
                            hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y:.0f}%"
                                            "<br>(%{customdata[0]} de %{customdata[1]} tareas)<extra></extra>")
            fig.update_yaxes(range=[0,100], ticksuffix="%")
            st.plotly_chart(fig, use_container_width=True)

        def chart_tendencia(dfe_all, df_tareas, ini_sel, weeks_back=8):
            st.markdown("##### Tendencia semanal por Tema")
            temas_all = sorted(df_tareas["Tema"].dropna().unique().tolist())
            sel = st.multiselect("Filtrar temas (opcional)", temas_all, default=[])

            # Si el usuario no selecciona nada, usamos todos
            if not sel:
                sel = temas_all

            end_week_start_date = ini_sel.date()
            week_starts = [end_week_start_date - dt.timedelta(weeks=i) for i in reversed(range(weeks_back))]

            hist_rows = []
            for ws_date in week_starts:
                ws = dt.datetime.combine(ws_date, dt.time.min).replace(tzinfo=STGO)
                we = ws + dt.timedelta(days=6, hours=23, minutes=59, seconds=59)
                in_w = (dfe_all["Fecha_dt"] >= ws) & (dfe_all["Fecha_dt"] <= we)
                dfe_w = dfe_all[in_w].copy()
                agg_w = acumulado_por_tarea_semana(dfe_w)
                base_w = merge_catalogo_estado(df_tareas, agg_w)
                meta_w = porcentaje_por_tema(base_w)
                for _, r in meta_w.iterrows():
                    hist_rows.append({"week_start": ws_date,
                                    "semana_iso": f"{ws.isocalendar().year}-W{ws.isocalendar().week:02d}",
                                    "Tema": r["Tema"],
                                    "pct": float(r["pct"]) if pd.notna(r["pct"]) else 0.0})
            hist_df = pd.DataFrame(hist_rows)

            if hist_df.empty:
                st.info("No hay datos suficientes para construir la tendencia.")
                return

            semana_order = hist_df.sort_values("week_start")["semana_iso"].unique().tolist()
            n_temas = hist_df["Tema"].nunique()
            facet_cols = min(3, max(1, n_temas))

            fig_facets = px.line(
                hist_df[hist_df["Tema"].isin(sel)],
                x="semana_iso", y="pct",
                facet_col="Tema", facet_col_wrap=facet_cols,
                markers=True,
                category_orders={"semana_iso": semana_order},
                color_discrete_sequence=[VERDE_COMPLETADAS],
                labels={"pct": "% completado"}
            )
            fig_facets.update_yaxes(range=[0,100])
            fig_facets.update_layout(showlegend=False)
            for ann in fig_facets.layout.annotations:
                if ann.text and "Tema=" in ann.text:
                    ann.text = ann.text.split("Tema=")[-1]
            st.plotly_chart(fig_facets, use_container_width=True)

        
        def chart_participacion(dfe_week, dfe_all):
            st.markdown("##### 👥 Participación (semana seleccionada)")

            # --- Controles globales ---
            col_filtros = st.columns([2, 2])
            with col_filtros[0]:
                filtro_usuario = st.selectbox("🔍 Filtrar usuario (opcional)", ["Todos"] + SEMANEROS)
            with col_filtros[1]:
                semanas_atras = st.number_input("⏱ Semanas a revisar", min_value=1, max_value=52, value=4, step=1)

            # --- KPIs de participación ---
            activos_set = set(dfe_week["Usuario"].dropna().unique().tolist()) & set(SEMANEROS)
            pct_activos = (len(activos_set) / len(SEMANEROS) * 100) if SEMANEROS else 0.0
            kpi_card("Auccanes activos", f"{pct_activos:.0f}%")

            temas_por_persona = (
                dfe_week.groupby("Usuario")["Tema"]
                .unique().apply(lambda xs: sorted([x for x in xs if x and str(x).strip() != ""]))
                if not dfe_week.empty else pd.Series(dtype=object)
            )
            last_in_week = dfe_week.groupby("Usuario")["Fecha_dt"].max() if not dfe_week.empty else pd.Series()
            last_ever = dfe_all.groupby("Usuario")["Fecha_dt"].max() if not dfe_all.empty else pd.Series()

            avances_count = dfe_week.groupby("Usuario")["Fecha_dt"].count() if not dfe_week.empty else pd.Series()
            orden_personas = avances_count.sort_values(ascending=False).index.tolist()
            orden_personas = orden_personas + [p for p in SEMANEROS if p not in orden_personas]

            # --- Definir rango de fechas según cantidad de semanas ---
            hoy = dt.datetime.now(tz=STGO)
            fecha_limite = hoy - dt.timedelta(weeks=semanas_atras)

            # --- Iterar usuarios ---
            for persona in orden_personas:
                if filtro_usuario != "Todos" and persona != filtro_usuario:
                    continue

                avances = avances_count.get(persona, 0)
                temas = temas_por_persona.get(persona, [])
                liw, lev = last_in_week.get(persona), last_ever.get(persona)

                if persona in activos_set:
                    actividad_txt = f"Última actividad: {liw.strftime('%d-%m-%Y %H:%M') if pd.notna(liw) else '—'}"
                else:
                    actividad_txt = f"Sin actividad esta semana · Última histórica: {lev.strftime('%d-%m-%Y %H:%M') if pd.notna(lev) else '—'}"

                # --- Card compacta ---
                st.markdown(
                    f"""
                    <div style="display:flex;justify-content:space-between;
                                align-items:center;background:#FAFAFA;
                                border:1px solid #E7DDC6;border-radius:10px;
                                padding:6px 10px;margin:4px 0;">
                        <div>
                            <strong>{persona}</strong><br>
                            <span style="font-size:0.85rem;color:#444;">{actividad_txt}</span>
                        </div>
                        <div>
                            <span style="font-size:0.9rem;color:#2E2A27;">
                                Avances: <strong>{avances}</strong>
                            </span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if temas:
                    chips(temas)

                # --- Expander con actividades ---
                df_persona = dfe_all[
                    (dfe_all["Usuario"] == persona) &
                    (dfe_all["Fecha_dt"] >= fecha_limite)
                ].copy()

                with st.expander(f"📋 Ver detalles de {persona} (últimas {semanas_atras} semanas)"):
                    if not df_persona.empty:
                        df_persona = df_persona.sort_values("Fecha_dt", ascending=False)
                        df_resumen = df_persona[["Fecha_dt", "Tema", "Zona", "Tarea", "Porcentaje", "Observaciones"]].copy()
                        df_resumen["Fecha"] = df_resumen["Fecha_dt"].dt.strftime("%d-%m-%Y %H:%M")
                        df_resumen = df_resumen.drop(columns=["Fecha_dt"])
                        df_resumen = df_resumen[["Fecha", "Tema", "Zona", "Tarea", "Porcentaje", "Observaciones"]]

                        def highlight_estado(row):
                            if row["Porcentaje"] >= 100:
                                return ["background-color: #D4EDDA; color: #155724;"] * len(row)
                            elif row["Porcentaje"] > 0:
                                return ["background-color: #FFF3CD; color: #856404;"] * len(row)
                            else:
                                return ["background-color: #F8F9FA; color: #6C757D;"] * len(row)

                        styled_df = df_resumen.style.apply(highlight_estado, axis=1)
                        st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    else:
                        st.caption("Sin actividades registradas en este período.")

               
        # ======================
        # Render tab 0
        # ======================

        def render_tab_explorar():
            st.markdown("### Seleccionar fechas")
            lunes_hoy = init_week_state()
            ini_sel, fin_sel = week_navigation(lunes_hoy)

            rel = "Semana actual" if st.session_state.week_start == lunes_hoy else \
                "Semana pasada" if st.session_state.week_start < lunes_hoy else "Semana próxima"
                
            st.markdown(f"### **{rel}** · {etiqueta_semana(ini_sel, fin_sel)}")

            df_tareas, dfe_all, dfe_week, base = load_dataframes(ini_sel, fin_sel)
            pct_global, n_completadas, n_proceso, n_pendientes = render_kpis(base)


            with st.expander("Gráficos Globales"):
                col1, col2 = st.columns(2)
                with col1: 
                    chart_donut_global(pct_global, n_completadas, n_proceso, n_pendientes)
                with col2: 
                    chart_line_global(dfe_all, df_tareas, ini_sel, weeks_back=8) 
            
            with st.expander("Gráficos por Zona"):
                col1, col2 = st.columns(2)
                with col1: 
                    chart_descomposicion_tema(base)
                with col2: 
                    chart_tendencia(dfe_all, df_tareas, ini_sel)
                
            chart_participacion(dfe_week, dfe_all)
 
        render_tab_explorar()

    # ------------------------
    # TAB 2: Mensajes
    # ------------------------
    elif tab_label == "📝 Mensajes":
        
        def mensajes_generales():
        
            df_msgs_raw = init_mensajes_general()

            # Asegurar tipos
            if not df_msgs_raw.empty:
                df_msgs_raw["ID"] = pd.to_numeric(df_msgs_raw["ID"], errors="coerce").fillna(0).astype(int)
                df_msgs_raw["ThreadID"] = pd.to_numeric(df_msgs_raw["ThreadID"], errors="coerce").fillna(0).astype(int)
                df_msgs_raw["Fecha_dt"] = pd.to_datetime(df_msgs_raw["Fecha"], errors="coerce")
                df_msgs = df_msgs_raw.sort_values("Fecha_dt", ascending=True)
            else:
                df_msgs = df_msgs_raw.copy()

            tab1, tab2 = st.tabs (["Mensajes Internos","Dejar un mensaje"])
            
            with tab1:
                # --- Barra de búsqueda ---
                col_filtros = st.columns([3, 2])
                with col_filtros[0]:
                    filtro_txt = st.text_input("🔎 Buscar en mensajes", placeholder="Palabra clave...")
                with col_filtros[1]:
                    filtro_usuario = st.selectbox("👤 Filtrar por usuario", ["Todos"] + SEMANEROS)

                # --- Función para etiquetar semana relativa ---
                def _rel_semana_label(fecha_dt: pd.Timestamp) -> str:
                    if pd.isna(fecha_dt):
                        return ""
                    hoy = dt.datetime.now(tz=STGO).date()
                    lunes_hoy = hoy - dt.timedelta(days=hoy.weekday())
                    semana_msg = fecha_dt.date() - dt.timedelta(days=fecha_dt.weekday())
                    delta_sem = (lunes_hoy - semana_msg).days // 7
                    if delta_sem == 0:
                        return "📅 Esta semana"
                    elif delta_sem == 1:
                        return "📅 Semana pasada"
                    elif delta_sem == 2:
                        return "📅 Hace 2 semanas"
                    else:
                        return f"📅 Hace {delta_sem} semanas"

                # --- Ordenar mensajes (más nuevo arriba) ---
                df_msgs_sorted = df_msgs.sort_values("Fecha_dt", ascending=False)

                # --- Filtrar por búsqueda ---
                if filtro_txt:
                    mask_txt = df_msgs_sorted["Mensaje"].str.contains(filtro_txt, case=False, na=False)
                    df_msgs_sorted = df_msgs_sorted[mask_txt]
                if filtro_usuario != "Todos":
                    df_msgs_sorted = df_msgs_sorted[df_msgs_sorted["Usuario"] == filtro_usuario]

                if df_msgs_sorted.empty:
                    st.info("No se encontraron mensajes con los filtros aplicados.")
                else:
                    # Agrupar por hilos (ya ordenados por fecha más nueva primero)
                    for thread_id, grupo in df_msgs_sorted.groupby("ThreadID", sort=False):
                        grupo = grupo.sort_values("Fecha_dt")
                        principal = grupo.iloc[0]

                        # Etiqueta de semana
                        sem_label = _rel_semana_label(principal["Fecha_dt"])

                        # Mensaje principal con botón de respuesta al lado
                        col_msg, col_btn = st.columns([8, 2])
                        with col_msg:
                            st.markdown(
                                f"""
                                <div style="background:#E6F4EA;border:1px solid #C6E0C3;
                                            border-radius:10px;padding:10px 12px;margin-bottom:6px;">
                                    <b>{principal['Usuario']}</b> · 🗓️ {principal['Fecha_dt'].strftime("%d-%m-%Y %H:%M") if pd.notna(principal['Fecha_dt']) else ""} 
                                    · {sem_label}
                                    <div style="margin-top:3px;color:#2E2A27;">{principal['Mensaje']}</div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
                        with col_btn:
                            if st.button("💬 Responder", key=f"btn_resp_{thread_id}"):
                                st.session_state[f"show_form_{thread_id}"] = True

                        # 🔽 Mostrar respuestas ya registradas
                        for _, msg in grupo.iloc[1:].iterrows():
                            sem_label = _rel_semana_label(msg["Fecha_dt"])
                            st.markdown(
                                f"""
                                <div style="margin-left:20px;padding:6px 10px;margin-bottom:4px;
                                            border-left:2px solid #ccc;">
                                    <b>{msg['Usuario']}</b>: {msg['Mensaje']}<br>
                                    <span style="font-size:0.8rem;color:#777;">
                                    {msg['Fecha_dt'].strftime("%d-%m-%Y %H:%M") if pd.notna(msg['Fecha_dt']) else ""} · {sem_label}
                                    </span>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )

                        # Formulario de respuesta
                        
                        if st.session_state.get(f"show_form_{thread_id}", False):
                            with st.form(f"form_respuesta_{thread_id}", clear_on_submit=True):
                                nombre_resp = st.selectbox(
                                    "Tu nombre:", [""] + SEMANEROS,
                                    index=([""] + SEMANEROS).index(st.session_state.get("nombre_sel",""))
                                    if st.session_state.get("nombre_sel","") in SEMANEROS else 0,
                                    key=f"resp_nombre_{thread_id}"
                                )
                                respuesta = st.text_area(
                                    "Escribe tu respuesta:",
                                    placeholder="Agrega un comentario...",
                                    key=f"resp_text_{thread_id}"
                                )
                                enviar_resp = st.form_submit_button("Responder")

                            if enviar_resp:
                                if not nombre_resp:
                                    st.error("Debes seleccionar tu nombre.")
                                elif not respuesta.strip():
                                    st.error("La respuesta no puede estar vacía.")
                                else:
                                    nuevo_id = int(df_msgs["ID"].max()) + 1 if not df_msgs.empty else 1
                                    ahora = dt.datetime.now(tz=STGO)
                                    append_row("mensajes_general", [
                                        nuevo_id,
                                        thread_id,  # mismo hilo
                                        ahora.strftime("%Y-%m-%d %H:%M"),
                                        nombre_resp,
                                        respuesta.strip()
                                    ])
                                    st.cache_data.clear()
                                    df_msgs = init_mensajes_general()
                                    st.success("✅ Respuesta enviada")
                                    st.session_state[f"show_form_{thread_id}"] = False
                                    st.rerun()

           
           
           
           
            
            with tab2:
                    # --- Crear mensaje principal ---
                    
                    st.markdown("##### Deja un mensaje y crea un hilo nuevo")
                    with st.form("form_mensaje_principal", clear_on_submit=True):
                        nombre_default = st.session_state.get("nombre_sel", "")
                        nombre_idx = ([""] + SEMANEROS).index(nombre_default) if nombre_default in SEMANEROS else 0
                        nombre = st.selectbox("Tu nombre:", [""] + SEMANEROS, index=nombre_idx, key="msg_nombre_principal")

                        mensaje = st.text_area("Escribe un nuevo mensaje:", placeholder="Ej: No podré hacer la tarea del patio esta semana...")
                        enviar = st.form_submit_button("Publicar mensaje")

                    if enviar:
                        if not nombre:
                            st.error("Debes seleccionar tu nombre.")
                        elif not mensaje.strip():
                            st.error("El mensaje no puede estar vacío.")
                        else:
                            nuevo_id = int(df_msgs["ID"].max()) + 1 if not df_msgs.empty else 1
                            ahora = dt.datetime.now(tz=STGO)
                            append_row("mensajes_general", [
                                nuevo_id,
                                nuevo_id,  # ThreadID = ID propio
                                ahora.strftime("%Y-%m-%d %H:%M"),
                                nombre,
                                mensaje.strip()
                            ])
                            st.cache_data.clear()
                            df_msgs = init_mensajes_general()  # refrescar
                            st.success("✅ Mensaje publicado")
                            st.rerun()
        mensajes_generales()



       
        
        def mensajes_tareas():
            st.markdown("---")
            st.markdown("##### Observaciones de tareas realizadas")
            # Usamos 'ahora' y 'hoy' definidos al inicio del render
            lunes_hoy = hoy - dt.timedelta(days=hoy.weekday())
            default_start = lunes_hoy - dt.timedelta(days=14)  # 2 semanas antes
            default_end   = lunes_hoy + dt.timedelta(days=6)   # fin semana actual

            # --- Filtros (Tema + Fechas + Estado)
            cA, cB, cC = st.columns([2, 2, 2])
            with cA:
                temas_disp = []
                if not dfe_all.empty:
                    temas_disp = sorted([
                        t for t in dfe_all["Tema"].dropna().unique().tolist()
                        if str(t).strip() != ""
                    ])
                f_temas = st.multiselect("Filtrar por tema", temas_disp, default=[])
            with cB:
                f_rango = st.date_input(
                    "Rango de fechas",
                    value=(default_start, default_end)
                )

                # Validar que se devuelvan 2 fechas
                if isinstance(f_rango, tuple) and len(f_rango) == 2:
                    f_ini = dt.datetime.combine(f_rango[0], dt.time.min).replace(tzinfo=STGO)
                    f_fin = dt.datetime.combine(f_rango[1], dt.time.max).replace(tzinfo=STGO)
                else:
                    st.warning("⚠️ Por favor selecciona un **rango con dos fechas** (inicio y fin).")
                    f_ini = None
                    f_fin = None
            with cC:
                f_estado = st.selectbox("Estado", ["Todos", "Completadas (100%)", "En proceso (<100%)"])

            if dfe_all.empty:
                st.info("No hay observaciones registradas.")
            else:
                # --- Observaciones filtradas
                
                obs_all = dfe_all.copy()
                obs_all = obs_all[(obs_all["Fecha_dt"] >= f_ini) & (obs_all["Fecha_dt"] <= f_fin)]
                if f_temas:
                    obs_all = obs_all[obs_all["Tema"].isin(f_temas)]

                # --- Semana (lunes) de cada fila
                obs_all["week_start"] = (
                    obs_all["Fecha_dt"].dt.date - pd.to_timedelta(obs_all["Fecha_dt"].dt.weekday, unit="D")
                )

                # --- Acumulado semanal por tarea
                acc = dfe_all.copy()
                acc["week_start"] = (
                    acc["Fecha_dt"].dt.date - pd.to_timedelta(acc["Fecha_dt"].dt.weekday, unit="D")
                )
                acc_grp = (
                    acc.groupby(["week_start", "Tema", "Zona", "Tarea"], dropna=False)["Porcentaje"]
                    .sum().clip(upper=100).rename("acum_semana")
                    .reset_index()
                )
                obs_all = obs_all.merge(acc_grp, on=["week_start", "Tema", "Zona", "Tarea"], how="left")
                obs_all["acum_semana"] = pd.to_numeric(obs_all["acum_semana"], errors="coerce").fillna(0).astype(int)

                # --- Filtrar por estado
                if f_estado == "Completadas (100%)":
                    obs_all = obs_all[obs_all["acum_semana"] >= 100]
                elif f_estado == "En proceso (<100%)":
                    obs_all = obs_all[obs_all["acum_semana"] < 100]

                # --- Limpiar observaciones vacías
                if "Observaciones" not in obs_all.columns:
                    obs_all["Observaciones"] = ""
                obs_all["__obs_txt__"] = (
                    obs_all["Observaciones"].astype(str)
                    .str.replace(r"\s+", " ", regex=True)
                    .str.strip()
                )
                placeholders = {"", "nan", "none", "null", "na", "-", "—"}
                obs_all = obs_all[~obs_all["__obs_txt__"].str.lower().isin(placeholders)].copy()
                obs_all.drop(columns="__obs_txt__", inplace=True)

                # --- Orden: más nuevo → más antiguo
                obs_all = obs_all.sort_values("Fecha_dt", ascending=False)

                if obs_all.empty:
                    st.info("No hay observaciones que cumplan los filtros.")
                else:
                    # Helpers
                    def _rel_label(week_start_date: dt.date) -> str:
                        if week_start_date == lunes_hoy: return "Esta semana"
                        if week_start_date == (lunes_hoy - dt.timedelta(days=7)): return "Semana pasada"
                        if week_start_date == (lunes_hoy - dt.timedelta(days=14)): return "Hace 2 semanas"
                        ws = dt.datetime.combine(week_start_date, dt.time.min).replace(tzinfo=STGO)
                        return f"Sem. ISO {ws.strftime('%G')}-W{ws.strftime('%V')}"

                    def _hace_texto(fecha_dt: pd.Timestamp) -> str:
                        if pd.isna(fecha_dt): return ""
                        delta = ahora - fecha_dt
                        if delta.days >= 1:
                            return f"hace {delta.days} día{'s' if delta.days != 1 else ''}"
                        horas = int(delta.total_seconds() // 3600)
                        if horas >= 1:
                            return f"hace {horas} h"
                        mins = int((delta.total_seconds() % 3600) // 60)
                        return f"hace {mins} min"

                    def _obs_card_enh(r):
                        fecha_s = r["Fecha_dt"].strftime("%d-%m-%Y %H:%M") if pd.notna(r["Fecha_dt"]) else "—"
                        hace_s = _hace_texto(r["Fecha_dt"])
                        is_current_week = (r["week_start"] == lunes_hoy)
                        is_done = int(r["acum_semana"]) >= 100
                        icon = "✅" if is_done else "⏳"
                        _VERDE = VERDE_COMPLETADAS
                        _TERRA = TERRACOTA_PROCESO
                        bg = "#F0FAF3" if is_current_week else "#FFFDF6"
                        border = _VERDE if is_done else _TERRA

                        st.markdown(
                            f"""
                            <div style="background:{bg}; border:1px solid {border};
                                        border-radius:12px; padding:10px 12px; margin-bottom:8px;">
                                <div style="font-size:0.85rem; color:#5a5a5a; margin-bottom:6px;">
                                    <span style="border:1px solid #cfcfcf;border-radius:999px;
                                                padding:2px 8px;margin-right:6px;">{r.get('Tema','—')}</span>
                                    <span style="border:1px solid #cfcfcf;border-radius:999px;
                                                padding:2px 8px;margin-right:6px;">{r.get('Zona','—')}</span>
                                    <span style="border:1px solid #cfcfcf;border-radius:999px;
                                                padding:2px 8px;margin-right:6px;">{r.get('Tarea','—')}</span>
                                    <span style="border:1px solid #cfcfcf;border-radius:999px;
                                                padding:2px 8px;margin-right:6px;">{icon} acum: {int(r.get('acum_semana') or 0)}%</span>
                                    <span style="border:1px solid #cfcfcf;border-radius:999px;
                                                padding:2px 8px;margin-right:6px;">🗓️ {fecha_s} · {hace_s}</span>
                                    <span style="border:1px solid #cfcfcf;border-radius:999px;
                                                padding:2px 8px;margin-right:6px;"> {r.get('Usuario','—')}</span>
                                </div>
                                <div style="white-space:pre-wrap; line-height:1; color:#2E2A27;">
                                    {(r.get('Observaciones') or '').replace('<','&lt;').replace('>','&gt;')}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )

                    # Agrupar por semana y paginar
                    obs_all["week_start"] = pd.to_datetime(obs_all["week_start"])
                    grupos = []
                    for ws, g in obs_all.groupby("week_start"):
                        grupos.append((ws.date(), g.sort_values("Fecha_dt", ascending=False)))
                    grupos.sort(key=lambda x: x[0], reverse=True)

                    if "obs_show_count" not in st.session_state:
                        st.session_state["obs_show_count"] = 15

                    mostradas = 0
                    to_show = st.session_state["obs_show_count"]

                    for ws_date, g in grupos:
                        st.markdown(f"**{_rel_label(ws_date)}**")
                        for _, r in g.iterrows():
                            if mostradas >= to_show:
                                break
                            _obs_card_enh(r)
                            mostradas += 1
                        if mostradas >= to_show:
                            break

                    total_tarjetas = len(obs_all)
                    if mostradas < total_tarjetas:
                        if st.button(f"Ver más ({total_tarjetas - mostradas} restantes)"):
                            st.session_state["obs_show_count"] += 20
                            st.rerun()
        mensajes_tareas()


    # ------------------------
    # TAB 3: Registrar avance
    # ------------------------
    elif tab_label == "✅ Registrar avance":
        st.markdown("##### Registrar avance")

        # =========================
        # 1. Preparar dataframes
        # =========================
        def preparar_data():
            df_tareas = cargar_datos("tareas_semaneros")
            try:
                dfe_raw = cargar_datos("estado_tareas")
            except Exception:
                dfe_raw = pd.DataFrame(columns=[
                    "Fecha","Usuario","Tema","Zona","Tarea",
                    "Completada","Porcentaje","Observaciones"
                ])
            dfe_all = normalizar_estado(dfe_raw)
            dfe_all = dfe_all.copy()
            if "Observaciones" not in dfe_all.columns:
                dfe_all["Observaciones"] = ""
            else:
                dfe_all["Observaciones"] = dfe_all["Observaciones"].astype(str)
            dfe_all["Porcentaje"] = pd.to_numeric(
                dfe_all.get("Porcentaje", 0), errors="coerce"
            ).fillna(0).astype(int)
            return df_tareas, dfe_all

        df_tareas, dfe_all = preparar_data()

        # Precalcular estado semanal
        in_week = (dfe_all["Fecha_dt"] >= ini_sel) & (dfe_all["Fecha_dt"] <= fin_sel)
        dfe_week = dfe_all[in_week].copy()
        agg_week = acumulado_por_tarea_semana(dfe_week)
        base = merge_catalogo_estado(df_tareas, agg_week)

        # =========================
        # 2. Selección de usuario
        # =========================
        def seleccionar_usuario():
            nombre_default = st.session_state.get("nombre_sel", "")
            nombre_idx = ([""] + SEMANEROS).index(nombre_default) if nombre_default in SEMANEROS else 0
            nombre = st.selectbox(
                "Selecciona tu nombre:",
                [""] + SEMANEROS,
                index=nombre_idx,
                key="reg_nombre"
            )
            if nombre:
                st.session_state["nombre_sel"] = nombre
            return nombre

        nombre = seleccionar_usuario()

        if not nombre:
            st.caption("Selecciona tu nombre para ver tareas disponibles.")
        else:
            disponibles = base[base["acumulado"] < 100].copy()
            if disponibles.empty:
                st.success("🎉 Todas las tareas están completadas.")
            else:
                dfe_user_all = dfe_all[dfe_all["Usuario"] == nombre].copy()
                disponibles = disponibles.sort_values(["Tema", "Zona", "Tarea"]).reset_index(drop=True)

                # =========================
                # 🔍 2.1 Filtro por tema
                # =========================
                temas_disp = sorted(disponibles["Tema"].dropna().unique().tolist())
                f_temas = st.multiselect(
                    "Filtrar por tema (opcional)",
                    temas_disp,
                    default=[]
                )
                if f_temas:
                    disponibles = disponibles[disponibles["Tema"].isin(f_temas)].copy()

                # =========================
                # 3. Render de tareas
                # =========================
                def render_tarea(row, idx, tema):
                    tarea_key = f"{tema}|{row['Zona']}|{row['Tarea']}|{idx}"
                    restante = int(100 - int(row["acumulado"]))

                    # Avance previo usuario
                    mask_prev = (
                        (dfe_user_all["Tema"] == tema) &
                        (dfe_user_all["Zona"] == row["Zona"]) &
                        (dfe_user_all["Tarea"] == row["Tarea"])
                    )
                    porc_prev_user = int(dfe_user_all.loc[mask_prev, "Porcentaje"].sum()) if mask_prev.any() else 0

                    # Acumulado + días sin hacer
                    df_task = dfe_all[
                        (dfe_all["Tema"] == tema) &
                        (dfe_all["Zona"] == row["Zona"]) &
                        (dfe_all["Tarea"] == row["Tarea"])
                    ].copy()
                    acumulado, ultima, dias_sin_hacer = calcular_acumulado_semana_a_semana(df_task, ini_sel, hoy)

                    # =========================
                    # Línea de preview por tarea
                    # =========================
                    if ultima is not None:
                        fecha_raw = ultima.get("Fecha")
                        fdt = pd.to_datetime(fecha_raw, errors="coerce")
                        if pd.notna(fdt):
                            try:
                                fdt = fdt.tz_localize(STGO, nonexistent="shift_forward", ambiguous="NaT") if fdt.tzinfo is None else fdt.tz_convert(STGO)
                            except Exception:
                                pass
                            dias_sem = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
                            dow = fdt.weekday()
                            fecha_txt = f"{dias_sem[dow]} {fdt.strftime('%d-%m')}"
                        else:
                            fecha_txt = "—"

                        usuario = ultima.get("Usuario", "—")
                        obs = (ultima.get("Observaciones") or "").strip()

                        if dias_sin_hacer == "Nunca":
                            preview_line = f"⚠️ No se ha realizado nunca."
                        elif dias_sin_hacer == "Hoy":
                            preview_line = f"⏱ Última vez: {fecha_txt} (Hoy) por {usuario}. {obs}"
                        else:
                            preview_line = f"⏱ Última vez: {fecha_txt} ({dias_sin_hacer}) por {usuario}. {obs}"
                    else:
                        preview_line = "⚠️ No se ha realizado nunca."

                    # Checkbox principal
                    label = f"**{row['Zona']}**: {row['Tarea']} — Pendiente {restante}%"
                    if 0 < porc_prev_user < 100:
                        label += f" (Avanzado: +{porc_prev_user}%)"

                    col1, col2 = st.columns(2)
                    with col1:
                        marcado = st.checkbox(label, key=f"chk_{tarea_key}")
                    with col2:
                        st.caption(preview_line)

                    if marcado:
                        st.info(preview_line)
                        render_form(row, tarea_key, tema, restante, preview_line)

                def render_form(row, tarea_key, tema, restante, preview_line):
                    notas_cur, notas_hist = _notes_for_form(
                        dfe_all, tema, row["Zona"], row["Tarea"], ini_sel, fin_sel,
                        n_actuales=3, n_hist=10
                    )
                    with st.form(key=f"form_{tarea_key}"):
                        fecha_registro = st.date_input(
                            "Fecha del avance",
                            value=hoy,
                            max_value=hoy,
                            key=f"fecha_{tarea_key}"
                        )

                        # Notas recientes
                        if not notas_cur.empty:
                            st.markdown("**Notas recientes de esta tarea (semana actual):**")
                            for _, rr in notas_cur.iterrows():
                                fecha_s = rr["Fecha_dt"].strftime("%d-%m %H:%M") if pd.notna(rr["Fecha_dt"]) else "—"
                                delta = int(pd.to_numeric(rr.get("Porcentaje", 0), errors="coerce") or 0)
                                acum_tr = int(pd.to_numeric(rr.get("acum_tr", 0), errors="coerce") or 0)
                                st.markdown(
                                    f"-  {rr.get('Usuario','—')} · 🕒 {fecha_s} · +{delta}% · *acum tras registro: {acum_tr}%*\n\n"
                                    f"  {rr.get('Observaciones','')}"
                                )
                        else:
                            st.caption("Sin notas en la semana actual.")

                        if not notas_hist.empty:
                            with st.expander("Ver historial de notas (anteriores)"):
                                for _, rh in notas_hist.iterrows():
                                    fecha_h = rh["Fecha_dt"].strftime("%d-%m %H:%M") if pd.notna(rh["Fecha_dt"]) else "—"
                                    delta_h = int(pd.to_numeric(rh.get("Porcentaje", 0), errors="coerce") or 0)
                                    st.markdown(
                                        f"-  {rh.get('Usuario','—')} · 🕒 {fecha_h} · +{delta_h}%\n\n"
                                        f"  {rh.get('Observaciones','')}"
                                    )

                        st.caption(f"Pendiente esta semana: **{restante}%** · Avanzado actual: **{int(row['acumulado'])}%**")
                        porc = st.slider(
                            "¿Cuánto se completó ahora?",
                            min_value=1,
                            max_value=restante if restante > 0 else 1,
                            value=restante if restante > 0 else 1,
                            step=1,
                            key=f"porc_{tarea_key}"
                        )
                        obs_txt = st.text_area(
                            "Observaciones (obligatorio si % < 100)",
                            placeholder="Describe brevemente el avance, materiales usados, bloqueos, etc.",
                            key=f"obs_{tarea_key}"
                        )
                        enviar = st.form_submit_button("Registrar")

                    if enviar:
                        procesar_registro(row, tarea_key, tema, restante, porc, obs_txt, fecha_registro)

                def procesar_registro(row, tarea_key, tema, restante, porc, obs_txt, fecha_registro):
                    if porc <= 0:
                        st.error("El porcentaje debe ser mayor que 0%.")
                        return
                    if restante <= 0:
                        st.error("Esta tarea ya fue completada.")
                        return
                    if porc > restante:
                        st.error(f"Solo queda {restante}% disponible.")
                        return
                    if porc < 100 and len((obs_txt or "").strip()) < 10:
                        st.error("Para avances < 100% debes escribir observaciones (mín. 10 caracteres).")
                        return

                    estado = "Sí" if (porc == restante) else "En proceso"

                    fecha_sel = pd.to_datetime(fecha_registro).strftime("%Y-%m-%d")
                    hora_sel = ahora.strftime("%H:%M")

                    append_row("estado_tareas", [
                        f"{fecha_sel} {hora_sel}",
                        nombre,
                        tema,
                        row["Zona"],
                        row["Tarea"],
                        estado,
                        porc,
                        (obs_txt or "").strip()
                    ])

                    try:
                        st.cache_data.clear()
                    except Exception:
                        pass

                    st.success(f"✅ Registrado: {row['Zona']} · {row['Tarea']} (+{porc}%)")
                    st.session_state["tab_idx"] = TAB_LABELS.index("✅ Registrar avance")
                    st.session_state["nombre_sel"] = nombre
                    st.rerun()

                # =========================
                # Render por tema/tarea
                # =========================
                tema_grupos = disponibles.groupby("Tema", dropna=False)
                for tema, df_tema in tema_grupos:
                    st.markdown(f"#### {tema}")
                    for idx, row in df_tema.reset_index(drop=True).iterrows():
                        render_tarea(row, idx, tema)
