"""
Filtra los nodos sobre agua de Tamaulipas y reindexa el dataset (no destructivo).

Quita los nodos listados en `nodos_a_eliminar.csv` (mar / laguna / isla), reindexa
de forma CONTINUA los que quedan (0..N-1) -tanto en el nombre del parquet como en
su columna interna `nodo_id`- y regenera los finales con los MISMOS nombres en
`Data/Tamaulipas/`.

La versión completa anterior (con los nodos de mar) ya fue movida a
`Data/Tamaulipas/historico_4501_con_mar/`, de donde este script lee. Nada se borra:
el histórico conserva los 4501 nodos y la metadata para reincluirlos en el futuro.

Salidas (en Data/Tamaulipas/):
  - metadata_nodos_tamaulipas.csv                          (4384, índice continuo)
  - 2017/crudos_api/nodo_<0..N-1>_2017_v4.parquet          (reindexados)
  - 2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet
"""

import os
import time
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Reutilizamos la ingeniería (datetime, dtypes compactos, orden de columnas)
from Utils.legacy.consolidar_tamaulipas_completo import transformar

HIST = 'Data/Tamaulipas/historico_4501_con_mar'
META_HIST = f'{HIST}/metadata_nodos_tamaulipas.csv'
ELIMINAR = f'{HIST}/nodos_a_eliminar.csv'
SRC_CRUDOS = f'{HIST}/2017/crudos_api'

META_OUT = 'Data/Tamaulipas/metadata_nodos_tamaulipas.csv'
CRUDOS_OUT = 'Data/Tamaulipas/2017/crudos_api'
COMPLETO_OUT = 'Data/Tamaulipas/2017/Finales/completo/dataset_tamaulipas_completo_24h_2017.parquet'
ANIO = '2017'
LOTE = 50


def main():
    t0 = time.time()
    os.makedirs(CRUDOS_OUT, exist_ok=True)
    os.makedirs(os.path.dirname(COMPLETO_OUT), exist_ok=True)

    meta = pd.read_csv(META_HIST)
    elim = set(pd.read_csv(ELIMINAR)['nodo_id'])

    # Nodos que se conservan -> índice continuo nuevo
    kept = meta[~meta['nodo_id'].isin(elim)].sort_values('nodo_id').reset_index(drop=True)
    kept['nodo_id_nuevo'] = range(len(kept))
    print(f"Nodos originales: {len(meta)} | eliminados: {len(elim)} | conservados: {len(kept)}")

    # --- Metadata nueva (índice continuo) con trazabilidad ---
    out_meta = pd.DataFrame({
        'nodo_id': kept['nodo_id_nuevo'],            # 0..N-1 (coincide con los parquet)
        'nodo_id_4501': kept['nodo_id'],             # índice de la versión con mar
        'nodo_id_original': kept['nodo_id_original'],  # índice de la malla cruda de 4940
        'latitude': kept['latitude'],
        'longitude': kept['longitude'],
        'msnm': kept['msnm'],
        'celda_id': kept['celda_id'],
    })
    out_meta.to_csv(META_OUT, index=False)

    # --- Reindexar crudos + consolidar el COMPLETO en una pasada ---
    writer, buffer = None, []

    def flush():
        nonlocal writer
        if not buffer:
            return
        tabla = pa.Table.from_pandas(pd.concat(buffer, ignore_index=True), preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(COMPLETO_OUT, tabla.schema,
                                      compression='zstd', compression_level=5)
        writer.write_table(tabla)
        buffer.clear()

    print("Reindexando crudos y consolidando...")
    for _, row in kept.iterrows():
        viejo, nuevo = int(row['nodo_id']), int(row['nodo_id_nuevo'])
        df = pd.read_parquet(f'{SRC_CRUDOS}/nodo_{viejo}_{ANIO}_v4.parquet')
        df['nodo_id'] = nuevo
        df.to_parquet(f'{CRUDOS_OUT}/nodo_{nuevo}_{ANIO}_v4.parquet', engine='pyarrow', index=False)
        buffer.append(transformar(df))
        if len(buffer) >= LOTE:
            flush()
        if (nuevo + 1) % 500 == 0:
            print(f"  {nuevo + 1}/{len(kept)} nodos")
    flush()
    if writer is not None:
        writer.close()

    # --- Verificación ---
    n_crudos = len([f for f in os.listdir(CRUDOS_OUT) if f.endswith('.parquet')])
    filas = pq.ParquetFile(COMPLETO_OUT).metadata.num_rows
    print("\n" + "=" * 60)
    print("✅ FILTRADO Y REINDEXADO COMPLETO")
    print("=" * 60)
    print(f"Metadata:  {META_OUT}  ({len(out_meta)} nodos)")
    print(f"Crudos:    {CRUDOS_OUT}  ({n_crudos} parquet)")
    print(f"Completo:  {COMPLETO_OUT}  ({filas:,} filas, esperadas {len(kept) * 8760:,})")
    print(f"Histórico (4501) intacto en: {HIST}")
    print(f"Tiempo: {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
