from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from app.core import db
from app.domain.catalogo import catalogo_match
from app.domain.catalogo import catalogo_categ_ai
from app.utils import ai_local_openai_compat

router = APIRouter(prefix="/api/catalogo", tags=["catalogo"])

class CategoriaCreate(BaseModel):
    tipo: str # equipo | material
    nombre: str
    parent_id: Optional[int] = None

class ItemCreate(BaseModel):
    nombre: str
    categoria_id: Optional[int] = None
    unidad: str = ""
    sku_canonico: str = ""
    marca: str = ""
    image_url: Optional[str] = None

class ItemUpdate(BaseModel):
    nombre: Optional[str] = None
    categoria_id: Optional[int] = None
    sku_canonico: Optional[str] = None
    image_url: Optional[str] = None

class MapeoCreate(BaseModel):
    fuente: str
    fuente_item_id: str
    item_id: int
    confianza: float = 1.0

class MatchSugerir(BaseModel):
    fuente: str
    fuente_item_id: str
    raw_nombre: str
    raw_sku: str = ""
    raw_ean: str = ""
    raw_marca: str = ""

class MatchAprobar(BaseModel):
    fuente: str
    fuente_item_id: str
    item_id: Optional[int] = None # Si es None, busca en suggested_item_id
    confianza: float = 1.0
    metodo_match: str = "manual"

class MatchRechazar(BaseModel):
    fuente: str
    fuente_item_id: str

class ItemCategoriaIn(BaseModel):
    categoria_id: int
@router.get("/categorias")
def list_categorias(
    tipo: Optional[str] = None, 
    parent_id: Optional[int] = None,
    include_hidden: bool = False
):
    conn = db.get_conn()
    try:
        sql = "SELECT * FROM cat_categorias WHERE activo=1"
        params = []
        
        if not include_hidden:
            sql += " AND (is_hidden IS NULL OR is_hidden = ?)"
            params.append(False)
            
        if tipo:
            sql += " AND tipo = ?"
            params.append(tipo)
        if parent_id is not None:

            if parent_id == 0: # root
                sql += " AND parent_id IS NULL"
            else:
                sql += " AND parent_id = ?"
                params.append(parent_id)
        
        sql += " ORDER BY nombre ASC"
        rows = conn.execute(sql, tuple(params)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.post("/categorias")
def create_categoria(body: CategoriaCreate):
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO cat_categorias (tipo, nombre, parent_id) VALUES (?, ?, ?) RETURNING id",
            (body.tipo, body.nombre, body.parent_id)
        )
        cid = cur.fetchone()["id"]
        conn.commit()
        return {"id": cid, "ok": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

class CategoryInlineReq(BaseModel):
    path: List[str] # ["Equipos", "Computación", "Notebooks"]

@router.post("/categorias/inline")
def create_category_inline(body: CategoryInlineReq):
    """Crea o busca una rama de categorías. Retorna ID de la última."""
    conn = db.get_conn()
    try:
        # Define Mirror Roots (Hardcoded for strict compliance)
        MIRROR_ROOTS = {'BODEGA': 6, 'ARRIENDO': 98, 'BAJAS': 99} 
        
        # 1. Identify Hierarchy
        # Path example: ["BODEGA", "EQUIPOS", "Celulares", "Samsung"]
        raw_path = [n.strip() for n in body.path if n.strip()]
        if not raw_path:
            return {"ok": False, "error": "Empty path"}

        root_name = raw_path[0].upper()
        
        # Determine targets
        # If path starts with one of our roots, we sync to others.
        # If it starts with something else (e.g. "EQUIPOS" directly), prompt error or legacy handling?
        # User wants strict taxonomy. So we assume frontend sends full path or we default to BODEGA if root is generic?
        # Let's support both: if 1st element is generic (EQUIPOS), prepend BODEGA and sync all.
        
        target_roots = []
        effective_path_suffix = [] # Path AFTER root
        
        if root_name in MIRROR_ROOTS.keys():
            # Explicit root
            effective_path_suffix = raw_path[1:]
            # We want to sync to ALL mirrors, ensuring the requested one is created too.
            target_roots = list(MIRROR_ROOTS.keys())
        else:
            # Generic root (e.g. "EQUIPOS"), assume it belongs to ALL roots (Mirror logic)
            effective_path_suffix = raw_path
            target_roots = list(MIRROR_ROOTS.keys())

        final_requested_id = None
        
        # 2. Iterate over ALL roots to enforce mirror
        for r_name in target_roots:
            r_id = MIRROR_ROOTS[r_name]
            current_parent_id = r_id
            
            # Traverse/Create Suffix
            for segment in effective_path_suffix:
                # Find or Create
                row = conn.execute(
                    "SELECT id FROM cat_categorias WHERE parent_id = %s AND nombre = %s", 
                    (current_parent_id, segment)
                ).fetchone()
                
                if row:
                    current_parent_id = row['id']
                else:
                    cur = conn.execute(
                        "INSERT INTO cat_categorias (tipo, nombre, parent_id) VALUES ('manual', %s, %s) RETURNING id",
                        (segment, current_parent_id)
                    )
                    current_parent_id = cur.fetchone()['id']
            
            # Capture the ID of the requested path's leaf
            # If the user requested "BODEGA" > ..., we return the ID corresponding to BODEGA's leaf.
            # If user requested generic, we probably return BODEGA's leaf as default.
            if root_name == r_name or (root_name not in MIRROR_ROOTS and r_name == 'BODEGA'):
                final_requested_id = current_parent_id

        conn.commit()
        return {"ok": True, "final_id": final_requested_id, "mirrored": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, detail=str(e))
    finally:
        conn.close()

@router.get("/items")
def list_items(
    categoria_id: Optional[int] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    conn = db.get_conn()
    try:
        sql = """
            SELECT i.*,
                   COALESCE(p.stock_current, p2.stock_current) AS stock_current,
                   COALESCE(p.sku, p2.sku) AS product_sku
            FROM cat_items i
            LEFT JOIN products p ON p.sku = i.sku_canonico
            LEFT JOIN (
                SELECT LOWER(name) AS lname,
                       MAX(stock_current) AS stock_current,
                       MAX(sku) AS sku,
                       COUNT(*) AS cnt
                FROM products
                GROUP BY LOWER(name)
            ) p2 ON LOWER(i.nombre) = p2.lname AND p2.cnt = 1
            WHERE i.activo=1
        """
        params = []
        if categoria_id:
            sql += " AND i.id IN (SELECT item_id FROM cat_item_categories WHERE categoria_id = ?)"
            params.append(categoria_id)
        if q:
            sql += " AND (LOWER(i.nombre) LIKE LOWER(?) OR LOWER(i.sku_canonico) LIKE LOWER(?))"
            p = f"%{q}%"
            params.extend([p, p])
            
        sql += " ORDER BY i.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = conn.execute(sql, tuple(params)).fetchall()
        items = [dict(r) for r in rows]

        if items:
            item_ids = [it["id"] for it in items]
            qmarks = ",".join(["?"] * len(item_ids))
            cat_rows = conn.execute(
                f"""
                SELECT mic.item_id, mic.categoria_id, c.nombre, c.parent_id
                FROM cat_item_categories mic
                JOIN cat_categorias c ON c.id = mic.categoria_id
                WHERE mic.item_id IN ({qmarks})
                """,
                tuple(item_ids),
            ).fetchall()
            cat_map = {}
            for r in cat_rows:
                cat_map.setdefault(r["item_id"], []).append(
                    {"id": r["categoria_id"], "nombre": r["nombre"], "parent_id": r["parent_id"]}
                )
            for it in items:
                cats = cat_map.get(it["id"], [])
                if not cats and it.get("categoria_id"):
                    cats = [{"id": it["categoria_id"], "nombre": None, "parent_id": None}]
                it["categorias"] = cats
                it["categoria_ids"] = [c["id"] for c in cats if c.get("id") is not None]
        return {"items": items}
    finally:
        conn.close()

@router.post("/items")
def create_item(body: ItemCreate):
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        sku_canon = catalogo_match.norm_sku(body.sku_canonico) if body.sku_canonico else ""
        cur = conn.execute(
            "INSERT INTO cat_items (nombre, categoria_id, unidad, sku_canonico, marca, image_url, creado_at, actualizado_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id",
            (body.nombre, body.categoria_id, body.unidad, sku_canon, body.marca, body.image_url or "", now, now)
        )
        iid = cur.fetchone()["id"]
        if body.categoria_id:
            conn.execute(
                "INSERT INTO cat_item_categories (item_id, categoria_id, created_at) VALUES (?, ?, ?)",
                (iid, body.categoria_id, now)
            )
        conn.commit()
        return {"id": iid, "ok": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.post("/mapear")
def crear_mapeo(body: MapeoCreate):
    conn = db.get_conn()
    try:
        # Upsert
        conn.execute("""
            INSERT INTO cat_fuente_map (fuente, fuente_item_id, item_id, confianza, metodo_match)
            VALUES (?, ?, ?, ?, 'manual')
            ON CONFLICT(fuente, fuente_item_id) DO UPDATE SET
                item_id = excluded.item_id,
                confianza = excluded.confianza,
                metodo_match = 'manual_update'
        """, (body.fuente, body.fuente_item_id, body.item_id, body.confianza))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()

# --- V2 Matching Endpoints ---

@router.get("/pendientes")
def list_pendientes(
    fuente: Optional[str] = None,
    limit: int = 50, 
    offset: int = 0
):
    conn = db.get_conn()
    try:
        sql = "SELECT * FROM cat_match_queue WHERE estado='pendiente'"
        params = []
        if fuente:
            sql += " AND fuente=?"
            params.append(fuente)
            
        sql += " ORDER BY score DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = conn.execute(sql, tuple(params)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@router.post("/sugerir")
def sugerir_match(body: MatchSugerir):
    conn = db.get_conn()
    try:
        # 1. Buscar candidates en items
        candidates_cur = conn.execute("SELECT id, nombre, marca, sku_canonico, image_url FROM cat_items WHERE activo=1")
        candidates = [dict(r) for r in candidates_cur]
        
        # 2. Logic de scoring
        # Primero intentar match exacto por SKU o EAN (si existiera campo ean en items, aqui asumimos sku_canonico)
        best_id = None
        best_score = 0.0
        
        # Check SKU match
        if body.raw_sku:
            target_sku = catalogo_match.norm_sku(body.raw_sku)
            for c in candidates:
                if c['sku_canonico'] and c['sku_canonico'] == target_sku:
                    best_id = c['id']
                    best_score = 1.0
                    break
        
        # If no sku match, fuzzy name
        if not best_id:
            best_id, best_score = catalogo_match.pick_best_candidate(body.raw_nombre, body.raw_marca, candidates)
            
        now = db.now_utc_iso()
        conn.execute("""
            INSERT INTO cat_match_queue (fuente, fuente_item_id, raw_nombre, raw_sku, raw_ean, raw_marca, suggested_item_id, score, estado, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, ?)
            ON CONFLICT(fuente, fuente_item_id) DO UPDATE SET
                raw_nombre = excluded.raw_nombre,
                raw_sku = excluded.raw_sku,
                raw_ean = excluded.raw_ean,
                raw_marca = excluded.raw_marca,
                suggested_item_id = excluded.suggested_item_id,
                score = excluded.score,
                estado='pendiente',
                updated_at = excluded.updated_at
        """, (body.fuente, body.fuente_item_id, body.raw_nombre, body.raw_sku, body.raw_ean, body.raw_marca, best_id, best_score, now, now))
        
        conn.commit()
        return {"ok": True, "suggested": best_id, "score": best_score}
    finally:
        conn.close()

@router.post("/items/{item_id}/categorias")
def add_item_categoria(item_id: int, body: ItemCategoriaIn):
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            "INSERT INTO cat_item_categories (item_id, categoria_id, created_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (item_id, body.categoria_id, now)
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()

@router.patch("/items/{item_id}")
def update_item_partial(item_id: int, body: ItemUpdate):
    conn = db.get_conn()
    try:
        fields = []
        params = []
        if body.nombre is not None:
             fields.append("nombre = ?")
             params.append(body.nombre)
        if body.categoria_id is not None:
             fields.append("categoria_id = ?")
             params.append(body.categoria_id)
        if body.sku_canonico is not None:
             fields.append("sku_canonico = ?")
             params.append(body.sku_canonico)
        if body.image_url is not None:
             fields.append("image_url = ?")
             params.append(body.image_url)
             
        if not fields:
            return {"ok": True, "msg": "No changes"}
            
        fields.append("actualizado_at = ?")
        params.append(db.now_utc_iso())
        
        params.append(item_id)
        
        sql = f"UPDATE cat_items SET {', '.join(fields)} WHERE id = ?"
        conn.execute(sql, tuple(params))
        conn.commit()
        return {"ok": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@router.delete("/items/{item_id}/categorias/{categoria_id}")
def remove_item_categoria(item_id: int, categoria_id: int):
    conn = db.get_conn()
    try:
        conn.execute(
            "DELETE FROM cat_item_categories WHERE item_id=? AND categoria_id=?",
            (item_id, categoria_id)
        )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()

@router.post("/aprobar")
def aprobar_match(body: MatchAprobar):
    conn = db.get_conn()
    try:
        final_item_id = body.item_id
        
        # Si no envian item_id, usamos el sugerido
        if not final_item_id:
            row = conn.execute("SELECT suggested_item_id FROM cat_match_queue WHERE fuente=? AND fuente_item_id=?", (body.fuente, body.fuente_item_id)).fetchone()
            if row:
                final_item_id = row['suggested_item_id']
                
        if not final_item_id:
            raise HTTPException(status_code=400, detail="no item_id provided or found")
            
        # 1. Guardar en mapa
        conn.execute("""
            INSERT INTO cat_fuente_map (fuente, fuente_item_id, item_id, confianza, metodo_match, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(fuente, fuente_item_id) DO UPDATE SET
                item_id=excluded.item_id,
                confianza=excluded.confianza,
                metodo_match=excluded.metodo_match,
                last_seen_at=excluded.last_seen_at
        """, (body.fuente, body.fuente_item_id, final_item_id, body.confianza, body.metodo_match, db.now_utc_iso()))
        
        # 2. Update Queue -> aprobado
        conn.execute("UPDATE cat_match_queue SET estado='aprobado', updated_at=? WHERE fuente=? AND fuente_item_id=?", 
                     (db.now_utc_iso(), body.fuente, body.fuente_item_id))
        
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


# --- V3 Categorizacion AI/Manual Improvements ---

class AsignarCategoria(BaseModel):
    item_id: int
    categoria_id: int
    metodo: str = "manual" # manual | ai_recommend

@router.get("/pendientes_categorizacion")
def list_pendientes_categorizacion(
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    conn = db.get_conn()
    try:
        # Detectar items sin categoria o en "Sin Clasificar"
        # Estrategia: JOIN cat_categorias. Si c.id es NULL (no existe categoria) OR c.nombre = 'Sin Clasificar'
        # Tambien incluir c.nombre = 'AutoSeed' si se desea limpiar
        
        sql = """
            SELECT i.id, i.nombre, i.marca, i.sku_canonico, i.atributos_json, 
                   c.nombre as current_cat
            FROM cat_items i
            LEFT JOIN cat_categorias c ON i.categoria_id = c.id
            WHERE (i.categoria_id IS NULL 
                   OR c.nombre IN ('Sin Clasificar', 'AutoSeed', 'Bodega')
                   OR i.categoria_id = 0)
            AND i.activo = 1
        """
        params = []
        
        if q:
            # Case-insensitive search (SQLite default LIKE is usually case-insensitive for ASCII, 
            # but for robustness matching lower)
            sql += " AND (LOWER(i.nombre) LIKE LOWER(?) OR LOWER(i.sku_canonico) LIKE LOWER(?))"
            p = f"%{q}%"
            params.extend([p, p])
            
        sql += " ORDER BY i.id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = conn.execute(sql, tuple(params)).fetchall()
        
        # Enriquecer con ruta string si ruta_json no existe
        results = []
        for r in rows:
            d = dict(r)
            if not d.get('current_cat'):
                 d['current_cat'] = "Sin Asignar"
            results.append(d)
            
        return {"items": results}
    finally:
        conn.close()

@router.post("/asignar_categoria")
def asignar_categoria(body: AsignarCategoria):
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        
        # 1. Update item
        conn.execute(
            "UPDATE cat_items SET categoria_id = ?, actualizado_at = ? WHERE id = ?",
            (body.categoria_id, now, body.item_id)
        )
        
        # 2. Log in attributes (json patch style)
        # Read current attrs
        cur = conn.execute("SELECT atributos_json FROM cat_items WHERE id = ?", (body.item_id,)).fetchone()
        import json
        attrs = {}
        if cur and cur["atributos_json"]:
            try:
                attrs = json.loads(cur["atributos_json"])
            except: pass
            
        attrs["last_category_set"] = body.metodo
        attrs["last_category_ts"] = now
        
        conn.execute(
            "UPDATE cat_items SET atributos_json = ? WHERE id = ?",
            (json.dumps(attrs), body.item_id)
        )
        
        conn.commit()
        return {"ok": True}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


# ... (Previous imports)
from app.domain.catalogo import catalogo_categ_ai
from app.utils import ai_local_openai_compat
from typing import Tuple

class RecomendarReq(BaseModel):
    item_id: int

class CrearAsignarReq(BaseModel):
    item_id: int
    ruta: List[str]
    atributos: Optional[Dict[str, Any]] = {}
    confidence: float
    reason: str

@router.post("/recomendar_categoria")
def recomendar_categoria(body: RecomendarReq):
    conn = db.get_conn()
    try:
        # 1. Get Item
        item = conn.execute("SELECT * FROM cat_items WHERE id=?", (body.item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
            
        # 2. Get All Cats (optimized: flat list with minimal path info)
        cats = conn.execute("SELECT id, nombre, parent_id FROM cat_categorias WHERE activo=1").fetchall()
        
        # Build paths
        cat_map = {c['id']: c for c in cats}
        flat_cats = []
        
        for c in cats:
            path_str = _build_path_str(c['id'], cat_map)
            flat_cats.append({
                "id": c['id'],
                "nombre": c['nombre'], # leaf
                "ruta_str": path_str
            })
            
        # 3. Call AI
        result = catalogo_categ_ai.recommend_category(dict(item), flat_cats, ai_local_openai_compat)
        
        return result
    finally:
        conn.close()

@router.post("/crear_categoria_y_asignar")
def crear_categoria_y_asignar(body: CrearAsignarReq):
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        
        # 1. Ensure Path
        parent_id = None
        if not body.ruta:
             raise HTTPException(status_code=400, detail="Empty path")

        for level_name in body.ruta:
            # Find or Create
            if parent_id is None:
                row = conn.execute("SELECT id FROM cat_categorias WHERE nombre=? AND parent_id IS NULL", (level_name,)).fetchone()
            else:
                 row = conn.execute("SELECT id FROM cat_categorias WHERE nombre=? AND parent_id=?", (level_name, parent_id)).fetchone()
            
            if row:
                parent_id = row['id']
            else:
                # Create
                cur = conn.execute(
                    "INSERT INTO cat_categorias (tipo, nombre, parent_id) VALUES ('auto', ?, ?) RETURNING id",
                    (level_name, parent_id)
                )
                parent_id = cur.fetchone()['id']
                
        final_cat_id = parent_id
        
        # 2. Update Item
        cur = conn.execute("SELECT atributos_json FROM cat_items WHERE id = ?", (body.item_id,)).fetchone()
        import json
        attrs = {}
        if cur and cur['atributos_json']:
            try: attrs = json.loads(cur['atributos_json'])
            except: pass
            
        if body.atributos:
            attrs.update(body.atributos)
            
        attrs['last_category_set'] = 'ai_create_new'
        attrs['ai_reason'] = body.reason
        
        conn.execute(
            "UPDATE cat_items SET categoria_id=?, atributos_json=?, actualizado_at=? WHERE id=?",
            (final_cat_id, json.dumps(attrs), now, body.item_id)
        )
        
        conn.commit()
        return {"ok": True, "final_cat_id": final_cat_id}
            
    finally:
        conn.close()


class DuplicadoReq(BaseModel):
    item_id: int
    top_n: int = 30

@router.post("/sugerir_duplicados")
def sugerir_duplicados(body: DuplicadoReq):
    conn = db.get_conn()
    try:
        # 1. Get Target Item
        target = conn.execute("SELECT * FROM cat_items WHERE id=?", (body.item_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="Item not found")
            
        # 2. Pre-filter candidates (Fuzzy/Token based or just similar names)
        # For simplicity and performance, we'll fetch items with matching words
        # or just fetch recent items if database is small.
        # Let's try to match at least one word from the name
        words = [w for w in target['nombre'].split() if len(w) > 3]
        
        candidates = []
        if words:
            # Build dynamic OR query
            likes = []
            params = []
            for w in words:
                likes.append("nombre LIKE ?")
                params.append(f"%{w}%")
            
            sql = f"SELECT id, nombre, marca, sku_canonico, image_url FROM cat_items WHERE activo=1 AND id != ? AND ({' OR '.join(likes)}) LIMIT 50"
            params.insert(0, body.item_id)
            rows = conn.execute(sql, tuple(params)).fetchall()
            candidates = [dict(r) for r in rows]
        else:
            # Fallback size
            rows = conn.execute("SELECT id, nombre, marca, sku_canonico FROM cat_items WHERE activo=1 AND id != ? LIMIT 50", (body.item_id,)).fetchall()
            candidates = [dict(r) for r in rows]
            
        if not candidates:
            return {"duplicates": [], "variants": [], "message": "No fuzzy candidates found"}
            
        # 3. Call AI
        result = catalogo_categ_ai.analyze_duplicates(dict(target), candidates, ai_local_openai_compat)
        
        # 4. Store/Log items (optional, not requested to persist but good for caching)
        # We return directly for UI to show
        
        return result
        
    finally:
        conn.close()



# --- AUTOMATED DUPLICATE SCANNER (V4) ---

@router.post("/run_duplicate_scan")
def run_duplicate_scan(limit: int = 500):
    conn = db.get_conn()
    try:
        # 1. Fetch active items
        items = conn.execute("SELECT id, nombre, sku_canonico, marca, image_url FROM cat_items WHERE activo=1 LIMIT ?", (limit,)).fetchall()
        items = [dict(r) for r in items]
        
        detected_count = 0
        now = db.now_utc_iso()
        
        # 2. Naive Comparisons (Improving this requires vector search or elastic)
        # Strategy: Group by "Normalized 3-gram" or rough words intersection
        
        # Simple loop for demo (O(N^2) limited)
        # Optimized: Sort by name and compare adjacents or use small window
        items.sort(key=lambda x: x['nombre'])
        
        for i in range(len(items)):
            a = items[i]
            # Look ahead window of 20 items
            for j in range(i + 1, min(i + 20, len(items))):
                b = items[j]
                
                # Check Name Similarity
                import difflib
                ratio = difflib.SequenceMatcher(None, a['nombre'].lower(), b['nombre'].lower()).ratio()
                
                if ratio > 0.85: # Threshold
                    # Insert Case
                    try:
                        conn.execute("""
                            INSERT INTO cat_duplicados_detectados 
                            (item_id_a, item_id_b, score, reason, status, created_at, updated_at)
                            VALUES (?, ?, ?, ?, 'pendiente', ?, ?)
                        """, (a['id'], b['id'], ratio, f"Nombres similares ({int(ratio*100)}%): {a['nombre']} vs {b['nombre']}", now, now))
                        detected_count += 1
                    except Exception: 
                        pass # Ignore unique constraint violations (already detected)
                        
        conn.commit()
        return {"processed": len(items), "detected": detected_count}
    finally:
        conn.close()

# Update list_pendientes to include duplicate cases
@router.get("/pendientes_dashboard") 
def list_pendientes_dashboard():
    # Helper aggregator for the "Pendientes Match" tab
    conn = db.get_conn()
    try:
        # 1. Uncategorized Items
        uncat_sql = """
            SELECT i.id, i.nombre, i.marca, i.sku_canonico, 
                   'uncategorized' as type, 
                   c.nombre as current_cat
            FROM cat_items i
            LEFT JOIN cat_categorias c ON i.categoria_id = c.id
            WHERE (i.categoria_id IS NULL OR c.nombre IN ('Sin Clasificar', 'AutoSeed', 'Bodega'))
            AND i.activo = 1
            LIMIT 50
        """
        uncat_rows = [dict(r) for r in conn.execute(uncat_sql).fetchall()]
        
        # 2. Duplicate Cases
        dup_sql = """
            SELECT d.id as case_id, d.score, d.reason,
                   a.nombre as nombre_a, a.id as id_a,
                   b.nombre as nombre_b, b.id as id_b,
                   'duplicate_case' as type
            FROM cat_duplicados_detectados d
            JOIN cat_items a ON d.item_id_a = a.id
            JOIN cat_items b ON d.item_id_b = b.id
            WHERE d.status = 'pendiente'
            ORDER BY d.score DESC
            LIMIT 20
        """
        dup_rows = [dict(r) for r in conn.execute(dup_sql).fetchall()]
        
        return {
            "uncategorized": uncat_rows,
            "duplicates": dup_rows
        }
    finally:
        conn.close()

@router.post("/resolver_duplicado")
def resolver_duplicado(body: dict = Body(...)):
    # body: { case_id: int, action: 'keep_a' | 'keep_b' | 'ignore' | 'mark_as_variant' }
    conn = db.get_conn()
    try:
        case_id = body.get('case_id')
        action = body.get('action')
        now = db.now_utc_iso()
        
        row = conn.execute("SELECT item_id_a, item_id_b, score, reason FROM cat_duplicados_detectados WHERE id=?", (case_id,)).fetchone()
        if not row: raise HTTPException(404, "Case not found")
        
        # Log training sample
        from app.api.routers.ai import log_training_case
        log_msg = f"Action: {action}"
        
        if action == 'ignore':
            conn.execute("UPDATE cat_duplicados_detectados SET status='ignorado', updated_at=? WHERE id=?", (now, case_id))
        
        elif action == 'mark_as_variant':
            # No se borra nada, se marca como resuelto "variante"
            # Opcional: enlazar items como variantes en una tabla futura
            conn.execute("UPDATE cat_duplicados_detectados SET status='resuelto_variante', updated_at=? WHERE id=?", (now, case_id))
            
            # Update items attributes to note they are checked
            for iid in [row['item_id_a'], row['item_id_b']]:
                 conn.execute("UPDATE cat_items SET atributos_json=json_patch(coalesce(atributos_json,'{}'), ?) WHERE id=?",
                              (f'{{"variant_checked": true}}', iid))

        elif action in ('keep_a', 'keep_b'):
            keep_id = row['item_id_a'] if action == 'keep_a' else row['item_id_b']
            drop_id = row['item_id_b'] if action == 'keep_a' else row['item_id_a']
            
            # Merge Logic: 
            # 1. Update drop_id to inactive
            conn.execute("UPDATE cat_items SET activo=0, atributos_json=json_patch(coalesce(atributos_json,'{}'), ?) WHERE id=?", 
                         (f'{{"merged_into": {keep_id}}}', drop_id))
            
            # 2. Reassign movements?? (Complex, maybe later)
            
            conn.execute("UPDATE cat_duplicados_detectados SET status='resuelto', updated_at=? WHERE id=?", (now, case_id))
            
        conn.commit()
        
        # Feedback Logging
        try:
             # Basic sampling, ideally fetch full items
             log_training_case(
                 input_data={"case_id": case_id, "score": row['score'], "reason": row['reason']},
                 output_data={"action": action},
                 mode="human_resolution",
                 ok=1,
                 msg=log_msg
             )
        except: pass
        
        return {"ok": True}
    finally:
        conn.close()


@router.post("/resolver_duplicado_instruccion")
def resolver_duplicado_instruccion(body: dict = Body(...)):
    # body: { case_id: int, instruction: str }
    conn = db.get_conn()
    try:
        case_id = body.get('case_id')
        instruction = body.get('instruction')
        
        # 1. Fetch Case Context
        row = conn.execute("SELECT item_id_a, item_id_b FROM cat_duplicados_detectados WHERE id=?", (case_id,)).fetchone()
        if not row: raise HTTPException(404, "Case not found")
        
        id_a, id_b = row['item_id_a'], row['item_id_b']
        item_a = dict(conn.execute("SELECT * FROM cat_items WHERE id=?", (id_a,)).fetchone())
        item_b = dict(conn.execute("SELECT * FROM cat_items WHERE id=?", (id_b,)).fetchone())
        
        # 2. Call AI
        actions = catalogo_categ_ai.process_user_instruction(item_a, item_b, instruction, ai_local_openai_compat)
        
        # 3. Execute Actions
        logs = []
        for action in actions:
            act_type = action.get('action')
            
            if act_type == 'rename':
                target_id = id_a if action.get('target') == 'A' else id_b
                new_name = action.get('new_name')
                conn.execute("UPDATE cat_items SET nombre=?, actualizado_at=? WHERE id=?", 
                             (new_name, db.now_utc_iso(), target_id))
                logs.append(f"Renombrado Item {target_id} -> {new_name}")
                
            elif act_type == 'set_category':
                path = action.get('category_path', [])
                # Recursive Find/Create Category Path
                parent_id = None
                for level in path:
                    # SQLite IS NULL trick using IS needs parameter logic or separate queries
                    if parent_id is None:
                        rid = conn.execute("SELECT id FROM cat_categorias WHERE nombre=? AND parent_id IS NULL", (level,)).fetchone()
                    else:
                        rid = conn.execute("SELECT id FROM cat_categorias WHERE nombre=? AND parent_id=?", (level, parent_id)).fetchone()
                    
                    if rid: 
                        parent_id = rid['id']
                    else:
                        cursor = conn.execute("INSERT INTO cat_categorias (nombre, parent_id, tipo) VALUES (?, ?, 'auto') RETURNING id", 
                                              (level, parent_id))
                        parent_id = cursor.fetchone()['id']
                
                final_cat = parent_id
                
                targets = []
                t_arg = action.get('target')
                if t_arg == 'A': targets = [id_a]
                elif t_arg == 'B': targets = [id_b]
                elif t_arg == 'BOTH': targets = [id_a, id_b]
                
                for tid in targets:
                    conn.execute("UPDATE cat_items SET categoria_id=?, actualizado_at=? WHERE id=?", 
                                 (final_cat, db.now_utc_iso(), tid))
                logs.append(f"Categorizado {targets} -> {path}")

            elif act_type == 'resolve_case':
                status = action.get('status')
                conn.execute("UPDATE cat_duplicados_detectados SET status=?, reason=? WHERE id=?", 
                             (status, f"AI Instruction: {instruction}", case_id))
                logs.append(f"Caso cerrado: {status}")

        conn.commit()
        return {"ok": True, "actions_executed": logs}
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()

@router.post("/resolver_duplicado_masivo")
def resolver_duplicado_masivo(body: dict = Body(...)):
    # body: { case_ids: List[int], instruction: str }
    case_ids = body.get('case_ids', [])
    instruction = body.get('instruction', "")
    
    if not case_ids:
        raise HTTPException(400, "No case_ids provided")

    conn = db.get_conn()
    results = []
    
    try:
        # Optimization: We could batch process if the LLM supports it, 
        # but for robustness we process iteratively.
        # Ideally, we should spawn a background task for large batches, 
        # but for < 20 items, sync is acceptable for this prototype.
        
        for case_id in case_ids:
            try:
                # 1. Fetch Case Context
                row = conn.execute("SELECT item_id_a, item_id_b FROM cat_duplicados_detectados WHERE id=?", (case_id,)).fetchone()
                if not row: 
                    results.append({"case_id": case_id, "status": "error", "message": "Not found"})
                    continue
                
                id_a, id_b = row['item_id_a'], row['item_id_b']
                item_a = dict(conn.execute("SELECT * FROM cat_items WHERE id=?", (id_a,)).fetchone())
                item_b = dict(conn.execute("SELECT * FROM cat_items WHERE id=?", (id_b,)).fetchone())
                
                # 2. Call AI
                if instruction == 'AUTO_PILOT':
                    actions = catalogo_categ_ai.process_auto_resolution(item_a, item_b, ai_local_openai_compat)
                else:
                    actions = catalogo_categ_ai.process_user_instruction(item_a, item_b, instruction, ai_local_openai_compat)
                
                # 3. Execute Actions (Reusing logic - ideally duplicate logic should be a shared function)
                logs = []
                for action in actions:
                    act_type = action.get('action')
                    
                    if act_type == 'rename':
                        target_id = id_a if action.get('target') == 'A' else id_b
                        new_name = action.get('new_name')
                        conn.execute("UPDATE cat_items SET nombre=?, actualizado_at=? WHERE id=?", 
                                     (new_name, db.now_utc_iso(), target_id))
                        logs.append(f"Renombrado Item {target_id} -> {new_name}")
                        
                    elif act_type == 'set_category':
                        path = action.get('category_path', [])
                        parent_id = None
                        for level in path:
                            if parent_id is None:
                                rid = conn.execute("SELECT id FROM cat_categorias WHERE nombre=? AND parent_id IS NULL", (level,)).fetchone()
                            else:
                                rid = conn.execute("SELECT id FROM cat_categorias WHERE nombre=? AND parent_id=?", (level, parent_id)).fetchone()
                            
                            if rid: 
                                parent_id = rid['id']
                            else:
                                cursor = conn.execute("INSERT INTO cat_categorias (nombre, parent_id, tipo) VALUES (?, ?, 'auto') RETURNING id", 
                                                      (level, parent_id))
                                parent_id = cursor.fetchone()['id']
                        
                        final_cat = parent_id
                        targets = []
                        t_arg = action.get('target')
                        if t_arg == 'A': targets = [id_a]
                        elif t_arg == 'B': targets = [id_b]
                        elif t_arg == 'BOTH': targets = [id_a, id_b]
                        
                        for tid in targets:
                            conn.execute("UPDATE cat_items SET categoria_id=?, actualizado_at=? WHERE id=?", 
                                         (final_cat, db.now_utc_iso(), tid))
                        logs.append(f"Categorizado {targets} -> {path}")

                    elif act_type == 'resolve_case':
                        status = action.get('status')
                        conn.execute("UPDATE cat_duplicados_detectados SET status=?, reason=? WHERE id=?", 
                                     (status, f"Mass AI: {instruction}", case_id))
                        logs.append(f"Caso cerrado: {status}")

                results.append({"case_id": case_id, "status": "ok", "actions": logs})

            except Exception as e:
                results.append({"case_id": case_id, "status": "error", "message": str(e)})

        conn.commit()
        return {"processed": len(case_ids), "details": results}

    except Exception as e:
        conn.rollback()
        raise HTTPException(500, str(e))
    finally:
        conn.close()
