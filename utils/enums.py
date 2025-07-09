"""
utils/enums.py
--------------
Enumerazioni condivise in tutto il progetto.
CORRETTO: Gestione corretta dell'iterazione su ShiftType.
"""

from enum import IntEnum, Enum


class ShiftType(IntEnum):
    """Identificatori dei turni e riposi."""

    MORNING = 0      # 06:00 – 14:00
    AFTERNOON = 1    # 14:00 – 22:00
    NIGHT = 2        # 22:00 – 06:00
    SMONTO = 3       # Smonto dopo turno notturno (= riposo speciale)
    # NOTA: Il riposo normale è rappresentato dall'assenza di turno (0 in tutte le variabili)

    def __str__(self) -> str:          # migliora la leggibilità in stampe/log
        return self.name.capitalize()


class AbsenceType(Enum):
    """Tipologie di assenza (verranno usate in fase successiva)."""

    SICK = "malattia"
    VACATION = "ferie"
    PERSONAL = "permesso"
    TRAINING = "formazione"

    def __str__(self) -> str:        return self.value