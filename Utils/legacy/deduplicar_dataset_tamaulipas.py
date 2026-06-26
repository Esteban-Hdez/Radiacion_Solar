"""
Deduplicación ORGANIZADA del dataset de Tamaulipas (no destructiva).

Con las coordenadas confirmadas por la API, 439 de los 4940 nodos son duplicados
(caen en la misma celda real NSRDB). Este script construye un dataset limpio con
los 4501 nodos canónicos, **reindexados de forma continua (0…4500)** tanto en el
nombre del archivo como en la columna interna `nodo_id`, y genera una metadata
continua que coincide 1:1 con los parquet.

NO elimina ni modifica nada del folder original: copia los canónicos a un folder
nuevo. El folder `Tamaulipas_2017_V4_Completo/` queda como archivo completo (4940).

Entradas:
  - Data/Geometria/metadata_nodos_tamaulipas_dedup.csv   (con es_duplicado / celda_id)
  - Data/API_Historico/Tamaulipas_2017_V4_Completo/      (4940 parquet originales)

Salidas:
  - Data/API_Historico/Tamaulipas_2017_V4_Dedup/         (4501 parquet reindexados)
  - Data/Geometria/metadata_nodos_tamaulipas_dedup_final.csv  (índice continuo)
"""

import os
import pandas as pd

DEDUP_META = 'Data/Geometria/metadata_nodos_tamaulipas_dedup.csv'
SRC_DIR = 'Data/API_Historico/Tamaulipas_2017_V4_Completo'
DST_DIR = 'Data/API_Historico/Tamaulipas_2017_V4_Dedup'
NEW_META = 'Data/Geometria/metadata_nodos_tamaulipas_dedup_final.csv'
ANIO = '2017'


def main():
    meta = pd.read_csv(DEDUP_META)

    # Canónicos = no duplicados, ordenados por nodo_id original -> índice continuo
    canon = meta[~meta['es_duplicado']].sort_values('nodo_id').reset_index(drop=True)
    canon['nodo_id_nuevo'] = range(len(canon))
    os.makedirs(DST_DIR, exist_ok=True)

    print(f"Nodos canónicos a reindexar: {len(canon)}  (de {len(meta)} totales)")
    print(f"Duplicados omitidos:         {int(meta['es_duplicado'].sum())}")
    print(f"Origen:  {SRC_DIR}")
    print(f"Destino: {DST_DIR}\n")

    copiados, ya_estaban, faltantes = 0, 0, []
    for _, row in canon.iterrows():
        orig = int(row['nodo_id'])
        nuevo = int(row['nodo_id_nuevo'])
        src = os.path.join(SRC_DIR, f'nodo_{orig}_{ANIO}_v4.parquet')
        dst = os.path.join(DST_DIR, f'nodo_{nuevo}_{ANIO}_v4.parquet')

        if not os.path.exists(src):
            faltantes.append(orig)
            continue
        if os.path.exists(dst):           # idempotente / reanudable
            ya_estaban += 1
            continue

        df = pd.read_parquet(src)
        df['nodo_id'] = nuevo             # reindexar la llave espacial interna
        df.to_parquet(dst, engine='pyarrow', index=False)
        copiados += 1
        if copiados % 500 == 0:
            print(f"  ... {copiados} parquet escritos")

    # ---- Metadata continua que coincide con los parquet ----
    out = canon[['nodo_id_nuevo', 'nodo_id', 'lat_nrel', 'lon_nrel', 'msnm', 'celda_id']].copy()
    out = out.rename(columns={
        'nodo_id_nuevo': 'nodo_id',          # índice continuo 0..4500
        'nodo_id': 'nodo_id_original',       # trazabilidad al dataset crudo
        'lat_nrel': 'latitude',              # coordenadas reales confirmadas por API
        'lon_nrel': 'longitude',
    })
    out.to_csv(NEW_META, index=False)

    # ---- Verificación ----
    n_files = len([f for f in os.listdir(DST_DIR) if f.endswith('.parquet')])
    print("\n" + "=" * 60)
    print("✅ DEDUPLICACIÓN ORGANIZADA COMPLETA")
    print("=" * 60)
    print(f"Parquet escritos esta corrida: {copiados}  (ya existían: {ya_estaban})")
    print(f"Parquet en {os.path.basename(DST_DIR)}/: {n_files}  (esperados: {len(canon)})")
    print(f"Metadata continua: {NEW_META}  ({len(out)} filas)")
    if faltantes:
        print(f"⚠️  No se encontró el origen de {len(faltantes)} nodos: {faltantes[:20]}")
    else:
        print("Integridad: todos los canónicos tenían su parquet de origen.")
    print(f"Folder original intacto: {SRC_DIR} (4940 nodos, archivo completo)")


if __name__ == "__main__":
    main()
