"""
analyze_monthly_feasibility.py
------------------------------
Analisi dettagliata della fattibilità mensile del modello.
"""

from pathlib import Path
from parser.nurse_loader import load_nurses
from parser.hard_constraint_loader import load_hard_constraints
from utils.enums import ShiftType
import calendar


def analyze_monthly_feasibility():
    """Analizza la fattibilità teorica del problema mensile."""

    print("🔍 ANALISI FATTIBILITÀ MENSILE")
    print("=" * 60)

    # Carica dati
    DATA_DIR = Path("data")
    nurses = load_nurses(DATA_DIR / "nurses.json")
    hard_constraints = load_hard_constraints(DATA_DIR / "hard_constraints.json")

    # Parametri mese tipo (31 giorni)
    num_days = 31
    num_weekends = 5  # Assumiamo 5 weekend in un mese di 31 giorni

    # Estrai requisiti copertura
    coverage = {"morning": 2, "afternoon": 2, "night": 1}
    for constraint in hard_constraints:
        if constraint["type"] == "coverage_minimum":
            coverage = constraint["params"]
            break

    print(f"\n📊 PARAMETRI BASE:")
    print(f"   Giorni: {num_days}")
    print(f"   Weekend: {num_weekends}")
    print(f"   Infermieri: {len(nurses)}")
    print(f"   Copertura richiesta: M={coverage['morning']}, P={coverage['afternoon']}, N={coverage['night']}")

    # Calcola fabbisogno turni
    print(f"\n📈 FABBISOGNO TURNI:")
    turni_mattino = coverage['morning'] * num_days
    turni_pomeriggio = coverage['afternoon'] * num_days
    turni_notte = coverage['night'] * num_days
    turni_totali = turni_mattino + turni_pomeriggio + turni_notte

    print(f"   Mattino: {turni_mattino} turni")
    print(f"   Pomeriggio: {turni_pomeriggio} turni")
    print(f"   Notte: {turni_notte} turni")
    print(f"   TOTALE: {turni_totali} turni")

    # Calcola capacità teorica
    print(f"\n💪 CAPACITÀ TEORICA:")
    ore_totali = sum(n.contracted_hours for n in nurses)
    turni_teorici = ore_totali // 8
    print(f"   Ore contrattuali totali: {ore_totali}h")
    print(f"   Turni teorici massimi: {turni_teorici}")
    print(f"   Margine teorico: {turni_teorici - turni_totali} turni ({(turni_teorici - turni_totali) * 8}h)")

    # Analisi vincoli critici
    print(f"\n⚠️  VINCOLI CRITICI:")

    # 1. Weekend liberi
    weekend_constraint = next((c for c in hard_constraints if c["type"] == "weekend_rest_monthly"), None)
    if weekend_constraint:
        free_weekends = weekend_constraint["params"]["free_weekends"]
        print(f"\n   1. WEEKEND LIBERI: {free_weekends} per infermiere")
        giorni_weekend_totali = num_weekends * 2  # sabato + domenica
        giorni_weekend_liberi_richiesti = free_weekends * 2 * len(nurses)
        giorni_weekend_lavorabili = giorni_weekend_totali * len(nurses) - giorni_weekend_liberi_richiesti
        turni_weekend_necessari = (coverage['morning'] + coverage['afternoon'] + coverage[
            'night']) * giorni_weekend_totali

        print(f"      Giorni weekend totali: {giorni_weekend_totali}")
        print(f"      Giorni-persona weekend disponibili: {giorni_weekend_lavorabili}")
        print(f"      Turni weekend necessari: {turni_weekend_necessari}")
        if giorni_weekend_lavorabili < turni_weekend_necessari:
            print(f"      ❌ IMPOSSIBILE! Servono {turni_weekend_necessari - giorni_weekend_lavorabili} turni in più")
        else:
            print(f"      ✅ Fattibile con margine di {giorni_weekend_lavorabili - turni_weekend_necessari}")

    # 2. Notti con smonto
    if any(c["type"] in ["mandatory_smonto_after_night", "mandatory_rest_after_smonto"] for c in hard_constraints):
        print(f"\n   2. VINCOLO NOTTE→SMONTO→RIPOSO:")
        print(f"      Ogni notte richiede 3 giorni (N + S + R)")
        print(f"      {turni_notte} notti → {turni_notte * 3} giorni-persona necessari")
        giorni_persona_totali = len(nurses) * num_days
        print(f"      Giorni-persona totali: {giorni_persona_totali}")
        print(f"      Solo per le notti servono: {(turni_notte * 3 / giorni_persona_totali) * 100:.1f}% della capacità")

    # 3. Bilanciamento turni
    balance_constraint = next((c for c in hard_constraints if c["type"] == "shift_balance_morning_afternoon"), None)
    if balance_constraint:
        max_disc = balance_constraint["params"]["max_discrepancy"]
        print(f"\n   3. BILANCIAMENTO M/P: max discrepanza {max_disc * 100:.0f}%")
        turni_medi = (turni_mattino + turni_pomeriggio) / (2 * len(nurses))
        print(f"      Turni M+P medi per infermiere: {turni_medi:.1f}")
        print(f"      Range ammesso: {turni_medi * (1 - max_disc):.1f} - {turni_medi * (1 + max_disc):.1f}")

    # 4. Max notti mensili
    max_nights_constraint = next((c for c in hard_constraints if c["type"] == "max_nights_per_month"), None)
    if max_nights_constraint:
        max_nights = max_nights_constraint["params"]["max_monthly"]
        print(f"\n   4. MAX NOTTI MENSILI: {max_nights} per infermiere")
        max_notti_totali = max_nights * len(nurses)
        print(f"      Capacità notti totale: {max_notti_totali}")
        print(f"      Notti richieste: {turni_notte}")
        if max_notti_totali < turni_notte:
            print(f"      ❌ IMPOSSIBILE! Servono {turni_notte - max_notti_totali} notti in più")
        else:
            print(f"      ✅ Fattibile con margine di {max_notti_totali - turni_notte}")

    # Suggerimenti
    print(f"\n💡 SUGGERIMENTI PER RISOLVERE:")
    print("   1. Cambiare weekend_rest_monthly da '==' a '>=' (almeno 2 weekend)")
    print("   2. Rendere lo smonto dopo notte un soft constraint")
    print("   3. Aumentare max_nights_per_month o ridurre copertura notturna")
    print("   4. Rilassare il bilanciamento M/P (es. 0.8 invece di 0.65)")
    print("   5. Verificare che workload_balance_hard usi factor=1.0 per i mesi")


if __name__ == "__main__":
    analyze_monthly_feasibility()