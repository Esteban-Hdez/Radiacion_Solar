"""
Reconstrucción matemática de las coordenadas reales NSRDB v4 (GOES aggregated).

Contexto
--------
La malla de Tamaulipas se generó con paso 0.038°, pero la rejilla real de NSRDB v4
es de 0.04°. Por eso las coordenadas solicitadas no coinciden con las que devuelve
el satélite ("desfasamiento") y, al ser la malla más densa que la rejilla real,
varios nodos distintos caen en la MISMA celda satelital (duplicados).

El "snapping" de NSRDB es determinista: redondea cada punto al nodo más cercano de
una rejilla regular. El modelo quedó CERTIFICADO contra 600 nodos reales (600/600
exactos), incluyendo los casos de frontera de celda:

    paso (d)      = 0.04°
    offset lat    = 0.01°   -> rejilla lat: ..., 22.37, 22.41, 22.45, ...
    offset lon    = 0.02°   -> rejilla lon: ..., -99.06, -99.02, -98.98, ...
    empates (.5)  = round half AWAY FROM ZERO  (lat -> norte, lon -> oeste)

Con eso se calculan las coordenadas reales de los 4940 nodos SIN consultar la API,
y la misma regla sirve para cualquier año que se descargue después.

NO modifica el archivo original. Escribe un CSV NUEVO con:
    lat_local / lon_local : coordenadas originales solicitadas (intactas)
    lat_real  / lon_real  : coordenadas reales del satélite (calculadas)
    celda_id              : id canónico de la celda real (mismo id = misma celda)
    es_duplicado          : True si otro nodo con id menor ya cubre esa celda
"""

import os
import numpy as np
import pandas as pd

# --- Parámetros certificados de la rejilla NSRDB v4 ---
PASO = 0.04
OFFSET_LAT = 0.01
OFFSET_LON = 0.02

RUTA_ENTRADA = 'Data/Geometria/metadata_nodos_tamaulipas_final.csv'
RUTA_SALIDA = 'Data/Geometria/metadata_nodos_tamaulipas_reconstruido.csv'


def snap_a_rejilla(valores, offset, paso=PASO):
    """Redondea al nodo de rejilla más cercano (empates alejándose de cero)."""
    t = (np.asarray(valores, dtype=float) - offset) / paso
    n = np.sign(t) * np.floor(np.abs(t) + 0.5)
    return np.round(n * paso + offset, 4)


def reconstruir():
    if not os.path.exists(RUTA_ENTRADA):
        print(f"❌ No se encontró {RUTA_ENTRADA}")
        return

    df = pd.read_csv(RUTA_ENTRADA)

    # Coordenadas solicitadas originales (las que se usaron para descargar)
    if 'lat_local' in df.columns:
        lat_sol, lon_sol = df['lat_local'].values, df['lon_local'].values
    else:
        lat_sol, lon_sol = df['latitude'].values, df['longitude'].values

    # 1. Calcular coordenadas reales de todos los nodos
    rlat = snap_a_rejilla(lat_sol, OFFSET_LAT)
    rlon = snap_a_rejilla(lon_sol, OFFSET_LON)

    # 2. Auto-validación contra los nodos ya verificados por la API (si existen)
    if 'corregido' in df.columns and (df['corregido'] == True).any():
        ya = df[df['corregido'] == True]
        col_lat = 'lat_local' if 'lat_local' in df.columns else 'latitude'
        col_lon = 'lon_local' if 'lon_local' in df.columns else 'longitude'
        pred_lat = snap_a_rejilla(ya[col_lat].values, OFFSET_LAT)
        pred_lon = snap_a_rejilla(ya[col_lon].values, OFFSET_LON)
        ok = int(np.sum((np.abs(pred_lat - ya['lat_nrel'].values) < 1e-6) &
                        (np.abs(pred_lon - ya['lon_nrel'].values) < 1e-6)))
        print(f"Validación contra API: {ok}/{len(ya)} exactas "
              f"({100 * ok / len(ya):.2f}%)")
        if ok != len(ya):
            print("⚠️  El modelo NO reproduce todos los nodos verificados. "
                  "Abortando para no generar datos dudosos.")
            return

    # 3. Construir tabla de salida (nueva, sin tocar el original)
    out = pd.DataFrame({
        'nodo_id': df['nodo_id'].values,
        'lat_local': lat_sol,
        'lon_local': lon_sol,
        'lat_real': rlat,
        'lon_real': rlon,
    })
    if 'msnm' in df.columns:
        out['msnm'] = df['msnm'].values

    out = out.sort_values('nodo_id').reset_index(drop=True)
    out['celda_id'] = out.groupby(['lat_real', 'lon_real']).ngroup()
    out['es_duplicado'] = out.duplicated(subset=['lat_real', 'lon_real'],
                                         keep='first')

    out.to_csv(RUTA_SALIDA, index=False)

    n = len(out)
    celdas = out['celda_id'].nunique()
    dups = int(out['es_duplicado'].sum())
    print(f"\n✅ Reconstrucción completada (0 consultas a la API)")
    print(f"   Nodos solicitados:       {n}")
    print(f"   Celdas reales distintas: {celdas}")
    print(f"   Nodos duplicados:        {dups} ({100 * dups / n:.1f}%)")
    print(f"   Desfase medio aplicado:  "
          f"lat {np.abs(out.lat_real - out.lat_local).mean():.4f}°, "
          f"lon {np.abs(out.lon_real - out.lon_local).mean():.4f}°")
    print(f"\n📁 Archivo NUEVO: {RUTA_SALIDA}")
    print(f"   Original intacto: {RUTA_ENTRADA}")


if __name__ == "__main__":
    reconstruir()
