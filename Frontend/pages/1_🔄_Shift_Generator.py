"""
Shift Generator Page
====================
"""

import streamlit as st
import os
import sys
import calendar
import json
from datetime import datetime, timedelta
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from parser.nurse_loader import load_nurses
from parser.hard_constraint_loader import load_hard_constraints
from parser.soft_constraint_loader import load_soft_constraints

from model.scheduler import Scheduler
from utils.schedule_formatter import ScheduleFormatter
from ortools.sat.python import cp_model

# Import custom constraints to register them
try:
    import model.custom_constraints
except ImportError:
    # Fallback per path issues
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    import model.custom_constraints

# Import shift history functions
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shift_history import (
    init_shift_history, 
    shift_exists, 
    save_shift, 
    get_shift_key
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

# Descrizioni dei vincoli hard
HARD_CONSTRAINT_DESCRIPTIONS = {
    "coverage_minimum": "Copertura minima per turno",
    "max_consecutive_nights": "Massimo notti consecutive",
    "max_consecutive_work_days": "Massimo giorni lavorativi consecutivi",
    "no_pm_to_m_transition": "Nessuna transizione pomeriggio-mattina",
    "no_afternoon_after_morning": "Nessun pomeriggio dopo mattina",
    "mandatory_smonto_after_night": "Smonto obbligatorio dopo notte",
    "mandatory_rest_after_smonto": "Riposo obbligatorio dopo smonto",
    "shift_balance_morning_afternoon": "Bilanciamento turni mattina-pomeriggio",
    "workload_balance_hard": "Bilanciamento carico lavoro",
    "max_nights_per_month": "Massimo notti per mese",
    "nurse_absence": "Assenze programmate infermieri",
    "predefined_shifts": "Turni predefiniti infermieri"
}

def load_constraints_from_files(data_folder):
    """Carica i vincoli dai file JSON"""
    hard_path = os.path.join(data_folder, "hard_constraints.json")
    soft_path = os.path.join(data_folder, "soft_constraints.json")
    
    with open(hard_path, 'r') as f:
        hard_constraints = json.load(f)
    
    with open(soft_path, 'r') as f:
        soft_constraints = json.load(f)
    
    return hard_constraints, soft_constraints

def init_constraint_state(hard_constraints, soft_constraints):
    """Inizializza lo state dei vincoli se non esiste"""
    if 'hard_constraints' not in st.session_state:
        # Aggiungi i nuovi vincoli dinamicamente
        extended_hard_constraints = hard_constraints.copy()
        extended_hard_constraints.extend([
            {"type": "nurse_absence", "params": {"absences": []}},
            {"type": "predefined_shifts", "params": {"predefined": []}}
        ])
        st.session_state.hard_constraints = extended_hard_constraints
    
    if 'soft_constraints' not in st.session_state:
        st.session_state.soft_constraints = soft_constraints.copy()
    
    # Stato per abilitazione/disabilitazione vincoli
    if 'hard_enabled' not in st.session_state:
        st.session_state.hard_enabled = {i: True for i in range(len(st.session_state.hard_constraints))}
    
    if 'soft_enabled' not in st.session_state:
        st.session_state.soft_enabled = {i: True for i in range(len(soft_constraints))}

def render_constraint_editor(data_folder):
    """Renderizza l'interfaccia per modificare i vincoli"""
    with st.expander("⚙️ Configurazione Vincoli", expanded=False):
        tab1, tab2 = st.tabs(["🔒 Vincoli Obbligatori", "🔓 Vincoli Preferenze"])
        
        with tab1:
            st.subheader("Vincoli Hard (Obbligatori)")
            render_hard_constraints(data_folder)
        
        with tab2:
            st.subheader("Vincoli Soft (Preferenze)")
            render_soft_constraints()

def render_hard_constraints(data_folder):
    """Renderizza l'interfaccia per i vincoli hard"""
    for i, constraint in enumerate(st.session_state.hard_constraints):
        constraint_type = constraint["type"]
        params = constraint.get("params", {})
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            # Toggle per abilitare/disabilitare
            st.session_state.hard_enabled[i] = st.checkbox(
                "Attivo", 
                value=st.session_state.hard_enabled[i],
                key=f"hard_enabled_{i}"
            )
        
        with col2:
            st.write(f"**{HARD_CONSTRAINT_DESCRIPTIONS.get(constraint_type, constraint_type)}**")
            
            # Parametri modificabili
            if constraint_type == "coverage_minimum":
                col_a, col_b, col_c, col_d = st.columns(4)
                with col_a:
                    params["morning"] = st.number_input("Mattino", min_value=0, value=params.get("morning", 2), key=f"hard_morning_{i}")
                with col_b:
                    params["afternoon"] = st.number_input("Pomeriggio", min_value=0, value=params.get("afternoon", 2), key=f"hard_afternoon_{i}")
                with col_c:
                    params["night"] = st.number_input("Notte", min_value=0, value=params.get("night", 1), key=f"hard_night_{i}")
                with col_d:
                    params["smonto"] = st.number_input("Smonto", min_value=0, value=params.get("smonto", 0), key=f"hard_smonto_{i}")
            
            elif constraint_type == "max_consecutive_nights":
                params["max"] = st.number_input("Massimo notti consecutive", min_value=1, value=params.get("max", 3), key=f"hard_max_nights_{i}")
            
            elif constraint_type == "max_consecutive_work_days":
                params["max_days"] = st.number_input("Massimo giorni lavorativi consecutivi", min_value=1, value=params.get("max_days", 5), key=f"hard_max_days_{i}")
            
            elif constraint_type == "shift_balance_morning_afternoon":
                params["max_discrepancy"] = st.number_input("Massima discrepanza", min_value=0.0, value=params.get("max_discrepancy", 0.5), step=0.1, key=f"hard_discrepancy_{i}")
            
            elif constraint_type == "workload_balance_hard":
                col_a, col_b = st.columns(2)
                with col_a:
                    params["tolerance"] = st.number_input("Tolleranza", min_value=0.0, value=params.get("tolerance", 0.25), step=0.05, key=f"hard_tolerance_{i}")
                with col_b:
                    params["daily_shifts"] = st.number_input("Turni giornalieri", min_value=1, value=params.get("daily_shifts", 5), key=f"hard_daily_{i}")
            
            elif constraint_type == "max_nights_per_month":
                params["max_monthly"] = st.number_input("Massimo notti per mese", min_value=1, value=params.get("max_monthly", 6), key=f"hard_max_monthly_{i}")
            
            elif constraint_type == "nurse_absence":
                st.markdown("**Gestione Assenze Programmate**")
                
                # Inizializza la lista assenze se non esiste
                if "absences" not in params:
                    params["absences"] = []
                
                # Carica lista infermieri per il dropdown
                try:
                    nurses = load_nurses(os.path.join(data_folder, "nurses.json"))
                    nurse_names = [nurse.name for nurse in nurses]
                except:
                    nurse_names = []
                
                # Mostra assenze esistenti
                if params["absences"]:
                    st.markdown("**Assenze Correnti:**")
                    for idx, absence in enumerate(params["absences"]):
                        col_a, col_b, col_c = st.columns([2, 2, 1])
                        with col_a:
                            st.write(f"👤 {absence['nurse_name']}")
                        with col_b:
                            st.write(f"📅 Giorni {absence['start_day']+1}-{absence['end_day']+1}")
                        with col_c:
                            if st.button("🗑️", key=f"del_absence_{i}_{idx}", help="Elimina assenza"):
                                params["absences"].pop(idx)
                                st.rerun()
                
                # Form per aggiungere nuova assenza
                with st.expander("➕ Aggiungi Assenza"):
                    if nurse_names:
                        new_nurse = st.selectbox("Infermiere", nurse_names, key=f"new_nurse_{i}")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            start_day = st.number_input("Giorno inizio", min_value=1, max_value=31, value=1, key=f"start_day_{i}")
                        with col_b:
                            end_day = st.number_input("Giorno fine", min_value=1, max_value=31, value=1, key=f"end_day_{i}")
                        
                        reason = st.selectbox("Motivo", ["Formazione", "Vacanza", "Altro"], key=f"reason_{i}")
                        
                        if st.button("➕ Aggiungi", key=f"add_absence_{i}"):
                            if start_day <= end_day:
                                new_absence = {
                                    "nurse_name": new_nurse,
                                    "start_day": start_day - 1,  # Converti in 0-based
                                    "end_day": end_day - 1,      # Converti in 0-based
                                    "reason": reason
                                }
                                params["absences"].append(new_absence)
                                st.success(f"Assenza aggiunta per {new_nurse}")
                                st.rerun()
                            else:
                                st.error("Il giorno di fine deve essere >= giorno di inizio")
                    else:
                        st.warning("Carica prima la lista infermieri dal file nurses.json")
            
            elif constraint_type == "predefined_shifts":
                st.markdown("**Gestione Turni Predefiniti**")
                
                # Inizializza la lista turni predefiniti se non esiste
                if "predefined" not in params:
                    params["predefined"] = []
                
                # Carica lista infermieri per il dropdown
                try:
                    nurses = load_nurses(os.path.join(data_folder, "nurses.json"))
                    nurse_names = [nurse.name for nurse in nurses]
                except:
                    nurse_names = []
                
                # Mappatura turni per display
                shift_types = {
                    "MORNING": "🌅 Mattino (06:00-14:00)",
                    "AFTERNOON": "🌆 Pomeriggio (14:00-22:00)", 
                    "NIGHT": "🌙 Notte (22:00-06:00)",
                    "SMONTO": "😴 Smonto"
                }
                
                # Mostra turni predefiniti esistenti
                if params["predefined"]:
                    st.markdown("**Turni Predefiniti Correnti:**")
                    for idx, predef in enumerate(params["predefined"]):
                        col_a, col_b, col_c, col_d = st.columns([2, 1, 2, 1])
                        with col_a:
                            st.write(f"👤 {predef['nurse_name']}")
                        with col_b:
                            st.write(f"📅 Giorno {predef['day']+1}")
                        with col_c:
                            shift_display = shift_types.get(predef['shift_type'], predef['shift_type'])
                            st.write(shift_display)
                        with col_d:
                            if st.button("🗑️", key=f"del_predef_{i}_{idx}", help="Elimina turno predefinito"):
                                params["predefined"].pop(idx)
                                st.rerun()
                
                # Form per aggiungere nuovo turno predefinito
                with st.expander("➕ Aggiungi Turno Predefinito"):
                    if nurse_names:
                        new_nurse = st.selectbox("Infermiere", nurse_names, key=f"new_nurse_predef_{i}")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            day = st.number_input("Giorno del mese", min_value=1, max_value=31, value=1, key=f"day_predef_{i}")
                        with col_b:
                            shift_type = st.selectbox(
                                "Tipo turno", 
                                list(shift_types.keys()),
                                format_func=lambda x: shift_types[x],
                                key=f"shift_type_predef_{i}"
                            )
                        
                        reason = st.text_input("Motivo/Note (opzionale)", key=f"reason_predef_{i}")
                        
                        if st.button("➕ Aggiungi Turno", key=f"add_predef_{i}"):
                            new_predefined = {
                                "nurse_name": new_nurse,
                                "day": day - 1,  # Converti in 0-based
                                "shift_type": shift_type,
                                "reason": reason if reason else "Turno predefinito"
                            }
                            params["predefined"].append(new_predefined)
                            st.success(f"Turno predefinito aggiunto per {new_nurse}")
                            st.rerun()
                    else:
                        st.warning("Carica prima la lista infermieri dal file nurses.json")
            
            # Aggiorna i parametri nel session state
            st.session_state.hard_constraints[i]["params"] = params
        
        st.divider()

def render_soft_constraints():
    """Renderizza l'interfaccia per i vincoli soft"""
    for i, constraint in enumerate(st.session_state.soft_constraints):
        constraint_type = constraint["type"]
        params = constraint.get("params", {})
        weight = constraint.get("weight", 100)
        description = constraint.get("description", "")
        
        col1, col2 = st.columns([1, 3])
        
        with col1:
            # Toggle per abilitare/disabilitare
            st.session_state.soft_enabled[i] = st.checkbox(
                "Attivo", 
                value=st.session_state.soft_enabled[i],
                key=f"soft_enabled_{i}"
            )
        
        with col2:
            st.write(f"**{constraint_type.replace('_', ' ').title()}**")
            if description:
                st.caption(description)
            
            # Peso del vincolo
            constraint["weight"] = st.slider(
                "Peso (importanza)", 
                min_value=1, 
                max_value=200, 
                value=weight,
                key=f"soft_weight_{i}"
            )
            
            # Parametri specifici
            if constraint_type == "shift_blocks":
                col_a, col_b = st.columns(2)
                with col_a:
                    params["min_block_size"] = st.number_input("Dimensione minima blocco", min_value=1, value=params.get("min_block_size", 2), key=f"soft_min_block_{i}")
                with col_b:
                    params["bonus_block_size"] = st.number_input("Dimensione bonus blocco", min_value=1, value=params.get("bonus_block_size", 3), key=f"soft_bonus_block_{i}")
            
            # Aggiorna i parametri nel session state
            st.session_state.soft_constraints[i]["params"] = params
        
        st.divider()

def get_active_hard_constraints():
    """Restituisce solo i vincoli hard attivi e non vuoti"""
    active_constraints = []
    if 'hard_constraints' not in st.session_state:
        return []
    
    for i, constraint in enumerate(st.session_state.hard_constraints):
        if st.session_state.hard_enabled.get(i, True):
            # Filtra vincoli vuoti
            if constraint['type'] == 'nurse_absence':
                if constraint['params'].get('absences', []):
                    active_constraints.append(constraint)
            elif constraint['type'] == 'predefined_shifts':
                if constraint['params'].get('predefined', []):
                    active_constraints.append(constraint)
            else:
                active_constraints.append(constraint)
    return active_constraints

def get_active_soft_constraints():
    """Restituisce solo i vincoli soft attivi"""
    active_constraints = []
    if 'soft_constraints' not in st.session_state:
        return []
        
    for i, constraint in enumerate(st.session_state.soft_constraints):
        if st.session_state.soft_enabled.get(i, True):
            active_constraints.append(constraint)
    return active_constraints


def main():
    st.title("🏥 Generatore Turni - Vista Mensile")
    
    # Inizializza lo storico dei turni
    init_shift_history()
    
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
    default_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    data_folder = st.sidebar.text_input("Cartella dati", default_folder)
    
    # Carica vincoli dai file e inizializza lo state
    try:
        hard_constraints_file, soft_constraints_file = load_constraints_from_files(data_folder)
        init_constraint_state(hard_constraints_file, soft_constraints_file)
    except FileNotFoundError:
        st.error("❌ File dei vincoli non trovati nella cartella dati specificata")
        return

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

    # Mostra weekend identificati (calcolo diretto senza scheduler)
    weekends = []
    for day in range(total_days - 1):
        weekday = (start_weekday + day) % 7
        next_weekday = (start_weekday + day + 1) % 7
        if weekday == 5 and next_weekday == 6:  # Sabato + Domenica
            weekends.append((day, day + 1))
    
    if weekends:
        weekend_str = ", ".join([f"{s+1}-{d+1}" for s, d in weekends])
        st.sidebar.markdown(f"🏖️ Weekend: giorni {weekend_str}")
    else:
        st.sidebar.markdown("🏖️ Weekend: nessuno completo")

    # Sezione configurazione vincoli
    render_constraint_editor(data_folder)

    # Controllo se esiste già un turno per questo mese-anno
    if shift_exists(year, month):
        st.warning(f"⚠️ **Attenzione!** Esiste già un turno per {period_desc}")
        st.info("Procedendo con la generazione, il turno esistente verrà sovrascritto.")

    # Pulsante per generare turni
    if st.button("🔄 Genera Turni", type="primary"):
        with st.spinner('Generazione turni in corso...'):
            try:
                # Caricamento dati
                nurses = load_nurses(os.path.join(data_folder, "nurses.json"))
                
                # Usa i vincoli modificati dall'interfaccia
                hard_constraints = get_active_hard_constraints()
                soft_constraints = get_active_soft_constraints()

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

                # Salva il turno nello storico
                stats = {
                    "total_worked": total_worked,
                    "total_contract": total_contract,
                    "total_diff": total_diff
                }
                
                save_shift(
                    year=year,
                    month=month,
                    period_desc=period_desc,
                    nurses=nurses,
                    schedule=schedule,
                    shift_matrix=shift_matrix,
                    stats=stats,
                    hard_constraints=hard_constraints,
                    soft_constraints=soft_constraints
                )
                
                st.success(f"✅ Turno salvato nello storico per {period_desc}")

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