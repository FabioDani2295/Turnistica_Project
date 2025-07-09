"""
debug_constraints.py
-------------------
Script di debug per analizzare dettagliatamente i vincoli OR-Tools
e identificare conflitti che impediscono di trovare soluzioni.
"""

from pathlib import Path
from parser.nurse_loader import load_nurses
from parser.hard_constraint_loader import load_hard_constraints
from parser.soft_constraint_loader import load_soft_constraints
from model.constraint_registry import registry
from utils.enums import ShiftType
from ortools.sat.python import cp_model
import sys


def debug_problem():
    """Analizza step-by-step la costruzione del problema."""

    print("🔍 DEBUG OR-TOOLS - ANALISI DETTAGLIATA")
    print("=" * 60)

    # Carica dati
    DATA_DIR = Path("data")
    nurses = load_nurses(DATA_DIR / "nurses.json")
    hard_constraints = load_hard_constraints(DATA_DIR / "hard_constraints.json")
    soft_constraints = load_soft_constraints(DATA_DIR / "soft_constraints.json")

    num_days = 7

    print(f"\n📊 DATI CARICATI:")
    print(f"   Infermieri: {len(nurses)}")
    print(f"   Hard constraints: {len(hard_constraints)}")
    print(f"   Soft constraints: {len(soft_constraints)}")
    print(f"   Giorni: {num_days}")

    # Crea modello base
    model = cp_model.CpModel()

    print(f"\n🏗️ CREAZIONE VARIABILI:")
    nurse_shift = {}
    var_count = 0

    for n_idx in range(len(nurses)):
        for d in range(num_days):
            for s in ShiftType:
                var = model.NewBoolVar(f"n{n_idx}_d{d}_s{s.value}")
                nurse_shift[n_idx, d, s.value] = var
                var_count += 1

    print(f"   Variabili create: {var_count}")

    # Analizza vincoli hard uno per uno
    print(f"\n🔒 ANALISI VINCOLI HARD:")

    # 1. Vincolo built-in: un solo turno per giorno
    print(f"\n   1️⃣ UN TURNO PER GIORNO:")
    builtin_constraints = 0
    for n_idx in range(len(nurses)):
        for d in range(num_days):
            model.Add(
                sum(nurse_shift[n_idx, d, s.value] for s in ShiftType) <= 1
            )
            builtin_constraints += 1
    print(f"      Vincoli aggiunti: {builtin_constraints}")

    # 2. Fallback coverage
    print(f"\n   2️⃣ COPERTURA FALLBACK:")
    coverage_constraints = 0
    min_coverage = {ShiftType.MORNING: 2, ShiftType.AFTERNOON: 2, ShiftType.NIGHT: 1}

    for d in range(num_days):
        for shift in ShiftType:
            model.Add(
                sum(
                    nurse_shift[n_idx, d, shift.value]
                    for n_idx in range(len(nurses))
                )
                >= min_coverage[shift]
            )
            coverage_constraints += 1
    print(f"      Vincoli aggiunti: {coverage_constraints}")

    # 3. Registry constraints
    print(f"\n   3️⃣ VINCOLI DA REGISTRY:")
    for i, constraint in enumerate(hard_constraints):
        c_type = constraint["type"]
        print(f"      {i + 1}. {c_type}: {constraint['params']}")

        handler = registry.hard.get(c_type)
        if handler:
            try:
                handler(model, nurse_shift, nurses, constraint["params"], num_days)
                print(f"         ✅ Applicato")
            except Exception as e:
                print(f"         ❌ Errore: {e}")
        else:
            print(f"         ❌ Handler non trovato")

    # Test risoluzione solo con hard constraints
    print(f"\n🧪 TEST RISOLUZIONE (SOLO HARD CONSTRAINTS):")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0

    status = solver.Solve(model)
    status_names = {
        cp_model.UNKNOWN: "UNKNOWN",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.OPTIMAL: "OPTIMAL"
    }

    print(f"   Status: {status_names.get(status, status)}")

    if status == cp_model.INFEASIBLE:
        print(f"   ❌ PROBLEMA: I vincoli HARD sono già infeasibili!")
        print(f"   🔍 Analizza i vincoli hard uno per uno...")
        return False
    elif status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"   ✅ Hard constraints OK")

        # Estrai soluzione di base
        print(f"\n📋 SOLUZIONE BASE (senza soft constraints):")
        total_shifts = [0] * len(nurses)

        for n_idx in range(len(nurses)):
            shifts_count = 0
            for d in range(num_days):
                for s in ShiftType:
                    if solver.Value(nurse_shift[n_idx, d, s.value]) == 1:
                        shifts_count += 1
            total_shifts[n_idx] = shifts_count
            print(f"      {nurses[n_idx].name}: {shifts_count} turni")

        avg_shifts = sum(total_shifts) / len(total_shifts)
        variance = sum((s - avg_shifts) ** 2 for s in total_shifts) / len(total_shifts)
        print(f"      Media: {avg_shifts:.1f}, Varianza: {variance:.2f}")

        # Test con soft constraints
        print(f"\n🎯 TEST CON SOFT CONSTRAINTS:")
        test_with_soft_constraints(model, nurse_shift, nurses, soft_constraints, num_days)

        return True
    else:
        print(f"   ⚠️ Status sconosciuto: {status}")
        return False


def test_with_soft_constraints(model, nurse_shift, nurses, soft_constraints, num_days):
    """Testa l'aggiunta di soft constraints."""

    objective_terms = []

    for constraint in soft_constraints:
        c_type = constraint["type"]
        weight = constraint.get("weight", 1)

        print(f"   Aggiungendo {c_type} (weight={weight})...")

        handler = registry.soft.get(c_type)
        if handler:
            try:
                terms = handler(
                    model, nurse_shift, nurses,
                    constraint["params"], num_days, weight
                )
                if terms:
                    objective_terms.extend(terms)
                    print(f"      ✅ {len(terms)} termini aggiunti")
                else:
                    print(f"      ⚠️ Nessun termine generato")
            except Exception as e:
                print(f"      ❌ Errore: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"      ❌ Handler non trovato")

    if objective_terms:
        print(f"   📊 Funzione obiettivo: {len(objective_terms)} termini")

        # Costruisci obiettivo
        objective_expr = sum(term.expr * term.weight for term in objective_terms)
        model.Maximize(objective_expr)

        # Risolvi con soft constraints
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60.0
        status = solver.Solve(model)

        status_names = {
            cp_model.UNKNOWN: "UNKNOWN",
            cp_model.MODEL_INVALID: "MODEL_INVALID",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.OPTIMAL: "OPTIMAL"
        }

        print(f"   Status finale: {status_names.get(status, status)}")

        if status == cp_model.INFEASIBLE:
            print(f"   ❌ PROBLEMA: Soft constraints rendono il problema infeasible!")
        elif status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print(f"   ✅ Soluzione trovata con soft constraints")
    else:
        print(f"   ⚠️ Nessun termine nell'obiettivo")


if __name__ == "__main__":
    try:
        debug_problem()
    except Exception as e:
        print(f"\n❌ Errore nel debug: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)