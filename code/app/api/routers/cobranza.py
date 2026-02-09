from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Dict, Any
from app.core import deps, db

router = APIRouter(prefix="/api/collection", tags=["collection"])


@router.get("/debtors", summary="List debtors with aging analysis")
async def list_debtors(
    min_debt: int = 1000, sess: dict = Depends(deps.require_permission("invoice:read"))
):
    """
    Returns a list of customers with their total debt and aging buckets.
    Buckets:
    - current: Not overdue
    - overdue_30: 1-30 days overdue
    - overdue_60: 31-60 days overdue
    - overdue_90: >60 days overdue
    """
    conn = db.get_conn()
    try:
        # Rules:
        # - Status != PAID, VOID, DRAFT (only ISSUED counts as debt ?)
        #   Actually, depending on workflow, maybe only ISSUED. Let's assume ISSUED + PARTIAL if it existed.
        #   For now: status = 'ISSUED'

        # Rules:
        # - Status != PAID, VOID, DRAFT (only ISSUED counts as debt)
        # - Schema: invoices(id, customer_id, total_final, status, issued_at)
        # - No partial payments in 'invoices' table yet, assuming full amount if ISSUED.

        # Postgres syntax for interval: NOW() - interval 'X days'
        # Note: issued_at is TEXT in SQLite/schema definition (ISO string).

        pg_query = """
        SELECT 
            COALESCE(INITCAP(c.name), i.customer_id) as customer_id,
            SUM(total_final) as total_debt,
            
            SUM(CASE 
                WHEN EXTRACT(DAY FROM NOW() - i.issued_at::timestamp) <= 30 THEN total_final
                ELSE 0 
            END) as debt_current,
            
            SUM(CASE 
                WHEN EXTRACT(DAY FROM NOW() - i.issued_at::timestamp) > 30 AND EXTRACT(DAY FROM NOW() - i.issued_at::timestamp) <= 60 THEN total_final
                ELSE 0 
            END) as debt_30,
            
            SUM(CASE 
                WHEN EXTRACT(DAY FROM NOW() - i.issued_at::timestamp) > 60 THEN total_final
                ELSE 0 
            END) as debt_60
            
        FROM invoices i
        LEFT JOIN laudus_customers c ON c.laudus_customer_id = i.customer_id
        WHERE i.status = 'ISSUED'
        GROUP BY COALESCE(INITCAP(c.name), i.customer_id)
        HAVING SUM(total_final) >= %s
        ORDER BY 2 DESC
        """

        cursor = conn.execute(pg_query, (min_debt,))
        rows = cursor.fetchall()

        results = []
        for r in rows:
            # r can be dict (RealDictCursor) or tuple depending on driver/shim
            # The PgConn in db.py uses RealDictCursor for psycopg2

            # Using dict access if available, else index
            if isinstance(r, dict):
                d_total = float(r.get("total_debt", 0))
                d_curr = float(r.get("debt_current", 0))
                d_30 = float(r.get("debt_30", 0))
                d_60 = float(r.get("debt_60", 0))
                cid = r.get("customer_id")
            else:
                cid = r[0]
                d_total = float(r[1] or 0)
                d_curr = float(r[2] or 0)
                d_30 = float(r[3] or 0)
                d_60 = float(r[4] or 0)

            results.append(
                {
                    "customer_id": cid,
                    "total_debt": d_total,
                    "debt_current": d_curr,
                    "debt_30": d_30,
                    "debt_60": d_60,
                    "risk_level": "CRITICAL"
                    if d_60 > 0
                    else ("WARNING" if d_30 > 0 else "NORMAL"),
                }
            )

        return results

    finally:
        conn.close()


@router.get("/customer-status", summary="List customers with debt status")
async def list_customer_status(
    limit: int = 120, sess: dict = Depends(deps.require_permission("invoice:read"))
):
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                COALESCE(NULLIF(TRIM(c.fantasy_name), ''), NULLIF(TRIM(c.name), ''), NULLIF(TRIM(c.rut), ''), TRIM(c.external_id), 'Sin nombre') AS customer_name,
                COALESCE(SUM(CASE WHEN i.status = 'ISSUED' THEN i.total_final ELSE 0 END), 0) AS total_debt,
                c.external_id
            FROM customers c
            LEFT JOIN invoices i
              ON TRIM(i.customer_id) = TRIM(c.external_id)
            GROUP BY c.fantasy_name, c.name, c.rut, c.external_id
            ORDER BY total_debt DESC, customer_name ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

        return [
            {
                "customer_name": (
                    row["customer_name"] if isinstance(row, dict) else row[0]
                ),
                "customer_id": (
                    row["external_id"]
                    if isinstance(row, dict)
                    else row[2]  # Assuming added as 3rd column
                ),
                "total_debt": float(
                    (row["total_debt"] if isinstance(row, dict) else row[1]) or 0
                ),
                "status": (
                    "DEBT"
                    if float(
                        (row["total_debt"] if isinstance(row, dict) else row[1]) or 0
                    )
                    > 0
                    else "OK"
                ),
            }
            for row in rows
        ]
    finally:
        conn.close()


from app.core import email as email_service


@router.post("/actions", summary="Register collection action")
async def register_action(
    payload: dict, sess: dict = Depends(deps.require_permission("invoice:write"))
):
    """
    Registers a collection action (call, email, etc)
    If type is EMAIL, attempts to send real email.
    """
    conn = db.get_conn()
    try:
        data = payload
        cid = data.get("customer_id")
        atype = data.get("action_type")
        notes = data.get("notes", "")
        amt = float(data.get("committed_amount", 0))
        cdate = data.get("commitment_date", "")
        subject = data.get("subject", "Aviso de Cobranza")

        user = sess.get("user", {}).get("username", "system")
        ts = db.now_utc_iso()

        # --- EMAIL DISPATCH LOGIC ---
        if atype == "EMAIL":
            # 1. Resolve Customer Email
            # Try finding in CRM table first, then laudus_customers fallback
            cust_row = conn.execute(
                "SELECT email, name FROM customers WHERE external_id = %s", (cid,)
            ).fetchone()

            target_email = None
            if cust_row:
                target_email = (
                    cust_row.get("email") if isinstance(cust_row, dict) else cust_row[0]
                )

            if not target_email:
                # Fallback to laudus_customers raw_json parsing
                lc_row = conn.execute(
                    "SELECT raw_json FROM laudus_customers WHERE laudus_customer_id = %s",
                    (cid,),
                ).fetchone()
                if lc_row:
                    import json

                    raw_data = json.loads(
                        lc_row.get("raw_json")
                        if isinstance(lc_row, dict)
                        else lc_row[0]
                    )
                    target_email = raw_data.get("email")

            if not target_email:
                raise HTTPException(
                    status_code=400,
                    detail=f"No se encontró email para el cliente {cid}. Verifique ficha CRM.",
                )

            # 2. Send Email
            html_body = notes.replace("\n", "<br>")

            try:
                email_service.send_email(
                    to_email=target_email, subject=subject, html_body=html_body
                )
                notes += f"\n[CORREO ENVIADO A: {target_email}]"
            except Exception as e:
                raise HTTPException(
                    status_code=500, detail=f"Fallo al enviar correo: {str(e)}"
                )

        conn.execute(
            """
            INSERT INTO collection_actions 
            (customer_id, action_type, notes, committed_amount, commitment_date, created_at, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
            (cid, atype, notes, amt, cdate, ts, user),
        )
        conn.commit()

        return {"ok": True, "id": cid}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/generate-template", summary="Generate email template based on debt")
async def generate_template(
    payload: dict, sess: dict = Depends(deps.require_permission("invoice:read"))
):
    """
    Generates subject/body for collection email.
    Payload: {"customer_id": "CYG"}
    """
    conn = db.get_conn()
    try:
        cid = payload.get("customer_id")

        # Re-use logic or quick query to get debt profile
        # We need to know specific amounts to be smart

        # 1. Get Debt Profile
        row = conn.execute(
            """
            SELECT 
                SUM(total_final) as total,
                SUM(CASE WHEN EXTRACT(DAY FROM NOW() - issued_at::timestamp) > 60 THEN total_final ELSE 0 END) as critic
            FROM invoices 
            WHERE status='ISSUED' AND 
            (customer_id = %s OR customer_id = (SELECT laudus_customer_id FROM laudus_customers WHERE name ILIKE %s))
        """,
            (cid, cid),
        ).fetchone()

        total = 0
        critic = 0
        if row:
            # Handle dict/tuple ambiguity from driver
            if isinstance(row, dict):
                total = float(row.get("total") or 0)
                critic = float(row.get("critic") or 0)
            else:
                total = float(row[0] or 0)
                critic = float(row[1] or 0)

        company_name = "Monstruo S.A."

        # 2. Determine Tone
        if critic > 0:
            subject = f"URGENTE: Regularización de Pagos Pendientes - {cid}"
            body = f"""Estimados {cid},
            
Le escribimos para informarle que mantiene facturas vencidas por más de 60 días en nuestra contabilidad.
El monto crítico asciende a ${int(critic):,}.
            
Solicitamos regularizar esta situación a la brevedad para evitar bloqueos en el servicio.
            
Atentamente,
Departamento de Cobranza
{company_name}"""
        else:
            subject = f"Estado de Cuenta y Pagos Pendientes - {cid}"
            body = f"""Estimados {cid},
            
Esperamos que se encuentren bien.
Les enviamos un recordatorio cordial sobre el saldo pendiente en su cuenta por un total de ${int(total):,}.
            
Agradeceremos nos indique una fecha estimativa de pago.
            
Saludos cordiales,
{company_name}"""

        return {"subject": subject, "body": body}

    except Exception as e:
        print(f"Error tamplating: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
