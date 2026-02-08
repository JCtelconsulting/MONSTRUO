import sys
import hashlib
from datetime import datetime, date
from pathlib import Path
from dotenv import load_dotenv
import requests

# Setup path
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "code"))

from app.core.db import get_conn
from app.integraciones.laudus import LaudusClient

def compute_hash(date_str, amount, description, doc_num):
    raw = f"{date_str}|{amount}|{description}|{doc_num}"
    return hashlib.sha256(raw.encode()).hexdigest()

def get_laudus_accounts_map(client):
    """Returns a dict {accountId: fullCode}"""
    url = f"{client.base_url}/accounting/accounts/list"
    # Campos que demostraron funcionar en nuestro probe result
    payload = {
        "skip": 0, 
        "take": 2000,
        "fields": ["accountId", "accountNumber"] 
    }
    try:
        resp = requests.post(url, json=payload, headers=client._get_headers(), timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return {item['accountId']: item.get('accountNumber') for item in data}
    except Exception as e:
        print(f"Error fetching account map: {e}")
    return {}

def sync_ledger_to_statement(bank_account_id=None, days_back=30):
    client = LaudusClient()
    if not client.login():
        raise Exception("Login Laudus failed")

    # 1. Mapa de codigos contables
    acc_map = get_laudus_accounts_map(client)
    
    conn = get_conn()
    try:
        # 2. Obtener cuentas bancarias locales
        query = "SELECT id, laudus_account_id, name FROM bank_accounts WHERE is_active=1"
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
                print(f"WARN: Banco {b['name']} (ID {laudus_id}) no tiene codigo contable mapeado.")
                continue

            # 3. Fetch Ledger
            today = date.today()
            # Simplificacion: traer todo el año actual o parametro
            start_date = f"{today.year}-01-01" 
            end_date = f"{today.year}-12-31"

            print(f"Syncing Bank {b['name']} (Code {acc_code}) range {start_date} to {end_date}")

            ledger_url = f"{client.base_url}/accounting/ledger"
            params = {
                "accountNumberFrom": acc_code,
                "accountNumberTo": acc_code,
                "from": start_date,
                "to": end_date
            }
            
            resp = requests.get(ledger_url, params=params, headers=client._get_headers(), timeout=60)
            if resp.status_code != 200:
                print(f"Error fetching ledger: {resp.status_code} {resp.text}")
                continue
                
            movements = resp.json()
            if not movements:
                continue
                
            # 4. Create Statement Header (one per month/year or generic 'Laudus Sync')
            # Estrategia: "Laudus Sync Snapshot"
            stmt_query = """
                INSERT INTO bank_statements 
                (bank_account_id, filename, upload_date, period, status)
                VALUES (?, ?, datetime('now'), ?, 'processed')
                RETURNING id
            """
            # Check if we already have a sync holder for today? 
            # For simplicity, creates new one or we could append. 
            # Lets create one "Laudus Sync {Date}"
            filename = f"SYNC_LAUDUS_{today.isoformat()}"
            period = f"{today.year}"
            
            # Insert Statement
            cur = conn.execute(stmt_query, (local_id, filename, period))
            stmt_id = cur.fetchone()['id']
            
            lines_inserted = 0
            
            for mov in movements:
                # Map fields
                # Laudus: date, description, debit, credit, journalEntryId
                m_date = mov.get('date', '')[:10] # 2025-12-31T00...
                desc = mov.get('description', '')
                doc_num = str(mov.get('journalEntryId', ''))
                
                # Debit = Cargo (Salida), Credit = Abono (Entrada) ? 
                # En Banco: Debit es Entrada (Debe), Credit es Salida (Haber)?
                # Cuidado: Contabilidad vs Banco es espejo.
                # En Contabilidad Activo Banco: Debe (Debit) aumenta, Haber (Credit) disminuye.
                # En Cartola Banco: Abono (Credit) aumenta, Cargo (Debit) disminuye.
                # Entonces: 
                # Laudus Debit (Aumento de activo) ~= Cartola Abono (Credit)
                # Laudus Credit (Disminucion activo) ~= Cartola Cargo (Debit)
                
                # Mapping:
                deposit = mov.get('debit', 0)  # Aumento saldo
                withdrawal = mov.get('credit', 0) # Disminucion saldo
                
                row_hash = compute_hash(m_date, (deposit - withdrawal), desc, doc_num)
                
                line_q = """
                INSERT INTO bank_statement_lines
                (bank_statement_id, date, description, document_number, amount_out, amount_in, balance, row_hash)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(row_hash) DO NOTHING
                """
                conn.execute(line_q, (stmt_id, m_date, desc, doc_num, withdrawal, deposit, row_hash))
                lines_inserted += 1
                
            conn.commit()
            results.append({"bank": b['name'], "lines": lines_inserted})
            
        return results
        
    finally:
        conn.close()

if __name__ == "__main__":
    print(sync_ledger_to_statement())
