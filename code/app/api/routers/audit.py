from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional
from app.core import db, deps
import csv
import io
import json

router = APIRouter(prefix="/api/audit", tags=["audit"])

@router.get("/export")
def export_audit_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    limit: int = Query(1000, le=10000),
    sess: dict = Depends(deps.require_permission("audit:export"))
):
    """
    Exporta logs de auditoría.
    Formato CSV es streaming para evitar sobrecarga de memoria.
    """
    conn = db.get_conn()
    cursor = conn.cursor()
    
    # Simple query, could add filters later
    cursor.execute("SELECT id, timestamp, severity, actor, action, target, ip_address, metadata_json FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    
    if format == "json":
        columns = [desc[0] for desc in cursor.description]
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        conn.close()
        return results

    # CSV Streaming
    def iter_csv():
        yield "id,timestamp,severity,actor,action,target,ip_address,metadata\n"
        while True:
            rows = cursor.fetchmany(100)
            if not rows:
                break
            output = io.StringIO()
            writer = csv.writer(output)
            for row in rows:
                # row is tuple (id, ts, sev, actor, action, target, ip, meta)
                writer.writerow(row)
            yield output.getvalue()
        conn.close()

    return StreamingResponse(iter_csv(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit_logs.csv"})
