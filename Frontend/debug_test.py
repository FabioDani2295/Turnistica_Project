"""
Debug test per identificare il problema specifico
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parser.nurse_loader import load_nurses
from parser.hard_constraint_loader import load_hard_constraints
from parser.soft_constraint_loader import load_soft_constraints
from model.scheduler import Scheduler

def test_full_flow():
    """Test del flusso completo che replica il frontend"""
    
    print("=== DEBUGGING FRONTEND FLOW ===")
    
    # Step 1: Carica dati come fa il frontend
    data_folder = "../data"
    try:
        nurses = load_nurses(os.path.join(data_folder, "nurses.json"))
        hard_constraints_file = load_hard_constraints(os.path.join(data_folder, "hard_constraints.json"))
        soft_constraints_file = load_soft_constraints(os.path.join(data_folder, "soft_constraints.json"))
        print(f"✅ Step 1: Loaded {len(nurses)} nurses, {len(hard_constraints_file)} hard constraints")
    except Exception as e:
        print(f"❌ Step 1 failed: {e}")
        return
    
    # Step 2: Simula session_state initialization
    session_state = {
        'hard_constraints': hard_constraints_file.copy(),
        'soft_constraints': soft_constraints_file.copy(),
        'hard_enabled': {i: True for i in range(len(hard_constraints_file))},
        'soft_enabled': {i: True for i in range(len(soft_constraints_file))}
    }
    print("✅ Step 2: Session state initialized")
    
    # Step 3: Simula aggiunta turno predefinito
    for i, constraint in enumerate(session_state['hard_constraints']):
        if constraint['type'] == 'predefined_shifts':
            constraint['params']['predefined'] = [
                {
                    'nurse_name': nurses[0].name,
                    'day': 5,
                    'shift_type': 'MORNING',
                    'reason': 'Test frontend'
                }
            ]
            print(f"✅ Step 3: Added predefined shift for {nurses[0].name}")
            break
    
    # Step 4: Simula get_active_hard_constraints
    def get_active_hard_constraints():
        active_constraints = []
        if 'hard_constraints' not in session_state:
            return []
        
        for i, constraint in enumerate(session_state['hard_constraints']):
            if session_state['hard_enabled'].get(i, True):
                active_constraints.append(constraint)
        return active_constraints
    
    active_hard = get_active_hard_constraints()
    print(f"✅ Step 4: Got {len(active_hard)} active hard constraints")
    
    # Step 5: Verifica constraint types
    constraint_types = [c['type'] for c in active_hard]
    print("Constraint types:", constraint_types)
    
    # Step 6: Test scheduler creation (il punto dove crasha)
    try:
        scheduler = Scheduler(
            nurses=nurses,
            hard_constraints=active_hard,
            soft_constraints=soft_constraints_file,
            num_days=30,
            start_weekday=0
        )
        print("✅ Step 6: Scheduler created successfully")
        
        # Step 7: Test solve
        status, schedule = scheduler.solve(max_seconds=2)
        print(f"✅ Step 7: Solve completed with status {status}")
        
    except Exception as e:
        print(f"❌ Step 6/7 failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Debug: verifica i vincoli uno per uno
        print("\n=== DETAILED CONSTRAINT DEBUG ===")
        for i, constraint in enumerate(active_hard):
            print(f"Constraint {i+1}: {constraint['type']}")
            print(f"  Params: {constraint.get('params', {})}")
            
            # Test individual constraint
            try:
                single_constraint_list = [constraint]
                test_scheduler = Scheduler(
                    nurses=nurses,
                    hard_constraints=single_constraint_list,
                    soft_constraints=[],
                    num_days=7,
                    start_weekday=0
                )
                print(f"  ✅ Individual constraint works")
            except Exception as ce:
                print(f"  ❌ Individual constraint fails: {ce}")

if __name__ == "__main__":
    test_full_flow()