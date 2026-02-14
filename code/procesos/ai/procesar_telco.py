
import pandas as pd
import os

# Configuración de rutas
INPUT_FILE = '/srv/monstruo_dev/BD Telecomunicaciones.xlsx'
OUTPUT_FILE = '/srv/monstruo_dev/data/Base_Preventa_Telecomunicaciones.xlsx'

# Asegurar que el directorio de salida existe
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

def process_data():
    print(f"Leyendo archivo: {INPUT_FILE}")
    try:
        df = pd.read_excel(INPUT_FILE)
    except FileNotFoundError:
        print(f"Error: No se encontró el archivo {INPUT_FILE}")
        return
    except Exception as e:
        print(f"Error al leer el archivo: {e}")
        return

    print(f"Total registros leídos: {len(df)}")

    
    # 1. Filtrado de Rubros -> SE INCLUYEN TODOS LOS REGISTROS POR PETICIÓN DEL USUARIO
    # rubros_validos = [...]
    
    # Normalizar para evitar problemas de espacios
    df['Tipo_Sugerido'] = df['Tipo_Sugerido'].astype(str).str.strip()
    
    # Tomamos todos los datos
    df_filtered = df.copy()
    print(f"Procesando sin filtro. Total registros: {len(df_filtered)}")

    # 2. Mapeo de Columnas
    # Estructura Solicitada:
    # DE LA EMPRESA: Nombre Empresa / Dirección / Ciudad / Telefono / Correo / Linea de Negocio
    # DEL CONTACTO: Contacto / Fono del Contacto / email

    # Mapeo:
    # Nombre Empresa <- Empresa
    # Dirección <- (Vacio)
    # Ciudad <- Region_Sugerida
    # Telefono (Empresa) <- Telefono
    # Correo (Empresa) <- Email
    # Linea de Negocio <- Tipo_Sugerido + " - " + Posibles_Negocios (para dar más contexto)
    
    # Contacto <- Contacto
    # Fono del Contacto <- Telefono (Si hay nombre de contacto, asumimos que el fono le sirve, o lo repetimos)
    # email (Contacto) <- Email (Mismo criterio)

    # Preparar columnas de salida
    output_data = pd.DataFrame()
    
    output_data['Nombre Empresa'] = df_filtered['Empresa']
    output_data['Dirección'] = "" # No hay dato en fuente
    output_data['Ciudad'] = df_filtered['Region_Sugerida']
    output_data['Teléfono Empresa'] = df_filtered['Telefono']
    output_data['Correo Empresa'] = df_filtered['Email']
    
    # Concatenar para Línea de Negocio
    output_data['Línea de Negocio'] = df_filtered['Tipo_Sugerido'] + " - " + df_filtered['Posibles_Negocios'].fillna('')
    
    # Separador visual (opcional, pero en excel son columnas contiguas)
    
    output_data['Nombre Contacto'] = df_filtered['Contacto']
    output_data['Fono Contacto'] = df_filtered['Telefono'] # Repetimos el fono base si no hay uno específico
    output_data['Email Contacto'] = df_filtered['Email']   # Repetimos el email base
    
    # Limpieza final (NaN a string vacio)
    output_data = output_data.fillna("")
    
    # Eliminar duplicados exactos
    initial_count = len(output_data)
    output_data = output_data.drop_duplicates()
    print(f"Eliminados {initial_count - len(output_data)} duplicados.")

    # 3. Exportar
    print(f"Guardando {len(output_data)} registros en {OUTPUT_FILE}")
    output_data.to_excel(OUTPUT_FILE, index=False)
    print("Proceso completado.")

if __name__ == "__main__":
    process_data()
