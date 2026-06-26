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
EMAIL_USUARIO = os.getenv('EMAIL_USUARIO')
ANIO_OBJETIVO = '2017'

# Rutas de archivos espaciales
ARCHIVO_H5 = 'Data/datos_nsrdb/nsrdb_puerto_rico_2017.h5'
DIRECTORIO_SALIDA = 'Data/Puerto_Rico_v4_2017/crudos_api/2017_V4_Completo'
LOG_COMPLETADOS = 'Data/Puerto_Rico_v4_2017/crudos_api/nodos_completados_v4.log'

def cargar_coordenadas(h5_path):
    """Extrae las coordenadas maestras de los 2,480 nodos."""
    with h5py.File(h5_path, 'r') as f:
        df_meta = pd.DataFrame(f['meta'][:])
        if isinstance(df_meta['latitude'].iloc[0], bytes):
            df_meta['latitude'] = df_meta['latitude'].apply(lambda x: float(x.decode('utf-8')))
            df_meta['longitude'] = df_meta['longitude'].apply(lambda x: float(x.decode('utf-8')))
    return df_meta[['latitude', 'longitude']]

def extraer_nodo_v4_total(nodo_id, lat, lon):
    """Descarga TODAS las variables de la API PSM v4 para un nodo."""
    url_base = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"
    wkt_punto = f"POINT({lon} {lat})"
    
    # Parámetros (SIN 'attributes' para forzar la descarga de la matriz completa)
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
        
        # Proteger contra el límite de 10,000 peticiones diarias
        if response.status_code == 429:
            return 'LIMITE'
            
        response.raise_for_status()
        
        # Inyectar a Pandas saltando los metadatos del servidor
        df = pd.read_csv(io.StringIO(response.text), skiprows=2)
        
        # Limpieza profesional de nombres de columnas (snake_case)
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Inyectar la llave espacial
        df.insert(0, 'nodo_id', nodo_id)
        
        # Guardar en disco duro con alta compresión
        ruta_salida = os.path.join(DIRECTORIO_SALIDA, f'nodo_{nodo_id}_{ANIO_OBJETIVO}_v4.parquet')
        df.to_parquet(ruta_salida, engine='pyarrow', index=False)
        
        return 'EXITO'
        
    except requests.exceptions.RequestException as e:
        print(f" [ERROR de red en Nodo {nodo_id}] {e}")
        return 'ERROR'

def iniciar_pipeline_blindado():
    os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_COMPLETADOS), exist_ok=True)
    
    print("🚀 Iniciando Pipeline Masivo PSM v4 (Variables Completas)")
    print("-" * 60)
    
    df_coords = cargar_coordenadas(ARCHIVO_H5)
    
    # Leer Checkpoints para protección contra fallos
    nodos_listos = set()
    if os.path.exists(LOG_COMPLETADOS):
        with open(LOG_COMPLETADOS, 'r') as f:
            nodos_listos = set(int(line.strip()) for line in f.readlines())
            
    nodos_pendientes = [n for n in df_coords.index if n not in nodos_listos]
    
    print(f"Total en malla original: {len(df_coords)}")
    print(f"Ya procesados en log:    {len(nodos_listos)}")
    print(f"En cola para descargar:  {len(nodos_pendientes)}\n")
    
    if not nodos_pendientes:
        print("✅ Descarga masiva completada al 100%.")
        return

    tiempo_inicio = time.time()
    
    for count, nodo_id in enumerate(nodos_pendientes, 1):
        lat = df_coords.loc[nodo_id, 'latitude']
        lon = df_coords.loc[nodo_id, 'longitude']
        
        print(f"[{count}/{len(nodos_pendientes)}] Descargando Nodo {nodo_id:04d}...", end=" ", flush=True)
        
        estado = extraer_nodo_v4_total(nodo_id, lat, lon)
        
        if estado == 'EXITO':
            print("✅ OK")
            # Escribir en el disco INMEDIATAMENTE para asegurar el checkpoint
            with open(LOG_COMPLETADOS, 'a') as f:
                f.write(f"{nodo_id}\n")
        elif estado == 'LIMITE':
            print("\n🛑 Límite diario de 10,000 alcanzado. Script detenido de forma segura.")
            break
        else:
            print("⚠️ Falla temporal. Se reintentará en el futuro.")
            
        # Pausa obligatoria para evitar baneo de IP por DDoS
        time.sleep(1.5)

    tiempo_total = (time.time() - tiempo_inicio) / 3600
    print(f"\nEjecución finalizada. Tiempo de sesión: {tiempo_total:.2f} horas.")

if __name__ == "__main__":
    if not API_KEY:
        print("❌ Error: Verifica tu archivo .env, no se detectó API_KEY.")
    else:
        iniciar_pipeline_blindado()