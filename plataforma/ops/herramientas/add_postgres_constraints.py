#!/usr/bin/env python3
import os
import sys
from typing import List, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CODE_ROOT = os.path.join(PROJECT_ROOT, "code")
if CODE_ROOT not in sys.path:
    sys.path.insert(0, CODE_ROOT)

from app.core import db

Constraint = Tuple[str, str, str]

CONSTRAINTS: List[Constraint] = [
    ("actions", "fk_actions_event", "FOREIGN KEY (event_id) REFERENCES events(id)"),
    ("cat_items", "fk_cat_items_categoria", "FOREIGN KEY (categoria_id) REFERENCES cat_categorias(id) ON DELETE SET NULL"),
    ("cat_fuente_map", "fk_cat_fuente_item", "FOREIGN KEY (item_id) REFERENCES cat_items(id) ON DELETE CASCADE"),
    ("crm_contacts", "fk_crm_contacts_company", "FOREIGN KEY (company_id) REFERENCES crm_companies(id)"),
    ("crm_consents", "fk_crm_consents_contact", "FOREIGN KEY (contact_id) REFERENCES crm_contacts(id)"),
    ("crm_opportunities", "fk_crm_opps_company", "FOREIGN KEY (company_id) REFERENCES crm_companies(id)"),
    ("tasks", "fk_tasks_case", "FOREIGN KEY (case_id) REFERENCES cases(id)"),
    ("task_comments", "fk_task_comments_task", "FOREIGN KEY (task_id) REFERENCES tasks(id)"),
    ("task_links", "fk_task_links_case", "FOREIGN KEY (case_id) REFERENCES cases(id)"),
    ("tks_eventos", "fk_tks_eventos_ticket", "FOREIGN KEY (ticket_id) REFERENCES tks_tickets(id) ON DELETE CASCADE"),
    ("workflow_dedup", "fk_workflow_dedup_task", "FOREIGN KEY (task_id) REFERENCES tasks(id)"),
    ("workflow_dedup", "fk_workflow_dedup_case", "FOREIGN KEY (case_id) REFERENCES cases(id)"),
]

def _constraint_exists(conn, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM pg_constraint WHERE conname = %s", (name,)).fetchone()
    return bool(row)

def main() -> int:
    if not db.is_postgres():
        print("ERROR: DB_URL debe apuntar a PostgreSQL.")
        return 1

    conn = db.get_conn()
    try:
        added = 0
        validated = 0
        created: List[Tuple[str, str]] = []
        for table, name, definition in CONSTRAINTS:
            if _constraint_exists(conn, name):
                continue
            sql = f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" {definition} NOT VALID'
            conn.execute(sql)
            added += 1
            created.append((table, name))

        conn.commit()

        for table, name in created:
            try:
                conn.execute(f'ALTER TABLE "{table}" VALIDATE CONSTRAINT "{name}"')
                validated += 1
            except Exception:
                conn.rollback()
                # Leave as NOT VALID if existing data conflicts
                continue

        conn.commit()
        print(f"CONSTRAINTS_ADDED={added} VALIDATED={validated}")
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
