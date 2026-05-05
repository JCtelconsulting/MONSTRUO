#!/usr/bin/env python3
from plataforma.core import db

def main() -> int:
    conn = db.get_conn()
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bridge_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id TEXT DEFAULT 'jarvis',
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            kind TEXT NOT NULL, -- status|result|request|proposal
            title TEXT DEFAULT '',
            body TEXT DEFAULT '',
            payload_json TEXT DEFAULT '{}',
            requires_approval INTEGER DEFAULT 0, -- boolean 0/1
            approval_status TEXT DEFAULT 'na', -- pending|approved|rejected|na
            created_at TEXT DEFAULT '',
            decided_at TEXT DEFAULT '',
            decided_by TEXT DEFAULT ''
        );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bridge_to ON bridge_messages(to_agent);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bridge_approval ON bridge_messages(approval_status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bridge_thread ON bridge_messages(thread_id);")

        conn.commit()
        print("BRIDGE_INIT_OK")
        return 0
    finally:
        conn.close()

if __name__ == "__main__":
    raise SystemExit(main())
