"""
model/nurse.py
--------------
Definizione della struttura dati per gli infermieri.
MODIFICATO: contracted_hours ora sono mensili invece che settimanali.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Nurse:
    """
    Rappresenta un infermiere e le sue proprietà rilevanti per lo scheduling.
    """
    name: str
    contracted_hours: int  # ore MENSILI (modificato da settimanali)
    preferences: Dict[str, Optional[List[int]]] = field(default_factory=dict)

    def max_shifts_weekly(self, hours_per_shift: int = 8) -> int:
        """
        Calcola il numero massimo di turni a settimana sulla base del contratto.
        MODIFICATO: Ora divide le ore mensili per 4.
        """
        weekly_hours = self.contracted_hours / 4.0
        return int(weekly_hours // hours_per_shift)

    def max_shifts_monthly(self, hours_per_shift: int = 8) -> int:
        """
        Calcola il numero massimo di turni al mese sulla base del contratto.
        NUOVO METODO.
        """
        return self.contracted_hours // hours_per_shift

    def max_shifts(self, hours_per_shift: int = 8, period_days: int = 7) -> int:
        """
        Calcola il numero massimo di turni per il periodo specificato.
        MODIFICATO: Gestisce automaticamente periodi settimanali/mensili.

        :param hours_per_shift: ore per turno (default 8)
        :param period_days: giorni del periodo (7=settimana, 30=mese, etc.)
        :return: numero massimo turni
        """
        if period_days == 7:
            # Settimana
            return self.max_shifts_weekly(hours_per_shift)
        elif period_days >= 28 and period_days <= 31:
            # Mese
            return self.max_shifts_monthly(hours_per_shift)
        else:
            # Periodo custom: scala proporzionalmente dal contratto mensile
            monthly_shifts = self.max_shifts_monthly(hours_per_shift)
            return int(monthly_shifts * period_days / 30.0)

    def prefers_shift(self, shift: int) -> bool:
        """
        Verifica se l'infermiere ha espresso preferenza per uno specifico turno.
        """
        return shift in self.preferences.get("preferred_shifts", [])

    def avoids_shift(self, shift: int) -> bool:
        """
        Verifica se l'infermiere ha espresso avversione per uno specifico turno.
        """
        return shift in self.preferences.get("avoid_shifts", [])

    def allowed_shifts(self) -> Optional[List[int]]:
        """
        Restituisce la lista dei soli turni ammessi (se specificata).
        """
        return self.preferences.get("only_shifts")

    def avoids_days(self) -> Optional[List[int]]:
        """
        Giorni da evitare (se presenti), 0 = lunedì, 6 = domenica.
        """
        return self.preferences.get("avoid_days")