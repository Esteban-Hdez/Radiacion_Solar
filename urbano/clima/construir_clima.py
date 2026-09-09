"""
Genera las series climáticas por ciudad (horaria y diaria).

    conda run -n rs python -m urbano.clima.construir_clima
    conda run -n rs python -m urbano.clima.construir_clima --top 5
    conda run -n rs python -m urbano.clima.construir_clima \
        --variables temperature relative_humidity --anios 2023 2024
    conda run -n rs python -m urbano.clima.construir_clima --horario-csv
    conda run -n rs python -m urbano.clima.construir_clima --simple
    conda run -n rs python -m urbano.clima.construir_clima --ambito cabeceras
    conda run -n rs python -m urbano.clima.construir_clima --ambito global
    conda run -n rs python -m urbano.clima.construir_clima --todos-los-ambitos

`--simple` usa el promedio SIN ponderar (todos los nodos de la ciudad cuentan
igual) y escribe a archivos con sufijo `_simple`, para que ambos modos puedan
convivir sin pisarse.

`--ambito` cambia la UNIDAD de la serie —cabeceras, otras localidades, todas,
conglomerados urbanos o el estado entero— y nombra los archivos según el ámbito.
Sin `--ambito`, se usan las `--top N` localidades de mayor área. Ver
`urbano.clima.consulta` para el detalle de cada ámbito.

Requiere haber corrido antes `python -m urbano.construir` (que produce los pesos
nodo↔ciudad) y tener los parquet anuales en `Data/Tamaulipas/<anio>/Finales/`.
"""
from __future__ import annotations
import argparse
import os

import pandas as pd

from urbano import config as C
from urbano.clima import agregacion as G
from urbano.clima import consulta as Q
from urbano.clima import variables as V


def main(top: int | None = C.TOP_CIUDADES, cvegeos=None,
         variables=V.POR_OMISION, anios=C.ANIOS_CLIMA,
         horario_csv: bool = False, decimales: int = 3,
         ponderar: bool = True, ambito: str | None = None) -> None:
    variables = V.validar(variables)
    os.makedirs(C.DIR_CLIMA, exist_ok=True)

    # El ámbito manda sobre --top: define él mismo cuáles son sus unidades.
    if ambito:
        pesos = Q.pesos(ambito)
        etiqueta = ambito
    else:
        pesos = G.cargar_pesos(cvegeos, top)
        etiqueta = "ciudades"
    print(f"[clima] ámbito '{etiqueta}' · {pesos['cvegeo'].nunique()} unidades · "
          f"{pesos['nodo_id'].nunique()} nodos · {len(anios)} años · "
          f"{len(variables)} variables · "
          f"promedio {'ponderado por área urbana' if ponderar else 'SIMPLE'}")

    horaria = G.serie_horaria(variables, anios=anios, pesos=pesos,
                              ponderar=ponderar)
    print(f"[clima] serie horaria: {len(horaria):,} filas "
          f"({horaria['datetime_utc'].min():%Y-%m-%d} → "
          f"{horaria['datetime_utc'].max():%Y-%m-%d} UTC)")

    diario = G.resumen_diario(horaria, variables)
    print(f"[clima] resumen diario: {len(diario):,} filas")

    ruta_diario = C.ruta_clima(C.csv_clima_diario(etiqueta), ponderar)
    ruta_horario_pq = C.ruta_clima(C.parquet_clima_horario(etiqueta), ponderar)
    ruta_horario_csv = C.ruta_clima(C.csv_clima_horario(etiqueta), ponderar)

    num = diario.select_dtypes("number").columns.drop("n_horas", errors="ignore")
    diario[num] = diario[num].round(decimales)
    diario.to_csv(ruta_diario, index=False)
    print(f"[csv] {ruta_diario}  ({os.path.getsize(ruta_diario)/1e6:.1f} MB)")

    horaria.to_parquet(ruta_horario_pq, index=False)
    print(f"[parquet] {ruta_horario_pq}  "
          f"({os.path.getsize(ruta_horario_pq)/1e6:.1f} MB)")

    if horario_csv:
        h = horaria.copy()
        cols = [c for c in h.select_dtypes("number").columns]
        h[cols] = h[cols].round(decimales)
        h.to_csv(ruta_horario_csv, index=False)
        print(f"[csv] {ruta_horario_csv}  "
              f"({os.path.getsize(ruta_horario_csv)/1e6:.1f} MB)")

    # Días con menos de 24 h: los bordes del periodo y los cambios de horario.
    incompletos = (diario["n_horas"] != 24).sum()
    print(f"\n{incompletos} días con != 24 h (bordes del periodo y cambios de "
          f"horario de verano); fíltralos con `n_horas == 24` si te estorban.")
    resumen = diario.groupby("ciudad")["temperature_media"].agg(
        ["count", "mean", "min", "max"]).round(2)
    print(resumen.head(15).to_string())
    if len(resumen) > 15:
        print(f"… y {len(resumen) - 15} unidades más")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=C.TOP_CIUDADES,
                    help="N ciudades de mayor área urbana (por omisión 12)")
    ap.add_argument("--ciudades", nargs="+", default=None,
                    help="claves cvegeo concretas; anula --top")
    ap.add_argument("--variables", nargs="+", default=list(V.POR_OMISION),
                    help=f"por omisión: {' '.join(V.POR_OMISION)}")
    ap.add_argument("--anios", nargs="+", type=int, default=list(C.ANIOS_CLIMA))
    ap.add_argument("--horario-csv", action="store_true",
                    help="además del parquet, escribe el horario como CSV")
    ap.add_argument("--simple", action="store_true",
                    help="promedio simple entre nodos (sin ponderar por área "
                         "urbana); escribe a archivos con sufijo _simple")
    ap.add_argument("--ambito", choices=Q.AMBITOS, default=None,
                    help="unidad de la serie; anula --top y --ciudades")
    ap.add_argument("--todos-los-ambitos", action="store_true",
                    help="genera un juego de archivos por cada ámbito")
    a = ap.parse_args()
    ambitos = list(Q.AMBITOS) if a.todos_los_ambitos else [a.ambito]
    for amb in ambitos:
        main(None if (a.ciudades or amb) else a.top, None if amb else a.ciudades,
             a.variables, a.anios, a.horario_csv, ponderar=not a.simple,
             ambito=amb)
        print()
