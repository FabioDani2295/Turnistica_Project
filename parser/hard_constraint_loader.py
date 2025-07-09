"""
Hard constraint
Sono regole vincolanti che non possono mai essere violate. Vengono modellate tramite chiamate a model.Add(...), model.AddAllDifferent(...), ecc.
Se il modello non trova alcuna assegnazione che rispetti tutte le hard constraint, restituisce uno stato INFEASIBLE.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict


# Vincoli supportati in questa versione (AGGIORNATO CON SMONTO)
_SUPPORTED_HARD_TYPES: set[str] = {
    "incompatibility",
    "max_consecutive_nights",
    "max_consecutive_work_days",
    "min_rest_hours",
    "coverage_minimum",
    "workload_balance_hard",
    "mandatory_smonto_after_night",      # AGGIUNTO
    "mandatory_rest_after_smonto",       # AGGIUNTO
    "no_afternoon_after_morning",
    "max_nights_per_month",
    "weekend_rest_monthly",
    "shift_balance_morning_afternoon"
}


def _validate_hard_constraint(entry: dict, index: int) -> None:
    """Controllo struttura minima e coerenza del tipo di vincolo."""
    if not isinstance(entry, dict):
        raise TypeError(f"Hard constraints – record {index}: deve essere un oggetto JSON")

    # campi obbligatori
    for field in ("type", "params"):
        if field not in entry:
            raise ValueError(
                f"Hard constraints – record {index}: campo obbligatorio '{field}' mancante"
            )

    if entry["type"] not in _SUPPORTED_HARD_TYPES:
        raise ValueError(
            f"Hard constraints – record {index}: tipo '{entry['type']}' non supportato"
        )

    if not isinstance(entry["params"], dict):
        raise TypeError(
            f"Hard constraints – record {index}: 'params' deve essere un oggetto/dict"
        )


def load_hard_constraints(json_path: str | Path) -> List[Dict]:
    """
    Carica e valida il file JSON dei vincoli rigidi.

    :param json_path: percorso a hard_constraints.json
    :return: lista di dizionari (vincoli hard)
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"File non trovato: {path}")

    with path.open(encoding="utf-8") as f:
        constraints = json.load(f)

    if not isinstance(constraints, list):
        raise ValueError("Il file hard_constraints.json deve contenere una lista di vincoli")

    for idx, entry in enumerate(constraints):
        _validate_hard_constraint(entry, idx)

    return constraints