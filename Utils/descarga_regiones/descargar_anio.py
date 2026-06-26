"""
Descarga NSRDB v4 de Tamaulipas para un AÑO dado, sobre los 4384 nodos finales.

Ejecutar como módulo desde la raíz del proyecto:
    python -m Utils.descarga_regiones.descargar_anio --anio 2018
    python -m Utils.descarga_regiones.descargar_anio --anio 2018 --guardar-metadatos

Es reanudable (checkpoint por nodo) y respeta el límite diario de la API (429).
Crea la estructura Data/Tamaulipas/<anio>/crudos_api/ automáticamente.
"""

import os
import time
import argparse
import pandas as pd

from Utils.descarga_regiones._comun import (
    cargar_credenciales, cargar_coordenadas_finales, rutas_anio, descargar_nodo,
    guardar_metadata, METADATA)


def main(anio, metadatos=None, pausa=1.0, limite=None, metadata=METADATA,
         raiz='Data/Tamaulipas', leap_day=True):
    guardar_metadatos = metadatos is not None
    api_key, email = cargar_credenciales()
    coords = cargar_coordenadas_finales(metadata)
    base, crudos, log = rutas_anio(anio, raiz)
    os.makedirs(crudos, exist_ok=True)

    hechos = set()
    if os.path.exists(log):
        hechos = {int(x) for x in open(log).read().split()}
    pendientes = [n for n in coords.index if n not in hechos]
    if limite:
        pendientes = pendientes[:limite]  # prueba / descarga parcial
    print(f"=== DESCARGA {os.path.basename(raiz)} {anio} ===")
    print(f"Nodos totales: {len(coords)} | ya descargados: {len(hechos)} | pendientes: {len(pendientes)}")
    if not pendientes:
        print("✅ Año completo.")
        return {'limite': False, 'descargados': 0}

    # Metadatos por año (opcional). Acumula sobre lo ya guardado si se reanuda.
    ruta_meta = f'{base}/metadata_nodos_{anio}.csv'
    meta_filas, cols_meta = {}, None
    if guardar_metadatos and os.path.exists(ruta_meta):
        prev = pd.read_csv(ruta_meta)
        cols_meta = list(prev.columns)
        meta_filas = {int(r['nodo_id']): r.to_dict() for _, r in prev.iterrows()}

    inicio = time.time()
    tope_alcanzado, descargados = False, 0
    for i, nodo_id in enumerate(pendientes, 1):
        lat = coords.loc[nodo_id, 'latitude']
        lon = coords.loc[nodo_id, 'longitude']
        estado, meta = descargar_nodo(nodo_id, lat, lon, anio, crudos, api_key, email,
                                      meta_modo=metadatos, leap_day=leap_day)
        if estado == 'EXITO':
            with open(log, 'a') as f:
                f.write(f"{nodo_id}\n")
            descargados += 1
            if meta:
                meta_filas[nodo_id] = meta
            if i % 200 == 0:
                print(f"  {i}/{len(pendientes)} ({100*i/len(pendientes):.0f}%)")
        elif estado == 'LIMITE':
            print("🛑 Límite diario de la API (10000) alcanzado. Progreso guardado.")
            tope_alcanzado = True
            break
        time.sleep(pausa)

    if guardar_metadatos and meta_filas:
        n = guardar_metadata(ruta_meta, meta_filas, cols_meta)
        print(f"📄 Metadatos del año: {ruta_meta} ({n} nodos)")

    print(f"⏱️ {(time.time()-inicio)/60:.1f} min | descargados {descargados} | crudos en {crudos}")
    return {'limite': tope_alcanzado, 'descargados': descargados}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Descarga Tamaulipas NSRDB v4 para un año (4384 nodos finales).")
    ap.add_argument('--anio', type=int, required=True, help="Año a descargar, p.ej. 2018.")
    ap.add_argument('--metadatos', choices=['todos', 'cambian'], default=None,
                    help="Guarda Data/Tamaulipas/<anio>/metadata_nodos_<anio>.csv. "
                         "'todos' = toda la cabecera NSRDB (47 campos); "
                         "'cambian' = solo los que varían por nodo (location_id, lat, lon, elevation). "
                         "Por defecto no guarda nada.")
    ap.add_argument('--pausa', type=float, default=1.0, help="Segundos entre peticiones (def: 1.0).")
    ap.add_argument('--limite', type=int, default=None,
                    help="Descarga solo los primeros N nodos pendientes (para pruebas).")
    ap.add_argument('--excluir-bisiesto', action='store_true',
                    help="Excluye el 29-feb (años homogéneos de 8760 h). Por defecto se incluye.")
    args = ap.parse_args()
    main(args.anio, metadatos=args.metadatos, pausa=args.pausa, limite=args.limite,
         leap_day=not args.excluir_bisiesto)
