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
                scheduler = Scheduler(nurses, hard_constraints, soft_constraints, num_days=total_days)
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

                # Creazione DataFrame dei turni con nomi colonne univoci
                columns = []
                for i, d in enumerate(date_labels):
                    day_name = ITALIAN_WEEKDAYS[d.weekday()]
                    col_name = f"{day_name} {d.day:02d}"
                    columns.append(col_name)

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

                # Visualizzazione tabella turni SENZA styling problematico
                st.subheader(f"📅 Turni per {period_desc}")

                # Evidenzia weekend manualmente nel header
                header_html = "<tr><th></th>"
                for col in df.columns:
                    if any(day in col for day in ["Sab", "Dom"]) and col not in ["Ore Ctr", "Ore Eff", "Diff"]:
                        header_html += f'<th style="background-color: #e3f2fd">{col}</th>'
                    else:
                        header_html += f"<th>{col}</th>"
                header_html += "</tr>"

                # Mostra DataFrame senza styling
                st.dataframe(df, use_container_width=True)

                # Legenda
                st.caption(
                    "**Legenda**: M=Mattino, P=Pomeriggio, N=Notte, S=Smonto, R=Riposo | Weekend evidenziati in blu | Smonto NON conta come ore lavorate")

                # Statistiche dettagliate
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

            ### File richiesti nella cartella dati:
            - `nurses.json`: Elenco infermieri e ore contrattuali
            - `hard_constraints.json`: Vincoli obbligatori
            - `soft_constraints.json`: Preferenze (opzionale)
            """)


if __name__ == "__main__":
    main()