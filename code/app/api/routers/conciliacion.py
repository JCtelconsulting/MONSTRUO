from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import List, Optional
from datetime import datetime
import io

from app.core.db import get_conn
from app.core import deps as auth_deps
from app.servicios.bank_parser import BankParser

router = APIRouter(prefix="/api/conciliacion", tags=["Conciliacion"])


@router.get("/banks", summary="Listar cuentas bancarias disponibles")
def list_banks(sess: dict = Depends(auth_deps.require_session_hybrid)):
    conn = get_conn()
    try:
        # Solo mostrar cuentas activas
        rows = conn.execute(
            "SELECT id, name, bank_name, account_number, laudus_account_id FROM bank_accounts WHERE is_active=1"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# Helper for auth
def get_current_username(sess: dict = Depends(auth_deps.require_session_hybrid)) -> str:
    return sess["username"]


@router.post("/upload", summary="Subir cartola bancaria")
async def upload_statement(
    bank_account_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_username),
):
    if not file.filename.endswith(".csv") and not file.filename.endswith(".txt"):
        raise HTTPException(
            status_code=400, detail="Solo se permiten archivos CSV/TXT por ahora."
        )

    # 1. Leer contenido
    content_bytes = await file.read()
    try:
        content_str = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content_str = content_bytes.decode("latin-1")  # Fallback comun en bancos

    # 2. Parsear (Asumimos Santander o Genérico por ahora)
    # TODO: Detectar formato según banco o parámetro
    try:
        lines = BankParser.parse_santander_csv(content_str)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Error parseando archivo: {str(e)}"
        )

    if not lines:
        raise HTTPException(
            status_code=400,
            detail="No se encontraron movimientos válidos en el archivo.",
        )

    # 3. Guardar en DB
    conn = get_conn()
    try:
        # Validate bank_account exists
        acc = conn.execute(
            "SELECT id FROM bank_accounts WHERE id=?", (bank_account_id,)
        ).fetchone()
        if not acc:
            raise HTTPException(
                status_code=404, detail="Cuenta bancaria no encontrada."
            )

        # Create Header
        period_start = min(l["date"] for l in lines)
        period_end = max(l["date"] for l in lines)

        # Calculate totals
        total_dep = sum(l["amount"] for l in lines if l["amount"] > 0)
        total_wd = sum(abs(l["amount"]) for l in lines if l["amount"] < 0)

        # INSERT statements
        # Statement
        cur = conn.execute(
            """
            INSERT INTO bank_statements (
                bank_account_id, filename, uploaded_at, uploaded_by, 
                period_start, period_end, total_deposit, total_withdrawal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
        """,
            (
                bank_account_id,
                file.filename,
                datetime.now().isoformat(),
                current_user,
                period_start,
                period_end,
                float(total_dep),
                float(total_wd),
            ),
        )

        stmt_id = cur.fetchone()["id"]

        # Lines (Bulk insert usually better, but robust loop for now is safer with UNIQUE constraints/Logic)
        inserted_count = 0
        skipped_count = 0

        for l in lines:
            # Check for dupe hash globally or just insert?
            # If we want to avoid re-inserting SAME transaction from overlapping statements,
            # we should check hash existence in `bank_statement_lines`.
            # BUT hashes are not unique globally (same transaction amount/desc could happen twice on same day?)
            # Santander provides unique Doc Num usually. If generic, hash collision risk exists.
            # Strategy: Insert, let unique index handle if we had one.
            # Our schema has index on hash but NOT unique constraint yet.
            # Let's check manually to avoid dupes.

            exists = conn.execute(
                "SELECT id FROM bank_statement_lines WHERE hash=?", (l["hash"],)
            ).fetchone()
            if exists:
                skipped_count += 1
                continue

            conn.execute(
                """
                INSERT INTO bank_statement_lines (
                    statement_id, date, description, document_number, amount, balance, hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    stmt_id,
                    l["date"],
                    l["description"],
                    l["document_number"],
                    l["amount"],
                    l["balance"],
                    l["hash"],
                ),
            )
            inserted_count += 1

        conn.commit()

        return {
            "status": "success",
            "statement_id": stmt_id,
            "period": f"{period_start} to {period_end}",
            "lines_processed": len(lines),
            "lines_inserted": inserted_count,
            "lines_skipped_duplicate": skipped_count,
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


from app.servicios import bank_sync, matcher_service
from app.core import payment_service


@router.post("/sync", summary="Sincronizar desde Laudus (Ledger)")
async def sync_laudus(
    bank_account_id: int = Form(None),
    sess: dict = Depends(auth_deps.require_session_hybrid),
):
    try:
        # Run sync synchronously for immediate feedback (volume is low)
        res = bank_sync.sync_ledger_to_statement(bank_account_id)
        return {"status": "success", "results": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/movements", summary="Listar movimientos de cartola")
def list_movements(
    bank_account_id: int,
    limit: int = 100,
    sess: dict = Depends(auth_deps.require_session_hybrid),
):
    conn = get_conn()
    try:
        # Fetch latest movements
        # Fetch latest movements with Match Info
        query = """
        SELECT 
            l.id, l.date, l.description, l.document_number, l.amount, l.balance, l.reconciled_at,
            r.id as rec_id, r.confidence, r.match_type,
            i.id as invoice_id, i.customer_id, i.total_final as invoice_amount, i.external_id
        FROM bank_statement_lines l
        JOIN bank_statements s ON l.statement_id = s.id
        LEFT JOIN bank_reconciliations r ON l.id = r.statement_line_id
        LEFT JOIN invoices i ON r.match_id = CAST(i.id AS TEXT) AND r.match_type = 'invoice'
        WHERE s.bank_account_id = ?
        ORDER BY l.date DESC
        LIMIT ?
        """
        rows = conn.execute(query, (bank_account_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/match", summary="Ejecutar motor de conciliación")
def run_matching(
    statement_id: int = Form(...),
    sess: dict = Depends(auth_deps.require_session_hybrid),
):
    try:
        matcher = matcher_service.MatcherService()
        results = matcher.match_statement_to_invoices(statement_id)
        return {"status": "success", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/matches", summary="Obtener sugerencias de conciliación")
def get_matches(
    statement_id: int, sess: dict = Depends(auth_deps.require_session_hybrid)
):
    conn = get_conn()
    try:
        # Return lines joined with Invoices (via match_id)
        query = """
        SELECT 
            l.id as line_id, l.date, l.description, l.amount, l.document_number,
            r.id as rec_id, r.confidence, r.match_type,
            -- Invoice Details
            i.id as invoice_id, i.customer_id, i.total_final as invoice_amount, i.created_at as invoice_date
        FROM bank_statement_lines l
        LEFT JOIN bank_reconciliations r ON l.id = r.statement_line_id
        LEFT JOIN invoices i ON r.match_id = CAST(i.id AS TEXT) AND r.match_type = 'invoice'
        WHERE l.statement_id = ?
        AND l.reconciled_at IS NULL
        ORDER BY l.date DESC
        """
        rows = conn.execute(query, (statement_id,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.post("/approve", summary="Aprobar Match (Pago Local)")
def approve_match(
    match_id: int = Form(...), sess: dict = Depends(auth_deps.require_session_hybrid)
):
    conn = get_conn()
    try:
        # 1. Get Match Info
        rec = conn.execute(
            "SELECT * FROM bank_reconciliations WHERE id=%s", (match_id,)
        ).fetchone()
        if not rec:
            raise HTTPException(status_code=404, detail="Match not found")

        if rec["match_type"] != "invoice":
            raise HTTPException(
                status_code=400, detail="Only invoice matches supported for now"
            )

        invoice_id = int(rec["match_id"])
        line_id = rec["statement_line_id"]

        # 2. Get Bank Line Amount
        line = conn.execute(
            "SELECT amount, date FROM bank_statement_lines WHERE id=%s", (line_id,)
        ).fetchone()

        # 3. Register Payment (Local)
        # Note: We pass the bank line amount. If it matches invoice, it will pay it.
        res = payment_service.register_payment_local(
            invoice_id=invoice_id,
            amount=line["amount"],
            date_str=line["date"],
            reference=f"MATCH-BANK-{line_id}",
        )

        # 4. Mark Line as Reconciled
        conn.execute(
            "UPDATE bank_statement_lines SET reconciled_at=NOW() WHERE id=%s",
            (line_id,),
        )

        # 5. Delete other suggestions for this line
        conn.execute(
            "DELETE FROM bank_reconciliations WHERE statement_line_id=%s AND id != %s",
            (line_id, match_id),
        )

        conn.commit()
        return {"status": "success", "payment": res}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/statements", summary="Listar cartolas por cuenta")
def list_statements(
    bank_account_id: int, sess: dict = Depends(auth_deps.require_session_hybrid)
):
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, filename, uploaded_at, period_start, period_end, status, total_deposit, total_withdrawal
            FROM bank_statements
            WHERE bank_account_id=?
            ORDER BY uploaded_at DESC
        """,
            (bank_account_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
