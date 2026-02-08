from fastapi import APIRouter, HTTPException, Depends, Header, Cookie
from typing import Dict, Any, List, Optional
from app.integraciones.parrotfy import ParrotfyClient
from app.integraciones.laudus import LaudusClient
from app.core import db
from app.core import deps as auth_deps
from app.core import bodega_service
from app.jobs import stock_sync

router = APIRouter(prefix="/api/integraciones", tags=["Integraciones"])

# ----------------
# PARROTFY
# ----------------


# --- Logic: Sync & Cache ---
# (Logic moved to app/jobs/stock_sync.py)

@router.post("/parrotfy/sync")
def trigger_parrotfy_sync(authorization: Optional[str] = Header(default=None), access_token: Optional[str] = Cookie(default=None)):
    """Forzar sincronización manual de stock"""
    sess = auth_deps.require_session_hybrid(authorization, access_token)
    auth_deps.require_roles(sess, ["admin", "finance", "ops", "warehouse"])
    
    try:
        # Call Job Logic Directly
        stock_sync.sync_stock()
        return {"status": "ok", "msg": "Sync process triggered. Check server logs."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- LAUDUS: Sync & Cache ---
def sync_laudus_stock_internal():
    """
    Sincroniza stock de Laudus y guarda snapshot.
    """
    client = LaudusClient()
    try:
        data_wrapper = client.get_stock()
        is_ok = 1
        msg = "OK"
        data = []
        
        if data_wrapper.get("error"):
            is_ok = 0
            msg = f"Laudus Error: {data_wrapper.get('detail')}"
        else:
            # Laudus retorna {..., products: [...]}
            data = data_wrapper.get("products", [])
            if not isinstance(data, list):
                # Fallback por si la estructura varia
                data = [] 
                msg = "Warn: No 'products' list in response"
                # Pero si es OK 200, quizas es vacio o diferente estructura. 
                # Consideramos OK pero vacio para no alarmar si no hay stock reportado.
        
        payload_str = json.dumps(data) if is_ok else ""
        total = len(data)
        
        db.init_db()
        conn = db.get_conn()
        try:
            ts = db.now_utc_iso()
            conn.execute("""
                INSERT INTO stock_snapshots (proveedor, creado_ts, total_items, ok, mensaje, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("laudus", ts, total, is_ok, msg, payload_str))
            conn.commit()
            
            return {
                "status": "ok" if is_ok else "error",
                "ts": ts,
                "data": data,
                "msg": msg
            }
        finally:
            conn.close()
    except Exception as e:
        err_msg = str(e)
        db.init_db()
        conn = db.get_conn()
        try:
            ts = db.now_utc_iso()
            conn.execute("""
                INSERT INTO stock_snapshots (proveedor, creado_ts, total_items, ok, mensaje, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("laudus", ts, 0, 0, err_msg, ""))
            conn.commit()
        finally:
            conn.close()
        raise e

@router.get("/parrotfy/stock")
def get_parrotfy_stock(
    authorization: Optional[str] = Header(default=None), 
    access_token: Optional[str] = Cookie(default=None),
    force_refresh: bool = False
):
    """
    Obtiene stock. Por defecto lee el último snapshot válido (< 1h).
    Si no existe o force_refresh=True, intenta sincronizar.
    """
    sess = auth_deps.require_session_hybrid(authorization, access_token)
    auth_deps.require_roles(sess, ["admin", "finance", "ops", "warehouse"])
    
    if force_refresh:
        try:
            res = sync_parrotfy_stock_internal()
            return {"status": "ok", "source": "parrotfy_live", "synced_at": res["ts"], "data": res["data"]}
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Sync failed: {str(e)}")

    # Leer cache
    db.init_db()
    conn = db.get_conn()
    try:
        row = conn.execute("""
            SELECT creado_ts, payload_json 
            FROM stock_snapshots 
            WHERE proveedor='parrotfy' AND ok=1 
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        
        if row:
            # Check edad del cache (opcional, por ahora retornamos lo que haya)
            # Si se desea auto-refresh si es viejo (>1h), se puede implementar logic aqui
            # Por simplicidad y robustez: retornamos cache y dejamos que el scheduler se encargue de actualizar.
            try:
                data = json.loads(row["payload_json"])
                return {
                    "status": "ok", 
                    "source": "cache", 
                    "synced_at": row["creado_ts"], 
                    "data": data
                }
            except:
                pass # Payload corrupto? Fallback a live
        
        # Si no hay cache, fallback live
        res = sync_parrotfy_stock_internal()
        return {"status": "ok", "source": "parrotfy_live_fallback", "synced_at": res["ts"], "data": res["data"]}
        
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Error reading cache: {str(e)}")
    finally:
        conn.close()

@router.get("/parrotfy/productos")
def get_parrotfy_products(authorization: Optional[str] = Header(default=None), access_token: Optional[str] = Cookie(default=None)):
    sess = auth_deps.require_session_hybrid(authorization, access_token)
    
    client = ParrotfyClient()
    data = client.get_products()
    if data.get("error"):
        raise HTTPException(status_code=data.get("status", 500), detail=data.get("detail", "Error Parrotfy Products"))
        
    return {"status": "ok", "count": len(data) if isinstance(data, list) else 0, "data": data}

# ----------------
# LAUDUS ENDPOINTS
# ----------------

@router.get("/laudus/health")
def check_laudus_health(authorization: Optional[str] = Header(default=None), access_token: Optional[str] = Cookie(default=None)):
    sess = auth_deps.require_session_hybrid(authorization, access_token)
    auth_deps.require_roles(sess, ["admin", "finance", "ops"])
    
    client = LaudusClient()
    res = client.get_health()
    return res

@router.post("/laudus/sync")
def trigger_laudus_sync(authorization: Optional[str] = Header(default=None), access_token: Optional[str] = Cookie(default=None)):
    """Forzar sync de Laudus"""
    sess = auth_deps.require_session_hybrid(authorization, access_token)
    auth_deps.require_roles(sess, ["admin", "finance", "ops"])
    try:
        res = sync_laudus_stock_internal()
        if res["status"] != "ok":
             raise HTTPException(status_code=502, detail=res["msg"])
        return {"status": "ok", "synced_at": res["ts"], "count": len(res["data"])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/laudus/stock")
def get_laudus_stock(
    authorization: Optional[str] = Header(default=None), 
    access_token: Optional[str] = Cookie(default=None),
    force_refresh: bool = False
):
    """
    Obtiene stock Laudus (Cacheado).
    """
    sess = auth_deps.require_session_hybrid(authorization, access_token)
    # Laudus stock might be sensitive? No, same roles as Parrotfy
    
    if force_refresh:
        try:
            res = sync_laudus_stock_internal()
            return {"status": "ok", "source": "laudus_live", "synced_at": res["ts"], "data": res["data"]}
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Sync failed: {str(e)}")
            
    # Leer cache
    db.init_db()
    conn = db.get_conn()
    try:
        row = conn.execute("""
            SELECT creado_ts, payload_json 
            FROM stock_snapshots 
            WHERE proveedor='laudus' AND ok=1 
            ORDER BY id DESC LIMIT 1
        """).fetchone()
        
        if row:
            try:
                data = json.loads(row["payload_json"])
                return {
                    "status": "ok", 
                    "source": "cache", 
                    "synced_at": row["creado_ts"], 
                    "data": data
                }
            except:
                pass
        
        # Fallback
        res = sync_laudus_stock_internal()
        return {"status": "ok", "source": "laudus_live_fallback", "synced_at": res["ts"], "data": res["data"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading cache: {str(e)}")
    finally:
        conn.close()
