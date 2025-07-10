"""
parser/soft_constraint_loader.py - VERSIONE AGGIORNATA
------------------------------------------------------
Aggiunge il nuovo tipo di soft constraint per i weekend.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict


_SUPPORTED_SOFT_TYPES: set[str] = {
    "prefer_shift",
    "avoid_shift",
    "equity",
    "workload_balance",
    "weekend_rest",  # AGGIUNTO!
    "shift_blocks",  # AGGIUNTO! Premia blocchi consecutivi di turni uguali
}


def _validate_soft_constraint(entry: dict, index: int) -> None:
    required = {"type", "params", "weight"}

    if not isinstance(entry, dict):
        raise TypeError(f"Soft constraints – record {index}: deve essere un oggetto JSON")

    missing = required - entry.keys()
    if missing:
        raise ValueError(
            f"Soft constraints – record {index}: campi mancanti {', '.join(missing)}"
        )

    if entry["type"] not in _SUPPORTED_SOFT_TYPES:
        raise ValueError(
            f"Soft constraints – record {index}: tipo '{entry['type']}' non supportato"
        )

    if not isinstance(entry["params"], dict):
        raise TypeError(
            f"Soft constraints – record {index}: 'params' deve essere un oggetto/dict"
        )

    if not isinstance(entry["weight"], int) or entry["weight"] < 0:
        raise ValueError(
            f"Soft constraints – record {index}: 'weight' deve essere intero ≥ 0"
        )


def load_soft_constraints(json_path: str | Path) -> List[Dict]:
    """
    Carica e valida il file JSON dei vincoli soft.

    :param json_path: percorso a soft_constraints.json
    :return: lista di dizionari (vincoli soft)
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"File non trovato: {path}")

    with path.open(encoding="utf-8") as f:
        constraints = json.load(f)

    if not isinstance(constraints, list):
        raise ValueError("Il file soft_constraints.json deve contenere una lista di vincoli")

    for idx, entry in enumerate(constraints):
        _validate_soft_constraint(entry, idx)

    return constraints