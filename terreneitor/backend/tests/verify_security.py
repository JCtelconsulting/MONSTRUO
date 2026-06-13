import os
import sys

from fastapi.testclient import TestClient

os.environ["TERRENEITOR_SECRET_KEY"] = "test_key_verification_123"

from terreneitor.backend.main import app

client = TestClient(app)

print("🧪 Verificando Headers de Seguridad...")
response = client.get("/api/auth/whoami")  # Endpoint ligero
headers = response.headers

expected = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}

missing = []
for key, val in expected.items():
    if headers.get(key) != val:
        print(f"❌ Falla: Expected {key}={val}, got {headers.get(key)}")
        missing.append(key)
    else:
        print(f"✅ {key}: OK")

if not missing:
    print("\n✨ Todos los headers de seguridad estan presentes.")
else:
    print("\n⚠️ Faltan headers de seguridad.")
    sys.exit(1)
