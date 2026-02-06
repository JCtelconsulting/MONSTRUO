from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from typing import List, Optional
from pydantic import BaseModel
from app.core import bodega_service, deps, db, jobs_engine
from app.core.audit_decorator import audit_action

router = APIRouter(prefix="/api/bodega", tags=["bodega"])

class StockAdjustSchema(BaseModel):
    sku: str
    quantity: float
    reason: str = "ADJUSTMENT" # PURCHASE, SALE, ADJUSTMENT
    reference: str = ""
    evidence_url: Optional[str] = None

@router.get("/products", response_model=List[dict])
async def search_products(
    q: Optional[str] = "",
    limit: int = 50,
    sess: dict = Depends(deps.require_permission("bodega:read"))
):
    return bodega_service.search_products(q, limit)

@router.get("/inventario_enriquecido", response_model=List[dict])
async def inventario_enriquecido(
    q: Optional[str] = "",
    limit: int = 3000,
    sess: dict = Depends(deps.require_permission("bodega:read"))
):
    """Alias para la UI existente que busca inventario con detalles."""
    return bodega_service.search_products(q, limit)

@router.get("/products/{sku}", response_model=dict)
async def get_product(
    sku: str,
    sess: dict = Depends(deps.require_permission("bodega:read"))
):
    prod = bodega_service.get_product_by_sku(sku)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Enrich with recent movements
    prod["recent_movements"] = bodega_service.get_kardex(sku, limit=5)
    return prod


@router.post("/adjust")
@audit_action("STOCK_ADJUSTMENT", severity="warn")
async def adjust_stock(
    body: StockAdjustSchema,
    request: Request,
    background_tasks: BackgroundTasks,
    sess: dict = Depends(deps.require_permission("bodega:write"))
):
    try:
        user_id = sess["username"]
        result = bodega_service.adjust_stock(
            body.sku, 
            body.quantity, 
            body.reason, 
            user_id, 
            body.reference
        )
        if body.evidence_url:
            try:
                conn = db.get_conn()
                now = db.now_utc_iso()
                movement = conn.execute(
                    "SELECT id FROM inventory_movements WHERE product_id = (SELECT id FROM products WHERE sku = ?) ORDER BY id DESC LIMIT 1",
                    (body.sku,)
                ).fetchone()
                if movement:
                    conn.execute(
                        "UPDATE inventory_movements SET reference = ?, created_at = created_at WHERE id = ?",
                        (f"{body.reference} | EVIDENCE:{body.evidence_url}", movement["id"])
                    )
                    conn.commit()
            finally:
                conn.close()
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/sync_stock")
async def sync_stock(
    sess: dict = Depends(deps.require_permission("bodega:read"))
):
    await jobs_engine.enqueue_job(
        "SYNC_STOCK",
        payload={"apply_stock": True, "trigger": "bodega_ui", "by": sess["username"]},
        max_retries=1
    )
    return {"status": "enqueued"}

@router.post("/sync_catalog_products")
async def sync_catalog_products(
    sess: dict = Depends(deps.require_permission("bodega:read"))
):
    return bodega_service.sync_catalog_products()

@router.get("/products/{sku}/kardex", response_model=List[dict])
async def get_product_kardex(
    sku: str,
    limit: int = 50,
    sess: dict = Depends(deps.require_permission("bodega:read"))
):
    return bodega_service.get_kardex(sku, limit)
