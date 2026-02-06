"""
Services Sync Job (Laudus).
Trae catálogo de productos desde Laudus y crea/actualiza servicios locales (products.is_service=1)
para que aparezcan en Pre-Factura aunque no tengan stock.
"""

from datetime import datetime, timedelta
from typing import Any

from app.core import db
from app.integraciones.laudus import LaudusClient


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return v != 0
    s = str(v).strip().lower()
    return s in ("1", "true", "t", "yes", "y", "si")


async def sync_services_from_laudus(payload: dict = None):
    """
    Upserta productos en tabla local `products` usando /production/products/list
    y marca como servicio cuando stockable = false.
    """
    client = LaudusClient()
    if not client.login():
        print("[ServicesSync] Laudus Login Failed. Aborting.")
        return {"ok": False, "error": "laudus_login_failed"}

    upserted = 0
    scanned = 0

    # Importante: evitar mantener una transacción abierta mientras se hacen llamadas HTTP.
    # Estrategia: traer páginas desde Laudus, preparar filas en memoria, y upsert en DB por páginas.
    now = db.now_utc_iso()

    skip = 0
    take = 1000
    max_pages = 25  # safety
    for _ in range(max_pages):
        rows = client.list_products(skip=skip, take=take)
        if not rows:
            break
        skip += take

        prepared = []
        for p in rows:
            scanned += 1
            sku = str(p.get("sku") or p.get("code") or "").strip()
            if not sku:
                continue

            name = (p.get("description") or p.get("name") or sku).strip()
            product_id = p.get("productId") or p.get("id") or p.get("product_id")
            external_id = str(product_id).strip() if product_id is not None else None

            unit_price = p.get("unitPrice")
            if unit_price is None:
                unit_price = p.get("price")
            try:
                price = float(unit_price or 0)
            except Exception:
                price = 0.0

            stockable = p.get("stockable")
            is_service = True if (stockable is not None and not _bool(stockable)) else False

            prepared.append(
                {
                    "sku": sku,
                    "name": name,
                    "price": price,
                    "price_currency": "CLP",
                    "price_parity": 1.0,
                    "is_service": is_service,
                    "external_id": external_id,
                }
            )

        if prepared:
            conn = db.get_conn()
            try:
                for r in prepared:
                    conn.execute(
                        """
                        INSERT INTO products (sku, name, price, price_currency, price_parity, is_service, external_id, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(sku) DO UPDATE SET
                          name=excluded.name,
                          price=CASE WHEN excluded.price != 0 THEN excluded.price ELSE products.price END,
                          price_currency=COALESCE(NULLIF(excluded.price_currency, ''), products.price_currency),
                          price_parity=COALESCE(excluded.price_parity, products.price_parity),
                          is_service=CASE WHEN excluded.is_service THEN TRUE ELSE products.is_service END,
                          external_id=COALESCE(NULLIF(excluded.external_id, ''), products.external_id),
                          updated_at=excluded.updated_at
                        """,
                        (
                            r["sku"],
                            r["name"],
                            r["price"],
                            r["price_currency"],
                            r["price_parity"],
                            r["is_service"],
                            r["external_id"],
                            now,
                            now,
                        ),
                    )
                    upserted += 1

                conn.commit()
            finally:
                conn.close()

        if len(rows) < take:
            break

    print(f"[ServicesSync] scanned={scanned} upserted={upserted}")

    # Re-encolar (diario)
    if payload and payload.get("recurring"):
        from app.core import jobs_engine

        next_run = (datetime.utcnow() + timedelta(days=1)).isoformat()
        now_iso = db.now_utc_iso()
        conn2 = db.get_conn()
        try:
            exists = conn2.execute(
                "SELECT 1 FROM sys_jobs WHERE job_type='SYNC_SERVICES_LAUDUS' AND status IN ('PENDING','RETRY')"
            ).fetchone()
            if not exists:
                conn2.execute(
                    """INSERT INTO sys_jobs
                       (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
                       VALUES ('SYNC_SERVICES_LAUDUS', 'PENDING', '{"recurring": true}', ?, 0, 1, ?, ?)""",
                    (next_run, now_iso, now_iso),
                )
                conn2.commit()
                print(f"[ServicesSync] Próximo sync programado para {next_run}")
        finally:
            conn2.close()

    return {"ok": True, "scanned": scanned, "upserted": upserted}
