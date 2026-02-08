import sys
import os
import requests
import re
from pathlib import Path
from dotenv import load_dotenv

# Setup path and env
PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "code"))

from app.core.db import get_conn
from app.integraciones.laudus import LaudusClient

def normalize_name(name):
    return name.strip().lower()

def is_likely_bank(name):
    """
    Heuristica simple: si tiene 'Banco' en el nombre y NO es una cuenta genérica
    de 'Obligaciones'.
    """
    n = normalize_name(name)
    if "obligaciones" in n:
        return False
    if "banco" in n:
        return True
    return False

def sync_banks():
    print("=== Sincronizando Bancos desde Laudus ===")
    
    # 1. Conectar a Laudus
    client = LaudusClient()
    if not client.login():
        print("ERROR: No se pudo loguear en Laudus.")
        sys.exit(1)

    # 2. Obtener cuentas
    url = f"{client.base_url}/accounting/accounts/list"
    payload = {
        "skip": 0,
        "take": 1000, 
        "fields": ["accountId", "name"]
    }
    
    try:
        resp = requests.post(url, json=payload, headers=client._get_headers(), timeout=30)
        if resp.status_code != 200:
            print(f"ERROR: API Laudus respondió {resp.status_code}")
            sys.exit(1)
            
        accounts = resp.json()
        print(f"Total cuentas recuperadas: {len(accounts)}")
        
        # 3. Filtrar Bancos
        bank_accounts = [a for a in accounts if is_likely_bank(a.get("name", ""))]
        print(f"Candidatos a Banco encontrados: {len(bank_accounts)}")
        
        if not bank_accounts:
            print("No se encontraron bancos. Revisa la heurística.")
            return

        # 4. Guardar en DB LOCAL
        conn = get_conn()
        try:
            for acc in bank_accounts:
                lid = acc["accountId"]
                name = acc["name"]
                
                print(f"Syncing: [{lid}] {name}")
                
                query = """
                INSERT INTO bank_accounts (name, laudus_account_id, bank_name, created_at)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(laudus_account_id) DO UPDATE SET
                    name = excluded.name;
                """
                # Adjust for PG vs SQLite syntax if needed (datetime vs current_timestamp)
                # But our db.py handles ? -> %s
                # For datetime('now'), it is SQLite specific. 
                # Better pass python datetime or use CURRENT_TIMESTAMP in SQL standar.
                
                query_std = """
                INSERT INTO bank_accounts (name, laudus_account_id, bank_name, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(laudus_account_id) DO UPDATE SET
                    name = excluded.name;
                """
                from datetime import datetime
                now_iso = datetime.now().isoformat()
                
                conn.execute(query_std, (name, lid, name, now_iso))
            
            conn.commit()
            print("=== Sincronización Exitosa ===")
            
        finally:
            conn.close()
            
    except Exception as e:
        print(f"EXCEPCION: {e}")
        sys.exit(1)

if __name__ == "__main__":
    sync_banks()
