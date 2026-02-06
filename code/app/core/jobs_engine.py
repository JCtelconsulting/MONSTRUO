import asyncio
import json
import traceback
import logging
from datetime import datetime, timedelta
from typing import Callable, Dict
from app.core import db

# Configuration
POLL_INTERVAL = 30  # seconds
JOB_HANDLERS: Dict[str, Callable] = {}

def register_job(job_type: str, handler: Callable):
    """Register a python function to a job type string."""
    JOB_HANDLERS[job_type] = handler

async def enqueue_job(job_type: str, payload: dict = {}, max_retries: int = 3):
    """Public helper to enqueue a job."""
    conn = db.get_conn()
    try:
        now = db.now_utc_iso()
        conn.execute(
            """INSERT INTO sys_jobs 
               (job_type, status, payload, next_run_at, retries_count, max_retries, created_at, updated_at)
               VALUES (?, 'PENDING', ?, ?, 0, ?, ?, ?)""",
            (job_type, json.dumps(payload), now, max_retries, now, now)
        )
        conn.commit()
    finally:
        conn.close()

async def process_job(job_row):
    """Execute a single job with retry logic."""
    job_id, job_type, payload_str, retries, max_retries = job_row['id'], job_row['job_type'], job_row['payload'], job_row['retries_count'], job_row['max_retries']
    
    handler = JOB_HANDLERS.get(job_type)
    conn = db.get_conn()
    now = db.now_utc_iso()
    
    if not handler:
        # Fatal error, unknown handler
        conn.execute("UPDATE sys_jobs SET status='FAILED', last_error='Unknown Handler', updated_at=? WHERE id=?", (now, job_id))
        conn.commit()
        conn.close()
        return

    try:
        # Parse payload
        payload = json.loads(payload_str)
        
        # Execute (Sync or Async support?)
        # For simplicity, we assume handlers are functions we can call. 
        # If they are async, we await them. If sync, we run in thread.
        if asyncio.iscoroutinefunction(handler):
            await handler(payload)
        else:
            await asyncio.to_thread(handler, payload)
            
        # Success
        conn.execute("UPDATE sys_jobs SET status='COMPLETED', updated_at=? WHERE id=?", (now, job_id))
        
    except Exception as e:
        error_msg = str(e) + "\n" + traceback.format_exc()
        print(f"[JobEngine] Job {job_id} ({job_type}) FAILED: {e}")
        
        if retries < max_retries:
            # Backoff: 2^retries * 60 seconds
            delay = (2 ** retries) * 60
            next_run = (datetime.utcnow() + timedelta(seconds=delay)).isoformat()
            conn.execute(
                "UPDATE sys_jobs SET status='RETRY', retries_count=retries_count+1, next_run_at=?, last_error=?, updated_at=? WHERE id=?",
                (next_run, error_msg, now, job_id)
            )
        else:
            # DLQ
            conn.execute(
                "UPDATE sys_jobs SET status='FAILED', last_error=?, updated_at=? WHERE id=?",
                (error_msg, now, job_id)
            )
    finally:
        conn.commit()
        conn.close()

async def worker_loop():
    """Background loop to poll and execute jobs."""
    print("[JobEngine] Worker started.")
    while True:
        try:
            conn = db.get_conn()
            now = db.now_utc_iso()
            
            # Simple locking mechanism: UPDATE ... RETURN is not fully concurrent-safe in SQLite without proper transaction modes,
            # but for this scale (single instance), a simple SELECT ... then UPDATE is "okay" if we accept rare race conditions 
            # or if we only have 1 worker. 
            # Better strategy for SQLite: Transaction exclusive.
            
            cursor = conn.execute(
                "SELECT id, job_type, payload, retries_count, max_retries FROM sys_jobs WHERE status IN ('PENDING', 'RETRY') AND next_run_at <= ? ORDER BY next_run_at ASC LIMIT 1",
                (now,)
            )
            row = cursor.fetchone()
            
            if row:
                job_data = dict(row)
                # Lock it
                conn.execute("UPDATE sys_jobs SET status='RUNNING', updated_at=? WHERE id=?", (now, job_data['id']))
                conn.commit()
                conn.close() # Free connection for execution phase
                
                # Process
                await process_job(job_data)
                
                # Loop immediately to check for more jobs
                continue
            else:
                conn.close()
                
            # No jobs, sleep
            await asyncio.sleep(POLL_INTERVAL)
            
        except asyncio.CancelledError:
            print("[JobEngine] Stopping worker.")
            break
        except Exception as e:
            print(f"[JobEngine] Loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL)
