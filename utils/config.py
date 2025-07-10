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

# ===== PARAMETRI PER SISTEMA DI MODIFICHE =====

# Peso per penalità di stabilità (preferenza per mantenere turni esistenti)
STABILITY_PENALTY_WEIGHT = 200

# Numero massimo di scenari alternativi da generare
MAX_ALTERNATIVE_SCENARIOS = 5

# Timeout per la generazione di ciascuno scenario (secondi)
SCENARIO_GENERATION_TIMEOUT = 30

# Peso relativo delle modifiche per tipologia (più alto = più costoso cambiare)
MODIFICATION_WEIGHTS = {
    "nurse_change": 10,      # Cambiare infermiere assegnato a un turno
    "shift_change": 8,       # Cambiare tipo di turno per un infermiere 
    "add_shift": 12,         # Aggiungere un turno dove prima c'era riposo
    "remove_shift": 15,      # Rimuovere un turno (creare riposo)
}

# Scope temporale per limitare le modifiche (giorni prima/dopo la modifica richiesta)
MODIFICATION_SCOPE_DAYS = 7

# Soglia minima di qualità per accettare uno scenario (punteggio soft constraints)
MIN_SCENARIO_QUALITY_THRESHOLD = 0.3  # 30% del punteggio ottimale (abbassata per debugging)