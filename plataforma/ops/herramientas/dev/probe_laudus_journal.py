#!/usr/bin/env python3
"""
Probe Laudus API para encontrar asientos contables manuales vs extractos bancarios.
"""
import sys
from pathlib import Path
from dotenv import load_dotenv
import requests
from datetime import datetime, timedelta
import os

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(ENV_PATH)

# Debug
print(f"Loading .env from: {ENV_PATH}")
print(f"LAUDUS_USERNAME: {os.getenv('LAUDUS_USERNAME', 'NOT SET')}")

sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "plataforma" / "legacy" / "code"))

from app.integraciones.laudus import LaudusClient

def explore_laudus_endpoints():
    client = LaudusClient()
    
    if not client.login():
        print("❌ Error al autenticar con Laudus")
        return
    
    print("=" * 70)
    print("EXPLORANDO API DE LAUDUS - ASIENTOS CONTABLES")
    print("=" * 70)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    date_from = start_date.strftime("%Y-%m-%d")
    date_to = end_date.strftime("%Y-%m-%d")
    
    bank_account_code = "11020103"  # Santander
    
    print(f"\nRango: {date_from} a {date_to}")
    print(f"Cuenta: {bank_account_code}")
    
    # TEST 1: Ledger
    print("\n" + "=" * 70)
    print("TEST 1: GET /accounting/ledger")
    print("=" * 70)
    
    try:
        resp = requests.get(
            f"{client.base_url}/accounting/ledger",
            headers=client._get_headers(),
            params={
                "accountNumberFrom": bank_account_code,
                "accountNumberTo": bank_account_code,
                "dateFrom": date_from,
                "dateTo": date_to
            }
        )
        
        if resp.status_code == 200:
            data = resp.json()
            entries = data.get('data', [])
            print(f"✅ {len(entries)} entradas")
            
            if entries:
                print("\n📄 Primera entrada:")
                first = entries[0]
                for key in ['date', 'description', 'debit', 'credit', 'documentNumber', 'documentType']:
                    print(f"  {key}: {first.get(key, 'N/A')}")
        else:
            print(f"❌ Error {resp.status_code}")
    except Exception as e:
        print(f"❌ {e}")
    
    # TEST 2: Journal Entries
    print("\n" + "=" * 70)
    print("TEST 2: GET /accounting/journal-entries")
    print("=" * 70)
    
    try:
        resp = requests.get(
            f"{client.base_url}/accounting/journal-entries",
            headers=client._get_headers(),
            params={"dateFrom": date_from, "dateTo": date_to}
        )
        
        if resp.status_code == 200:
            data = resp.json()
            entries = data.get('data', [])
            print(f"✅ {len(entries)} asientos")
            if entries:
                print(f"  Keys: {list(entries[0].keys())}")
        else:
            print(f"❌ Error {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"❌ {e}")
    
    # TEST 3: Análisis campos
    print("\n" + "=" * 70)
    print("TEST 3: Análisis de Campos Distinguidores")
    print("=" * 70)
    
    try:
        resp = requests.get(
            f"{client.base_url}/accounting/ledger",
            headers=client._get_headers(),
            params={
                "accountNumberFrom": bank_account_code,
                "accountNumberTo": bank_account_code,
                "dateFrom": date_from,
                "dateTo": date_to
            }
        )
        
        if resp.status_code == 200:
            data = resp.json()
            entries = data.get('data', [])
            
            if entries:
                all_keys = set()
                for e in entries[:10]:
                    all_keys.update(e.keys())
                
                print("\n🔍 Campos disponibles:")
                for key in sorted(all_keys):
                    print(f"  - {key}")
                
                print("\n📊 Muestra de 3 entradas:")
                for i, entry in enumerate(entries[:3], 1):
                    print(f"\n  #{i}:")
                    print(f"    Date: {entry.get('date')}")
                    print(f"    Desc: {entry.get('description', '')[:30]}")
                    print(f"    DocType: {entry.get('documentType')}")
                    print(f"    DocNum: {entry.get('documentNumber')}")
                    print(f"    Journal: {entry.get('journalNumber', 'N/A')}")
        else:
            print(f"❌ Error {resp.status_code}")
    except Exception as e:
        print(f"❌ {e}")

if __name__ == "__main__":
    explore_laudus_endpoints()
