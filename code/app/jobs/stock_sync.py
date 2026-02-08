"""
Stock Sync Job v2 (Laudus Source of Truth).
Sincroniza inventario desde Laudus.
Si hay diferencias, NO ajusta automáticamente: Crea un Ticket.
"""
from app.integraciones.laudus import LaudusClient
from app.core import bodega_service, tickets_service
from app.core import db

def sync_stock(payload: dict = None):
    """
    1. Trae datos de Laudus (Source of Truth).
    2. Upsert en tabla `products` (Catálogo).
    3. Compara stock. Si difiere => Crea Ticket "Discrepancia".
    """
    print("[STOCK] Starting Laudus Sync (Discrepancy Mode)...")
    client = LaudusClient()
    db.init_db()
    
    try:
        if not client.login():
            print("[STOCK] Laudus Login Failed. Aborting.")
            return

        # Obtener stock remoto
        resp = client.get_stock()
        if resp.get("error"):
            print(f"[STOCK] API Error: {resp.get('detail')}")
            return
            
        data = resp.get("products", [])
        if not isinstance(data, list):
             print("[STOCK] Format Error: Expected 'products' list from Laudus")
             return

        apply_stock = bool(payload.get("apply_stock")) if payload else False
        stats = {"upserted": 0, "discrepancies": 0, "tickets_created": 0, "stock_applied": 0}
        
        # Iterar productos
        for item in data:
            # Structure from Laudus: {sku, name, price, stock, cost...}
            sku = str(
                item.get("sku")
                or item.get("code")
                or item.get("productCode")
                or item.get("product_id")
                or item.get("productId")
                or ""
            ).strip()
            if not sku:
                continue
                
            name = item.get("name") or item.get("description") or item.get("sku") or sku or "Unknown Product"
            external_id = item.get("productId") or item.get("id") or None
            price = float(item.get("price") or item.get("unitPrice") or 0)
            cost = float(item.get("cost") or item.get("unitCost") or 0)
            remote_stock = int(item.get("stock") or item.get("stockQuantity") or item.get("quantity") or 0)
            
            # 1. Upsert Product (Catalog Sync) - Esto siempre se mantiene al día
            prod = bodega_service.create_or_update_product(
                sku=sku,
                name=name,
                key_props={
                    "price": price,
                    "cost": cost,
                    "external_id": str(external_id) if external_id is not None else None
                }
            )
            stats["upserted"] += 1
            
            # 2. Check Stock Drift
            current_local = int(prod["stock_current"])
            
            if apply_stock and current_local != remote_stock:
                diff = remote_stock - current_local
                # Ajuste directo para reflejar Laudus como fuente de verdad
                conn = db.get_conn()
                try:
                    now = db.now_utc_iso()
                    conn.execute(
                        "UPDATE products SET stock_current = ?, updated_at = ? WHERE sku = ?",
                        (remote_stock, now, sku)
                    )
                    if diff != 0:
                        conn.execute(
                            """INSERT INTO inventory_movements 
                               (product_id, quantity, type, reference, user_id, created_at)
                               VALUES ((SELECT id FROM products WHERE sku = ?), ?, 'SYNC', 'LAUDUS_SYNC', 'job:sync_stock', ?)""",
                            (sku, diff, now)
                        )
                    conn.commit()
                    stats["stock_applied"] += 1
                    current_local = remote_stock
                finally:
                    conn.close()

            if current_local != remote_stock:
                stats["discrepancies"] += 1
                diff = remote_stock - current_local
                
                # Check duplicates based on Title
                ticket_title = f"Diferencia Stock SKU: {sku}"
                
                # Buscamos si ya existe un ticket abierto con este título
                existing = tickets_service.list_tickets(q=ticket_title, estado="abierto")
                
                if not existing:
                    desc = (
                        f"Se detectó diferencia de inventario.\n"
                        f"Laudus (Oficial): {remote_stock}\n"
                        f"Monstruo (Local): {current_local}\n"
                        f"Diferencia: {diff}\n"
                        f"Favor contar físicamente y ajustar en Laudus o Monstruo según corresponda."
                    )
                    
                    tickets_service.create_ticket(
                        titulo=ticket_title,
                        descripcion=desc,
                        creador_id="job:sync_stock",
                        severidad="alta",     # Prioridad alta para que Bodega corra
                        tipo="inventario"
                    )
                    stats["tickets_created"] += 1
                    print(f"[STOCK] Ticket created for SKU {sku}. Diff: {diff}")
                else:
                    print(f"[STOCK] Ticket already exists for SKU {sku}. Skipping.")
                
        print(f"[STOCK] Sync Complete. Upserted: {stats['upserted']}, Discrepancies: {stats['discrepancies']}, Tickets: {stats['tickets_created']}")
        
    except Exception as e:
        print(f"[STOCK] Critical Error: {e}")
