from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.core import db, deps, jobs_engine

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.get("/", response_model=List[dict])
def list_jobs(
    limit: int = 50,
    status: str = None,
    sess: dict = Depends(deps.require_permission("admin"))
):
    conn = db.get_conn()
    try:
        query = "SELECT * FROM sys_jobs"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status.upper())
            
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        
        cursor = conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

@router.post("/{job_id}/retry")
async def retry_job(
    job_id: int,
    sess: dict = Depends(deps.require_permission("admin"))
):
    conn = db.get_conn()
    try:
        # Check ownership logic if needed, here pure admin
        job = conn.execute("SELECT * FROM sys_jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
            
        # Reset to PENDING, now, 0 retries (or keep count?)
        # Let's simple reset to give it a fresh chance
        now = db.now_utc_iso()
        conn.execute(
            "UPDATE sys_jobs SET status='PENDING', next_run_at=?, last_error='', retries_count=0 WHERE id=?",
            (now, job_id)
        )
        conn.commit()
        return {"status": "queued"}
    finally:
        conn.close()

@router.post("/trigger/{job_type}")
async def trigger_manual_job(
    job_type: str,
    sess: dict = Depends(deps.require_permission("admin"))
):
    # trigger immediate
    conn = db.get_conn()
    try:
        # Check if job exists in registry?
        if job_type not in jobs_engine.JOB_HANDLERS:
             raise HTTPException(status_code=400, detail="Unknown job type")
             
        await jobs_engine.enqueue_job(job_type, payload={"manual_trigger_by": sess["username"]})
        return {"status": "enqueued", "job": job_type}
    finally:
        conn.close()
