"""
Funciones comunes del pipeline ANUAL de Tamaulipas (descarga NSRDB v4).

Todas las descargas usan las **coordenadas reales finales** de los 4384 nodos
sobre tierra (`Data/Tamaulipas/metadata_nodos_tamaulipas.csv`), ya confirmadas por
la API. Como son centros de celda de la rejilla 0.04°, consultar `POINT(lon lat)`
devuelve exactamente esa celda en cualquier año (sin desfase).
"""

import os
import io
import re
import calendar
import requests
import pandas as pd
from dotenv import load_dotenv

URL_BASE = "https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv"
METADATA = 'Data/Tamaulipas/metadata_nodos_tamaulipas.csv'

# Campos de la cabecera de NSRDB que CAMBIAN por nodo (el resto es constante:
# unidades, diccionarios de cloud_type/fill_flag, husos, versión — ver
# Data/Tamaulipas/REFERENCIA_NSRDB.md).
VARIABLES_POR_NODO = ['location_id', 'latitude', 'longitude', 'elevation']


def cargar_credenciales():
    load_dotenv()
    api_key, email = os.getenv('API_KEY'), os.getenv('EMAIL_USUARIO')
    if not api_key:
        raise RuntimeError("No se detectó API_KEY en el .env")
    return api_key, email


def horas_anio(anio, leap_day=True):
    """Horas esperadas en el año: 8784 si es bisiesto y se incluye el 29-feb; si no, 8760."""
    return 8784 if (leap_day and calendar.isleap(anio)) else 8760


def cargar_coordenadas_finales(metadata=METADATA):
    """Coordenadas reales por nodo (lat, lon) desde la metadata de la región."""
    df = pd.read_csv(metadata, usecols=['nodo_id', 'latitude', 'longitude'])
    return df.set_index('nodo_id')[['latitude', 'longitude']]


def guardar_metadata(ruta_meta, meta_filas, cols=None):
    """Escribe el CSV de metadatos por año, ordenado por `nodo_id`.

    `meta_filas` es un dict {nodo_id: fila_dict}. Si se pasa `cols` (el orden de
    columnas de un CSV ya existente) se respeta ese orden y se añaden al final las
    columnas nuevas que pudieran aparecer. Devuelve el nº de filas escritas.
    """
    if not meta_filas:
        return 0
    dfm = pd.DataFrame(list(meta_filas.values()))
    if cols is None:
        cols = ['nodo_id'] + [c for c in dfm.columns if c != 'nodo_id']
    else:
        cols = list(cols) + [c for c in dfm.columns if c not in cols]
    dfm = dfm.reindex(columns=cols).sort_values('nodo_id')
    dfm.to_csv(ruta_meta, index=False)
    return len(dfm)


def rutas_anio(anio, raiz='Data/Tamaulipas'):
    """Devuelve (base, crudos_dir, log) para un año dado, bajo `raiz` (región)."""
    base = f'{raiz}/{anio}'
    crudos = f'{base}/crudos_api'
    log = f'{crudos}/nodos_completados_{anio}.log'
    return base, crudos, log


def ids_presentes(crudos_dir):
    """Conjunto de nodo_id ya descargados (según los archivos en disco)."""
    ids = set()
    if not os.path.isdir(crudos_dir):
        return ids
    for f in os.listdir(crudos_dir):
        m = re.search(r'nodo_(\d+)_', f)
        if m and f.endswith('.parquet'):
            ids.add(int(m.group(1)))
    return ids


def descargar_nodo(nodo_id, lat, lon, anio, crudos_dir, api_key, email,
                   meta_modo=None, timeout=60, leap_day=True):
    """
    Descarga un nodo para un año y guarda su parquet.

    Parameters
    ----------
    meta_modo : {None, 'todos', 'cambian'}
        None      -> no captura metadatos.
        'todos'   -> captura toda la cabecera de NSRDB (47 campos).
        'cambian' -> solo los campos que varían por nodo (location_id, lat, lon, elevation).

    Returns
    -------
    (estado, meta) : estado en {'EXITO','LIMITE','ERROR'}; meta es un dict (o None).
    """
    params = {
        'api_key': api_key, 'email': email,
        'wkt': f"POINT({lon} {lat})", 'names': str(anio),
        'interval': '60', 'utc': 'true',
        'leap_day': 'true' if leap_day else 'false',
    }
    try:
        r = requests.get(URL_BASE, params=params, timeout=timeout)
        if r.status_code == 429:
            return 'LIMITE', None
        r.raise_for_status()

        meta = None
        if meta_modo:
            cab = pd.read_csv(io.StringIO(r.text), nrows=1)
            todos = {}
            for c in cab.columns:
                if str(c).startswith('Unnamed'):
                    continue
                clave = str(c).strip().lower().replace(' ', '_').replace('-', '_')
                todos[clave] = cab[c].iloc[0]
            meta = {'nodo_id': nodo_id}
            if meta_modo == 'cambian':
                meta.update({k: todos[k] for k in VARIABLES_POR_NODO if k in todos})
            else:  # 'todos'
                meta.update(todos)

        df = pd.read_csv(io.StringIO(r.text), skiprows=2)
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        df.insert(0, 'nodo_id', nodo_id)          # índice final (0..4383)
        df.to_parquet(f'{crudos_dir}/nodo_{nodo_id}_{anio}_v4.parquet',
                      engine='pyarrow', index=False)
        return 'EXITO', meta
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR red nodo {nodo_id}] {e}")
        return 'ERROR', None
