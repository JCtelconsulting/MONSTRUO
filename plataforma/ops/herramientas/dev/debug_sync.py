import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "plataforma" / "legacy" / "code"))

# Configure logging to stdout
logging.basicConfig(level=logging.DEBUG)

from app.servicios import bank_sync

print("--- DEBUGGING SYNC ---")
try:
    # Force sync for Santander (check ID 8 based on previous outputs)
    # If ID 8 is Santander in local DB.
    # We can list banks first to be sure.
    from app.core.db import get_conn
    conn = get_conn()
    rows = conn.execute("SELECT id, name, laudus_account_id FROM bank_accounts").fetchall()
    
    santander_id = None
    chile_id = None
    
    print("Local Banks:")
    for r in rows:
        print(dict(r))
        if "Santander" in r['name']:
            santander_id = r['id']
        if "Chile" in r['name']:
            chile_id = r['id']

    if santander_id:
        print(f"\n>>> Attempting Sync for Santander (Local ID {santander_id})")
        res = bank_sync.sync_ledger_to_statement(santander_id)
        print("Result:", res)
    else:
        print("Santander not found locally.")

    if chile_id:
        print(f"\n>>> Attempting Sync for Chile (Local ID {chile_id})")
        # FORCE range check logic in sync (it defaults to current year)
        # We might need to modify bank_sync.py to accept custom dates OR just trust the output.
        res = bank_sync.sync_ledger_to_statement(chile_id)
        print("Result:", res)
        
        # Check DB directly
        print("Checking DB for inserted lines...")
        rows = conn.execute("SELECT count(*) as c FROM bank_statement_lines l JOIN bank_statements s ON l.statement_id = s.id WHERE s.bank_account_id = ?", (chile_id,)).fetchone()
        print(f"Lines in DB for Chile ({chile_id}): {rows['c']}")

except Exception as e:
    print("\nEXCEPTION CAUGHT:")
    print(e)
    import traceback
    traceback.print_exc()
