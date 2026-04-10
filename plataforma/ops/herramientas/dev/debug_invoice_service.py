import sys
import os
import json

# Add code dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "code")))

# Setup basic env if needed (usually done by uvicorn/main)
# We need to ensure db connection works
from app.core import db
from app.core import sales_service


def debug_invoice():
    conn = db.get_conn()
    try:
        # 1. Find the local ID for our test case (E00000697)
        # We know from previous steps it exists
        print("Finding local ID for external_id 'E00000697'...")
        cur = conn.execute("SELECT id FROM invoices WHERE external_id = 'E00000697'")
        row = cur.fetchone()

        if not row:
            print(
                "E00000697 not found by external_id. Searching for potential match (fuzzy search target)..."
            )
            # Fallback search if external_id is empty in DB
            # Customer 583, Total 260020
            cur = conn.execute(
                "SELECT id, external_id FROM invoices WHERE customer_id='583' AND ABS(total_final - 260020) < 1.0"
            )
            row = cur.fetchone()

        if not row:
            print("Could not find local invoice to test.")
            return

        local_id = row["id"]
        print(
            f"Testing get_invoice({local_id}) [Current External ID: {row.get('external_id')}]..."
        )

        # 2. Call the service function
        result = sales_service.get_invoice(local_id)

        # 3. Print keys relevant to the issue
        print("\n--- Service Result ---")
        if result:
            print(f"ID: {result.get('id')}")
            print(f"Origin: {result.get('origin')}")
            print(f"External ID: {result.get('external_id')}")
            print(f"Customer Name: {result.get('customer_name')}")
            print(f"Payment Term: {result.get('payment_term')}")
            print(f"Items Count: {len(result.get('items', []))}")
        else:
            print("Result is None")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    debug_invoice()
