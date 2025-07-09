"""
utils/config.py
----------------
Configurazione centralizzata di costanti e parametri base.
È progettato per essere semplice ma estensibile (es. con Pydantic, dotenv, ecc.).
"""

from utils.enums import ShiftType

# Giorni della settimana (0 = lunedì, 6 = domenica)
WEEKDAY_NAMES = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

# Etichette testuali associate ai turni
SHIFT_LABELS = {
    ShiftType.MORNING: "mattino",
    ShiftType.AFTERNOON: "pomeriggio",
    ShiftType.NIGHT: "notte",
    ShiftType.SMONTO: "smonto",
}

DEFAULT_COVERAGE = {
    ShiftType.MORNING: 2,
    ShiftType.AFTERNOON: 2,
    ShiftType.NIGHT: 1,
    ShiftType.SMONTO: 0,
}