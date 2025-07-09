"""
utils/date_manager.py
---------------------
Gestione delle date e periodi di pianificazione turni.
Supporta pianificazione settimanale e mensile semplificata.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple
import calendar


class DateManager:
    """Gestione intelligente dei periodi di pianificazione."""

    def __init__(self, start_date: datetime):
        self.start_date = start_date

    @classmethod
    def today(cls) -> 'DateManager':
        """Crea un DateManager partendo da oggi."""
        return cls(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))

    def get_next_week_period(self) -> Tuple[datetime, int]:
        """
        Restituisce l'inizio della prossima settimana (lunedì) e numero di giorni (7).

        :return: (data_inizio, num_giorni)
        """
        # Trova il lunedì della prossima settimana
        days_since_monday = self.start_date.weekday()
        next_monday = self.start_date + timedelta(days=(7 - days_since_monday))

        return next_monday, 7

    def get_next_month_period(self) -> Tuple[datetime, int]:
        """
        Restituisce il primo giorno del prossimo mese e il numero di giorni.

        :return: (data_inizio, num_giorni)
        """
        current_month = self.start_date.month
        current_year = self.start_date.year

        # Calcola mese successivo
        if current_month == 12:
            next_month = 1
            next_year = current_year + 1
        else:
            next_month = current_month + 1
            next_year = current_year

        start_date = datetime(next_year, next_month, 1)
        days_in_month = calendar.monthrange(next_year, next_month)[1]

        return start_date, days_in_month

    def generate_date_labels(self, start_date: datetime, num_days: int) -> List[str]:
        """
        Genera etichette per le date del periodo.

        :param start_date: data di inizio
        :param num_days: numero di giorni
        :return: lista di stringhe formato "Lun 01/07"
        """
        labels = []
        current_date = start_date

        weekday_names = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]

        for _ in range(num_days):
            weekday = weekday_names[current_date.weekday()]
            day_month = current_date.strftime("%d/%m")
            labels.append(f"{weekday} {day_month}")
            current_date += timedelta(days=1)

        return labels


def interactive_period_selection() -> Tuple[datetime, int, str]:
    """
    Chiede all'utente di selezionare il periodo di pianificazione.
    Opzioni semplificate: solo prossima settimana o prossimo mese.

    :return: (data_inizio, num_giorni, descrizione)
    """
    print("📅 SELEZIONE PERIODO DI PIANIFICAZIONE")
    print("=" * 50)

    today = datetime.now()
    print(f"📍 Oggi: {today.strftime('%A, %d %B %Y')}")
    print()

    dm = DateManager.today()

    # Calcola informazioni sui periodi
    next_week_start, _ = dm.get_next_week_period()
    next_month_start, next_month_days = dm.get_next_month_period()

    next_week_end = next_week_start + timedelta(days=6)
    next_month_end = next_month_start + timedelta(days=next_month_days-1)

    print("Scegli il periodo da pianificare:")
    print(f"1. 📅 Prossima settimana ({next_week_start.strftime('%d/%m')} - {next_week_end.strftime('%d/%m')})")
    print(f"2. 🗓  Prossimo mese ({next_month_start.strftime('%B %Y')} - {next_month_days} giorni)")

    while True:
        try:
            choice = input("\nInserisci scelta (1-2): ").strip()

            if choice == "1":
                start_date, num_days = dm.get_next_week_period()
                end_date = start_date + timedelta(days=6)
                desc = f"Prossima settimana ({start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')})"
                break

            elif choice == "2":
                start_date, num_days = dm.get_next_month_period()
                month_name = calendar.month_name[start_date.month]
                desc = f"{month_name} {start_date.year} ({num_days} giorni)"
                break

            else:
                print("❌ Scelta non valida. Scegli 1 o 2.")
                continue

        except KeyboardInterrupt:
            print("\n\n👋 Operazione annullata.")
            exit(0)

    print(f"\n✅ Periodo selezionato: {desc}")
    print(f"📊 Giorni da pianificare: {num_days}")
    print()

    return start_date, num_days, desc