import csv
import hashlib
import io
from typing import List, Dict, Any, Optional
from datetime import datetime

class BankParser:
    """
    Servicio para parsear cartolas bancarias (Santander, Chile, Generico).
    Retorna una lista de dicts estandarizados:
    {
        "date": "YYYY-MM-DD",
        "description": str,
        "document_number": str,
        "amount": float, (Positivo=Abono, Negativo=Cargo)
        "balance": float (opcional)
        "hash": str (SHA256 unico)
    }
    """

    @staticmethod
    def compute_hash(date: str, amount: float, description: str, doc_num: str) -> str:
        """Genera hash único para evitar duplicados."""
        raw = f"{date}|{amount}|{description.strip()}|{doc_num.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def parse_generic_csv(content: str, delimiter: str = ";") -> List[Dict[str, Any]]:
        """
        Espera columnas: FECHA, DESCRIPCION, DOCUMENTO, CARGO, ABONO, SALDO (Opcional)
        """
        lines = content.splitlines()
        reader = csv.reader(lines, delimiter=delimiter)
        parsed_lines = []
        
        # Saltamos headers básicos si existen
        # En una imp. real, detectariamos headers. Asumiremos que la fila 1 es header si falla fecha.
        
        for row in reader:
            if not row or len(row) < 4:
                continue
            
            # Intentar parsear fecha para ver si es header
            try:
                # Asumimos formato DD/MM/YYYY o YYYY-MM-DD
                date_str = row[0].strip()
                dt = BankParser._parse_date(date_str)
            except ValueError:
                # Posible header
                continue

            desc = row[1].strip()
            doc_num = row[2].strip()
            
            # Montos
            cargo = BankParser._parse_amount(row[3])
            abono = BankParser._parse_amount(row[4]) if len(row) > 4 else 0.0
            
            amount = abono - cargo # Net amount
            
            line_hash = BankParser.compute_hash(dt, amount, desc, doc_num)
            
            parsed_lines.append({
                "date": dt,
                "description": desc,
                "document_number": doc_num,
                "amount": amount,
                "balance": 0.0, # TODO: parsear si existe
                "hash": line_hash
            })
            
        return parsed_lines

    @staticmethod
    def parse_santander_csv(content: str) -> List[Dict[str, Any]]:
        """
        Formato típico Santander Empresas (CSV):
        Fecha;Sucursal;Descripción;N° Documento;Cargos;Abonos;Saldo
        Indices:
        0: Fecha
        1: Sucursal
        2: Descripcion
        3: N Doc
        4: Cargo
        5: Abono
        """
        lines = content.splitlines()
        reader = csv.reader(lines, delimiter=";")
        parsed_lines = []
        
        for row in reader:
            if not row or len(row) < 5:
                continue
            
            # Intentar parsear fecha
            try:
                date_str = row[0].strip()
                dt = BankParser._parse_date(date_str)
            except ValueError:
                continue # Header or footer

            desc = row[2].strip()
            doc_num = row[3].strip()
            
            # Montos
            cargo = BankParser._parse_amount(row[4])
            abono = BankParser._parse_amount(row[5]) if len(row) > 5 else 0.0
            
            amount = abono - cargo # Net amount
            
            # Balance (Col 6)
            balance = BankParser._parse_amount(row[6]) if len(row) > 6 else 0.0

            line_hash = BankParser.compute_hash(dt, amount, desc, doc_num)
            
            parsed_lines.append({
                "date": dt,
                "description": desc,
                "document_number": doc_num,
                "amount": amount,
                "balance": balance,
                "hash": line_hash
            })
            
        return parsed_lines

    @staticmethod
    def _parse_date(date_str: str) -> str:
        # Intentar formatos comunes Chile
        formats = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date().isoformat()
            except ValueError:
                continue
        raise ValueError(f"Fecha invalida: {date_str}")

    @staticmethod
    def _parse_amount(amount_str: str) -> float:
        if not amount_str:
            return 0.0
        # Limpiar $ y puntos miles, cambiar coma decimal por punto
        clean = amount_str.replace("$", "").replace(".", "").replace(",", ".")
        try:
            return float(clean)
        except ValueError:
            return 0.0
