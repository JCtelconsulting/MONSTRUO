import json
from datetime import datetime
from app.core import db

def run():
    """
    Sync logic: laudus_customers -> customers
    """
    print("Starting Customer Schema Sync...")
    conn = db.get_conn()
    try:
        # 1. Get raw customers
        raw_list = conn.execute("SELECT * FROM laudus_customers").fetchall()
        print(f"Found {len(raw_list)} raw customers")

        count = 0
        for raw in raw_list:
            laudus_id = raw['laudus_customer_id']
            rut = (raw['vat_id'] or "").strip()
            name = raw['name'] or raw['legal_name']
            name = (name or "").strip()
            
            # Extract info from JSON if available
            email = None
            city = None
            phone = None
            category = "General"
            
            try:
                data = json.loads(raw['raw_json']) if raw['raw_json'] else {}
                email = data.get('email')
                city = data.get('city')
                phone = data.get('phone')
            except:
                pass

            # Skip invalid rows
            if not rut or not name:
                continue

            # Upsert into main customers table
            # Check by External ID first, then RUT
            exists = conn.execute("SELECT id FROM customers WHERE external_id = ?", (str(laudus_id),)).fetchone()
            if not exists:
                exists = conn.execute("SELECT id FROM customers WHERE rut = ?", (rut,)).fetchone()
            
            now = db.now_utc_iso()
            
            if exists:
                conn.execute("""
                    UPDATE customers 
                    SET name=?, rut=?, email=?, city=?, phone=?, external_id=?, updated_at=?, is_active=1
                    WHERE id=?
                """, (name, rut, email, city, phone, str(laudus_id), now, exists['id']))
            else:
                conn.execute("""
                    INSERT INTO customers (external_id, name, rut, email, city, phone, category, updated_at, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (str(laudus_id), name, rut, email, city, phone, category, now))
            
            count += 1
            
        conn.commit()
        print(f"Synced {count} customers successfully.")
        
    except Exception as e:
        print(f"Error syncing customers: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run()
