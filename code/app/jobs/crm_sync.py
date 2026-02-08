"""
CRM Sync Job.
Sincroniza clientes desde Laudus hacia Monstruo.
"""
from app.core import db
from app.integraciones.laudus import LaudusClient
import json

async def sync_customers(payload: dict = None):
    """
    Trae clientes de Laudus y actualiza tabla customers.
    """
    print("[CRM] Starting Customer Sync...")
    client = LaudusClient()
    
    # Check health first
    health = client.get_health()
    if health.get("status") != "ok":
         print(f"[CRM] Laudus not healthy: {health}")
         return
         
    raw_customers = client.get_all_customers()
    if not raw_customers:
        print("[CRM] No customers found or API error.")
        return
        
    print(f"[CRM] Fetched {len(raw_customers)} raw customers from Laudus. Processing...")
    
    conn = db.get_conn()
    updated_count = 0
    created_count = 0
    
    try:
        now = db.now_utc_iso()
        
        for c in raw_customers:
            # Map fields. Laudus fields might be: customerId, legalName, VATId, address, ...
            # Assume structure:
            ext_id = str(c.get("customerId", ""))
            rut = c.get("VATId", "")
            name = c.get("legalName") or c.get("fantasyName") or "Sin Nombre"
            fantasy = c.get("fantasyName", "")
            address = c.get("address", "")
            city = c.get("city", "")
            category = c.get("category", {}).get("name", "") if isinstance(c.get("category"), dict) else str(c.get("category", ""))
            email = c.get("email", "")
            phone = c.get("phone", "")
            
            if not rut:
                continue # Skip invalid
                
            # Upsert by external_id
            # First check if exists
            exists = conn.execute("SELECT id FROM customers WHERE external_id = ?", (ext_id,)).fetchone()
            
            if exists:
                conn.execute("""
                    UPDATE customers 
                    SET rut=?, name=?, fantasy_name=?, address=?, city=?, category=?, email=?, phone=?, updated_at=?
                    WHERE external_id=?
                """, (rut, name, fantasy, address, city, category, email, phone, now, ext_id))
                updated_count += 1
            else:
                conn.execute("""
                    INSERT INTO customers (rut, name, fantasy_name, address, city, category, email, phone, external_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (rut, name, fantasy, address, city, category, email, phone, ext_id, now))
                created_count += 1
                
        conn.commit()
        print(f"[CRM] Sync Complete. Created: {created_count}, Updated: {updated_count}")
        
    finally:
        conn.close()
