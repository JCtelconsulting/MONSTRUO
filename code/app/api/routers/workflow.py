from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

import workflow_db
from app.core import dependencias as auth_deps

router = APIRouter(prefix="/workflow", tags=["workflow"])

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class CaseCreate(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"       # low|medium|high|critical
    owner_role: str = "ops"        # ops|finance|warehouse|admin

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    assignee_role: str = "ops"
    due_date: str = ""

class CommentCreate(BaseModel):
    comment: str

class LinkDiscrepancy(BaseModel):
    discrepancy_key: str

@router.get("/cases")
def list_cases(
    status: str = "", 
    owner_role: str = "", 
    authorization: Optional[str] = Header(default=None)
):
    user = auth_deps.require_session(authorization)
    workflow_db.init_workflow_db()

    sql = "SELECT * FROM cases WHERE 1=1"
    params: List[Any] = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if owner_role:
        sql += " AND owner_role=?"
        params.append(owner_role)

    sql += " ORDER BY updated_at DESC, id DESC LIMIT 200"
    rows = workflow_db.q(sql, tuple(params))
    return {"items": [dict(r) for r in rows]}

@router.post("/cases")
def create_case(
    payload: CaseCreate,
    authorization: Optional[str] = Header(default=None)
):
    user = auth_deps.require_session(authorization)
    # Allow any authenticated user to create cases
    workflow_db.init_workflow_db()
    ts = now_utc_iso()
    cid = workflow_db.exec1(
        """INSERT INTO cases (title, description, status, priority, owner_role, created_by, created_at, updated_at)
           VALUES (?, ?, 'open', ?, ?, ?, ?, ?)""",
        (payload.title, payload.description, payload.priority, payload.owner_role, user.get("username",""), ts, ts),
    )
    return {"case_id": cid}

@router.get("/cases/{case_id}")
def get_case(
    case_id: int,
    authorization: Optional[str] = Header(default=None)
):
    user = auth_deps.require_session(authorization)
    workflow_db.init_workflow_db()

    cases = workflow_db.q("SELECT * FROM cases WHERE id=?", (case_id,))
    if not cases:
        raise HTTPException(status_code=404, detail="case not found")
    c = dict(cases[0])

    tasks = workflow_db.q("SELECT * FROM tasks WHERE case_id=? ORDER BY id ASC", (case_id,))
    links = workflow_db.q("SELECT * FROM task_links WHERE case_id=? ORDER BY id ASC", (case_id,))
    return {"case": c, "tasks": [dict(t) for t in tasks], "links": [dict(l) for l in links]}

@router.post("/cases/{case_id}/tasks")
def add_task(
    case_id: int, 
    payload: TaskCreate,
    authorization: Optional[str] = Header(default=None)
):
    user = auth_deps.require_session(authorization)
    workflow_db.init_workflow_db()
    ts = now_utc_iso()

    exists = workflow_db.q("SELECT id FROM cases WHERE id=?", (case_id,))
    if not exists:
        raise HTTPException(status_code=404, detail="case not found")

    tid = workflow_db.exec1(
        """INSERT INTO tasks (case_id, title, description, status, assignee_role, due_date, created_at, updated_at)
           VALUES (?, ?, ?, 'open', ?, ?, ?, ?)""",
        (case_id, payload.title, payload.description, payload.assignee_role, payload.due_date, ts, ts),
    )
    return {"task_id": tid}

@router.post("/tasks/{task_id}/comment")
def add_comment(
    task_id: int, 
    payload: CommentCreate,
    authorization: Optional[str] = Header(default=None)
):
    user = auth_deps.require_session(authorization)
    workflow_db.init_workflow_db()
    ts = now_utc_iso()

    exists = workflow_db.q("SELECT id FROM tasks WHERE id=?", (task_id,))
    if not exists:
        raise HTTPException(status_code=404, detail="task not found")

    cid = workflow_db.exec1(
        "INSERT INTO task_comments (task_id, author, comment, created_at) VALUES (?, ?, ?, ?)",
        (task_id, user.get("username",""), payload.comment, ts),
    )
    return {"comment_id": cid}

@router.post("/link/discrepancy")
def link_discrepancy_to_case(
    case_id: int, 
    payload: LinkDiscrepancy,
    authorization: Optional[str] = Header(default=None)
):
    user = auth_deps.require_session(authorization)
    role = (user.get("role") or "")
    if role not in ("admin", "finance"):
        raise HTTPException(status_code=403, detail="forbidden")

    workflow_db.init_workflow_db()
    ts = now_utc_iso()

    # Ensure discrepancy exists
    rows = workflow_db.q("SELECT key FROM parrotfy_discrepancies WHERE key=?", (payload.discrepancy_key,))
    if not rows:
        raise HTTPException(status_code=404, detail="discrepancy not found")

    # Ensure case exists
    c = workflow_db.q("SELECT id FROM cases WHERE id=?", (case_id,))
    if not c:
        raise HTTPException(status_code=404, detail="case not found")

    try:
        workflow_db.exec1(
            "INSERT INTO task_links (case_id, link_type, link_key, created_at) VALUES (?, 'parrotfy_discrepancy', ?, ?)",
            (case_id, payload.discrepancy_key, ts),
        )
    except Exception:
        # ignore duplicates
        pass

    return {"linked": True}


class StatusUpdate(BaseModel):
    status: str

@router.post("/tasks/{task_id}/status")
def set_task_status(
    task_id: int, 
    payload: StatusUpdate,
    authorization: Optional[str] = Header(default=None)
):
    user = auth_deps.require_session(authorization)
    workflow_db.init_workflow_db()
    ts = now_utc_iso()
    # Validate
    if payload.status not in ("open", "doing", "blocked", "done"):
        raise HTTPException(status_code=400, detail="invalid status")
    exists = workflow_db.q("SELECT id FROM tasks WHERE id=?", (task_id,))
    if not exists:
        raise HTTPException(status_code=404, detail="task not found")
    workflow_db.exec1("UPDATE tasks SET status=?, updated_at=? WHERE id=?", (payload.status, ts, task_id))
    return {"ok": True}
