import json
from pathlib import Path

def load_data():
    with open(Path(__file__).parent.parent / 'data' / 'bomberos.json', encoding="utf-8") as f:
        return json.load(f)

BOMBEROS_DATA = load_data()
