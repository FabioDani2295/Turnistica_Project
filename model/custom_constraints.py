"""
Custom Constraints - Vincoli aggiuntivi
======================================
"""

from model.constraint_registry import registry
from utils.enums import ShiftType
from model.nurse import Nurse
from typing import List
from ortools.sat.python import cp_model


@registry.hard_constraint("nurse_absence")
def hc_nurse_absence(
        model: cp_model.CpModel,
        nurse_shift,
        nurses: List[Nurse],
        params,
        num_days: int,
        start_weekday: int = 0
):
    """
    Hard constraint: assenze programmate per infermieri specifici.
    """
    absences = params.get("absences", [])
    
    # Crea indice nome -> posizione
    nurse_name_to_idx = {nurse.name: i for i, nurse in enumerate(nurses)}
    
    for absence in absences:
        nurse_name = absence.get("nurse_name", "")
        start_day = absence.get("start_day", 0)
        end_day = absence.get("end_day", 0)
        
        # Verifica che l'infermiere esista
        if nurse_name not in nurse_name_to_idx:
            continue
            
        nurse_idx = nurse_name_to_idx[nurse_name]
        
        # Verifica che i giorni siano validi
        if start_day < 0 or end_day >= num_days or start_day > end_day:
            continue
        
        # Impedisce qualsiasi turno nei giorni di assenza
        for day in range(start_day, end_day + 1):
            for shift_type in ShiftType:
                model.Add(nurse_shift[nurse_idx, day, shift_type.value] == 0)


@registry.hard_constraint("predefined_shifts")
def hc_predefined_shifts(
        model: cp_model.CpModel,
        nurse_shift,
        nurses: List[Nurse],
        params,
        num_days: int,
        start_weekday: int = 0
):
    """
    Hard constraint: turni predefiniti per infermieri specifici.
    """
    predefined = params.get("predefined", [])
    
    # Crea indice nome -> posizione
    nurse_name_to_idx = {nurse.name: i for i, nurse in enumerate(nurses)}
    
    # Mappatura nomi turni a valori enum
    shift_type_mapping = {
        "MORNING": ShiftType.MORNING,
        "AFTERNOON": ShiftType.AFTERNOON, 
        "NIGHT": ShiftType.NIGHT,
        "SMONTO": ShiftType.SMONTO
    }
    
    for predef in predefined:
        nurse_name = predef.get("nurse_name", "")
        day = predef.get("day", 0)
        shift_type_name = predef.get("shift_type", "")
        
        # Verifica che l'infermiere esista
        if nurse_name not in nurse_name_to_idx:
            continue
            
        # Verifica che il tipo di turno sia valido
        if shift_type_name not in shift_type_mapping:
            continue
            
        nurse_idx = nurse_name_to_idx[nurse_name]
        shift_type = shift_type_mapping[shift_type_name]
        
        # Verifica che il giorno sia valido
        if day < 0 or day >= num_days:
            continue
        
        # Forza il turno specifico per questo infermiere in questo giorno
        model.Add(nurse_shift[nurse_idx, day, shift_type.value] == 1)
        
        # Impedisce altri turni nello stesso giorno
        for other_shift in ShiftType:
            if other_shift != shift_type:
                model.Add(nurse_shift[nurse_idx, day, other_shift.value] == 0)