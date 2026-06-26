"""
Orquestador: descarga SECUENCIAL de varios años de Tamaulipas hasta agotar la
cuota diaria de la API (10000 peticiones).

Para cada año, en orden:
  1. Descarga masiva (reanudable).
  2. Parche de faltantes, hasta 2 intentos. Si tras 2 parches aún faltan nodos
     (por fallas de red, no por límite), se OMITE la consolidación y se pasa al
     siguiente año.
  3. Si están los 4384 nodos, consolida el dataset COMPLETO del año.

Si en cualquier momento la API responde 429 (límite diario agotado), el proceso se
detiene de forma segura: todo el progreso queda guardado y es reanudable al día
siguiente volviendo a ejecutar el mismo comando (los años/nodos ya completos se
saltan automáticamente).

Solo el año 2018 guarda los metadatos que varían por nodo (`--metadatos cambian`).

Ejecutar como módulo desde la raíz:
    python -m Utils.descarga_regiones.descargar_varios_anios --anios 2018 2019 2020
"""

import os
import argparse

from Utils.descarga_regiones import descargar_anio, parche_anio, consolidar_anio
from Utils.descarga_regiones._comun import cargar_coordenadas_finales, rutas_anio, ids_presentes

MAX_PARCHES = 2
ANIO_METADATOS = 2018          # único año que guarda metadatos (modo 'cambian')


def _faltan(anio, total):
    _, crudos, _ = rutas_anio(anio)
    return total - len(ids_presentes(crudos))


def main(anios, pausa=1.0):
    total = len(cargar_coordenadas_finales())   # 4384
    print(f"### PROCESO MULTI-AÑO TAMAULIPAS ### años={anios} | nodos/año={total}\n")

    for anio in anios:
        print(f"\n{'#'*64}\n#  AÑO {anio}\n{'#'*64}")

        # 1) Descarga masiva
        meta = 'cambian' if anio == ANIO_METADATOS else None
        res = descargar_anio.main(anio, metadatos=meta, pausa=pausa)
        if res['limite']:
            print(f"\n🛑 Límite diario agotado durante la descarga de {anio}. "
                  f"Fin de la sesión (reanudar mañana con el mismo comando).")
            return

        # 2) Parche, hasta MAX_PARCHES veces
        detener = False
        for intento in range(1, MAX_PARCHES + 1):
            if _faltan(anio, total) == 0:
                break
            print(f"\n-- Parche {intento}/{MAX_PARCHES} para {anio} --")
            rp = parche_anio.main(anio, pausa=pausa)
            if rp['limite']:
                print(f"\n🛑 Límite diario agotado durante el parche de {anio}. Fin de la sesión.")
                detener = True
                break
        if detener:
            return

        # 3) Consolidar si está completo
        faltan = _faltan(anio, total)
        base, _, _ = rutas_anio(anio)
        out = f'{base}/Finales/completo/dataset_tamaulipas_completo_24h_{anio}.parquet'
        if faltan == 0:
            if os.path.exists(out):
                print(f"\n✅ {anio} completo y ya consolidado ({out}). Se omite.")
            else:
                print(f"\n✅ {anio} completo ({total} nodos). Consolidando...")
                consolidar_anio.main(anio)
        else:
            print(f"\n⚠️ {anio} quedó con {faltan} nodos faltantes tras {MAX_PARCHES} "
                  f"parches. Se OMITE la consolidación y se pasa al siguiente año.")

    print(f"\n{'='*64}\n=== PROCESO MULTI-AÑO FINALIZADO ===\n{'='*64}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Descarga secuencial de varios años de Tamaulipas (hasta agotar la cuota diaria).")
    ap.add_argument('--anios', type=int, nargs='+', default=[2018, 2019, 2020],
                    help="Lista de años en orden. Def: 2018 2019 2020.")
    ap.add_argument('--pausa', type=float, default=1.0, help="Segundos entre peticiones (def: 1.0).")
    args = ap.parse_args()
    main(args.anios, pausa=args.pausa)
