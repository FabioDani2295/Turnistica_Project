"""
Shift Changer Page
==================
"""

import streamlit as st
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def main():
    st.title("🔄 Modifica Turni")
    
    # CSS personalizzato per allargare la visualizzazione
    st.markdown("""
    <style>
    .main .block-container {
        max-width: 100% !important;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
    </style>
    """, unsafe_allow_html=True)

    # Sidebar: tempo max risoluzione
    max_time = st.sidebar.slider("Tempo max risoluzione (secondi)", 30, 300, 120)

    # Contenuto principale vuoto per ora
    st.info("🚧 Funzionalità in sviluppo...")
    
    st.markdown("""
    Questa pagina permetterà di:
    - Modificare turni esistenti
    - Applicare cambiamenti manuali
    - Ricalcolare automaticamente i turni
    """)


if __name__ == "__main__":
    main()