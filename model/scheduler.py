"""
model/scheduler.py - AGGIORNATO PER WEEKEND DETECTION
====================================================
Aggiunge il parametro start_weekday per identificare sabati e domeniche.
"""

from __future__ import annotations

from typing import List, Dict, Tuple, Any
from datetime import datetime

from ortools.sat.python import cp_model

from utils.enums import ShiftType  # 0=morning,1=afternoon,2=night
from model.constraint_registry import registry, SoftTerm
from model.nurse import Nurse


class Scheduler:
    """Industrial‑grade, extensible scheduler con supporto weekend detection"""

    def __init__(
            self,
            nurses: List[Nurse],
            hard_constraints: List[Dict[str, Any]],
            soft_constraints: List[Dict[str, Any]],
            num_days: int = 7,
            min_coverage: Dict[ShiftType, int] | None = None,
            start_weekday: int = 0,  # NUOVO: 0=lunedì, 6=domenica
    ) -> None:
        self.nurses = nurses
        self.hard_constraints = hard_constraints
        self.soft_constraints = soft_constraints
        self.num_days = num_days
        self.start_weekday = start_weekday  # NUOVO

        # fall‑back coverage requirement if not provided by hard constraint
        self.min_coverage = (
                min_coverage
                or {
                    ShiftType.MORNING: 2,
                    ShiftType.AFTERNOON: 2,
                    ShiftType.NIGHT: 1,
                    ShiftType.SMONTO: 0
                }
        )

        self.model = cp_model.CpModel()
        self._build_decision_variables()
        self.hints = None  # Storage for warm-start hints

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_hints(self, hints: Dict[Tuple[int, int, int], int]) -> None:
        """
        Imposta hint per warm-start del solver.
        
        :param hints: dizionario {(nurse_idx, day, shift_type_value): 1 or 0}
        """
        self.hints = hints

    def solve(self, max_seconds: float = 60.0) -> Tuple[int, List[Dict]]:
        """Return (solver status, schedule list)"""
        self._apply_constraints()
        self._build_objective()

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_seconds
        
        # Note: OR-Tools hints non disponibili in questa versione
        # La stabilità è gestita tramite soft constraints
        
        status = solver.Solve(self.model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return status, []
        return status, self._extract_schedule(solver)

    # ------------------------------------------------------------------
    # NUOVO: Metodo per identificare weekend
    # ------------------------------------------------------------------
    def get_weekend_days(self) -> List[Tuple[int, int]]:
        """
        Restituisce lista di coppie (sabato, domenica) nel periodo.

        :return: Lista di tuple (indice_sabato, indice_domenica)
        """
        weekends = []

        for day in range(self.num_days):
            weekday = (self.start_weekday + day) % 7

            # Se questo giorno è sabato (5) e c'è anche domenica (giorno successivo)
            if weekday == 5 and day + 1 < self.num_days:
                next_weekday = (self.start_weekday + day + 1) % 7
                if next_weekday == 6:  # Domenica
                    weekends.append((day, day + 1))

        return weekends

    # ------------------------------------------------------------------
    # Internal helpers (modificati per passare weekend info)
    # ------------------------------------------------------------------
    def _build_decision_variables(self) -> None:
        self.nurse_shift: Dict[Tuple[int, int, int], cp_model.IntVar] = {}
        for n_idx in range(len(self.nurses)):
            for d in range(self.num_days):
                for s in ShiftType:  # iterate enum
                    var = self.model.NewBoolVar(f"n{n_idx}_d{d}_s{s.value}")
                    self.nurse_shift[n_idx, d, s.value] = var

    def _apply_constraints(self) -> None:
        """Apply built‑in and registry‑based constraints."""
        # Built‑in: one shift per nurse per day (ora include SMONTO)
        for n_idx in range(len(self.nurses)):
            for d in range(self.num_days):
                self.model.Add(
                    sum(
                        self.nurse_shift[n_idx, d, s.value] for s in ShiftType
                    )
                    <= 1
                )
        # Built‑in: coverage minimum fallback (overridden by explicit hard constraint)
        self._fallback_coverage_constraints()

        # Registry‑driven constraints (ora passano anche weekend info se necessario)
        for h in self.hard_constraints:
            c_type = h["type"]
            handler = registry.hard.get(c_type)
            if handler is None:
                raise ValueError(f"Unknown hard constraint type '{c_type}'")

            # Passa parametri standard + weekend info per vincoli che ne hanno bisogno
            if c_type in ["weekend_rest_monthly", "forced_assignment"]:
                # Modifica il call per passare info weekend
                handler(self.model, self.nurse_shift, self.nurses, h["params"],
                        self.num_days, self.start_weekday)
            else:
                handler(self.model, self.nurse_shift, self.nurses, h["params"], self.num_days)

    def _build_objective(self) -> None:
        objective_terms: List[SoftTerm] = []
        for s in self.soft_constraints:
            c_type = s["type"]
            weight = int(s.get("weight", 1))
            handler = registry.soft.get(c_type)
            if handler is None:
                raise ValueError(f"Unknown soft constraint type '{c_type}'")

            # Passa weekend info ai soft constraints che ne hanno bisogno
            if c_type in ["weekend_rest", "shift_blocks"]:
                terms = handler(
                    self.model,
                    self.nurse_shift,
                    self.nurses,
                    s["params"],
                    self.num_days,
                    weight,
                    self.start_weekday  # NUOVO parametro
                )
            else:
                terms = handler(
                    self.model,
                    self.nurse_shift,
                    self.nurses,
                    s["params"],
                    self.num_days,
                    weight,
                )
            if terms:
                objective_terms.extend(terms)
        if objective_terms:
            self.model.Maximize(sum(term.expr * term.weight for term in objective_terms))

    # ---------------- private helpers (unchanged) ----------------
    def _fallback_coverage_constraints(self):
        for d in range(self.num_days):
            for shift in ShiftType:
                self.model.Add(
                    sum(
                        self.nurse_shift[n_idx, d, shift.value]
                        for n_idx in range(len(self.nurses))
                    )
                    >= self.min_coverage[shift]
                )

    def _extract_schedule(self, solver: cp_model.CpSolver) -> List[Dict]:
        schedule: List[Dict] = []
        for d in range(self.num_days):
            day_data: Dict[str, Any] = {"day_index": d}
            for shift in ShiftType:
                assigned = [
                    self.nurses[n_idx].name
                    for n_idx in range(len(self.nurses))
                    if solver.Value(self.nurse_shift[n_idx, d, shift.value]) == 1
                ]
                day_data[shift.name.lower()] = assigned
            schedule.append(day_data)
        return schedule