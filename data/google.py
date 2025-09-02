import pandas as pd
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SHEET_KEY = "1C8njkp0RQMdXnxuJvPvfK_pNZHQSi7q7dUPeUg-2624"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def _get_client():
    creds = Credentials.from_service_account_info(st.secrets["gspread"], scopes=SCOPES)
    return gspread.authorize(creds)

@st.cache_data(ttl=300)
def cargar_datos(sheet_name: str) -> pd.DataFrame:
    sh = _get_client().open_by_key(SHEET_KEY)
    ws = sh.worksheet(sheet_name)
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    df.columns = [c.strip() for c in df.columns]
    return df

def append_row(sheet_name: str, values: list):
    sh = _get_client().open_by_key(SHEET_KEY)
    ws = sh.worksheet(sheet_name)
    ws.append_row(values)