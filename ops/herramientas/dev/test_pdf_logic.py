import sys
import os

# Ensure we can import app
sys.path.append("/srv/monstruo_dev/code")

# Mock current working dir so .env loads if needed (though we might have issues with dotenv)
os.chdir("/srv/monstruo_dev/code")

try:
    from app.core import db

    print("DB module imported.")

    # Test connection
    conn = db.get_conn()
    print("DB Connection successful.")

    remote_id = "E00000697"
    final_id = remote_id

    print(f"Testing resolution for ID {remote_id}...")

    # Heuristic: Resolve if ID is alphanumeric (like E00000697) or small local ID
    needs_resolution = not remote_id.isdigit() or int(remote_id) < 100000

    if needs_resolution:
        print(f"DEBUG PDF: Resolving potential local ID {remote_id}...")
        try:
            local_inv = None

            # A) If it's a digit, look up by local ID first
            if remote_id.isdigit():
                cur = conn.execute(
                    "SELECT external_id, customer_id, total_final, created_at FROM invoices WHERE id = %s",
                    (remote_id,),
                )
                local_inv = cur.fetchone()

            # B) If not found or alphanumeric, look up by external_id
            if not local_inv:
                cur = conn.execute(
                    "SELECT external_id, customer_id, total_final, created_at FROM invoices WHERE external_id = %s",
                    (remote_id,),
                )
                local_inv = cur.fetchone()

            # 1. Check if we found a local record
            if local_inv:
                print(f"DEBUG PDF: Found local record: {local_inv}")

                # If the record itself has a valid numeric external_id that IS NOT the one we started with
                if (
                    local_inv["external_id"]
                    and str(local_inv["external_id"]).isdigit()
                    and str(local_inv["external_id"]) != str(remote_id)
                ):
                    final_id = local_inv["external_id"]
                    print(f"DEBUG PDF: Resolved to numeric external_id {final_id}")
                else:
                    # 2. Fuzzy match in laudus_invoices
                    print(f"DEBUG PDF: No direct numeric ID, fuzzy matching...")
                    cust_id = local_inv["customer_id"]
                    total = local_inv["total_final"]
                    date_ts = local_inv["created_at"]

                    # DEBUG: Broad search to see what exists
                    print(
                        f"DEBUG: Searching broadly for Cust={cust_id}, Total={total}..."
                    )
                    broad_query = """
                        SELECT laudus_invoice_id, customer_id, total_amount, doc_date 
                        FROM laudus_invoices 
                        WHERE TRIM(customer_id) = TRIM(%s)
                        AND ABS(total_amount - %s) < 50.0
                        ORDER BY doc_date DESC
                    """
                    cur = conn.execute(broad_query, (cust_id, total))
                    candidates = cur.fetchall()
                    print(f"DEBUG: Found {len(candidates)} broad candidates:")
                    for cand in candidates:
                        print(f" - {cand}")

                    # Original query for testing result
                    query = """
                        """
                    # NOTE: In test script I'm fetching more fields to debug
                    cur = conn.execute(query, (cust_id, total, date_ts, date_ts))
                    results = cur.fetchall()
                    print(f"DEBUG PDF: Found {len(results)} potential fuzzy matches.")
                    for r in results:
                        print(f" - Candidate: {r}")

                    if results:
                        final_id = results[0]["laudus_invoice_id"]
                        print(f"DEBUG PDF: Fuzzy match selected remote ID {final_id}")
            else:
                print("DEBUG PDF: ID not found in local invoices.")
        except Exception as e:
            print(f"DEBUG PDF: Resolution error: {e}")
        finally:
            conn.close()

    print(f"Final Resolved ID: {final_id}")

except Exception as e:
    print(f"CRITICAL ERROR: {e}")
