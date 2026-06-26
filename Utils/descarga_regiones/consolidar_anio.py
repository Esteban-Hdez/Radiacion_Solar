"""
Consolida los crudos de un AÑO en el dataset COMPLETO unificado de Tamaulipas,
con la misma ingeniería para modelos que el resto del proyecto.

    python -m Utils.descarga_regiones.consolidar_anio --anio 2018

Lee  Data/Tamaulipas/<anio>/crudos_api/nodo_*_<anio>_v4.parquet
Crea Data/Tamaulipas/<anio>/Finales/completo/dataset_tamaulipas_completo_24h_<anio>.parquet
"""

import os
import re
import glob
import time
import argparse
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from Utils.descarga_regiones._comun import rutas_anio, horas_anio, METADATA

LOTE = 50
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
    """datetime + dtypes compactos + drop minute + nombres UV + orden de columnas."""
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


def main(anio, lote=LOTE, raiz='Data/Tamaulipas', tag='tamaulipas', metadata=METADATA,
         leap_day=True):
    base, crudos, _ = rutas_anio(anio, raiz)
    out_dir = f'{base}/Finales/completo'
    os.makedirs(out_dir, exist_ok=True)
    out = f'{out_dir}/dataset_{tag}_completo_24h_{anio}.parquet'

    files = glob.glob(f'{crudos}/nodo_*_{anio}_v4.parquet')
    if not files:
        print(f"❌ No hay crudos en {crudos}. Corre primero descargar_anio --anio {anio}")
        return
    files.sort(key=lambda p: int(re.search(r'nodo_(\d+)_', os.path.basename(p)).group(1)))
    n_esperado = len(pd.read_csv(metadata, usecols=['nodo_id']))

    print(f"=== CONSOLIDA {tag} {anio} ===")
    print(f"Crudos: {len(files)} (metadata final: {n_esperado} nodos)")
    if len(files) != n_esperado:
        print(f"⚠️  Faltan {n_esperado - len(files)} nodos. Corre parche_anio antes de consolidar.")

    t0 = time.time()
    writer, buffer, total = None, [], 0

    def flush():
        nonlocal writer
        if not buffer:
            return
        tabla = pa.Table.from_pandas(pd.concat(buffer, ignore_index=True), preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out, tabla.schema, compression='zstd', compression_level=5)
        writer.write_table(tabla)
        buffer.clear()

    for k, f in enumerate(files, 1):
        df = transformar(pd.read_parquet(f))
        buffer.append(df)
        total += len(df)
        if len(buffer) >= lote:
            flush()
        if k % 500 == 0:
            print(f"  {k}/{len(files)} nodos")
    flush()
    if writer is not None:
        writer.close()

    horas = horas_anio(anio, leap_day)
    print("\n" + "=" * 56)
    print("✅ COMPLETO GENERADO")
    print(f"Filas: {total:,} (esperadas {len(files) * horas:,}, {horas} h/nodo)")
    print(f"Tiempo: {time.time()-t0:.1f} s")
    print(f"Salida: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Consolida el dataset completo de un año (Tamaulipas).")
    ap.add_argument('--anio', type=int, required=True)
    ap.add_argument('--excluir-bisiesto', action='store_true',
                    help="El año se bajó sin 29-feb (ajusta el conteo esperado a 8760 h).")
    args = ap.parse_args()
    main(args.anio, leap_day=not args.excluir_bisiesto)
