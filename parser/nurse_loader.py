"""
parser/nurse_loader.py
----------------------
Parsing e validazione del file JSON contenente l’elenco degli operatori (infermiere, OSS, ecc.).
Restituisce una lista di oggetti Nurse già pronta per l’uso nel motore di scheduling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from model.nurse import Nurse


def _validate_nurse_entry(entry: dict, index: int) -> None:
    """Controllo campi obbligatori e tipi di dato di un singolo record."""
    required_fields = {"name": str, "contracted_hours": int}

    for field, ftype in required_fields.items():
        if field not in entry:
            raise ValueError(
                f"Nurse JSON – record {index}: campo obbligatorio '{field}' mancante"
            )
        if not isinstance(entry[field], ftype):
            raise TypeError(
                f"Nurse JSON – record {index}: campo '{field}' deve essere di tipo {ftype.__name__}"
            )

    # Preferenze opzionali, se presenti devono essere dict
    if "preferences" in entry and not isinstance(entry["preferences"], dict):
        raise TypeError(
            f"Nurse JSON – record {index}: 'preferences' deve essere un oggetto/dict"
        )


def load_nurses(json_path: str | Path) -> List[Nurse]:
    """
    Carica e valida il file JSON degli operatori.

    :param json_path: percorso al file nurses.json
    :return: lista di oggetti Nurse
    :raises (ValueError, TypeError, FileNotFoundError, json.JSONDecodeError)
    """
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"File non trovato: {path}")

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Il file nurses.json deve contenere una lista di operatori")

    nurses: List[Nurse] = []

    for idx, entry in enumerate(data):
        _validate_nurse_entry(entry, idx)

        nurses.append(
            Nurse(
                name=entry["name"],
                contracted_hours=entry["contracted_hours"],
                preferences=entry.get("preferences", {}),
            )
        )

    return nurses
