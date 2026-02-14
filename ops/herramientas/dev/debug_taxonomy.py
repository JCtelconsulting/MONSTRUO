#!/usr/bin/env python3
import sys
import os
import json
import logging

# Add code dir to path
sys.path.append("/srv/monstruo_dev/code")
sys.path.append("/srv/monstruo_dev/code/sistema_gestion")

from sistema_gestion import catalogo_seed_ai
from sistema_gestion import ai_local_openai_compat, nucleo

# Setup logging
logging.basicConfig(level=logging.INFO)

def test_classify():
    print("--- DEBUG TAXONOMY ---")
    
    # 1. Check Status
    status = ai_local_openai_compat.check_status()
    print(f"Ai Status: {status}")
    
    if not status.get("ok"):
        print("ERROR: AI Module not OK")
        return

    # 2. Test Items
    items = [
        {"raw_nombre": "Switch Mikrotik 24p", "raw_marca": "Mikrotik", "raw_sku": "RB1100AHx4"},
        {"raw_nombre": "Router Cisco 48 Puertos", "raw_marca": "Cisco", "raw_sku": "ISR4331"},
        {"raw_nombre": "Cable UTP Cat6 Exterior", "raw_marca": "", "raw_sku": ""},
        {"raw_nombre": "Caja Tornillos 1 pulgada", "raw_marca": "", "raw_sku": ""}
    ]
    
    print(f"\nSending {len(items)} items to AI...")
    
    # 3. Call Classify
    # Mock connection not needed for basic test unless few-shot fails
    # But let's pass None for conn to skip few-shot for now to isolate prompt
    results = catalogo_seed_ai.ai_classify_batch(items, ai_local_openai_compat, conn=None)
    
    print("\n--- RESULTS ---")
    print(json.dumps(results, indent=2))
    
    # 4. Verify against Expected
    print("\n--- VERIFICATION ---")
    for i, res in enumerate(results):
        ruta = res.get("ruta", [])
        print(f"Item: {items[i]['raw_nombre']}")
        print(f"  -> Path: {ruta}")
        
        if "Switch" in items[i]["raw_nombre"]:
            if "24 Puertos" in ruta:
                print("  [OK] Detected 24 Ports")
            else:
                print("  [FAIL] Did NOT detect 24 Ports")

if __name__ == "__main__":
    test_classify()
