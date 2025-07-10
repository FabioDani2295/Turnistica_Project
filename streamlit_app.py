"""
streamlit_app.py - SISTEMA COMPLETO CON MODIFICHE TURNI
=======================================================
Interfaccia Streamlit avanzata per generazione e modifica turni infermieristici
con supporto per scenari alternativi e modifiche iterative.
"""

import streamlit as st
import os
import calendar
import pickle
import copy
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd

from parser.nurse_loader import load_nurses
from parser.hard_constraint_loader import load_hard_constraints
from parser.soft_constraint_loader import load_soft_constraints

from model.scheduler import Scheduler
from utils.schedule_formatter import ScheduleFormatter
from ortools.sat.python import cp_model
from main import solve_model

# Sistema di modifiche
from modification_handler import ModificationHandler, Modification, Scenario
from parser.solution_analyzer import compare_plans
from utils.enums import ShiftType

# Mappatura giorni della settimana in italiano
ITALIAN_WEEKDAYS = {
    0: "Lun", 1: "Mar", 2: "Mer", 3: "Gio", 
    4: "Ven", 5: "Sab", 6: "Dom",
}

# File per persistenza stato
CURRENT_PLAN_FILE = "current_plan.pkl"
PLAN_METADATA_FILE = "plan_metadata.pkl"


def init_session_state():
    """Inizializza lo stato della sessione Streamlit."""
    if 'current_plan' not in st.session_state:
        st.session_state.current_plan = None
    if 'plan_metadata' not in st.session_state:
        st.session_state.plan_metadata = None
    if 'modification_mode' not in st.session_state:
        st.session_state.modification_mode = False
    if 'generated_scenarios' not in st.session_state:
        st.session_state.generated_scenarios = []
    if 'selected_scenario_id' not in st.session_state:
        st.session_state.selected_scenario_id = None


def save_current_plan(plan: List[Dict], metadata: Dict):
    """Salva il piano corrente su disco per persistenza."""
    try:
        with open(CURRENT_PLAN_FILE, 'wb') as f:
            pickle.dump(plan, f)
        with open(PLAN_METADATA_FILE, 'wb') as f:
            pickle.dump(metadata, f)
        st.session_state.current_plan = plan
        st.session_state.plan_metadata = metadata
    except Exception as e:
        st.warning(f"Impossibile salvare piano: {e}")


def load_current_plan() -> tuple[Optional[List[Dict]], Optional[Dict]]:
    """Carica il piano corrente da disco."""
    try:
        if os.path.exists(CURRENT_PLAN_FILE) and os.path.exists(PLAN_METADATA_FILE):
            with open(CURRENT_PLAN_FILE, 'rb') as f:
                plan = pickle.load(f)
            with open(PLAN_METADATA_FILE, 'rb') as f:
                metadata = pickle.load(f)
            return plan, metadata
    except Exception as e:
        st.warning(f"Impossibile caricare piano esistente: {e}")
    return None, None


def setup_page_style():
    """Configura lo stile CSS della pagina."""
    st.markdown("""
    <style>
    .main .block-container {
        max-width: 100% !important;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
    }
    
    /* Stile tabelle con sfondo verde scuro - solo per piano turni e statistiche */
    .main-schedule-table .stDataFrame {
        width: 100% !important;
        background-color: #1e4d2b !important;
    }
    
    .main-schedule-table .stDataFrame > div {
        width: 100% !important;
        overflow-x: auto;
        background-color: #1e4d2b !important;
    }
    
    .main-schedule-table .stDataFrame td, .main-schedule-table .stDataFrame th {
        font-size: 11px !important;
        white-space: nowrap;
        text-align: center;
        padding: 3px 4px !important;
        min-width: 40px;
        max-width: 55px;
        background-color: #1e4d2b !important;
        color: white !important;
        border: 1px solid #2d5a34 !important;
    }
    
    .main-schedule-table .stDataFrame table {
        background-color: #1e4d2b !important;
    }
    
    .main-schedule-table .stDataFrame tbody tr:hover {
        background-color: #2d5a34 !important;
    }
    
    /* Stile per sezioni con sfondo verde scuro */
    .section-header {
        background-color: #1e4d2b;
        color: white;
        padding: 10px;
        border-radius: 5px;
        margin: 10px 0;
    }
    
    /* Stile per modifiche evidenziate */
    .modification-highlight {
        border: 2px solid #ff6b6b;
        border-radius: 5px;
        padding: 5px;
        margin: 5px 0;
        background-color: #1e4d2b;
        color: white;
    }
    
    /* Stile per scenari */
    .scenario-card {
        border: 1px solid #2d5a34;
        border-radius: 5px;
        padding: 10px;
        margin: 5px 0;
        background-color: #1e4d2b;
        color: white;
    }
    
    .scenario-selected {
        border-color: #4CAF50;
        background-color: #2d5a34;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)


def render_sidebar():
    """Renderizza la sidebar con controlli principali."""
    st.sidebar.title("⚙️ Configurazione")
    
    # Percorso dati
    default_folder = os.path.join(os.getcwd(), "data")
    data_folder = st.sidebar.text_input("📁 Cartella dati", default_folder)
    
    # Selezione periodo
    st.sidebar.markdown("### 📅 Periodo")
    months = list(calendar.month_name)[1:]
    now = datetime.now()
    month_name = st.sidebar.selectbox("Mese", months, index=now.month - 1)
    year = st.sidebar.number_input("Anno", min_value=2000, max_value=2100, value=now.year)
    month = months.index(month_name) + 1
    
    # Parametri risoluzione
    st.sidebar.markdown("### ⚡ Risoluzione")
    max_time = st.sidebar.slider("Tempo max (sec)", 30, 300, 120)
    
    return data_folder, month, year, month_name, max_time


def calculate_period_info(month: int, year: int):
    """Calcola informazioni sul periodo selezionato."""
    start_date = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, last_day)
    total_days = (end_date - start_date).days + 1
    date_labels = [start_date + timedelta(days=i) for i in range(total_days)]
    start_weekday = start_date.weekday()
    
    return start_date, end_date, total_days, date_labels, start_weekday


def generate_initial_plan(data_folder: str, total_days: int, start_weekday: int, max_time: int, period_desc: str, start_date: datetime = None):
    """Genera il piano iniziale."""
    try:
        # Carica dati
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
        
        # Generazione piano
        with st.spinner('🔄 Generazione piano iniziale...'):
            status, schedule = solve_model(
                nurses, hard_constraints, soft_constraints,
                total_days, start_weekday, max_time
            )
        
        if status == cp_model.INFEASIBLE:
            st.error("❌ Impossibile generare il piano - vincoli incompatibili!")
            st.info("💡 Suggerimento: Verifica i vincoli nel file hard_constraints.json")
            return None, None, None, None
        elif status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            st.error("❌ Impossibile generare il piano per il periodo selezionato.")
            return None, None, None, None
        
        # Salva piano
        metadata = {
            'period_desc': period_desc,
            'total_days': total_days,
            'start_weekday': start_weekday,
            'start_date': start_date,
            'generation_time': datetime.now(),
            'status': 'optimal' if status == cp_model.OPTIMAL else 'feasible'
        }
        
        save_current_plan(schedule, metadata)
        
        # Mostra stato soluzione
        if status == cp_model.OPTIMAL:
            st.success("✅ Soluzione ottimale trovata!")
        else:
            st.warning("⚠️ Soluzione feasible trovata (non ottimale)")
        
        return nurses, hard_constraints, soft_constraints, schedule
        
    except FileNotFoundError as e:
        st.error(f"❌ File non trovato: {e}")
        st.info("Verifica che la cartella dati contenga: nurses.json, hard_constraints.json, soft_constraints.json")
        return None, None, None, None
    except Exception as e:
        st.error(f"❌ Errore: {str(e)}")
        return None, None, None, None


def display_schedule_table(schedule: List[Dict], nurses, date_labels: List[datetime], metadata: Dict):
    """Visualizza la tabella dei turni."""
    st.markdown('<div class="section-header"><h3>📅 Piano Turni</h3></div>', unsafe_allow_html=True)
    
    # Info piano
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"📊 **Periodo:** {metadata['period_desc']}")
    with col2:
        st.info(f"⏰ **Generato:** {metadata['generation_time'].strftime('%d/%m %H:%M')}")
    with col3:
        st.info(f"🎯 **Qualità:** {metadata['status'].title()}")
    
    # Prepara dati tabella
    formatter = ScheduleFormatter(nurses, [d.strftime("%d/%m") for d in date_labels], metadata['period_desc'])
    shift_matrix = formatter._build_shift_matrix(schedule)
    
    # Identifica weekend
    weekend_columns = set()
    columns = []
    for i, d in enumerate(date_labels):
        day_name = ITALIAN_WEEKDAYS[d.weekday()]
        col_name = f"{day_name} {d.day:02d}"
        columns.append(col_name)
        if d.weekday() in [5, 6]:  # Sabato o domenica
            weekend_columns.add(col_name)
    
    # Crea DataFrame
    data_dict = {}
    
    # Colonne riepilogo
    contract_hours = [formatter._calculate_contract_hours_for_period(n.contracted_hours) for n in nurses]
    effective_hours = [row.count("M") * 8 + row.count("P") * 8 + row.count("N") * 8 for row in shift_matrix]
    diff_hours = [eff - ctr for eff, ctr in zip(effective_hours, contract_hours)]
    
    data_dict["Ore Ctr"] = [f"{int(c)}h" for c in contract_hours]
    data_dict["Ore Eff"] = [f"{h}h" for h in effective_hours]
    data_dict["Diff"] = [f"{d:+.0f}h" for d in diff_hours]
    
    # Colonne turni
    for col, day_shifts in zip(columns, zip(*shift_matrix)):
        data_dict[col] = list(day_shifts)
    
    df = pd.DataFrame(data_dict, index=[n.name for n in nurses])
    
    # Styling weekend
    def highlight_weekends(x):
        styles = pd.DataFrame('', index=x.index, columns=x.columns)
        for col in x.columns:
            if col in weekend_columns:
                styles[col] = 'background-color: #1565c0; color: white'
        return styles
    
    styled_df = df.style.apply(highlight_weekends, axis=None)
    
    # Wrapper per stile verde scuro
    st.markdown('<div class="main-schedule-table">', unsafe_allow_html=True)
    st.dataframe(styled_df, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.caption("**Legenda**: M=Mattino, P=Pomeriggio, N=Notte, S=Smonto, R=Riposo | 🏖️ Weekend evidenziati in blu scuro")
    
    return shift_matrix, df


def render_modification_interface(nurses, hard_constraints, soft_constraints, current_plan, metadata, max_time):
    """Renderizza l'interfaccia per le modifiche ai turni."""
    
    st.markdown('<div class="section-header"><h3>✏️ Modifica Turni</h3></div>', unsafe_allow_html=True)
    
    # Forza la visualizzazione sempre
    st.markdown("---")
    
    # Selezione modifica
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        nurse_names = [n.name for n in nurses]
        selected_nurse = st.selectbox("👤 Infermiere", nurse_names, key="mod_nurse")
    
    with col2:
        days_options = [(i, f"Giorno {i+1}") for i in range(metadata['total_days'])]
        selected_day_idx, selected_day_label = st.selectbox("📅 Giorno", days_options, format_func=lambda x: x[1], key="mod_day")
    
    with col3:
        shift_options = [
            ('M', '🌅 Mattino'),
            ('P', '🌞 Pomeriggio'), 
            ('N', '🌙 Notte'),
            ('S', '🔄 Smonto'),
            ('R', '😴 Riposo')
        ]
        selected_shift, shift_label = st.selectbox("🔄 Nuovo Turno", shift_options, format_func=lambda x: x[1], key="mod_shift")
    
    with col4:
        reason = st.text_input("📝 Motivo", placeholder="es. Cambio richiesto", key="mod_reason")
    
    # Mostra turno attuale con styling verde scuro
    current_shift = get_current_shift(current_plan, nurses, selected_nurse, selected_day_idx)
    st.markdown(f"""
    <div style="background-color: #1e4d2b; color: white; padding: 10px; border-radius: 5px; margin: 10px 0;">
        <strong>🔍 Turno attuale:</strong> {selected_nurse} - {selected_day_label} - {format_shift_display(current_shift)}
    </div>
    """, unsafe_allow_html=True)
    
    # Bottone genera scenari con info timeout
    st.markdown(f"**⏱️ Timeout configurato:** {max_time} secondi")
    
    if st.button("🎭 Genera Scenari Alternativi", type="primary", key="generate_scenarios_btn"):
        generate_scenarios(nurses, hard_constraints, soft_constraints, current_plan, metadata, 
                         selected_nurse, selected_day_idx, selected_shift, reason, max_time)


def get_current_shift(plan: List[Dict], nurses, nurse_name: str, day: int) -> str:
    """Ottiene il turno attuale di un infermiere in un giorno specifico."""
    try:
        # Trova l'indice dell'infermiere
        nurse_idx = next(i for i, n in enumerate(nurses) if n.name == nurse_name)
        
        # Converte piano in matrice
        date_labels = [f"Day{i}" for i in range(len(plan))]
        formatter = ScheduleFormatter(nurses, date_labels, "Current")
        shift_matrix = formatter._build_shift_matrix(plan)
        
        return shift_matrix[nurse_idx][day]
    except:
        return 'R'  # Default riposo


def format_shift_display(shift: str) -> str:
    """Formatta la visualizzazione del turno."""
    mapping = {
        'M': '🌅 Mattino',
        'P': '🌞 Pomeriggio',
        'N': '🌙 Notte', 
        'S': '🔄 Smonto',
        'R': '😴 Riposo'
    }
    return mapping.get(shift, f'❓ {shift}')


def generate_scenarios(nurses, hard_constraints, soft_constraints, current_plan, metadata,
                      nurse_name: str, day: int, new_shift: str, reason: str, max_time: int):
    """Genera scenari alternativi per la modifica richiesta."""
    
    with st.spinner(f'🔮 Generazione scenari alternativi (timeout: {max_time}s)...'):
        try:
            # Crea handler modifiche
            handler = ModificationHandler(
                nurses, hard_constraints, soft_constraints,
                metadata['total_days'], metadata['start_weekday']
            )
            
            # Crea oggetto modifica
            modification = Modification(
                nurse_name=nurse_name,
                day=day,
                new_shift=new_shift,
                reason=reason
            )
            
            # Genera scenari usando il timeout configurabile
            scenarios = handler.generate_alternative_scenarios(current_plan, modification, max_scenarios=5, timeout_seconds=max_time)
            
            # Salva scenari nello stato
            st.session_state.generated_scenarios = scenarios
            st.session_state.modification_mode = True
            
            if scenarios:
                st.success(f"✅ Generati {len(scenarios)} scenari alternativi in {max_time}s!")
            else:
                st.warning("⚠️ Nessuno scenario generato. La modifica potrebbe essere incompatibile con i vincoli.")
                
        except Exception as e:
            st.error(f"❌ Errore nella generazione scenari: {e}")
            st.exception(e)


def display_scenarios(scenarios: List[Scenario], current_plan: List[Dict], nurses, metadata: Dict):
    """Visualizza i scenari alternativi generati."""
    
    st.markdown('<div class="section-header"><h3>🎭 Scenari Alternativi</h3></div>', unsafe_allow_html=True)
    
    if not scenarios:
        st.info("Nessuno scenario disponibile.")
        return
    
    # Tabs per scenari
    tab_names = [f"Scenario {i+1}" for i in range(len(scenarios))]
    tabs = st.tabs(tab_names)
    
    for i, (tab, scenario) in enumerate(zip(tabs, scenarios)):
        with tab:
            display_single_scenario(scenario, current_plan, nurses, metadata, i)
    
    # Selezione e applicazione scenario
    st.markdown("### 🎯 Applica Scenario")
    
    col1, col2 = st.columns(2)
    
    with col1:
        scenario_options = [(i, f"Scenario {i+1} - {s.modifications_count} modifiche") 
                          for i, s in enumerate(scenarios)]
        selected_idx = st.selectbox("Scegli scenario", range(len(scenarios)), 
                                  format_func=lambda x: scenario_options[x][1])
    
    with col2:
        if st.button("✅ Applica Scenario Selezionato", type="primary"):
            apply_selected_scenario(scenarios[selected_idx], metadata)


def display_scenario_compact_stats(scenario: Scenario, comparison: Dict, nurses):
    """Visualizza statistiche compatte per lo scenario."""
    
    # Calcola ore totali scenario vs originale
    scenario_matrix = []
    for day in scenario.plan:
        day_matrix = []
        for nurse in nurses:
            shift = 'R'  # Default riposo
            for shift_type in ['morning', 'afternoon', 'night', 'smonto']:
                if nurse.name in day.get(shift_type, []):
                    shift = {'morning': 'M', 'afternoon': 'P', 'night': 'N', 'smonto': 'S'}[shift_type]
                    break
            day_matrix.append(shift)
        scenario_matrix.append(day_matrix)
    
    # Calcola ore scenario
    scenario_hours = {}
    for i, nurse in enumerate(nurses):
        hours = 0
        for day in scenario_matrix:
            if i < len(day):
                shift = day[i]
                if shift in ['M', 'P', 'N']:
                    hours += 8
        scenario_hours[nurse.name] = hours
    
    # Calcola differenza ore contratto
    total_contract_hours = sum(nurse.contracted_hours for nurse in nurses)
    total_scenario_hours = sum(scenario_hours.values())
    hours_diff = total_scenario_hours - total_contract_hours
    
    # Statistiche sui tipi di modifiche
    change_types = comparison.get("changes_by_type", {})
    
    # Layout compatto con metriche
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📊 Ore Totali", f"{total_scenario_hours}h", f"{hours_diff:+}h")
        
    with col2:
        shift_changes = change_types.get("shift_change", 0)
        st.metric("🔄 Cambio Turni", shift_changes)
        
    with col3:
        new_assignments = change_types.get("new_assignment", 0)
        st.metric("➕ Nuovi Assegn.", new_assignments)
        
    with col4:
        removed_assignments = change_types.get("removed_assignment", 0)
        st.metric("➖ Rimossi Assegn.", removed_assignments)
    
    # Seconda riga di statistiche
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        weekend_changes = sum(1 for change in comparison.get("detailed_changes", []) 
                             if change.get("is_weekend", False))
        st.metric("🏖️ Weekend Modificati", weekend_changes)
        
    with col2:
        night_changes = sum(1 for change in comparison.get("detailed_changes", []) 
                           if change.get("new_shift") == "N" or change.get("old_shift") == "N")
        st.metric("🌙 Notti Coinvolte", night_changes)
        
    with col3:
        nurses_affected = len(set(change.get("nurse", "") for change in comparison.get("detailed_changes", [])))
        st.metric("👥 Infermieri Coinvolti", nurses_affected)
        
    with col4:
        stability_pct = scenario.stability_score * 100
        st.metric("🎯 Stabilità", f"{stability_pct:.1f}%")


def display_single_scenario(scenario: Scenario, current_plan: List[Dict], nurses, metadata: Dict, index: int):
    """Visualizza un singolo scenario con confronto."""
    
    # Metriche scenario
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("🔄 Modifiche", scenario.modifications_count)
    with col2:
        st.metric("👥 Infermieri coinvolti", scenario.affected_nurses)
    with col3:
        st.metric("🏆 Qualità", f"{scenario.quality_score:.2f}")
    with col4:
        st.metric("🎯 Stabilità", f"{scenario.stability_score:.2f}")
    
    # Confronto dettagliato
    comparison = scenario.comparison_report
    
    # Mostra sempre le statistiche, anche se non ci sono modifiche
    st.markdown("#### 📊 Analisi Modifiche")
    
    # Debug: mostra informazioni sul confronto
    if comparison["total_changes"] == 0:
        st.warning("⚠️ Questo scenario non presenta modifiche rispetto al piano originale")
    
    # Statistiche compatte ore e soft constraints
    display_scenario_compact_stats(scenario, comparison, nurses)
    
    if comparison["total_changes"] > 0:
        # Dettaglio modifiche
        with st.expander("🔍 Dettaglio Modifiche"):
            changes_data = []
            for change in comparison["detailed_changes"][:10]:  # Primi 10
                changes_data.append({
                    "Infermiere": change["nurse"],
                    "Giorno": change["day"] + 1,
                    "Da": format_shift_display(change["old_shift"]),
                    "A": format_shift_display(change["new_shift"]),
                    "Tipo": change["change_type"]
                })
            
            if changes_data:
                changes_df = pd.DataFrame(changes_data)
                st.dataframe(changes_df, use_container_width=True)
            
            if len(comparison["detailed_changes"]) > 10:
                st.caption(f"... e altre {len(comparison['detailed_changes']) - 10} modifiche")
    
    # Visualizzazione piano scenario (opzionale, per non appesantire)
    if st.checkbox(f"📅 Mostra Piano Completo Scenario {index + 1}"):
        display_scenario_schedule_table(scenario, current_plan, nurses, metadata)


def display_scenario_schedule_table(scenario: Scenario, original_plan: List[Dict], nurses, metadata: Dict):
    """Visualizza la tabella dei turni di uno scenario con modifiche evidenziate."""
    
    st.markdown(f'<div class="section-header"><h4>📅 Piano Scenario con Modifiche Evidenziate</h4></div>', unsafe_allow_html=True)
    
    # Usa le date originali salvate nei metadata
    start_date = None
    if 'start_date' in metadata:
        start_date = metadata['start_date']
    elif 'period_desc' in metadata:
        # Estrai mese e anno dalla descrizione del periodo
        period_parts = metadata['period_desc'].split()
        if len(period_parts) >= 2:
            try:
                month_name = period_parts[0]
                year = int(period_parts[1])
                month = list(calendar.month_name)[1:].index(month_name) + 1
                start_date = datetime(year, month, 1)
            except:
                pass
    
    # Fallback se non riusciamo a estrarre la data
    if start_date is None:
        st.error("❌ Impossibile determinare le date del calendario originale")
        return
    
    # Genera le date labels corrette
    date_labels = [start_date + timedelta(days=i) for i in range(metadata['total_days'])]
    
    # Prepara dati tabella
    formatter = ScheduleFormatter(nurses, [d.strftime("%d/%m") for d in date_labels], f"Scenario - {metadata['period_desc']}")
    scenario_matrix = formatter._build_shift_matrix(scenario.plan)
    original_matrix = formatter._build_shift_matrix(original_plan)
    
    # Identifica weekend e modifiche
    weekend_columns = set()
    modified_cells = set()  # (nurse_idx, day_idx)
    columns = []
    
    for i, d in enumerate(date_labels):
        day_name = ITALIAN_WEEKDAYS[d.weekday()]
        col_name = f"{day_name} {d.day:02d}"
        columns.append(col_name)
        if d.weekday() in [5, 6]:  # Sabato o domenica
            weekend_columns.add(col_name)
    
    # Identifica celle modificate
    for nurse_idx in range(len(nurses)):
        for day_idx in range(metadata['total_days']):
            if scenario_matrix[nurse_idx][day_idx] != original_matrix[nurse_idx][day_idx]:
                modified_cells.add((nurse_idx, day_idx))
    
    # Crea DataFrame
    data_dict = {}
    
    # Colonne riepilogo
    contract_hours = [formatter._calculate_contract_hours_for_period(n.contracted_hours) for n in nurses]
    effective_hours = [row.count("M") * 8 + row.count("P") * 8 + row.count("N") * 8 for row in scenario_matrix]
    diff_hours = [eff - ctr for eff, ctr in zip(effective_hours, contract_hours)]
    
    data_dict["Ore Ctr"] = [f"{int(c)}h" for c in contract_hours]
    data_dict["Ore Eff"] = [f"{h}h" for h in effective_hours]
    data_dict["Diff"] = [f"{d:+.0f}h" for d in diff_hours]
    
    # Colonne turni
    for col, day_shifts in zip(columns, zip(*scenario_matrix)):
        data_dict[col] = list(day_shifts)
    
    df = pd.DataFrame(data_dict, index=[n.name for n in nurses])
    
    # Styling avanzato per weekend E modifiche
    def highlight_scenario_changes(x):
        styles = pd.DataFrame('', index=x.index, columns=x.columns)
        
        # Crea mapping colonne -> giorno
        day_columns = {}
        for day_idx, col_name in enumerate(columns):
            day_columns[col_name] = day_idx
        
        for col in x.columns:
            if col in weekend_columns:
                # Weekend: gestisce weekend + eventuali modifiche
                day_idx = day_columns.get(col, -1)
                for row_idx in range(len(x.index)):
                    if day_idx >= 0 and (row_idx, day_idx) in modified_cells:
                        # Modifica + Weekend: rosso scuro con testo bianco
                        styles[col].iloc[row_idx] = 'background-color: #8b0000; color: white; font-weight: bold;'
                    else:
                        # Solo Weekend: blu scuro come originale
                        styles[col].iloc[row_idx] = 'background-color: #1565c0; color: white'
            elif col in day_columns:
                # Colonne giorni (non weekend): gestisce solo modifiche
                day_idx = day_columns[col]
                for row_idx in range(len(x.index)):
                    if (row_idx, day_idx) in modified_cells:
                        # Solo modifica: rosso scuro con testo bianco
                        styles[col].iloc[row_idx] = 'background-color: #8b0000; color: white; font-weight: bold;'
        
        return styles
    
    styled_df = df.style.apply(highlight_scenario_changes, axis=None)
    
    # Tabella scenario senza stile verde scuro  
    st.dataframe(styled_df, use_container_width=True)
    
    # Legenda aggiornata
    st.caption("""
    **Legenda**: M=Mattino, P=Pomeriggio, N=Notte, S=Smonto, R=Riposo  
    🏖️ **Weekend** (blu scuro) | 🔥 **Modifiche** (rosso scuro) | 🔥🏖️ **Weekend Modificati** (rosso scuro)
    """)
    
    # Info modifiche
    if modified_cells:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("🔄 Celle Modificate", len(modified_cells))
        with col2:
            modified_nurses = len(set(nurse_idx for nurse_idx, _ in modified_cells))
            st.metric("👥 Infermieri Coinvolti", modified_nurses)


def apply_selected_scenario(scenario: Scenario, metadata: Dict):
    """Applica lo scenario selezionato come nuovo piano corrente."""
    
    try:
        # Aggiorna metadata
        new_metadata = metadata.copy()
        new_metadata['last_modification'] = datetime.now()
        new_metadata['modification_count'] = new_metadata.get('modification_count', 0) + 1
        
        # Salva nuovo piano
        save_current_plan(scenario.plan, new_metadata)
        
        # Reset stato modifiche
        st.session_state.generated_scenarios = []
        st.session_state.modification_mode = False
        
        st.success("✅ Scenario applicato con successo!")
        st.info("🔄 La pagina si ricaricherà per mostrare il piano aggiornato.")
        
        # Forza reload
        st.rerun()
        
    except Exception as e:
        st.error(f"❌ Errore nell'applicazione dello scenario: {e}")


def display_statistics(schedule: List[Dict], nurses):
    """Visualizza statistiche dettagliate del piano."""
    
    st.markdown('<div class="section-header"><h3>📊 Statistiche</h3></div>', unsafe_allow_html=True)
    
    # Prepara dati
    date_labels = [f"Day{i}" for i in range(len(schedule))]
    formatter = ScheduleFormatter(nurses, date_labels, "Stats")
    shift_matrix = formatter._build_shift_matrix(schedule)
    
    # Statistiche per infermiere
    stats_data = []
    for i, (nurse, row) in enumerate(zip(nurses, shift_matrix)):
        m = row.count("M")
        p = row.count("P") 
        n = row.count("N")
        s = row.count("S")
        r = row.count("R")
        total_shifts = m + p + n
        
        stats_data.append({
            "Infermiere": nurse.name,
            "Mattino": m,
            "Pomeriggio": p,
            "Notte": n,
            "Smonto": s,
            "Riposi": r,
            "Tot turni": total_shifts,
            "Ore lavorate": f"{total_shifts * 8}h",
            "Ore contratto": f"{nurse.contracted_hours}h"
        })
    
    stats_df = pd.DataFrame(stats_data)
    
    # Wrapper per stile verde scuro
    st.markdown('<div class="main-schedule-table">', unsafe_allow_html=True)
    st.dataframe(stats_df, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Riepilogo generale
    st.markdown("#### 📈 Riepilogo Generale")
    total_m = sum(row.count("M") for row in shift_matrix)
    total_p = sum(row.count("P") for row in shift_matrix) 
    total_n = sum(row.count("N") for row in shift_matrix)
    total_s = sum(row.count("S") for row in shift_matrix)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🌅 Turni Mattino", total_m)
    with col2:
        st.metric("🌞 Turni Pomeriggio", total_p)
    with col3:
        st.metric("🌙 Turni Notte", total_n)
    with col4:
        st.metric("🔄 Giorni Smonto", total_s)


def main():
    """Funzione principale dell'applicazione."""
    
    st.set_page_config(
        page_title="Sistema Turni Infermieristici",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🏥 Sistema Turni Infermieristici - Avanzato")
    
    # Inizializzazione
    init_session_state()
    setup_page_style()
    
    # Sidebar
    data_folder, month, year, month_name, max_time = render_sidebar()
    
    # Calcola periodo
    start_date, end_date, total_days, date_labels, start_weekday = calculate_period_info(month, year)
    period_desc = f"{month_name} {year}"
    
    # Info periodo nella sidebar
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**📅 Periodo selezionato:**")
    st.sidebar.markdown(f"{period_desc} ({total_days} giorni)")
    st.sidebar.markdown(f"Inizio: {ITALIAN_WEEKDAYS[start_weekday]} {start_date.strftime('%d/%m')}")
    
    # Controllo piano esistente
    if st.session_state.current_plan is not None:
        current_metadata = st.session_state.plan_metadata
        
        # Verifica se il periodo è cambiato
        if (current_metadata and 
            current_metadata.get('period_desc') == period_desc and
            current_metadata.get('total_days') == total_days):
            
            # Piano esistente valido
            st.info(f"📋 **Piano esistente trovato** per {period_desc}")
            
            # Carica dati per modifiche
            try:
                nurses = load_nurses(os.path.join(data_folder, "nurses.json"))
                hard_constraints = load_hard_constraints(os.path.join(data_folder, "hard_constraints.json"))
                soft_constraints = load_soft_constraints(os.path.join(data_folder, "soft_constraints.json"))
                
                # Visualizza piano attuale
                shift_matrix, df = display_schedule_table(st.session_state.current_plan, nurses, date_labels, current_metadata)
                
                # Interfaccia modifiche (sempre visibile)
                render_modification_interface(nurses, hard_constraints, soft_constraints, 
                                           st.session_state.current_plan, current_metadata, max_time)
                
                # Visualizza scenari se in modalità modifica
                if st.session_state.modification_mode and st.session_state.generated_scenarios:
                    display_scenarios(st.session_state.generated_scenarios, st.session_state.current_plan, 
                                    nurses, current_metadata)
                
                # Statistiche
                display_statistics(st.session_state.current_plan, nurses)
                
            except Exception as e:
                st.error(f"❌ Errore nel caricamento dati: {e}")
                st.session_state.current_plan = None
        
        else:
            # Periodo cambiato, reset piano
            st.session_state.current_plan = None
            st.session_state.plan_metadata = None
    
    # Genera nuovo piano se necessario
    if st.session_state.current_plan is None:
        st.markdown("### 🚀 Genera Nuovo Piano")
        
        if st.button("🔄 Genera Turni", type="primary"):
            result = generate_initial_plan(data_folder, total_days, start_weekday, max_time, period_desc, start_date)
            nurses, hard_constraints, soft_constraints, schedule = result
            
            if schedule:
                # Visualizza piano generato
                shift_matrix, df = display_schedule_table(schedule, nurses, date_labels, st.session_state.plan_metadata)
                
                # Statistiche
                display_statistics(schedule, nurses)
                
                st.success("🎉 Piano generato con successo! Ora puoi utilizzare le funzioni di modifica.")
        
        else:
            # Istruzioni iniziali
            with st.expander("ℹ️ Come utilizzare il sistema"):
                st.markdown("""
                ### 🏥 Sistema Avanzato di Turni Infermieristici
                
                #### 🎯 Funzionalità Principali:
                1. **Generazione Piano Iniziale** - Crea un piano ottimale rispettando tutti i vincoli
                2. **Modifiche Interattive** - Modifica singoli turni e genera scenari alternativi  
                3. **Analisi Impatto** - Visualizza l'effetto delle modifiche sul piano globale
                4. **Persistenza Stato** - Il piano rimane salvato tra le sessioni
                
                #### 🔄 Workflow:
                1. Seleziona mese/anno e clicca "Genera Turni"
                2. Esamina il piano generato e le statistiche
                3. Per modifiche: seleziona infermiere, giorno e nuovo turno
                4. Genera scenari alternativi e scegli il migliore
                5. Applica lo scenario per aggiornare il piano
                6. Ripeti per modifiche successive
                
                #### 📋 File Richiesti:
                - `nurses.json`: Elenco infermieri e ore contrattuali
                - `hard_constraints.json`: Vincoli obbligatori
                - `soft_constraints.json`: Preferenze e ottimizzazioni
                
                #### 🎭 Scenari Alternativi:
                Il sistema genera fino a 5 scenari diversi per ogni modifica:
                - **Minimale**: Cambia solo il necessario
                - **Scambio**: Cerca scambi con altri infermieri
                - **Locale**: Riorganizza nell'intorno temporale  
                - **Rilassato**: Più libertà di modifica
                - **Globale**: Ottimizzazione completa
                """)


if __name__ == "__main__":
    main()