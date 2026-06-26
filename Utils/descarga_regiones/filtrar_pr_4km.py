"""
Aplica la malla 4 km correcta a Puerto Rico sobre los datos YA descargados de un AÑO.

  1. Verifica que los nodos que comparten celda (location_id) tengan datos idénticos.
  2. Mueve la metadata original (2480 nodos, 0.02°) al histórico y la reemplaza por
     la malla 4 km (754 celdas, 0.04°).
  3. Filtra los crudos: conserva 1 nodo por celda real, los reindexa 0..N-1 (nombre
     de archivo + columna `nodo_id`) y ELIMINA los duplicados.
  4. Reindexa metadata_nodos_<anio>.csv a las mismas celdas (respaldando el original).
  5. Regenera el dataset completo consolidado.

No re-descarga nada: los duplicados eliminados son copias exactas del mismo
location_id. Paso provisional mientras se re-descarga el año con el 29-feb.

    python -m Utils.descarga_regiones.filtrar_pr_4km --anio 2024
"""

import os
import shutil
import argparse
import pandas as pd

from Utils.descarga_regiones import consolidar_anio

RAIZ = 'Data/Puerto_Rico'
MALLA = f'{RAIZ}/malla_4km_propuesta/metadata_nodos_pr_4km.csv'
MAPEO = f'{RAIZ}/malla_4km_propuesta/mapeo_pr_4km.csv'
META_OFICIAL = f'{RAIZ}/metadata_nodos_pr.csv'
HIST = f'{RAIZ}/historico_2480_0.02'


def _verificar_identicos(crudos, anio, mapeo, n_grupos=8):
    """Comprueba en una muestra que los nodos de una misma celda son datos idénticos."""
    multi = mapeo.groupby('nodo_id_nuevo')['nodo_id_viejo'].apply(list)
    multi = multi[multi.apply(len) > 1]
    revisados = 0
    for new_id, viejos in multi.items():
        base = pd.read_parquet(f'{crudos}/nodo_{viejos[0]}_{anio}_v4.parquet').drop(columns=['nodo_id'])
        for v in viejos[1:]:
            otro = pd.read_parquet(f'{crudos}/nodo_{v}_{anio}_v4.parquet').drop(columns=['nodo_id'])
            if not base.equals(otro):
                raise AssertionError(
                    f"Celda nueva {new_id}: nodos viejos {viejos[0]} y {v} NO son idénticos.")
        revisados += 1
        if revisados >= n_grupos:
            break
    print(f"  ✔ Verificados {revisados} grupos de duplicados: datos idénticos.")


def main(anio):
    malla = pd.read_csv(MALLA)
    mapeo = pd.read_csv(MAPEO)
    crudos = f'{RAIZ}/{anio}/crudos_api'

    # new_id -> old_id representante (el menor) y diccionario inverso old->new
    rep = mapeo.groupby('nodo_id_nuevo')['nodo_id_viejo'].min()
    old2new = {int(o): int(n) for o, n in zip(mapeo['nodo_id_viejo'], mapeo['nodo_id_nuevo'])}
    n = len(malla)
    assert len(rep) == n, f"rep={len(rep)} != malla={n}"
    print(f"=== FILTRAR PR 4 km · {anio} ===")
    print(f"Celdas a conservar: {n} | nodos viejos: {len(mapeo)} | a eliminar: {len(mapeo) - n}")

    # 1) Seguridad: duplicados idénticos ANTES de tocar nada.
    print("Verificando que los duplicados sean idénticos...")
    _verificar_identicos(crudos, anio, mapeo)

    os.makedirs(HIST, exist_ok=True)

    # 2) Metadata oficial: original -> histórico, escribir la de 4 km.
    if os.path.exists(META_OFICIAL):
        shutil.move(META_OFICIAL, f'{HIST}/metadata_nodos_pr.csv')
        print(f"📦 Original -> {HIST}/metadata_nodos_pr.csv")
    malla[['nodo_id', 'latitude', 'longitude', 'msnm']].to_csv(META_OFICIAL, index=False)
    print(f"📄 Nueva metadata oficial ({n} celdas): {META_OFICIAL}")

    # 3) Crudos: reconstruir filtrado+reindexado en tmp y hacer swap.
    tmp = f'{crudos}_4km_tmp'
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)
    for new_id, old_id in rep.items():
        df = pd.read_parquet(f'{crudos}/nodo_{old_id}_{anio}_v4.parquet')
        df['nodo_id'] = int(new_id)
        df.to_parquet(f'{tmp}/nodo_{new_id}_{anio}_v4.parquet', engine='pyarrow', index=False)
    shutil.rmtree(crudos)
    os.rename(tmp, crudos)
    with open(f'{crudos}/nodos_completados_{anio}.log', 'w') as f:
        f.write('\n'.join(str(i) for i in range(n)) + '\n')
    print(f"🧹 Crudos filtrados y reindexados: {n} archivos en {crudos}")

    # 4) metadata_nodos_<anio>.csv: respaldo + filtrar + reindexar.
    ruta_meta_anio = f'{RAIZ}/{anio}/metadata_nodos_{anio}.csv'
    if os.path.exists(ruta_meta_anio):
        shutil.copy(ruta_meta_anio, f'{HIST}/metadata_nodos_{anio}.csv')
        ma = pd.read_csv(ruta_meta_anio)
        ma = ma[ma['nodo_id'].isin(rep.values)].copy()
        ma['nodo_id'] = ma['nodo_id'].map(old2new)
        ma.sort_values('nodo_id').to_csv(ruta_meta_anio, index=False)
        print(f"📄 metadata_nodos_{anio}.csv reindexada ({len(ma)} celdas)")

    # 5) Consolidar (datos sin 29-feb => 8760 h).
    print("\nConsolidando dataset completo...")
    consolidar_anio.main(anio, raiz=RAIZ, tag='pr', metadata=META_OFICIAL, leap_day=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Filtra PR a la malla 4 km sobre datos ya descargados.")
    ap.add_argument('--anio', type=int, required=True)
    args = ap.parse_args()
    main(args.anio)
