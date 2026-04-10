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

def list_accounts():
    client = LaudusClient()
    if not client.login():
        print("Login failed")
        return

    print("--- Fetching Laudus Accounting Accounts ---")
    
    url = f"{client.base_url}/accounting/accounts/list"
    try:
        # Assuming list is POST with skip/take/fields
        payload = {
            "skip": 0, 
            "take": 1000,
            "fields": ["accountId", "name", "accountNumber"]
        }
        resp = requests.post(url, json=payload, headers=client._get_headers())
        if resp.status_code == 200:
            accounts = resp.json()
            print(f"Total Accounts: {len(accounts)}")
            
            # Find banks
            for acc in accounts:
                name = acc.get("name", "").lower()
            # Find banks and fintechs
            for acc in accounts:
                name = acc.get("name", "").lower()
                # Check for expanded keywords
                keywords = ["banco", "santander", "chile", "mercado", "pago", "tenpo", "tempo"]
                if any(k in name for k in keywords):
                    print(f"ID: {acc.get('accountId')} | Code: {acc.get('accountNumber')} | Name: {acc.get('name')}")
        else:
            print(f"Error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"Ex: {e}")

if __name__ == "__main__":
    list_accounts()
