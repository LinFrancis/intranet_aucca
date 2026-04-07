import streamlit as st

def render():
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Foto grupal centrada
    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        try:
            st.image("data/foto_grupal.jpg", use_container_width=True, channels="RGB", output_format="JPEG")
            st.markdown(
                "<p style='text-align: center; color: #7B4F9E; font-size: 1.05rem; font-weight: 600; margin-top: 8px; letter-spacing: 0.02em;'>"
                "Aucca Familia 15 noviembre 2025"
                "</p>", 
                unsafe_allow_html=True
            )
        except Exception as e:
            st.warning("No se pudo cargar la foto grupal.")
            
    st.markdown("---")
    
    st.markdown("""
    #### 📌 ¿Qué puedes hacer aquí?
    - **Semanerx**: Gestionar el checklist y responsabilidades semanales.
    - **Finanzas**: Administrar los ingresos, gastos y traspasos entre auccanes.
    - **Links Claves**: Accesos rápidos a recursos importantes.
    - **Acuerdos**: Repositorio de nuestros acuerdos internos de convivencia y comunicación externa.
    
    ---
    *Caminamos una ruta de aprendizajes para fortalecer la energía que nos une en el convivir y nos inspira en la creación de un día a día mejor* 🌱
    """)
