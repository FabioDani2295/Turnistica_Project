"""
Shift History Management
========================
"""

import streamlit as st
import json
import os
from datetime import datetime


def init_shift_history():
    """Inizializza lo storico dei turni se non esiste"""
    if 'shift_history' not in st.session_state:
        st.session_state.shift_history = {}


def get_shift_key(year, month):
    """Genera la chiave per lo storico (formato: YYYY-MM)"""
    return f"{year}-{month:02d}"


def shift_exists(year, month):
    """Verifica se esiste già un turno per il mese-anno specificato"""
    init_shift_history()
    key = get_shift_key(year, month)
    return key in st.session_state.shift_history


def save_shift(year, month, period_desc, nurses, schedule, shift_matrix, stats, hard_constraints, soft_constraints):
    """Salva un turno nello storico"""
    init_shift_history()
    
    key = get_shift_key(year, month)
    
    st.session_state.shift_history[key] = {
        "period_desc": period_desc,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nurses": [{"name": n.name, "contracted_hours": n.contracted_hours} for n in nurses],
        "schedule": schedule,
        "shift_matrix": shift_matrix,
        "stats": stats,
        "constraints_used": {
            "hard": hard_constraints,
            "soft": soft_constraints
        }
    }


def get_shift(year, month):
    """Recupera un turno dallo storico"""
    init_shift_history()
    key = get_shift_key(year, month)
    return st.session_state.shift_history.get(key, None)


def get_all_shifts():
    """Recupera tutti i turni dallo storico"""
    init_shift_history()
    return st.session_state.shift_history


def get_shift_list():
    """Recupera lista dei turni ordinata per data (più recenti primi)"""
    init_shift_history()
    shifts = []
    
    for key, shift_data in st.session_state.shift_history.items():
        year, month = key.split('-')
        shifts.append({
            "key": key,
            "year": int(year),
            "month": int(month),
            "period_desc": shift_data["period_desc"],
            "created_at": shift_data["created_at"]
        })
    
    # Ordina per anno e mese (più recenti primi)
    shifts.sort(key=lambda x: (x["year"], x["month"]), reverse=True)
    return shifts


def delete_shift(year, month):
    """Elimina un turno dallo storico"""
    init_shift_history()
    key = get_shift_key(year, month)
    if key in st.session_state.shift_history:
        del st.session_state.shift_history[key]
        return True
    return False


def export_shift_history():
    """Esporta lo storico in formato JSON"""
    init_shift_history()
    return json.dumps(st.session_state.shift_history, indent=2, ensure_ascii=False)


def get_shift_stats():
    """Recupera statistiche generali dello storico"""
    init_shift_history()
    total_shifts = len(st.session_state.shift_history)
    
    if total_shifts == 0:
        return {
            "total_shifts": 0,
            "latest_shift": None,
            "total_nurses": 0
        }
    
    # Trova l'ultimo turno creato
    latest_key = None
    latest_date = None
    
    for key, shift_data in st.session_state.shift_history.items():
        created_at = datetime.strptime(shift_data["created_at"], "%Y-%m-%d %H:%M:%S")
        if latest_date is None or created_at > latest_date:
            latest_date = created_at
            latest_key = key
    
    # Conta infermieri unici
    all_nurses = set()
    for shift_data in st.session_state.shift_history.values():
        for nurse in shift_data["nurses"]:
            all_nurses.add(nurse["name"])
    
    return {
        "total_shifts": total_shifts,
        "latest_shift": st.session_state.shift_history[latest_key]["period_desc"] if latest_key else None,
        "total_nurses": len(all_nurses)
    }