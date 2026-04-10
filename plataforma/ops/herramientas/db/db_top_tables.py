import sqlite3
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DB_PATH = os.getenv("DB_TOP_TABLES_PATH", str(PROJECT_ROOT / "data/db/monstruo.db"))

def main():
    if not os.path.exists(DB_PATH):
        print("DB not found")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print(f"Total tables: {len(tables)}")
        
        results = []
        for t in tables:
            name = t[0]
            try:
                c = conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                results.append((name, c))
            except:
                pass
                
        results.sort(key=lambda x: x[1], reverse=True)
        
        print("\nTOP 20 TABLES BY ROW COUNT:")
        for name, count in results[:20]:
            print(f"- {name}: {count}")
            
    finally:
        conn.close()

if __name__ == "__main__":
    main()
