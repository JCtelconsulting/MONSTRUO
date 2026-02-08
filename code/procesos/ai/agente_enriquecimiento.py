
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from googlesearch import search
import time
import random
import os

# Configuración
INPUT_FILE = '/srv/monstruo/data/Base_Preventa_Telecomunicaciones.xlsx'
OUTPUT_FILE = '/srv/monstruo/data/Base_Preventa_Enriquecida_Pilot.xlsx'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# --- ZONA "GUIÑO GUIÑO" ---
# Un proxy rotativo cambia tu IP en cada petición automáticamente.
# Formato típico: "http://usuario:password@host:puerto"
PROXY_URL = None  # <--- Pega aquí tu proxy comprado (ej. Smartproxy, BrightData, IPRoyal)
# --------------------------

from duckduckgo_search import DDGS
from fake_useragent import UserAgent

# --- CONFIGURACIÓN DE PROXIES ---
PROXY_FILE = '/srv/monstruo/proxies.txt'

def load_proxies():
    if not os.path.exists(PROXY_FILE):
        return []
    with open(PROXY_FILE, 'r') as f:
        # Formatos esperados: 
        # ip:port
        # user:pass@ip:port
        # http://...
        raw = [l.strip() for l in f.readlines() if l.strip()]
        
    proxies = []
    for p in raw:
        if not p.startswith('http'):
            # Asumimos http por defecto si no tiene esquema
            proxies.append(f"http://{p}")
        else:
            proxies.append(p)
    return proxies

PROXIES = load_proxies()
print(f"Proxies cargados: {len(PROXIES)}")
# ------------------------------

def get_url(company_name):
    query = f"{company_name} chile contacto"
    ua = UserAgent()
    
    # Seleccionar proxy rotativo
    current_proxy = random.choice(PROXIES) if PROXIES else None
    
    try:
        # Nota: DDGS espera 'proxies' (plural) o 'proxy' (singular)?
        # Check docs: DDGS(proxies="http://user:pass@10.10.10.10:3128") or dict?
        # En versiones recientes es 'proxies' string o dict. Probamos string directo.
        
        if current_proxy:
            # print(f"   [Debug] Usando proxy: {current_proxy}")
            ddgs = DDGS(headers={"User-Agent": ua.random}, proxies=current_proxy, timeout=20)
        else:
            ddgs = DDGS(headers={"User-Agent": ua.random})
            
        results = ddgs.text(query, max_results=1)
        if results:
            return results[0]['href']
    except Exception as e:
        print(f"Error buscando {company_name}: {e}")
        # Si falla proxy, podríamos reintentar, pero por simplicidad seguimos
        return None
    return None

def extract_contacts(url):
    contacts = {'email': [], 'phone': []}
    if not url:
        return contacts
    
    ua = UserAgent()
    current_proxy = random.choice(PROXIES) if PROXIES else None
    proxies_dict = {"http": current_proxy, "https": current_proxy} if current_proxy else None

    try:
        response = requests.get(url, headers={'User-Agent': ua.random}, proxies=proxies_dict, timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()
            
            # Emails: regex simple
            emails = set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text))
            # Filtrar emails basura comunes
            clean_emails = [e for e in emails if not any(x in e.lower() for x in ['wix', 'sentry', 'example', 'domain', 'image'])]
            contacts['email'] = list(clean_emails)[:2] # Tomar max 2
            
            # Telefonos: regex chileno muy basico (+569, 22, etc)
            # Esto es ruidoso, mejor buscar patrones específicos o 'tel:', 'callto:' links
            phone_links = soup.select('a[href^="tel:"]')
            phones = set([p['href'].replace('tel:', '') for p in phone_links])
            contacts['phone'] = list(phones)[:1]

    except Exception as e:
        print(f"Error scraping {url}: {e}")
    
    return contacts

def process_batch(limit=10):
    print(f"Cargando {INPUT_FILE}...")
    df = pd.read_excel(INPUT_FILE)
    
    # Seleccionar solo los vacíos
    # Para el piloto tomaremos los primeros 'limit' registros
    
    print(f"Iniciando piloto con {limit} empresas...")
    
    for index, row in df.head(limit).iterrows():
        company = row['Nombre Empresa']
        print(f"[{index+1}/{limit}] Procesando: {company}")
        
        # 1. Buscar URL
        url = get_url(company)
        print(f"   -> URL encontrada: {url}")
        
        if url:
            # 2. Extraer datos
            data = extract_contacts(url)
            print(f"   -> Datos: {data}")
            
            # 3. Actualizar DF
            if data['email']:
                current_email = str(row['Email Contacto']) if pd.notna(row['Email Contacto']) else ""
                new_email = ", ".join(data['email'])
                df.at[index, 'Email Contacto'] = f"{current_email} {new_email}".strip()
                
                # Tambien llenar el de empresa si esta vacio
                if pd.isna(row['Correo Empresa']) or str(row['Correo Empresa']).strip() == "":
                    df.at[index, 'Correo Empresa'] = new_email

            if data['phone']:
                current_phone = str(row['Fono Contacto']) if pd.notna(row['Fono Contacto']) else ""
                new_phone = ", ".join(data['phone'])
                df.at[index, 'Fono Contacto'] = f"{current_phone} {new_phone}".strip()
            
            # Guardamos la web encontrada en algun lado? Podriamos usar "Web Sugerida" si existiera o Notas, 
            # pero por ahora vamos directo a los contactos.
            
        else:
            print("   -> No se encontró URL")
            
        # Pausa dramática para que Google no sospeche
        wait_time = random.uniform(DELAY_MIN, DELAY_MAX)
        print(f"   ...Esperando {wait_time:.1f}s para parecer humano...")
        time.sleep(wait_time)

    print(f"Guardando resultados piloto en {OUTPUT_FILE}")
    df.head(limit).to_excel(OUTPUT_FILE, index=False)
    print("Piloto finalizado.")

if __name__ == "__main__":
    process_batch(limit=10)
