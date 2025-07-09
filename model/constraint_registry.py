"""Registry: maps constraint 'type' strings to handler functions.

Hard constraint handler signature:
    handler(model, nurse_shift, nurses, params, num_days) -> None

Soft constraint handler signature:
    handler(model, nurse_shift, nurses, params, num_days, weight) -> List[SoftTerm]

A SoftTerm is a tiny dataclass holding an OR‑Tools linear expression and
its weight (penalty/bonus). This abstraction allows combining terms in
_scheduler_ without worrying about signs.

MODIFICATO: Aggiunti vincoli per max notti mensili, weekend liberi, bilanciamento turni.
CORRETTO: Gestione corretta di SMONTO in tutti i vincoli.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Callable, List

from ortools.sat.python import cp_model

from utils.enums import ShiftType
from model.nurse import Nurse


@dataclass
class SoftTerm:
    expr: cp_model.LinearExpr
    weight: int  # positive for bonus, negative for penalty


class ConstraintRegistry:
    def __init__(self):
        self.hard: Dict[str, Callable] = {}
        self.soft: Dict[str, Callable] = {}

    # decorators --------------------------------------------------------
    def hard_constraint(self, name: str):
        def decorator(fn):
            self.hard[name] = fn
            return fn

        return decorator

    def soft_constraint(self, name: str):
        def decorator(fn):
            self.soft[name] = fn
            return fn

        return decorator


registry = ConstraintRegistry()

# ---------------------------------------------------------------------
#   HARD CONSTRAINT IMPLEMENTATIONS
# ---------------------------------------------------------------------


@registry.hard_constraint("incompatibility")
def hc_incompatibility(model, nurse_shift, nurses: List[Nurse], params, num_days):
    pairs = params.get("pairs", [])
    name_to_id = {n.name: i for i, n in enumerate(nurses)}
    for n1, n2 in pairs:
        id1, id2 = name_to_id[n1], name_to_id[n2]
        for d in range(num_days):
            for s in ShiftType:
                model.Add(nurse_shift[id1, d, s.value] + nurse_shift[id2, d, s.value] <= 1)


@registry.hard_constraint("max_consecutive_nights")
def hc_max_consec_nights(model, nurse_shift, nurses: List[Nurse], params, num_days):
    max_n = int(params.get("max", 3))
    for n_idx in range(len(nurses)):
        for d in range(num_days - max_n):
            model.Add(
                sum(
                    nurse_shift[n_idx, d + offset, ShiftType.NIGHT.value]
                    for offset in range(max_n + 1)
                )
                <= max_n
            )


@registry.hard_constraint("max_consecutive_work_days")
def hc_max_consec_days(model, nurse_shift, nurses: List[Nurse], params, num_days):
    max_days = int(params.get("max_days", 6))
    for n_idx in range(len(nurses)):
        for d in range(num_days - max_days):
            # CORRETTO: include tutti i tipi di turno ma gestisce correttamente il range
            if d + max_days < num_days:  # Controllo extra per sicurezza
                model.Add(
                    sum(
                        nurse_shift[n_idx, d + offset, s.value]
                        for offset in range(max_days + 1)
                        for s in ShiftType
                    )
                    <= max_days
                )


@registry.hard_constraint("min_rest_hours")
def hc_min_rest(model, nurse_shift, nurses: List[Nurse], params, num_days):
    # For a daily model, min_rest 11h ≈ forbid Night->Morning pattern.
    hours = int(params.get("hours", 11))
    if hours < 11:
        return  # not modeled at daily granularity
    for n_idx in range(len(nurses)):
        for d in range(num_days - 1):
            model.Add(
                nurse_shift[n_idx, d, ShiftType.NIGHT.value]
                + nurse_shift[n_idx, d + 1, ShiftType.MORNING.value]
                <= 1
            )


@registry.hard_constraint("coverage_minimum")
def hc_coverage_min(model, nurse_shift, nurses: List[Nurse], params, num_days):
    required = {
        ShiftType.MORNING: params.get("morning", 2),
        ShiftType.AFTERNOON: params.get("afternoon", 2),
        ShiftType.NIGHT: params.get("night", 1),
        ShiftType.SMONTO: params.get("smonto", 0),  # AGGIUNTO: default 0 per smonto
    }
    for d in range(num_days):
        for shift in ShiftType:
            if shift == ShiftType.SMONTO:  # Lo smonto non ha requisiti di copertura minima
                continue
            model.Add(
                sum(
                    nurse_shift[n_idx, d, shift.value]
                    for n_idx in range(len(nurses))
                )
                >= required[shift]
            )


@registry.hard_constraint("workload_balance_hard")
def hc_workload_balance(model, nurse_shift, nurses: List[Nurse], params, num_days):
    """
    Bilanciamento HARD del carico di lavoro.
    MODIFICATO: contract_hours ora sono mensili, divise per 4 per settimane.
    CORRETTO: gestisce correttamente SMONTO che non conta come turno lavorativo.
    """
    tolerance = params.get("tolerance", 0.25)  # ±25% di default

    # Calcola turni totali necessari
    if num_days == 7:
        # Settimana: ore mensili / 4
        total_hours = sum(nurse.contracted_hours / 4.0 for nurse in nurses)
    else:
        # Mese o altro periodo
        total_hours = sum(nurse.contracted_hours * (num_days / 30.0) for nurse in nurses)

    # Stima turni totali (dalle coverage requirements) - SOLO turni lavorativi
    daily_shifts = params.get("daily_shifts", 5)  # Default: 2M + 2P + 1N
    total_shifts_needed = daily_shifts * num_days

    for n_idx, nurse in enumerate(nurses):
        # Calcola turni ideali per questo infermiere
        if num_days == 7:
            nurse_hours_period = nurse.contracted_hours / 4.0
        else:
            nurse_hours_period = nurse.contracted_hours * (num_days / 30.0)

        contract_ratio = nurse_hours_period / total_hours
        ideal_shifts = contract_ratio * total_shifts_needed

        # Range con tolleranza
        min_shifts = max(0, int(ideal_shifts * (1 - tolerance)))
        max_shifts = min(num_days, int(ideal_shifts * (1 + tolerance)) + 1)

        # Limita ulteriormente basandosi sul contratto (8 ore per turno)
        contract_max_shifts = int(nurse_hours_period / 8.0)
        max_shifts = min(max_shifts, contract_max_shifts)

        # Vincolo HARD: range obbligatorio - SOLO sui turni lavorativi (M, P, N)
        # IMPORTANTE: SMONTO non conta!
        total_nurse_shifts = sum(
            nurse_shift[n_idx, d, s.value]
            for d in range(num_days)
            for s in [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]
        )

        model.Add(total_nurse_shifts >= min_shifts)
        model.Add(total_nurse_shifts <= max_shifts)


# NUOVI VINCOLI AGGIUNTI

@registry.hard_constraint("max_nights_per_month")
def hc_max_nights_per_month(model, nurse_shift, nurses: List[Nurse], params, num_days):
    """
    Vincolo: massimo N turni notturni per periodo (scalato per settimane).
    Default: max 4 notti al mese, 1 a settimana.
    """
    max_nights_monthly = params.get("max_monthly", 4)

    # Scala per periodo
    if num_days == 7:
        # Settimana: max 1-2 notti
        max_nights_period = min(2, max_nights_monthly // 4 + 1)
    elif num_days >= 28:
        # Mese: usa il limite mensile
        max_nights_period = max_nights_monthly
    else:
        # Periodo custom: scala proporzionalmente
        max_nights_period = max(1, int(max_nights_monthly * num_days / 30.0))

    for n_idx in range(len(nurses)):
        total_nights = sum(
            nurse_shift[n_idx, d, ShiftType.NIGHT.value]
            for d in range(num_days)
        )
        model.Add(total_nights <= max_nights_period)


@registry.hard_constraint("weekend_rest_monthly")
def hc_weekend_rest_monthly(model, nurse_shift, nurses: List[Nurse], params, num_days):
    """
    Vincolo: garantire 1-2 weekend liberi al mese per infermiere.
    Weekend = sabato (5) e domenica (6).
    """
    min_free_weekends = params.get("min_weekends", 1)

    if num_days < 7:
        return  # Non applicabile per periodi troppo corti

    # Trova tutti i weekend nel periodo
    weekends = []
    for d in range(num_days):
        day_of_week = d % 7  # Assumendo che il giorno 0 sia lunedì
        if day_of_week == 5:  # Sabato
            # Weekend = sabato e domenica consecutive
            if d + 1 < num_days:  # C'è anche domenica
                weekends.append((d, d + 1))
            else:
                weekends.append((d,))  # Solo sabato

    if not weekends:
        return  # Nessun weekend nel periodo

    for n_idx in range(len(nurses)):
        # Variabile binaria per ogni weekend libero
        free_weekends = []

        for weekend_idx, weekend in enumerate(weekends):
            # Weekend libero = nessun turno né sabato né domenica
            weekend_free = model.NewBoolVar(f"weekend_free_{n_idx}_{weekend_idx}")

            # Se weekend_free = 1, allora nessun turno nei giorni del weekend
            for day in weekend:
                for shift in ShiftType:
                    model.Add(
                        nurse_shift[n_idx, day, shift.value] + weekend_free <= 1
                    )

            free_weekends.append(weekend_free)

        # Vincolo: almeno min_free_weekends weekend liberi
        if free_weekends:
            # Scala per periodo
            if num_days == 7:
                required_free = 1  # Almeno 1 weekend libero a settimana (se presente)
            elif num_days >= 28:
                required_free = min_free_weekends  # Target mensile
            else:
                required_free = max(1, len(weekends) // 2)  # Almeno metà dei weekend

            model.Add(sum(free_weekends) >= min(required_free, len(weekends)))


@registry.hard_constraint("shift_balance_morning_afternoon")
def hc_shift_balance_morning_afternoon(model, nurse_shift, nurses: List[Nurse], params, num_days):
    """
    Vincolo: bilanciamento turni mattina/pomeriggio per ogni infermiere.
    Massima discrepanza 65%-35% (o parametrizzabile).
    """
    max_discrepancy = params.get("max_discrepancy", 0.65)  # 65% default

    for n_idx in range(len(nurses)):
        # Conta turni mattina e pomeriggio
        morning_shifts = sum(
            nurse_shift[n_idx, d, ShiftType.MORNING.value]
            for d in range(num_days)
        )
        afternoon_shifts = sum(
            nurse_shift[n_idx, d, ShiftType.AFTERNOON.value]
            for d in range(num_days)
        )

        # Per evitare decimali, moltiplichiamo per 100
        discrepancy_factor = int(max_discrepancy * 100)  # 65
        balance_factor = 100 - discrepancy_factor  # 35

        # morning_shifts * 35 <= afternoon_shifts * 65
        # afternoon_shifts * 35 <= morning_shifts * 65
        model.Add(morning_shifts * balance_factor <= afternoon_shifts * discrepancy_factor)
        model.Add(afternoon_shifts * balance_factor <= morning_shifts * discrepancy_factor)


@registry.hard_constraint("mandatory_smonto_after_night")
def hc_mandatory_smonto_after_night(model, nurse_shift, nurses: List[Nurse], params, num_days):
    """
    Vincolo obbligatorio: dopo ogni turno notturno deve seguire uno smonto.
    """
    for n_idx in range(len(nurses)):
        for d in range(num_days - 1):  # Non ultimo giorno
            # Se fa notte il giorno d, DEVE fare smonto il giorno d+1
            model.Add(
                nurse_shift[n_idx, d, ShiftType.NIGHT.value] <=
                nurse_shift[n_idx, d + 1, ShiftType.SMONTO.value]
            )


@registry.hard_constraint("mandatory_rest_after_smonto")
def hc_mandatory_rest_after_smonto(model, nurse_shift, nurses: List[Nurse], params, num_days):
    """
    Vincolo obbligatorio: dopo lo smonto deve seguire riposo (nessun turno).
    """
    for n_idx in range(len(nurses)):
        for d in range(num_days - 1):  # Non ultimo giorno
            # Se fa smonto il giorno d, NON può fare nessun turno il giorno d+1
            for s in ShiftType:
                model.Add(
                    nurse_shift[n_idx, d, ShiftType.SMONTO.value] +
                    nurse_shift[n_idx, d + 1, s.value] <= 1
                )


@registry.hard_constraint("no_afternoon_after_morning")
def hc_no_afternoon_after_morning(model, nurse_shift, nurses: List[Nurse], params, num_days):
    """
    Vincolo: non si può fare pomeriggio dopo mattina nello stesso giorno.
    """
    for n_idx in range(len(nurses)):
        for d in range(num_days):
            # Non può fare sia mattina che pomeriggio lo stesso giorno
            model.Add(
                nurse_shift[n_idx, d, ShiftType.MORNING.value] +
                nurse_shift[n_idx, d, ShiftType.AFTERNOON.value] <= 1
            )


# ---------------------------------------------------------------------
#   SOFT CONSTRAINT IMPLEMENTATIONS
# ---------------------------------------------------------------------


@registry.soft_constraint("prefer_shift")
def sc_prefer_shift(model, nurse_shift, nurses, params, num_days, weight):
    nurse_name = params["nurse"]
    shift = ShiftType(params["shift"])
    idx = {n.name: i for i, n in enumerate(nurses)}[nurse_name]
    terms = [
        SoftTerm(nurse_shift[idx, d, shift.value], weight) for d in range(num_days)
    ]
    return terms


@registry.soft_constraint("avoid_shift")
def sc_avoid_shift(model, nurse_shift, nurses, params, num_days, weight):
    nurse_name = params["nurse"]
    shift = ShiftType(params["shift"])
    idx = {n.name: i for i, n in enumerate(nurses)}[nurse_name]
    # Penalty term: +1 if forbidden shift worked
    terms = [
        SoftTerm(nurse_shift[idx, d, shift.value], -abs(weight)) for d in range(num_days)
    ]
    return terms


@registry.soft_constraint("equity")
def sc_equity(model, nurse_shift, nurses, params, num_days, weight):
    """
    Vincolo di equità: minimizza la varianza nel numero di turni.
    Versione corretta che gestisce correttamente i range delle variabili.
    CORRETTO: conta solo turni lavorativi (M, P, N), non SMONTO.
    """
    total = []
    max_possible_shifts = num_days * 3  # Solo M, P, N (non SMONTO)

    for n_idx in range(len(nurses)):
        t = model.NewIntVar(0, max_possible_shifts, f"tot_{n_idx}")
        model.Add(
            t == sum(
                nurse_shift[n_idx, d, s.value]
                for d in range(num_days)
                for s in [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]  # Solo turni lavorativi
            )
        )
        total.append(t)

    # Calcola media con range corretto
    avg = model.NewIntVar(0, max_possible_shifts, "avg")
    model.AddDivisionEquality(avg, sum(total), len(nurses))

    terms = []
    for i, t in enumerate(total):
        # Variabile per differenza assoluta
        diff = model.NewIntVar(0, max_possible_shifts, f"diff_{i}")
        model.AddAbsEquality(diff, t - avg)
        terms.append(SoftTerm(diff, -abs(weight)))  # Penalizza squilibrio

    return terms


@registry.soft_constraint("workload_balance")
def sc_workload_balance(model, nurse_shift, nurses, params, num_days, weight):
    """
    Bilanciamento flessibile del carico di lavoro.
    MODIFICATO: contracted_hours ora sono mensili.
    CORRETTO: conta solo turni lavorativi (M, P, N), non SMONTO.
    """
    terms: List[SoftTerm] = []

    # Calcola il peso relativo di ogni infermiere (basato su ore mensili)
    if num_days == 7:
        # Settimana: usa ore settimanali (mensili / 4)
        total_contract_hours = sum(nurse.contracted_hours / 4.0 for nurse in nurses)
        nurse_weights = [nurse.contracted_hours / 4.0 for nurse in nurses]
    else:
        # Mese o altro: scala proporzionalmente
        period_factor = num_days / 30.0
        total_contract_hours = sum(nurse.contracted_hours * period_factor for nurse in nurses)
        nurse_weights = [nurse.contracted_hours * period_factor for nurse in nurses]

    for n_idx, nurse in enumerate(nurses):
        # Peso proporzionale al contratto (0.0 - 1.0)
        contract_weight = nurse_weights[n_idx] / total_contract_hours

        # Calcola turni effettivi per questo infermiere (solo lavorativi)
        total_shifts = model.NewIntVar(0, num_days * 3, f"shifts_{n_idx}")
        model.Add(
            total_shifts == sum(
                nurse_shift[n_idx, d, s.value]
                for d in range(num_days)
                for s in [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]  # Solo turni lavorativi
            )
        )

        # Premia in base al peso contrattuale
        # Infermieri con più ore dovrebbero fare più turni
        bonus_weight = int(weight * contract_weight * 10)  # Scala per OR-Tools
        terms.append(SoftTerm(total_shifts, bonus_weight))

    return terms