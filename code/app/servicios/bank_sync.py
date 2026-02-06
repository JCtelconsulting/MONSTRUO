import hashlib
from datetime import datetime, date
import requests
from app.core.db import get_conn
from app.integraciones.laudus import LaudusClient


def compute_hash(date_str, amount, description, doc_num):
    raw = f"{date_str}|{amount}|{description}|{doc_num}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_laudus_accounts_map(client):
    """Returns a dict {accountId: fullCode}"""
    url = f"{client.base_url}/accounting/accounts/list"
    payload = {"skip": 0, "take": 2000, "fields": ["accountId", "accountNumber"]}
    try:
        resp = requests.post(
            url, json=payload, headers=client._get_headers(), timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            return {item["accountId"]: item.get("accountNumber") for item in data}
    except Exception as e:
        print(f"Error fetching account map: {e}")
    return {}


def sync_ledger_to_statement(bank_account_id=None):
    client = LaudusClient()
    if not client.login():
        raise ValueError("Login Laudus failed")

    # 1. Mapa de codigos contables
    acc_map = get_laudus_accounts_map(client)

    conn = get_conn()
    try:
        # 2. Obtener cuentas bancarias locales
        query = (
            "SELECT id, laudus_account_id, name FROM bank_accounts WHERE is_active=1"
        )
        if bank_account_id:
            query += f" AND id={bank_account_id}"

        banks = conn.execute(query).fetchall()

        results = []

        for b in banks:
            local_id = b["id"]
            laudus_id = b["laudus_account_id"]

            # Buscar codigo contable
            acc_code = acc_map.get(laudus_id)
            if not acc_code:
                print(
                    f"WARN: Banco {b['name']} (ID {laudus_id}) no tiene codigo contable mapeado."
                )
                continue

            # 3. Fetch Ledger
            today = date.today()
            # Default: Current Year AND Previous Year to ensure coverage
            start_date = f"{today.year - 1}-01-01"
            end_date = f"{today.year}-12-31"

            # Use params that yielded 200 OK in probe
            ledger_url = f"{client.base_url}/accounting/ledger"
            params = {
                "accountNumberFrom": acc_code,
                "accountNumberTo": acc_code,
                "startDate": start_date,
                "endDate": end_date,
            }

            resp = requests.get(
                ledger_url, params=params, headers=client._get_headers(), timeout=60
            )
            if resp.status_code != 200:
                print(f"Error fetching ledger: {resp.status_code} {resp.text}")
                continue

            movements = resp.json()
            if not movements:
                results.append(
                    {"bank": b["name"], "lines": 0, "status": "no_movements"}
                )
                continue

            # 4. Create Statement Header
            filename = f"SYNC_LAUDUS_{today.isoformat()}"

            # Insert Statement
            # Schema: bank_account_id, filename, uploaded_at, uploaded_by, period_start, period_end, status
            stmt_query = """
                INSERT INTO bank_statements 
                (bank_account_id, filename, uploaded_at, uploaded_by, period_start, period_end, status)
                VALUES (?, ?, ?, 'system', ?, ?, 'processed')
                RETURNING id
            """
            cur = conn.execute(
                stmt_query,
                (local_id, filename, datetime.now().isoformat(), start_date, end_date),
            )
            stmt_id = cur.fetchone()["id"]

            lines_inserted = 0

            for mov in movements:
                m_date = mov.get("date", "")[:10]
                desc = mov.get("description", "")
                doc_num = str(mov.get("journalEntryId", ""))

                deposit = mov.get("debit", 0)
                withdrawal = mov.get("credit", 0)

                # Schema: statement_id, date, description, document_number, amount, balance, hash
                # amount: Positivo (Deposit/Abono), Negativo (Withdrawal/Cargo)

                # Logic: Laudus Debit? Credit?
                # We need to ensure sign is correct.
                # Usually: Debit (Debe) = Increase Asset = Deposit in Bank.
                # Credit (Haber) = Decrease Asset = Withdrawal from Bank.

                net_amount = deposit - withdrawal
                row_hash = compute_hash(m_date, net_amount, desc, doc_num)

                line_q = """
                INSERT INTO bank_statement_lines
                (statement_id, date, description, document_number, amount, balance, hash)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(hash) DO NOTHING
                """
                conn.execute(
                    line_q, (stmt_id, m_date, desc, doc_num, net_amount, row_hash)
                )
                lines_inserted += 1

            conn.commit()
            results.append(
                {
                    "bank": b["name"],
                    "lines": lines_inserted,
                    "status": "synced",
                    "statement_id": stmt_id,
                }
            )

        return results

    finally:
        conn.close()
