from fastapi import APIRouter, Depends
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from app.core import db, deps

router = APIRouter(prefix="/api/ops", tags=["ops"])

@router.get("/dashboard", response_model=Dict[str, Any])
def get_dashboard_stats(
    sess: dict = Depends(deps.require_permission("dashboard:read"))
):
    """
    Aggregates System Health, Sales KPIs, and Ticket Stats.
    """
    conn = db.get_conn()
    try:
        stats = {
            "system_status": "healthy",
            "kpis": {},
            "jobs_health": {},
            "recent_failures": []
        }
        
        today = db.now_utc_iso()[:10] # YYYY-MM-DD
        
        # 1. SALES KPI
        # Count issued invoices today
        row = conn.execute(
            "SELECT count(*) as cnt, sum(total_final) as total FROM invoices WHERE status='ISSUED' AND issued_at LIKE ?", 
            (f"{today}%",)
        ).fetchone()
        sales_today_count = row["cnt"] or 0
        sales_today_amount = row["total"] or 0.0
        if sales_today_count == 0 and float(sales_today_amount or 0) == 0.0:
            row_laudus = conn.execute(
                """
                SELECT count(*) as cnt, sum(total_amount) as total
                FROM laudus_invoices
                WHERE doc_date LIKE ?
                """,
                (f"{today}%",),
            ).fetchone()
            sales_today_count = row_laudus["cnt"] or 0
            sales_today_amount = row_laudus["total"] or 0.0

        stats["kpis"]["sales_today_count"] = sales_today_count
        stats["kpis"]["sales_today_amount"] = sales_today_amount
        
        # 2. TICKETS KPI
        # Open tickets
        row = conn.execute("SELECT count(*) as cnt FROM tickets WHERE estado != 'cerrado'").fetchone()
        stats["kpis"]["tickets_open"] = row["cnt"]
        
        # Critical tickets (SLA Breach)
        row = conn.execute("SELECT count(*) as cnt FROM tickets WHERE severidad='critica' AND estado != 'cerrado'").fetchone()
        stats["kpis"]["tickets_critical"] = row["cnt"]
        
        # 3. JOBS HEALTH
        # Failures last 24h
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        row = conn.execute("""
            SELECT count(*) as cnt FROM sys_jobs 
            WHERE status='FAILED' AND updated_at >= ?
        """, (cutoff,)).fetchone()
        stats["jobs_health"]["failures_24h"] = row["cnt"]
        if row["cnt"] > 0:
            stats["system_status"] = "degraded"
            
        # Recent Failures Table
        rows = conn.execute("""
            SELECT job_type, last_error, updated_at 
            FROM sys_jobs 
            WHERE status='FAILED' 
            ORDER BY updated_at DESC LIMIT 5
        """).fetchall()
        stats["recent_failures"] = [dict(r) for r in rows]
        
        # 4. CUSTOMERS KPI
        row = conn.execute("SELECT count(*) as cnt FROM customers").fetchone()
        stats["kpis"]["total_customers"] = row["cnt"]

        return stats
    finally:
        conn.close()
