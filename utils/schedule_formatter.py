"""
utils/schedule_formatter.py - VERSIONE CORRETTA CON SMONTO
----------------------------------------------------------
Formattazione e visualizzazione dei piani turni in formato tabellare.
CORRETTO: Include lo smonto (S) nella visualizzazione.
"""

from __future__ import annotations

from typing import List, Dict, Any
from datetime import datetime

from model.nurse import Nurse
from utils.enums import ShiftType


class ScheduleFormatter:
    """Formattatore professionale per piani turni."""

    def __init__(self, nurses: List[Nurse], date_labels: List[str], period_desc: str):
        self.nurses = nurses
        self.date_labels = date_labels
        self.period_desc = period_desc
        self.num_days = len(date_labels)

    def print_schedule_table(self, schedule: List[Dict[str, Any]]) -> None:
        """
        Stampa il piano turni in formato tabellare.

        Formato:
        - Righe: infermieri con % contratto e ore effettive
        - Colonne: giorni
        - Valori: R=riposo, M=mattino, P=pomeriggio, N=notte, S=smonto
        """
        print("📋 PIANO TURNI - FORMATO TABELLARE")
        print("=" * (50 + len(self.period_desc)))
        print(f"📅 Periodo: {self.period_desc}")
        print(f"👥 Infermieri: {len(self.nurses)} | 📆 Giorni: {self.num_days}")
        print()

        # Crea matrice turni
        shift_matrix = self._build_shift_matrix(schedule)

        # Stampa tabella
        self._print_header()
        self._print_separator()

        for nurse_idx, nurse in enumerate(self.nurses):
            self._print_nurse_row(nurse, shift_matrix[nurse_idx])

        self._print_separator()
        self._print_legend()
        self._print_statistics(shift_matrix)

    def _build_shift_matrix(self, schedule: List[Dict[str, Any]]) -> List[List[str]]:
        """
        Costruisce matrice [infermiere][giorno] = tipo_turno.

        :param schedule: schedule da OR-Tools
        :return: matrice con R=riposo, M=mattino, P=pomeriggio, N=notte, S=smonto
        """
        # Inizializza matrice con R (riposo)
        matrix = [['R' for _ in range(self.num_days)] for _ in range(len(self.nurses))]

        # Mappa nomi -> indici
        name_to_idx = {nurse.name: idx for idx, nurse in enumerate(self.nurses)}

        # Riempi matrice dai risultati OR-Tools
        for day_idx, day_data in enumerate(schedule):
            for shift_type in ShiftType:
                shift_name = shift_type.name.lower()
                assigned_nurses = day_data.get(shift_name, [])

                for nurse_name in assigned_nurses:
                    if nurse_name in name_to_idx:
                        nurse_idx = name_to_idx[nurse_name]
                        # CORRETTO: Incluso lo smonto nel mapping
                        shift_letters = {
                            'morning': 'M',
                            'afternoon': 'P',
                            'night': 'N',
                            'smonto': 'S'  # AGGIUNTO!
                        }
                        matrix[nurse_idx][day_idx] = shift_letters.get(shift_name, 'R')

        return matrix

    def _print_header(self) -> None:
        """Stampa intestazione tabella."""
        # Colonne: Nome, Ore Contratto, Ore Effettive, Differenza
        header = f"{'Infermiere':<18} {'OreCtr':<6} {'OreEff':<6} {'Diff':<5}"

        # Date complete con giorno della settimana e data (10 caratteri)
        for date_label in self.date_labels:
            header += f" {date_label:^10}"

        print(header)

    def _print_separator(self) -> None:
        """Stampa linea separatrice."""
        # 18+6+6+5+1 = 36 caratteri fissi, poi 11 caratteri per ogni giorno
        width = 36 + (11 * self.num_days)
        print("-" * width)

    def _print_nurse_row(self, nurse: Nurse, shifts: List[str]) -> None:
        """
        Stampa riga di un infermiere con ore contrattuali, effettive e differenza.
        NOTA: Lo smonto NON conta come ore lavorate.

        :param nurse: oggetto infermiere
        :param shifts: lista turni per ogni giorno (lettere)
        """
        # Calcola statistiche - SMONTO NON CONTA COME ORE LAVORATE
        worked_shifts = sum(1 for shift in shifts if shift in ['M', 'P', 'N'])  # Escluso 'S'
        worked_hours = worked_shifts * 8  # 8 ore per turno

        # Ore contrattuali per il periodo
        contract_hours_period = self._calculate_contract_hours_for_period(nurse.contracted_hours)

        # Differenza (positiva = sopra contratto, negativa = sotto contratto)
        diff_hours = worked_hours - contract_hours_period

        # Nome infermiere (troncato se necessario)
        name = nurse.name[:17] if len(nurse.name) > 17 else nurse.name

        # Formato differenza con segno
        diff_str = f"{diff_hours:+.0f}h" if diff_hours != 0 else "0h"

        # Formato riga: Nome | Ore Contratto | Ore Effettive | Differenza | Turni
        row = f"{name:<18} {contract_hours_period:4.0f}h {worked_hours:4}h {diff_str:>5}"

        # Turni
        for shift in shifts:
            row += f" {shift:^10}"

        print(row)

    def _calculate_contract_hours_for_period(self, monthly_hours: int) -> float:
        """
        Calcola le ore contrattuali per il periodo specifico.

        :param monthly_hours: ore mensili da contratto
        :return: ore totali per il periodo
        """
        if self.num_days == 7:
            # Settimana: monthly_hours / 4
            return float(monthly_hours) / 4.0
        elif self.num_days >= 28 and self.num_days <= 31:
            # Mese: usa direttamente le ore mensili
            return float(monthly_hours)
        else:
            # Periodo personalizzato: proporzione su base mensile
            return monthly_hours * (self.num_days / 30.0)

    def _print_legend(self) -> None:
        """Stampa legenda simboli."""
        print()
        print("📖 LEGENDA:")
        print("   R = Riposo | M = Mattino | P = Pomeriggio | N = Notte | S = Smonto")
        print("   OreCtr = Ore da contratto per il periodo (base mensile)")
        print("   OreEff = Ore effettivamente pianificate (smonto NON conta)")
        print("   Diff = Differenza (+ sopra contratto, - sotto contratto)")
        print()

    def _print_statistics(self, shift_matrix: List[List[str]]) -> None:
        """
        Stampa statistiche del piano turni.

        :param shift_matrix: matrice turni
        """
        print("📊 STATISTICHE DETTAGLIATE:")

        # Conteggi per infermiere
        for nurse_idx, nurse in enumerate(self.nurses):
            shifts = shift_matrix[nurse_idx]

            morning_count = shifts.count('M')
            afternoon_count = shifts.count('P')
            night_count = shifts.count('N')
            smonto_count = shifts.count('S')  # AGGIUNTO
            rest_count = shifts.count('R')
            total_shifts = morning_count + afternoon_count + night_count  # Smonto NON conta

            hours_worked = total_shifts * 8
            contract_hours_period = self._calculate_contract_hours_for_period(nurse.contracted_hours)
            diff_hours = hours_worked - contract_hours_period

            diff_str = f"{diff_hours:+.0f}h" if diff_hours != 0 else "±0h"

            print(f"   👤 {nurse.name:<18} | "
                  f"M:{morning_count:2} P:{afternoon_count:2} N:{night_count:2} S:{smonto_count:2} R:{rest_count:2} | "
                  f"Tot: {total_shifts:2} turni ({hours_worked:3}h) | "
                  f"Contratto: {contract_hours_period:3.0f}h ({diff_str})")

        print()

        # Sommario generale
        total_contract_hours = sum(self._calculate_contract_hours_for_period(n.contracted_hours) for n in self.nurses)
        total_worked_hours = sum(
            sum(1 for shift in nurse_shifts if shift in ['M', 'P', 'N']) * 8
            for nurse_shifts in shift_matrix
        )
        total_smonto_days = sum(
            sum(1 for shift in nurse_shifts if shift == 'S')
            for nurse_shifts in shift_matrix
        )
        overall_diff = total_worked_hours - total_contract_hours

        print(f"📈 SOMMARIO GENERALE:")
        print(f"   Ore contrattuali totali: {total_contract_hours:.0f}h")
        print(f"   Ore pianificate totali:  {total_worked_hours}h")
        print(f"   Giorni di smonto totali: {total_smonto_days}")
        print(f"   Differenza complessiva:  {overall_diff:+.0f}h")
        print()