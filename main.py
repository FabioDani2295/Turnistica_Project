"""
main.py - AGGIORNATO
--------------------
Passa il giorno della settimana di partenza al Scheduler.
"""

import sys
from pathlib import Path

from parser.nurse_loader import load_nurses
from parser.hard_constraint_loader import load_hard_constraints
from parser.soft_constraint_loader import load_soft_constraints
from parser.solution_analyzer import SolutionAnalyzer

from model.scheduler import Scheduler
from ortools.sat.python import cp_model

from utils.date_manager import get_next_month_period, DateManager
from utils.schedule_formatter import ScheduleFormatter


# ============================== CONFIGURAZIONE FILE ==============================

DATA_DIR = Path("data")

NURSES_FILE = DATA_DIR / "nurses.json"
HARD_CONSTRAINTS_FILE = DATA_DIR / "hard_constraints.json"
SOFT_CONSTRAINTS_FILE = DATA_DIR / "soft_constraints.json"


# ============================== ESECUZIONE =======================================

def main():
    print("🏥 SISTEMA DI PIANIFICAZIONE TURNI - OR-Tools & JSON")
    print("=" * 60)
    print()

    try:
        # Pianificazione automatica del prossimo mese
        start_date, num_days, period_desc = get_next_month_period()

        # NUOVO: Ottieni il giorno della settimana di partenza
        start_weekday = start_date.weekday()  # 0=lunedì, 6=domenica

        # Genera etichette date
        dm = DateManager(start_date)
        date_labels = dm.generate_date_labels(start_date, num_days)

        # Carica configurazione
        nurses = load_nurses(NURSES_FILE)
        hard_constraints = load_hard_constraints(HARD_CONSTRAINTS_FILE)
        soft_constraints = load_soft_constraints(SOFT_CONSTRAINTS_FILE)

        print(f"👥 Infermieri caricati: {len(nurses)}")
        print(f"🔒 Vincoli rigidi:      {len(hard_constraints)}")
        print(f"🔓 Vincoli flessibili:  {len(soft_constraints)}")
        print(f"📅 Periodo:             {period_desc}")
        print(f"📊 Giorni da pianificare: {num_days} (mensile)")
        print(f"📆 Inizio:              {start_date.strftime('%A')} {start_date.strftime('%d/%m/%Y')}")

        # Mostra weekend identificati
        temp_scheduler = Scheduler([], [], [], num_days, start_weekday=start_weekday)
        weekends = temp_scheduler.get_weekend_days()
        if weekends:
            print(f"🏖️  Weekend nel periodo:   {len(weekends)} (giorni {[f'{s+1}-{d+1}' for s,d in weekends]})")
        else:
            print("🏖️  Weekend nel periodo:   Nessun weekend completo")
        print()

        # Risoluzione
        print("🔄 Avvio risoluzione OR-Tools...")
        scheduler = Scheduler(
            nurses=nurses,
            hard_constraints=hard_constraints,
            soft_constraints=soft_constraints,
            num_days=num_days,
            start_weekday=start_weekday  # NUOVO parametro
        )

        status, schedule = scheduler.solve(max_seconds=120.0)  # Più tempo per periodi lunghi

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            print("❌ Nessuna soluzione trovata. Avvio analisi diagnostica...\n")

            # Esegui analisi approfondita
            analyzer = SolutionAnalyzer(
                nurses=nurses,
                hard_constraints=hard_constraints,
                soft_constraints=soft_constraints,
                num_days=num_days
            )
            analyzer.analyze_infeasibility()

            sys.exit(1)

        print("✅ Soluzione trovata!\n")

        # Visualizza risultato in formato tabellare
        formatter = ScheduleFormatter(nurses, date_labels, period_desc)
        formatter.print_schedule_table(schedule)

    except KeyboardInterrupt:
        print("\n\n👋 Operazione annullata dall'utente.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Errore durante l'esecuzione: {e}")
        sys.exit(1)


# ============================== AVVIO =============================================

if __name__ == "__main__":
    main()