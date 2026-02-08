#!/usr/bin/env python3
"""
Debug: Inspeccionar estado de la BD después de carga CSV
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "code"))

from app.core.db import get_conn

def debug_statements():
    conn = get_conn()
    
    try:
        print("=" * 60)
        print("STATEMENTS (Cartolas)")
        print("=" * 60)
        
        rows = conn.execute("""
            SELECT id, bank_account_id, filename, uploaded_at, 
                   (SELECT COUNT(*) FROM bank_statement_lines WHERE statement_id = s.id) as line_count
            FROM bank_statements s
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()
        
        for r in rows:
            print(f"ID: {r['id']} | Bank: {r['bank_account_id']} | File: {r['filename'][:40]} | Lines: {r['line_count']}")
        
        print("\n" + "=" * 60)
        print("SAMPLE LINES - CSV (uploaded)")
        print("=" * 60)
        
        csv_stmt = conn.execute("""
            SELECT id FROM bank_statements 
            WHERE filename NOT LIKE 'SYNC_LAUDUS%'
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        
        if csv_stmt:
            lines = conn.execute("""
                SELECT date, description, document_number, amount
                FROM bank_statement_lines
                WHERE statement_id = %s
                LIMIT 5
            """, (csv_stmt['id'],)).fetchall()
            
            print(f"Statement ID: {csv_stmt['id']}")
            for l in lines:
                print(f"  {l['date']} | {l['description'][:30]:30} | Doc: {l['document_number']:10} | Amt: {l['amount']:12.2f}")
        else:
            print("No CSV statement found!")
        
        print("\n" + "=" * 60)
        print("SAMPLE LINES - LAUDUS (synced)")
        print("=" * 60)
        
        laudus_stmt = conn.execute("""
            SELECT id FROM bank_statements 
            WHERE filename LIKE 'SYNC_LAUDUS%'
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        
        if laudus_stmt:
            lines = conn.execute("""
                SELECT date, description, document_number, amount
                FROM bank_statement_lines
                WHERE statement_id = %s
                LIMIT 5
            """, (laudus_stmt['id'],)).fetchall()
            
            print(f"Statement ID: {laudus_stmt['id']}")
            for l in lines:
                print(f"  {l['date']} | {l['description'][:30]:30} | Doc: {l['document_number']:10} | Amt: {l['amount']:12.2f}")
        else:
            print("No LAUDUS statement found!")
        
        print("\n" + "=" * 60)
        print("MATCHING CANDIDATES TEST")
        print("=" * 60)
        
        if csv_stmt and laudus_stmt:
            # Tomar primera línea del CSV
            csv_line = conn.execute("""
                SELECT * FROM bank_statement_lines
                WHERE statement_id = %s
                LIMIT 1
            """, (csv_stmt['id'],)).fetchone()
            
            print(f"\nLooking for match for CSV line:")
            print(f"  Date: {csv_line['date']}, Amount: {csv_line['amount']}, Doc: {csv_line['document_number']}")
            
            # Buscar candidatos en Laudus
            candidates = conn.execute("""
                SELECT l.*, s.filename 
                FROM bank_statement_lines l
                JOIN bank_statements s ON l.statement_id = s.id
                WHERE s.bank_account_id = (SELECT bank_account_id FROM bank_statements WHERE id = %s)
                AND s.id != %s
                AND l.amount = %s
            """, (csv_stmt['id'], csv_stmt['id'], csv_line['amount'])).fetchall()
            
            print(f"\n  Found {len(candidates)} candidates with same amount:")
            for c in candidates[:3]:
                print(f"    {c['date']} | {c['description'][:25]} | {c['amount']} | From: {c['filename'][:30]}")
        
    finally:
        conn.close()

if __name__ == "__main__":
    debug_statements()
