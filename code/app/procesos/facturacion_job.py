from datetime import datetime, date, timedelta
import calendar
from app.core import db, sales_service
from app.servicios import indicators_service
from app.core import facturacion_service


def add_months(sourcedate: date, months: int) -> date:
    """Avanza una fecha N meses manteniendo el día si es posible."""
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


async def run_billing_cycles(payload: dict = None, **kwargs):
    """
    Evalúa reglas de facturación y genera borradores.
    Soporta:
    - billing_rules (legacy)
    - billing_profiles + invoice_templates (nuevo)
    """
    print(f"[BillingJob] Inciando proceso de ciclos: {datetime.now()}")
    conn = db.get_conn()
    try:
        today = date.today()
        # 1) NUEVO: billing_profiles (multi-factura por cliente)
        profs = conn.execute(
            """
            SELECT * FROM billing_profiles 
            WHERE is_active = 1 
            AND (next_billing_date IS NULL OR next_billing_date <= %s)
        """,
            (today.isoformat(),),
        ).fetchall()

        if profs:
            for p in profs:
                p = dict(p)
                pid = p["id"]
                cid = p["customer_id"]
                tpl_id = p.get("template_id")
                if not tpl_id:
                    print(f"[BillingJob] Perfil {pid} sin template_id, se omite.")
                    continue

                try:
                    inv = facturacion_service.create_invoice_from_template(
                        customer_id=str(cid),
                        template_id=int(tpl_id),
                        issuer_id="ROBOT_FACTURACION",
                        profile_id=int(pid),
                        currency_override=p.get("currency"),
                        uf_rule=p.get("uf_rule") or "VALOR_DIA",
                        uf_custom_value=float(p.get("uf_custom_value") or 0),
                        issue_date=today,
                    )
                    print(
                        f"[BillingJob] Draft creado para perfil {pid} (cliente {cid}): ID {inv.get('id')}"
                    )

                    # Auto-issue (SII via Laudus)
                    if int(p.get("auto_issue") or 0) == 1:
                        if not p.get("doc_type_id"):
                            print(
                                f"[BillingJob] Perfil {pid} con auto_issue pero sin doc_type_id, queda en DRAFT."
                            )
                        else:
                            inv2 = facturacion_service.issue_invoice_via_laudus(
                                invoice_id=int(inv["id"]),
                                customer_id=str(cid),
                                doc_type_id=int(p["doc_type_id"]),
                                purchase_order_number=p.get("purchase_order_number") or "",
                                notes=p.get("notes") or "",
                                user_id="ROBOT_FACTURACION",
                            )
                            print(
                                f"[BillingJob] Emitida en Laudus: local {inv2.get('id')} -> {inv2.get('external_id')}"
                            )

                    # Update next run
                    current_next = (
                        date.fromisoformat(p["next_billing_date"])
                        if p.get("next_billing_date")
                        else today
                    )
                    base_next = add_months(current_next, int(p.get("frequency_months") or 1))
                    dom = int(p.get("day_of_month") or base_next.day)
                    new_day = min(dom, calendar.monthrange(base_next.year, base_next.month)[1])
                    new_next = date(base_next.year, base_next.month, new_day)

                    conn.execute(
                        """
                        UPDATE billing_profiles SET
                            last_billed_at = %s,
                            next_billing_date = %s,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (
                            today.isoformat(),
                            new_next.isoformat(),
                            db.now_utc_iso(),
                            pid,
                        ),
                    )
                    conn.commit()
                except Exception as e:
                    print(f"[BillingJob] Error perfil {pid} (cliente {cid}): {e}")

        # 2) LEGACY: billing_rules (una regla por cliente)
        rows = conn.execute(
            """
            SELECT * FROM billing_rules 
            WHERE is_active = 1 
            AND (next_billing_date IS NULL OR next_billing_date <= %s)
        """,
            (today.isoformat(),),
        ).fetchall()

        if not profs and not rows:
            print("[BillingJob] No hay ciclos pendientes para hoy.")
            return

        uf_val = indicators_service.get_uf_value() or 37000.0

        for r in rows:
            cid = r["customer_id"]
            print(f"[BillingJob] Procesando cliente: {cid}")

            # 1. Calcular Monto
            factor = 1.0
            if r["currency"] == "UF":
                if r["uf_rule"] == "VALOR_DIA":
                    factor = uf_val
                elif r["uf_rule"] in ["VALOR_FIJO", "VALOR_CONTRATO"]:
                    factor = r["uf_custom_value"]

            unit_price = r["base_amount"] * factor

            # 2. Preparar Items (Glosa genérica por ahora)
            items = [
                {
                    "sku": "SERV-GENERIC",  # Debería ser configurable, pero usamos uno base
                    "quantity": 1,
                    "unit_price": unit_price,
                }
            ]

            # 3. Crear Borrador
            try:
                res = sales_service.create_invoice_draft(
                    customer_id=cid,
                    invoice_type="FACTURA",
                    issuer_id="ROBOT_FACTURACION",
                    items=items,
                )
                print(f"[BillingJob] Draft creado para {cid}: ID {res.get('id')}")

                # 4. Actualizar Regla (Siguiente fecha)
                current_next = (
                    date.fromisoformat(r["next_billing_date"])
                    if r["next_billing_date"]
                    else today
                )
                new_next = add_months(current_next, r["frequency_months"])

                conn.execute(
                    """
                    UPDATE billing_rules SET
                        last_billed_at = %s,
                        next_billing_date = %s,
                        updated_at = %s
                    WHERE id = %s
                """,
                    (
                        today.isoformat(),
                        new_next.isoformat(),
                        db.now_utc_iso(),
                        r["id"],
                    ),
                )
                conn.commit()

            except Exception as e:
                print(f"[BillingJob] Error creando factura para {cid}: {e}")

    finally:
        conn.close()

    # Re-encolar para próxima ejecución (cada 12 horas)
    if payload and payload.get("recurring"):
        from app.core import jobs_engine

        now_iso = db.now_utc_iso()
        next_run = (datetime.utcnow() + timedelta(hours=12)).isoformat()
        conn2 = db.get_conn()
        try:
            exists = conn2.execute(
                "SELECT 1 FROM sys_jobs WHERE job_type='SYNC_BILLING_CYCLES' AND status IN ('PENDING','RETRY')"
            ).fetchone()
            if not exists:
                conn2.execute(
                    """INSERT INTO sys_jobs
                       (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
                       VALUES ('SYNC_BILLING_CYCLES', 'PENDING', '{"recurring": true}', %s, 0, 1, %s, %s)""",
                    (next_run, now_iso, now_iso),
                )
                conn2.commit()
                print(f"[BillingJob] Próximo ciclo programado para {next_run}")
            else:
                print("[BillingJob] Job recurrente ya pendiente, no se re-encola.")
        finally:
            conn2.close()
