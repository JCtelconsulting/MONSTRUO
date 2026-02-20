
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from pathlib import Path

def check_db():
    load_dotenv(dotenv_path="/srv/monstruo_dev/.env.server.dev")
    db_url = os.getenv("DB_URL")
    print(f"Connecting to: {db_url}")
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        tables = ['invoices', 'laudus_invoices', 'laudus_payments', 'laudus_customers']
        for table in tables:
            cur.execute(f"SELECT count(*) FROM {table}")
            count = cur.fetchone()['count']
            print(f"Table {table}: {count} rows")
            
            if count > 0:
                cur.execute(f"SELECT * FROM {table} LIMIT 1")
                sample = cur.fetchone()
                print(f"Sample from {table}: {sample}")
        
        # Check sales.py KPI logic specifically
        from datetime import datetime, timedelta
        today = datetime.now()
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        print(f"Start date for KPIs: {start_date}")
        
        cur.execute("SELECT SUM(total_final) as total FROM invoices WHERE status IN ('ISSUED', 'PAID') AND issued_at >= %s", (start_date,))
        res = cur.fetchone()
        print(f"KPI Facturado (invoices): {res['total']}")
        
        cur.execute("SELECT SUM(total_amount) as total FROM laudus_invoices WHERE doc_date >= %s", (start_date,))
        res = cur.fetchone()
        print(f"KPI Facturado (laudus_invoices): {res['total']}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
