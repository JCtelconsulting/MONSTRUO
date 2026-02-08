#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from jira_client import load_cfg, has_creds, make_session

DB_PATH = "monstruo.db"

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_tables(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS jira_issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        jira_id TEXT NOT NULL UNIQUE,
        jira_key TEXT DEFAULT '',
        summary TEXT DEFAULT '',
        status TEXT DEFAULT '',
        status_category TEXT DEFAULT '',
        updated_at TEXT DEFAULT '',
        raw_json TEXT NOT NULL,
        synced_at TEXT DEFAULT ''
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jira_issues_status ON jira_issues(status);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jira_issues_updated ON jira_issues(updated_at);")
    conn.commit()

def upsert_issue(conn: sqlite3.Connection, jira_id: str, jira_key: str, summary: str, status: str,
                 status_category: str, updated_at: str, raw_json: str, synced_at: str) -> None:
    conn.execute("""
    INSERT INTO jira_issues (jira_id, jira_key, summary, status, status_category, updated_at, raw_json, synced_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(jira_id) DO UPDATE SET
      jira_key=excluded.jira_key,
      summary=excluded.summary,
      status=excluded.status,
      status_category=excluded.status_category,
      updated_at=excluded.updated_at,
      raw_json=excluded.raw_json,
      synced_at=excluded.synced_at;
    """, (jira_id, jira_key, summary, status, status_category, updated_at, raw_json, synced_at))

def safe_get(d: Dict[str, Any], path: List[str], default: str = "") -> str:
    cur: Any = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    if cur is None:
        return default
    return str(cur)

def fetch_jsm_requests(cfg: dict) -> List[Dict[str, Any]]:
    # JSM customer/agent request list (may be limited if only customer)
    s = make_session(cfg)
    base = cfg["base"]
    out: List[Dict[str, Any]] = []
    start = 0
    limit = 50
    for _ in range(50):
        url = f"{base}/rest/servicedeskapi/request"
        r = s.get(url, params={"start": start, "limit": limit}, timeout=30)
        if r.status_code == 401:
            raise RuntimeError("jira_auth_401")
        if r.status_code == 403:
            # no permission for JSM API with this account
            return []
        if r.status_code != 200:
            raise RuntimeError(f"jsm_request_list_fail_{r.status_code}")
        data = r.json()
        vals = data.get("values") or []
        if not isinstance(vals, list) or not vals:
            break
        for it in vals:
            if isinstance(it, dict):
                out.append(it)
        # paging
        if len(vals) < limit:
            break
        start += limit
    return out

def fetch_jql_issues(cfg: dict) -> List[Dict[str, Any]]:
    # Jira platform search (agent-wide if permissions allow)
    jql = (cfg.get("jql") or "").strip()
    if not jql:
        return []
    s = make_session(cfg)
    base = cfg["base"]
    out: List[Dict[str, Any]] = []
    start_at = 0
    max_results = 50
    for _ in range(50):
        url = f"{base}/rest/api/3/search"
        params = {"jql": jql, "startAt": start_at, "maxResults": max_results}
        r = s.get(url, params=params, timeout=30)
        if r.status_code == 401:
            raise RuntimeError("jira_auth_401")
        if r.status_code == 403:
            return []
        if r.status_code != 200:
            raise RuntimeError(f"jira_search_fail_{r.status_code}")
        data = r.json()
        issues = data.get("issues") or []
        if not isinstance(issues, list) or not issues:
            break
        for it in issues:
            if isinstance(it, dict):
                out.append(it)
        if len(issues) < max_results:
            break
        start_at += max_results
    return out

def normalize_from_jsm(item: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    # JSM request has issueId and issueKey sometimes
    jira_id = safe_get(item, ["issueId"], "")
    jira_key = safe_get(item, ["issueKey"], "")
    summary = safe_get(item, ["requestFieldValues", "summary"], "")  # often not present
    if not summary:
        summary = safe_get(item, ["summary"], "")
    st = safe_get(item, ["currentStatus", "status"], "")
    st_cat = safe_get(item, ["currentStatus", "statusCategory"], "")
    upd = safe_get(item, ["createdDate", "iso8601"], "")  # may not be updated
    return jira_id or jira_key, jira_key, summary, st, st_cat, upd

def normalize_from_jira(issue: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    jira_id = safe_get(issue, ["id"], "")
    jira_key = safe_get(issue, ["key"], "")
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    summary = str(fields.get("summary") or "")
    status = safe_get(fields, ["status", "name"], "")
    status_category = safe_get(fields, ["status", "statusCategory", "name"], "")
    updated_at = str(fields.get("updated") or "")
    return jira_id, jira_key, summary, status, status_category, updated_at

def main() -> int:
    cfg = load_cfg()
    if not has_creds(cfg):
        print("JIRA_SYNC_SKIPPED missing_creds=1")
        return 0

    conn = get_conn()
    try:
        init_tables(conn)

        synced_at = now_utc_iso()
        upserts = 0

        # Prefer JSM request list (good for service desk)
        items = fetch_jsm_requests(cfg)
        mode = "jsm_request"
        if not items:
            # Optional JQL fallback (agent-wide)
            jql_items = fetch_jql_issues(cfg)
            items = jql_items
            mode = "jql_search" if jql_items else "none"

        if mode == "none":
            print("JIRA_SYNC_OK mode=none upserts=0 note=no_data_or_no_permission")
            return 0

        for it in items:
            if mode == "jsm_request":
                rid, key, summary, st, st_cat, upd = normalize_from_jsm(it)
                jira_id = rid
            else:
                jira_id, key, summary, st, st_cat, upd = normalize_from_jira(it)

            if not jira_id:
                continue

            raw = json.dumps(it, ensure_ascii=True, sort_keys=True)
            upsert_issue(conn, str(jira_id), str(key), summary[:300], st[:120], st_cat[:120], upd[:64], raw, synced_at)
            upserts += 1

        conn.commit()
        print(f"JIRA_SYNC_OK mode={mode} upserts={upserts}")
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
