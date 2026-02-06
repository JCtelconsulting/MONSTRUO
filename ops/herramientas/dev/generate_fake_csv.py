#!/usr/bin/env python3
"""
Genera un CSV sintético de cartola bancaria basado en datos reales de Laudus.
Introduce variaciones para demostrar el motor de matching.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import random
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "code"))

from app.core.db import get_conn

def generate_synthetic_csv(bank_account_id=2, output_file="cartola_sintetica.csv"):
    """
    Toma movimientos reales de Laudus y genera un CSV sintético.
    
    Estrategia:
    - 70% coinciden exactamente (para Match Exacto)
    - 20% coinciden en monto pero fecha +/- 1-3 días (para Match Fuzzy)
    - 10% son completamente diferentes (Sin Match)
    """
    conn = get_conn()
    
    try:
        # Obtener movimientos de Laudus para este banco
        query = """
        SELECT l.date, l.description, l.document_number, l.amount
        FROM bank_statement_lines l
        JOIN bank_statements s ON l.statement_id = s.id
        WHERE s.bank_account_id = %s
        AND s.filename LIKE 'SYNC_LAUDUS%%'
        ORDER BY l.date DESC
        LIMIT 30
        """
        rows = conn.execute(query, (bank_account_id,)).fetchall()
        
        if not rows:
            print("No hay datos de Laudus para generar CSV sintético.")
            return
        
        csv_lines = []
        # Header Santander format: Fecha;Sucursal;Descripción;N° Documento;Cargos;Abonos;Saldo
        csv_lines.append("Fecha;Sucursal;Descripción;N° Documento;Cargos;Abonos;Saldo")
        
        for idx, row in enumerate(rows):
            date_str = row['date']
            desc = row['description']
            doc = row['document_number'] or ''
            amount = row['amount']
            
            # Determinar categoría
            rand = random.random()
            
            if rand < 0.7:
                # 70% Match Exacto
                if amount >= 0:
                    # Abono (deposit) - SIN DECIMALES
                    csv_lines.append(f"{date_str};001;{desc};{doc};0;{int(amount)};0")
                else:
                    # Cargo (withdrawal) - SIN DECIMALES
                    csv_lines.append(f"{date_str};001;{desc};{doc};{int(abs(amount))};0;0")
            elif rand < 0.9:
                # 20% Match Fuzzy (fecha desplazada)
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                shift = random.randint(-3, 3)
                if shift == 0:
                    shift = 1
                new_dt = dt + timedelta(days=shift)
                new_date = new_dt.strftime("%Y-%m-%d")
                if amount >= 0:
                    csv_lines.append(f"{new_date};001;{desc};{doc};0;{int(amount)};0")
                else:
                    csv_lines.append(f"{new_date};001;{desc};{doc};{int(abs(amount))};0;0")
            else:
                # 10% Sin Match (monto diferente) - SIN DECIMALES
                new_amount = int(abs(amount) * random.uniform(0.5, 1.5))
                csv_lines.append(f"{date_str};001;MOVIMIENTO DESCONOCIDO;{doc};{new_amount};0;0")
        
        
        # Escribir CSV
        output_path = PROJECT_ROOT / output_file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(csv_lines))
        
        print(f"✅ CSV sintético generado: {output_path}")
        print(f"Total movimientos: {len(rows)}")
        print(f"Estimado - Exactos: ~{int(len(rows)*0.7)}, Fuzzy: ~{int(len(rows)*0.2)}, Sin Match: ~{int(len(rows)*0.1)}")
        print(f"\nAhora puedes subir este archivo en el ERP para probar el motor de conciliación.")
        
    finally:
        conn.close()

if __name__ == "__main__":
    generate_synthetic_csv()
