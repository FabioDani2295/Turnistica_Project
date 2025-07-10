"""
utils/date_manager.py
---------------------
Gestione delle date e periodi di pianificazione turni.
Supporta solo pianificazione mensile.
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


def get_next_month_period() -> Tuple[datetime, int, str]:
    """
    Restituisce il primo giorno del prossimo mese e il numero di giorni.
    Solo pianificazione mensile supportata.

    :return: (data_inizio, num_giorni, descrizione)
    """
    today = datetime.now()
    current_month = today.month
    current_year = today.year

    # Calcola mese successivo
    if current_month == 12:
        next_month = 1
        next_year = current_year + 1
    else:
        next_month = current_month + 1
        next_year = current_year

    start_date = datetime(next_year, next_month, 1)
    days_in_month = calendar.monthrange(next_year, next_month)[1]
    month_name = calendar.month_name[start_date.month]
    desc = f"{month_name} {start_date.year} ({days_in_month} giorni)"

    return start_date, days_in_month, desc