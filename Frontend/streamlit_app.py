"""
Turnistica - Sistema di Gestione Turni Infermieristici
=====================================================
"""

import streamlit as st

# Configurazione della pagina
st.set_page_config(
    page_title="HealthFactor",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    st.title("🏥 HealthFactor - Sistema di Gestione Turni")
    
    st.markdown("""
    ### Benvenuto nel Sistema di Gestione Turni Infermieristici
    
    Seleziona una delle pagine dal menu laterale per iniziare:
    
    - **🔄 Shift Generator**: Genera automaticamente i turni mensili
    - **✏️ Shift Changer**: Modifica turni esistenti (in sviluppo)
    - **📅 Shift**: Visualizza e analizza i turni (in sviluppo)
    """)
    
    st.info("👈 Utilizza il menu laterale per navigare tra le pagine")


if __name__ == "__main__":
    main()