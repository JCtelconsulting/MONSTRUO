from typing import List, Optional, Dict, Any, Union
from app.core import db, bodega_service


def create_invoice_draft(
    customer_id: str,
    invoice_type: str,  # FACTURA, BOLETA, NC, ND
    issuer_id: str,
    items: List[Dict[str, Any]],
    ref_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Create a new invoice in DRAFT status.
    items: [{sku, quantity, unit_price}]
    Example items: [{"sku": "SKU-1", "quantity": 1, "unit_price": 1000}]
    """
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()

        # Calculate totals
        total_net = 0
        total_tax = 0  # 19% Chile?

        for item in items:
            subtotal = item["quantity"] * item["unit_price"]
            total_net += subtotal

        total_tax = total_net * 0.19
        total_final = total_net + total_tax

        cursor = conn.execute(
            """
            INSERT INTO invoices 
            (customer_id, type, status, total_net, total_tax, total_final, ref_id, issuer_id, created_at, updated_at)
            VALUES (?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?) RETURNING id
        """,
            (
                customer_id,
                invoice_type.upper(),
                total_net,
                total_tax,
                total_final,
                ref_id,
                issuer_id,
                now,
                now,
            ),
        )

        row = cursor.fetchone()
        invoice_id = row["id"] if row else None

        # Insert items
        for item in items:
            subtotal = item["quantity"] * item["unit_price"]
            conn.execute(
                """
                INSERT INTO invoice_items (invoice_id, product_sku, quantity, unit_price, subtotal)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    invoice_id,
                    item["sku"],
                    item["quantity"],
                    item["unit_price"],
                    subtotal,
                ),
            )

        conn.commit()
        return get_invoice(invoice_id)
    finally:
        conn.close()


def get_invoice(invoice_id: Union[int, str]) -> Optional[Dict[str, Any]]:
    conn = db.get_conn()
    try:
        # Determine if invoice_id is local (int) or remote (alphanumeric/str)
        # Heuristic: all digits and < 9 chars is likely a local ID
        is_local_id = str(invoice_id).isdigit() and len(str(invoice_id)) < 9

        row = None
        if is_local_id:
            # Standard local lookup
            query = """
                SELECT i.*, lc.legal_name as customer_name
                FROM invoices i
                LEFT JOIN laudus_customers lc ON lc.laudus_customer_id = i.customer_id
                WHERE i.id = %s
            """
            row = conn.execute(query, (int(invoice_id),)).fetchone()
        else:
            # Fallback: Try looking up by external_id directly
            # This handles cases like "E00000722" passed directly
            query = """
                SELECT i.*, lc.legal_name as customer_name
                FROM invoices i
                LEFT JOIN laudus_customers lc ON lc.laudus_customer_id = i.customer_id
                WHERE i.external_id = %s
            """
            row = conn.execute(query, (str(invoice_id),)).fetchone()

        if not row:
            # If not found in invoices table, check laudus_invoices directly
            laudus_query = """
                SELECT 
                    l.laudus_invoice_id as id, 
                    COALESCE(lc.name, l.customer_id) as customer_id, 
                    lc.legal_name as customer_name,
                    'FACTURA' as type, 
                    CASE WHEN l.is_paid=1 THEN 'PAID' ELSE 'ISSUED' END as status,
                    l.total_amount as total_final, 
                    l.doc_date as created_at, 
                    'LAUDUS' as origin,
                    l.laudus_invoice_id as external_id
                FROM laudus_invoices l
                LEFT JOIN laudus_customers lc ON lc.laudus_customer_id = l.customer_id
                WHERE l.laudus_invoice_id = %s
            """
            l_row = conn.execute(laudus_query, (str(invoice_id),)).fetchone()
            if l_row:
                res = dict(l_row)
                res["items"] = []
            else:
                return None
        else:
            res = dict(row)
            # Get items locally
            items_cur = conn.execute(
                "SELECT * FROM invoice_items WHERE invoice_id = %s", (res["id"],)
            )
            local_items = [dict(r) for r in items_cur.fetchall()]
            res["items"] = local_items

        # Logic to enrich with remote details
        should_enrich = (
            res.get("origin") == "LAUDUS"
            or (res.get("external_id") and str(res.get("external_id")).strip() != "")
            or (str(invoice_id) == str(res.get("external_id")))
        )

        if should_enrich:
            try:
                from app.integraciones.laudus import LaudusClient

                client = LaudusClient()

                remote_id = str(res.get("external_id") or "")

                # Check for Fuzzy Match need if remote_id missing or local-looking
                if not remote_id or (remote_id.isdigit() and int(remote_id) < 100000):
                    try:
                        cust_id = res["customer_id"]
                        total = res["total_final"]
                        date_ts = res["created_at"]

                        fuzzy_query = """
                            SELECT laudus_invoice_id 
                            FROM laudus_invoices 
                            WHERE TRIM(customer_id) = TRIM(%s)
                            AND ABS(total_amount - %s) < 1.0
                            AND doc_date::date >= (%s::date - INTERVAL '1 day')
                            AND doc_date::date <= (%s::date + INTERVAL '1 day')
                            LIMIT 1
                        """
                        match = conn.execute(
                            fuzzy_query, (cust_id, total, date_ts, date_ts)
                        ).fetchone()
                        if match:
                            remote_id = match["laudus_invoice_id"]
                            # Update local record if possible
                            if is_local_id and res.get("id"):
                                conn.execute(
                                    "UPDATE invoices SET external_id = %s WHERE id = %s",
                                    (remote_id, res["id"]),
                                )
                                conn.commit()
                            print(
                                f"DEBUG: Fuzzy resolved Invoice {invoice_id} -> {remote_id}"
                            )
                    except Exception as e:
                        print(f"Fuzzy match error in get_invoice: {e}")

                if remote_id:
                    details = client.get_invoice_details(remote_id)
                    if details:
                        # Map Laudus items to local structure for display
                        mapped_items = []
                        for it in details.get("items", []):
                            mapped_items.append(
                                {
                                    "product_sku": it.get("product", {}).get("sku")
                                    or it.get("description", "Item"),
                                    "quantity": it.get("quantity", 0),
                                    "subtotal": it.get("total", 0),
                                    "unit_price": it.get("unitPrice", 0),
                                }
                            )

                        # Overwrite items with fresh remote data for display accuracy
                        if mapped_items:
                            res["items"] = mapped_items

                        # Enrich keys
                        res["files"] = details.get("files", [])
                        res["payment_term"] = details.get("term", {}).get(
                            "name"
                        ) or details.get("term", {}).get("description")

                        # If name was missing locally, try to fill it
                        if not res.get("customer_name") and details.get("customer"):
                            res["customer_name"] = details["customer"].get(
                                "legalName"
                            ) or details["customer"].get("name")
            except Exception as e:
                print(f"Error fetching remote details for invoice {invoice_id}: {e}")

        return res
    finally:
        conn.close()


def issue_invoice(invoice_id: int, user_id: str) -> Dict[str, Any]:
    """
    Transition DRAFT -> ISSUED.
    Deducts stock from Bodega using bodega_service.
    """
    conn = db.get_conn()
    try:
        # 1. Lock & Get
        cursor = conn.execute(
            "SELECT status, type FROM invoices WHERE id = ?", (invoice_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Invoice not found")
        status, inv_type = row["status"], row["type"]

        if status != "DRAFT":
            raise ValueError(f"Cannot issue invoice in status {status}")

        # 2. Get items (+ whether they are services)
        items = conn.execute(
            """
            SELECT ii.product_sku, ii.quantity, COALESCE(p.is_service, FALSE) AS is_service
            FROM invoice_items ii
            LEFT JOIN products p ON p.sku = ii.product_sku
            WHERE ii.invoice_id = ?
            """,
            (invoice_id,),
        ).fetchall()

        stock_action = "SALE"
        if inv_type in ["NC"]:
            stock_action = "RETURN"

        for item in items:
            sku, qty = item["product_sku"], item["quantity"]
            is_service = bool(item.get("is_service"))
            if is_service:
                continue

            adjust_qty = -qty if stock_action == "SALE" else qty
            bodega_service.adjust_stock(
                sku=sku,
                quantity=adjust_qty,
                reason_type=stock_action,
                user_id=user_id,
                reference=f"INV-{invoice_id}",
            )

        # 4. Update Status
        now = db.now_utc_iso()
        conn.execute(
            "UPDATE invoices SET status = 'ISSUED', issued_at = ?, issuer_id = ?, updated_at = ? WHERE id = ?",
            (now, user_id, now, invoice_id),
        )
        conn.commit()

        return get_invoice(invoice_id)
    finally:
        conn.close()


def void_invoice(
    invoice_id: int, user_id: str, reason: str = "Voiding"
) -> Dict[str, Any]:
    """
    Void an issued invoice by creating a NC.
    """
    orig = get_invoice(invoice_id)
    if not orig:
        raise ValueError("Invoice not found")

    if orig["status"] not in ["ISSUED", "PAID"]:
        raise ValueError("Can only void ISSUED or PAID invoices")

    if orig["type"] == "NC":
        raise ValueError("Cannot void a NC")

    # 1. Create NC Draft with same items
    items_payload = [
        {
            "sku": i["product_sku"],
            "quantity": i["quantity"],
            "unit_price": i["unit_price"],
        }
        for i in orig["items"]
    ]

    nc = create_invoice_draft(
        customer_id=orig["customer_id"],
        invoice_type="NC",
        issuer_id=user_id,
        items=items_payload,
        ref_id=invoice_id,
    )

    # 2. Issue NC (Restores Stock)
    issue_invoice(nc["id"], user_id)

    conn = db.get_conn()
    conn.execute(
        "UPDATE invoices SET status = 'VOID', updated_at = ? WHERE id = ?",
        (db.now_utc_iso(), invoice_id),
    )
    conn.commit()
    conn.close()

    return get_invoice(nc["id"])


def list_invoices(
    status: Optional[str] = None, customer_id: Optional[str] = None, limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Unified list: local + Laudus + Parrotfy
    """
    conn = db.get_conn()
    try:
        results = []

        # 1. Unified Invoices (Local + Synced)
        # Check issuer_id to determine origin
        # Join with laudus_customers to get name if available
        sql = """
            SELECT 
                i.id, 
                COALESCE(INITCAP(c.name), i.customer_id) as customer_id, 
                i.type, 
                i.status, 
                i.total_final, 
                i.created_at, 
                COALESCE(i.external_id, l.laudus_invoice_id) as external_id,
                CASE 
                    WHEN i.issuer_id = 'laudus_sync' THEN 'LAUDUS' 
                    WHEN i.external_id IS NOT NULL THEN 'LAUDUS'
                    ELSE 'LOCAL' 
                END as origin 
            FROM invoices i
            LEFT JOIN laudus_customers c ON c.laudus_customer_id = i.customer_id
            LEFT JOIN laudus_invoices l ON (
                TRIM(l.customer_id) = TRIM(i.customer_id) 
                AND ABS(l.total_amount - i.total_final) < 1.0
                AND l.doc_date::date >= (i.created_at::date - INTERVAL '1 day') 
                AND l.doc_date::date <= (i.created_at::date + INTERVAL '1 day')
            )
            WHERE 1=1
        """
        params = []
        if status:
            sql += " AND status = ?"
            params.append(status.upper())
        if customer_id:
            sql += " AND customer_id = ?"
            params.append(customer_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(sql, params)
        for r in cur.fetchall():
            results.append(dict(r))

        # 2. Laudus
        if len(results) < limit:
            sql = """
                SELECT 
                    l.laudus_invoice_id as id, 
                    COALESCE(c.name, l.customer_id) as customer_id, 
                    'FACTURA' as type, 
                    CASE WHEN l.is_paid=1 THEN 'PAID' ELSE 'ISSUED' END as status,
                    l.total_amount as total_final, 
                    l.doc_date as created_at, 
                    'LAUDUS' as origin,
                    l.laudus_invoice_id as external_id
                FROM laudus_invoices l
                LEFT JOIN laudus_customers c ON c.laudus_customer_id = l.customer_id
                WHERE 1=1
            """
            params = []
            if status:
                if status.upper() == "PAID":
                    sql += " AND is_paid = 1"
                elif status.upper() == "ISSUED":
                    sql += " AND is_paid = 0"
                else:
                    sql += " AND 1=0"
            if customer_id:
                sql += " AND customer_id = ?"
                params.append(customer_id)
            sql += " ORDER BY doc_date DESC LIMIT ?"
            params.append(limit - len(results))
            cur = conn.execute(sql, params)
            for r in cur.fetchall():
                results.append(dict(r))

        # 3. Parrotfy
        if len(results) < limit:
            sql = """
                SELECT parrotfy_invoice_id as id, customer_id, 'FACTURA' as type, 
                       status, total_amount as total_final, issued_date as created_at, 'PARROTFY' as origin,
                       parrotfy_invoice_id as external_id
                FROM parrotfy_invoices WHERE 1=1
            """
            params = []
            if status:
                sql += " AND status = ?"
                params.append(status.upper())
            if customer_id:
                sql += " AND customer_id = ?"
                params.append(customer_id)
            sql += " ORDER BY issued_date DESC LIMIT ?"
            params.append(limit - len(results))
            cur = conn.execute(sql, params)
            for r in cur.fetchall():
                results.append(dict(r))

        results.sort(key=lambda x: str(x["created_at"]), reverse=True)
        return results[:limit]
    finally:
        conn.close()
