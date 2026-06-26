import os
import requests
import pandas as pd
import time
import csv
from dotenv import load_dotenv

def corregir_alineacion_masiva():
    """
    Recorre todos los nodos del archivo maestro, consulta las coordenadas
    reales del satélite NREL usando peticiones ultraligeras y corrige el CSV.
    """
    print("=== REPARACIÓN DE ALINEACIÓN SATELITAL (RASTER SHIFT) ===")
    
    # 1. Configuración
    load_dotenv()
    API_KEY = os.getenv('API_KEY')
    EMAIL_USUARIO = os.getenv('EMAIL_USUARIO')
    
    if not API_KEY:
        print("❌ Error: Verifica tu archivo .env, no se detectó API_KEY.")
        return

    ruta_csv = 'Data/Geometria/metadata_nodos_tamaulipas_final.csv'
    
    try:
        df_meta = pd.read_csv(ruta_csv)
    except FileNotFoundError:
        print(f"❌ Error: No se encontró el archivo {ruta_csv}")
        return

    # Crear columnas de respaldo para las coordenadas locales si no existen
    if 'lat_local' not in df_meta.columns:
        df_meta['lat_local'] = df_meta['latitude']
        df_meta['lon_local'] = df_meta['longitude']

    # Crear columnas para las coordenadas corregidas si no existen
    if 'lat_nrel' not in df_meta.columns:
        df_meta['lat_nrel'] = 0.0
        df_meta['lon_nrel'] = 0.0
        df_meta['corregido'] = False

    nodos_a_corregir = df_meta[df_meta['corregido'] == False]
    total_pendientes = len(nodos_a_corregir)
    
    print(f"-> Archivo maestro cargado: {len(df_meta)} nodos.")
    print(f"-> Nodos pendientes por corregir: {total_pendientes}\n")
    
    if total_pendientes == 0:
        print("✅ Todos los nodos ya han sido corregidos y alineados con NREL.")
        return

    url_base = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"
    tiempo_inicio = time.time()

    # 2. Iterar y Corregir
    for index, row in nodos_a_corregir.iterrows():
        nodo_id = int(row['nodo_id'])
        lat_local = row['lat_local']
        lon_local = row['lon_local']
        
        # Petición ULTRALIGERA: Pedimos 'ghi' como excusa válida para que la API responda
        parametros = {
            'api_key': API_KEY,
            'email': EMAIL_USUARIO,
            'wkt': f"POINT({lon_local} {lat_local})",
            'names': '2017',
            'attributes': 'ghi',  # <-- SOLUCIÓN: Usamos una variable temporal válida
            'interval': '60',
            'utc': 'true',
            'leap_day': 'false'
        }
        
        try:
            # stream=True nos permite cortar la conexión apenas leemos las cabeceras
            response = requests.get(url_base, params=parametros, stream=True, timeout=15)
            
            if response.status_code == 429:
                print("\n🛑 Límite de peticiones de la API alcanzado. El progreso ha sido guardado.")
                break
                
            response.raise_for_status()
            
            # Extraer las primeras dos líneas (Headers y Values de la Metadata)
            lineas = []
            for line in response.iter_lines():
                if line:
                    lineas.append(line.decode('utf-8'))
                if len(lineas) == 2:
                    break
            response.close()
            
            # Procesar el CSV en memoria
            headers = list(csv.reader([lineas[0]]))[0]
            values = list(csv.reader([lineas[1]]))[0]
            meta_dict = dict(zip(headers, values))
            
            lat_nrel = float(meta_dict['Latitude'])
            lon_nrel = float(meta_dict['Longitude'])
            
            # 3. Aplicar Corrección
            df_meta.at[index, 'lat_nrel'] = lat_nrel
            df_meta.at[index, 'lon_nrel'] = lon_nrel
            df_meta.at[index, 'corregido'] = True
            
            # Imprimir progreso limpio
            if index % 50 == 0:
                print(f"[{index}/{total_pendientes}] Corrigiendo Nodo {nodo_id:04d} -> Shift ajustado: Δ Lat {abs(lat_local - lat_nrel):.4f}")
            
            # Guardar Checkpoint cada 200 nodos
            if index % 200 == 0:
                df_meta.to_csv(ruta_csv, index=False)
                
            time.sleep(0.3) # Pausa corta (es una petición muy ligera)

        except Exception as e:
            print(f"⚠️ [ERROR] Falla en Nodo {nodo_id}: {e}")
            time.sleep(2)

    # 4. Guardado Final y Limpieza
    # Reemplazamos las columnas principales (latitude/longitude) por las reales de NREL 
    # para que los modelos de Machine Learning las usen por defecto.
    df_meta['latitude'] = df_meta['lat_nrel']
    df_meta['longitude'] = df_meta['lon_nrel']
    
    # Limpiamos solo la columna temporal de control, pero CONSERVAMOS 
    # lat_local, lon_local, lat_nrel y lon_nrel para revisiones futuras.
    df_meta.drop(columns=['corregido'], inplace=True, errors='ignore')
    
    df_meta.to_csv(ruta_csv, index=False)
    
    tiempo_total = (time.time() - tiempo_inicio) / 60
    print(f"\n✅ CORRECCIÓN FINALIZADA EN {tiempo_total:.1f} MINUTOS.")
    print("Tu archivo maestro ahora contiene la topología esférica satelital exacta de NREL.")

if __name__ == "__main__":
    corregir_alineacion_masiva()