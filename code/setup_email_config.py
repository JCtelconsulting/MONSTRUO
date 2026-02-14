import sys
import getpass
from app.core import db

def setup_email():
    print("Configuración de Email (IMAP/SMTP)")
    print("This will store credentials in the 'system_settings' table.")
    
    config = {}
    config['smtp_host'] = input("SMTP Host (ej. smtp.gmail.com): ").strip()
    config['smtp_port'] = input("SMTP Port (ej. 587): ").strip()
    config['smtp_user'] = input("SMTP User (email): ").strip()
    config['smtp_password'] = getpass.getpass("SMTP Password: ").strip()
    config['smtp_from_name'] = input("From Name (ej. Soporte Monstruo): ").strip()
    
    config['imap_host'] = input("IMAP Host (ej. imap.gmail.com): ").strip()
    config['imap_port'] = input("IMAP Port (ej. 993): ").strip()
    config['imap_user'] = input("IMAP User (email): ").strip() or config['smtp_user']
    config['imap_password'] = getpass.getpass("IMAP Password (leave empty to use SMTP pass): ").strip() or config['smtp_password']
    
    config['email_polling_interval'] = input("Polling Interval (seconds, default 60): ").strip() or "60"

    conn = db.get_conn()
    try:
        for k, v in config.items():
            # Upsert
            conn.execute("""
                INSERT INTO system_settings (key, value) VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """, (k, v))
        conn.commit()
        print("\nConfiguración guardada exitosamente.")
    except Exception as e:
        print(f"\nError guardando configuración: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    setup_email()
