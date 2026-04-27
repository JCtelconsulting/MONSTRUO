from typing import List, Optional, Dict, Any
from plataforma.core import db
from erp import sales_service  # We'll use list_invoices
from datetime import datetime

def get_account_status(customer_id: str) -> Dict[str, Any]:
    """
    Calcula deuda total y vencida basándose en facturas.
    """
    conn = db.get_conn()
    try:
        # 1. Obtener facturas (Locales + Laudus + Parrotfy)
        invoices = sales_service.list_invoices(customer_id=customer_id, status="ISSUED", limit=500)
        
        total_debt = 0.0
        overdue_debt = 0.0
        now = datetime.now()
        
        items = []
        for inv in invoices:
             # Calculate balance if available, else total
             # En local 'total_final', en Laudus 'total_final' (mapped from amount).
             # Assuming 'ISSUED' means unpaid or partially paid.
             
             amount = float(inv.get("total_final", 0))
             # TODO: Check if partial payment exists (not implemented effectively universally yet)
             
             total_debt += amount
             
             # Check due date (mocked for now as created_at + 30 days if not present)
             created_at_str = str(inv.get("created_at", ""))[:10]
             is_overdue = False
             
             # Simple logic: if created > 30 days ago, it's overdue
             try:
                 created_dt = datetime.strptime(created_at_str, "%Y-%m-%d")
                 age_days = (now - created_dt).days
                 if age_days > 30:
                     overdue_debt += amount
                     is_overdue = True
             except:
                 pass
                 
             items.append({
                 "id": inv.get("id"),
                 "number": inv.get("id"), # Or explicit number
                 "amount": amount,
                 "date": created_at_str,
                 "origin": inv.get("origin", "LOCAL"),
                 "is_overdue": is_overdue
             })
             
        return {
            "total_debt": total_debt,
            "overdue_debt": overdue_debt,
            "invoices": items
        }
    finally:
        conn.close()

def add_interaction(customer_id: int, type: str, content: str, user_id: str) -> Dict[str, Any]:
    conn = db.get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not exists:
            raise ValueError("Customer not found")
        now = db.now_utc_iso()
        cursor = conn.execute("""
            INSERT INTO crm_interactions (customer_id, type, content, created_by, created_at)
            VALUES (?, ?, ?, ?, ?) RETURNING id
        """, (customer_id, type, content, user_id, now))
        
        row = cursor.fetchone()
        row_id = row["id"] if row else None
        conn.commit()
        
        return {
            "id": row_id,
            "type": type,
            "content": content,
            "created_at": now,
            "created_by": user_id
        }
    finally:
        conn.close()

def get_timeline(customer_id: int) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        cursor = conn.execute("""
            SELECT * FROM crm_interactions 
            WHERE customer_id = ? 
            ORDER BY created_at DESC LIMIT 50
        """, (customer_id,))
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
