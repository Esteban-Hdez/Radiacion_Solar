"""
Orquestador multi-REGIÓN / multi-AÑO (Tamaulipas y Puerto Rico).

Misma lógica que `Utils.descarga_regiones.descargar_varios_anios`, pero recorre una
o varias regiones. Por cada (región, año), en orden:
  1. Descarga masiva (reanudable).
  2. Parche de faltantes, hasta 2 intentos; si tras 2 aún faltan (por red), se omite
     la consolidación y se pasa al siguiente.
  3. Si están todos los nodos, consolida el dataset COMPLETO.
Si la API agota la cuota diaria (429), se detiene de forma segura (reanudable).

Estructura creada por región:
  Data/Tamaulipas/<anio>/...        (4384 nodos)
  Data/Puerto_Rico/<anio>/...       (754 nodos)

Ejemplo (esta noche): 2024 para ambas regiones, guardando todos los metadatos:
  python -m Utils.descarga_regiones --regiones tamaulipas puerto_rico --anios 2024 --metadatos todos
"""

import os
import argparse

from Utils.descarga_regiones import descargar_anio, parche_anio, consolidar_anio
from Utils.descarga_regiones._comun import cargar_coordenadas_finales, rutas_anio, ids_presentes

MAX_PARCHES = 2

REGIONES = {
    'tamaulipas': {'metadata': 'Data/Tamaulipas/metadata_nodos_tamaulipas.csv',
                   'raiz': 'Data/Tamaulipas', 'tag': 'tamaulipas'},
    'puerto_rico': {'metadata': 'Data/Puerto_Rico/metadata_nodos_pr.csv',
                    'raiz': 'Data/Puerto_Rico', 'tag': 'pr'},
}


def _faltan(anio, raiz, total):
    _, crudos, _ = rutas_anio(anio, raiz)
    return total - len(ids_presentes(crudos))


def main(regiones, anios, metadatos='todos', pausa=1.0, leap_day=True):
    print(f"### MULTI-REGIÓN ### regiones={regiones} | años={anios} | "
          f"metadatos={metadatos} | 29-feb={'incluido' if leap_day else 'excluido'}\n")
    for region in regiones:
        cfg = REGIONES[region]
        total = len(cargar_coordenadas_finales(cfg['metadata']))
        print(f"\n{'='*64}\n=== REGIÓN: {region.upper()}  ({total} nodos)\n{'='*64}")

        for anio in anios:
            print(f"\n{'#'*60}\n#  {region} · AÑO {anio}\n{'#'*60}")

            # 1) Descarga
            res = descargar_anio.main(anio, metadatos=metadatos, pausa=pausa,
                                      metadata=cfg['metadata'], raiz=cfg['raiz'],
                                      leap_day=leap_day)
            if res['limite']:
                print(f"\n🛑 Cuota diaria agotada en {region} {anio}. "
                      f"Fin de la sesión (reanudar con el mismo comando).")
                return

            # 2) Parche (máx. MAX_PARCHES)
            detener = False
            for intento in range(1, MAX_PARCHES + 1):
                if _faltan(anio, cfg['raiz'], total) == 0:
                    break
                print(f"\n-- Parche {intento}/{MAX_PARCHES}: {region} {anio} --")
                rp = parche_anio.main(anio, pausa=pausa,
                                      metadata=cfg['metadata'], raiz=cfg['raiz'],
                                      metadatos=metadatos, leap_day=leap_day)
                if rp['limite']:
                    print(f"\n🛑 Cuota diaria agotada en parche {region} {anio}. Fin de la sesión.")
                    detener = True
                    break
            if detener:
                return

            # 3) Consolidar si está completo
            faltan = _faltan(anio, cfg['raiz'], total)
            base, _, _ = rutas_anio(anio, cfg['raiz'])
            out = f"{base}/Finales/completo/dataset_{cfg['tag']}_completo_24h_{anio}.parquet"
            if faltan == 0:
                if os.path.exists(out):
                    print(f"\n✅ {region} {anio} completo y ya consolidado. Se omite.")
                else:
                    print(f"\n✅ {region} {anio} completo ({total} nodos). Consolidando...")
                    consolidar_anio.main(anio, raiz=cfg['raiz'], tag=cfg['tag'],
                                         metadata=cfg['metadata'], leap_day=leap_day)
            else:
                print(f"\n⚠️ {region} {anio} quedó con {faltan} faltantes tras {MAX_PARCHES} "
                      f"parches. Se omite la consolidación y se continúa.")

    print(f"\n{'='*64}\n=== PROCESO MULTI-REGIÓN FINALIZADO ===\n{'='*64}")


def _cli():
    ap = argparse.ArgumentParser(description="Descarga NSRDB v4 por región(es) y año(s).")
    ap.add_argument('--regiones', nargs='+', default=['tamaulipas'],
                    choices=list(REGIONES), help="Regiones a procesar.")
    ap.add_argument('--anios', type=int, nargs='+', required=True, help="Años a descargar.")
    ap.add_argument('--metadatos', choices=['todos', 'cambian'], default=None,
                    help="Guarda metadata por año: 'todos' (47 campos) o 'cambian' (por nodo).")
    ap.add_argument('--pausa', type=float, default=1.0)
    ap.add_argument('--excluir-bisiesto', action='store_true',
                    help="Excluye el 29-feb (años homogéneos de 8760 h). Por defecto se incluye.")
    args = ap.parse_args()
    main(args.regiones, args.anios, metadatos=args.metadatos, pausa=args.pausa,
         leap_day=not args.excluir_bisiesto)


if __name__ == "__main__":
    _cli()
