#!/usr/bin/env python3
"""
Debug detallado: ¿Por qué no hay matches?
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "code"))

from app.core.db import get_conn

def debug_why_no_matches():
    conn = get_conn()
    
    try:
        print("=" * 70)
        print("STEP 1: Identificar las cartolas")
        print("=" * 70)
        
        # CSV Statement (más reciente)
        csv_stmt = conn.execute("""
            SELECT id, bank_account_id, filename 
            FROM bank_statements 
            WHERE filename NOT LIKE 'SYNC_LAUDUS%'
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        
        if not csv_stmt:
            print("❌ No se encontró ninguna cartola CSV cargada")
            return
        
        print(f"✅ CSV Statement: ID={csv_stmt['id']}, File={csv_stmt['filename']}")
        
        # Laudus Statement (mismo banco, con líneas)
        laudus_stmt = conn.execute("""
            SELECT s.id, s.filename, COUNT(l.id) as line_count
            FROM bank_statements s
            LEFT JOIN bank_statement_lines l ON l.statement_id = s.id
            WHERE s.filename LIKE 'SYNC_LAUDUS%%'
            AND s.bank_account_id = %s
            GROUP BY s.id, s.filename
            HAVING COUNT(l.id) > 0
            ORDER BY s.id DESC LIMIT 1
        """, (csv_stmt['bank_account_id'],)).fetchone()
        
        if not laudus_stmt:
            print("❌ No se encontró ninguna cartola SYNC_LAUDUS con líneas")
            return
        
        print(f"✅ Laudus Statement: ID={laudus_stmt['id']}, File={laudus_stmt['filename']}, Lines={laudus_stmt['line_count']}")
        
        print("\n" + "=" * 70)
        print("STEP 2: Comparar una línea específica")
        print("=" * 70)
        
        # Tomar primera línea del CSV
        csv_line = conn.execute("""
            SELECT date, description, document_number, amount
            FROM bank_statement_lines
            WHERE statement_id = %s
            ORDER BY date DESC
            LIMIT 1
        """, (csv_stmt['id'],)).fetchone()
        
        print(f"\n🔍 CSV Line:")
        print(f"   Fecha: {csv_line['date']}")
        print(f"   Desc: {csv_line['description']}")
        print(f"   Doc: {csv_line['document_number']}")
        print(f"   Monto: {csv_line['amount']}")
        
        # Buscar en Laudus con MISMO monto
        exact_matches = conn.execute("""
            SELECT l.date, l.description, l.document_number, l.amount
            FROM bank_statement_lines l
            WHERE l.statement_id = %s
            AND l.amount = %s
        """, (laudus_stmt['id'], csv_line['amount'])).fetchall()
        
        print(f"\n🔍 Buscando en Laudus con amount={csv_line['amount']}...")
        print(f"   Resultados: {len(exact_matches)}")
        
        if exact_matches:
            for m in exact_matches[:3]:
                print(f"   ✅ {m['date']} | {m['description'][:30]} | Doc:{m['document_number']} | Amt:{m['amount']}")
        else:
            print("   ❌ No se encontraron coincidencias exactas de monto")
            
            # Mostrar algunos amounts de Laudus para comparar
            print("\n   📊 Primeros 5 amounts en Laudus:")
            sample_laudus = conn.execute("""
                SELECT date, description, amount
                FROM bank_statement_lines
                WHERE statement_id = %s
                ORDER BY date DESC
                LIMIT 5
            """, (laudus_stmt['id'],)).fetchall()
            
            for s in sample_laudus:
                print(f"      {s['date']} | {s['description'][:25]:25} | {s['amount']:12.2f}")
        
        print("\n" + "=" * 70)
        print("STEP 3: Verificar signos de amounts")
        print("=" * 70)
        
        csv_stats = conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN amount > 0 THEN 1 END) as positivos,
                COUNT(CASE WHEN amount < 0 THEN 1 END) as negativos,
                COUNT(CASE WHEN amount = 0 THEN 1 END) as ceros
            FROM bank_statement_lines
            WHERE statement_id = %s
        """, (csv_stmt['id'],)).fetchone()
        
        laudus_stats = conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN amount > 0 THEN 1 END) as positivos,
                COUNT(CASE WHEN amount < 0 THEN 1 END) as negativos,
                COUNT(CASE WHEN amount = 0 THEN 1 END) as ceros
            FROM bank_statement_lines
            WHERE statement_id = %s
        """, (laudus_stmt['id'],)).fetchone()
        
        print(f"CSV Stats:    Total={csv_stats['total']}, Pos={csv_stats['positivos']}, Neg={csv_stats['negativos']}, Zero={csv_stats['ceros']}")
        print(f"Laudus Stats: Total={laudus_stats['total']}, Pos={laudus_stats['positivos']}, Neg={laudus_stats['negativos']}, Zero={laudus_stats['ceros']}")
        
        print("\n" + "=" * 70)
        print("CONCLUSIÓN")
        print("=" * 70)
        
        if exact_matches:
            print("✅ SÍ hay coincidencias de monto. El problema debe estar en otro lado.")
        else:
            print("❌ NO hay coincidencias de monto. Posibles causas:")
            print("   1. Los montos del CSV están invertidos (signo opuesto)")
            print("   2. El parser no está procesando correctamente Cargos/Abonos")
            print("   3. Los datos sintéticos no coinciden con los reales")
        
    finally:
        conn.close()

if __name__ == "__main__":
    debug_why_no_matches()
