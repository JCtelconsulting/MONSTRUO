import sys
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "code"))

# Force DB_URL for testing if needed, or use .env
from app.core.db import init_db, get_conn
from app.servicios.bank_parser import BankParser

def test_parser_santander():
    print("--- [TEST] BankParser Santander ---")
    csv_content = """Fecha;Sucursal;Descripción;N° Documento;Cargos;Abonos;Saldo
01/02/2026;Santiago;PAGO PROVEEDOR IMPORTADORA;123456;$150.000;;$1.000.000
02/02/2026;Santiago;TRANSFERENCIA DE CLIENTE;789012;;$500.000;$1.500.000
03/02/2026;Santiago;COMISION MANTENCION;000000;$5.990;;$1.494.010
"""
    results = BankParser.parse_santander_csv(csv_content)
    
    # Assertions
    assert len(results) == 3, f"Expected 3 lines, got {len(results)}"
    
    # Line 1: Cargo
    l1 = results[0]
    assert l1["amount"] == -150000.0, f"Expected -150000.0, got {l1['amount']}"
    assert l1["description"] == "PAGO PROVEEDOR IMPORTADORA"
    assert l1["date"] == "2026-02-01"

    # Line 2: Abono
    l2 = results[1]
    assert l2["amount"] == 500000.0
    
    print("SUCCESS: Parser output correct.")
    return results

def test_db_insert(lines):
    print("--- [TEST] DB Insert (Simulation) ---")
    init_db()
    conn = get_conn()
    try:
    # Create Dummy Bank Account if not exists
        conn.execute("INSERT INTO bank_accounts (id, name, laudus_account_id) VALUES (999, 'Test Bank', 9999) ON CONFLICT(id) DO NOTHING")
        
        # Insert Statement
        file_name = "test_cartola.csv"
        now = datetime.now().isoformat()
        
        cur = conn.execute("""
            INSERT INTO bank_statements (bank_account_id, filename, uploaded_at, uploaded_by) 
            VALUES (999, ?, ?, 'tester') RETURNING id
        """, (file_name, now))
        stmt_id = cur.fetchone()["id"]
        print(f"Created Statement ID: {stmt_id}")
        
        # Insert Lines
        inserted = 0
        for l in lines:
            try:
                conn.execute("""
                INSERT INTO bank_statement_lines (statement_id, date, description, document_number, amount, hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (stmt_id, l["date"], l["description"], l["document_number"], l["amount"], l["hash"]))
                inserted += 1
            except Exception as e:
                print(f"Insert error: {e}")
        
        conn.commit()
        print(f"Inserted {inserted} lines into DB.")
        
        # Verification Query
        row = conn.execute("SELECT count(*) as c FROM bank_statement_lines WHERE statement_id=?", (stmt_id,)).fetchone()
        assert row["c"] == 3
        
        print("SUCCESS: DB insertion verified.")
        
    finally:
        # Cleanup
        # conn.execute("DELETE FROM bank_statements WHERE id=?", (stmt_id,))
        # conn.execute("DELETE FROM bank_statement_lines WHERE statement_id=?", (stmt_id,))
        conn.commit()
        conn.close()

if __name__ == "__main__":
    lines = test_parser_santander()
    test_db_insert(lines)
