"""
Comparación NSRDB vs ERA5 en los mismos 43 nodos.

    conda run -n rs python -m copernicus.comparar --anios 2024 --meses 1

Cruza hora a hora, **en UTC**, las series de las tres fuentes y calcula sesgo,
MAE, RMSE y correlación por nodo y variable. No hay conversión de huso: las tres
vienen en UTC y convertirlas solo añadiría oportunidades de error.

## ⚠ Las dos fuentes NO etiquetan la hora igual: usa `--alinear`

Estar las dos en UTC no basta para que casen. Cada una pone la etiqueta en un
extremo distinto del intervalo horario:

- **NSRDB** etiqueta con el **inicio**: el valor `12:00` es el promedio de
  12:00–13:00.
- **ERA5** acumula `ssrd` sobre la hora anterior y etiqueta con el **final**: el
  valor `13:00` es lo acumulado entre 12:00 y 13:00.

El mismo intervalo físico lleva dos etiquetas distintas, así que el merge directo
—`on=["nodo_id", "datetime_utc"]`— empareja la hora `t` de ERA5 con la hora `t`
del NSRDB, que es en realidad la `t−1` de ERA5. La comparación sale desplazada un
paso completo.

Se ve en el perfil diurno medio (junio 2024, Victoria, W/m²): ERA5 en `t` es el
NSRDB en `t−1`.

| hora UTC | NSRDB | ERA5-Land |
|---|---|---|
| 12 | 66.4 | 0.4 |
| 13 | 227.6 | 65.2 |
| 14 | 395.1 | 225.5 |

Y lo que cuesta no corregirlo, en Victoria 2024:

| variable | RMSE sin alinear | RMSE alineado |
|---|---|---|
| `ghi` | 121.11 W/m² | **75.71 W/m²** (−37 %) |
| `temperature` | 3.93 °C | 3.37 °C |
| `pressure` | 25.62 mbar | 25.61 mbar |

**Por qué el parámetro es opcional y no el comportamiento por omisión**: las
cifras ya publicadas en `copernicus/README.md` se midieron sin alinear, y cambiar
el default en silencio las volvería irreproducibles sin avisar a nadie. Así que
`alinear=False` sigue siendo lo de fábrica, pero la salida dice siempre en qué
modo se calculó y el CLI lo avisa en pantalla. **Para medir de verdad la
discrepancia entre fuentes hay que pasar `--alinear`.**

**El matiz que hay que respetar**: la hora exacta solo aplica al **GHI**, que
viene de la acumulación. En las instantáneas de ERA5 (`t2m`, `sp`, `u10`, `v10`)
el desajuste frente al NSRDB —media de `[t, t+1)`, centrada en `t+30min`— es de
**media hora**, y con datos horarios no se puede resolver medio paso: alinear
mejora el resultado pero no lo deja exacto. Es una aproximación que hay que
elegir y documentar, no mezclar entre análisis.

## Qué NO es una comparación limpia

Conviene tenerlo delante al leer la tabla, porque parte de la diferencia no es
"error" de ninguna fuente sino que se está comparando cosas distintas:

- **Viento**: ERA5 lo da a **10 m**, NSRDB a **2 m**. Son alturas distintas; el
  viento crece con la altura, así que ERA5 saldrá sistemáticamente más alto. Se
  reporta igual, marcado, pero no debe leerse como sesgo del modelo.
- **Humedad relativa**: ninguna de las dos la mide. NSRDB la deriva de
  T2M+QV2M+PS; aquí de T2M+Td. Parte de la diferencia es de fórmula.
- **Resolución y altitud**: la celda de ERA5 (9 o 31 km) promedia un terreno que
  el nodo NSRDB (4 km) no. Con nodos de 6 a 2140 m, y a −6.5 °C/km, el desnivel
  entre el nodo y la celda explica por sí solo varios grados. Por eso la salida
  arrastra `dist_celda_km`.

## La dirección del viento es circular

Restar 350° − 10° da 340, no −20. La diferencia se envuelve a [−180, 180] y el
sesgo se promedia como vector; el RMSE lineal de un ángulo no significa nada.
"""
from __future__ import annotations
import argparse
import os

import numpy as np
import pandas as pd

from copernicus import config as C
from copernicus import extraer as E

VARIABLES = ["temperature", "relative_humidity", "dew_point", "pressure",
             "ghi", "wind_speed", "wind_direction"]

# Variables donde las dos fuentes NO miden lo mismo (ver docstring).
NO_COMPARABLES = {
    "wind_speed": "ERA5 a 10 m vs NSRDB a 2 m",
    "wind_direction": "ERA5 a 10 m vs NSRDB a 2 m",
    "relative_humidity": "derivada con fórmulas distintas en cada fuente",
}


def cargar_nsrdb(nodos: list[int], desde: str, hasta: str) -> pd.DataFrame:
    """Serie horaria del NSRDB para los mismos nodos, vía `urbano.clima`."""
    from urbano.clima import consulta as Q
    h = Q.serie([v for v in VARIABLES if v != "ghi"] + ["ghi"],
                nodo=nodos, desde=desde, hasta=hasta)
    h["nodo_id"] = h["ciudad"].str.removeprefix("nodo ").astype(int)
    cols = ["nodo_id", "cve_mun", "municipio", "datetime_utc"] + VARIABLES
    return h[cols]


def _dif_circular(a, b):
    """(a − b) envuelto a [−180, 180]."""
    return (np.asarray(a) - np.asarray(b) + 180.0) % 360.0 - 180.0


def cruzar(anios, meses, productos=("land", "single"),
           alinear: bool = False) -> pd.DataFrame:
    """
    Tabla larga con una fila por (nodo, hora, producto) y las dos fuentes.

    `alinear=True` resta una hora a la marca de tiempo de ERA5 antes del merge,
    para que las dos fuentes describan el MISMO intervalo físico (ver el
    docstring del módulo: el NSRDB etiqueta el inicio y ERA5 el final). Es la
    diferencia entre medir la discrepancia entre fuentes y medirla sumada a un
    desplazamiento de un paso.

    Conviene pensarlo como "reetiquetar ERA5", no como un `shift` con signo, que
    es donde uno se equivoca: el valor de ERA5 rotulado 13:00 describe el
    intervalo 12:00–13:00, que el NSRDB rotula 12:00.

    La columna `alineado` marca la tabla resultante, para que una salida guardada
    no se pueda leer luego sin saber en qué modo se calculó.
    """
    partes = []
    for producto in productos:
        for anio in anios:
            for mes in meses:
                ruta = os.path.join(C.dir_series(producto),
                                    f"{producto}_{anio}_{mes:02d}.parquet")
                if not os.path.exists(ruta):
                    print(f"[cmp] falta {os.path.basename(ruta)}, se salta")
                    continue
                partes.append(pd.read_parquet(ruta))
    if not partes:
        raise FileNotFoundError(
            "No hay series de ERA5 extraídas. Corre antes "
            "`python -m copernicus.extraer --producto <p> --anios ... --meses ...`")
    era5 = pd.concat(partes, ignore_index=True)
    # Defensa por si algún parquet viene de una versión anterior sin zona.
    era5["datetime_utc"] = pd.to_datetime(era5["datetime_utc"], utc=True)

    if alinear:
        # Reetiquetado, no desplazamiento del dato: el valor que ERA5 rotula
        # 13:00 describe el intervalo 12:00-13:00, que es el que el NSRDB rotula
        # 12:00. Se hace ANTES de calcular el rango para que el periodo que se le
        # pide al NSRDB sea ya el de las etiquetas nuevas.
        era5["datetime_utc"] -= pd.Timedelta(hours=1)

    lo = era5["datetime_utc"].min()
    hi = era5["datetime_utc"].max()
    nsrdb = cargar_nsrdb(sorted(era5["nodo_id"].unique()),
                         lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d"))

    j = era5.merge(nsrdb, on=["nodo_id", "datetime_utc"],
                   suffixes=("_era5", "_nsrdb"), how="inner")
    if j.empty:
        raise ValueError("El cruce quedó vacío: ¿coinciden los periodos?")
    # Viaja con la tabla: una salida guardada no debe poder leerse después sin
    # saber si las horas estaban alineadas o no.
    j["alineado"] = bool(alinear)
    return j


def metricas(j: pd.DataFrame, por=("producto", "nodo_id")) -> pd.DataFrame:
    """
    Sesgo, MAE, RMSE y correlación de ERA5 respecto al NSRDB.

    La columna `alineado` se arrastra desde `cruzar`: sin ella, dos tablas de
    métricas calculadas en modos distintos son indistinguibles a simple vista y
    difieren en un 37 % en el GHI.
    """
    # `False` cuando la tabla viene de una versión anterior, que es lo que
    # aquellas hacían.
    alineado = bool(j["alineado"].iloc[0]) if "alineado" in j else False
    filas = []
    for llaves, g in j.groupby(list(por), sort=True):
        llaves = llaves if isinstance(llaves, tuple) else (llaves,)
        for v in VARIABLES:
            a, b = g[f"{v}_era5"], g[f"{v}_nsrdb"]
            ok = a.notna() & b.notna()
            if ok.sum() < 2:
                continue
            a, b = a[ok].to_numpy(), b[ok].to_numpy()
            if v == "wind_direction":
                d = _dif_circular(a, b)
                # La correlación lineal de un ángulo no significa nada.
                corr = np.nan
            else:
                d = a - b
                corr = float(np.corrcoef(a, b)[0, 1])
            filas.append({
                **dict(zip(por, llaves)),
                "variable": v,
                "n": int(ok.sum()),
                "sesgo": float(np.mean(d)),
                "mae": float(np.mean(np.abs(d))),
                "rmse": float(np.sqrt(np.mean(d ** 2))),
                "corr": corr,
                "comparable": v not in NO_COMPARABLES,
                "alineado": alineado,
                "nota": NO_COMPARABLES.get(v, ""),
            })
    return pd.DataFrame(filas)


def resumen(j: pd.DataFrame) -> pd.DataFrame:
    """Una fila por producto y variable, sobre todos los nodos juntos."""
    return (metricas(j, por=("producto",))
            .sort_values(["variable", "producto"])
            .reset_index(drop=True))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anios", nargs="+", type=int, default=[2024])
    ap.add_argument("--meses", nargs="+", type=int, default=[1])
    ap.add_argument("--productos", nargs="+", default=["land", "single"])
    ap.add_argument("--alinear", action="store_true",
                    help="reetiqueta ERA5 una hora atrás para que las dos "
                         "fuentes describan el mismo intervalo (exacto en GHI, "
                         "aproximado en las instantáneas). RECOMENDADO para "
                         "medir la discrepancia real entre fuentes.")
    a = ap.parse_args()

    pd.set_option("display.width", 200)
    j = cruzar(a.anios, a.meses, a.productos, alinear=a.alinear)
    print(f"\n{len(j):,} horas cruzadas · {j['nodo_id'].nunique()} nodos · "
          f"{j['datetime_utc'].min()} .. {j['datetime_utc'].max()}")
    print(f"horas alineadas: {'SÍ' if a.alinear else 'NO'}\n")
    r = resumen(j)
    print(r[["producto", "variable", "n", "sesgo", "mae", "rmse", "corr",
             "comparable"]].round(3).to_string(index=False))
    print("\nNotas:")
    for v, nota in NO_COMPARABLES.items():
        print(f"  {v}: {nota}")
    if not a.alinear:
        # El aviso va al final, donde queda a la vista junto a la tabla que
        # califica, y no arriba donde el scroll se lo lleva.
        print("\n⚠ SIN ALINEAR: el NSRDB etiqueta el inicio del intervalo horario"
              " y ERA5 el final,\n  así que estas cifras incluyen un desfase de un"
              " paso y SOBRESTIMAN la\n  discrepancia (en GHI, ~37 %). Repite con"
              " --alinear para medirla de verdad.")
