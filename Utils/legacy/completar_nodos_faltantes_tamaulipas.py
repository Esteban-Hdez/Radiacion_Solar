"""
Completa los nodos de Tamaulipas que quedaron SIN coordenada real de la API.

Tras correr `verificar_alineacion_espacial.py` algunos nodos fallaron por red y
quedaron con `lat_nrel == 0` / `lon_nrel == 0` en
`Data/Geometria/metadata_nodos_tamaulipas_final.csv`. Este script detecta esos
pendientes y les pide a la API NSRDB v4 únicamente la metadata (cabecera) para
recuperar su Latitude/Longitude reales, dejando las 4940 coordenadas 100%
confirmadas por la API.

Es idempotente y reanudable: solo procesa los que siguen en 0, y guarda tras
cada nodo. Petición ultraligera (stream + attributes=ghi, se leen 2 líneas).
"""

import os
import csv
import time
import requests
import pandas as pd
from dotenv import load_dotenv

RUTA_CSV = 'Data/Geometria/metadata_nodos_tamaulipas_final.csv'
URL_BASE = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"


def pedir_coordenada_real(lat_local, lon_local, api_key, email):
    """Devuelve (lat_nrel, lon_nrel, elevacion) leyendo solo la cabecera del CSV."""
    parametros = {
        'api_key': api_key,
        'email': email,
        'wkt': f"POINT({lon_local} {lat_local})",
        'names': '2017',
        'attributes': 'ghi',   # variable mínima válida para que la API responda
        'interval': '60',
        'utc': 'true',
        'leap_day': 'false',
    }
    response = requests.get(URL_BASE, params=parametros, stream=True, timeout=20)
    if response.status_code == 429:
        return 'LIMITE'
    response.raise_for_status()

    # Leer solo las 2 primeras líneas (headers + valores de la metadata)
    lineas = []
    for line in response.iter_lines():
        if line:
            lineas.append(line.decode('utf-8'))
        if len(lineas) == 2:
            break
    response.close()

    headers = next(csv.reader([lineas[0]]))
    valores = next(csv.reader([lineas[1]]))
    meta = dict(zip(headers, valores))
    elev = float(meta['Elevation']) if 'Elevation' in meta else None
    return float(meta['Latitude']), float(meta['Longitude']), elev


def main():
    load_dotenv()
    api_key = os.getenv('API_KEY')
    email = os.getenv('EMAIL_USUARIO')
    if not api_key:
        print("❌ No se detectó API_KEY en el .env")
        return

    df = pd.read_csv(RUTA_CSV)
    pend = df[(df['lat_nrel'] == 0) | (df['lon_nrel'] == 0)]
    print(f"Nodos pendientes (lat_nrel/lon_nrel == 0): {len(pend)}")
    if pend.empty:
        print("✅ No hay pendientes. Las 4940 coordenadas ya están confirmadas por la API.")
        return
    print(f"IDs: {pend['nodo_id'].tolist()}\n")

    completados = 0
    for idx, row in pend.iterrows():
        nodo_id = int(row['nodo_id'])
        lat_local, lon_local = row['lat_local'], row['lon_local']
        print(f"-> Nodo {nodo_id:04d}  POINT({lon_local} {lat_local})...", end=" ", flush=True)
        try:
            res = pedir_coordenada_real(lat_local, lon_local, api_key, email)
            if res == 'LIMITE':
                print("\n🛑 Límite diario de la API alcanzado. Progreso guardado.")
                break

            lat_nrel, lon_nrel, elev = res
            df.at[idx, 'lat_nrel'] = lat_nrel
            df.at[idx, 'lon_nrel'] = lon_nrel
            # Coordenadas oficiales = reales de la API (igual que el resto del archivo)
            df.at[idx, 'latitude'] = lat_nrel
            df.at[idx, 'longitude'] = lon_nrel
            if elev is not None and ('msnm' not in df.columns or pd.isna(row.get('msnm'))):
                df.at[idx, 'msnm'] = elev

            df.to_csv(RUTA_CSV, index=False)  # checkpoint tras cada nodo
            completados += 1
            print(f"✅ -> ({lat_nrel}, {lon_nrel})")
        except Exception as e:
            print(f"⚠️ falla: {e}")
        time.sleep(0.5)

    # Verificación final
    df = pd.read_csv(RUTA_CSV)
    restantes = int(((df['lat_nrel'] == 0) | (df['lon_nrel'] == 0)).sum())
    print(f"\nCompletados esta corrida: {completados}")
    print(f"Pendientes restantes:     {restantes}")
    if restantes == 0:
        print("🎉 Las 4940 coordenadas de Tamaulipas están 100% confirmadas por la API.")
    else:
        print("Vuelve a ejecutar el script para reintentar los que falten.")


if __name__ == "__main__":
    main()
