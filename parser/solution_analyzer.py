"""
parser/solution_analyzer.py
---------------------------
Analizza i motivi per cui OR-Tools non riesce a trovare una soluzione,
fornendo diagnostica dettagliata su vincoli, monte ore, e conflitti.
"""

from __future__ import annotations

from typing import List, Dict, Any
from collections import defaultdict

from model.nurse import Nurse
from utils.enums import ShiftType
from utils.config import WEEKDAY_NAMES, SHIFT_LABELS
from utils.schedule_formatter import ScheduleFormatter


class SolutionAnalyzer:
    """Diagnostica problemi di infeasibility nei modelli di scheduling."""

    def __init__(
            self,
            nurses: List[Nurse],
            hard_constraints: List[Dict[str, Any]],
            soft_constraints: List[Dict[str, Any]],
            num_days: int = 7,
            hours_per_shift: int = 8
    ):
        self.nurses = nurses
        self.hard_constraints = hard_constraints
        self.soft_constraints = soft_constraints
        self.num_days = num_days
        self.hours_per_shift = hours_per_shift

        # Estrai parametri dai vincoli
        self.coverage_requirements = self._extract_coverage_requirements()

    def analyze_infeasibility(self) -> None:
        """Esegue analisi completa e stampa i risultati."""
        print("🔍 ANALISI INFEASIBILITÀ - Diagnosi problemi di scheduling\n")

        self._analyze_workload_balance()
        self._analyze_coverage_constraints()
        self._analyze_nurse_availability()
        self._analyze_incompatibilities()
        self._analyze_consecutive_constraints()
        self._analyze_preference_conflicts()
        self._suggest_solutions()

    def _extract_coverage_requirements(self) -> Dict[ShiftType, int]:
        """Estrae i requisiti di copertura dai vincoli hard."""
        default_coverage = {
            ShiftType.MORNING: 2,
            ShiftType.AFTERNOON: 2,
            ShiftType.NIGHT: 1,
            ShiftType.SMONTO: 0
        }

        for constraint in self.hard_constraints:
            if constraint["type"] == "coverage_minimum":
                params = constraint["params"]
                return {
                    ShiftType.MORNING: params.get("morning", 2),
                    ShiftType.AFTERNOON: params.get("afternoon", 2),
                    ShiftType.NIGHT: params.get("night", 1),
                    ShiftType.SMONTO: 0  # Smonto non ha requisiti di copertura
                }
        return default_coverage

    def _analyze_workload_balance(self) -> None:
        """Analizza il bilanciamento generale delle ore."""
        print("📊 ANALISI MONTE ORE")
        print("=" * 50)

        total_hours = sum(nurse.contracted_hours for nurse in self.nurses)
        # Solo i turni lavorativi contano per le ore
        shifts_needed = (self.coverage_requirements[ShiftType.MORNING] +
                        self.coverage_requirements[ShiftType.AFTERNOON] +
                        self.coverage_requirements[ShiftType.NIGHT]) * self.num_days
        hours_needed = shifts_needed * self.hours_per_shift

        print(f"👥 Infermieri totali:       {len(self.nurses)}")
        print(f"⏰ Ore contrattuali totali: {total_hours}")
        print(f"🎯 Turni necessari:         {shifts_needed} ({shifts_needed // self.num_days}/giorno × {self.num_days} giorni)")
        print(f"⚖️  Ore necessarie:          {hours_needed}")
        print(f"📈 Bilancio ore:            {total_hours - hours_needed:+} ore")

        if total_hours < hours_needed:
            print("❌ PROBLEMA CRITICO: Ore insufficienti!")
        elif total_hours - hours_needed < hours_needed * 0.1:  # Meno del 10% di margine
            print("⚠️  ATTENZIONE: Margine molto ridotto")
        else:
            print("✅ Monte ore sufficiente")

        # Dettaglio per infermiere
        print(f"\n👤 Dettaglio per infermiere:")
        for nurse in self.nurses:
            max_shifts = nurse.max_shifts(self.hours_per_shift)
            print(f"   • {nurse.name:<20} {nurse.contracted_hours:2}h → max {max_shifts} turni")

        print()

    def _analyze_coverage_constraints(self) -> None:
        """Analizza la fattibilità della copertura per turno."""
        print("🏥 ANALISI COPERTURA TURNI")
        print("=" * 50)

        for shift_type, required in self.coverage_requirements.items():
            if shift_type == ShiftType.SMONTO:
                continue  # Lo smonto non ha requisiti di copertura

            available_nurses = self._count_available_nurses_for_shift(shift_type)
            total_required = required * self.num_days

            print(f"\n{SHIFT_LABELS[shift_type].upper()}:")
            print(f"   Richiesti:   {required}/giorno × {self.num_days} giorni = {total_required} turni")
            print(f"   Disponibili: {available_nurses} infermieri")

            if available_nurses < required:
                print(f"   ❌ PROBLEMA: Infermieri insufficienti ({available_nurses} < {required})")
            elif available_nurses == required:
                print(f"   ⚠️  RIGIDO: Nessun margine di manovra")
            else:
                print(f"   ✅ OK: Margine di {available_nurses - required} infermieri")

    def _count_available_nurses_for_shift(self, shift_type: ShiftType) -> int:
        """Conta quanti infermieri possono lavorare in un dato turno."""
        count = 0
        for nurse in self.nurses:
            if self._can_nurse_work_shift(nurse, shift_type):
                count += 1
        return count

    def _can_nurse_work_shift(self, nurse: Nurse, shift_type: ShiftType) -> bool:
        """Verifica se un infermiere può lavorare in un turno specifico."""
        shift_value = shift_type.value

        # Controlla only_shifts
        only_shifts = nurse.preferences.get("only_shifts")
        if only_shifts is not None and shift_value not in only_shifts:
            return False

        # Controlla avoid_shifts (interpretato come vincolo hard per questa analisi)
        avoid_shifts = nurse.preferences.get("avoid_shifts", [])
        if shift_value in avoid_shifts:
            return False

        return True

    def _analyze_nurse_availability(self) -> None:
        """Analizza le restrizioni individuali degli infermieri."""
        print("\n👥 ANALISI DISPONIBILITÀ INDIVIDUALE")
        print("=" * 50)

        restricted_nurses = []

        for nurse in self.nurses:
            restrictions = []

            # Solo alcuni turni
            only_shifts = nurse.preferences.get("only_shifts")
            if only_shifts is not None:
                shift_names = [SHIFT_LABELS[ShiftType(s)] for s in only_shifts]
                restrictions.append(f"SOLO {'/'.join(shift_names)}")

            # Evita turni
            avoid_shifts = nurse.preferences.get("avoid_shifts", [])
            if avoid_shifts:
                shift_names = [SHIFT_LABELS[ShiftType(s)] for s in avoid_shifts]
                restrictions.append(f"EVITA {'/'.join(shift_names)}")

            # Evita giorni
            avoid_days = nurse.preferences.get("avoid_days", [])
            if avoid_days:
                day_names = [WEEKDAY_NAMES[d] for d in avoid_days]
                restrictions.append(f"EVITA {'/'.join(day_names)}")

            if restrictions:
                restricted_nurses.append((nurse.name, restrictions))
                max_shifts = nurse.max_shifts(self.hours_per_shift)
                print(f"⚠️  {nurse.name:<20} ({max_shifts} turni max): {' | '.join(restrictions)}")

        if not restricted_nurses:
            print("✅ Nessuna restrizione significativa")
        else:
            print(f"\n📊 {len(restricted_nurses)}/{len(self.nurses)} infermieri con restrizioni")

        print()

    def _analyze_incompatibilities(self) -> None:
        """Analizza vincoli di incompatibilità."""
        print("🚫 ANALISI INCOMPATIBILITÀ")
        print("=" * 50)

        incompatibilities = []
        for constraint in self.hard_constraints:
            if constraint["type"] == "incompatibility":
                pairs = constraint["params"].get("pairs", [])
                incompatibilities.extend(pairs)

        if not incompatibilities:
            print("✅ Nessuna incompatibilità definita")
        else:
            print(f"⚠️  {len(incompatibilities)} coppia/e incompatibili:")
            for pair in incompatibilities:
                print(f"   • {pair[0]} ↔ {pair[1]}")

            # Analizza l'impatto
            total_shifts_per_day = (self.coverage_requirements[ShiftType.MORNING] +
                                   self.coverage_requirements[ShiftType.AFTERNOON] +
                                   self.coverage_requirements[ShiftType.NIGHT])
            if len(incompatibilities) * 2 >= len(self.nurses):
                print("❌ RISCHIO ALTO: Troppe incompatibilità rispetto al team")

        print()

    def _analyze_consecutive_constraints(self) -> None:
        """Analizza vincoli di consecutività."""
        print("🔄 ANALISI VINCOLI CONSECUTIVITÀ")
        print("=" * 50)

        max_consec_nights = None
        max_consec_days = None
        has_smonto_constraints = False

        for constraint in self.hard_constraints:
            if constraint["type"] == "max_consecutive_nights":
                max_consec_nights = constraint["params"].get("max", 3)
            elif constraint["type"] == "max_consecutive_work_days":
                max_consec_days = constraint["params"].get("max_days", 6)
            elif constraint["type"] in ["mandatory_smonto_after_night", "mandatory_rest_after_smonto"]:
                has_smonto_constraints = True

        if max_consec_nights:
            print(f"🌙 Max notti consecutive: {max_consec_nights}")
            night_required = self.coverage_requirements[ShiftType.NIGHT]
            if night_required > 0 and max_consec_nights < self.num_days // 2:
                print("   ⚠️  Potrebbe limitare la pianificazione notturna")

        if max_consec_days:
            print(f"📅 Max giorni consecutivi: {max_consec_days}")
            if max_consec_days < 5:
                print("   ⚠️  Vincolo molto restrittivo per una settimana lavorativa")

        # Controllo riposo minimo
        has_min_rest = any(c["type"] == "min_rest_hours" for c in self.hard_constraints)
        if has_min_rest:
            print("😴 Vincolo riposo minimo: attivo (no notte→mattina)")

        if has_smonto_constraints:
            print("🔄 Vincoli smonto: attivi (notte→smonto→riposo obbligatorio)")
            print("   ⚠️  Ogni turno notturno richiede 2 giorni (notte + smonto)")

        print()

    def _analyze_preference_conflicts(self) -> None:
        """Analizza conflitti nelle preferenze."""
        print("⚡ ANALISI CONFLITTI PREFERENZE")
        print("=" * 50)

        # Conta preferenze per turno mattino
        morning_preferred = 0
        morning_required = self.coverage_requirements[ShiftType.MORNING] * self.num_days

        for nurse in self.nurses:
            preferred = nurse.preferences.get("preferred_shifts", [])
            if ShiftType.MORNING.value in preferred:
                morning_preferred += 1

        if morning_preferred > 0:
            print(f"🌅 Preferenze turno mattino: {morning_preferred} infermieri")
            print(f"   Turni mattino necessari: {morning_required}")
            if morning_preferred * nurse.max_shifts(self.hours_per_shift) < morning_required:
                print("   ⚠️  Preferenze insufficienti a coprire il fabbisogno")

        print()

    def _suggest_solutions(self) -> None:
        """Suggerisce possibili soluzioni ai problemi rilevati."""
        print("💡 SUGGERIMENTI PER RISOLVERE I PROBLEMI")
        print("=" * 50)

        suggestions = []

        # Controllo ore
        total_hours = sum(nurse.contracted_hours for nurse in self.nurses)
        shifts_needed = (self.coverage_requirements[ShiftType.MORNING] +
                        self.coverage_requirements[ShiftType.AFTERNOON] +
                        self.coverage_requirements[ShiftType.NIGHT]) * self.num_days
        hours_needed = shifts_needed * self.hours_per_shift

        if total_hours < hours_needed:
            suggestions.append("📈 Aumentare le ore contrattuali o aggiungere infermieri")

        # Controllo copertura notturna
        night_nurses = self._count_available_nurses_for_shift(ShiftType.NIGHT)
        night_required = self.coverage_requirements[ShiftType.NIGHT]

        if night_nurses < night_required:
            suggestions.append("🌙 Rimuovere restrizioni sui turni notturni o ridurre copertura notturna")
        elif night_nurses == night_required:
            suggestions.append("🌙 Aggiungere flessibilità sui turni notturni (margine zero)")

        # Vincoli troppo rigidi
        if any(c["type"] == "max_consecutive_work_days" and c["params"].get("max_days", 6) < 5
               for c in self.hard_constraints):
            suggestions.append("📅 Rilassare il vincolo sui giorni lavorativi consecutivi")

        # Incompatibilità eccessive
        incompatibility_count = sum(
            len(c["params"].get("pairs", []))
            for c in self.hard_constraints
            if c["type"] == "incompatibility"
        )
        if incompatibility_count >= len(self.nurses) // 3:
            suggestions.append("🚫 Ridurre il numero di incompatibilità tra infermieri")

        # Controllo vincoli smonto
        has_smonto = any(c["type"] in ["mandatory_smonto_after_night", "mandatory_rest_after_smonto"]
                        for c in self.hard_constraints)
        if has_smonto and night_required > 0:
            suggestions.append("🔄 Considerare che ogni notte richiede 2 giorni (notte+smonto)")

        if not suggestions:
            print("🤔 Problema complesso: analisi manuale necessaria")
            print("   Prova a rilassare gradualmente i vincoli soft o ridurre la copertura minima")
        else:
            for i, suggestion in enumerate(suggestions, 1):
                print(f"{i}. {suggestion}")

        print("\n" + "=" * 50)


def compare_plans(plan_old: List[Dict], plan_new: List[Dict], nurses: List[Nurse]) -> Dict[str, Any]:
    """
    Confronta due piani di turni e restituisce un report dettagliato delle differenze.
    
    :param plan_old: piano originale (formato schedule)
    :param plan_new: piano modificato (formato schedule)  
    :param nurses: lista degli infermieri
    :return: dizionario con statistiche delle modifiche
    """
    if len(plan_old) != len(plan_new):
        raise ValueError("I piani devono avere lo stesso numero di giorni")
    
    # Converte i piani in matrici per facilitare il confronto
    num_days = len(plan_old)
    date_labels = [f"Day{i}" for i in range(num_days)]  # Date fittizie per il formatter
    formatter = ScheduleFormatter(nurses, date_labels, "Confronto")
    matrix_old = formatter._build_shift_matrix(plan_old)
    matrix_new = formatter._build_shift_matrix(plan_new)
    
    num_nurses = len(nurses)
    
    # Statistiche delle modifiche
    total_changes = 0
    affected_nurses = set()
    changes_by_day = defaultdict(int)
    changes_by_nurse = defaultdict(int)
    changes_by_type = defaultdict(int)
    
    detailed_changes = []
    
    for nurse_idx in range(num_nurses):
        for day in range(num_days):
            old_shift = matrix_old[nurse_idx][day]
            new_shift = matrix_new[nurse_idx][day]
            
            if old_shift != new_shift:
                total_changes += 1
                affected_nurses.add(nurse_idx)
                changes_by_day[day] += 1
                changes_by_nurse[nurse_idx] += 1
                
                # Classifica il tipo di modifica
                if old_shift == 'R' and new_shift != 'R':
                    change_type = "new_assignment"
                elif old_shift != 'R' and new_shift == 'R':
                    change_type = "removed_assignment"
                elif old_shift != 'R' and new_shift != 'R':
                    change_type = "shift_change"
                else:
                    change_type = "other"
                
                changes_by_type[change_type] += 1
                
                detailed_changes.append({
                    "nurse": nurses[nurse_idx].name,
                    "nurse_idx": nurse_idx,
                    "day": day,
                    "old_shift": old_shift,
                    "new_shift": new_shift,
                    "change_type": change_type
                })
    
    # Calcola metriche di impatto
    impact_percentage = (total_changes / (num_nurses * num_days)) * 100
    nurses_affected_percentage = (len(affected_nurses) / num_nurses) * 100
    
    # Giorni con più modifiche
    most_affected_days = sorted(changes_by_day.items(), key=lambda x: x[1], reverse=True)[:3]
    
    # Infermieri con più modifiche  
    most_affected_nurses = sorted(changes_by_nurse.items(), key=lambda x: x[1], reverse=True)[:3]
    
    return {
        "total_changes": total_changes,
        "affected_nurses_count": len(affected_nurses),
        "affected_nurses_percentage": nurses_affected_percentage,
        "impact_percentage": impact_percentage,
        "changes_by_day": dict(changes_by_day),
        "changes_by_nurse": dict(changes_by_nurse),
        "changes_by_type": dict(changes_by_type),
        "most_affected_days": most_affected_days,
        "most_affected_nurses": [(nurses[idx].name, count) for idx, count in most_affected_nurses],
        "detailed_changes": detailed_changes,
        "summary": {
            "low_impact": total_changes <= num_nurses * 0.1,  # Meno del 10% del totale possibile
            "medium_impact": num_nurses * 0.1 < total_changes <= num_nurses * 0.3,
            "high_impact": total_changes > num_nurses * 0.3
        }
    }