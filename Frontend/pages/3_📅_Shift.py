"""
Shift Page - Visualizzazione Storico Turni
==========================================
"""

import streamlit as st
import os
import sys
import pandas as pd
import calendar
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shift_history import (
    init_shift_history,
    get_shift_list,
    get_shift,
    get_shift_stats,
    delete_shift
)

# Mappatura giorni della settimana in italiano
ITALIAN_WEEKDAYS = {
    0: "Lun",
    1: "Mar",
    2: "Mer",
    3: "Gio",
    4: "Ven",
    5: "Sab",
    6: "Dom",
}


def render_shift_sidebar():
    """Renderizza la sidebar con filtri e navigazione"""
    st.sidebar.title("🔍 Filtri Turni")
    
    # Statistiche generali
    stats = get_shift_stats()
    st.sidebar.metric("Turni Salvati", stats["total_shifts"])
    
    if stats["total_shifts"] > 0:
        st.sidebar.metric("Ultimo Turno", stats["latest_shift"])
        st.sidebar.metric("Infermieri Totali", stats["total_nurses"])
    
    st.sidebar.markdown("---")
    
    # Lista dei turni disponibili
    shifts = get_shift_list()
    
    if not shifts:
        st.sidebar.info("Nessun turno salvato")
        return None
    
    # Filtro per anno
    available_years = sorted(list(set(shift["year"] for shift in shifts)), reverse=True)
    selected_year = st.sidebar.selectbox(
        "Filtra per Anno",
        ["Tutti"] + available_years,
        key="year_filter"
    )
    
    # Filtra turni per anno se selezionato
    if selected_year != "Tutti":
        filtered_shifts = [s for s in shifts if s["year"] == selected_year]
    else:
        filtered_shifts = shifts
    
    if not filtered_shifts:
        st.sidebar.info("Nessun turno per l'anno selezionato")
        return None
    
    # Selezione del turno specifico
    shift_options = []
    for shift in filtered_shifts:
        shift_options.append({
            "label": f"{shift['period_desc']} ({shift['created_at'][:10]})",
            "key": shift["key"],
            "year": shift["year"],
            "month": shift["month"]
        })
    
    if shift_options:
        st.sidebar.markdown("### Seleziona Turno")
        selected_shift = st.sidebar.selectbox(
            "Turno da visualizzare",
            shift_options,
            format_func=lambda x: x["label"],
            key="shift_selector"
        )
        return selected_shift
    
    return None


def render_shift_data(shift_data, period_desc):
    """Renderizza i dati del turno selezionato"""
    st.header(f"📅 Turno: {period_desc}")
    
    # Informazioni generali
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Data Creazione", shift_data["created_at"])
    with col2:
        st.metric("Infermieri", len(shift_data["nurses"]))
    with col3:
        constraints_count = len(shift_data["constraints_used"]["hard"]) + len(shift_data["constraints_used"]["soft"])
        st.metric("Vincoli Utilizzati", constraints_count)
    
    # Statistiche del turno
    st.subheader("📊 Statistiche Turno")
    col1, col2, col3 = st.columns(3)
    
    stats = shift_data["stats"]
    with col1:
        st.metric("Ore Totali Lavorate", f"{stats['total_worked']}h")
    with col2:
        st.metric("Ore Totali Contratto", f"{int(stats['total_contract'])}h")
    with col3:
        st.metric("Differenza Totale", f"{stats['total_diff']:+.0f}h",
                  delta_color="inverse" if stats['total_diff'] < 0 else "normal")
    
    # Matrice turni
    st.subheader("🗓️ Matrice Turni")
    
    # Ricostruisce il DataFrame come nel generatore
    shift_matrix = shift_data["shift_matrix"]
    
    # Determina le colonne (giorni del mese)
    # Assumiamo che period_desc sia in formato "Mese YYYY"
    try:
        month_name, year_str = period_desc.split()
        year = int(year_str)
        month = list(calendar.month_name).index(month_name)
        
        # Calcola le date
        start_date = datetime(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        
        columns = []
        weekend_columns = set()
        
        for day in range(1, last_day + 1):
            current_date = datetime(year, month, day)
            day_name = ITALIAN_WEEKDAYS[current_date.weekday()]
            col_name = f"{day_name} {day:02d}"
            columns.append(col_name)
            
            # Marca weekend
            if current_date.weekday() in [5, 6]:
                weekend_columns.add(col_name)
        
        # Crea DataFrame
        data_dict = {}
        
        # Colonne turni
        for col, day_shifts in zip(columns, zip(*shift_matrix)):
            data_dict[col] = list(day_shifts)
        
        df = pd.DataFrame(data_dict, index=[nurse["name"] for nurse in shift_data["nurses"]])
        
        # Styling per weekend
        def highlight_weekends(x):
            styles = pd.DataFrame('', index=x.index, columns=x.columns)
            for col in x.columns:
                if col in weekend_columns:
                    styles[col] = 'background-color: #1565c0; color: white'
            return styles
        
        styled_df = df.style.apply(highlight_weekends, axis=None)
        st.dataframe(styled_df, use_container_width=True)
        
        # Legenda
        st.caption(
            "**Legenda**: M=Mattino, P=Pomeriggio, N=Notte, S=Smonto, R=Riposo | "
            "🏖️ Weekend evidenziati in blu scuro")
        
    except Exception as e:
        st.error(f"Errore nella visualizzazione della matrice: {e}")
        st.dataframe(pd.DataFrame(shift_matrix))


def main():
    st.title("📅 Storico Turni")
    
    # Inizializza lo storico
    init_shift_history()
    
    # CSS personalizzato
    st.markdown("""
    <style>
    .main .block-container {
        max-width: 100% !important;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
    
    .stDataFrame {
        width: 100% !important;
    }
    
    .stDataFrame > div {
        width: 100% !important;
        overflow-x: auto;
    }
    
    .stDataFrame td, .stDataFrame th {
        font-size: 12px !important;
        white-space: nowrap;
        text-align: center;
        padding: 4px 6px !important;
        min-width: 45px;
        max-width: 60px;
    }
    
    .stDataFrame table {
        table-layout: auto !important;
        width: 100% !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Sidebar con filtri
    selected_shift = render_shift_sidebar()
    
    if selected_shift is None:
        st.info("👆 Seleziona un turno dalla barra laterale per visualizzarlo")
        
        # Mostra statistiche generali se ci sono turni
        stats = get_shift_stats()
        if stats["total_shifts"] > 0:
            st.markdown("### 📊 Statistiche Generali")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Turni Totali", stats["total_shifts"])
            with col2:
                st.metric("Ultimo Turno", stats["latest_shift"])
            with col3:
                st.metric("Infermieri Unici", stats["total_nurses"])
        else:
            st.markdown("""
            ### 🚀 Come iniziare:
            
            1. Vai alla pagina **🔄 Shift Generator**
            2. Configura i parametri e vincoli
            3. Genera un turno per un mese
            4. Torna qui per visualizzare lo storico
            """)
    
    else:
        # Recupera e mostra i dati del turno selezionato
        shift_data = get_shift(selected_shift["year"], selected_shift["month"])
        
        if shift_data:
            render_shift_data(shift_data, shift_data["period_desc"])
        else:
            st.error("Impossibile caricare i dati del turno selezionato")


if __name__ == "__main__":
    main()