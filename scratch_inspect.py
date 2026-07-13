import json

with open('ConspiracyMaster_Refactored.ipynb', 'r') as f:
    notebook = json.load(f)

for i, cell in enumerate(notebook['cells']):
    cell_text = "".join(cell.get('source', []))
    if 'hedged_suspicion_pipeline' in cell_text or 'hedged_suspicion' in cell_text and 'pipeline' in cell_text:
        print(f"--- Cell {i} ---")
        print(cell_text)
        print("="*40)
