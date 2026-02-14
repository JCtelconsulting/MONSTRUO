
import sys
import unittest
from unittest.mock import MagicMock
sys.path.append("/srv/monstruo_dev/code")

# Mock LaudusClient before importing sync logic
sys.modules["app.integraciones.laudus"] = MagicMock()
from app.integraciones.laudus import LaudusClient

# Import the code to test
from app.jobs.stock_sync import sync_stock
from app.core import tickets_service, db

class TestDiscrepancy(unittest.TestCase):
    def test_ticket_creation(self):
        # 1. Setup Mock
        mock_client = LaudusClient.return_value
        mock_client.login.return_value = True
        mock_client.get_stock.return_value = {
            "products": [
                {
                    "sku": "TEST-IPHONE",
                    "name": "iPhone 15 Mock",
                    "price": 1000,
                    "cost": 800,
                    "stock": 100  # Remote says 100
                }
            ]
        }
        
        # 2. Reset DB status for this SKU
        conn = db.get_conn()
        conn.execute("DELETE FROM products WHERE sku = 'TEST-IPHONE'")
        conn.execute("DELETE FROM tickets WHERE titulo LIKE '%TEST-IPHONE%'")
        # Insert local product with DIFFERENT stock
        conn.execute("""
            INSERT INTO products (sku, name, price, cost, stock_current, created_at, updated_at)
            VALUES ('TEST-IPHONE', 'iPhone 15 Mock', 1000, 800, 50, '2025-01-01', '2025-01-01')
        """) # Local says 50
        conn.commit()
        conn.close()
        
        # 3. Run Sync
        print("Running Sync...")
        sync_stock()
        
        # 4. Verify Ticket Created
        print("Verifying Ticket...")
        result = tickets_service.list_tickets(q="TEST-IPHONE")
        tickets = result.get("items", []) if isinstance(result, dict) else result
        self.assertTrue(len(tickets) > 0, "No se creó el ticket!")
        
        ticket = tickets[0]
        print(f"Ticket Created: {ticket['titulo']} | ID: {ticket['id']}")
        self.assertIn("Diferencia Stock SKU: TEST-IPHONE", ticket["titulo"])
        self.assertEqual(ticket["severidad"], "alta")
        self.assertEqual(ticket["estado"], "abierto")
        
        print("SUCCESS: Discrepancy detected and ticket created.")

if __name__ == "__main__":
    unittest.main()
