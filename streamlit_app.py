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
    st.title("Visualizzazione Turni Infermieristici - Vista Mensile")

    # Sidebar: percorso cartella dati
    default_folder = os.path.join(os.getcwd(), "data")
    data_folder = st.sidebar.text_input("Cartella dati", default_folder)

    # Sidebar: selezione mese e anno
    months = list(calendar.month_name)[1:]
    now = datetime.now()
    month_name = st.sidebar.selectbox("Mese", months, index=now.month - 1)
    year = st.sidebar.number_input("Anno", min_value=2000, max_value=2100, value=now.year)
    month = months.index(month_name) + 1

    # Intervallo date per il mese selezionato
    start_date = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, last_day)
    total_days = (end_date - start_date).days + 1
    date_labels = [start_date + timedelta(days=i) for i in range(total_days)]
    period_desc = f"{month_name} {year}"

    # Caricamento dati
    nurses = load_nurses(os.path.join(data_folder, "nurses.json"))
    hard_constraints = load_hard_constraints(os.path.join(data_folder, "hard_constraints.json"))
    soft_constraints = load_soft_constraints(os.path.join(data_folder, "soft_constraints.json"))

    # Calcolo piano per l'intero mese
    scheduler = Scheduler(nurses, hard_constraints, soft_constraints, num_days=total_days)
    status, schedule = scheduler.solve()
    if not schedule:
        st.error("Impossibile generare il piano per il periodo selezionato.")
        return

    # Formattazione matrice turni
    formatter = ScheduleFormatter(nurses, date_labels, period_desc)
    shift_matrix = formatter._build_shift_matrix(schedule)

    # Creazione DataFrame dei turni
    columns = [
        f"{ITALIAN_WEEKDAYS[d.weekday()]} {d.day:02d}/{d.month:02d}"
        for d in date_labels
    ]
    df = pd.DataFrame(shift_matrix, index=[n.name for n in nurses], columns=columns)

    # Calcolo riepilogo ore
    contract_hours = [
        formatter._calculate_contract_hours_for_period(n.contracted_hours)
        for n in nurses
    ]
    effective_hours = [
        row.count("M") * 8 + row.count("P") * 8 + row.count("N") * 8
        for row in shift_matrix
    ]
    diff_hours = [eff - ctr for eff, ctr in zip(effective_hours, contract_hours)]

    # Aggiunta colonne di riepilogo (senza nome infermiere)
    df.insert(0, "Diff", [f"{d:+.0f}h" for d in diff_hours])
    df.insert(0, "OreEff", [f"{h}h" for h in effective_hours])
    df.insert(0, "OreCtr", [f"{int(c)}h" for c in contract_hours])

    # Identificazione colonne weekend
    weekend_cols = [
        col for date, col in zip(date_labels, columns) if date.weekday() >= 5
    ]

    # Styling: evidenzia colonne weekend con sfondo blu chiaro
    def highlight_weekend(col):
        if col.name in weekend_cols:
            return ['background-color: #3d85c6'] * len(col)
        else:
            return [''] * len(col)

    styled_df = df.style.apply(highlight_weekend, axis=0)

    # Visualizzazione tabella turni con styling
    st.subheader(f"Turni per {period_desc}")
    st.dataframe(styled_df, use_container_width=True)

    # Statistiche dettagliate in tabella
    stats_data = {
        "Infermiere": [],
        "M": [],
        "P": [],
        "N": [],
        "R": [],
        "Tot turni": [],
        "Ore": [],
        "Contratto": [],
        "Diff": [],
    }
    for n, row, ctr, eff, diff in zip(nurses, shift_matrix, contract_hours, effective_hours, diff_hours):
        m = row.count("M")
        p = row.count("P")
        nn = row.count("N")
        r = row.count("R")
        total_shifts = m + p + nn

        stats_data["Infermiere"].append(n.name)
        stats_data["M"].append(m)
        stats_data["P"].append(p)
        stats_data["N"].append(nn)
        stats_data["R"].append(r)
        stats_data["Tot turni"].append(total_shifts)
        stats_data["Ore"].append(f"{eff}h")
        stats_data["Contratto"].append(f"{int(n.contracted_hours)}h")
        stats_data["Diff"].append(f"{diff:+.0f}h")

    stats_df = pd.DataFrame(stats_data)

    st.subheader("📊 STATISTICHE DETTAGLIATE")
    st.table(stats_df)

if __name__ == "__main__":
    main()
