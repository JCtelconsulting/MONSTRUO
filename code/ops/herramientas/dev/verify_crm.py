from app.core import db, crm_service

def verify():
    conn = db.get_conn()
    try:
        # 1. Ensure test customer
        rut = "99.999.999-K"
        conn.execute("INSERT OR IGNORE INTO customers (rut, name, is_active, updated_at) VALUES (?, ?, 1, ?)", 
                     (rut, "Cliente Test CRM", db.now_utc_iso()))
        
        cur = conn.execute("SELECT id FROM customers WHERE rut = ?", (rut,))
        cust_id = cur.fetchone()[0]
        print(f"Customer ID: {cust_id}")
        
        # 2. Add Interaction
        print("Testing add_interaction...")
        res = crm_service.add_interaction(cust_id, "nota", "Prueba de nota automática", "verification_script")
        print(f"Interaction created: {res['id']}")
        
        # 3. Get Timeline
        print("Testing get_timeline...")
        timeline = crm_service.get_timeline(cust_id)
        if len(timeline) > 0 and timeline[0]['content'] == "Prueba de nota automática":
            print("PASS: Timeline ok")
        else:
            print("FAIL: Timeline mismatch")
            
        # 4. Account Status (Mock invoice if needed, but lets just check structure)
        print("Testing get_account_status...")
        status = crm_service.get_account_status(cust_id)
        print(f"Account Status: {status}")
        
        conn.commit()
    finally:
        conn.close()

if __name__ == "__main__":
    verify()
