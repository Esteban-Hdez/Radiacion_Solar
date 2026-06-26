"""
Recupera la metadata (cabecera NSRDB) de nodos que YA tienen su parquet crudo
descargado pero que NO quedaron en metadata_nodos_<anio>.csv.

Caso típico: nodos recuperados por un PARCHE antiguo que no guardaba metadatos.
Re-consulta la API solo para esos nodos, fusiona con el CSV existente, reordena
por nodo_id y reescribe el CSV (también reescribe el parquet, idéntico).

    # Tamaulipas (por defecto): recupera los que falten en el CSV
    python -m Utils.descarga_regiones.recuperar_metadata --anio 2024

    # Otra región / ids concretos
    python -m Utils.descarga_regiones.recuperar_metadata --anio 2024 \
        --metadata Data/Puerto_Rico/metadata_nodos_pr.csv --raiz Data/Puerto_Rico
    python -m Utils.descarga_regiones.recuperar_metadata --anio 2024 --ids 308 309 312
"""

import os
import time
import argparse
import pandas as pd

from Utils.descarga_regiones._comun import (
    cargar_credenciales, cargar_coordenadas_finales, rutas_anio, descargar_nodo,
    ids_presentes, guardar_metadata, METADATA)


def main(anio, ids=None, meta_modo='todos', pausa=1.0, metadata=METADATA,
         raiz='Data/Tamaulipas', leap_day=True):
    api_key, email = cargar_credenciales()
    coords = cargar_coordenadas_finales(metadata)
    base, crudos, log = rutas_anio(anio, raiz)
    ruta_meta = f'{base}/metadata_nodos_{anio}.csv'

    # Metadata existente (orden de columnas + filas ya guardadas).
    meta_filas, cols_meta = {}, None
    con_meta = set()
    if os.path.exists(ruta_meta):
        prev = pd.read_csv(ruta_meta)
        cols_meta = list(prev.columns)
        meta_filas = {int(r['nodo_id']): r.to_dict() for _, r in prev.iterrows()}
        con_meta = set(meta_filas)

    # Objetivos: ids dados, o los que tienen parquet pero no fila de metadata.
    if ids:
        objetivos = [n for n in ids if n in coords.index]
    else:
        presentes = ids_presentes(crudos)
        objetivos = sorted(presentes - con_meta)

    print(f"=== RECUPERAR METADATA {os.path.basename(raiz)} {anio} ===")
    print(f"CSV existente: {len(con_meta)} nodos | a recuperar: {len(objetivos)}")
    if not objetivos:
        print("✅ Nada que recuperar, la metadata está completa.")
        return {'limite': False, 'recuperados': 0}
    print(f"IDs: {objetivos}\n")

    tope, recuperados = False, 0
    for nodo_id in objetivos:
        lat = coords.loc[nodo_id, 'latitude']
        lon = coords.loc[nodo_id, 'longitude']
        estado, meta = descargar_nodo(nodo_id, lat, lon, anio, crudos, api_key, email,
                                      meta_modo=meta_modo, leap_day=leap_day)
        if estado == 'EXITO':
            if meta:
                meta_filas[nodo_id] = meta
                recuperados += 1
            # Asegura el checkpoint por si el parquet no estaba registrado.
            with open(log, 'a') as f:
                f.write(f"{nodo_id}\n")
            print(f"  ✅ {nodo_id}")
        elif estado == 'LIMITE':
            print("🛑 Límite diario de la API alcanzado. Progreso guardado.")
            tope = True
            break
        time.sleep(pausa)

    n = guardar_metadata(ruta_meta, meta_filas, cols_meta)
    print(f"\n📄 Metadata reescrita y ordenada: {ruta_meta} ({n} nodos, +{recuperados})")
    return {'limite': tope, 'recuperados': recuperados}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Recupera la metadata de nodos ya descargados sin fila en el CSV.")
    ap.add_argument('--anio', type=int, required=True)
    ap.add_argument('--ids', type=int, nargs='+', default=None,
                    help="Nodos concretos a recuperar (por defecto, los que falten en el CSV).")
    ap.add_argument('--meta-modo', choices=['todos', 'cambian'], default='todos',
                    help="Campos a capturar (def: 'todos', para casar con el CSV existente).")
    ap.add_argument('--pausa', type=float, default=1.0)
    ap.add_argument('--metadata', default=METADATA, help="CSV de coordenadas de la región.")
    ap.add_argument('--raiz', default='Data/Tamaulipas', help="Raíz de la región.")
    ap.add_argument('--excluir-bisiesto', action='store_true',
                    help="Excluye el 29-feb (debe coincidir con cómo se bajó el año).")
    args = ap.parse_args()
    main(args.anio, ids=args.ids, meta_modo=args.meta_modo, pausa=args.pausa,
         metadata=args.metadata, raiz=args.raiz, leap_day=not args.excluir_bisiesto)
