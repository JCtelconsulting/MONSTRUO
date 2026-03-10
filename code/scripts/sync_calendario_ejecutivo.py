import pandas as pd
import sys
import os
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from pathlib import Path

# Configuración de rutas y carga de entorno
BASE_DIR = Path("/srv/monstruo_dev")
load_dotenv(BASE_DIR / ".env.server.dev")

DB_URL = os.getenv("DB_URL", "postgresql://monstruo:monstruo@172.25.0.3:5432/monstruo")
EXCEL_PATH = BASE_DIR / "data/fundacion/planificaciones/Calendario 2026.xlsx"

def get_db_conn():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def get_event_meta(text):
    """
    Determina subcategoría y color basado en palabras clave.
    """
    import re
    # Normalizar texto: quitar acentos, pasar a minúsculas y limpiar espacios/saltos de línea
    text_clean = " ".join(text.split()).lower()
    text_lc = text_clean.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    
    # Feriados (con manejo de typos y efemérides chilenas)
    feriados_kw = [
        "feriado", "feriaado", "festivo", "irrenunciable", "semana santa", "navidad", "pascua", 
        "año nuevo", "glorias navales", "virgen", "santos", "independencia", "descubrimiento",
        "fiestas patrias", "ejercito", "dia del trabajador", "asuncion", "encuentro de dos mundos"
    ]
    if any(k in text_lc for k in feriados_kw):
        return "feriado", "#e74c3c" # Rojo
    
    # Cumpleaños
    if any(k in text_lc for k in ["cumpleaños", "cumple"]):
        return "cumpleaños", "#f1c40f" # Amarillo/Dorado
        
    # Diagnósticos / Evaluaciones / Encuestas (Prioridad Alta)
    eval_kw = ["diagnostico", "evaluacion", "prueba", "glifing", "test", "encuesta", "encuenta"]
    if any(k in text_lc for k in eval_kw):
        return "evaluacion", "#9b59b6" # Morado

    # Inicio
    if any(k in text_lc for k in ["inicio", "comienzo", "parte", "entrada"]):
        return "inicio", "#2ecc71" # Verde
        
    # Término (Uso de busqueda de palabra exacta para 'fin' para evitar 'glifing')
    termino_kw = ["termino", "finaliza", "concluye", "salida", "finalizado"]
    has_exact_fin = re.search(r'\bfin\b', text_lc)
    if any(k in text_lc for k in termino_kw) or has_exact_fin:
        return "termino", "#3498db" # Azul
        
    return "general", "#e67e22" # Naranja (default ejecutivo)

def parse_month_sheet(df, month_name, year=2026):
    """
    Parsea una hoja de Excel tipo calendario visual.
    Busca números (días) y el texto debajo o al lado como evento.
    """
    events = []
    
    meses_map = {
        "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
        "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12
    }
    
    month_num = meses_map.get(month_name.upper())
    if not month_num:
        return []

    for r in range(len(df)):
        for c in range(len(df.columns)):
            val = df.iloc[r, c]
            
            if isinstance(val, (int, float)) and not pd.isna(val) and 1 <= int(val) <= 31:
                day = int(val)
                
                event_text = ""
                for offset in range(1, 4):
                    if r + offset < len(df):
                        candidate = df.iloc[r + offset, c]
                        if isinstance(candidate, str) and not pd.isna(candidate) and not candidate.isdigit():
                            event_text = candidate.strip()
                            break
                
                if event_text:
                    try:
                        fecha = datetime(year, month_num, day)
                        subcat, color = get_event_meta(event_text)
                        events.append({
                            "titulo": event_text,
                            "fecha": fecha,
                            "categoria": "ejecutiva",
                            "subcategoria": subcat,
                            "color": color
                        })
                    except ValueError:
                        pass
    
    return events

def main():
    if not EXCEL_PATH.exists():
        print(f"Error: No se encuentra el archivo en {EXCEL_PATH}")
        sys.exit(1)

    xl = pd.ExcelFile(EXCEL_PATH)
    all_events = []
    
    seen_events = set()
    for sheet in xl.sheet_names:
        print(f"Procesando hoja: {sheet}...")
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet, header=None)
        sheet_events = parse_month_sheet(df, sheet)
        
        filtered_sheet_events = []
        for ev in sheet_events:
            # Clave única: (título normalizado, fecha)
            key = (ev["titulo"].strip().lower(), ev["fecha"].date())
            if key not in seen_events:
                seen_events.add(key)
                filtered_sheet_events.append(ev)
        
        print(f"  - Encontrados {len(filtered_sheet_events)} eventos únicos (de {len(sheet_events)}).")
        all_events.extend(filtered_sheet_events)

    if not all_events:
        print("No se encontraron eventos para importar.")
        return

    print(f"\nTotal eventos encontrados: {len(all_events)}")
    
    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
            # Primero limpiar eventos previos de categoría ejecutiva para evitar duplicados en re-sincronización
            cur.execute("DELETE FROM fundacion_tareas WHERE categoria = 'ejecutiva'")
            
            for ev in all_events:
                cur.execute("""
                    INSERT INTO fundacion_tareas (titulo, fecha_inicio, fecha_fin, categoria, subcategoria, color, estado, creado_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    ev["titulo"],
                    ev["fecha"],
                    ev["fecha"],
                    "ejecutiva",
                    ev["subcategoria"],
                    ev["color"],
                    "pendiente",
                    "system_sync"
                ))
            
            conn.commit()
            print("Importación completada exitosamente en la base de datos.")
    except Exception as e:
        conn.rollback()
        print(f"Error durante la importación: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
