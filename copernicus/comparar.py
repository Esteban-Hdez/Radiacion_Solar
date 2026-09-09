"""
Comparación NSRDB vs ERA5 en los mismos 43 nodos.

    conda run -n rs python -m copernicus.comparar --anios 2024 --meses 1

Cruza hora a hora, **en UTC**, las series de las tres fuentes y calcula sesgo,
MAE, RMSE y correlación por nodo y variable. No hay conversión de huso: las tres
vienen en UTC y convertirlas solo añadiría oportunidades de error.

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


def cruzar(anios, meses, productos=("land", "single")) -> pd.DataFrame:
    """Tabla larga con una fila por (nodo, hora, producto) y las dos fuentes."""
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

    lo = era5["datetime_utc"].min()
    hi = era5["datetime_utc"].max()
    nsrdb = cargar_nsrdb(sorted(era5["nodo_id"].unique()),
                         lo.strftime("%Y-%m-%d"), hi.strftime("%Y-%m-%d"))

    j = era5.merge(nsrdb, on=["nodo_id", "datetime_utc"],
                   suffixes=("_era5", "_nsrdb"), how="inner")
    if j.empty:
        raise ValueError("El cruce quedó vacío: ¿coinciden los periodos?")
    return j


def metricas(j: pd.DataFrame, por=("producto", "nodo_id")) -> pd.DataFrame:
    """Sesgo, MAE, RMSE y correlación de ERA5 respecto al NSRDB."""
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
    a = ap.parse_args()

    pd.set_option("display.width", 200)
    j = cruzar(a.anios, a.meses, a.productos)
    print(f"\n{len(j):,} horas cruzadas · {j['nodo_id'].nunique()} nodos · "
          f"{j['datetime_utc'].min()} .. {j['datetime_utc'].max()}\n")
    r = resumen(j)
    print(r[["producto", "variable", "n", "sesgo", "mae", "rmse", "corr",
             "comparable"]].round(3).to_string(index=False))
    print("\nNotas:")
    for v, nota in NO_COMPARABLES.items():
        print(f"  {v}: {nota}")
