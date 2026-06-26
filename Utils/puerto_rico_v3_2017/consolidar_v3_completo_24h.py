"""
Dataset COMPLETO v3 de 24 horas (sin filtro diurno) con TODAS las variables.

A diferencia del FILTRADO `dataset_v3_filtrado_diurno_2017.parquet` (que es diurno,
porque `etl_solar.py` aplica el doble filtro astronómico antes de guardar), este script
reconstruye la base física horaria **sin filtrar** —reutilizando las MISMAS reglas
de agregación de `etl_solar` (promedio intrahorario, minuto-30 para el ángulo
cenital)— y la fusiona con el complemento meteorológico de la API (cloud_type,
relative_humidity), que ya es de 24 h.

Resultado: 2480 nodos × 8760 h = 21,724,800 filas, todas las variables, 24 h.

Salida: Data/Puerto_Rico_v3_2017/Finales/completo/dataset_v3_completo_24h_2017.parquet
"""

import os
import time
import h5py
import numpy as np
import pandas as pd

# Reutilizamos las reglas de agregación ya validadas del ETL v3
from Utils.puerto_rico_v3_2017.etl_solar import (
    obtener_ejes_espaciotemporales,
    leer_variable_cruda,
    calcular_metricas_horarias,
)

H5_PATH = 'Data/datos_nsrdb/nsrdb_puerto_rico_2017.h5'
API_CONSOLIDADA = 'Data/Puerto_Rico_v3_2017/intermedios/api_consolidada_2017.parquet'
RUTA_SALIDA = 'Data/Puerto_Rico_v3_2017/Finales/completo/dataset_v3_completo_24h_2017.parquet'

# Mismas variables y reglas que etl_solar (las que existen en el HDF5 de PR)
VARIABLES_PROMEDIO = ['ghi', 'dni', 'dhi', 'clearsky_ghi', 'air_temperature',
                      'surface_pressure', 'wind_speed', 'total_precipitable_water']


def construir_fisico_24h(h5_path):
    """Base física horaria de 24 h (sin filtro diurno), con reglas de etl_solar."""
    print("[1/3] Reconstruyendo base física horaria 24 h desde el HDF5...")
    datos = {}
    with h5py.File(h5_path, 'r') as f:
        time_index_1h, nodos_ids = obtener_ejes_espaciotemporales(f)
        n_horas, n_nodos = len(time_index_1h), len(nodos_ids)

        for var in VARIABLES_PROMEDIO:
            crudo = leer_variable_cruda(f, var)
            if crudo is not None:
                datos[var] = calcular_metricas_horarias(crudo, 'promedio')

        # El ángulo cenital se toma del minuto :30 (instante representativo)
        crudo_z = leer_variable_cruda(f, 'solar_zenith_angle')
        if crudo_z is not None:
            datos['solar_zenith_angle'] = calcular_metricas_horarias(crudo_z, 'minuto_30')

    # Ensamblaje en formato largo SIN aplicar el filtro diurno
    d = {
        'timestamp': pd.to_datetime(np.repeat(time_index_1h.values, n_nodos)),
        'nodo_id': np.tile(nodos_ids, n_horas),
    }
    for nombre, matriz in datos.items():
        d[nombre] = matriz.flatten()
    df = pd.DataFrame(d)

    # Llaves temporales para el cruce con la API
    df['year'] = df['timestamp'].dt.year.astype(np.int32)
    df['month'] = df['timestamp'].dt.month.astype(np.int32)
    df['day'] = df['timestamp'].dt.day.astype(np.int32)
    df['hour'] = df['timestamp'].dt.hour.astype(np.int32)
    print(f"      -> Física 24 h: {df.shape[0]:,} filas x {df.shape[1]} columnas")
    return df


def main():
    inicio = time.time()
    os.makedirs(os.path.dirname(RUTA_SALIDA), exist_ok=True)

    df_fisico = construir_fisico_24h(H5_PATH)

    print("[2/3] Cargando complemento meteorológico de la API (24 h)...")
    df_api = pd.read_parquet(API_CONSOLIDADA)
    for col in ['nodo_id', 'year', 'month', 'day', 'hour']:
        df_api[col] = df_api[col].astype(np.int32)
    # Conservamos la air_temperature del HDF5; descartamos la de la API
    if 'temperature' in df_api.columns:
        df_api.drop(columns=['temperature'], inplace=True)
    print(f"      -> API consolidada: {df_api.shape[0]:,} filas x {df_api.shape[1]} columnas")

    print("[3/3] Fusionando (inner, 24 h ⋈ 24 h) y guardando...")
    df = pd.merge(df_fisico, df_api, on=['nodo_id', 'year', 'month', 'day', 'hour'],
                  how='inner')
    df.sort_values(['nodo_id', 'timestamp'], inplace=True, ignore_index=True)
    df.to_parquet(RUTA_SALIDA, engine='pyarrow', index=False)

    filas_esperadas = 2480 * 8760
    print("\n" + "=" * 60)
    print("✅ DATASET v3 COMPLETO 24 H GENERADO")
    print("=" * 60)
    print(f"Filas:    {df.shape[0]:,}  (esperadas: {filas_esperadas:,})")
    print(f"Columnas: {df.shape[1]} -> {list(df.columns)}")
    print(f"Integridad: {'PERFECTA' if df.shape[0] == filas_esperadas else '⚠️ revisar'}")
    print(f"Tiempo: {time.time() - inicio:.1f} s")
    print(f"Salida: {RUTA_SALIDA}")


if __name__ == "__main__":
    main()
