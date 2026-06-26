import os
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

# Rutas de trabajo
ARCHIVO_CSV = 'Data/Geometria/metadata_nodos_tamaulipas.csv'
ARCHIVO_METADATOS_FINAL = 'Data/Geometria/metadata_nodos_tamaulipas_final.csv'
DIRECTORIO_SALIDA = 'Data/API_Historico/Tamaulipas_2017_V4_Completo'
LOG_COMPLETADOS = 'Data/API_Historico/nodos_completados_tamaulipas_v4.log'

def cargar_coordenadas(csv_path):
    """Carga la matriz de coordenadas generada previamente."""
    df_meta = pd.read_csv(csv_path)
    df_meta.set_index('nodo_id', inplace=True)
    return df_meta[['latitude', 'longitude']]

def extraer_nodo_v4(nodo_id, lat, lon):
    """
    Descarga el clima y extrae la elevación (msnm) de los metadatos.
    Retorna: (Estado, Elevación)
    """
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
        
        if response.status_code == 429:
            return 'LIMITE', None
            
        response.raise_for_status()
        
        # 1. Extracción de Metadatos Estáticos (MSNM)
        df_meta_api = pd.read_csv(io.StringIO(response.text), nrows=1)
        elevacion_oficial = float(df_meta_api['Elevation'].iloc[0])
        
        # 2. Procesamiento de Series Temporales (Clima)
        df_clima = pd.read_csv(io.StringIO(response.text), skiprows=2)
        df_clima.columns = df_clima.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # Inyectamos solo la llave espacial primaria
        df_clima.insert(0, 'nodo_id', nodo_id)
        
        # Guardar archivo Parquet (limpio de redundancias estáticas)
        ruta_salida = os.path.join(DIRECTORIO_SALIDA, f'nodo_{nodo_id}_{ANIO_OBJETIVO}_v4.parquet')
        df_clima.to_parquet(ruta_salida, engine='pyarrow', index=False)
        
        return 'EXITO', elevacion_oficial
        
    except requests.exceptions.RequestException as e:
        print(f" [ERROR de red en Nodo {nodo_id}] {e}")
        return 'ERROR', None
    except Exception as e:
        print(f" [ERROR inesperado en Nodo {nodo_id}] {e}")
        return 'ERROR', None

def iniciar_pipeline_blindado():
    os.makedirs(DIRECTORIO_SALIDA, exist_ok=True)
    os.makedirs(os.path.dirname(LOG_COMPLETADOS), exist_ok=True)
    
    print("🚀 Iniciando Pipeline Masivo PSM v4 - TAMAULIPAS")
    print("-" * 60)
    
    try:
        df_coords = cargar_coordenadas(ARCHIVO_CSV)
    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo {ARCHIVO_CSV}.")
        return
    
    # 1. Leer Checkpoints
    nodos_listos = set()
    diccionario_msnm = {}
    
    if os.path.exists(LOG_COMPLETADOS):
        with open(LOG_COMPLETADOS, 'r') as f:
            nodos_listos = set(int(line.strip()) for line in f.readlines())
            
    # Si ya existe un progreso de metadatos, lo cargamos
    if os.path.exists(ARCHIVO_METADATOS_FINAL):
        df_existente = pd.read_csv(ARCHIVO_METADATOS_FINAL)
        diccionario_msnm = dict(zip(df_existente['nodo_id'], df_existente['msnm']))

    nodos_pendientes = [n for n in df_coords.index if n not in nodos_listos]
    
    print(f"Total en malla Tamaulipas: {len(df_coords)}")
    print(f"Ya procesados en log:      {len(nodos_listos)}")
    print(f"En cola para descargar:    {len(nodos_pendientes)}\n")
    
    if not nodos_pendientes:
        print("✅ Descarga masiva completada al 100%.")
        return

    tiempo_inicio = time.time()
    
    for count, nodo_id in enumerate(nodos_pendientes, 1):
        lat = df_coords.loc[nodo_id, 'latitude']
        lon = df_coords.loc[nodo_id, 'longitude']
        
        print(f"[{count}/{len(nodos_pendientes)}] Descargando Nodo {nodo_id:04d}...", end=" ", flush=True)
        
        estado, elevacion = extraer_nodo_v4(nodo_id, lat, lon)
        
        if estado == 'EXITO':
            print(f"✅ OK (Altitud: {elevacion}m)")
            
            # Actualizar progreso en disco de forma atómica
            with open(LOG_COMPLETADOS, 'a') as f:
                f.write(f"{nodo_id}\n")
                
            # Guardar la altitud en memoria RAM
            diccionario_msnm[nodo_id] = elevacion
            
            # Cada 100 iteraciones, guardar el CSV final por si el servidor se apaga
            if count % 100 == 0 or count == len(nodos_pendientes):
                print(f"   💾 Guardando checkpoint de metadatos estáticos...")
                # Reconstruir la metadata combinando las coordenadas y las altitudes
                df_final = df_coords.copy().reset_index()
                # Mapear las altitudes (si no se ha descargado un nodo aún, quedará NaN)
                df_final['msnm'] = df_final['nodo_id'].map(diccionario_msnm)
                df_final.to_csv(ARCHIVO_METADATOS_FINAL, index=False)
                
        elif estado == 'LIMITE':
            print("\n🛑 Límite diario de 10,000 alcanzado. Script detenido de forma segura.")
            break
        else:
            print("⚠️ Falla temporal. Se reintentará en el futuro.")
            
        time.sleep(1.5)

    tiempo_total = (time.time() - tiempo_inicio) / 3600
    print(f"\nEjecución finalizada. Tiempo de sesión: {tiempo_total:.2f} horas.")
    print(f"Metadatos finales (con MSNM) asegurados en: {ARCHIVO_METADATOS_FINAL}")

if __name__ == "__main__":
    if not API_KEY:
        print("❌ Error: Verifica tu archivo .env, no se detectó API_KEY.")
    else:
        iniciar_pipeline_blindado()