import os
import io
import time
import requests
import numpy as np
import pandas as pd
import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point
import matplotlib.pyplot as plt
from dotenv import load_dotenv

def generar_malla_calibrada():
    print("=== PIPELINE DE GEOPROCESAMIENTO CALIBRADO: NSRDB V4 (TAMAULIPAS) ===")
    inicio = time.time()
    
    # Configuración de API
    load_dotenv()
    API_KEY = os.getenv('API_KEY')
    EMAIL_USUARIO = os.getenv('EMAIL_USUARIO')
    
    RESOLUCION_GRADOS = 0.038
    dir_salida = 'Data/Geometria'
    ruta_csv = os.path.join(dir_salida, 'metadata_nodos_tamaulipas.csv')
    ruta_png = os.path.join(dir_salida, 'validacion_malla_tamaulipas.png')
    os.makedirs(dir_salida, exist_ok=True)

    if not API_KEY:
        print("❌ Error: Verifica tu archivo .env, no se detectó API_KEY.")
        return

    # =====================================================================
    # FASE 1: Frontera Territorial y Centroide
    # =====================================================================
    print("\n[Fase 1] Descargando frontera oficial de Tamaulipas (OpenStreetMap)...")
    gdf_tamaulipas = ox.geocode_to_gdf("Tamaulipas, Mexico")
    geometria_estado = gdf_tamaulipas.unary_union
    
    # Calculamos el centro geográfico aproximado para nuestro disparo de prueba
    centroide = geometria_estado.centroid
    lon_centro, lat_centro = centroide.x, centroide.y

    # =====================================================================
    # FASE 2: El Disparo de Calibración (Anchor Point)
    # =====================================================================
    print(f"\n[Fase 2] Realizando disparo de calibración a la API de NREL...")
    print(f"         Coordenada de prueba (Centroide): Lat {lat_centro:.4f}, Lon {lon_centro:.4f}")
    
    url_base = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"
    parametros = {
        'api_key': API_KEY,
        'email': EMAIL_USUARIO,
        'wkt': f'POINT({lon_centro} {lat_centro})',
        'names': '2017', 
        'interval': '60',       
        'utc': 'true',
        'leap_day': 'false'
    }

    response = requests.get(url_base, params=parametros, timeout=45)
    
    if response.status_code != 200:
        print(f"❌ Error HTTP {response.status_code} al calibrar: {response.text}")
        return
        
    # Extraemos SOLO la línea de metadatos (ignorar los miles de registros climáticos por ahora)
    df_meta_api = pd.read_csv(io.StringIO(response.text), nrows=1)
    
    # Rescatamos las coordenadas exactas de la cuadrícula satelital
    lat_ancla = float(df_meta_api['Latitude'].iloc[0])
    lon_ancla = float(df_meta_api['Longitude'].iloc[0])
    
    print(f"✅ Calibración exitosa.")
    print(f"         Punto Ancla Real (Satélite): Lat {lat_ancla}, Lon {lon_ancla}")

    # =====================================================================
    # FASE 3: Expansión Matemática Bidireccional
    # =====================================================================
    print("\n[Fase 3] Calculando Bounding Box y expandiendo matriz matemáticamente...")
    minx, miny, maxx, maxy = geometria_estado.bounds
    
    # Calculamos cuántos "saltos" de 0.038 grados caben hacia cada dirección desde el ancla
    n_oeste = int(np.floor((minx - lon_ancla) / RESOLUCION_GRADOS))
    n_este  = int(np.ceil((maxx - lon_ancla) / RESOLUCION_GRADOS))
    
    n_sur   = int(np.floor((miny - lat_ancla) / RESOLUCION_GRADOS))
    n_norte = int(np.ceil((maxy - lat_ancla) / RESOLUCION_GRADOS))
    
    # Generamos los vectores perfectos anclados a la malla real
    x_coords = lon_ancla + (np.arange(n_oeste, n_este + 1) * RESOLUCION_GRADOS)
    y_coords = lat_ancla + (np.arange(n_sur, n_norte + 1) * RESOLUCION_GRADOS)
    
    xx, yy = np.meshgrid(x_coords, y_coords)
    puntos_totales = [Point(x, y) for x, y in zip(xx.flatten(), yy.flatten())]
    gdf_puntos = gpd.GeoDataFrame(geometry=puntos_totales, crs="EPSG:4326")
    
    print(f"         -> Puntos generados en el rectángulo calibrado: {len(gdf_puntos)}")

    # =====================================================================
    # FASE 4: Intersección Espacial (Point-in-Polygon)
    # =====================================================================
    print("\n[Fase 4] Ejecutando recorte espacial (Point-in-Polygon)...")
    gdf_nodos = gdf_puntos[gdf_puntos.geometry.within(geometria_estado)].copy()
    
    gdf_nodos.insert(0, 'nodo_id', range(len(gdf_nodos)))
    gdf_nodos['latitude'] = gdf_nodos.geometry.y
    gdf_nodos['longitude'] = gdf_nodos.geometry.x
    
    total_nodos = len(gdf_nodos)
    print(f"         -> Nodos finales calibrados para Tamaulipas: {total_nodos}")

    # =====================================================================
    # FASE 5: Exportación y Verificación Visual
    # =====================================================================
    print("\n[Fase 5] Exportando metadatos y gráfico de validación...")
    
    df_exportar = gdf_nodos[['nodo_id', 'latitude', 'longitude']]
    df_exportar.to_csv(ruta_csv, index=False)
    
    fig, ax = plt.subplots(figsize=(10, 10), dpi=200)
    gdf_tamaulipas.plot(ax=ax, facecolor='lightblue', edgecolor='blue', alpha=0.5)
    gdf_nodos.plot(ax=ax, color='red', markersize=2, alpha=0.8)
    
    plt.title(f"Malla Espacial V4 Calibrada - Tamaulipas ({total_nodos} Nodos)", fontsize=14, fontweight='bold')
    plt.xlabel("Longitud")
    plt.ylabel("Latitud")
    plt.grid(True, linestyle='--', alpha=0.3)
    
    plt.savefig(ruta_png, bbox_inches='tight')
    plt.close()
    
    tiempo_total = time.time() - inicio
    print(f"\n✅ Pipeline completado en {tiempo_total:.2f} segundos.")
    print(f"📁 Coordenadas exactas en: {ruta_csv}")
    print(f"🗺️ Mapa de validación en:  {ruta_png}")

if __name__ == "__main__":
    generar_malla_calibrada()