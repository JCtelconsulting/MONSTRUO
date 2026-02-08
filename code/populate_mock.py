from app.core import db
from datetime import datetime, timedelta
import random

def populate_mock_data():
    conn = db.get_conn()
    try:
        customers = ['CUST-001', 'CUST-002', 'CUST-003', 'CUST-004', 'CUST-005']
        
        # Clear existing
        conn.execute("DELETE FROM invoices")
        
        # Generate invoices
        for i in range(20):
            cust = random.choice(customers)
            # Random date within last 90 days
            days_ago = random.randint(1, 100)
            issued_at = (datetime.now() - timedelta(days=days_ago)).isoformat()
            
            amount = random.randint(100, 5000) * 1000
            
            conn.execute("""
                INSERT INTO invoices (customer_id, type, status, total_final, issued_at, created_at, updated_at, issuer_id)
                VALUES (%s, 'FACTURA', 'ISSUED', %s, %s, %s, %s, 'admin')
            """, (cust, amount, issued_at, issued_at, issued_at))
            
        conn.commit()
        print(f"✅ Generated 20 mock invoices for {len(customers)} customers")
        
    finally:
        conn.close()

if __name__ == "__main__":
    populate_mock_data()
