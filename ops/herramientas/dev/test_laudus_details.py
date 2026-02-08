import sys
import os
import json

# Setup environment to run standalone
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "code")))

# Mock minimal env if needed, or rely on .env if loaded by app logic
# For this script we need to ensure we can import LaudusClient

try:
    from app.integraciones.laudus import LaudusClient

    print("LaudusClient imported.")
except ImportError as e:
    print(f"Error importing LaudusClient: {e}")
    sys.path.append("/srv/monstruo/code")
    from app.integraciones.laudus import LaudusClient

    print("LaudusClient imported after path fix.")


def test_details(invoice_id):
    client = LaudusClient()
    print(f"Fetching details for ID: {invoice_id}...")

    # Try to login first to ensure creds work
    if not client.login():
        print("Login failed. Check env vars.")
        return

    details = client.get_invoice_details(invoice_id)
    print("\n--- RAW DETAILS TOP LEVEL ---")
    for k, v in details.items():
        if k != "items":
            print(f"{k}: {v}")
    print("-------------------\n")

    print(f"Issued Date: {details.get('issuedDate')}")
    print(f"Due Date: {details.get('dueDate')}")
    print(f"Term (Payment Condition): {details.get('term')}")

    print("\n--- ALL KEYS ---")
    print(sorted(details.keys()))
    print("----------------\n")

    # Check for payment term specifically
    term = details.get("paymentTerm")
    print(f"Payment Term Field: {term}")
    if term and isinstance(term, dict):
        print(f"Description: {term.get('description')}")


if __name__ == "__main__":
    # Use the alphanumeric ID we know exists/was tested: E00000697
    # Or a numeric one if preferred.
    test_id = "E00000697"
    if len(sys.argv) > 1:
        test_id = sys.argv[1]

    test_details(test_id)
