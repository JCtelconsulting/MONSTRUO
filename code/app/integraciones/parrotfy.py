import os
import requests
from typing import Dict, Any, Optional

class ParrotfyClient:
    def __init__(self):
        self.base_url = "https://telconsulting.parrotfy.com"
        self.token = os.getenv("PARROTFY_TOKEN", "").strip()
        if not self.token:
            # No lanzamos error init para no romper boot si falta env,
            # pero fallará al llamar métodos.
            print("WARN: PARROTFY_TOKEN no definido en entorno.")
        
        # Corrección defensiva: Si el usuario puso "Bearer xyz" en .env, lo limpiamos
        if self.token.lower().startswith("bearer "):
            self.token = self.token[7:].strip()

    def _get_headers(self) -> Dict[str, str]:
        if not self.token:
            raise ValueError("Falta PARROTFY_TOKEN")
        return {
            "P-API-KEY": self.token,
            "Accept": "application/json"
        }

    def _handle_response(self, resp: requests.Response, context: str) -> Dict[str, Any]:
        try:
            if resp.status_code == 200:
                return resp.json()
            # Intento de parsear error
            err_body = resp.text[:300]
            # Si es 500, retornamos estructura de error controlado
            return {
                "error": True, 
                "status": resp.status_code, 
                "detail": f"{context} failed: {err_body}"
            }
        except Exception as e:
            return {"error": True, "status": resp.status_code, "detail": f"JSON decode error: {str(e)}"}

    def get_stock(self) -> Dict[str, Any]:
        """
        GET /api/v1/inventory_movements/stock
        Retorna el stock actual calculado por movimientos.
        """
        url = f"{self.base_url}/api/v1/inventory_movements/stock"
        try:
            # Aumentamos timeout a 60s porque el calculo de stock es pesado en servidor destino
            resp = requests.get(url, headers=self._get_headers(), timeout=60)
            # El endpoint suele devolver una lista directa o un wrapper. 
            # Segun spec es array en raiz o paginado. Asumimos standard handling.
            return self._handle_response(resp, "GetStock")
        except Exception as e:
            return {"error": True, "detail": str(e)}

    def get_products(self) -> Dict[str, Any]:
        """
        GET /api/v1/products
        """
        url = f"{self.base_url}/api/v1/products"
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            return self._handle_response(resp, "GetProducts")
        except Exception as e:
            return {"error": True, "detail": str(e)}
