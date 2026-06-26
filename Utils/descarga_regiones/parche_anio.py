"""
Re-descarga los nodos faltantes de un AÑO (fallas de red) para Tamaulipas.

Escanea el disco, detecta qué nodos (de los 4384) faltan y los vuelve a pedir.
    python -m Utils.descarga_regiones.parche_anio --anio 2018
    python -m Utils.descarga_regiones.parche_anio --anio 2018 --metadatos todos
Correr después de `descargar_anio` y antes de `consolidar_anio`.

Si se pasa `--metadatos`, captura y FUSIONA la cabecera NSRDB de los nodos que
recupera en Data/<region>/<anio>/metadata_nodos_<anio>.csv (acumulando sobre lo
ya guardado y reordenando por nodo_id), igual que `descargar_anio`.
"""

import os
import time
import argparse
import pandas as pd

from Utils.descarga_regiones._comun import (
    cargar_credenciales, cargar_coordenadas_finales, rutas_anio, descargar_nodo,
    ids_presentes, guardar_metadata, METADATA)


def main(anio, pausa=1.0, metadata=METADATA, raiz='Data/Tamaulipas', metadatos=None,
         leap_day=True):
    guardar_metadatos = metadatos is not None
    api_key, email = cargar_credenciales()
    coords = cargar_coordenadas_finales(metadata)
    base, crudos, log = rutas_anio(anio, raiz)
    os.makedirs(crudos, exist_ok=True)

    presentes = ids_presentes(crudos)
    faltantes = [n for n in coords.index if n not in presentes]

    print(f"=== PARCHE {os.path.basename(raiz)} {anio} ===")
    print(f"En disco: {len(presentes)} | faltantes: {len(faltantes)}")
    if not faltantes:
        print("✅ 0 faltantes, el año está completo.")
        return {'limite': False, 'faltantes': 0}
    print(f"IDs a recuperar: {faltantes}\n")

    # Metadatos por año (opcional): acumula sobre lo ya guardado y respeta su orden.
    ruta_meta = f'{base}/metadata_nodos_{anio}.csv'
    meta_filas, cols_meta = {}, None
    if guardar_metadatos and os.path.exists(ruta_meta):
        prev = pd.read_csv(ruta_meta)
        cols_meta = list(prev.columns)
        meta_filas = {int(r['nodo_id']): r.to_dict() for _, r in prev.iterrows()}

    tope = False
    for nodo_id in faltantes:
        lat = coords.loc[nodo_id, 'latitude']
        lon = coords.loc[nodo_id, 'longitude']
        estado, meta = descargar_nodo(nodo_id, lat, lon, anio, crudos, api_key, email,
                                      meta_modo=metadatos, leap_day=leap_day)
        if estado == 'EXITO':
            with open(log, 'a') as f:
                f.write(f"{nodo_id}\n")
            if meta:
                meta_filas[nodo_id] = meta
            print(f"  ✅ {nodo_id}")
        elif estado == 'LIMITE':
            print("🛑 Límite diario de la API alcanzado. Progreso guardado.")
            tope = True
            break
        time.sleep(pausa)

    if guardar_metadatos and meta_filas:
        n = guardar_metadata(ruta_meta, meta_filas, cols_meta)
        print(f"📄 Metadatos del año: {ruta_meta} ({n} nodos)")

    faltan_final = sum(1 for n in coords.index if n not in ids_presentes(crudos))
    print(f"Parche finalizado. Faltantes restantes: {faltan_final}")
    return {'limite': tope, 'faltantes': faltan_final}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Recupera nodos faltantes de un año (Tamaulipas).")
    ap.add_argument('--anio', type=int, required=True)
    ap.add_argument('--pausa', type=float, default=1.0)
    ap.add_argument('--metadatos', choices=['todos', 'cambian'], default=None,
                    help="Captura y fusiona la metadata de los nodos recuperados "
                         "(igual que descargar_anio). Por defecto no guarda nada.")
    ap.add_argument('--excluir-bisiesto', action='store_true',
                    help="Excluye el 29-feb (debe coincidir con cómo se bajó el año).")
    args = ap.parse_args()
    main(args.anio, pausa=args.pausa, metadatos=args.metadatos,
         leap_day=not args.excluir_bisiesto)
