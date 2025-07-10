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
        num_days: int,
        start_weekday: int = 0  # NUOVO parametro
):
    """
    Hard constraint: almeno free_weekends weekend liberi veri (sab+dom).
    Ora usa il calendario reale per identificare i weekend.
    """
    free_req = int(params.get("free_weekends", 2))

    # Trova weekend veri
    weekend_pairs = []
    for day in range(num_days - 1):
        weekday = (start_weekday + day) % 7
        next_weekday = (start_weekday + day + 1) % 7

        if weekday == 5 and next_weekday == 6:  # Sabato + Domenica
            weekend_pairs.append((day, day + 1))

    if len(weekend_pairs) < free_req:
        # Non ci sono abbastanza weekend nel periodo per soddisfare il vincolo
        return

    for i in range(len(nurses)):
        free_weekend_flags = []

        for w_idx, (saturday, sunday) in enumerate(weekend_pairs):
            # Variabile: questo weekend è libero?
            weekend_free = model.NewBoolVar(f"n{i}_w{w_idx}_free")

            # Conta turni nel weekend
            saturday_shifts = sum(nurse_shift[i, saturday, s.value] for s in ShiftType)
            sunday_shifts = sum(nurse_shift[i, sunday, s.value] for s in ShiftType)
            total_shifts = saturday_shifts + sunday_shifts

            # Weekend libero solo se nessun turno
            model.Add(total_shifts == 0).OnlyEnforceIf(weekend_free)
            model.Add(total_shifts > 0).OnlyEnforceIf(weekend_free.Not())

            free_weekend_flags.append(weekend_free)

        # Almeno free_req weekend liberi
        if free_weekend_flags:
            model.Add(sum(free_weekend_flags) >= free_req)

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
        weight: int,
        start_weekday: int = 0
) -> List[SoftTerm]:
    """
    Soft constraint EQUO per weekend liberi:
    1. PRIORITÀ ALTA: Ogni infermiere ha almeno 1 weekend libero
    2. PRIORITÀ MEDIA: Chi può, arriva a 2 weekend liberi
    3. BONUS BASSO: Chi può, arriva a 3+ weekend liberi

    Questo evita che alcuni abbiano 2 weekend e altri zero.
    """
    terms = []

    # Trova tutti i weekend veri nel periodo
    weekend_pairs = []
    for day in range(num_days - 1):
        weekday = (start_weekday + day) % 7
        next_weekday = (start_weekday + day + 1) % 7

        if weekday == 5 and next_weekday == 6:
            weekend_pairs.append((day, day + 1))

    if not weekend_pairs:
        return terms

    for i in range(len(nurses)):
        # Lista di variabili boolean: ogni weekend è libero?
        free_weekends = []

        for weekend_idx, (saturday, sunday) in enumerate(weekend_pairs):
            weekend_free = model.NewBoolVar(f"nurse{i}_weekend{weekend_idx}_free")

            # Conta turni nel weekend
            saturday_shifts = sum(nurse_shift[i, saturday, s.value] for s in ShiftType)
            sunday_shifts = sum(nurse_shift[i, sunday, s.value] for s in ShiftType)
            total_weekend_shifts = saturday_shifts + sunday_shifts

            # Il weekend è libero solo se non ci sono turni
            model.Add(total_weekend_shifts == 0).OnlyEnforceIf(weekend_free)
            model.Add(total_weekend_shifts > 0).OnlyEnforceIf(weekend_free.Not())

            free_weekends.append(weekend_free)

        if not free_weekends:
            continue

        # STRATEGIA EQUA: Pesi decrescenti per incentivare distribuzione equa

        # 1. PRIORITÀ MASSIMA: Almeno 1 weekend libero (peso x3)
        if len(weekend_pairs) >= 1:
            has_1_free = model.NewBoolVar(f"nurse{i}_has_1_weekend")
            model.Add(sum(free_weekends) >= 1).OnlyEnforceIf(has_1_free)
            model.Add(sum(free_weekends) == 0).OnlyEnforceIf(has_1_free.Not())
            terms.append(SoftTerm(has_1_free, weight * 3))  # PESO TRIPLICATO

        # 2. PRIORITÀ MEDIA: Secondo weekend libero (peso normale)
        if len(weekend_pairs) >= 2:
            has_2_free = model.NewBoolVar(f"nurse{i}_has_2_weekends")
            model.Add(sum(free_weekends) >= 2).OnlyEnforceIf(has_2_free)
            model.Add(sum(free_weekends) <= 1).OnlyEnforceIf(has_2_free.Not())
            terms.append(SoftTerm(has_2_free, weight))  # PESO NORMALE

        # 3. BONUS BASSO: Terzo weekend libero (peso ridotto)
        if len(weekend_pairs) >= 3:
            has_3_free = model.NewBoolVar(f"nurse{i}_has_3_weekends")
            model.Add(sum(free_weekends) >= 3).OnlyEnforceIf(has_3_free)
            model.Add(sum(free_weekends) <= 2).OnlyEnforceIf(has_3_free.Not())
            terms.append(SoftTerm(has_3_free, weight // 3))  # PESO RIDOTTO

        # 4. EXTRA: Quarto weekend se disponibile (bonus minimo)
        if len(weekend_pairs) >= 4:
            has_4_free = model.NewBoolVar(f"nurse{i}_has_4_weekends")
            model.Add(sum(free_weekends) >= 4).OnlyEnforceIf(has_4_free)
            model.Add(sum(free_weekends) <= 3).OnlyEnforceIf(has_4_free.Not())
            terms.append(SoftTerm(has_4_free, weight // 6))  # PESO MINIMO

    return terms

@registry.soft_constraint("shift_blocks")
def sc_shift_blocks(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int,
    weight: int,
    start_weekday: int = 0
) -> List[SoftTerm]:
    """
    Soft constraint: premia la formazione di blocchi consecutivi di turni uguali.
    
    Esempi preferiti:
    - 3 mattine consecutive + riposo + 2 notti + smonto + riposo
    - 2 pomeriggi + riposo + 3 mattine + riposo
    
    Parametri:
    - min_block_size: dimensione minima blocco per ottenere premio (default 2)
    - bonus_block_size: dimensione blocco che ottiene bonus extra (default 3)
    """
    terms = []
    
    min_block_size = params.get("min_block_size", 2)
    bonus_block_size = params.get("bonus_block_size", 3)
    
    # Solo turni lavorativi (escludiamo SMONTO e RIPOSO dai blocchi)
    working_shifts = [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]
    
    for i in range(len(nurses)):
        for shift_type in working_shifts:
            shift_val = shift_type.value
            
            # Trova blocchi consecutivi di questo tipo di turno
            for start_day in range(num_days - min_block_size + 1):
                
                # Blocco di dimensione minima (2-3 giorni)
                for block_size in range(min_block_size, min(bonus_block_size + 1, num_days - start_day + 1)):
                    
                    # Variabile: esiste un blocco di questa dimensione che inizia in start_day?
                    block_var = model.NewBoolVar(f"nurse{i}_block_{shift_type.name.lower()}_{start_day}_{block_size}")
                    
                    # Condizioni per il blocco:
                    block_conditions = []
                    
                    # 1. Tutti i giorni del blocco devono avere questo turno
                    for day_offset in range(block_size):
                        day = start_day + day_offset
                        block_conditions.append(nurse_shift[i, day, shift_val])
                    
                    # 2. Il giorno prima del blocco (se esiste) NON deve avere questo turno
                    if start_day > 0:
                        block_conditions.append(nurse_shift[i, start_day - 1, shift_val].Not())
                    
                    # 3. Il giorno dopo il blocco (se esiste) NON deve avere questo turno
                    if start_day + block_size < num_days:
                        block_conditions.append(nurse_shift[i, start_day + block_size, shift_val].Not())
                    
                    # Il blocco esiste solo se tutte le condizioni sono vere
                    model.AddBoolAnd(block_conditions).OnlyEnforceIf(block_var)
                    model.AddBoolOr([cond.Not() for cond in block_conditions]).OnlyEnforceIf(block_var.Not())
                    
                    # Premio proporzionale alla dimensione del blocco
                    if block_size == bonus_block_size:
                        # Bonus extra per blocchi della dimensione preferita
                        block_weight = weight * 2
                    else:
                        # Premio normale per blocchi di dimensione minima
                        block_weight = weight
                    
                    terms.append(SoftTerm(block_var, block_weight))
                
                # Bonus speciale per blocchi molto lunghi (4+ giorni)
                if num_days - start_day >= 4:
                    for long_block_size in range(4, min(6, num_days - start_day + 1)):  # Max 5 giorni consecutivi
                        
                        long_block_var = model.NewBoolVar(f"nurse{i}_long_block_{shift_type.name.lower()}_{start_day}_{long_block_size}")
                        
                        long_conditions = []
                        
                        # Tutti i giorni del blocco lungo devono avere questo turno
                        for day_offset in range(long_block_size):
                            day = start_day + day_offset
                            long_conditions.append(nurse_shift[i, day, shift_val])
                        
                        # Bordi del blocco
                        if start_day > 0:
                            long_conditions.append(nurse_shift[i, start_day - 1, shift_val].Not())
                        if start_day + long_block_size < num_days:
                            long_conditions.append(nurse_shift[i, start_day + long_block_size, shift_val].Not())
                        
                        model.AddBoolAnd(long_conditions).OnlyEnforceIf(long_block_var)
                        model.AddBoolOr([cond.Not() for cond in long_conditions]).OnlyEnforceIf(long_block_var.Not())
                        
                        # Bonus decrescente per blocchi troppo lunghi (evitare affaticamento)
                        long_weight = weight * 3 // long_block_size  # Peso decrescente
                        terms.append(SoftTerm(long_block_var, long_weight))
    
    return terms

@registry.hard_constraint("forced_assignment")
def hc_forced_assignment(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int,
    start_weekday: int = 0
):
    """
    Hard constraint: forza un'assegnazione specifica per supportare modifiche.
    """
    nurse_idx = params["nurse_idx"]
    day = params["day"]
    shift_type_val = params["shift_type"]
    must_assign = params.get("must_assign", True)
    
    if must_assign:
        model.Add(nurse_shift[nurse_idx, day, shift_type_val] == 1)
    else:
        model.Add(nurse_shift[nurse_idx, day, shift_type_val] == 0)

@registry.soft_constraint("stability_penalty")
def sc_stability_penalty(
    model: cp_model.CpModel,
    nurse_shift,
    nurses: List[Nurse],
    params,
    num_days: int,
    weight: int,
    start_weekday: int = 0
) -> List[SoftTerm]:
    """
    Soft constraint: penalizza deviazioni dal piano originale per favorire stabilità.
    """
    terms = []
    original_hints = params.get("original_plan_hints", {})
    
    for (nurse_idx, day, shift_val), original_value in original_hints.items():
        if (nurse_idx, day, shift_val) in nurse_shift:
            var = nurse_shift[nurse_idx, day, shift_val]
            
            if original_value == 1:
                # Premio per mantenere assegnazioni esistenti
                terms.append(SoftTerm(var, weight))
            else:
                # Penalità per creare nuove assegnazioni dove non c'erano
                penalty_var = model.NewBoolVar(f"stability_penalty_{nurse_idx}_{day}_{shift_val}")
                model.Add(var == 1).OnlyEnforceIf(penalty_var)
                model.Add(var == 0).OnlyEnforceIf(penalty_var.Not())
                terms.append(SoftTerm(penalty_var, -weight))  # Penalità negativa
    
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
