import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app.core import tickets_service, db
import json

def debug_list():
    print("Testing tickets_service.list_tickets()...")
    try:
        # Simulate default call from UI
        result = tickets_service.list_tickets(limit=100, offset=0)
        print(f"Total tickets returned: {len(result['items'])}")
        for t in result['items']:
            print(f"ID: {t['id']} | Codigo: {t['codigo']} | Titulo: {t['titulo']} | Estado: {t['estado']} | Asignado: {t['asignado_a']}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_list()
