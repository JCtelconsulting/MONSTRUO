import requests
import time
import os
import sys

# Configuration
API_URL = "http://localhost:9001/api"
COOKIES = {}
USERNAME = "juan.lopez@telconsulting.cl"
PASSWORD = "Monstruo2024!"

def login():
    global COOKIES
    print("[1] Logging in...")
    resp = requests.post(f"{API_URL}/auth/login", json={"email": USERNAME, "password": PASSWORD})
    if resp.status_code != 200:
        print(f"FAILED LOGIN: {resp.text}")
        sys.exit(1)
    # The API sets cookies. We need to capture them.
    # Actually, the response returns {access_token: ...} but requests Session can also handle cookies.
    # Let's use a Session object generally.
    return resp.json()

session = requests.Session()

def run_test():
    # 1. Login
    login_resp = login()
    token = login_resp["token"]
    # Manually set cookie if not automatically handled, though Session should. 
    # But API expects cookie 'access_token' mainly.
    session.cookies.set("access_token", token)
    print(f"[OK] Logged in as {login_resp['name']}")

    # 2. Create Ticket
    print("\n[2] Creating Ticket...")
    ticket_data = {
        "titulo": "E2E Test Attachments & Dedupe",
        "descripcion": "Probando flujo completo con adjuntos y deduplicación.",
        "tipo": "incidencia",
        "severidad": "media",
        "origen_email": "cliente.e2e@example.com",
        "cliente_nombre": "Cliente E2E"
    }
    resp = session.post(f"{API_URL}/tks/tickets", json=ticket_data)
    if resp.status_code != 200:
        print(f"FAILED CREATE TICKET: {resp.text}")
        sys.exit(1)
    
    ticket = resp.json()
    ticket_id = ticket["id"]
    print(f"[OK] Ticket Created: #{ticket_id} {ticket['codigo']}")

    # 3. Reply with Attachment
    print("\n[3] Replying with Attachment...")
    # Create dummy file
    with open("test_attachment.txt", "w") as f:
        f.write("Este es un archivo de prueba para el E2E.")
    
    with open("test_attachment.txt", "rb") as f:
        files = {'files': ('test_attachment.txt', f, 'text/plain')}
        data = {'mensaje': 'Hola, adjunto archivo de prueba.', 'asunto': 'Re: Prueba E2E'}
        resp = session.post(f"{API_URL}/tks/tickets/{ticket_id}/reply-email", files=files, data=data)
    
    if resp.status_code != 200:
        print(f"FAILED REPLY TICKET: {resp.text}")
        sys.exit(1)
    
    print(f"[OK] Reply Sent: {resp.json()}")

    # 4. Test Dedupe (Resend same request)
    print("\n[4] Testing Dedupe (Resending same reply)...")
    time.sleep(1) # Ensure we are within the dedupe window (3 mins)
    with open("test_attachment.txt", "rb") as f:
        files = {'files': ('test_attachment.txt', f, 'text/plain')}
        data = {'mensaje': 'Hola, adjunto archivo de prueba.', 'asunto': 'Re: Prueba E2E'}
        resp = session.post(f"{API_URL}/tks/tickets/{ticket_id}/reply-email", files=files, data=data)
    
    if resp.status_code != 200:
        print(f"FAILED DEDUPE REQUEST: {resp.text}")
        sys.exit(1)
    
    result = resp.json()
    if result.get("duplicate_skipped") is True:
        print(f"[OK] Dedupe worked: {result['message']}")
    else:
        print(f"[FAIL] Dedupe NOT triggered: {result}")
        sys.exit(1)

    # 5. Verify Email History & Attachments
    print("\n[5] Verifying Email History...")
    resp = session.get(f"{API_URL}/tks/tickets/{ticket_id}/emails")
    if resp.status_code != 200:
        print(f"FAILED GET EMAILS: {resp.text}")
        sys.exit(1)
    
    emails = resp.json()["items"]
    # We expect at least:
    # 1. Incoming (if auto-created? No, we created via API manual)
    # Wait, we created via API, so no initial email log unless generic.
    # We sent 1 reply. So at least 1 outgoing.
    
    found_outgoing = False
    for email in emails:
        if email["direction"] == "outgoing" and "test_attachment.txt" in email["attachments_json"]:
            print(f"[OK] Found outgoing email with attachment: {email['attachments_json']}")
            found_outgoing = True
            break
    
    if not found_outgoing:
        print(f"[FAIL] Outgoing email with attachment NOT found in history. History: {emails}")
        sys.exit(1)

    # 6. Verify File on Disk (Remote check via docker exec usually, but here we can check if running locally or trust API)
    # Since we are running outside container but mounting /srv/monstruo/data, let's check config path.
    # We set TICKET_ATTACHMENTS_DIR = "/srv/monstruo/data/tickets" in config.py
    # If we are running this script from the host, and the app is in docker mounting /srv/monstruo, it should be visible.
    
    print("\n[6] Cleanup...")
    if os.path.exists("test_attachment.txt"):
        os.remove("test_attachment.txt")
    
    print("\n=== E2E SUCCESS ===")

if __name__ == "__main__":
    run_test()
