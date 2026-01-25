from typing import Optional, List, Any, Dict
from fastapi import Query, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import subprocess

import nucleo as db
import rutas_workflow
import dependencias as auth_deps
import api  # existing app

app = api.app
app.mount("/ui", StaticFiles(directory="ui", html=True), name="ui")

class LoginIn(BaseModel):
    username: str
    password: str

@app.post("/auth/login")
def login(body: LoginIn):
    user = db.verify_user(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="bad_credentials")
    sess = db.create_session(user["username"], user["role"], minutes=720)
    return {"access_token": sess["token"], "token_type": "bearer", "role": sess["role"], "expires_at": sess["expires_at"]}

@app.get("/auth/me")
def me(authorization: Optional[str] = Header(default=None)):
    sess = auth_deps.require_session(authorization)
    return {"username": sess["username"], "role": sess["role"], "expires_at": sess["expires_at"]}

# -----------------------------
# ACTIONS (protected)
# -----------------------------
@app.post("/actions/sync-now")
def sync_now(authorization: Optional[str] = Header(default=None)):
    sess = auth_deps.require_session(authorization)
    # Only admin + finance can run full sync
    auth_deps.require_roles(sess, ["admin", "finance"])

    p = subprocess.run(["python3", "run_pipeline.py"], capture_output=True, text=True)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode != 0:
        raise HTTPException(status_code=500, detail={"step_failed": True, "stdout": out[-1500:], "stderr": err[-1500:]})
    return {"status": "ok", "stdout": out[-2000:]}

# -----------------------------
# Alerts endpoints (protected read)
# -----------------------------
@app.get("/alerts")
def list_alerts(
    authorization: Optional[str] = Header(default=None),
    status: str = Query("open", pattern="^(open|resolved|all)$"),
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    sess = auth_deps.require_session(authorization)
    # Finance and admin can see alerts. Ops can see later if you want.
    auth_deps.require_roles(sess, ["admin", "finance"])

    db.init_db()
    conn = db.get_conn()
    try:
        where = []
        params: List[Any] = []
        if status != "all":
            where.append("status = ?")
            params.append(status)
        if severity:
            where.append("severity = ?")
            params.append(severity)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
            SELECT rule, severity, entity_type, entity_id, summary, status, first_seen_at, last_seen_at, resolved_at, occurrences
            FROM alerts
            {where_sql}
            ORDER BY last_seen_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        rows = conn.execute(sql, tuple(params)).fetchall()
        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()

@app.get("/alerts/summary")
def alerts_summary(authorization: Optional[str] = Header(default=None)):
    sess = auth_deps.require_session(authorization)
    auth_deps.require_roles(sess, ["admin", "finance"])

    db.init_db()
    conn = db.get_conn()
    try:
        sev = conn.execute("""
            SELECT severity, count(*) AS n
            FROM alerts
            WHERE status='open'
            GROUP BY severity
            ORDER BY n DESC
        """).fetchall()
        rule = conn.execute("""
            SELECT rule, count(*) AS n
            FROM alerts
            WHERE status='open'
            GROUP BY rule
            ORDER BY n DESC
        """).fetchall()
        return {
            "by_severity": {r["severity"]: r["n"] for r in sev},
            "by_rule": {r["rule"]: r["n"] for r in rule},
        }
    finally:
        conn.close()

# Workflow
app.include_router(rutas_workflow.router)

from rutas_crm import router as crm_router

app.include_router(crm_router)

# from summary_api import router as summary_router

# app.include_router(summary_router)

# from compliance_api import router as compliance_router

# app.include_router(compliance_router)

# from events_api import router as events_router

# app.include_router(events_router)

from rutas_ai import router as ai_router

app.include_router(ai_router)

from rutas_bridge import router as bridge_router

app.include_router(bridge_router)
