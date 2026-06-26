import os
import re
import io
import time
import h5py
import requests
import pandas as pd
from dotenv import load_dotenv

# Configuración
load_dotenv()
API_KEY = os.getenv('API_KEY')
EMAIL_USUARIO = os.getenv('EMAIL_USUARIO')
ANIO_OBJETIVO = '2017'

ARCHIVO_H5 = 'Data/datos_nsrdb/nsrdb_puerto_rico_2017.h5'
DIRECTORIO_SALIDA = 'Data/Puerto_Rico_v4_2017/crudos_api/2017_V4_Completo'

def cargar_coordenadas(h5_path):
    with h5py.File(h5_path, 'r') as f:
        df_meta = pd.DataFrame(f['meta'][:])
        if isinstance(df_meta['latitude'].iloc[0], bytes):
            df_meta['latitude'] = df_meta['latitude'].apply(lambda x: float(x.decode('utf-8')))
            df_meta['longitude'] = df_meta['longitude'].apply(lambda x: float(x.decode('utf-8')))
    return df_meta[['latitude', 'longitude']]

def extraer_nodo_v4_total(nodo_id, lat, lon):
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
        
        df = pd.read_csv(io.StringIO(response.text), skiprows=2)
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        df.insert(0, 'nodo_id', nodo_id)
        
        ruta_salida = os.path.join(DIRECTORIO_SALIDA, f'nodo_{nodo_id}_{ANIO_OBJETIVO}_v4.parquet')
        df.to_parquet(ruta_salida, engine='pyarrow', index=False)
        return True
        
    except Exception as e:
        print(f"  -> [ERROR] Falló nuevamente el nodo {nodo_id}: {e}")
        return False

def ejecutar_parche_quirurgico():
    print("=== INICIANDO ESCANEO DE DISCO (PARCHE DE RED) ===")
    
    # 1. Identificar qué nodos están realmente en el disco
    archivos_existentes = os.listdir(DIRECTORIO_SALIDA)
    nodos_en_disco = set()
    
    for archivo in archivos_existentes:
        # Extraer el número del nodo usando una expresión regular
        match = re.search(r'nodo_(\d+)_', archivo)
        if match:
            nodos_en_disco.add(int(match.group(1)))
            
    print(f"Archivos sanos encontrados en disco: {len(nodos_en_disco):,}")
    
    # 2. Encontrar los faltantes (sabemos que en total son 2480, del 0 al 2479)
    nodos_faltantes = [i for i in range(2480) if i not in nodos_en_disco]
    
    print(f"Nodos con fallas de red a recuperar: {len(nodos_faltantes)}")
    
    if not nodos_faltantes:
        print("No hay nodos faltantes. El directorio está completo.")
        return
        
    print(f"IDs a descargar: {nodos_faltantes}\n")
    
    # 3. Descargar los faltantes
    df_coords = cargar_coordenadas(ARCHIVO_H5)
    
    for nodo_id in nodos_faltantes:
        lat = df_coords.loc[nodo_id, 'latitude']
        lon = df_coords.loc[nodo_id, 'longitude']
        
        print(f"Recuperando Nodo {nodo_id}...", end=" ", flush=True)
        exito = extraer_nodo_v4_total(nodo_id, lat, lon)
        
        if exito:
            print("✅ Exito")
        
        time.sleep(1.5) # Pausa de seguridad
        
    print("\n=== PARCHE FINALIZADO ===")
    print("Por favor, vuelve a ejecutar el script 'consolidar_limpiar_v4.py'")

if __name__ == "__main__":
    ejecutar_parche_quirurgico()