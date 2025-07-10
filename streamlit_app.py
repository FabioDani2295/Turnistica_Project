"""
streamlit_app.py - AGGIORNATO PER WEEKEND DETECTION
===================================================
"""

import streamlit as st
import os
import calendar
from datetime import datetime, timedelta
import pandas as pd

from parser.nurse_loader import load_nurses
from parser.hard_constraint_loader import load_hard_constraints
from parser.soft_constraint_loader import load_soft_constraints

from model.scheduler import Scheduler
from utils.schedule_formatter import ScheduleFormatter
from ortools.sat.python import cp_model

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


def main():
    st.title("🏥 Visualizzazione Turni Infermieristici - Vista Mensile")
    
    # CSS personalizzato per allargare la visualizzazione e mostrare più colonne
    st.markdown("""
    <style>
    .main .block-container {
        max-width: 100% !important;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
    
    /* Allarga la tabella dataframe per mostrare più colonne */
    .stDataFrame {
        width: 100% !important;
    }
    
    .stDataFrame > div {
        width: 100% !important;
        overflow-x: auto;
    }
    
    /* Ottimizza le celle per mostrare più colonne */
    .stDataFrame td, .stDataFrame th {
        font-size: 12px !important;
        white-space: nowrap;
        text-align: center;
        padding: 4px 6px !important;
        min-width: 45px;
        max-width: 60px;
    }
    
    /* Colonne più strette per mostrarne di più */
    .stDataFrame table {
        table-layout: auto !important;
        width: 100% !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Sidebar: percorso cartella dati
    default_folder = os.path.join(os.getcwd(), "data")
    data_folder = st.sidebar.text_input("Cartella dati", default_folder)

    # Sidebar: selezione mese e anno
    months = list(calendar.month_name)[1:]
    now = datetime.now()
    month_name = st.sidebar.selectbox("Mese", months, index=now.month - 1)
    year = st.sidebar.number_input("Anno", min_value=2000, max_value=2100, value=now.year)
    month = months.index(month_name) + 1

    # Sidebar: tempo max risoluzione
    max_time = st.sidebar.slider("Tempo max risoluzione (secondi)", 30, 300, 120)

    # Intervallo date per il mese selezionato
    start_date = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, last_day)
    total_days = (end_date - start_date).days + 1
    date_labels = [start_date + timedelta(days=i) for i in range(total_days)]
    period_desc = f"{month_name} {year}"

    # NUOVO: Calcola start_weekday
    start_weekday = start_date.weekday()  # 0=lunedì, 6=domenica

    # Info periodo nella sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**📅 Periodo selezionato:**")
    st.sidebar.markdown(f"{period_desc} ({total_days} giorni)")
    st.sidebar.markdown(f"Inizio: {ITALIAN_WEEKDAYS[start_weekday]} {start_date.strftime('%d/%m')}")

    # Mostra weekend identificati
    temp_scheduler = Scheduler([], [], [], total_days, start_weekday=start_weekday)
    weekends = temp_scheduler.get_weekend_days()
    if weekends:
        weekend_str = ", ".join([f"{s+1}-{d+1}" for s, d in weekends])
        st.sidebar.markdown(f"🏖️ Weekend: giorni {weekend_str}")
    else:
        st.sidebar.markdown("🏖️ Weekend: nessuno completo")

    # Pulsante per generare turni
    if st.button("🔄 Genera Turni", type="primary"):
        with st.spinner('Generazione turni in corso...'):
            try:
                # Caricamento dati
                nurses = load_nurses(os.path.join(data_folder, "nurses.json"))
                hard_constraints = load_hard_constraints(os.path.join(data_folder, "hard_constraints.json"))
                soft_constraints = load_soft_constraints(os.path.join(data_folder, "soft_constraints.json"))

                # Info caricamento
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("👥 Infermieri", len(nurses))
                with col2:
                    st.metric("🔒 Vincoli Hard", len(hard_constraints))
                with col3:
                    st.metric("🔓 Vincoli Soft", len(soft_constraints))

                # Calcolo piano per l'intero mese
                scheduler = Scheduler(
                    nurses,
                    hard_constraints,
                    soft_constraints,
                    num_days=total_days,
                    start_weekday=start_weekday  # NUOVO parametro
                )
                status, schedule = scheduler.solve(max_seconds=max_time)

                if status == cp_model.INFEASIBLE:
                    st.error("❌ Impossibile generare il piano - vincoli incompatibili!")
                    st.info("💡 Suggerimento: Verifica i vincoli nel file hard_constraints.json")
                    return
                elif status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    st.error("❌ Impossibile generare il piano per il periodo selezionato.")
                    return

                # Mostra stato soluzione
                if status == cp_model.OPTIMAL:
                    st.success("✅ Soluzione ottimale trovata!")
                else:
                    st.warning("⚠️ Soluzione feasible trovata (non ottimale)")

                # Formattazione matrice turni
                formatter = ScheduleFormatter(nurses, [d.strftime("%d/%m") for d in date_labels], period_desc)
                shift_matrix = formatter._build_shift_matrix(schedule)

                # Creazione DataFrame dei turni con weekend highlighting
                columns = []
                weekend_columns = set()

                for i, d in enumerate(date_labels):
                    day_name = ITALIAN_WEEKDAYS[d.weekday()]
                    col_name = f"{day_name} {d.day:02d}"
                    columns.append(col_name)

                    # NUOVO: Marca le colonne weekend per evidenziazione
                    if d.weekday() in [5, 6]:  # Sabato o domenica
                        weekend_columns.add(col_name)

                # Dati per il DataFrame principale
                data_dict = {}

                # Colonne riepilogo
                contract_hours = [
                    formatter._calculate_contract_hours_for_period(n.contracted_hours)
                    for n in nurses
                ]
                effective_hours = [
                    row.count("M") * 8 + row.count("P") * 8 + row.count("N") * 8
                    for row in shift_matrix
                ]
                diff_hours = [eff - ctr for eff, ctr in zip(effective_hours, contract_hours)]

                data_dict["Ore Ctr"] = [f"{int(c)}h" for c in contract_hours]
                data_dict["Ore Eff"] = [f"{h}h" for h in effective_hours]
                data_dict["Diff"] = [f"{d:+.0f}h" for d in diff_hours]

                # Colonne turni
                for col, day_shifts in zip(columns, zip(*shift_matrix)):
                    data_dict[col] = list(day_shifts)

                df = pd.DataFrame(data_dict, index=[n.name for n in nurses])

                # Visualizzazione tabella turni con evidenziazione weekend
                st.subheader(f"📅 Turni per {period_desc}")

                # Stile per evidenziare weekend
                def highlight_weekends(x):
                    styles = pd.DataFrame('', index=x.index, columns=x.columns)
                    for col in x.columns:
                        if col in weekend_columns:
                            styles[col] = 'background-color: #1565c0; color: white'
                    return styles

                # Mostra DataFrame con styling ALLARGATO
                styled_df = df.style.apply(highlight_weekends, axis=None)
                st.dataframe(
                    styled_df, 
                    use_container_width=True
                )

                # Legenda
                st.caption(
                    "**Legenda**: M=Mattino, P=Pomeriggio, N=Notte, S=Smonto, R=Riposo | "
                    "🏖️ Weekend evidenziati in blu scuro | Smonto NON conta come ore lavorate")

                # NUOVO: Analisi weekend liberi
                # NUOVO: Analisi weekend liberi (AGGIORNATA per 2+ weekend)
                st.subheader("🏖️ Analisi Weekend Liberi")

                if weekends:
                    weekend_analysis = []
                    total_target_met = 0  # Quanti infermieri hanno raggiunto l'obiettivo di 2+ weekend

                    for i, nurse in enumerate(nurses):
                        free_weekends = 0
                        weekend_details = []

                        for w_idx, (saturday, sunday) in enumerate(weekends):
                            is_free = (shift_matrix[i][saturday] == 'R' and shift_matrix[i][sunday] == 'R')
                            if is_free:
                                free_weekends += 1
                                weekend_details.append(f"W{w_idx + 1}")

                        # Determina se ha raggiunto l'obiettivo (2+ weekend liberi)
                        target_met = free_weekends >= 2
                        if target_met:
                            total_target_met += 1

                        weekend_analysis.append({
                            "Infermiere": nurse.name,
                            "Weekend liberi": free_weekends,
                            "Weekend totali": len(weekends),
                            "Obiettivo (≥2)": "✅" if target_met else "❌",
                            "Quali": ", ".join(weekend_details) if weekend_details else "Nessuno"
                        })

                    weekend_df = pd.DataFrame(weekend_analysis)
                    st.dataframe(weekend_df, use_container_width=True)

                    # Statistiche obiettivo
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        avg_free = sum(w["Weekend liberi"] for w in weekend_analysis) / len(weekend_analysis)
                        st.metric("Media weekend liberi", f"{avg_free:.1f}")

                    with col2:
                        target_percentage = (total_target_met / len(nurses)) * 100
                        st.metric("Obiettivo raggiunto", f"{total_target_met}/{len(nurses)}",
                                  delta=f"{target_percentage:.0f}%")

                    with col3:
                        st.metric("Weekend disponibili", f"{len(weekends)}")

                    # Analisi distribuzione
                    if len(weekends) >= 2:
                        distribution = {}
                        for analysis in weekend_analysis:
                            count = analysis["Weekend liberi"]
                            distribution[count] = distribution.get(count, 0) + 1

                        st.subheader("📊 Distribuzione Weekend Liberi")
                        dist_data = []
                        for free_count in sorted(distribution.keys()):
                            dist_data.append({
                                "Weekend liberi": free_count,
                                "Infermieri": distribution[free_count],
                                "Percentuale": f"{(distribution[free_count] / len(nurses) * 100):.1f}%"
                            })

                        dist_df = pd.DataFrame(dist_data)
                        st.dataframe(dist_df, use_container_width=True)

                        # Valutazione qualità soluzione
                        if target_percentage >= 80:
                            st.success("🎯 Ottima distribuzione! La maggior parte degli infermieri ha ≥2 weekend liberi")
                        elif target_percentage >= 60:
                            st.warning(
                                "⚠️ Distribuzione accettabile, ma alcuni infermieri hanno meno di 2 weekend liberi")
                        else:
                            st.error(
                                "❌ Distribuzione non ottimale. Considera di rilassare altri vincoli per migliorare i weekend liberi")
                    else:
                        st.warning("⚠️ Periodo troppo breve per avere 2 weekend completi")

                else:
                    st.info("ℹ️ Nessun weekend completo nel periodo selezionato")

                # Statistiche dettagliate (resto del codice invariato)
                st.subheader("📊 Statistiche Dettagliate")

                stats_data = []
                for n, row, ctr, eff, diff in zip(nurses, shift_matrix, contract_hours, effective_hours, diff_hours):
                    m = row.count("M")
                    p = row.count("P")
                    nn = row.count("N")
                    s = row.count("S")
                    r = row.count("R")
                    total_shifts = m + p + nn  # Smonto NON conta come turno lavorativo

                    stats_data.append({
                        "Infermiere": n.name,
                        "Mattino": m,
                        "Pomeriggio": p,
                        "Notte": nn,
                        "Smonto": s,
                        "Riposi": r,
                        "Tot turni": total_shifts,
                        "Ore lavorate": f"{eff}h",
                        "Ore contratto": f"{int(n.contracted_hours)}h",
                        "Differenza": f"{diff:+.0f}h"
                    })

                stats_df = pd.DataFrame(stats_data)
                st.dataframe(stats_df, use_container_width=True)

                # Riepilogo generale
                st.subheader("📈 Riepilogo Generale")
                col1, col2, col3 = st.columns(3)

                total_worked = sum(effective_hours)
                total_contract = sum(contract_hours)
                total_diff = total_worked - total_contract

                with col1:
                    st.metric("Ore Totali Lavorate", f"{total_worked}h")
                with col2:
                    st.metric("Ore Totali Contratto", f"{int(total_contract)}h")
                with col3:
                    st.metric("Differenza Totale", f"{total_diff:+.0f}h",
                              delta_color="inverse" if total_diff < 0 else "normal")

                # Distribuzione turni
                total_m = sum(row.count("M") for row in shift_matrix)
                total_p = sum(row.count("P") for row in shift_matrix)
                total_n = sum(row.count("N") for row in shift_matrix)
                total_s = sum(row.count("S") for row in shift_matrix)

                st.subheader("🔄 Distribuzione Turni")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Turni Mattino", total_m)
                with col2:
                    st.metric("Turni Pomeriggio", total_p)
                with col3:
                    st.metric("Turni Notte", total_n)
                with col4:
                    st.metric("Giorni Smonto", total_s)

            except FileNotFoundError as e:
                st.error(f"❌ File non trovato: {e}")
                st.info(
                    "Verifica che la cartella dati contenga: nurses.json, hard_constraints.json, soft_constraints.json")
            except Exception as e:
                st.error(f"❌ Errore: {str(e)}")
                st.info("Controlla i file di configurazione e riprova")

    else:
        # Istruzioni iniziali
        st.info("👆 Clicca su 'Genera Turni' per creare il piano mensile")

        with st.expander("ℹ️ Informazioni"):
            st.markdown("""
            ### Come funziona:
            1. Seleziona il mese e l'anno dal menu laterale
            2. Clicca su 'Genera Turni'
            3. Il sistema genererà automaticamente i turni rispettando tutti i vincoli
            4. I weekend (sabato+domenica) saranno evidenziati in blu
            5. Il soft constraint premia infermieri con almeno un weekend completo libero

            ### File richiesti nella cartella dati:
            - `nurses.json`: Elenco infermieri e ore contrattuali
            - `hard_constraints.json`: Vincoli obbligatori
            - `soft_constraints.json`: Preferenze (include weekend_rest)
            
            ### Soft constraint weekend:
            Il sistema cerca di assegnare almeno un weekend completo (sabato+domenica) 
            libero a ogni infermiere, riconoscendo automaticamente i veri weekend 
            basandosi sul calendario.
            """)


if __name__ == "__main__":
    main()