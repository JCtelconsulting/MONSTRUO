import os
import requests
from typing import Dict, Any, Optional
import json


class LaudusClient:
    def __init__(self):
        self.base_url = os.getenv("LAUDUS_BASE_URL", "https://api.laudus.cl").rstrip(
            "/"
        )
        self.username = os.getenv("LAUDUS_USERNAME", "")
        self.password = os.getenv("LAUDUS_PASSWORD", "")
        self.vat_id = os.getenv("LAUDUS_COMPANY_VAT_ID", "")
        self.token = None

    def login(self) -> bool:
        """
        Realiza login en /security/login y guarda el token.
        Retorna True si éxito.
        """
        if not (self.username and self.password and self.vat_id):
            print("WARN: Faltan credenciales LAUDUS_*")
            return False

        url = f"{self.base_url}/security/login"
        payload = {
            "userName": self.username,
            "password": self.password,
            "companyVATId": self.vat_id,
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("token")
                return True
            else:
                print(f"Laudus Login Failed: {resp.status_code} {resp.text[:100]}")
                return False
        except Exception as e:
            print(f"Laudus Login Error: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        if not self.token:
            # Intentar autologin si no hay token
            if not self.login():
                raise ValueError("No autenticado en Laudus")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Connection": "close",
        }

    def get_health(self) -> Dict[str, Any]:
        """
        Verifica conectividad intentando login o una llamada ligera.
        """
        if self.login():
            return {"status": "ok", "msg": "Login exitoso", "base_url": self.base_url}
        return {"status": "error", "msg": "Fallo autenticacion"}

    def get_stock(self) -> Dict[str, Any]:
        """
        Obtiene stock actual usando endpoint descubierto /production/products/stock
        Retorna: {products: [...]}
        """
        endpoint = "/production/products/stock"
        url = f"{self.base_url}{endpoint}"

        try:
            # Nota: Usamos GET segun investigacion
            resp = requests.get(url, headers=self._get_headers(), timeout=45)
            if resp.status_code == 200:
                return resp.json()  # Retorna dict con key 'products'

            return {
                "error": True,
                "status": resp.status_code,
                "detail": resp.text[:200],
            }
        except Exception as e:
            return {"error": True, "detail": str(e)}

    def get_invoice_pdf(self, invoice_id: str) -> Optional[bytes]:
        """
        Obtiene el PDF de una factura por ID remoto.
        Retorna bytes del PDF o None si falla.
        """
        # Endpoint hipotético: /sales/invoices/{id}/pdf
        endpoint = f"/sales/invoices/{invoice_id}/pdf"
        url = f"{self.base_url}{endpoint}"
        try:
            headers = self._get_headers()
            headers["Accept"] = "application/pdf"
            # Algunos ERPs piden Content-Type application/json aunque sea GET
            del headers["Content-Type"]

            resp = requests.get(url, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.content
            print(f"Laudus PDF Error {invoice_id}: {resp.status_code}")
            return None
        except Exception as e:
            print(f"Laudus PDF Exception {invoice_id}: {e}")
            return None

    def get_invoice_details(self, invoice_id: str) -> Dict[str, Any]:
        """
        Obtiene detalles de una factura (items, condiciones) por ID remoto.
        """
        endpoint = f"/sales/invoices/{invoice_id}"
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=(5, 30))
            if resp.status_code == 200:
                return resp.json()
            print(f"Laudus Details Error {invoice_id}: {resp.status_code}")
            return {}
        except Exception as e:
            print(f"Laudus Details Exception {invoice_id}: {e}")
            return {}

    def list_doc_types(self) -> list:
        """
        Lista tipos de documento (docTypeId) disponibles.
        Endpoint: /system/docTypes/list
        """
        endpoint = "/system/docTypes/list"
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                    return data["data"]
                return data if isinstance(data, list) else []
            print(f"Laudus DocTypes Error: {resp.status_code} {resp.text[:200]}")
            return []
        except Exception as e:
            print(f"Laudus DocTypes Exception: {e}")
            return []

    def list_customer_contacts(self, customer_id: str) -> list:
        """
        Lista contactos de un cliente.
        Endpoint: /sales/customers/{customerId}/contacts
        """
        endpoint = f"/sales/customers/{customer_id}/contacts"
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                    return data["data"]
                return data if isinstance(data, list) else []
            print(f"Laudus Contacts Error: {resp.status_code} {resp.text[:200]}")
            return []
        except Exception as e:
            print(f"Laudus Contacts Exception: {e}")
            return []

    def create_sales_invoice(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crea una factura en Laudus (DTE/SII se gestiona en Laudus según configuración).
        Endpoint: POST /sales/invoices
        Retorna dict de respuesta o {error: True, ...}
        """
        endpoint = "/sales/invoices"
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.post(url, json=payload, headers=self._get_headers(), timeout=60)
            if resp.status_code in (200, 201):
                return resp.json() if resp.text else {"ok": True}
            return {
                "error": True,
                "status": resp.status_code,
                "detail": resp.text[:800],
                "payload": json.dumps(payload)[:1500],
            }
        except Exception as e:
            return {"error": True, "detail": str(e)}

    def get_invoice_payments(self, invoice_id: str) -> list:
        """
        Obtiene lista de pagos de una factura.
        """
        endpoint = f"/sales/invoices/{invoice_id}/payments"
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else []
            return []
        except Exception as e:
            print(f"Laudus Payments Error: {e}")
            return []

    def get_invoice_receipts(self, invoice_id: str) -> list:
        """
        Obtiene lista de cobros aplicados a una factura.
        Endpoint: /sales/invoices/{id}/receipts
        """
        endpoint = f"/sales/invoices/{invoice_id}/receipts"
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                    return data["data"]
                return data if isinstance(data, list) else []
            return []
        except Exception as e:
            print(f"Laudus Receipts Error: {e}")
            return []

    def get_all_customers(self) -> list:
        """
        Obtiene todos los clientes desde Laudus.
        Endpoint: /sales/customers/list (hipotético, ajustar según API real)
        """
        endpoint = "/sales/customers/list"
        url = f"{self.base_url}{endpoint}"
        payload = {
            "skip": 0,
            "take": 1000,
            "fields": ["customerId", "legalName", "name", "VATId"],
        }

        try:
            # POST vs GET depende de API Laudus. Muchos endpoints de lista son POST para filtros.
            resp = requests.post(
                url, json=payload, headers=self._get_headers(), timeout=60
            )
            if resp.status_code == 200:
                data = resp.json()
                # Laudus suele devolver {total: N, data: [...]} o directo lista
                if isinstance(data, dict) and "data" in data:
                    return data["data"]
                if isinstance(data, list):
                    return data

            print(f"Laudus Customers Error: {resp.status_code}")
            return []
        except Exception as e:
            print(f"Laudus Customers Exception: {e}")
            return []

    def list_products(
        self,
        skip: int = 0,
        take: int = 1000,
        q: str = "",
        fields: Optional[list] = None,
    ) -> list:
        """
        Lista productos desde Laudus.
        Endpoint: /production/products/list
        Nota: El OpenAPI de Laudus marca este endpoint como "string" (soporta CSV),
        pero en práctica suele aceptar JSON con paginación y devolver JSON.
        """
        endpoint = "/production/products/list"
        url = f"{self.base_url}{endpoint}"
        # Laudus suele exigir "fields" (lista de campos) en endpoints /list
        payload: Dict[str, Any] = {
            "skip": int(skip),
            "take": int(take),
            "fields": fields
            or ["productId", "sku", "description", "stockable", "unitPrice", "unitPriceWithTaxes"],
        }
        if q and str(q).strip():
            payload["q"] = str(q).strip()

        try:
            resp = requests.post(url, json=payload, headers=self._get_headers(), timeout=90)
            if resp.status_code != 200:
                print(f"Laudus Products Error: {resp.status_code} {resp.text[:200]}")
                return []

            data = resp.json()
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                return data["data"]
            if isinstance(data, dict) and "products" in data and isinstance(data["products"], list):
                return data["products"]
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            print(f"Laudus Products Exception: {e}")
            return []

    def get_product(self, product_id: str) -> Dict[str, Any]:
        """
        Obtiene detalle de un producto.
        Endpoint: /production/products/{productId}
        """
        endpoint = f"/production/products/{product_id}"
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=30)
            if resp.status_code == 200:
                return resp.json()
            return {}
        except Exception as e:
            print(f"Laudus GetProduct Error: {e}")
            return {}

    def get_product_sales_price(
        self,
        product_id: int,
        quantity: float = 1.0,
        customer_id: Optional[int] = None,
        price_list_id: Optional[int] = None,
        vat_rate: Optional[float] = None,
        date_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Obtiene el precio de venta calculado por Laudus.
        Endpoint: /production/products/{productId}/salesPrice
        """
        endpoint = f"/production/products/{int(product_id)}/salesPrice"
        url = f"{self.base_url}{endpoint}"
        params: Dict[str, Any] = {"quantity": float(quantity or 1)}
        if customer_id is not None:
            params["customerId"] = int(customer_id)
        if price_list_id is not None:
            params["priceListId"] = int(price_list_id)
        if vat_rate is not None:
            params["VATRate"] = float(vat_rate)
        if date_iso:
            params["date"] = date_iso

        try:
            resp = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            return {"error": True, "status": resp.status_code, "detail": resp.text[:300]}
        except Exception as e:
            return {"error": True, "detail": str(e)}

    def list_sales_invoices(
        self,
        *,
        skip: int = 0,
        take: int = 200,
        fields: Optional[list] = None,
    ) -> list:
        """
        Lista facturas de venta desde Laudus.
        Endpoint: POST /sales/invoices/list

        Nota: muchos endpoints /list exigen un array `fields` y devuelven una lista JSON.
        """
        endpoint = "/sales/invoices/list"
        url = f"{self.base_url}{endpoint}"
        payload: Dict[str, Any] = {
            "skip": int(skip),
            "take": int(take),
            "fields": fields
            or [
                "salesInvoiceId",
                "customerId",
                "docTypeId",
                "issuedDate",
                "docNumber",
            ],
        }

        try:
            resp = requests.post(url, json=payload, headers=self._get_headers(), timeout=90)
            if resp.status_code != 200:
                print(f"Laudus InvoicesList Error: {resp.status_code} {resp.text[:200]}")
                return []

            # Normalmente retorna lista JSON (no wrapper)
            data = resp.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                return data["data"]
            return []
        except Exception as e:
            print(f"Laudus InvoicesList Exception: {e}")
            return []
