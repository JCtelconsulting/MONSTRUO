import sys
import json
import requests
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(PROJECT_ROOT / ".env")
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "plataforma" / "legacy" / "code"))

from app.integraciones.laudus import LaudusClient

def probe_ledger_endpoints():
    client = LaudusClient()
    if not client.login():
        print("Login failed")
        return

    print("--- Probing Laudus ACCOUNTING Endpoints ---")
    
    # Lista de endpoints probables para obtener "La Cartola" (Movimientos)
    # Basado en estructura REST habitual de Laudus (que usa POST con search params)
    
    candidates = [
        # 1. Movimientos Contables: Test GET /accounting/ledger variants with CORRECT Codes
        # Santander Code: 1101201
        
        # Case A: Standard 'from'/'to'
        {"url": "/accounting/ledger", "method": "GET", "payload": None, 
         "params": {"accountNumberFrom": "1101201", "accountNumberTo": "1101201", "from": "2024-01-01", "to": "2026-12-31"}}, 
        
        # Case B: 'startDate'/'endDate'
        {"url": "/accounting/ledger", "method": "GET", "payload": None, 
         "params": {"accountNumberFrom": "1101201", "accountNumberTo": "1101201", "startDate": "2024-01-01", "endDate": "2026-12-31"}},
         
        # Case C: dateFrom / dateTo (common in some Systems)
        {"url": "/accounting/ledger", "method": "GET", "payload": None, 
         "params": {"accountNumberFrom": "1101201", "accountNumberTo": "1101201", "dateFrom": "2024-01-01", "dateTo": "2026-12-31"}},
        {"url": "/treasury/movements/list", "method": "POST", "payload": {"skip":0, "take":1}},
        
        # 3. Reports (a veces los datos estan en reportes)
        {"url": "/reports/accounting/ledger", "method": "POST", "payload": {"accountId": 8, "from": "2026-01-01", "to": "2026-02-01"}},
    ]
    
    for c in candidates:
        full_url = f"{client.base_url}{c['url']}"
        print(f"Testing {c['method']} {c['url']} ...", end=" ")
        try:
            if c['method'] == "POST":
                resp = requests.post(full_url, json=c['payload'], headers=client._get_headers(), timeout=5)
            else:
                resp = requests.get(full_url, params=c.get('params'), headers=client._get_headers(), timeout=5)
            
            print(f"Status: {resp.status_code}")
            if resp.status_code == 200:
                print(">>> SUCCESS! Response snippet:", resp.text[:200])
            else:
                # Always print body for errors to see validation messages
                print(f"Status: {resp.status_code} | Body: {resp.text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    probe_ledger_endpoints()
