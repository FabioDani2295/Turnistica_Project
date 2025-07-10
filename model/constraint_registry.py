"""
Registry: maps constraint 'type' strings to handler functions.

Hard constraint handler signature:
    handler(model, nurse_shift, nurses, params, num_days) -> None

Soft constraint handler signature:
    handler(model, nurse_shift, nurses, params, num_days, weight) -> List[SoftTerm]

A SoftTerm is a tiny dataclass holding an OR‑Tools linear expression and
its weight (penalty/bonus). This abstraction allows combining terms in
_scheduler_ without worrying about signs.

MODIFICATO: Aggiunti vincoli per no PM->M, max notti mensili, weekend liberi, bilanciamento turni.
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
    """Soft constraint term: OR-Tools expression + weight"""
    expr: cp_model.LinearExpr
    weight: int  # positive=bonus, negative=penalty


class ConstraintRegistry:
    def __init__(self):
        self.hard: Dict[str, Callable] = {}
        self.soft: Dict[str, Callable] = {}

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

# -----------------------------
# HARD CONSTRAINTS
# -----------------------------

@registry.hard_constraint("coverage_minimum")
def hc_coverage_min(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Numero minimo di infermieri per turno"""
    required = {
        ShiftType.MORNING: params.get("morning", 2),
        ShiftType.AFTERNOON: params.get("afternoon", 2),
        ShiftType.NIGHT: params.get("night", 1),
    }
    for d in range(num_days):
        for shift, req in required.items():
            model.Add(
                sum(nurse_shift[i, d, shift.value] for i in range(len(nurses))) >= req
            )

@registry.hard_constraint("incompatibility")
def hc_incompatibility(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Coppie di infermieri non possono lavorare lo stesso turno"""
    name_to_id = {n.name: i for i, n in enumerate(nurses)}
    for n1, n2 in params.get("pairs", []):
        i1, i2 = name_to_id[n1], name_to_id[n2]
        for d in range(num_days):
            for shift in ShiftType:
                model.Add(
                    nurse_shift[i1, d, shift.value] + nurse_shift[i2, d, shift.value] <= 1
                )

@registry.hard_constraint("max_consecutive_nights")
def hc_max_consec_nights(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Limita il numero di notti consecutive"""
    max_n = int(params.get("max", 3))
    for i in range(len(nurses)):
        for d in range(num_days - max_n):
            model.Add(
                sum(
                    nurse_shift[i, d + k, ShiftType.NIGHT.value]
                    for k in range(max_n + 1)
                ) <= max_n
            )

@registry.hard_constraint("max_consecutive_work_days")
def hc_max_consec_days(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Limita i giorni lavorativi consecutivi"""
    max_d = int(params.get("max_days", 6))
    for i in range(len(nurses)):
        for d in range(num_days - max_d):
            model.Add(
                sum(
                    nurse_shift[i, d + k, s.value]
                    for k in range(max_d + 1)
                    for s in ShiftType
                ) <= max_d
            )

@registry.hard_constraint("min_rest_hours")
def hc_min_rest(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Riposo minimo tra notte e mattina successiva"""
    hours = int(params.get("hours", 11))
    if hours < 11:
        return
    for i in range(len(nurses)):
        for d in range(num_days - 1):
            model.Add(
                nurse_shift[i, d, ShiftType.NIGHT.value] +
                nurse_shift[i, d + 1, ShiftType.MORNING.value] <= 1
            )

@registry.hard_constraint("no_pm_to_m_transition")
def hc_no_pm_to_m_transition(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Impedisce Pomeriggio->Mattina giorno successivo"""
    for i in range(len(nurses)):
        for d in range(num_days - 1):
            p = nurse_shift[i, d, ShiftType.AFTERNOON.value]
            m = nurse_shift[i, d + 1, ShiftType.MORNING.value]
            model.Add(p + m <= 1)

@registry.hard_constraint("no_afternoon_after_morning")
def hc_no_afternoon_after_morning(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Non permette Mattina+Pomeriggio nello stesso giorno"""
    for i in range(len(nurses)):
        for d in range(num_days):
            model.Add(
                nurse_shift[i, d, ShiftType.MORNING.value] +
                nurse_shift[i, d, ShiftType.AFTERNOON.value] <= 1
            )

@registry.hard_constraint("mandatory_smonto_after_night")
def hc_mandatory_smonto_after_night(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Assicura smonto dopo ogni notte"""
    for i in range(len(nurses)):
        for d in range(num_days - 1):
            model.Add(
                nurse_shift[i, d, ShiftType.NIGHT.value] <=
                nurse_shift[i, d + 1, ShiftType.SMONTO.value]
            )

@registry.hard_constraint("mandatory_rest_after_smonto")
def hc_mandatory_rest_after_smonto(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Riposo obbligatorio dopo smonto"""
    for i in range(len(nurses)):
        for d in range(num_days - 1):
            for s in ShiftType:
                model.Add(
                    nurse_shift[i, d, ShiftType.SMONTO.value] +
                    nurse_shift[i, d + 1, s.value] <= 1
                )

@registry.hard_constraint("shift_balance_morning_afternoon")
def hc_shift_balance_morning_afternoon(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Bilanciamento M vs P con discrepanza massima"""
    max_disc = params.get("max_discrepancy", 0.65)
    factor = int(max_disc * 100)
    inv = 100 - factor
    for i in range(len(nurses)):
        m_cnt = sum(nurse_shift[i, d, ShiftType.MORNING.value] for d in range(num_days))
        p_cnt = sum(nurse_shift[i, d, ShiftType.AFTERNOON.value] for d in range(num_days))
        model.Add(m_cnt * inv <= p_cnt * factor)
        model.Add(p_cnt * inv <= m_cnt * factor)

@registry.hard_constraint("workload_balance_hard")
def hc_workload_balance_hard(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Bilanciamento HARD del carico di lavoro"""
    tol = params.get("tolerance", 0.25)
    daily = params.get("daily_shifts", 5)

    # FIX: Per i mesi usa direttamente le ore mensili
    if num_days == 7:
        factor = 1 / 4  # Settimana: ore mensili / 4
    elif num_days >= 28 and num_days <= 31:
        factor = 1.0  # Mese: usa ore mensili direttamente
    else:
        factor = num_days / 30.0  # Periodo custom

    total_h = sum(n.contracted_hours * factor for n in nurses)
    req = daily * num_days

    for i, n in enumerate(nurses):
        h = n.contracted_hours * factor
        ideal = (h / total_h) * req if total_h > 0 else 0
        min_s = max(0, int(ideal * (1 - tol)))
        max_s = min(int(ideal * (1 + tol)) + 1, int(h / 8))

        total_w = sum(
            nurse_shift[i, d, s.value]
            for d in range(num_days)
            for s in [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]
        )
        model.Add(total_w >= min_s)
        model.Add(total_w <= max_s)

@registry.hard_constraint("max_nights_per_month")
def hc_max_nights_per_month(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Massimo turni notturni nel periodo"""
    max_m = params.get("max_monthly", 4)
    if num_days == 7:
        lim = min(2, max_m // 4 + 1)
    elif num_days >= 28:
        lim = max_m
    else:
        lim = max(1, int(max_m * num_days / 30.0))
    for i in range(len(nurses)):
        tot_n = sum(nurse_shift[i, d, ShiftType.NIGHT.value] for d in range(num_days))
        model.Add(tot_n <= lim)

@registry.hard_constraint("weekend_rest_monthly")
def hc_weekend_rest_monthly(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int
):
    """Almeno free_weekends weekend liberi (sab+dom)"""
    free_req = int(params.get("free_weekends", 2))
    if num_days < 7:
        return
    weekends = [(d, d+1) for d in range(num_days-1) if d % 7 == 5]
    for i in range(len(nurses)):
        flags: List[cp_model.BoolVar] = []
        for w, (sat, sun) in enumerate(weekends):
            sum_sat = sum(nurse_shift[i, sat, s.value] for s in ShiftType)
            sum_sun = sum(nurse_shift[i, sun, s.value] for s in ShiftType)
            model.Add(sum_sat == sum_sun)
            free_w = model.NewBoolVar(f"n{i}_w{w}_free")
            model.Add(sum_sat == 0).OnlyEnforceIf(free_w)
            model.Add(sum_sat > 0).OnlyEnforceIf(free_w.Not())
            flags.append(free_w)
        model.Add(sum(flags) >= free_req)

# -----------------------------
# SOFT CONSTRAINTS
# -----------------------------

@registry.soft_constraint("prefer_shift")
def sc_prefer_shift(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int,
    weight: int
) -> List[SoftTerm]:
    idx = {n.name: i for i, n in enumerate(nurses)}[params["nurse"]]
    stype = ShiftType(params["shift"]).value
    return [SoftTerm(nurse_shift[idx, d, stype], weight) for d in range(num_days)]


"""
Aggiungi questo codice al file model/constraint_registry.py
----------------------------------------------------------
Soft constraint semplice per weekend liberi.
"""


@registry.soft_constraint("weekend_rest")
def sc_weekend_rest(
        model: cp_model.CpModel,
        nurse_shift,
        nurses: List[Nurse],
        params,
        num_days: int,
        weight: int
) -> List[SoftTerm]:
    """
    Soft constraint: premia ogni infermiere che ha almeno una coppia
    di giorni consecutivi liberi (potenziale weekend).

    Questo approccio è agnostico rispetto al giorno della settimana iniziale.
    """
    terms = []

    for i in range(len(nurses)):
        # Per ogni infermiere, trova tutte le coppie di giorni consecutivi liberi
        free_pairs = []

        # Controlla ogni coppia di giorni consecutivi
        for d in range(num_days - 1):
            # Variabile: questa coppia di giorni è libera?
            pair_free = model.NewBoolVar(f"nurse{i}_days{d}_{d + 1}_free")

            # La coppia è libera se non ci sono turni in nessuno dei due giorni
            day1_shifts = sum(nurse_shift[i, d, s.value] for s in ShiftType)
            day2_shifts = sum(nurse_shift[i, d + 1, s.value] for s in ShiftType)

            model.Add(day1_shifts + day2_shifts == 0).OnlyEnforceIf(pair_free)
            model.Add(day1_shifts + day2_shifts > 0).OnlyEnforceIf(pair_free.Not())

            free_pairs.append(pair_free)

        # Ha almeno una coppia di giorni liberi?
        if free_pairs:
            has_free_pair = model.NewBoolVar(f"nurse{i}_has_free_pair")
            model.AddBoolOr(free_pairs).OnlyEnforceIf(has_free_pair)
            model.AddBoolAnd([p.Not() for p in free_pairs]).OnlyEnforceIf(has_free_pair.Not())

            # Premio per avere almeno una coppia libera
            terms.append(SoftTerm(has_free_pair, weight))

    return terms

@registry.soft_constraint("avoid_shift")
def sc_avoid_shift(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int,
    weight: int
) -> List[SoftTerm]:
    idx = {n.name: i for i, n in enumerate(nurses)}[params["nurse"]]
    stype = ShiftType(params["shift"]).value
    return [SoftTerm(nurse_shift[idx, d, stype], -abs(weight)) for d in range(num_days)]

@registry.soft_constraint("equity")
def sc_equity(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int,
    weight: int
) -> List[SoftTerm]:
    # Minimizza la varianza nel numero di turni lavorativi (M,P,N)
    max_shifts = num_days * 3
    totals: List[cp_model.IntVar] = []
    for i in range(len(nurses)):
        t = model.NewIntVar(0, max_shifts, f"tot_{i}")
        model.Add(
            t == sum(
                nurse_shift[i, d, s.value]
                for d in range(num_days)
                for s in [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]
            )
        )
        totals.append(t)
    avg = model.NewIntVar(0, max_shifts, "avg")
    model.AddDivisionEquality(avg, sum(totals), len(nurses))
    terms: List[SoftTerm] = []
    for i, t in enumerate(totals):
        diff = model.NewIntVar(0, max_shifts, f"diff_{i}")
        model.AddAbsEquality(diff, t - avg)
        terms.append(SoftTerm(diff, -abs(weight)))
    return terms

@registry.soft_constraint("workload_balance")
def sc_workload_balance(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int,
    weight: int
) -> List[SoftTerm]:
    # Premi total shifts in base alle ore contrattuali
    factor = (1/4) if num_days == 7 else (num_days / 30.0)
    total_hours = sum(n.contracted_hours * factor for n in nurses)
    terms: List[SoftTerm] = []
    for i, n in enumerate(nurses):
        nurse_hours = n.contracted_hours * factor
        proportion = nurse_hours / total_hours if total_hours else 0
        total_var = model.NewIntVar(0, num_days * 3, f"wb_{i}")
        model.Add(
            total_var == sum(
                nurse_shift[i, d, s.value]
                for d in range(num_days)
                for s in [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]
            )
        )
        bonus = int(weight * proportion)
        terms.append(SoftTerm(total_var, bonus))
    return terms
