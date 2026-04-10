import sys

sys.path.append("/srv/monstruo_dev/code")

from app.core import sales_service

try:
    print("Testing list_invoices...")
    result = sales_service.list_invoices(limit=50)
    found = False
    for inv in result["items"]:
        if inv["id"] in [64, 65]:
            found = True
            print(
                f"ID: {inv['id']}, External_ID: {inv.get('external_id')}, Origin: {inv.get('origin')}"
            )

    if not found:
        print("Invoices 64/65 not found in list.")

except Exception as e:
    print(f"Error: {e}")
