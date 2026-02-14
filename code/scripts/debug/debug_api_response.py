import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[2]
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from app.core import tickets_service, db
import json
from datetime import datetime

class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)

def debug_response():
    print("Simulating API JSON response for Ticket #17...")
    try:
        t = tickets_service.get_ticket(17)
        if not t:
            print("Ticket 17 not found!")
            return
            
        # Simulate FastAPIs JSON serialization
        json_output = json.dumps(t, cls=DateTimeEncoder, indent=2)
        print(json_output)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_response()
