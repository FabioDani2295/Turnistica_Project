# =========================
#  model/scheduler.py
# =========================
"""High‑level OR‑Tools scheduler with pluggable constraint registry.
Designed for extensibility: new constraint types can be added by
registering a handler in `constraint_registry.py` without touching this
module.

The scheduler expects:
    • nurses: List[Nurse]
    • hard_constraints: List[Dict]
    • soft_constraints: List[Dict]

Any domain‑specific entity (Nurse, ShiftType, etc.) is assumed to be
already defined in utils/enums.py or model/nurse.py.
"""

from __future__ import annotations

from typing import List, Dict, Tuple, Any

from ortools.sat.python import cp_model

from utils.enums import ShiftType  # 0=morning,1=afternoon,2=night
from model.constraint_registry import registry, SoftTerm
from model.nurse import Nurse


class Scheduler:
    """Industrial‑grade, extensible scheduler"""

    def __init__(
        self,
        nurses: List[Nurse],
        hard_constraints: List[Dict[str, Any]],
        soft_constraints: List[Dict[str, Any]],
        num_days: int = 7,
        min_coverage: Dict[ShiftType, int] | None = None,
    ) -> None:
        self.nurses = nurses
        self.hard_constraints = hard_constraints
        self.soft_constraints = soft_constraints
        self.num_days = num_days
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def solve(self, max_seconds: float = 60.0) -> Tuple[int, List[Dict]]:
        """Return (solver status, schedule list)"""
        self._apply_constraints()
        self._build_objective()

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_seconds
        status = solver.Solve(self.model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return status, []
        return status, self._extract_schedule(solver)

    # ------------------------------------------------------------------
    # Internal helpers
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

        # Registry‑driven constraints
        for h in self.hard_constraints:
            c_type = h["type"]
            handler = registry.hard.get(c_type)
            if handler is None:
                raise ValueError(f"Unknown hard constraint type '{c_type}'")
            handler(self.model, self.nurse_shift, self.nurses, h["params"], self.num_days)

    def _build_objective(self) -> None:
        objective_terms: List[SoftTerm] = []
        for s in self.soft_constraints:
            c_type = s["type"]
            weight = int(s.get("weight", 1))
            handler = registry.soft.get(c_type)
            if handler is None:
                raise ValueError(f"Unknown soft constraint type '{c_type}'")
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

    # ---------------- private helpers ----------------
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
