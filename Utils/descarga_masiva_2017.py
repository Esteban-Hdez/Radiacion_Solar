import os
import io
import time
import h5py
import requests
import pandas as pd
from dotenv import load_dotenv

# ==========================================
# Configuración Inicial
# ==========================================
load_dotenv()
API_KEY = os.getenv('API_KEY')
EMAIL_USUARIO = "a2173010088@alumnos.uat.edu.mx" # <-- Actualiza esto
ANIO_OBJETIVO = '2017'

# Rutas de archivos
ARCHIVO_H5 = 'Data/datos_nsrdb/nsrdb_puerto_rico_2017.h5'
DIRECTORIO_SALIDA = 'Data/API_Historico/2017'
LOG_COMPLETADOS = 'Data/API_Historico/nodos_completados_2017.log'

def cargar_coordenadas(h5_path):
    """Extrae las coordenadas de todos los nodos en el archivo HDF5."""
    with h5py.File(h5_path, 'r') as f:
        df_meta = pd.DataFrame(f['meta'][:])
        
        # Manejo de decodificación de bytes
        if isinstance(df_meta['latitude'].iloc[0], bytes):
            df_meta['latitude'] = df_meta['latitude'].apply(lambda x: float(x.decode('utf-8')))
            df_meta['longitude'] = df_meta['longitude'].apply(lambda x: float(x.decode('utf-8')))
            
    return df_meta[['latitude', 'longitude']]

def extraer_nodo_psmv4(nodo_id, lat, lon):
    """Realiza la petición al endpoint PSM v4 y guarda el Parquet."""
    url_base = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"
    wkt_punto = f"POINT({lon} {lat})"
    
    parametros = {
        'api_key': API_KEY,
        'email': EMAIL_USUARIO,
        'wkt': wkt_punto,
        'names': ANIO_OBJETIVO,
        # Atributos actualizados: Incluye temperatura del aire
        'attributes': 'cloud_type,relative_humidity,air_temperature',
        'interval': '60',
        'utc': 'true',
        'leap_day': 'false'
    }

    try:
        response = requests.get(url_base, params=parametros, timeout=45)
        
        if response.status_code == 429:
            return 'LIMITE'
            
        response.raise_for_status()
        
        # Procesar datos
        df = pd.read_csv(io.StringIO(response.text), skiprows=2)
        df.columns = df.columns.str.strip()
        df.insert(0, 'nodo_id', nodo_id)
        
        # Guardar archivo individual
        ruta_salida = os.path.join(DIRECTORIO_SALIDA, f'nodo_{nodo_id}_{ANIO_OBJETIVO}.parquet')
        df.to_parquet(ruta_salida, engine='pyarrow', index=False)
        
        return 'EXITO'
        
    except requests.exceptions.RequestException as e:
        print(f" [ERROR de red] {e}")
        return 'ERROR'

def iniciar_pipeline_masivo():
    os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)
    
    print("Iniciando Pipeline Espacial - NSRDB PSM v4")
    print("-" * 50)
    
    df_coords = cargar_coordenadas(ARCHIVO_H5)
    total_nodos = len(df_coords)
    
    # Sistema de Checkpoints (Tolerancia a fallos)
    nodos_listos = set()
    if os.path.exists(LOG_COMPLETADOS):
        with open(LOG_COMPLETADOS, 'r') as f:
            nodos_listos = set(int(line.strip()) for line in f.readlines())
            
    nodos_pendientes = [n for n in df_coords.index if n not in nodos_listos]
    
    print(f"Total en malla: {total_nodos}")
    print(f"Ya procesados:  {len(nodos_listos)}")
    print(f"Por descargar:  {len(nodos_pendientes)}\n")
    
    if len(nodos_pendientes) == 0:
        print("✅ Todos los nodos han sido descargados.")
        return

    tiempo_inicio = time.time()
    
    for count, nodo_id in enumerate(nodos_pendientes, 1):
        lat = df_coords.loc[nodo_id, 'latitude']
        lon = df_coords.loc[nodo_id, 'longitude']
        
        print(f"[{count}/{len(nodos_pendientes)}] Descargando Nodo {nodo_id:04d}...", end=" ", flush=True)
        
        estado = extraer_nodo_psmv4(nodo_id, lat, lon)
        
        if estado == 'EXITO':
            print("✅ OK")
            # Guardar el nodo en el log inmediatamente
            with open(LOG_COMPLETADOS, 'a') as f:
                f.write(f"{nodo_id}\n")
        elif estado == 'LIMITE':
            print("\n🛑 Límite diario de API alcanzado. El progreso está a salvo.")
            break
        else:
            print("⚠️ Reintento sugerido en próxima ejecución.")
            
        # Pausa para evitar saturar el servidor del laboratorio (Buenas prácticas)
        time.sleep(1.5)

    tiempo_total = (time.time() - tiempo_inicio) / 3600
    print(f"\nEjecución finalizada. Tiempo de sesión: {tiempo_total:.2f} horas.")

if __name__ == "__main__":
    if not API_KEY:
        print("❌ Error: API_KEY no configurada.")
    else:
        iniciar_pipeline_masivo()