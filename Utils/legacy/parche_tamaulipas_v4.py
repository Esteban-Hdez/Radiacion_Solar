import os
import re
import io
import time
import requests
import pandas as pd
from dotenv import load_dotenv

# ==========================================
# Configuración Inicial
# ==========================================
load_dotenv()
API_KEY = os.getenv('API_KEY')
EMAIL_USUARIO = os.getenv('EMAIL_USUARIO')
ANIO_OBJETIVO = '2017'

TOTAL_NODOS = 4940  # Malla oficial de Tamaulipas

# Rutas actualizadas
ARCHIVO_CSV = 'Data/Geometria/metadata_nodos_tamaulipas.csv'
ARCHIVO_METADATOS_FINAL = 'Data/Geometria/metadata_nodos_tamaulipas_final.csv'
DIRECTORIO_SALIDA = 'Data/API_Historico/Tamaulipas_2017_V4_Completo'

def cargar_coordenadas(csv_path):
    """Carga la matriz de coordenadas original."""
    df_meta = pd.read_csv(csv_path)
    df_meta.set_index('nodo_id', inplace=True)
    return df_meta[['latitude', 'longitude']]

def extraer_nodo_y_elevacion(nodo_id, lat, lon):
    """Descarga el clima y extrae la elevación oficial."""
    url_base = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"
    wkt_punto = f"POINT({lon} {lat})"
    
    parametros = {
        'api_key': API_KEY,
        'email': EMAIL_USUARIO,
        'wkt': wkt_punto,
        'names': ANIO_OBJETIVO,
        'interval': '60',
        'utc': 'true',
        'leap_day': 'false'
    }

    try:
        response = requests.get(url_base, params=parametros, timeout=45)
        response.raise_for_status()
        
        # 1. Extraer MSNM (Elevación)
        df_meta_api = pd.read_csv(io.StringIO(response.text), nrows=1)
        elevacion = float(df_meta_api['Elevation'].iloc[0])
        
        # 2. Extraer Clima y limpiar nombres
        df_clima = pd.read_csv(io.StringIO(response.text), skiprows=2)
        df_clima.columns = df_clima.columns.str.strip().str.lower().str.replace(' ', '_')
        df_clima.insert(0, 'nodo_id', nodo_id)
        
        # Guardar en disco el clima dinámico
        ruta_salida = os.path.join(DIRECTORIO_SALIDA, f'nodo_{nodo_id}_{ANIO_OBJETIVO}_v4.parquet')
        df_clima.to_parquet(ruta_salida, engine='pyarrow', index=False)
        
        return True, elevacion
        
    except Exception as e:
        print(f"  -> [ERROR] Falló el nodo {nodo_id}: {e}")
        return False, None

def ejecutar_parche_quirurgico():
    print("=== INICIANDO ESCANEO DE DISCO (PARCHE DE RED TAMAULIPAS) ===")
    
    # 1. Identificar qué nodos están realmente en el disco duro
    archivos_existentes = os.listdir(DIRECTORIO_SALIDA)
    nodos_en_disco = set()
    
    for archivo in archivos_existentes:
        # Extraer el número del nodo usando una expresión regular
        match = re.search(r'nodo_(\d+)_', archivo)
        if match:
            nodos_en_disco.add(int(match.group(1)))
            
    print(f"Archivos sanos encontrados en disco: {len(nodos_en_disco):,}")
    
    # 2. Encontrar los faltantes
    nodos_faltantes = [i for i in range(TOTAL_NODOS) if i not in nodos_en_disco]
    
    print(f"Nodos con fallas de red a recuperar: {len(nodos_faltantes)}")
    
    if not nodos_faltantes:
        print("✅ No hay nodos faltantes. El directorio está 100% completo.")
        return
        
    print(f"IDs a descargar: {nodos_faltantes}\n")
    
    # 3. Preparación de la recuperación
    df_coords = cargar_coordenadas(ARCHIVO_CSV)
    
    # Cargar el archivo de metadatos maestro para tapar los "huecos" de MSNM
    if os.path.exists(ARCHIVO_METADATOS_FINAL):
        df_meta_final = pd.read_csv(ARCHIVO_METADATOS_FINAL)
        df_meta_final.set_index('nodo_id', inplace=True)
    else:
        df_meta_final = df_coords.copy()
        df_meta_final['msnm'] = float('nan')
    
    # 4. Descarga de los faltantes
    for nodo_id in nodos_faltantes:
        lat = df_coords.loc[nodo_id, 'latitude']
        lon = df_coords.loc[nodo_id, 'longitude']
        
        print(f"Recuperando Nodo {nodo_id:04d}...", end=" ", flush=True)
        exito, elevacion = extraer_nodo_y_elevacion(nodo_id, lat, lon)
        
        if exito:
            print(f"✅ Exito (Altitud: {elevacion}m)")
            # Actualizar el MSNM en la tabla maestra
            df_meta_final.loc[nodo_id, 'msnm'] = elevacion
            
            # Guardar el CSV maestro actualizando el registro (sin reescribir el índice de nuevo)
            df_meta_final.reset_index().to_csv(ARCHIVO_METADATOS_FINAL, index=False)
        
        # Pausa de seguridad para evitar baneos
        time.sleep(1.5) 
        
    print("\n=== PARCHE FINALIZADO ===")
    print("Vuelve a correr este script una vez más solo para certificar que queden 0 faltantes.")

if __name__ == "__main__":
    ejecutar_parche_quirurgico()