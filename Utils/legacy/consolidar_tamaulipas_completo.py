"""
Dataset COMPLETO unificado de Tamaulipas 2017 (24 h, todas las variables),
optimizado para entrenar modelos.

Une los 4501 parquet deduplicados (índice continuo) en un único archivo con
ingeniería pensada para ML:
  - Índice temporal `datetime` (a la hora), filas ordenadas por [nodo_id, datetime].
  - dtypes compactos: int16 / int8 / float32 (en vez de int64 / float64).
  - Se elimina `minute` (constante = 30) por redundante.
  - Nombres de las columnas UV legibles.
  - Compresión zstd y escritura por lotes (memoria acotada).

Las coordenadas NO se incluyen aquí (se quedan normalizadas en
`Data/Tamaulipas/metadata_nodos_tamaulipas.csv`, year-agnostic). La llave de unión
es `nodo_id`.

Entrada: Data/Tamaulipas/2017/crudos_api/nodo_<0..4500>_2017_v4.parquet
Salida:  Data/Tamaulipas/2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet
"""

import time
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

SRC = 'Data/Tamaulipas/2017/crudos_api'
OUT = 'Data/Tamaulipas/2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet'
N_NODOS = 4501
LOTE = 50  # nodos por row-group (≈438k filas)

RENOMBRES = {
    'global_horizontal_uv_irradiance_(280-400nm)': 'ghi_uv_280_400',
    'global_horizontal_uv_irradiance_(295-385nm)': 'ghi_uv_295_385',
}
A_INT16 = ['nodo_id', 'year', 'ghi', 'dni', 'dhi', 'clearsky_ghi', 'clearsky_dni',
           'clearsky_dhi', 'pressure', 'wind_direction']
A_INT8 = ['month', 'day', 'hour', 'cloud_type', 'cloud_fill_flag', 'fill_flag']
A_FLOAT32 = ['temperature', 'dew_point', 'relative_humidity', 'solar_zenith_angle',
             'surface_albedo', 'aerosol_optical_depth', 'alpha', 'asymmetry', 'ssa',
             'ozone', 'precipitable_water', 'wind_speed', 'ghi_uv_280_400', 'ghi_uv_295_385']
ORDEN = ['nodo_id', 'datetime', 'year', 'month', 'day', 'hour',
         'ghi', 'dni', 'dhi', 'clearsky_ghi', 'clearsky_dni', 'clearsky_dhi', 'solar_zenith_angle',
         'cloud_type', 'cloud_fill_flag', 'fill_flag',
         'temperature', 'dew_point', 'relative_humidity', 'pressure', 'precipitable_water',
         'wind_speed', 'wind_direction',
         'surface_albedo', 'aerosol_optical_depth', 'alpha', 'asymmetry', 'ssa', 'ozone',
         'ghi_uv_280_400', 'ghi_uv_295_385']


def transformar(df):
    df = df.rename(columns=RENOMBRES)
    df['datetime'] = pd.to_datetime(df[['year', 'month', 'day', 'hour']])
    df = df.drop(columns=['minute'])
    for c in A_INT16:
        df[c] = df[c].astype('int16')
    for c in A_INT8:
        df[c] = df[c].astype('int8')
    for c in A_FLOAT32:
        df[c] = df[c].astype('float32')
    return df[ORDEN]


def main():
    t0 = time.time()
    writer = None
    total = 0
    buffer = []

    def flush():
        nonlocal writer
        if not buffer:
            return
        tabla = pa.Table.from_pandas(pd.concat(buffer, ignore_index=True),
                                     preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(OUT, tabla.schema,
                                      compression='zstd', compression_level=5)
        writer.write_table(tabla)
        buffer.clear()

    for i in range(N_NODOS):
        df = transformar(pd.read_parquet(f'{SRC}/nodo_{i}_2017_v4.parquet'))
        buffer.append(df)
        total += len(df)
        if len(buffer) >= LOTE:
            flush()
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{N_NODOS} nodos  ({total:,} filas)")
    flush()
    if writer is not None:
        writer.close()

    print("\n" + "=" * 60)
    print("✅ DATASET COMPLETO TAMAULIPAS 2017 GENERADO")
    print("=" * 60)
    esp = N_NODOS * 8760
    print(f"Filas: {total:,}  (esperadas {esp:,}: {'OK' if total == esp else '⚠️'})")
    print(f"Tiempo: {time.time() - t0:.1f} s")
    print(f"Salida: {OUT}")


if __name__ == "__main__":
    main()
