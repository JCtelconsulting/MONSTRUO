from typing import List, Optional, Dict, Any
from app.core import db

def create_or_update_product(
    sku: str, 
    name: str, 
    key_props: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Upsert a product in the catalog.
    key_props can include: category, price, cost, is_service, external_id
    """
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        
        # Check if exists
        existing = conn.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
        
        if existing:
            # UPDATE
            prod_id = existing["id"]
            allowed = {"category", "price", "cost", "is_service", "external_id", "name"}
            updates = {k: v for k, v in key_props.items() if k in allowed}
            updates["name"] = name # Ensure name is updated
            
            if updates:
                set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
                set_clause += ", updated_at = ?"
                params = list(updates.values()) + [now, prod_id]
                conn.execute(f"UPDATE products SET {set_clause} WHERE id = ?", params)
        else:
            # INSERT
            cols = ["sku", "name", "created_at", "updated_at"]
            vals = [sku, name, now, now]
            placeholders = ["?", "?", "?", "?"]
            
            for k, v in key_props.items():
                if k in ["category", "price", "cost", "is_service", "external_id"]:
                    cols.append(k)
                    vals.append(v)
                    placeholders.append("?")
            
            query = f"INSERT INTO products ({', '.join(cols)}) VALUES ({', '.join(placeholders)})"
            conn.execute(query, vals)
            
        conn.commit()
        return get_product_by_sku(sku)
    finally:
        conn.close()

def get_product_by_sku(sku: str) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        row = conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def search_products(query_str: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        sql = "SELECT * FROM products WHERE external_id IS NOT NULL AND TRIM(external_id) != ''"
        params = []
        qs = (query_str or "").strip()
        if qs:
            if db.is_postgres():
                sql += " AND (sku ILIKE ? OR name ILIKE ?)"
                params.extend([f"%{qs}%", f"%{qs}%"])
            else:
                sql += " AND (LOWER(sku) LIKE LOWER(?) OR LOWER(name) LIKE LOWER(?))"
                params.extend([f"%{qs}%", f"%{qs}%"])
        
        sql += " ORDER BY name ASC LIMIT ?"
        params.append(limit)
        
        cursor = conn.execute(sql, params)
        products = [dict(row) for row in cursor.fetchall()]
        if not products:
            return products

        skus = [p.get("sku") for p in products if p.get("sku")]
        sku_norms = [s.lower() for s in skus if isinstance(s, str)]
        if not sku_norms:
            return products

        qmarks = ",".join(["?"] * len(sku_norms))
        cat_rows = conn.execute(
            f"""
            SELECT
                ci.id AS item_id,
                LOWER(ci.sku_canonico) AS sku_norm,
                c.id AS categoria_id,
                c.nombre AS categoria_nombre,
                c.parent_id AS categoria_parent_id,
                c2.id AS legacy_categoria_id,
                c2.nombre AS legacy_categoria_nombre,
                c2.parent_id AS legacy_categoria_parent_id
            FROM cat_items ci
            LEFT JOIN cat_item_categories mic ON mic.item_id = ci.id
            LEFT JOIN cat_categorias c ON c.id = mic.categoria_id
            LEFT JOIN cat_categorias c2 ON c2.id = ci.categoria_id
            WHERE LOWER(ci.sku_canonico) IN ({qmarks})
            """,
            tuple(sku_norms),
        ).fetchall()

        # Build category map for full paths
        cat_all = conn.execute("SELECT id, nombre, parent_id FROM cat_categorias WHERE activo=1").fetchall()
        cat_by_id = {r["id"]: dict(r) for r in cat_all}

        def build_path(cat_id: Optional[int]) -> List[str]:
            if not cat_id:
                return []
            parts: List[str] = []
            cur = cat_by_id.get(cat_id)
            seen = set()
            while cur and cur.get("id") not in seen:
                seen.add(cur.get("id"))
                name = cur.get("nombre") or ""
                parts.append(name)
                cur = cat_by_id.get(cur.get("parent_id"))
            parts = list(reversed([p for p in parts if p]))
            # Remove root (nivel 1) if present to show niveles 2-4
            if len(parts) > 1:
                parts = parts[1:]
            return parts

        cat_map: Dict[str, Dict[str, Any]] = {}
        for r in cat_rows:
            sku_norm = r["sku_norm"]
            if not sku_norm:
                continue
            entry = cat_map.get(sku_norm)
            if not entry:
                entry = {"item_id": r["item_id"], "categorias": [], "cat_ids": set(), "legacy": None}
                cat_map[sku_norm] = entry

            if r["categoria_id"] is not None:
                cat_id = r["categoria_id"]
                if cat_id not in entry["cat_ids"]:
                    entry["cat_ids"].add(cat_id)
                    ruta = " > ".join(build_path(cat_id))
                    entry["categorias"].append(
                        {
                            "id": r["categoria_id"],
                            "nombre": r["categoria_nombre"],
                            "parent_id": r["categoria_parent_id"],
                            "ruta": ruta or r["categoria_nombre"],
                        }
                    )
            elif r["legacy_categoria_id"] is not None:
                legacy_id = r["legacy_categoria_id"]
                ruta = " > ".join(build_path(legacy_id))
                entry["legacy"] = {
                    "id": legacy_id,
                    "nombre": r["legacy_categoria_nombre"],
                    "parent_id": r["legacy_categoria_parent_id"],
                    "ruta": ruta or r["legacy_categoria_nombre"],
                }

        for p in products:
            sku = p.get("sku") or ""
            sku_norm = sku.lower() if isinstance(sku, str) else ""
            entry = cat_map.get(sku_norm)
            if not entry:
                continue
            p["item_id"] = entry.get("item_id")
            categorias = entry.get("categorias") or []
            if not categorias and entry.get("legacy"):
                categorias = [entry["legacy"]]
            p["categorias"] = categorias
            p["categoria_ids"] = [c["id"] for c in categorias if c.get("id") is not None]

        return products
    finally:
        conn.close()

def sync_catalog_products(limit: int = 10000) -> Dict[str, Any]:
    """
    Ensure catalog items exist in products table by sku_canonico.
    Does not modify stock; only inserts missing products or updates name.
    """
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        rows = conn.execute(
            "SELECT sku_canonico, nombre FROM cat_items WHERE activo=1 AND sku_canonico IS NOT NULL AND TRIM(sku_canonico) != '' LIMIT ?",
            (limit,)
        ).fetchall()
        inserted = 0
        updated = 0
        for r in rows:
            sku = (r["sku_canonico"] or "").strip()
            name = (r["nombre"] or "").strip()
            if not sku:
                continue
            existing = conn.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE products SET name = ?, updated_at = ? WHERE sku = ?",
                    (name, now, sku)
                )
                updated += 1
            else:
                conn.execute(
                    "INSERT INTO products (sku, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (sku, name, now, now)
                )
                inserted += 1
        conn.commit()
        return {"ok": True, "inserted": inserted, "updated": updated}
    finally:
        conn.close()

def adjust_stock(
    sku: str, 
    quantity: float, 
    reason_type: str, 
    user_id: str, 
    reference: str = ""
) -> Dict[str, Any]:
    """
    Adjust stock for a product.
    quantity: + for add, - for remove
    reason_type: PURCHASE, SALE, ADJUSTMENT, SYNC
    """
    if quantity == 0:
        raise ValueError("Quantity cannot be zero")
    if not sku or not sku.strip():
        raise ValueError("SKU requerido")
    if not user_id or not user_id.strip():
        raise ValueError("Usuario requerido")
    reason_type = (reason_type or "").upper().strip()
    allowed_types = {"PURCHASE", "SALE", "ADJUSTMENT", "SYNC", "RETURN"}
    if reason_type not in allowed_types:
        raise ValueError("Tipo de movimiento inválido")
    if reason_type == "SALE" and quantity > 0:
        raise ValueError("SALE requiere cantidad negativa")
    if reason_type in {"PURCHASE", "RETURN"} and quantity < 0:
        raise ValueError("PURCHASE/RETURN requiere cantidad positiva")
    if abs(quantity) > 1000000:
        raise ValueError("Cantidad fuera de rango")
        
    conn = db.get_conn()
    try:
        # 1. Get Product
        prod = conn.execute("SELECT id, stock_current FROM products WHERE sku = ?", (sku,)).fetchone()
        if not prod:
            raise ValueError(f"Product SKU {sku} not found")
            
        prod_id, current_stock = prod["id"], prod["stock_current"]
        
        # 2. Insert Movement (Kardex)
        now = db.now_utc_iso()
        conn.execute("""
            INSERT INTO inventory_movements 
            (product_id, quantity, type, reference, user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (prod_id, quantity, reason_type, reference, user_id, now))
        
        # 3. Update Product Stock Cache
        new_stock = current_stock + quantity
        if new_stock < 0:
            raise ValueError("Stock no puede quedar negativo")
        conn.execute("UPDATE products SET stock_current = ?, updated_at = ? WHERE id = ?", (new_stock, now, prod_id))
        
        conn.commit()
        
        return {
            "sku": sku,
            "old_stock": current_stock,
            "new_stock": new_stock,
            "change": quantity
        }
    finally:
        conn.close()

def get_kardex(sku: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        curr = conn.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
        if not curr:
            return []
        prod_id = curr["id"]
        
        cursor = conn.execute(
            "SELECT * FROM inventory_movements WHERE product_id = ? ORDER BY created_at DESC LIMIT ?", 
            (prod_id, limit)
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
