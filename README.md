# Acuerdos AUCCA — App modular (Streamlit)

## Estructura
```
acuerdos_app/
├─ acuerdos.py
├─ secciones/
│  ├─ links_claves.py
│  ├─ acuerdos_internos.py
│  ├─ acuerdos_externos.py
│  └─ checklist.py
├─ ui/estilos.py
├─ data/google.py
├─ utils/busqueda.py
├─ images/
│  ├─ logo_aucca.png
│  └─ queltehue.png
└─ .streamlit/
   ├─ secrets.example.toml
   └─ secrets.toml (no versionar)
```

## Configuración
1. Crea y activa tu entorno (recomendado):
   ```bash
   python -m venv venv && source venv/bin/activate  # Linux/Mac
   # o en Windows (PowerShell):
   # python -m venv venv; venv\Scripts\Activate.ps1
   ```

2. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```

3. Configura credenciales de Google en `.streamlit/secrets.toml` (NO subas este archivo a Git):
   - Usa el ejemplo en `.streamlit/secrets.example.toml` y pega tu JSON de service account bajo `[gspread]`.

4. Ejecuta la app:
   ```bash
   streamlit run acuerdos.py
   ```

## Notas
- El `SHEET_KEY` está en `data/google.py`. Si cambia, actualízalo allí.
- Puedes crear más temas/estilos en `ui/` y cambiar el import en `acuerdos.py`.
- Cada sección expone `render()` para mantener el router súper simple.