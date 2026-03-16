
import os
import sys
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path

# /app/code/scripts/ -> /app/code
CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.append(str(CODE_ROOT))

from app.integraciones.laudus import LaudusClient
from app.core.env_loader import load_runtime_env


def _get_direct_conn():
    """Conexión directa a PostgreSQL con autocommit para evitar locks."""
    db_url = os.getenv("DB_URL", "")
    try:
        import psycopg
        conn = psycopg.connect(db_url, autocommit=True)
        return conn, 3
    except ImportError:
        pass
    try:
        import psycopg2
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        return conn, 2
    except ImportError:
        pass
    raise RuntimeError("No PostgreSQL driver available")


def sync_erp(days=60, verbose=False):
    """
    Sincroniza datos ERP (Clientes y Facturas) desde Laudus a la DB local.
    Usa conexión directa con autocommit para evitar bloqueos.
    """
    load_runtime_env(Path(__file__).resolve())

    print("--- Iniciando Sincronización ERP ---")
    client = LaudusClient()
    if not client.login():
        print("Error: No se pudo iniciar sesión en Laudus.")
        return

    conn, pg_ver = _get_direct_conn()
    print(f"DB conectada (psycopg{pg_ver}, autocommit=True)")
    cur = conn.cursor()

    try:
        # 1. Sincronizar Clientes
        print("Sincronizando Clientes...")
        customers = client.get_all_customers()
        count_cust = 0
        for c in customers:
            lid = str(c.get("customerId"))
            name = c.get("legalName") or c.get("name") or "Desconocido"
            vat = c.get("VATId") or ""
            now = datetime.utcnow().isoformat()

            cur.execute("SELECT id FROM laudus_customers WHERE laudus_customer_id = %s", (lid,))
            exists = cur.fetchone()
            if exists:
                cur.execute(
                    "UPDATE laudus_customers SET name=%s, vat_id=%s, synced_at=%s WHERE laudus_customer_id=%s",
                    (name, vat, now, lid)
                )
            else:
                cur.execute(
                    "INSERT INTO laudus_customers (laudus_customer_id, name, vat_id, synced_at) VALUES (%s, %s, %s, %s)",
                    (lid, name, vat, now)
                )
            count_cust += 1
        print(f"  → {count_cust} clientes sincronizados.")

        # 2. Sincronizar Facturas
        print(f"Sincronizando Facturas (últimos {days} días)...")
        invoices = client.list_sales_invoices(take=500)
        print(f"  → {len(invoices)} facturas encontradas en Laudus.")

        count_inv = 0
        skipped = 0
        cutoff = datetime.now() - timedelta(days=days)

        for idx, inv in enumerate(invoices):
            lid = str(inv.get("salesInvoiceId"))
            doc_date_str = inv.get("issuedDate")
            if not doc_date_str:
                skipped += 1
                continue

            try:
                doc_date = datetime.fromisoformat(doc_date_str.replace('Z', '+00:00'))
            except Exception:
                skipped += 1
                continue

            if doc_date < cutoff.replace(tzinfo=doc_date.tzinfo):
                skipped += 1
                continue

            # Obtener detalles completos
            time.sleep(0.3)
            details = client.get_invoice_details(lid)
            if not details:
                print(f"  ⚠ Sin detalles para {lid}, saltando.")
                skipped += 1
                continue

            totals = details.get("totals", {})
            total = totals.get("total", 0) if isinstance(totals, dict) else 0
            # Laudus no tiene "balance" directo; si no hay campo, asumir = total (no pagado)
            balance = totals.get("balance", total) if isinstance(totals, dict) else total
            is_paid = 1 if balance <= 0 else 0
            cust_id = str(details.get("customer", {}).get("customerId", ""))
            now = datetime.utcnow().isoformat()

            cur.execute("SELECT id FROM laudus_invoices WHERE laudus_invoice_id = %s", (lid,))
            exists = cur.fetchone()
            if exists:
                cur.execute(
                    """UPDATE laudus_invoices 
                       SET total_amount=%s, balance=%s, is_paid=%s, doc_date=%s, customer_id=%s, synced_at=%s 
                       WHERE laudus_invoice_id=%s""",
                    (total, balance, is_paid, doc_date_str, cust_id, now, lid)
                )
            else:
                cur.execute(
                    """INSERT INTO laudus_invoices 
                       (laudus_invoice_id, customer_id, doc_date, total_amount, balance, is_paid, synced_at) 
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (lid, cust_id, doc_date_str, total, balance, is_paid, now)
                )
            count_inv += 1
            if verbose or (count_inv % 10 == 0):
                print(f"  [{idx+1}/{len(invoices)}] {lid} total={total} balance={balance}")

        print(f"  → {count_inv} facturas sincronizadas, {skipped} saltadas.")

    except Exception as e:
        print(f"Error en sincronización: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()
        print("--- Sincronización Completa ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60, help="Días hacia atrás para facturas")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    sync_erp(days=args.days, verbose=args.verbose)
